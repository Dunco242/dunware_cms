from django_q.tasks import schedule, async_task
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from core.models import Task, Meeting
from core.signals import EmailToSMS
import logging
from functools import wraps
from django.core.cache import cache
from typing import Optional, List, Dict, Any
import json

logger = logging.getLogger(__name__)

def retry_on_failure(max_retries=3, delay=5):
    """Decorator to retry failed operations"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Failed after {max_retries} attempts: {str(e)}", exc_info=True)
                        raise
                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

def log_execution_time(func):
    """Decorator to log function execution time"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = timezone.now()
        result = func(*args, **kwargs)
        execution_time = timezone.now() - start_time
        logger.info(f"{func.__name__} executed in {execution_time.total_seconds():.2f} seconds")
        return result
    return wrapper

class NotificationManager:
    def __init__(self):
        self.cache_timeout = 3600  # 1 hour

    def get_cache_key(self, notification_type: str, identifier: str) -> str:
        return f"notification_{notification_type}_{identifier}"

    def should_send_notification(self, notification_type: str, identifier: str) -> bool:
        cache_key = self.get_cache_key(notification_type, identifier)
        return not cache.get(cache_key)

    def mark_notification_sent(self, notification_type: str, identifier: str):
        cache_key = self.get_cache_key(notification_type, identifier)
        cache.set(cache_key, True, self.cache_timeout)

notification_manager = NotificationManager()

@retry_on_failure(max_retries=3)
def send_sms_notification(phone: str, carrier: str, message: str) -> bool:
    """Send SMS notification with retry logic"""
    try:
        EmailToSMS.send_sms(phone, carrier, message)
        return True
    except Exception as e:
        logger.error(f"Failed to send SMS to {phone}: {str(e)}")
        raise

@log_execution_time
def process_task_reminders():
    """Process task reminders with improved error handling"""
    tomorrow = timezone.now().date() + timedelta(days=1)

    try:
        tasks = Task.objects.filter(
            due_date__date=tomorrow,
            status__in=['pending', 'in_progress']
        ).select_related('assigned_to__user')  # Optimize query

        for task in tasks:
            if (task.assigned_to and
                task.assigned_to.phone and
                task.assigned_to.carrier and
                notification_manager.should_send_notification('task', f"{task.id}_{tomorrow}")):

                try:
                    message = (
                        f"REMINDER: Task '{task.title}' is due tomorrow!\n"
                        f"Priority: {task.get_priority_display()}\n"
                        f"Status: {task.get_status_display()}"
                    )

                    if send_sms_notification(task.assigned_to.phone, task.assigned_to.carrier, message):
                        notification_manager.mark_notification_sent('task', f"{task.id}_{tomorrow}")
                        logger.info(f"Task reminder sent for task {task.id}")

                except Exception as e:
                    logger.error(f"Failed to process task reminder for task {task.id}: {str(e)}")

    except Exception as e:
        logger.error(f"Error processing task reminders: {str(e)}", exc_info=True)
        raise

@log_execution_time
def process_meeting_reminders():
    """Process meeting reminders with improved error handling"""
    soon = timezone.now() + timedelta(minutes=5)

    try:
        meetings = Meeting.objects.filter(
            start_time__range=(soon, soon + timedelta(minutes=1))
        ).select_related('organizer__user').prefetch_related('attendees')

        for meeting in meetings:
            meeting_key = f"{meeting.id}_{soon.strftime('%Y%m%d%H%M')}"

            if notification_manager.should_send_notification('meeting', meeting_key):
                message = (
                    f"REMINDER: Meeting '{meeting.title}' starts in 5 minutes!\n"
                    f"Type: {meeting.get_meeting_type_display()}"
                )

                if meeting.meeting_type == 'zoom' and meeting.zoom_join_url:
                    message += f"\nZoom Link: {meeting.zoom_join_url}"

                # Send to organizer
                if meeting.organizer and meeting.organizer.phone and meeting.organizer.carrier:
                    try:
                        organizer_message = f"{message}\nYou are the organizer."
                        if send_sms_notification(meeting.organizer.phone, meeting.organizer.carrier, organizer_message):
                            logger.info(f"Meeting reminder sent to organizer for meeting {meeting.id}")
                    except Exception as e:
                        logger.error(f"Failed to send organizer reminder for meeting {meeting.id}: {str(e)}")

                # Send to attendees
                for attendee in meeting.attendees.all():
                    if attendee.phone and attendee.carrier:
                        try:
                            attendee_message = f"{message}\nYou are an attendee."
                            if send_sms_notification(attendee.phone, attendee.carrier, attendee_message):
                                logger.info(f"Meeting reminder sent to attendee {attendee.id} for meeting {meeting.id}")
                        except Exception as e:
                            logger.error(f"Failed to send attendee reminder for meeting {meeting.id}: {str(e)}")

                notification_manager.mark_notification_sent('meeting', meeting_key)

    except Exception as e:
        logger.error(f"Error processing meeting reminders: {str(e)}", exc_info=True)
        raise

@log_execution_time
def send_reminder_notifications():
    """Main function to process all reminders"""
    try:
        process_task_reminders()
        process_meeting_reminders()
        logger.info("Reminder notifications processed successfully")
    except Exception as e:
        logger.error(f"Failed to process reminder notifications: {str(e)}", exc_info=True)
        raise

def schedule_reminders():
    """Schedule reminder checks"""
    schedule(
        'core.tasks.send_reminder_notifications',
        schedule_type='I',  # Independent
        minutes=5,
        repeats=-1,  # Repeat indefinitely
        next_run=timezone.now(),
        catch_up=False  # Don't run missed tasks
    )
