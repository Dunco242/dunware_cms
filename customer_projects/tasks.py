from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ProjectTask

@receiver(post_save, sender=ProjectTask)
def update_phase_progress(sender, instance, **kwargs):
    """Update phase progress when a task is saved"""
    instance.phase.calculate_progress()
