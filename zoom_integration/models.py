# zoom_integration/models.py

from django.db import models
from django.conf import settings

class ZoomMeeting(models.Model):
    meeting_id = models.CharField(max_length=200)
    topic = models.CharField(max_length=200)
    start_time = models.DateTimeField()
    duration = models.IntegerField()  # in minutes
    join_url = models.URLField()
    password = models.CharField(max_length=20)
    host_email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.topic} - {self.meeting_id}"

class ZoomCredentials(models.Model):
    api_key = models.CharField(max_length=100)
    api_secret = models.CharField(max_length=100)
    user_id = models.CharField(max_length=100)  # Zoom user ID
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.api_key
