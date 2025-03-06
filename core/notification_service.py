# Add this file to core/services.py or create a new file core/notification_service.py

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from .models import (
    GeneralNotifier, Meeting, Task, Event, Document, Employee,
    ProjectTask, Project, ProjectPhase
)

class NotificationService:
    """Service for creating and processing notifications"""

    @staticmethod
    def create_notification(user, title, message, notification_type, event_datetime,
                           priority='medium', content_object=None, action_url=''):
        """
        Create a new notification
        """
        content_type = None
        object_id = None

        if content_object:
            content_type = ContentType.objects.get_for_model(content_object)
            object_id = content_object.id

        return GeneralNotifier.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            event_datetime=event_datetime,
            priority=priority,
            content_type=content_type,
            object_id=object_id,
            action_url=action_url
        )

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

    @staticmethod
    def create_meeting_notifications(meeting):
        """
        Create notifications for a meeting
        """
        # Create notification for organizer
        NotificationService.create_notification(
            user=meeting.organizer.user,
            title=f"Meeting: {meeting.title}",
            message=f"You have an upcoming meeting: {meeting.title}",
            notification_type='meeting',
            event_datetime=meeting.start_time,
            priority='high' if meeting.priority == 'high' else 'medium',
            content_object=meeting,
            action_url=reverse('meeting-detail', kwargs={'pk': meeting.pk})
        )

        # Create notifications for attendees
        for attendee in meeting.attendees.all():
            if attendee.user != meeting.organizer.user:  # Skip organizer if they're also an attendee
                NotificationService.create_notification(
                    user=attendee.user,
                    title=f"Meeting: {meeting.title}",
                    message=f"You have an upcoming meeting: {meeting.title}",
                    notification_type='meeting',
                    event_datetime=meeting.start_time,
                    priority='high' if meeting.priority == 'high' else 'medium',
                    content_object=meeting,
                    action_url=reverse('meeting-detail', kwargs={'pk': meeting.pk})
                )

    @staticmethod
    def create_task_notifications(task):
        """
        Create notifications for a task
        """
        if task.assigned_to and task.assigned_to.user:
            NotificationService.create_notification(
                user=task.assigned_to.user,
                title=f"Task: {task.title}",
                message=f"You have a task due: {task.title}",
                notification_type='task',
                event_datetime=task.due_date,
                priority='high' if task.priority == 'high' or task.priority == 'urgent' else 'medium',
                content_object=task,
                action_url=reverse('task-detail', kwargs={'pk': task.pk})
            )

    @staticmethod
    def create_project_task_notifications(project_task):
        """
        Create notifications for a project task
        """
        if project_task.assigned_to and project_task.assigned_to.user:
            NotificationService.create_notification(
                user=project_task.assigned_to.user,
                title=f"Project Task: {project_task.title}",
                message=f"Project: {project_task.phase.project.name} - Task: {project_task.title}",
                notification_type='task',
                event_datetime=project_task.due_date,
                priority='high' if project_task.priority in ['high', 'urgent'] else 'medium',
                content_object=project_task,
                action_url=reverse('customer_projects:task-detail', kwargs={'pk': project_task.pk, 'phase_id': project_task.phase.id})
            )

    @staticmethod
    def create_event_notifications(event):
        """
        Create notifications for an event
        """
        # Notification for creator
        NotificationService.create_notification(
            user=event.created_by.user,
            title=f"Event: {event.title}",
            message=f"You have an upcoming event: {event.title}",
            notification_type='event',
            event_datetime=event.start_time,
            content_object=event,
            action_url=reverse('event-detail', kwargs={'pk': event.pk})
        )

        # Notifications for attendees
        for attendee in event.attendees.all():
            if attendee.user != event.created_by.user:  # Skip creator
                NotificationService.create_notification(
                    user=attendee.user,
                    title=f"Event: {event.title}",
                    message=f"You have an upcoming event: {event.title}",
                    notification_type='event',
                    event_datetime=event.start_time,
                    content_object=event,
                    action_url=reverse('event-detail', kwargs={'pk': event.pk})
                )

    @staticmethod
    def create_document_notifications(document):
        """
        Create notifications for document deadlines or approvals
        """
        # For the document author
        NotificationService.create_notification(
            user=document.author.user,
            title=f"Document: {document.title}",
            message=f"Your document {document.title} is under review",
            notification_type='document',
            event_datetime=timezone.now() + timedelta(days=3),  # Arbitrary deadline for review
            content_object=document,
            action_url=reverse('document-detail', kwargs={'pk': document.pk})
        )

        # For collaborators
        for collaborator in document.collaborators.all():
            if collaborator.permission in ['edit', 'manage'] and collaborator.employee.user != document.author.user:
                NotificationService.create_notification(
                    user=collaborator.employee.user,
                    title=f"Document: {document.title}",
                    message=f"You are collaborating on document: {document.title}",
                    notification_type='document',
                    event_datetime=timezone.now() + timedelta(days=3),
                    content_object=document,
                    action_url=reverse('document-detail', kwargs={'pk': document.pk})
                )

    @staticmethod
    def create_video_conference_notifications(video_conference):
        """
        Create notifications for video conferences
        """
        NotificationService.create_notification(
            user=video_conference.host_user,
            title=f"Video Meeting: {video_conference.channel_name}",
            message=f"You have a scheduled video meeting",
            notification_type='video_conference',
            event_datetime=video_conference.scheduled_for or timezone.now(),
            content_object=video_conference,
            action_url=video_conference.get_invite_url()
        )

    @staticmethod
    def create_project_phase_notifications(phase):
        """
        Create notifications for project phase deadlines
        """
        # Notify project manager
        if phase.project.project_manager and phase.project.project_manager.user:
            NotificationService.create_notification(
                user=phase.project.project_manager.user,
                title=f"Project Phase: {phase.name}",
                message=f"Project phase {phase.name} for {phase.project.name} is ending soon",
                notification_type='deadline',
                event_datetime=phase.end_date,
                priority='high',
                content_object=phase,
                action_url=reverse('customer_projects:phase-update', kwargs={'pk': phase.pk})
            )
