import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.room_group_name = f"chat_{self.session_id}"

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"WebSocket connected for session {self.session_id}")

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"WebSocket disconnected for session {self.session_id}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'new_message':
                message = await self.save_message(
                    session_id=data['session_id'],
                    sender_id=data['sender_id'],
                    receiver_id=data['receiver_id'],
                    content=data['content']
                )

                if message:
                    message_data = await self.get_message_data(message)
                    # Broadcast to room group
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'chat_message',
                            'message': message_data
                        }
                    )

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid message format'
            }))
        except Exception as e:
            logger.error(f"Error in receive: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message']
        }))

    @database_sync_to_async
    def get_message_data(self, message):
        return {
            'id': message.id,
            'content': message.content,
            'sender': {
                'id': message.sender.employee_id,
                'name': message.sender.get_full_name()
            },
            'timestamp': message.timestamp.isoformat(),
            'is_read': message.is_read
        }

    @database_sync_to_async
    def save_message(self, session_id, sender_id, receiver_id, content):
        from .models import ChatSession, ChatMessage, Employee
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

            return message
        except Exception as e:
            logger.error(f"Error saving message: {str(e)}")
            raise

    @database_sync_to_async
    def get_user(self, user_id):
        from .models import Employee
        return Employee.objects.get(id=user_id)

    @database_sync_to_async
    def get_session(self, session_id):
        from .models import ChatSession
        return ChatSession.objects.get(id=session_id)

    @database_sync_to_async
    def update_message_status(self, message_id, is_read=True):
        from .models import ChatMessage
        return ChatMessage.objects.filter(id=message_id).update(
            is_read=is_read,
            read_at=timezone.now() if is_read else None
        )
