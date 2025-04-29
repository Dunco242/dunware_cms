# models.py
from django.db import models
import uuid

class VerificationCode(models.Model):
    code = models.CharField(max_length=12, unique=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    download_ip = models.GenericIPAddressField(null=True, blank=True)
    download_user_agent = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.code
