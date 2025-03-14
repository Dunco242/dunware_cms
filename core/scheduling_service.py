# core/scheduling_service.py
import logging
from datetime import datetime, timedelta
from typing import Tuple, Dict, List, Optional
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth.models import User

from .models import (
    ScheduleRule, ScheduleException, Employee,
    Meeting, Event, Task
)

logger = logging.getLogger(__name__)

class SchedulingService:
    """Enhanced scheduling service with automated time slot suggestions"""

    def __init__(self, user):
        self.user = user
        try:
            self.employee = user.employee_profile
        except (AttributeError, Employee.DoesNotExist):
            raise ValueError("User does not have an employee profile")

        self.schedule_rules = ScheduleRule.objects.filter(
            user=user,
            is_active=True
        )

    def get_availability(self, date, detailed=False):
        """
        Get availability for a specific date
        Returns dict with available time slots
        """
        if isinstance(date, str):
            try:
                date = datetime.strptime(date, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError(f"Invalid date format: {date}")

        # Check for date exceptions first
        exceptions = ScheduleException.objects.filter(
            user=self.user,
            date=date
        )

        if exceptions.exists():
            exception = exceptions.first()
            if not exception.is_available:
                return {'available': False, 'reason': exception.reason or 'Not available on this date'}

            # If exception has custom times
            if exception.start_time and exception.end_time:
                return {
                    'available': True,
                    'start_time': exception.start_time,
                    'end_time': exception.end_time,
                    'slots': self._get_available_slots(date, exception.start_time, exception.end_time)
                }

        # Get applicable rules for this date
        applicable_rules = self._get_applicable_rules(date)

        if not applicable_rules.exists():
            return {'available': False, 'reason': 'No scheduling rules defined for this date'}

        # Combine available times from all applicable rules
        result = {
            'available': True,
            'slots': []
        }

        for rule in applicable_rules:
            slots = self._get_available_slots(date, rule.start_time, rule.end_time,
                                             min_duration=rule.min_booking_duration,
                                             max_duration=rule.max_booking_duration,
                                             buffer_before=rule.buffer_before,
                                             buffer_after=rule.buffer_after)
            result['slots'].extend(slots)

        # Sort and de-duplicate slots
        result['slots'] = sorted(result['slots'], key=lambda x: x['start'])

        # If detailed, include existing events
        if detailed:
            result['events'] = self._get_day_events(date)

        return result

    def check_availability(self, start_time, end_time, duration_minutes, exclude_meeting_id=None):
        """
        Check if a specific time slot is available with detailed logging
        """
        logger = logging.getLogger(__name__)

        if not isinstance(start_time, datetime):
            logger.error("start_time is not a datetime object")
            return False
        if not isinstance(end_time, datetime):
            logger.error("end_time is not a datetime object")
            return False

        date = start_time.date()
        logger.debug(f"Checking availability for date: {date}")

        # Check date exceptions
        exceptions = ScheduleException.objects.filter(
            user=self.user,
            date=date
        )

        if exceptions.exists():
            exception = exceptions.first()
            logger.debug(f"Found exception for date: {exception.is_available}")
            if not exception.is_available:
                return False

            # Check if within exception time bounds
            if exception.start_time and exception.end_time:
                exception_start = datetime.combine(date, exception.start_time)
                exception_end = datetime.combine(date, exception.end_time)

                if exception_start <= start_time and end_time <= exception_end:
                    logger.debug("Time is within exception bounds")
                else:
                    logger.debug("Time is outside exception bounds")
                    return False

        # Get applicable rules
        applicable_rules = self._get_applicable_rules(date)
        rule_count = applicable_rules.count()
        logger.debug(f"Found {rule_count} applicable rules for date {date}")

        # If no applicable rules and no active schedule rules, consider it available
        # This makes the system work even if no rules are configured
        if not applicable_rules.exists():
            all_rules = self.schedule_rules.count()
            logger.debug(f"No applicable rules found (total rules: {all_rules})")

            # If there are no rules at all, consider all times available
            if all_rules == 0:
                logger.debug("No rules configured, considering all times available")
                # Check for conflicts with existing meetings/events
                if self._check_slot_conflicts(start_time, end_time, 15, 15, exclude_meeting_id):
                    return True
            return False

        # Check against each rule
        for rule in applicable_rules:
            logger.debug(f"Checking rule: {rule.name} ({rule.recurrence_type})")
            rule_start = datetime.combine(date, rule.start_time)
            rule_end = datetime.combine(date, rule.end_time)

            # Check time bounds
            time_in_bounds = (rule_start <= start_time and end_time <= rule_end)
            logger.debug(f"Time in bounds: {time_in_bounds} ({rule.start_time}-{rule.end_time})")
            if not time_in_bounds:
                continue

            # Check duration constraints
            duration = (end_time - start_time).total_seconds() / 60
            duration_valid = (rule.min_booking_duration <= duration <= rule.max_booking_duration)
            logger.debug(f"Duration valid: {duration_valid} ({duration} minutes, allowed: {rule.min_booking_duration}-{rule.max_booking_duration})")
            if not duration_valid:
                continue

            # Check scheduling conflicts with buffer times
            no_conflicts = self._check_slot_conflicts(start_time, end_time,
                                            rule.buffer_before, rule.buffer_after,
                                            exclude_meeting_id)
            logger.debug(f"No conflicts: {no_conflicts}")
            if not no_conflicts:
                continue

            # If we got here, the rule allows this slot
            logger.debug("Slot is available!")
            return True

        # No rules allow this slot
        logger.debug("No rules allow this slot")
        return False

    def _get_applicable_rules(self, date):
        """Get schedule rules that apply to the given date with logging"""
        import logging
        logger = logging.getLogger(__name__)

        weekday = date.strftime('%A').lower()
        month = date.month
        day_of_month = date.day

        logger.debug(f"Getting rules for date {date} (weekday: {weekday}, month: {month}, day: {day_of_month})")

        # List all available rules for debugging
        all_rules = self.schedule_rules.all()
        logger.debug(f"User has {all_rules.count()} total rules:")
        for rule in all_rules:
            logger.debug(f" - Rule: {rule.name}, Type: {rule.recurrence_type}, Active: {rule.is_active}")

        # Get applicable rules
        from django.db.models import Q

        rules = self.schedule_rules.filter(
            Q(recurrence_type='daily') |
            Q(recurrence_type='weekly', day_of_week=weekday) |
            Q(recurrence_type='monthly', day_of_month=day_of_month) |
            Q(recurrence_type='yearly', month=month, day_of_month=day_of_month)
        )

        logger.debug(f"Found {rules.count()} applicable rules for date {date}")
        return rules

    def get_next_available_slot(self, from_datetime, duration_minutes,
                                max_days_ahead=14, preferred_times=None):
        """
        Find the next available time slot starting from a given datetime

        Args:
            from_datetime: Starting datetime to search from
            duration_minutes: Required slot duration in minutes
            max_days_ahead: Maximum number of days to look ahead
            preferred_times: Optional list of preferred time ranges (e.g., morning, afternoon)

        Returns:
            Tuple of (start_datetime, end_datetime) or (None, None) if no slot found
        """
        current_date = from_datetime.date()
        end_date = current_date + timedelta(days=max_days_ahead)

        while current_date <= end_date:
            # Get availability for the current date
            availability = self.get_availability(current_date)

            if availability['available'] and availability['slots']:
                # Filter slots by duration
                valid_slots = [
                    slot for slot in availability['slots']
                    if (datetime.combine(current_date, slot['end']) -
                        datetime.combine(current_date, slot['start'])).total_seconds() / 60 >= duration_minutes
                ]

                # If we have preferred times, prioritize those slots
                if preferred_times and valid_slots:
                    for pref in preferred_times:
                        pref_start = datetime.strptime(pref['start'], '%H:%M').time()
                        pref_end = datetime.strptime(pref['end'], '%H:%M').time()

                        preferred_slots = [
                            slot for slot in valid_slots
                            if slot['start'] >= pref_start and slot['end'] <= pref_end
                        ]

                        if preferred_slots:
                            # Return the first preferred slot
                            slot = preferred_slots[0]
                            start_dt = datetime.combine(current_date, slot['start'])
                            end_dt = start_dt + timedelta(minutes=duration_minutes)
                            return start_dt, end_dt

                # If no preferred slots or no preferences, return the first valid slot
                if valid_slots:
                    slot = valid_slots[0]
                    start_dt = datetime.combine(current_date, slot['start'])
                    end_dt = start_dt + timedelta(minutes=duration_minutes)
                    return start_dt, end_dt

            # Move to the next day
            current_date += timedelta(days=1)

        # No slots found within the specified range
        return None, None

    def suggest_meeting_time(self, participants, duration_minutes,
                            within_days=7, preferred_times=None):
        """
        Suggest a meeting time that works for all participants

        Args:
            participants: List of User or Employee objects
            duration_minutes: Required meeting duration
            within_days: Look for slots within this many days
            preferred_times: Optional preferred time ranges

        Returns:
            Dict with suggested time or conflict information
        """
        # Normalize participants to Employee objects
        employee_participants = []
        for participant in participants:
            if isinstance(participant, User):
                try:
                    employee_participants.append(participant.employee_profile)
                except (AttributeError, Employee.DoesNotExist):
                    return {
                        'success': False,
                        'error': f"User {participant.username} does not have an employee profile"
                    }
            elif isinstance(participant, Employee):
                employee_participants.append(participant)
            else:
                return {
                    'success': False,
                    'error': f"Participant must be User or Employee, got {type(participant)}"
                }

        # Add the current user's employee
        if self.employee not in employee_participants:
            employee_participants.append(self.employee)

        # Get common free slots for all participants
        start_date = timezone.now().date()
        end_date = start_date + timedelta(days=within_days)

        best_slot = None

        # Check each day
        current_date = start_date
        while current_date <= end_date:
            common_slots = self._find_common_slots(employee_participants, current_date, duration_minutes)

            if common_slots:
                # Apply preferred times if specified
                if preferred_times:
                    for pref in preferred_times:
                        pref_start = datetime.strptime(pref['start'], '%H:%M').time()
                        pref_end = datetime.strptime(pref['end'], '%H:%M').time()

                        preferred_slots = [
                            slot for slot in common_slots
                            if slot['start'] >= pref_start and slot['end'] <= pref_end
                        ]

                        if preferred_slots:
                            best_slot = {
                                'date': current_date,
                                'start_time': preferred_slots[0]['start'],
                                'end_time': (
                                    datetime.combine(current_date, preferred_slots[0]['start']) +
                                    timedelta(minutes=duration_minutes)
                                ).time()
                            }
                            break

                # If no preferred times or no matching preferred slots, use the first common slot
                if not best_slot:
                    best_slot = {
                        'date': current_date,
                        'start_time': common_slots[0]['start'],
                        'end_time': (
                            datetime.combine(current_date, common_slots[0]['start']) +
                            timedelta(minutes=duration_minutes)
                        ).time()
                    }
                break

            current_date += timedelta(days=1)

        if best_slot:
            start_datetime = datetime.combine(best_slot['date'], best_slot['start_time'])
            end_datetime = datetime.combine(best_slot['date'], best_slot['end_time'])

            # Format in a user-friendly way
            return {
                'success': True,
                'start_datetime': start_datetime,
                'end_datetime': end_datetime,
                'date': start_datetime.strftime('%A, %B %d, %Y'),
                'start_time': start_datetime.strftime('%I:%M %p'),
                'end_time': end_datetime.strftime('%I:%M %p'),
                'duration_minutes': duration_minutes
            }
        else:
            return {
                'success': False,
                'error': f"No common available time found within {within_days} days"
            }

    def _get_applicable_rules(self, date):
        """Get schedule rules that apply to the given date"""
        weekday = date.strftime('%A').lower()
        month = date.month
        day_of_month = date.day

        return self.schedule_rules.filter(
            Q(recurrence_type='daily') |
            Q(recurrence_type='weekly', day_of_week=weekday) |
            Q(recurrence_type='monthly', day_of_month=day_of_month) |
            Q(recurrence_type='yearly', month=month, day_of_month=day_of_month)
        )

    def _get_available_slots(self, date, start_time, end_time,
                            min_duration=30, max_duration=240,
                            buffer_before=15, buffer_after=15,
                            slot_increment=15):
        """
        Get available time slots for a date within given constraints
        Returns list of dicts with start and end times
        """
        slots = []

        # Convert to datetime for easier calculation
        start_datetime = datetime.combine(date, start_time)
        end_datetime = datetime.combine(date, end_time)

        # Get existing events
        events = self._get_day_events(date)

        # Calculate busy periods including buffer times
        busy_periods = []
        for event in events:
            event_start = event['start'] - timedelta(minutes=buffer_after)
            event_end = event['end'] + timedelta(minutes=buffer_before)
            busy_periods.append((event_start, event_end))

        # Sort busy periods by start time
        busy_periods.sort(key=lambda x: x[0])

        # Merge overlapping busy periods
        merged_busy_periods = []
        for period in busy_periods:
            if not merged_busy_periods or period[0] > merged_busy_periods[-1][1]:
                merged_busy_periods.append(period)
            else:
                merged_busy_periods[-1] = (
                    merged_busy_periods[-1][0],
                    max(merged_busy_periods[-1][1], period[1])
                )

        # Create available slots
        current = start_datetime
        slot_delta = timedelta(minutes=slot_increment)

        while current + timedelta(minutes=min_duration) <= end_datetime:
            slot_end = current + timedelta(minutes=min_duration)

            # Check if slot overlaps with any busy period
            is_available = True
            for busy_start, busy_end in merged_busy_periods:
                if current < busy_end and slot_end > busy_start:
                    is_available = False
                    # Jump to the end of this busy period
                    current = busy_end
                    break

            if is_available:
                slots.append({
                    'start': current.time(),
                    'end': slot_end.time()
                })
                current += slot_delta
            elif current == start_datetime:
                # If we haven't moved from the start, increment by slot_delta
                current += slot_delta

        return slots

    def _get_day_events(self, date):
        """Get all events for a specific day that involve this user"""
        start_of_day = datetime.combine(date, datetime.min.time())
        end_of_day = datetime.combine(date, datetime.max.time())

        # Get meetings
        meetings = Meeting.objects.filter(
            (Q(organizer=self.employee) | Q(attendees=self.employee)),
            start_time__date=date,
            status__in=['scheduled', 'in_progress']
        )

        # Get tasks with due dates
        tasks = Task.objects.filter(
            (Q(assigned_to=self.employee) | Q(created_by=self.employee)),
            due_date__date=date,
            status__in=['pending', 'in_progress']
        )

        # Get events
        events = Event.objects.filter(
            (Q(created_by=self.employee) | Q(attendees=self.employee)),
            start_time__date=date,
            status__in=['scheduled', 'in_progress']
        )

        # Combine all events
        all_events = []

        for meeting in meetings:
            all_events.append({
                'type': 'meeting',
                'id': meeting.id,
                'title': meeting.title,
                'start': meeting.start_time,
                'end': meeting.end_time
            })

        for task in tasks:
            # For tasks, create a 1-hour block around the due time
            task_time = task.due_date
            all_events.append({
                'type': 'task',
                'id': task.id,
                'title': task.title,
                'start': task_time - timedelta(minutes=30),
                'end': task_time + timedelta(minutes=30)
            })

        for event in events:
            all_events.append({
                'type': 'event',
                'id': event.id,
                'title': event.title,
                'start': event.start_time,
                'end': event.end_time
            })

        return all_events

    def _check_slot_conflicts(self, start_time, end_time, buffer_before, buffer_after, exclude_id=None):
        """Check if a time slot conflicts with existing events"""
        # Add buffer times
        buffered_start = start_time - timedelta(minutes=buffer_before)
        buffered_end = end_time + timedelta(minutes=buffer_after)

        # Check meetings
        meeting_conflicts = Meeting.objects.filter(
            (Q(organizer=self.employee) | Q(attendees=self.employee)),
            start_time__lt=buffered_end,
            end_time__gt=buffered_start,
            status__in=['scheduled', 'in_progress']
        )

        if exclude_id:
            meeting_conflicts = meeting_conflicts.exclude(id=exclude_id)

        if meeting_conflicts.exists():
            return False

        # Check events
        event_conflicts = Event.objects.filter(
            (Q(created_by=self.employee) | Q(attendees=self.employee)),
            start_time__lt=buffered_end,
            end_time__gt=buffered_start,
            status__in=['scheduled', 'in_progress']
        )

        if exclude_id:
            event_conflicts = event_conflicts.exclude(id=exclude_id)

        if event_conflicts.exists():
            return False

        return True

    def _find_common_slots(self, participants, date, duration_minutes):
        """Find time slots that work for all participants"""
        common_slots = None

        for participant in participants:
            # Create a service for this participant
            try:
                participant_service = SchedulingService(participant.user)
                availability = participant_service.get_availability(date)

                if not availability['available'] or not availability['slots']:
                    # This participant has no availability on this date
                    return []

                # Filter slots by duration
                valid_slots = []
                for slot in availability['slots']:
                    slot_start = datetime.combine(date, slot['start'])
                    slot_end = datetime.combine(date, slot['end'])
                    slot_duration = (slot_end - slot_start).total_seconds() / 60

                    if slot_duration >= duration_minutes:
                        valid_slots.append(slot)

                if not valid_slots:
                    # No slots long enough for this participant
                    return []

                if common_slots is None:
                    common_slots = valid_slots
                else:
                    # Find intersection of slots
                    new_common_slots = []
                    for common_slot in common_slots:
                        for valid_slot in valid_slots:
                            # Check if slots overlap enough for the required duration
                            overlap_start = max(common_slot['start'], valid_slot['start'])
                            overlap_end = min(common_slot['end'], valid_slot['end'])

                            overlap_duration = (
                                datetime.combine(date, overlap_end) -
                                datetime.combine(date, overlap_start)
                            ).total_seconds() / 60

                            if overlap_duration >= duration_minutes:
                                new_common_slots.append({
                                    'start': overlap_start,
                                    'end': overlap_end
                                })

                    common_slots = new_common_slots

                    if not common_slots:
                        # No common slots found
                        return []

            except Exception as e:
                logger.error(f"Error finding slots for participant {participant}: {str(e)}")
                return []

        return common_slots
