# core/utils/calendar.py

from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q
from core.models import Meeting, Task

class Calendar:
    def __init__(self, employee):
        self.employee = employee

    def get_events_for_date_range(self, start_date, end_date):
        """Get all events (meetings and tasks) for a date range."""
        meetings = Meeting.objects.filter(
            Q(organizer=self.employee) | Q(attendees=self.employee),
            start_time__gte=start_date,
            end_time__lte=end_date
        ).order_by('start_time')

        tasks = Task.objects.filter(
            assigned_to=self.employee,
            due_date__gte=start_date,
            due_date__lte=end_date
        ).order_by('due_date')

        events = []

        # Add meetings to events
        for meeting in meetings:
            events.append({
                'type': 'meeting',
                'id': meeting.id,
                'title': meeting.title,
                'start': meeting.start_time,
                'end': meeting.end_time,
                'url': f'/meetings/{meeting.id}/',
                'backgroundColor': self._get_meeting_color(meeting),
                'borderColor': self._get_meeting_color(meeting)
            })

        # Add tasks to events
        for task in tasks:
            events.append({
                'type': 'task',
                'id': task.id,
                'title': task.title,
                'start': task.due_date,
                'url': f'/tasks/{task.id}/',
                'backgroundColor': self._get_task_color(task),
                'borderColor': self._get_task_color(task)
            })

        return events

    def get_available_slots(self, date, duration_minutes=30):
        """Get available time slots for a given date."""
        # Define working hours (9 AM to 5 PM)
        work_start = datetime.combine(date, datetime.strptime('09:00', '%H:%M').time())
        work_end = datetime.combine(date, datetime.strptime('17:00', '%H:%M').time())

        # Get all meetings for the day
        meetings = Meeting.objects.filter(
            Q(organizer=self.employee) | Q(attendees=self.employee),
            start_time__date=date
        ).order_by('start_time')

        # Create list of busy slots
        busy_slots = []
        for meeting in meetings:
            busy_slots.append({
                'start': meeting.start_time,
                'end': meeting.end_time
            })

        # Find available slots
        available_slots = []
        current_time = work_start
        slot_duration = timedelta(minutes=duration_minutes)

        while current_time + slot_duration <= work_end:
            slot_end = current_time + slot_duration
            is_available = True

            # Check if slot overlaps with any meeting
            for busy_slot in busy_slots:
                if (current_time < busy_slot['end'] and
                    slot_end > busy_slot['start']):
                    is_available = False
                    current_time = busy_slot['end']
                    break

            if is_available:
                available_slots.append({
                    'start': current_time,
                    'end': slot_end
                })
                current_time += slot_duration
            else:
                continue

        return available_slots

    def _get_meeting_color(self, meeting):
        """Get color for meeting based on type."""
        colors = {
            'zoom': '#2D8CFF',  # Zoom blue
            'in_person': '#28a745',  # Green
            'phone': '#17a2b8'  # Blue
        }
        return colors.get(meeting.meeting_type, '#6c757d')

    def _get_task_color(self, task):
        """Get color for task based on priority and status."""
        if task.status == 'completed':
            return '#28a745'  # Green

        priority_colors = {
            'high': '#dc3545',  # Red
            'medium': '#ffc107',  # Yellow
            'low': '#17a2b8'  # Blue
        }
        return priority_colors.get(task.priority, '#6c757d')
