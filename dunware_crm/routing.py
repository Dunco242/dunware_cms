from django.urls import re_path
from . import consumers
import os

# Determine if we're in production
use_wss = os.getenv("DJANGO_ENV", "development") == "production"

websocket_urlpatterns = [
    re_path(r'wss/chat/(?P<session_id>\d+)/$', consumers.ChatConsumer.as_asgi()) if use_wss else
    re_path(r'ws/chat/(?P<session_id>\d+)/$', consumers.ChatConsumer.as_asgi()),

    re_path(r'wss/notifications/(?P<employee_id>\w+)/$', consumers.NotificationConsumer.as_asgi()) if use_wss else
    re_path(r'ws/notifications/(?P<employee_id>\w+)/$', consumers.NotificationConsumer.as_asgi()),

    # ✅ New WebSocket Route: Add User to Chat
    re_path(r'wss/chat/add-user/(?P<session_id>\d+)/$', consumers.AddUserConsumer.as_asgi()) if use_wss else
    re_path(r'ws/chat/add-user/(?P<session_id>\d+)/$', consumers.AddUserConsumer.as_asgi()),
]
