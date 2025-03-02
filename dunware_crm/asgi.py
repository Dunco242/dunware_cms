import os
import django
import asyncio
import logging

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from core.routing import websocket_urlpatterns

# ✅ Ensure settings are loaded before anything else
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dunware_crm.settings")
django.setup()

# ✅ Get the ASGI application
django_asgi_app = get_asgi_application()

# ✅ Setup logging
logger = logging.getLogger("django")

# ✅ Graceful shutdown function
async def graceful_shutdown():
    """Closes all connections before the application shuts down."""
    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    if tasks:
        logger.info(f"Shutting down {len(tasks)} running tasks...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All background tasks have been shut down.")

# ✅ Define ASGI application with WebSocket support
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})

# ✅ Attach shutdown handler
application.on_shutdown = graceful_shutdown  # Ensures WebSocket cleanup on shutdown

# ✅ Debugging startup logs
logger.info("ASGI application has started successfully.")
