import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from core.routing import websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dunware_crm.settings')
django.setup()

django_asgi_app = get_asgi_application()

# Determine if we are using secure WebSockets
use_wss = os.getenv("DJANGO_ENV", "development") == "production"

fixed_websocket_urlpatterns = [
    re_path(r'wss/chat/(?P<session_id>\d+)/$', consumers.ChatConsumer.as_asgi()) if use_wss else
    re_path(r'ws/chat/(?P<session_id>\d+)/$', consumers.ChatConsumer.as_asgi()),

    re_path(r'wss/notifications/(?P<employee_id>\w+)/$', consumers.NotificationConsumer.as_asgi()) if use_wss else
    re_path(r'ws/notifications/(?P<employee_id>\w+)/$', consumers.NotificationConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(fixed_websocket_urlpatterns)
    ),
})
