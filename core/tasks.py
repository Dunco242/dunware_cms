from django_q.tasks import schedule
from django.utils import timezone
from datetime import timedelta
from core.models import Task, Meeting
from core.signals import EmailToSMS

def send_reminder_notifications():
    tomorrow = timezone.now().date() + timedelta(days=1)

    tasks = Task.objects.filter(
        due_date__date=tomorrow,
        status__in=['pending', 'in_progress']
    )

    for task in tasks:
        if task.assigned_to and task.assigned_to.phone and task.assigned_to.carrier:
            message = f"REMINDER: Task '{task.title}' is due tomorrow!"
            EmailToSMS.send_sms(task.assigned_to.phone, task.assigned_to.carrier, message)

    soon = timezone.now() + timedelta(minutes=5)
    meetings = Meeting.objects.filter(
        start_time__range=(soon, soon + timedelta(minutes=1))
    )

    for meeting in meetings:
        message = f"REMINDER: Meeting '{meeting.title}' starts in 5 minutes!"

        if meeting.organizer and meeting.organizer.phone and meeting.organizer.carrier:
            EmailToSMS.send_sms(meeting.organizer.phone, meeting.organizer.carrier, message)

        for attendee in meeting.attendees.all():
            if attendee.phone and attendee.carrier:
                EmailToSMS.send_sms(attendee.phone, attendee.carrier, message)
