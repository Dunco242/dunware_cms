from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ProjectTask, Phase

@receiver([post_save, post_delete], sender=ProjectTask)
def task_changed(sender, instance, **kwargs):
    """Update phase progress when tasks are created or deleted"""
    if instance.phase:
        instance.phase.calculate_progress()
