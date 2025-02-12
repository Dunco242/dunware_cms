# services/scheduling.py
import logging
from datetime import datetime, timedelta
from django.db.models import Q
from django.utils import timezone
from core.models import ScheduleRule, ScheduleException, Event, Meeting, Employee

logger = logging.getLogger(__name__)

class SchedulingService:
    def __init__(self, user):
        """
        Initialize with a user instance
        """
        self.user = user
        try:
            self.employee = user.employee_profile  # Changed from employee to employee_profile
        except AttributeError:
            raise ValueError("User does not have an associated employee profile")

    def check_availability(self, start_time, end_time, duration, exclude_meeting_id=None):
        """
        Check if a proposed time slot is available based on rules
        """
        logger.info(f"Checking availability:")
        logger.info(f"Start Time: {start_time}")
        logger.info(f"End Time: {end_time}")
        logger.info(f"Duration: {duration} minutes")

        # Fetch all active schedule rules for this user
        rules = ScheduleRule.objects.filter(
            user=self.user,
            is_active=True
        )

        # Log found rules
        logger.info(f"Found {rules.count()} active scheduling rules")

        # Check existing events and meetings
        existing_events = Event.objects.filter(
            Q(created_by=self.employee) | Q(attendees=self.employee),
            start_time__lt=end_time,
            end_time__gt=start_time
        )

        meetings_query = Meeting.objects.filter(
            Q(organizer=self.employee) | Q(attendees=self.employee),
            start_time__lt=end_time,
            end_time__gt=start_time
        )

        # Exclude current meeting if updating
        if exclude_meeting_id:
            meetings_query = meetings_query.exclude(id=exclude_meeting_id)

        existing_meetings = meetings_query.all()

        # Combine events and meetings
        existing_bookings = list(existing_events) + list(existing_meetings)

        # If there are any existing bookings, return False
        if existing_bookings:
            logger.warning("Existing bookings found during proposed time")
            return False

        # Check schedule exceptions
        exception = ScheduleException.objects.filter(
            user=self.user,
            date=start_time.date()
        ).first()

        if exception:
            if not exception.is_available:
                logger.warning("Date marked as unavailable in exceptions")
                return False
            if exception.start_time and exception.end_time:
                if (start_time.time() < exception.start_time or
                    end_time.time() > exception.end_time):
                    logger.warning("Time outside of exception allowed hours")
                    return False

        # Check each scheduling rule
        for rule in rules:
            logger.info(f"Checking rule: {rule.name}")

            # Check if the rule applies to this date
            if not self._rule_applies_to_date(rule, start_time.date()):
                logger.info(f"Rule {rule.name} does not apply to this date")
                continue

            logger.info(f"Rule time: {rule.start_time} - {rule.end_time}")
            logger.info(f"Proposed time: {start_time.time()} - {end_time.time()}")

            # Time constraints
            if (start_time.time() < rule.start_time or
                end_time.time() > rule.end_time):
                logger.warning("Time outside of rule hours")
                return False

            # Duration constraints
            if (duration < rule.min_booking_duration or
                duration > rule.max_booking_duration):
                logger.warning("Duration outside of rule constraints")
                return False

            # Check buffer times
            if not self._check_buffer_times(rule, start_time, end_time, exclude_meeting_id):
                logger.warning("Buffer time requirements not met")
                return False

            # Check maximum bookings per day
            if not self._check_max_bookings(rule, start_time.date()):
                logger.warning("Maximum bookings for the day reached")
                return False

        # If we've passed all checks, return True
        logger.info("All availability checks passed")
        return True

    def _rule_applies_to_date(self, rule, date):
        """Check if a rule applies to a specific date"""
        if rule.recurrence_type == 'daily':
            return True
        elif rule.recurrence_type == 'weekly':
            return date.strftime('%A').lower() == rule.day_of_week
        elif rule.recurrence_type == 'monthly':
            return date.day == rule.day_of_month
        elif rule.recurrence_type == 'yearly':
            return date.month == rule.month and date.day == rule.day_of_month
        return False

    def _check_buffer_times(self, rule, start_time, end_time, exclude_meeting_id=None):
        """Check if buffer times are respected"""
        buffer_start = start_time - timedelta(minutes=rule.buffer_after)
        buffer_end = end_time + timedelta(minutes=rule.buffer_before)

        # Check events
        conflicting_events = Event.objects.filter(
            Q(created_by=self.employee) | Q(attendees=self.employee),
            end_time__gt=buffer_start,
            start_time__lt=buffer_end
        ).exists()

        if conflicting_events:
            return False

        # Check meetings
        meetings_query = Meeting.objects.filter(
            Q(organizer=self.employee) | Q(attendees=self.employee),
            end_time__gt=buffer_start,
            start_time__lt=buffer_end
        )

        if exclude_meeting_id:
            meetings_query = meetings_query.exclude(id=exclude_meeting_id)

        return not meetings_query.exists()

    def _check_max_bookings(self, rule, date):
        """Check if maximum bookings per day is reached"""
        # Count existing bookings for the day
        events_count = Event.objects.filter(
            Q(created_by=self.employee) | Q(attendees=self.employee),
            start_time__date=date
        ).count()

        meetings_count = Meeting.objects.filter(
            Q(organizer=self.employee) | Q(attendees=self.employee),
            start_time__date=date
        ).count()

        total_bookings = events_count + meetings_count
        return total_bookings < rule.max_bookings_per_day

    def get_next_available_slot(self, desired_start, duration, max_days_ahead=30):
        """
        Find the next available time slot
        """
        current_time = desired_start
        max_attempts = max_days_ahead * 24 * 4  # 4 attempts per hour, for max days

        while max_attempts > 0:
            proposed_end = current_time + timedelta(minutes=duration)

            # Detailed logging
            logger.info(f"Checking slot: {current_time} - {proposed_end}")

            # Ensure time is within business hours
            if (current_time.time() >= datetime.strptime('09:00', '%H:%M').time() and
                proposed_end.time() <= datetime.strptime('17:00', '%H:%M').time()):

                if self.check_availability(current_time, proposed_end, duration):
                    logger.info(f"Found available slot: {current_time} - {proposed_end}")
                    return current_time, proposed_end

            # Increment by 15-minute intervals
            current_time += timedelta(minutes=15)
            max_attempts -= 1

        logger.warning("No available time slots found")
        return None, None

    def get_daily_schedule(self, date):
        """
        Get the available time slots for a specific date
        """
        available_slots = []
        rules = ScheduleRule.objects.filter(
            user=self.user,
            is_active=True
        )

        for rule in rules:
            if self._rule_applies_to_date(rule, date):
                current_time = datetime.combine(date, rule.start_time)
                end_time = datetime.combine(date, rule.end_time)

                while current_time + timedelta(minutes=rule.min_booking_duration) <= end_time:
                    slot_end = current_time + timedelta(minutes=rule.min_booking_duration)
                    if self.check_availability(current_time, slot_end, rule.min_booking_duration):
                        available_slots.append({
                            'start': current_time,
                            'end': slot_end,
                            'duration': rule.min_booking_duration
                        })
                    current_time += timedelta(minutes=15)

        return available_slots
