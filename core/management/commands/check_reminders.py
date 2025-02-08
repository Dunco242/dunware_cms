from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
from core.models import Task, Meeting
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Check and send email reminders for tasks and meetings'

    def send_email(self, subject, message, recipient_email):
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
            return True, "Email sent successfully"
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_email}: {str(e)}")
            return False, str(e)

    def handle(self, *args, **options):
        self.stdout.write('Checking for reminders...')

        # Check tasks due tomorrow
        tomorrow = timezone.now().date() + timedelta(days=1)
        tasks = Task.objects.filter(
            due_date__date=tomorrow,
            status__in=['pending', 'in_progress']
        )

        for task in tasks:
            if task.assigned_to and task.assigned_to.user.email:
                subject = f"Task Due Tomorrow: {task.title}"
                message = (
                    f"This is a reminder that the following task is due tomorrow:\n\n"
                    f"Task: {task.title}\n"
                    f"Due Date: {task.due_date}\n"
                    f"Priority: {task.get_priority_display()}\n"
                    f"Status: {task.get_status_display()}\n"
                    f"Description: {task.description}\n\n"
                    f"Please ensure this task is completed on time."
                )

                success, msg = self.send_email(
                    subject,
                    message,
                    task.assigned_to.user.email
                )

                if success:
                    self.stdout.write(self.style.SUCCESS(f'Task reminder sent for {task.title}'))
                else:
                    self.stdout.write(self.style.ERROR(f'Failed to send task reminder: {msg}'))

        # Check meetings starting soon
        soon = timezone.now() + timedelta(minutes=5)
        meetings = Meeting.objects.filter(
            start_time__range=(soon, soon + timedelta(minutes=1))
        )

        for meeting in meetings:
            local_start_time = localtime(meeting.start_time)  # Convert to local timezone
            local_end_time = localtime(meeting.end_time)
            subject = f"Meeting Starting Soon: {meeting.title}"
            base_message = (
                f"Your meeting starts in 5 minutes:\n\n"
                f"Title: {meeting.title}\n"
                f"Start Time: {local_start_time.strftime('%Y-%m-%d %I:%M %p %Z')}\n"  # Format as human-readable
                f"End Time: {local_end_time.strftime('%Y-%m-%d %I:%M %p %Z')}\n"
                f"Type: {meeting.get_meeting_type_display()}\n"
                f"Description: {meeting.description}\n"
            )

            if meeting.meeting_type == 'zoom' and meeting.zoom_join_url:
                base_message += f"\nZoom Link: {meeting.zoom_join_url}"

            # Notify organizer
            if meeting.organizer and meeting.organizer.user.email:
                organizer_message = base_message + "\n\nYou are the organizer of this meeting."
                success, msg = self.send_email(
                    subject,
                    organizer_message,
                    meeting.organizer.user.email
                )

                if success:
                    self.stdout.write(self.style.SUCCESS(f'Meeting reminder sent to organizer for {meeting.title}'))
                else:
                    self.stdout.write(self.style.ERROR(f'Failed to send meeting reminder to organizer: {msg}'))

            # Notify attendees
            for attendee in meeting.attendees.all():
                if attendee.user.email:
                    attendee_message = base_message + "\n\nYou are an attendee of this meeting."
                    success, msg = self.send_email(
                        subject,
                        attendee_message,
                        attendee.user.email
                    )

                    if success:
                        self.stdout.write(self.style.SUCCESS(f'Meeting reminder sent to attendee {attendee.user.email}'))
                    else:
                        self.stdout.write(self.style.ERROR(f'Failed to send meeting reminder to attendee: {msg}'))

        self.stdout.write(self.style.SUCCESS('Reminder check completed'))
