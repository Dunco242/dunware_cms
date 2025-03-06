# models.py
from django.db import models
import uuid
from django.utils import timezone
import datetime

class VideoConference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel_name = models.CharField(max_length=255, unique=True)
    host_user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='hosted_conferences')
    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    passcode = models.CharField(max_length=10, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Conference: {self.channel_name}"

    def get_invite_url(self, request=None):
        if request:
            base_url = f"{request.scheme}://{request.get_host()}"
        else:
            # Fallback to your site domain if request not provided
            base_url = "https://yourdomain.com"
        return f"{base_url}/meeting/join/{self.id}/"

    def is_expired(self):
        # Check if meeting has passed or been inactive for 24 hours
        if self.scheduled_for and self.scheduled_for < timezone.now():
            return True
        if self.created_at < timezone.now() - datetime.timedelta(hours=24):
            return True
        return not self.is_active
