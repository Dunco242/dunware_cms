from django.urls import re_path
import os
from .consumers import DocumentConsumer

# Determine if we're in production
use_wss = os.getenv("DJANGO_ENV", "development") == "production"

# Document editor WebSocket patterns
document_websocket_urlpatterns = [
    re_path(r'wss/documents/(?P<document_id>\w+)/$', DocumentConsumer.as_asgi()) if use_wss else
    re_path(r'ws/documents/(?P<document_id>\w+)/$', DocumentConsumer.as_asgi()),
]
