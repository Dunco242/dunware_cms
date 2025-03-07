import os
import django
import asyncio
import logging
import signal


# Ensure settings are loaded before anything else
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dunware_crm.settings")
django.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from core.routing import websocket_urlpatterns


# Setup logging
logger = logging.getLogger("django")

# Get the ASGI application
django_asgi_app = get_asgi_application()

# Track active WebSocket connections
active_connections = set()

class ConnectionTrackingMiddleware:
    """Middleware to track active connections for proper cleanup."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Create a unique connection identifier
        connection_id = id(scope)
        if scope['type'] == 'websocket':
            active_connections.add(connection_id)

        # Define a custom send function to detect disconnection
        async def tracking_send(message):
            if message.get('type') == 'websocket.close':
                active_connections.discard(connection_id)
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        finally:
            # Ensure connection is removed even if an exception occurs
            active_connections.discard(connection_id)

# Define graceful shutdown function with timeout
async def graceful_shutdown(timeout=5.0):
    """Closes all connections before the application shuts down."""
    logger.info(f"Initiating graceful shutdown with {len(active_connections)} active connections")

    # Cancel all background tasks
    tasks = [task for task in asyncio.all_tasks()
             if task is not asyncio.current_task() and not task.done()]

    if tasks:
        logger.info(f"Cancelling {len(tasks)} running tasks...")
        for task in tasks:
            task.cancel()

        # Wait for tasks to complete with timeout
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout)
            logger.info("All background tasks have been shut down.")
        except asyncio.TimeoutError:
            logger.warning(f"Some tasks did not complete within {timeout} seconds and will be forcibly terminated.")

    # Clear the active connections tracking
    active_connections.clear()

# Define the application with connection tracking
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": ConnectionTrackingMiddleware(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})

# Attach shutdown handler
application.on_shutdown = graceful_shutdown

# Setup signal handlers for graceful shutdown
for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, lambda sig, frame: asyncio.create_task(graceful_shutdown()))

# Log startup
logger.info("ASGI application has started successfully with improved shutdown handling.")
