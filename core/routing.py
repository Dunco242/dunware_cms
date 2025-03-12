# core/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Use consistent paths without protocol prefixes
    re_path(r'ws/chat/(?P<session_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'wss/chat/(?P<session_id>\d+)/$', consumers.ChatConsumer.as_asgi()),


    re_path(r'ws/notifications/(?P<employee_id>\w+)/$', consumers.NotificationConsumer.as_asgi()),
    # Add this line to support both ws and wss paths for notifications
    re_path(r'wss/notifications/(?P<employee_id>\w+)/$', consumers.NotificationConsumer.as_asgi()),
    re_path(r'ws/chat/add-user/(?P<session_id>\d+)/$', consumers.AddUserConsumer.as_asgi()),
    re_path(r'wss/chat/add-user/(?P<session_id>\d+)/$', consumers.AddUserConsumer.as_asgi()),
    re_path(r'ws/debug/$', consumers.DebugConsumer.as_asgi()),
]
