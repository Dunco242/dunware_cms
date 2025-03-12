from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from django.utils.timezone import now
import logging
from .models import Meeting, GeneralNotifier, ChatMessage
from django.utils import timezone

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


@receiver(post_save, sender=Meeting)
def create_meeting_notification(sender, instance, created, **kwargs):
    """Create or update notification when a meeting is saved"""
    if instance.is_past:
        return  # Don't create notifications for past meetings

    # Check if start time is in the future
    now = timezone.now()
    if instance.start_time <= now:
        return  # Don't create notifications for meetings that have already started

    # Get related users who should be notified (organizer and attendees)
    participants = [instance.organizer]
    participants.extend(list(instance.attendees.all()))

    for participant in participants:
        user = participant.user

        # Look for an existing notification for this meeting and user
        existing_notification = GeneralNotifier.objects.filter(
            user=user,
            notification_type='meeting',
            title__contains=instance.title,
            # Use a reference field to track which meeting this is for
            reference_id=instance.id,
            is_dismissed=False
        ).first()

        if existing_notification:
            # Update existing notification
            existing_notification.message = f"Meeting: {instance.title} on {instance.start_time.strftime('%Y-%m-%d at %H:%M')}"
            existing_notification.event_datetime = instance.start_time
            existing_notification.action_url = f"/meetings/{instance.id}/"
            existing_notification.save()
        else:
            # Create new notification
            GeneralNotifier.objects.create(
                user=user,
                notification_type='meeting',
                title=f"Upcoming Meeting: {instance.title}",
                message=f"Meeting scheduled for {instance.start_time.strftime('%Y-%m-%d at %H:%M')}",
                priority='normal',
                event_datetime=instance.start_time,
                action_url=f"/meetings/{instance.id}/",
                reference_id=instance.id
            )


@receiver(post_save, sender=ChatMessage)
def create_chat_notification(sender, instance, created, **kwargs):
    """Create notification for unread chat messages"""
    if created and instance.receiver != instance.sender:
        GeneralNotifier.objects.create(
            user=instance.receiver.user,
            notification_type='chat',
            title=f'New message from {instance.sender.get_full_name()}',
            message=instance.content[:50] + ('...' if len(instance.content) > 50 else ''),
            priority='normal',
            action_url=f'/chat/session/{instance.session.id}/',
            reference_id=instance.id,
            event_datetime=timezone.now()  # Add this line to fix the error
        )
