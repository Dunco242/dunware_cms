from django.urls import re_path
from . import consumers
import os

# Determine if we're in production
use_wss = os.getenv("DJANGO_ENV", "development") == "production"

websocket_urlpatterns = [
    # Chat consumer
    re_path(r'wss/chat/(?P<session_id>\d+)/$', consumers.ChatConsumer.as_asgi()) if use_wss else
    re_path(r'ws/chat/(?P<session_id>\d+)/$', consumers.ChatConsumer.as_asgi()),

    # Notification consumer - fix for the double slash issue
    re_path(r'wss/notifications/(?P<employee_id>\w+)/?$', consumers.NotificationConsumer.as_asgi()) if use_wss else
    re_path(r'ws/notifications/(?P<employee_id>\w+)/?$', consumers.NotificationConsumer.as_asgi()),

    # Add User to Chat consumer
    re_path(r'wss/chat/add-user/(?P<session_id>\d+)/$', consumers.AddUserConsumer.as_asgi()) if use_wss else
    re_path(r'ws/chat/add-user/(?P<session_id>\d+)/$', consumers.AddUserConsumer.as_asgi()),

    # Debug WebSocket endpoint
    re_path(r'wss/debug/$', consumers.DebugConsumer.as_asgi()) if use_wss else
    re_path(r'ws/debug/$', consumers.DebugConsumer.as_asgi()),

    # Fallback for empty employee_id - this catches the double slash case
    re_path(r'wss/notifications//?$', consumers.NotificationConsumer.as_asgi()) if use_wss else
    re_path(r'ws/notifications//?$', consumers.NotificationConsumer.as_asgi()),
]
