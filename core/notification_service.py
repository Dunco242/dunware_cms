# core/notification_service.py
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q, F
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import (
    GeneralNotifier, Customer, Lead, Meeting, Task, Event, Employee,
    Invoice, Subscription, ServiceSubscription, ChatMessage
)

try:
    from customer_projects.models import (
        ProjectTask, ProjectPhase, Project
    )
    CUSTOMER_PROJECTS_AVAILABLE = True
except ImportError:
    CUSTOMER_PROJECTS_AVAILABLE = False
    logging.info("customer_projects app not available - some notifications will be disabled")

logger = logging.getLogger(__name__)

class SmartNotificationService:
    """Enhanced notification service with context-aware and adaptive notifications"""

    def __init__(self):
        self.channel_layer = get_channel_layer()

    def create_notification(self, user, title, message, notification_type,
                          event_datetime, priority='medium', content_object=None,
                          reference_id=None, action_url=None):
        """
        Create a notification for a user

        Args:
            user: User to receive notification
            title: Notification title
            message: Notification message
            notification_type: Type from GeneralNotifier.NOTIFICATION_TYPES
            event_datetime: When the event is happening
            priority: Priority level from GeneralNotifier.PRIORITY_LEVELS
            content_object: Optional related Django model object
            reference_id: Optional ID for reference
            action_url: Optional URL to direct user when clicked
        """
        try:
            # Create notification in database
            content_type = None
            object_id = None

            if content_object:
                content_type = ContentType.objects.get_for_model(content_object)
                object_id = content_object.id

            notification = GeneralNotifier.objects.create(
                user=user,
                title=title,
                message=message,
                notification_type=notification_type,
                event_datetime=event_datetime,
                priority=priority,
                reference_id=reference_id,
                action_url=action_url,
                content_type=content_type,
                object_id=object_id
            )

            # Send notification via WebSocket
            self._send_notification_to_user(user, notification)

            return notification

        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            return None

    def _send_notification_to_user(self, user, notification):
        """Send notification to a user via WebSocket"""
        try:
            channel_name = f"notifications_{user.id}"

            # Calculate time until event
            time_left = None
            urgency_class = ''

            if notification.event_datetime > timezone.now():
                delta = notification.event_datetime - timezone.now()
                minutes = delta.total_seconds() / 60

                if minutes <= 5:
                    time_left = "In less than 5 minutes"
                    urgency_class = 'immediate'
                elif minutes <= 30:
                    time_left = "In less than 30 minutes"
                    urgency_class = 'very-soon'
                elif minutes <= 60:
                    time_left = "In less than an hour"
                    urgency_class = 'soon'
                elif minutes <= 1440:  # 24 hours
                    hours = round(minutes / 60)
                    time_left = f"In about {hours} hour{'s' if hours != 1 else ''}"
                    urgency_class = 'today'
                else:
                    days = round(minutes / 1440)
                    time_left = f"In about {days} day{'s' if days != 1 else ''}"
                    urgency_class = 'upcoming'
            else:
                time_left = "Now"
                urgency_class = 'immediate'

            # Prepare notification data
            notification_data = {
                'id': notification.id,
                'title': notification.title,
                'message': notification.message,
                'type': notification.notification_type,
                'priority': notification.priority,
                'time_left': time_left,
                'urgency_class': urgency_class,
                'action_url': notification.action_url
            }

            # Send through WebSocket
            async_to_sync(self.channel_layer.group_send)(
                channel_name,
                {
                    'type': 'notification.message',
                    'notification': notification_data
                }
            )

        except Exception as e:
            logger.error(f"Error sending notification via WebSocket: {str(e)}")

    def create_meeting_notification(self, meeting, user=None, reminder_minutes=15):
        """Create a smart notification for a meeting"""
        if not user:
            # Notify the organizer and all attendees
            users = [meeting.organizer.user]
            for attendee in meeting.attendees.all():
                users.append(attendee.user)
        else:
            users = [user]

        for user in users:
            # Create notification
            title = f"Meeting: {meeting.title}"

            # Customize message based on time
            now = timezone.now()
            minutes_until = (meeting.start_time - now).total_seconds() / 60

            if minutes_until < 5:
                message = f"Your meeting '{meeting.title}' is starting now!"
                priority = 'urgent'
            elif minutes_until < reminder_minutes:
                message = f"Your meeting '{meeting.title}' starts in less than {reminder_minutes} minutes."
                priority = 'high'
            else:
                message = f"Reminder: You have a {meeting.get_meeting_type_display()} meeting scheduled."
                priority = 'medium'

            # Add location or joining info
            if meeting.meeting_type == 'zoom' and meeting.zoom_join_url:
                message += f" Join via Zoom: {meeting.zoom_join_url}"
            elif meeting.location:
                message += f" Location: {meeting.location}"

            action_url = reverse('meeting-detail', args=[meeting.id])

            self.create_notification(
                user=user,
                title=title,
                message=message,
                notification_type='meeting',
                event_datetime=meeting.start_time,
                priority=priority,
                content_object=meeting,
                reference_id=meeting.id,
                action_url=action_url
            )

    def create_task_notification(self, task, user=None, reminder_hours=24):
        """Create a smart notification for a task"""
        if not user:
            # Notify the assigned employee
            user = task.assigned_to.user

        # Create notification
        title = f"Task: {task.title}"

        # Customize message based on time
        now = timezone.now()
        hours_until = (task.due_date - now).total_seconds() / 3600

        if hours_until < 0:
            message = f"Overdue task: '{task.title}' was due {abs(int(hours_until))} hours ago."
            priority = 'urgent'
        elif hours_until < 1:
            message = f"Task '{task.title}' is due in less than an hour."
            priority = 'high'
        elif hours_until < reminder_hours:
            message = f"Task '{task.title}' is due in less than {int(hours_until)} hours."
            priority = 'high'
        else:
            message = f"Reminder: Task '{task.title}' is due soon."
            priority = 'medium'

        action_url = reverse('task-detail', args=[task.id])

        self.create_notification(
            user=user,
            title=title,
            message=message,
            notification_type='task',
            event_datetime=task.due_date,
            priority=priority,
            content_object=task,
            reference_id=task.id,
            action_url=action_url
        )

    def create_event_notification(self, event, user=None, reminder_minutes=30):
        """Create a smart notification for an event"""
        if not user:
            # Notify the creator and all attendees
            users = [event.created_by.user]
            for attendee in event.attendees.all():
                users.append(attendee.user)
        else:
            users = [user]

        for user in users:
            # Create notification
            title = f"Event: {event.title}"

            # Customize message based on time
            now = timezone.now()
            minutes_until = (event.start_time - now).total_seconds() / 60

            if minutes_until < 5:
                message = f"Your event '{event.title}' is starting now!"
                priority = 'urgent'
            elif minutes_until < reminder_minutes:
                message = f"Your event '{event.title}' starts in less than {reminder_minutes} minutes."
                priority = 'high'
            else:
                message = f"You have an upcoming event: {event.title}"
                priority = 'medium'

            # Add location if available
            if event.location:
                message += f" Location: {event.location}"

            action_url = reverse('event-detail', args=[event.id])

            self.create_notification(
                user=user,
                title=title,
                message=message,
                notification_type='event',
                event_datetime=event.start_time,
                priority=priority,
                content_object=event,
                reference_id=event.id,
                action_url=action_url
            )

    def create_chat_notification(self, message):
        """Create a notification for a chat message"""
        # Notify only the receiver
        user = message.receiver.user

        title = f"New message from {message.sender.get_full_name()}"
        snippet = message.content[:50] + ("..." if len(message.content) > 50 else "")

        action_url = reverse('chat_detail', args=[message.session.id])

        self.create_notification(
            user=user,
            title=title,
            message=snippet,
            notification_type='chat',
            event_datetime=timezone.now(),
            priority='medium',
            content_object=message,
            reference_id=message.id,
            action_url=action_url
        )

    def create_invoice_notification(self, invoice):
        """
        Create a notification for a new invoice
        """
        if not invoice.customer.assigned_to:
            return None

        user = invoice.customer.assigned_to.user

        # Get project name if available
        project_info = f" for project '{invoice.project.name}'" if invoice.project else ""

        message = f"New invoice #{invoice.invoice_number} created for {invoice.customer.company_name}{project_info}. Amount: ${invoice.total}"

        return self.create_notification(
            user=user,
            title=f"New Invoice #{invoice.invoice_number}",
            message=message,
            notification_type="invoice",
            event_datetime=timezone.now(),
            priority="medium",
            content_object=invoice,
            action_url=f"/billing/invoices/{invoice.id}/"
        )

    def create_invoice_overdue_notification(self, invoice):
        """
        Create a notification for an overdue invoice
        """
        if not invoice.customer.assigned_to:
            return None

        user = invoice.customer.assigned_to.user
        days_overdue = (timezone.now().date() - invoice.due_date).days

        # Get project name if available
        project_info = f" for project '{invoice.project.name}'" if invoice.project else ""

        message = f"Invoice #{invoice.invoice_number} for {invoice.customer.company_name}{project_info} is {days_overdue} days overdue. Balance due: ${invoice.balance_due}"

        return self.create_notification(
            user=user,
            title=f"Invoice #{invoice.invoice_number} Overdue",
            message=message,
            notification_type="deadline",
            event_datetime=timezone.now(),
            priority="high",
            content_object=invoice,
            action_url=f"/billing/invoices/{invoice.id}/"
        )

    def create_invoice_due_notification(self, invoice, days_before=3):
        """
        Create a notification for an upcoming invoice due date
        """
        if not invoice.customer.assigned_to:
            return None

        user = invoice.customer.assigned_to.user

        # Get project name if available
        project_info = f" for project '{invoice.project.name}'" if invoice.project else ""

        message = f"Invoice #{invoice.invoice_number} for {invoice.customer.company_name}{project_info} is due in {days_before} days. Amount: ${invoice.total}"

        return self.create_notification(
            user=user,
            title=f"Invoice #{invoice.invoice_number} Due Soon",
            message=message,
            notification_type="deadline",
            event_datetime=timezone.now(),
            priority="medium",
            content_object=invoice,
            action_url=f"/billing/invoices/{invoice.id}/"
        )

    def create_subscription_expiry_notification(self, subscription, days_before=7):
        """Create a notification for an expiring subscription"""
        # Notify the customer's assigned employee
        if subscription.customer.assigned_to:
            user = subscription.customer.assigned_to.user

            title = f"Subscription Expiring Soon"
            message = f"{subscription.customer.company_name}'s {subscription.service.name} subscription expires in {days_before} days"

            if days_before <= 3:
                priority = 'high'
            else:
                priority = 'medium'

            # Assuming you have a subscription detail view
            action_url = "#"  # Replace with actual URL when available

            self.create_notification(
                user=user,
                title=title,
                message=message,
                notification_type='deadline',
                event_datetime=datetime.combine(subscription.end_date, datetime.min.time()),
                priority=priority,
                content_object=subscription,
                reference_id=subscription.id,
                action_url=action_url
            )

    def create_project_task_notification(self, project_task):
        """Create a notification for a project task"""
        if not CUSTOMER_PROJECTS_AVAILABLE:
            return

        if project_task.assigned_to and project_task.assigned_to.user:
            title = f"Project Task: {project_task.title}"
            message = f"Task for project {project_task.phase.project.name}: {project_task.title}"

            # Determine priority based on task priority
            if hasattr(project_task, 'priority'):
                priority = 'high' if project_task.priority in ['high', 'urgent'] else 'medium'
            else:
                priority = 'medium'

            action_url = reverse('customer_projects:task-detail', kwargs={
                'pk': project_task.id,
                'phase_id': project_task.phase.id
            })

            self.create_notification(
                user=project_task.assigned_to.user,
                title=title,
                message=message,
                notification_type='task',
                event_datetime=project_task.due_date,
                priority=priority,
                content_object=project_task,
                reference_id=project_task.id,
                action_url=action_url
            )

    def create_project_phase_notification(self, phase):
        """Create a notification for a project phase deadline"""
        if not CUSTOMER_PROJECTS_AVAILABLE:
            return

        if phase.project.project_manager and phase.project.project_manager.user:
            title = f"Project Phase Deadline: {phase.name}"
            message = f"Phase {phase.name} of project {phase.project.name} is nearing its deadline"

            action_url = reverse('customer_projects:phase-update', kwargs={'pk': phase.id})

            self.create_notification(
                user=phase.project.project_manager.user,
                title=title,
                message=message,
                notification_type='deadline',
                event_datetime=phase.end_date,
                priority='high',
                content_object=phase,
                reference_id=phase.id,
                action_url=action_url
            )

    def create_document_notification(self, document):
        """Create a notification for a document"""
        # For the document author
        if document.author and document.author.user:
            self.create_notification(
                user=document.author.user,
                title=f"Document: {document.title}",
                message=f"Your document {document.title} is under review",
                notification_type='document',
                event_datetime=timezone.now() + timedelta(days=3),  # Arbitrary deadline for review
                content_object=document,
                reference_id=document.id,
                action_url=reverse('document-detail', kwargs={'pk': document.id})
            )

        # For collaborators if they exist
        if hasattr(document, 'collaborators'):
            for collaborator in document.collaborators.all():
                if collaborator.permission in ['edit', 'manage'] and collaborator.employee.user != document.author.user:
                    self.create_notification(
                        user=collaborator.employee.user,
                        title=f"Document: {document.title}",
                        message=f"You are collaborating on document: {document.title}",
                        notification_type='document',
                        event_datetime=timezone.now() + timedelta(days=3),
                        content_object=document,
                        reference_id=document.id,
                        action_url=reverse('document-detail', kwargs={'pk': document.id})
                    )

    def create_video_conference_notification(self, video_conference):
        """Create a notification for a video conference"""
        if not hasattr(video_conference, 'host_user'):
            return

        self.create_notification(
            user=video_conference.host_user,
            title=f"Video Meeting: {video_conference.channel_name}",
            message=f"You have a scheduled video meeting",
            notification_type='video_conference',
            event_datetime=video_conference.scheduled_for or timezone.now(),
            content_object=video_conference,
            reference_id=video_conference.id,
            action_url=video_conference.get_invite_url() if hasattr(video_conference, 'get_invite_url') else '#'
        )

    def process_scheduling_suggestions(self):
        """Process and create scheduling suggestions"""
        today = timezone.now().date()

        # Find overloaded days (more than 8 hours of meetings)
        employees = Employee.objects.filter(is_active=True)

        for employee in employees:
            user = employee.user

            # Get upcoming meetings for the next 7 days
            start_date = timezone.now()
            end_date = start_date + timedelta(days=7)

            meetings = Meeting.objects.filter(
                Q(organizer=employee) | Q(attendees=employee),
                start_time__range=(start_date, end_date),
                status='scheduled'
            )

            # Group meetings by day
            meetings_by_day = {}
            for meeting in meetings:
                day = meeting.start_time.date()

                if day not in meetings_by_day:
                    meetings_by_day[day] = []

                meetings_by_day[day].append(meeting)

            # Check for overloaded days
            for day, day_meetings in meetings_by_day.items():
                total_hours = sum(
                    (meeting.end_time - meeting.start_time).total_seconds() / 3600
                    for meeting in day_meetings
                )

                if total_hours > 8:
                    # Day is overloaded
                    overload_hours = round(total_hours - 8, 1)

                    title = f"Schedule Alert: Overbooked Day"
                    message = f"You have {total_hours:.1f} hours of meetings on {day.strftime('%A, %b %d')}. Consider rescheduling some meetings."

                    self.create_notification(
                        user=user,
                        title=title,
                        message=message,
                        notification_type='other',
                        event_datetime=datetime.combine(day, datetime.min.time()),
                        priority='medium',
                        action_url="#"  # Calendar URL
                    )

    def check_for_client_inactivity(self, days_threshold=30):
        """Check for customer inactivity and send notifications"""
        threshold_date = timezone.now() - timedelta(days=days_threshold)

        # Find customers with no recent activity
        customers = Customer.objects.filter(status='active')

        for customer in customers:
            if not customer.assigned_to:
                continue

            # Check for recent activity
            recent_meetings = Meeting.objects.filter(
                customers=customer,
                start_time__gt=threshold_date
            ).exists()

            recent_notes = customer.notes.filter(
                created_at__gt=threshold_date
            ).exists()

            recent_events = Event.objects.filter(
                customer=customer,
                start_time__gt=threshold_date
            ).exists()

            if not (recent_meetings or recent_notes or recent_events):
                # No recent activity
                title = f"Customer Inactivity Alert"
                message = f"No activity with {customer.company_name} in the last {days_threshold} days. Consider reaching out."

                self.create_notification(
                    user=customer.assigned_to.user,
                    title=title,
                    message=message,
                    notification_type='other',
                    event_datetime=timezone.now(),
                    priority='medium',
                    content_object=customer,
                    reference_id=customer.id,
                    action_url=reverse('customer-detail', args=[customer.id])
                )

    def send_batch_notifications(self):
        """Send all pending notifications based on time thresholds"""
        now = timezone.now()

        # Process upcoming meetings (within next hour)
        upcoming_meetings = Meeting.objects.filter(
            start_time__gt=now,
            start_time__lt=now + timedelta(hours=1),
            reminder_sent=False,
            status='scheduled'
        )

        for meeting in upcoming_meetings:
            self.create_meeting_notification(meeting)
            meeting.reminder_sent = True
            meeting.save(update_fields=['reminder_sent'])

        # Process upcoming tasks (due today)
        today = now.date()
        upcoming_tasks = Task.objects.filter(
            due_date__date=today,
            status__in=['pending', 'in_progress']
        )

        for task in upcoming_tasks:
            self.create_task_notification(task)

        # Process upcoming events (within next hour)
        upcoming_events = Event.objects.filter(
            start_time__gt=now,
            start_time__lt=now + timedelta(hours=1),
            reminder_sent=False,
            status='scheduled'
        )

        for event in upcoming_events:
            self.create_event_notification(event)
            event.reminder_sent = True
            event.save(update_fields=['reminder_sent'])

        # Process upcoming invoice due dates
        upcoming_invoices = Invoice.objects.filter(
            due_date__range=(today, today + timedelta(days=3)),
            status__in=['pending', 'partial']
        )

        for invoice in upcoming_invoices:
            days_until = (invoice.due_date - today).days
            self.create_invoice_due_notification(invoice, days_before=days_until)

        # Process expiring subscriptions
        subscriptions = ServiceSubscription.objects.filter(
            is_active=True,
            end_date__range=(today, today + timedelta(days=7))
        )

        for subscription in subscriptions:
            days_until = (subscription.end_date - today).days
            self.create_subscription_expiry_notification(subscription, days_before=days_until)

        # Check for scheduling issues
        self.process_scheduling_suggestions()

        # Run inactivity checks weekly (e.g., on Mondays)
        if now.weekday() == 0:  # Monday
            self.check_for_client_inactivity()

    def dismiss_old_notifications(self, days_old=30):
        """Automatically dismiss old notifications to keep the system clean"""
        threshold = timezone.now() - timedelta(days=days_old)

        # Get old notifications that aren't dismissed
        old_notifications = GeneralNotifier.objects.filter(
            created_at__lt=threshold,
            is_dismissed=False
        )

        count = old_notifications.update(is_dismissed=True)
        logger.info(f"Dismissed {count} old notifications automatically")

    # Methods to maintain compatibility with your original NotificationService

    @staticmethod
    def get_user_active_notifications(user, limit=None):
        """
        Get active (unread and undismissed) notifications for a user
        """
        notifications = GeneralNotifier.objects.filter(
            user=user,
            is_read=False,
            is_dismissed=False
        ).order_by('event_datetime')

        if limit:
            notifications = notifications[:limit]

        return notifications

    @staticmethod
    def get_user_upcoming_notifications(user, limit=None):
        """
        Get upcoming notifications (events in the future) for a user
        """
        now = timezone.now()

        notifications = GeneralNotifier.objects.filter(
            user=user,
            is_dismissed=False,
            event_datetime__gt=now
        ).order_by('event_datetime')

        if limit:
            notifications = notifications[:limit]

        return notifications

    @staticmethod
    def mark_all_as_read(user):
        """
        Mark all notifications as read for a user
        """
        GeneralNotifier.objects.filter(
            user=user,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )

# For backward compatibility, maintain the original service name
NotificationService = SmartNotificationService
