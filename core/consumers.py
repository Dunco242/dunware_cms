import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Connects to the WebSocket chat session."""
        try:
            self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
            self.room_group_name = f"chat_{self.session_id}"

            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            logger.info(f"WebSocket connected for session {self.session_id}")

        except Exception as e:
            logger.error(f"Error connecting ChatConsumer: {str(e)}")
            await self.close()

    async def disconnect(self, close_code):
        """Disconnects from WebSocket and removes the user from the chat group."""
        try:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            logger.info(f"WebSocket disconnected for session {self.session_id}")

        except Exception as e:
            logger.error(f"Error disconnecting ChatConsumer: {str(e)}")

    async def receive(self, text_data):
        """Handles incoming WebSocket messages (e.g., new messages)."""
        try:
            from .models import ChatSession, Employee, ChatMessage, ChatNotification  # ✅ Lazy Import

            data = json.loads(text_data)
            message_type = data.get("type")

            if message_type == "new_message":
                message = await self.save_message(
                    session_id=data["session_id"],
                    sender_id=data["sender_id"],
                    receiver_id=data["receiver_id"],
                    content=data["content"]
                )

                if message:
                    message_data = await self.get_message_data(message)

                    # Broadcast new message to chat room
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "chat_message",
                            "message": message_data
                        }
                    )

                    # Send notification to recipient
                    await self.channel_layer.group_send(
                        f'notifications_{data["receiver_id"]}',
                        {
                            "type": "notification_message",
                            "message": message_data
                        }
                    )

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": "Invalid message format"
            }))
        except Exception as e:
            logger.error(f"Error in receive: {str(e)}")
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": str(e)
            }))

    async def chat_message(self, event):
        """Sends a new chat message to WebSocket clients."""
        try:
            await self.send(text_data=json.dumps({
                "type": "chat_message",
                "message": event["message"]
            }))
            logger.info(f"Message sent to chat session {self.session_id}")

        except Exception as e:
            logger.error(f"Error sending chat message: {str(e)}")

    async def notification_message(self, event):
        """Sends a new message notification to WebSocket clients."""
        try:
            await self.send(text_data=json.dumps({
                "type": "new_message",
                "message": event["message"]
            }))
            logger.info(f"Notification sent for new message in session {self.session_id}")

        except Exception as e:
            logger.error(f"Error sending notification message: {str(e)}")

    @database_sync_to_async
    def save_message(self, session_id, sender_id, receiver_id, content):
        """Saves a new chat message asynchronously."""
        from .models import ChatSession, Employee, ChatMessage, ChatNotification  # ✅ Lazy Import

        try:
            session = ChatSession.objects.get(id=session_id)
            sender = Employee.objects.get(employee_id=sender_id)
            receiver = Employee.objects.get(employee_id=receiver_id)

            message = ChatMessage.objects.create(
                session=session,
                sender=sender,
                receiver=receiver,
                content=content,
                timestamp=timezone.now()
            )

            # Update session timestamp
            session.updated_at = timezone.now()
            session.save()

            # Create a new chat notification
            ChatNotification.objects.create(
                recipient=receiver,
                message=message,
                is_seen=False
            )

            return message
        except Exception as e:
            logger.error(f"Error saving message: {str(e)}")
            return None

    @database_sync_to_async
def get_message_data(self, message):
    """Get message data in a format suitable for JSON serialization"""
    try:
        # Get sender name info
        sender_name = ""
        if hasattr(message.sender, 'user') and message.sender.user:
            sender_name = f"{message.sender.user.first_name} {message.sender.user.last_name}".strip()
            if not sender_name:
                sender_name = message.sender.user.username

        return {
            'id': message.id,
            'content': message.content,
            'sender': {
                'id': message.sender.employee_id,
                'name': sender_name  # Include sender name in the response
            },
            'receiver': {
                'id': message.receiver.employee_id,
                'name': f"{message.receiver.user.first_name} {message.receiver.user.last_name}".strip()
            },
            'timestamp': message.timestamp.isoformat(),
            'is_read': message.is_read
        }
    except Exception as e:
        logger.error(f"Error in get_message_data: {str(e)}")
        # Return minimal data to avoid breaking the app
        return {
            'id': message.id,
            'content': message.content,
            'sender': {
                'id': getattr(message.sender, 'employee_id', 'unknown'),
                'name': 'Unknown'
            },
            'receiver': {
                'id': getattr(message.receiver, 'employee_id', 'unknown'),
                'name': 'Unknown'
            },
            'timestamp': message.timestamp.isoformat(),
            'is_read': message.is_read
        }

    @database_sync_to_async
    def mark_message_as_read(self, message_id):
        """Marks a message as read asynchronously."""
        from .models import ChatMessage  # ✅ Lazy Import
        try:
            ChatMessage.objects.filter(id=message_id).update(
                is_read=True,
                read_at=timezone.now()
            )
            logger.info(f"Message {message_id} marked as read.")

        except Exception as e:
            logger.error(f"Error marking message as read: {str(e)}")


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
