# management/commands/create_meeting_notifications.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from core.models import Meeting, GeneralNotifier, Employee

class Command(BaseCommand):
    help = 'Create notifications for upcoming meetings'

    def handle(self, *args, **options):
        now = timezone.now()

        # Get upcoming meetings
        upcoming_meetings = Meeting.objects.filter(
            start_time__gt=now
        ).distinct()

        notification_count = 0

        for meeting in upcoming_meetings:
            participants = [meeting.organizer]
            participants.extend(list(meeting.attendees.all()))

            for participant in participants:
                user = participant.user

                # Skip if notification already exists
                exists = GeneralNotifier.objects.filter(
                    user=user,
                    notification_type='meeting',
                    reference_id=meeting.id,
                    is_dismissed=False
                ).exists()

                if not exists:
                    GeneralNotifier.objects.create(
                        user=user,
                        notification_type='meeting',
                        title=f"Upcoming Meeting: {meeting.title}",
                        message=f"Meeting scheduled for {meeting.start_time.strftime('%Y-%m-%d at %H:%M')}",
                        priority='normal',
                        event_datetime=meeting.start_time,
                        action_url=f"/meetings/{meeting.id}/",
                        reference_id=meeting.id
                    )
                    notification_count += 1

        self.stdout.write(self.style.SUCCESS(f'Created {notification_count} meeting notifications'))
