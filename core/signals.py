from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from django.utils.timezone import now
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=User)
def create_employee_profile(sender, instance, created, **kwargs):
    """Create Employee profile when a new user is created"""
    from .models import Employee  # Import here to avoid circular import

    if created:
        try:
            # Check if employee profile already exists
            if not hasattr(instance, 'employee'):
                Employee.objects.create(
                    user=instance,
                    hire_date=now().date(),
                    employee_id=f"EMP{instance.id:04d}",
                    department="General",
                    position="Unassigned",
                    phone="000-000-0000",
                    is_active=True
                )
                logger.info(f"Created employee profile for user {instance.username}")
        except Exception as e:
            logger.error(f"Error creating employee profile for user {instance.username}: {str(e)}")

@receiver(post_save, sender=User)
def save_employee_profile(sender, instance, **kwargs):
    """Save Employee profile when user is updated"""
    try:
        if hasattr(instance, 'employee'):
            instance.employee.save()
    except Exception as e:
        logger.error(f"Error saving employee profile for user {instance.username}: {str(e)}")
