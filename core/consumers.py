import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.user_id = self.scope["user"].id  # Get current user ID
        self.room_group_name = f"chat_{self.session_id}"

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        logger.info(f"WebSocket connected for session {self.session_id}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"WebSocket disconnected for session {self.session_id}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get("type")

            if message_type == "new_message":
                session_id = data["session_id"]
                sender_id = data["sender_id"]
                receiver_id = data.get("receiver_id", None)  # Receiver ID is optional for groups
                content = data["content"]

                # Get session details
                session = await self.get_chat_session(session_id)

                # Determine recipients
                if session.is_group_chat:
                    recipient_list = await self.get_group_members(session_id, sender_id)
                else:
                    recipient_list = [receiver_id]

                # Save message
                message = await self.save_message(session_id, sender_id, receiver_id, content)

                if message:
                    message_data = await self.get_message_data(message)

                    # Send message to recipients
                    for recipient_id in recipient_list:
                        recipient_room = f"chat_{session_id}_{recipient_id}"
                        await self.channel_layer.group_send(
                            recipient_room,
                            {
                                "type": "chat_message",
                                "message": message_data,
                            },
                        )

            elif message_type == "leave_chat":
                session_id = data["session_id"]
                user_id = data["user_id"]
                success = await self.leave_chat(session_id, user_id)

                if success:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "chat_message",
                            "message": {
                                "type": "info",
                                "content": f"User {user_id} has left the chat.",
                            },
                        }
                    )

        except Exception as e:
            logger.error(f"Error in receive: {str(e)}")
            await self.send(text_data=json.dumps({"type": "error", "message": str(e)}))

    async def chat_message(self, event):
        """Send message to WebSocket"""
        await self.send(text_data=json.dumps({
            "type": "chat_message",
            "message": event["message"],
        }))

    @database_sync_to_async
    def get_chat_session(self, session_id):
        """Retrieve a chat session from the database"""
        return ChatSession.objects.get(id=session_id)

    @database_sync_to_async
    def get_group_members(self, session_id, sender_id):
        """Retrieve group members excluding sender"""
        session = ChatSession.objects.get(id=session_id)
        return list(session.participants.exclude(id=sender_id).values_list("id", flat=True))

    @database_sync_to_async
    def save_message(self, session_id, sender_id, receiver_id, content):
        """Save chat message to the database"""
        session = ChatSession.objects.get(id=session_id)
        sender = Employee.objects.get(employee_id=sender_id)
        receiver = Employee.objects.get(employee_id=receiver_id) if receiver_id else None

        message = ChatMessage.objects.create(
            session=session,
            sender=sender,
            receiver=receiver,
            content=content,
        )

        session.updated_at = timezone.now()
        session.save()

        return message

    @database_sync_to_async
    def leave_chat(self, session_id, user_id):
        """Allow a user to leave a group chat"""
        session = ChatSession.objects.get(id=session_id)
        user = Employee.objects.get(employee_id=user_id)

        if session.is_group_chat:
            session.participants.remove(user)
            session.save()
            return True
        return False


class AddUserConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.room_group_name = f"chat_{self.session_id}_add_user"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        logger.info(f"WebSocket connected for user addition in session {self.session_id}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"WebSocket disconnected from user addition in session {self.session_id}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('type')

            if action == 'add_user':
                new_user_id = data.get('user_id')

                if new_user_id:
                    success, response = await self.add_user_to_chat(self.session_id, new_user_id)

                    if success:
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'user_added',
                                'user_id': new_user_id,
                                'message': response
                            }
                        )
                    else:
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'message': response
                        }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"Error in AddUserConsumer receive: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def user_added(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_added',
            'user_id': event['user_id'],
            'message': event['message']
        }))

    @database_sync_to_async
    def add_user_to_chat(self, session_id, user_id):
        """Add a user to a chat session asynchronously"""
        from .models import ChatSession, Employee  # ✅ Lazy Import
        try:
            session = ChatSession.objects.get(id=session_id)
            new_user = Employee.objects.get(employee_id=user_id)

            if new_user in session.participants.all():
                return False, "User is already in the chat."

            session.participants.add(new_user)

            return True, f"User {new_user.user.get_full_name()} added to chat successfully."
        except ChatSession.DoesNotExist:
            return False, "Chat session not found."
        except Employee.DoesNotExist:
            return False, "User not found."
        except Exception as e:
            logger.error(f"Error adding user to chat: {str(e)}")
            return False, str(e)


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.employee_id = self.scope['url_route']['kwargs']['employee_id']
        self.notification_group_name = f'notifications_{self.employee_id}'

        await self.channel_layer.group_add(
            self.notification_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.notification_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data['type'] == 'read_notifications':
                await self.mark_notifications_read()
        except json.JSONDecodeError:
            pass

    async def notification_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "new_message",
            "message": event["message"]
        }))

    @database_sync_to_async
    def mark_notifications_read(self):
        from .models import ChatNotification
        ChatNotification.objects.filter(recipient_id=self.employee_id, is_seen=False).update(is_seen=True)



logger = logging.getLogger('django')

class DebugConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info("DEBUG: WebSocket connection attempt received")
        try:
            await self.accept()
            logger.info("DEBUG: WebSocket connection accepted")
        except Exception as e:
            logger.error(f"DEBUG: Error accepting WebSocket connection: {str(e)}")
            raise

    async def disconnect(self, close_code):
        logger.info(f"DEBUG: WebSocket disconnected with code {close_code}")
