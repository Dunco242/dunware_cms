from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<session_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/notifications/(?P<employee_id>\w+)/$', consumers.NotificationConsumer.as_asgi()),  # Add this line

]
