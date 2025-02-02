# core/utils/scheduler.py

from datetime import datetime, timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from core.models import Meeting
from core.utils.zoom import create_zoom_meeting

class MeetingScheduler:
    def __init__(self, organizer):
        self.organizer = organizer

    def schedule_meeting(self, data):
        """Schedule a new meeting and handle all related tasks."""
        # Create the meeting
        meeting = Meeting.objects.create(
            title=data['title'],
            description=data.get('description', ''),
            meeting_type=data['meeting_type'],
            start_time=data['start_time'],
            end_time=data['end_time'],
            organizer=self.organizer
        )

        # Add attendees
        if 'attendees' in data:
            meeting.attendees.set(data['attendees'])

        # Add customers if any
        if 'customers' in data:
            meeting.customers.set(data['customers'])

        # Add leads if any
        if 'leads' in data:
            meeting.leads.set(data['leads'])

        # If it's a Zoom meeting, create it in Zoom
        if data['meeting_type'] == 'zoom':
            try:
                zoom_details = create_zoom_meeting(meeting)
                meeting.zoom_meeting_id = zoom_details['id']
                meeting.zoom_join_url = zoom_details['join_url']
                meeting.zoom_meeting_password = zoom_details['password']
                meeting.save()
            except Exception as e:
                # If Zoom creation fails, delete the meeting and raise the error
                meeting.delete()
                raise e

        # Send notifications
        self._send_meeting_notifications(meeting)

        return meeting

    def reschedule_meeting(self, meeting, new_start_time, new_end_time):
        """Reschedule an existing meeting."""
        old_start_time = meeting.start_time
        meeting.start_time = new_start_time
        meeting.end_time = new_end_time

        # If it's a Zoom meeting, update it in Zoom
        if meeting.meeting_type == 'zoom' and meeting.zoom_meeting_id:
            try:
                update_zoom_meeting(meeting)
            except Exception as e:
                # Revert the changes if Zoom update fails
                meeting.start_time = old_start_time
                meeting.save()
                raise e

        meeting.save()
        self._send_rescheduling_notifications(meeting)
        return meeting

    def _send_meeting_notifications(self, meeting):
        """Send meeting notifications to all participants."""
        context = {
            'meeting': meeting,
            'organizer': self.organizer
        }

        # Prepare the email content
        subject = f"New Meeting: {meeting.title}"
        html_message = render_to_string('core/email/meeting_invitation.html', context)
        plain_message = render_to_string('core/email/meeting_invitation.txt', context)

        # Collect all recipient email addresses
        recipients = set()

        # Add attendees
        for attendee in meeting.attendees.all():
            if attendee.user.email:
                recipients.add(attendee.user.email)

        # Add customers
        for customer in meeting.customers.all():
            if customer.email:
                recipients.add(customer.email)

        # Add leads
        for lead in meeting.leads.all():
            if lead.email:
                recipients.add(lead.email)

        # Send the emails
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=list(recipients),
            html_message=html_message
        )

    def _send_rescheduling_notifications(self, meeting):
        """Send notifications about meeting rescheduling."""
        context = {
            'meeting': meeting,
            'organizer': self.organizer
        }

        subject = f"Meeting Rescheduled: {meeting.title}"
        html_message = render_to_string('core/email/meeting_rescheduled.html', context)
        plain_message = render_to_string('core/email/meeting_rescheduled.txt', context)

        recipients = set()

        # Add attendees
        for attendee in meeting.attendees.all():
            if attendee.user.email:
                recipients.add(attendee.user.email)

        # Add customers
        for customer in meeting.customers.all():
            if customer.email:
                recipients.add(customer.email)

        # Add leads
        for lead in meeting.leads.all():
            if lead.email:
                recipients.add(lead.email)

        # Send the emails
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=list(recipients),
            html_message=html_message
        )
