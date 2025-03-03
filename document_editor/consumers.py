import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)

class DocumentConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time document collaboration.
    Handles user presence, real-time edits, cursor positions, and document saving.
    """

    # Class-level tracking of connections
    active_documents = {}  # Document ID -> set of channel names
    active_users = {}      # User ID -> set of channel names

    async def connect(self):
        """Handle WebSocket connection establishment."""
        try:
            # Get the document ID from the URL
            self.document_id = self.scope['url_route']['kwargs']['document_id']
            self.user = self.scope['user']
            self.group_name = f'document_{self.document_id}'

            # Validate authentication
            if not self.user.is_authenticated:
                logger.warning(f"Unauthenticated connection attempt to document {self.document_id}")
                await self.close(code=4001)
                return

            # Verify document access permission
            has_permission = await self.check_document_permission()
            if not has_permission:
                logger.warning(f"User {self.user.id} attempted to access document {self.document_id} without permission")
                await self.close(code=4003)
                return

            # Join the document group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )

            # Track connection in class variables
            if self.document_id not in self.active_documents:
                self.active_documents[self.document_id] = set()
            self.active_documents[self.document_id].add(self.channel_name)

            if self.user.id not in self.active_users:
                self.active_users[self.user.id] = set()
            self.active_users[self.user.id].add(self.channel_name)

            # Create edit session record
            self.session_id = await self.create_edit_session()

            # Accept the connection
            await self.accept()

            # Notify others about the new user
            employee = await self.get_employee_profile()
            if employee:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'user_joined',
                        'user_id': self.user.id,
                        'user_name': employee.get('name', self.user.username),
                        'session_id': self.session_id,
                        'timestamp': timezone.now().isoformat(),
                    }
                )

            logger.info(f"User {self.user.id} connected to document {self.document_id}")

        except Exception as e:
            logger.error(f"Error in document WebSocket connection: {str(e)}", exc_info=True)
            await self.close(code=4000)

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection with proper cleanup."""
        try:
            # Remove from document group
            if hasattr(self, 'group_name') and hasattr(self, 'channel_name'):
                await self.channel_layer.group_discard(
                    self.group_name,
                    self.channel_name
                )

            # Cleanup tracking dictionaries
            if hasattr(self, 'document_id') and self.document_id in self.active_documents:
                self.active_documents[self.document_id].discard(self.channel_name)
                if not self.active_documents[self.document_id]:
                    del self.active_documents[self.document_id]

            if hasattr(self, 'user') and hasattr(self.user, 'id') and self.user.id in self.active_users:
                self.active_users[self.user.id].discard(self.channel_name)
                if not self.active_users[self.user.id]:
                    del self.active_users[self.user.id]

            # End edit session
            if hasattr(self, 'session_id'):
                await self.end_edit_session()

            # Notify group about user leaving
            if hasattr(self, 'group_name') and hasattr(self, 'user') and hasattr(self.user, 'id'):
                employee = await self.get_employee_profile()
                if employee:
                    await self.channel_layer.group_send(
                        self.group_name,
                        {
                            'type': 'user_left',
                            'user_id': self.user.id,
                            'user_name': employee.get('name', self.user.username),
                            'session_id': getattr(self, 'session_id', None),
                            'timestamp': timezone.now().isoformat(),
                        }
                    )

                logger.info(f"User {self.user.id} disconnected from document {self.document_id}")

        except Exception as e:
            logger.error(f"Error in document WebSocket disconnection: {str(e)}", exc_info=True)

    async def receive(self, text_data):
        """Handle incoming WebSocket data."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            # Process based on message type
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat(),
                }))
            elif message_type == 'save_document':
                await self.handle_save_document(data)
            else:
                logger.warning(f"Unknown message type: {message_type}")

            # Update session activity timestamp
            await self.update_session_activity()

        except json.JSONDecodeError:
            logger.warning(f"Received invalid JSON data from user {self.user.id}")
        except Exception as e:
            logger.error(f"Error handling WebSocket data: {str(e)}", exc_info=True)

    async def handle_save_document(self, data):
        """Process document save requests."""
        try:
            content = data.get('content')
            create_version = data.get('create_version', False)

            if content:
                # Save to database
                result = await self.save_document_content(content, create_version)

                # Send confirmation to the client
                await self.send(text_data=json.dumps({
                    'type': 'save_confirmed',
                    'success': result['success'],
                    'error': result.get('error'),
                    'version': result.get('version'),
                    'create_version': create_version,
                    'updated_at': result.get('updated_at'),
                    'timestamp': timezone.now().isoformat(),
                }))

                # Notify others about the save if successful
                if result.get('success'):
                    employee = await self.get_employee_profile()
                    await self.channel_layer.group_send(
                        self.group_name,
                        {
                            'type': 'document_saved',
                            'user_id': self.user.id,
                            'user_name': employee.get('name', self.user.username) if employee else self.user.username,
                            'version': result.get('version'),
                            'create_version': create_version,
                            'timestamp': timezone.now().isoformat(),
                        }
                    )
            else:
                await self.send(text_data=json.dumps({
                    'type': 'save_confirmed',
                    'success': False,
                    'error': 'No content provided',
                    'timestamp': timezone.now().isoformat(),
                }))

        except Exception as e:
            logger.error(f"Error saving document: {str(e)}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'save_confirmed',
                'success': False,
                'error': str(e),
                'timestamp': timezone.now().isoformat(),
            }))

    # Event handlers for broadcasting messages to clients

    async def user_joined(self, event):
        """Send user joined notification to WebSocket."""
        await self.send(text_data=json.dumps(event))

    async def user_left(self, event):
        """Send user left notification to WebSocket."""
        await self.send(text_data=json.dumps(event))

    async def document_saved(self, event):
        """Send document saved notification to WebSocket."""
        await self.send(text_data=json.dumps(event))

    # Database helper methods

    @database_sync_to_async
    def check_document_permission(self):
        """Check if user has permission to access the document."""
        try:
            from .models import Document, DocumentCollaborator

            # Get employee profile
            if not hasattr(self.user, 'employee_profile'):
                return False

            employee = self.user.employee_profile

            # Get document
            document = Document.objects.get(id=self.document_id)

            # Check if user is the author
            if document.author_id == employee.id:
                return True

            # Check if user is a collaborator
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee
                )
                return True
            except DocumentCollaborator.DoesNotExist:
                return False

        except Exception as e:
            logger.error(f"Error checking document permission: {str(e)}", exc_info=True)
            return False

    @database_sync_to_async
    def create_edit_session(self):
        """Create a document edit session record."""
        try:
            from .models import DocumentEditSession

            # Create session
            session = DocumentEditSession.objects.create(
                document_id=self.document_id,
                user=self.user,
                start_time=timezone.now(),
                is_active=True,
                client_info=self.scope.get('client', [''])[0]
            )
            return session.id

        except Exception as e:
            logger.error(f"Error creating edit session: {str(e)}", exc_info=True)
            return None

    @database_sync_to_async
    def end_edit_session(self):
        """End the document edit session."""
        try:
            from .models import DocumentEditSession

            session = DocumentEditSession.objects.get(id=self.session_id)
            session.end_session()
            return True

        except Exception as e:
            logger.error(f"Error ending edit session: {str(e)}", exc_info=True)
            return False

    @database_sync_to_async
    def update_session_activity(self):
        """Update the session's last activity timestamp."""
        try:
            from .models import DocumentEditSession

            DocumentEditSession.objects.filter(id=self.session_id).update(
                last_activity=timezone.now()
            )
            return True

        except Exception as e:
            logger.error(f"Error updating session activity: {str(e)}", exc_info=True)
            return False

    @database_sync_to_async
    def get_employee_profile(self):
        """Get the user's employee profile information."""
        try:
            if hasattr(self.user, 'employee_profile'):
                employee = self.user.employee_profile
                return {
                    'id': employee.id,
                    'name': employee.get_full_name(),
                    'email': employee.user.email,
                }
            return None
        except Exception as e:
            logger.error(f"Error getting employee profile: {str(e)}", exc_info=True)
            return None

    @database_sync_to_async
    def save_document_content(self, content, create_version=False):
        """Save document content to the database."""
        try:
            from .models import Document, DocumentVersion

            with transaction.atomic():
                document = Document.objects.select_for_update().get(id=self.document_id)

                # Check if user has permission to edit
                if not hasattr(self.user, 'employee_profile'):
                    return {
                        'success': False,
                        'error': 'No employee profile found'
                    }

                employee = self.user.employee_profile

                # Check if user can edit this document
                if not document.can_user_edit(self.user):
                    return {
                        'success': False,
                        'error': 'You do not have permission to edit this document'
                    }

                # Update content
                document.content = content
                document.plain_text = document.extract_plain_text()
                document.updated_by = employee
                document.updated_at = timezone.now()

                # Create a version if requested
                version_number = None
                if create_version:
                    # Get next version number
                    version_number = DocumentVersion.get_next_version_number(document)

                    # Create the version record
                    DocumentVersion.objects.create(
                        document=document,
                        version_number=version_number,
                        content=content,
                        created_by=employee
                    )

                    # Update document version
                    document.version = version_number

                # Save the document
                document.save()

                return {
                    'success': True,
                    'version': version_number or document.version,
                    'updated_at': document.updated_at.isoformat()
                }

        except Exception as e:
            logger.error(f"Error saving document content: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
