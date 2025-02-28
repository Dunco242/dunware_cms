import os
import django

# ✅ Set the settings module explicitly
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dunware_crm.settings')

# ✅ Setup Django before importing anything else
django.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from core.routing import websocket_urlpatterns

# ✅ Load Django ASGI application
django_asgi_app = get_asgi_application()

# ✅ Configure WebSockets
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
