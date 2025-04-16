# core/models.py

from django.db import models, transaction
from django.contrib.auth.models import User
from .mixins import ProjectDatesMixin
from django.urls import reverse
from django.utils import timezone
from zoom_integration.models import ZoomMeeting
from django.conf import settings
from zoomus import ZoomClient
from datetime import datetime, time, timedelta, date
from dateutil.relativedelta import relativedelta
import uuid
from django.utils.crypto import get_random_string
from decimal import Decimal
from django.utils.timezone import make_aware
from dateutil.rrule import rrulestr
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, EmailValidator, URLValidator,  MinLengthValidator
import pytz
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from typing import Optional, List, Dict
import random
import logging

logger = logging.getLogger(__name__)

class Employee(models.Model):
    """Employee model with enhanced validations and relationships"""

    CARRIER_CHOICES = [
        ('rogers', 'Rogers'),
        ('bell', 'Bell Canada'),
        ('public', 'Public Mobile'),
        ('telus', 'Telus'),
        ('btc', 'Batelco'),
        ('aliv', 'Aliv - Bahamas'),
        ('metro', 'Metro PCS'),
        ('virgin', 'Virgin Mobile'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='employee_profile'
    )

    employee_id = models.CharField(
        max_length=10,
        unique=True,
        validators=[
            MinLengthValidator(4, 'Employee ID must be at least 4 characters'),
            RegexValidator(
                regex=r'^[A-Za-z0-9-]+$',
                message='Employee ID can only contain letters, numbers, and hyphens'
            )
        ]
    )

    DEPARTMENT_CHOICES = [
        ('general', 'General'),
        ('sales', 'Sales'),
        ('support', 'Support'),
        ('engineering', 'Engineering'),
        ('marketing', 'Marketing'),
        ('finance', 'Finance'),
        ('hr', 'Human Resources'),
    ]

    department = models.CharField(
        max_length=100,
        choices=DEPARTMENT_CHOICES,
        default='general'
    )

    POSITION_CHOICES = [
        ('unassigned', 'Unassigned'),
        ('junior', 'Junior'),
        ('senior', 'Senior'),
        ('lead', 'Lead'),
        ('manager', 'Manager'),
        ('director', 'Director'),
    ]

    position = models.CharField(
        max_length=100,
        choices=POSITION_CHOICES,
        default='unassigned'
    )

    phone_regex = RegexValidator(
        regex=r'^\(\d{3}\)\d{3}-\d{4}$',
        message="Phone number must be entered in the format: '(999)999-9999'"
    )

    phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
        blank=True,
        help_text="Contact phone number"
    )

    carrier = models.CharField(
        max_length=20,
        choices=CARRIER_CHOICES,
        blank=True,
        help_text="Mobile carrier for SMS notifications"
    )

    hire_date = models.DateField(
        null=True,
        blank=True,
        help_text="Employee hire date"
    )

    termination_date = models.DateField(
        null=True,
        blank=True,
        help_text="Employee termination date"
    )

    def profile_picture_path(instance, filename):
        ext = filename.split('.')[-1]
        new_filename = f"{instance.employee_id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        return f'employee_photos/{timezone.now().year}/{timezone.now().month}/{new_filename}'

    profile_picture = models.ImageField(
        upload_to='employee_photos/',
        null=True,
        blank=True,
        help_text="Employee profile picture"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this employee is currently active"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['employee_id']),
            models.Index(fields=['department', 'position']),
            models.Index(fields=['is_active', 'created_at']),
        ]
        permissions = [
            ("can_view_employee_details", "Can view employee details"),
            ("can_edit_employee_details", "Can edit employee details"),
            ("can_terminate_employee", "Can terminate employee"),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.employee_id}"

    def clean(self):
        """Validate employee data"""
        if self.hire_date and self.hire_date > timezone.now().date():
            raise ValidationError({'hire_date': 'Hire date cannot be in the future'})

        if self.termination_date:
            if not self.hire_date:
                raise ValidationError({
                    'termination_date': 'Cannot set termination date without hire date'
                })
            if self.termination_date < self.hire_date:
                raise ValidationError({
                    'termination_date': 'Termination date cannot be before hire date'
                })

        if bool(self.phone) != bool(self.carrier):
            raise ValidationError('Both phone number and carrier must be provided together')

    def get_full_name(self):
        """Return the user's full name or username if not available"""
        if self.user.first_name or self.user.last_name:
            return f"{self.user.first_name} {self.user.last_name}".strip()
        return self.user.username


class Customer(ProjectDatesMixin, models.Model):
    """
    Customer model with improved validation and relationship handling
    """
    CUSTOMER_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('pending', 'Pending'),
        ('archived', 'Archived')
    ]

    # Basic Information
    company_name = models.CharField(
        max_length=200,
        validators=[
            RegexValidator(
                regex=r'^[\w\s\-\',.&]+$',
                message='Company name can only contain letters, numbers, spaces, and basic punctuation'
            )
        ],
        help_text="Official company name"
    )

    contact_person = models.CharField(
        max_length=100,
        validators=[
            RegexValidator(
                regex=r'^[\w\s\-\']+$',
                message='Contact person name can only contain letters, spaces, and hyphens'
            )
        ],
        help_text="Primary contact person's name"
    )

    # Contact Information
    email = models.EmailField(
        unique=True,
        validators=[EmailValidator()],
        help_text="Primary contact email"
    )

    phone_regex = RegexValidator(
        regex=r'^\(\d{3}\)\d{3}-\d{4}$',
        message="Phone number must be entered in the format: '(999)999-9999'"
    )

    phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
        help_text="Primary contact phone number"
    )

    # Address Information
    address = models.TextField(
        help_text="Street address",
        validators=[
            RegexValidator(
                regex=r'^[\w\s\-\',./\\#]+$',
                message='Address can only contain letters, numbers, spaces, and basic punctuation'
            )
        ]
    )

    city = models.CharField(
        max_length=100,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Z\s\-]+$',
                message='City name can only contain letters, spaces, and hyphens'
            )
        ]
    )

    state = models.CharField(
        max_length=100,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Z\s\-]+$',
                message='State name can only contain letters, spaces, and hyphens'
            )
        ]
    )

    zip_code = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r'^\d{5}(-\d{4})?$',
                message='ZIP code must be in the format: 12345 or 12345-6789'
            )
        ]
    )

    # Online Presence
    website = models.URLField(
        blank=True,
        null=True,
        validators=[URLValidator(schemes=['http', 'https'])],
        help_text="Company website URL"
    )

    # Status and Assignment
    status = models.CharField(
        max_length=20,
        choices=CUSTOMER_STATUS,
        default='active',
        db_index=True
    )

    assigned_to = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        related_name='assigned_customers',
        help_text="Employee responsible for this customer"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_contact_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date of last contact with customer"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_name']),
            models.Index(fields=['email']),
            models.Index(fields=['status', 'assigned_to']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.company_name

    def get_absolute_url(self):
        return reverse('customer-detail', kwargs={'pk': self.pk})

    def get_full_address(self):
        """Get formatted full address"""
        return f"{self.address}, {self.city}, {self.state} {self.zip_code}"



class Lead(models.Model):
    """
    Lead model with improved validation and status management
    """

    LEAD_STATUS = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('qualified', 'Qualified'),
        ('unqualified', 'Unqualified'),
        ('negotiating', 'Negotiating'),
        ('converted', 'Converted'),
        ('lost', 'Lost')
    ]

    LEAD_SOURCE = [
        ('website', 'Website'),
        ('referral', 'Referral'),
        ('social', 'Social Media'),
        ('email', 'Email Campaign'),
        ('trade_show', 'Trade Show'),
        ('cold_call', 'Cold Call'),
        ('other', 'Other')
    ]

    LEAD_PRIORITY = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High')
    ]

    # Basic Information
    company_name = models.CharField(
        max_length=200,
        validators=[
            RegexValidator(
                regex=r'^[\w\s\-\',.&]+$',
                message='Company name can only contain letters, numbers, spaces, and basic punctuation'
            )
        ],
        help_text="Company name"
    )

    contact_person = models.CharField(
        max_length=100,
        validators=[
            RegexValidator(
                regex=r'^[\w\s\-\']+$',
                message='Contact person name can only contain letters, spaces, and hyphens'
            )
        ],
        help_text="Primary contact person"
    )

    # Contact Information
    email = models.EmailField(
        validators=[EmailValidator()],
        help_text="Primary contact email"
    )

    phone_regex = RegexValidator(
        regex=r'^\(\d{3}\)\d{3}-\d{4}$',
        message="Phone number must be entered in the format: '(999)999-9999'"
    )
    phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
        blank=True,
        help_text="Primary contact phone number"
    )

    # Lead Classification
    source = models.CharField(
        max_length=20,
        choices=LEAD_SOURCE,
        help_text="Where did this lead come from?"
    )

    status = models.CharField(
        max_length=20,
        choices=LEAD_STATUS,
        default='new',
        db_index=True,
        help_text="Current status of the lead"
    )

    priority = models.CharField(
        max_length=10,
        choices=LEAD_PRIORITY,
        default='medium',
        help_text="Lead priority level"
    )

    # Additional Information
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about the lead"
    )

    estimated_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated value of the lead"
    )

    # Relationships
    assigned_to = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        related_name='assigned_leads',
        help_text="Employee responsible for this lead"
    )

    converted_to_customer = models.ForeignKey(
        'Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='converted_from_lead',
        help_text="Customer record if lead was converted"
    )

    # Tracking Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_contacted = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When was the lead last contacted?"
    )
    conversion_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When was the lead converted to a customer?"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['email']),
            models.Index(fields=['created_at']),
        ]
        permissions = [
            ("can_convert_lead", "Can convert lead to customer"),
            ("can_assign_lead", "Can assign lead to employee"),
        ]

    def __str__(self):
        return f"{self.company_name} - {self.get_status_display()}"

    def clean(self):
        """Validate lead data"""
        # Validate status transitions
        if self.pk:
            old_instance = Lead.objects.get(pk=self.pk)

            # Prevent status changes after conversion
            if old_instance.status == 'converted' and self.status != 'converted':
                raise ValidationError("Cannot change status of converted lead")

            # Validate conversion
            if self.status == 'converted' and not self.converted_to_customer:
                raise ValidationError("Converted lead must have an associated customer")

        # Validate assignment
        if self.assigned_to and not self.assigned_to.is_active:
            raise ValidationError({
                'assigned_to': 'Cannot assign lead to inactive employee'
            })

        # Validate estimated value
        if self.estimated_value and self.estimated_value < Decimal('0.00'):
            raise ValidationError({
                'estimated_value': 'Estimated value cannot be negative'
            })

    def save(self, *args, **kwargs):
        """Override save for additional processing"""
        self.full_clean()

        # Handle status changes
        if self.pk:
            old_instance = Lead.objects.get(pk=self.pk)
            if old_instance.status != self.status:
                if self.status == 'converted':
                    self.conversion_date = timezone.now()
                self._handle_status_change(old_instance.status, self.status)

        super().save(*args, **kwargs)

    def _handle_status_change(self, old_status, new_status):
        """Handle status change side effects"""
        if new_status == 'contacted':
            self.last_contacted = timezone.now()

        # Log status change
        logger.info(f"Lead {self.pk} status changed from {old_status} to {new_status}")

    def get_absolute_url(self):
        """Get URL for lead detail view"""
        return reverse('lead-detail', kwargs={'pk': self.pk})

    def convert_to_customer(self):
        """Convert lead to customer"""
        if self.status == 'converted':
            raise ValidationError("Lead is already converted")

        from .models import Customer
        with transaction.atomic():
            try:
                # Create customer record
                customer = Customer.objects.create(
                    company_name=self.company_name,
                    contact_person=self.contact_person,
                    email=self.email,
                    phone=self.phone,
                    assigned_to=self.assigned_to,
                    status='active'
                )

                # Update lead
                self.status = 'converted'
                self.converted_to_customer = customer
                self.conversion_date = timezone.now()
                self.save()

                logger.info(f"Successfully converted lead {self.pk} to customer {customer.pk}")
                return customer

            except Exception as e:
                logger.error(f"Failed to convert lead {self.pk}: {str(e)}")
                raise ValidationError(f"Failed to convert lead: {str(e)}")

    def update_last_contact(self):
        """Update last contact timestamp"""
        self.last_contacted = timezone.now()
        self.save(update_fields=['last_contacted', 'updated_at'])

    @property
    def days_since_last_contact(self):
        """Calculate days since last contact"""
        if not self.last_contacted:
            return None
        return (timezone.now() - self.last_contacted).days

    @property
    def is_convertible(self):
        """Check if lead can be converted"""
        return self.status in ['qualified', 'negotiating'] and not self.converted_to_customer

    @property
    def is_stale(self):
        """Check if lead is stale (no contact in 30 days)"""
        if not self.last_contacted:
            return True
        return (timezone.now() - self.last_contacted).days > 30

    def get_related_tasks(self):
        """Get all related tasks"""
        return self.tasks.all().order_by('-created_at')

    def get_related_meetings(self):
        """Get all related meetings"""
        return self.meetings.all().order_by('-start_time')

    def get_contact_history(self):
        """Get all contact history (notes)"""
        return self.lead_notes.all().order_by('-created_at')


class Service(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('service-detail', kwargs={'pk': self.pk})

class Note(models.Model):
    NOTE_TYPES = [
        ('general', 'General'),
        ('meeting', 'Meeting'),
        ('call', 'Call'),
        ('email', 'Email'),
        ('task', 'Task')
    ]

    title = models.CharField(max_length=200)
    content = models.TextField()
    note_type = models.CharField(max_length=20, choices=NOTE_TYPES)
    created_by = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='notes')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True, related_name='notes')
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True, related_name='lead_notes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('note-detail', kwargs={'pk': self.pk})

class Task(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High')
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    due_date = models.DateTimeField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    assigned_to = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='tasks')
    created_by = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='created_tasks')  # ✅ Add this
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True, related_name='tasks')
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True, related_name='tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('task-detail', kwargs={'pk': self.pk})

class MeetingManager(models.Manager):
    def get_upcoming_meetings(self, user):
        """Get upcoming meetings for a user"""
        now = timezone.now()
        return self.filter(
            models.Q(organizer__user=user) | models.Q(attendees__user=user),
            start_time__gt=now
        ).distinct()

    def get_ongoing_meetings(self, user):
        """Get ongoing meetings for a user"""
        now = timezone.now()
        return self.filter(
            models.Q(organizer__user=user) | models.Q(attendees__user=user),
            start_time__lte=now,
            end_time__gt=now
        ).distinct()

class Meeting(models.Model):
    """
    Meeting model with improved scheduling and integration handling
    """

    MEETING_TYPES = [
        ('zoom', 'Zoom Meeting'),
        ('in_person', 'In Person'),
        ('phone', 'Phone Call'),
        ('teams', 'Microsoft Teams'),
        ('google_import', 'Google Calendar Import'),
        ('other', 'Other')
    ]

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rescheduled', 'Rescheduled')
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High')
    ]

    # Basic meeting information
    title = models.CharField(
        max_length=200,
        help_text="Meeting title"
    )

    description = models.TextField(
        blank=True,
        help_text="Meeting description and agenda"
    )

    # Schedule information
    start_time = models.DateTimeField(
        help_text="Meeting start time"
    )

    end_time = models.DateTimeField(
        help_text="Meeting end time"
    )

    # Meeting classification
    meeting_type = models.CharField(
        max_length=20,
        choices=MEETING_TYPES,
        help_text="Type of meeting"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='scheduled'
    )

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium'
    )

    # Location information
    location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Physical meeting location if applicable"
    )

    # Zoom specific fields
    zoom_meeting_id = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )

    zoom_meeting_password = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    zoom_join_url = models.URLField(
        blank=True,
        null=True
    )

    # Participant information
    organizer = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='organized_meetings'
    )

    attendees = models.ManyToManyField(
        'Employee',
        related_name='attending_meetings',
        blank=True
    )

    customers = models.ManyToManyField(
        'Customer',
        related_name='customer_meetings',
        blank=True
    )

    leads = models.ManyToManyField(
        'Lead',
        related_name='lead_meetings',
        blank=True
    )

    # Tracking fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reminder_sent = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    # Custom manager
    objects = MeetingManager()

    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['start_time', 'end_time']),
            models.Index(fields=['meeting_type', 'status']),
            models.Index(fields=['organizer']),
        ]
        permissions = [
            ("can_schedule_meetings", "Can schedule meetings"),
            ("can_cancel_meetings", "Can cancel meetings"),
        ]

    def __str__(self):
        return f"{self.title} - {self.start_time}"

    def clean(self):
        """Validate meeting data"""
        # Validate meeting times
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("End time must be after start time")

            if self.start_time < timezone.now() and not self.pk:
                raise ValidationError("Cannot schedule meetings in the past")

            # Maximum meeting duration validation
            max_duration = timedelta(hours=8)
            if (self.end_time - self.start_time) > max_duration:
                raise ValidationError("Meeting duration cannot exceed 8 hours")

        # Validate meeting type specific requirements
        if self.meeting_type == 'zoom' and not settings.ZOOM_API_KEY:
            raise ValidationError("Zoom API credentials not configured")

        if self.meeting_type == 'in_person' and not self.location:
            raise ValidationError("Location is required for in-person meetings")

    def save(self, *args, **kwargs):
        """Override save for additional processing"""
        self.full_clean()

        # Handle Zoom meeting creation/updates
        if self.meeting_type == 'zoom':
            self._handle_zoom_meeting()

        # Update status based on time
        self._update_status_based_on_time()

        super().save(*args, **kwargs)

    def _get_zoom_client(self) -> Optional[ZoomClient]:
        """Get configured Zoom client"""
        try:
            return ZoomClient(
                api_key=settings.ZOOM_API_KEY,
                api_secret=settings.ZOOM_API_SECRET
            )
        except Exception as e:
            logger.error(f"Failed to initialize Zoom client: {str(e)}")
            return None

    def _handle_zoom_meeting(self):
        """Handle Zoom meeting creation and updates"""
        client = self._get_zoom_client()
        if not client:
            return

        try:
            if not self.zoom_meeting_id:
                self._create_zoom_meeting(client)
            else:
                self._update_zoom_meeting(client)
        except Exception as e:
            logger.error(f"Zoom API error: {str(e)}")
            raise ValidationError(f"Failed to manage Zoom meeting: {str(e)}")

    def _create_zoom_meeting(self, client: ZoomClient):
        """Create a new Zoom meeting"""
        try:
            meeting_data = {
                "topic": self.title,
                "type": 2,  # Scheduled meeting
                "start_time": self.start_time.isoformat(),
                "duration": int((self.end_time - self.start_time).total_seconds() / 60),
                "timezone": settings.TIME_ZONE,
                "agenda": self.description,
                "settings": {
                    "host_video": True,
                    "participant_video": True,
                    "join_before_host": False,
                    "mute_upon_entry": True,
                    "waiting_room": True,
                    "meeting_authentication": True
                }
            }

            response = client.meeting.create(**meeting_data)

            self.zoom_meeting_id = response.get('id')
            self.zoom_meeting_password = response.get('password')
            self.zoom_join_url = response.get('join_url')

            logger.info(f"Created Zoom meeting: {self.zoom_meeting_id}")

        except Exception as e:
            logger.error(f"Failed to create Zoom meeting: {str(e)}")
            raise

    def _update_zoom_meeting(self, client: ZoomClient):
        """Update existing Zoom meeting"""
        try:
            meeting_data = {
                "topic": self.title,
                "start_time": self.start_time.isoformat(),
                "duration": int((self.end_time - self.start_time).total_seconds() / 60),
                "agenda": self.description
            }

            client.meeting.update(meeting_id=self.zoom_meeting_id, **meeting_data)
            logger.info(f"Updated Zoom meeting: {self.zoom_meeting_id}")

        except Exception as e:
            logger.error(f"Failed to update Zoom meeting: {str(e)}")
            raise

    def _update_status_based_on_time(self):
        """Update meeting status based on current time"""
        now = timezone.now()

        if self.status != 'cancelled':
            if now < self.start_time:
                self.status = 'scheduled'
            elif self.start_time <= now <= self.end_time:
                self.status = 'in_progress'
            else:
                self.status = 'completed'

    def cancel_meeting(self, reason: str = None):
        """Cancel the meeting and clean up"""
        with transaction.atomic():
            if self.meeting_type == 'zoom' and self.zoom_meeting_id:
                client = self._get_zoom_client()
                if client:
                    try:
                        client.meeting.delete(meeting_id=self.zoom_meeting_id)
                    except Exception as e:
                        logger.error(f"Failed to delete Zoom meeting: {str(e)}")

            self.status = 'cancelled'
            if reason:
                self.notes += f"\nCancellation reason: {reason}"
            self.save()

    def get_absolute_url(self):
        """Get URL for meeting detail view"""
        from django.urls import reverse
        return reverse('meeting-detail', kwargs={'pk': self.pk})

    def get_attendee_emails(self) -> List[str]:
        """Get list of all attendee emails"""
        emails = set()

        # Add employee emails
        emails.update(self.attendees.values_list('user__email', flat=True))

        # Add customer emails
        emails.update(self.customers.values_list('email', flat=True))

        # Add lead emails
        emails.update(self.leads.values_list('email', flat=True))

        return list(filter(None, emails))

    def get_duration(self) -> int:
        """Get meeting duration in minutes"""
        return int((self.end_time - self.start_time).total_seconds() / 60)

    @property
    def is_upcoming(self) -> bool:
        """Check if meeting is upcoming"""
        return self.start_time > timezone.now()

    @property
    def is_ongoing(self) -> bool:
        """Check if meeting is currently ongoing"""
        now = timezone.now()
        return self.start_time <= now <= self.end_time

    @property
    def is_past(self) -> bool:
        """Check if meeting is in the past"""
        now = timezone.now()

        # Compare against start time, not end time
        meeting_time = self.start_time

        # Ensure both times are timezone-aware for proper comparison
        if not timezone.is_aware(meeting_time):
            meeting_time = timezone.make_aware(meeting_time)

        is_past = meeting_time < now
        print(f"Now: {now}, Meeting start time: {meeting_time}, Is past: {is_past}")
        return is_past
        @property
        def can_be_cancelled(self) -> bool:
            """Check if meeting can be cancelled"""
            return self.status in ['scheduled', 'rescheduled'] and self.start_time > timezone.now()


# core/models.py (Invoice model updates)

class Invoice(models.Model):
    """
    Represents customer invoices
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled')
    ]

    invoice_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey('core.Customer', on_delete=models.CASCADE, related_name='invoices')
    project = models.ForeignKey('customer_projects.Project', on_delete=models.SET_NULL,
                               null=True, blank=True, related_name='invoices')
    issue_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Invoice #{self.invoice_number} - {self.customer.company_name}"

    def save(self, *args, **kwargs):
        # Generate invoice number if not set
        if not self.invoice_number:
            last_invoice = Invoice.objects.order_by('-created_at').first()
            if last_invoice and last_invoice.invoice_number:
                try:
                    # Extract the numeric part and increment
                    numeric_part = int(last_invoice.invoice_number.split('-')[1])
                    self.invoice_number = f"INV-{numeric_part + 1:06d}"
                except (IndexError, ValueError):
                    # Fallback if parsing fails
                    self.invoice_number = f"INV-{timezone.now().strftime('%Y%m%d')}-001"
            else:
                # First invoice
                self.invoice_number = f"INV-{timezone.now().strftime('%Y%m%d')}-001"

        # Calculate totals from line items if they exist and invoice is being updated
        if self.pk and not kwargs.get('skip_calculation', False):
            self.update_totals()

        # Remove the custom argument if present
        if 'skip_calculation' in kwargs:
            del kwargs['skip_calculation']

        super().save(*args, **kwargs)

    @property
    def balance_due(self):
        """Calculate the remaining balance to be paid"""
        return self.total - self.amount_paid

    def update_totals(self):
        """
        Recalculate invoice totals from line items
        """
        line_items = self.line_items.all()
        self.subtotal = sum(item.amount for item in line_items)
        # Calculate tax based on taxable items
        self.tax_amount = sum(item.amount * (item.tax_rate / 100) for item in line_items if item.tax_rate > 0)
        self.total = self.subtotal + self.tax_amount

    def update_status(self):
        """Comprehensive invoice status management"""
        now = timezone.now().date()

        # Calculate total payments
        amount_paid = sum(payment.amount for payment in self.payments.filter(status='completed'))

        # Update amount paid instead of balance_due
        self.amount_paid = amount_paid

        # Status transitions
        if amount_paid >= self.total:
            self.status = 'paid'
            self.last_payment_date = timezone.now()
        elif amount_paid > Decimal('0.00') and amount_paid < self.total:
            self.status = 'partial'
        elif now > self.due_date and (self.total - amount_paid) > Decimal('0.00'):
            self.status = 'overdue'
        else:
            self.status = 'pending'

        self.save()

class InvoiceLineItem(models.Model):
    """
    Line items for invoices
    """
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='line_items')
    project_name = models.CharField(max_length=200, blank=True)
    project_code = models.CharField(max_length=50, blank=True)
    task_description = models.CharField(max_length=200, blank=True)
    product_or_service = models.CharField(max_length=200)
    description = models.TextField()
    quantity = models.DecimalField(max_digits=8, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.product_or_service} - ${self.amount}"

    def save(self, *args, **kwargs):
        # Calculate amount if not set
        if not self.amount:
            self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)

        # Update invoice totals if not specified otherwise
        if not kwargs.get('skip_invoice_update', False) and self.invoice:
            self.invoice.update_totals()
            self.invoice.save(skip_calculation=True)  # Avoid circular updates



# core/models.py (Payment model updates)

# core/models.py (Payment model updates)

class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded')
    ]

    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('credit_card', 'Credit Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('check', 'Check'),
        ('online', 'Online Payment')
    ]

    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='payments')
    invoice = models.ForeignKey('Invoice', on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, null=True, blank=True)
    transaction_date = models.DateTimeField(default=timezone.now)

    # Add reference field
    reference = models.CharField(max_length=50, unique=True, null=True, blank=True)

    def __str__(self):
        return f"Payment #{self.id} - {self.customer.company_name} - {self.status}"

    def save(self, *args, **kwargs):
        """
        Enhanced save method with payment processing logic
        """
        # Generate reference number if not provided
        if not hasattr(self, 'reference') or not self.reference:
            self.reference = self.generate_reference_number()

        # Validate payment amount
        if self.amount <= 0:
            raise ValueError("Payment amount must be greater than zero")

        # Prevent overpayment
        if self.invoice:
            max_payable = self.invoice.balance_due
            if self.amount > max_payable:
                raise ValueError(f"Payment amount exceeds outstanding balance of {max_payable}")

        # Save payment
        super().save(*args, **kwargs)

        # Update invoice status after payment
        if self.invoice:
            self.invoice.update_status()


    def generate_reference_number(self):
        """
        Generate a unique payment reference number
        """
        while True:
            # Combine timestamp and random string for uniqueness
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
            random_suffix = get_random_string(length=6, allowed_chars='0123456789ABCDEF')
            ref_number = f"PAY-{timestamp}-{random_suffix}"

            # Ensure the reference is unique
            if not Payment.objects.filter(reference=ref_number).exists():
                return ref_number

    def create_transaction(self):
        """
        Create a transaction record for the payment
        """
        if self.status == 'completed':
            from .models import Transaction  # Import here to avoid circular import

            Transaction.objects.create(
                customer=self.customer,
                invoice=self.invoice,
                payment=self,
                transaction_type='invoice_payment',
                amount=self.amount,
                reference=self.reference,
                transaction_date=self.transaction_date,
                status='completed'
            )

    def validate_payment(self):
        """
        Comprehensive payment validation
        """
        # Check invoice exists and is payable
        if not self.invoice.can_generate_payment():
            raise ValueError("Cannot make payment on this invoice")

        # Validate payment method
        if not self.payment_method:
            raise ValueError("Payment method is required")

        # Additional custom validation can be added here
        return True

    class Meta:
        verbose_name_plural = "Payments"
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['customer', 'transaction_date']),
            models.Index(fields=['invoice', 'transaction_date']),
            models.Index(fields=['status', 'transaction_date'])
        ]


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired')
    ]

    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='billing_subscriptions')
    plan = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')  # ✅ Add this

    def __str__(self):
        return f"{self.customer} - {self.plan} ({self.get_status_display()})"

    def get_absolute_url(self):
        return reverse('subscription-detail', kwargs={'pk': self.pk})


# core/models.py (Transaction model updates)

# core/models.py (Transaction model updates)

class Transaction(models.Model):
    TRANSACTION_TYPE = [
        ('invoice_payment', 'Invoice Payment'),
        ('refund', 'Refund'),
        ('subscription', 'Subscription Payment'),
        ('credit', 'Credit'),
        ('adjustment', 'Adjustment')
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('reversed', 'Reversed')
    ]

    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='transactions')
    invoice = models.ForeignKey('Invoice', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    payment = models.ForeignKey('Payment', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    subscription = models.ForeignKey('ServiceSubscription', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_date = models.DateTimeField(default=timezone.now)
    reference = models.CharField(max_length=50, unique=True, null=True, blank=True)

    # Additional metadata fields
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, related_name='created_transactions')

    def __str__(self):
        return f"{self.customer.company_name} - {self.get_transaction_type_display()} - {self.amount}"

    def save(self, *args, **kwargs):
        """
        Override save method to ensure unique reference and additional validations
        """
        # Always generate a unique reference if not provided or already exists
        if not self.reference or Transaction.objects.filter(reference=self.reference).exists():
            self.reference = self.generate_unique_reference()

        # Validate transaction amount
        if self.amount <= 0:
            raise ValueError("Transaction amount must be positive")

        # Additional validation based on transaction type
        self.validate_transaction()

        # Use force_insert to handle potential race conditions
        super().save(*args, **kwargs)

    def generate_unique_reference(self):
        """
        Generate a unique transaction reference number with additional uniqueness checks
        """
        while True:
            # Combine timestamp, random string, and prefix for maximum uniqueness
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
            random_suffix = get_random_string(length=6, allowed_chars='0123456789ABCDEF')
            ref_number = f"TXN-{timestamp}-{random_suffix}"

            # Ensure the reference is truly unique
            if not Transaction.objects.filter(reference=ref_number).exists():
                return ref_number

    def validate_transaction(self):
        """
        Validate transaction based on its type
        """
        # Ensure required relationships exist based on transaction type
        if self.transaction_type == 'invoice_payment' and not self.invoice:
            raise ValueError("Invoice is required for invoice payment transactions")

        if self.transaction_type == 'subscription' and not self.subscription:
            raise ValueError("Subscription is required for subscription transactions")

        # Additional type-specific validations can be added here

    def mark_completed(self):
        """
        Mark transaction as completed
        """
        self.status = 'completed'
        self.save()

    def mark_failed(self, reason=None):
        """
        Mark transaction as failed with optional reason
        """
        self.status = 'failed'
        if reason:
            self.notes = reason
        self.save()

    def reverse_transaction(self, reason=None):
        """
        Reverse a completed transaction
        """
        if self.status != 'completed':
            raise ValueError("Only completed transactions can be reversed")

        self.status = 'reversed'
        if reason:
            self.notes = reason
        self.save()

        # Create a reverse transaction
        reverse_transaction = Transaction.objects.create(
            customer=self.customer,
            invoice=self.invoice,
            subscription=self.subscription,
            transaction_type=self.transaction_type,
            amount=-self.amount,  # Negative amount to reverse
            notes=f"Reversal of {self.reference}",
            status='completed'
        )

        return reverse_transaction

    class Meta:
        verbose_name_plural = "Transactions"
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['customer', 'transaction_date']),
            models.Index(fields=['invoice', 'transaction_date']),
            models.Index(fields=['status', 'transaction_date'])
        ]

# core/models.py (ServiceSubscription model updates)

class ServiceSubscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('canceled', 'Canceled'),
        ('expired', 'Expired'),
    ]

    BILLING_CYCLE_CHOICES = [
        ('hourly', 'Hourly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]

    # Core fields
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='service_subscriptions')
    service = models.ForeignKey('Service', on_delete=models.CASCADE, related_name='service_subscriptions')

    # Dates
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)

    # Billing details
    billing_cycle = models.CharField(
        max_length=20,
        choices=BILLING_CYCLE_CHOICES,
        default='monthly'
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    hours = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)

    # Status tracking
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    invoice_generated = models.BooleanField(default=False)

    class Meta:
        ordering = ['-start_date']
        verbose_name = "Service Subscription"
        verbose_name_plural = "Service Subscriptions"
        indexes = [
            models.Index(fields=['customer', 'service', 'status']),
            models.Index(fields=['start_date', 'end_date']),
        ]

    def __str__(self):
        return f"{self.customer.company_name} - {self.service.name} ({self.get_status_display()})"

    def calculate_total(self):
        """Calculate total price for the subscription based on billing cycle"""
        if self.billing_cycle == 'hourly':
            if self.hours <= 0 or self.hourly_rate <= 0:
                return Decimal('0.00')
            return Decimal(str(self.hours)) * Decimal(str(self.hourly_rate))

        if self.billing_cycle == 'monthly':
            return Decimal(str(self.price))
        elif self.billing_cycle == 'quarterly':
            return Decimal(str(self.price)) * Decimal('3')
        elif self.billing_cycle == 'yearly':
            return Decimal(str(self.price)) * Decimal('12')

        return Decimal(str(self.price))

    def generate_unique_invoice_number(self):
        """Generate a unique invoice number with collision checking"""
        while True:
            invoice_number = f"INV-{random.randint(100000, 999999)}"
            from .models import Invoice  # Import here to avoid circular import
            if not Invoice.objects.filter(invoice_number=invoice_number).exists():
                return invoice_number

    def generate_invoice(self):
        """Generate an invoice for the service subscription"""
        from .models import Invoice  # Import here to avoid circular import

        with transaction.atomic():
            try:
                # Check for existing invoice
                existing_invoice = Invoice.objects.filter(
                    customer=self.customer,
                    status__in=['pending', 'overdue']
                ).first()

                if existing_invoice:
                    existing_invoice.services.add(self)
                    return existing_invoice

                if self.invoice_generated:
                    return None

                # Calculate total and generate number
                total_amount = self.calculate_total()
                invoice_number = self.generate_unique_invoice_number()

                # Create invoice first
                invoice = Invoice.objects.create(
                    customer=self.customer,
                    invoice_number=invoice_number,
                    issue_date=timezone.now().date(),
                    due_date=timezone.now().date() + timedelta(days=30),
                    total_amount=total_amount,
                    amount_due=total_amount,
                    status='pending'
                )

                # Add service subscription after invoice is created
                invoice.services.add(self)
                invoice.save()

                return invoice

            except Exception as e:
                logger.error(f"Error generating invoice: {str(e)}")
                raise

    def save(self, *args, **kwargs):
        """Override save method to handle invoice generation"""
        is_new = self.pk is None

        # Set end date based on billing cycle if not provided
        if self.billing_cycle in ['monthly', 'quarterly', 'yearly'] and not self.end_date:
            if self.billing_cycle == 'monthly':
                self.end_date = self.start_date + relativedelta(months=1)
            elif self.billing_cycle == 'quarterly':
                self.end_date = self.start_date + relativedelta(months=3)
            elif self.billing_cycle == 'yearly':
                self.end_date = self.start_date + relativedelta(years=1)

        # First, save the subscription itself
        super().save(*args, **kwargs)

        # Generate invoice for new active subscriptions
        if (is_new and
            self.is_active and
            not self.invoice_generated and
            not kwargs.get('update_fields')):
            try:
                with transaction.atomic():
                    invoice = self.generate_invoice()
                    if invoice:
                        self.invoice_generated = True
                        self.save(update_fields=['invoice_generated'])
            except Exception as e:
                logger.error(f"Error generating invoice for service subscription {self.id}: {str(e)}")
                raise

    def update_status(self):
        """Update subscription status based on various conditions"""
        now = timezone.now().date()

        if self.end_date and now > self.end_date:
            self.status = 'expired'
        elif not self.is_active:
            self.status = 'canceled'

        self.save(update_fields=['status'])

    def get_duration_days(self):
        """Calculate the duration of the subscription in days"""
        if not self.end_date:
            return None
        return (self.end_date - self.start_date).days

    def is_expired(self):
        """Check if the subscription is expired"""
        if not self.end_date:
            return False
        return timezone.now().date() > self.end_date

class UploadedICSFile(models.Model):
    file = models.FileField(upload_to='uploads/ics/')
    uploaded_by = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='uploaded_ics_files')
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, null=True, blank=True, related_name='ics_files')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.customer:
            return f"ICS Upload for {self.customer.company_name} by {self.uploaded_by.user.get_full_name()}"
        return f"ICS Upload by {self.uploaded_by.user.get_full_name()}"


class EventManager(models.Manager):
    def get_events_in_range(self, start_date, end_date, user=None):
        """Get all events within a date range"""
        queryset = self.get_queryset()
        if user:
            queryset = queryset.filter(
                models.Q(created_by__user=user) |
                models.Q(attendees__user=user)
            ).distinct()

        return queryset.filter(
            models.Q(start_time__range=(start_date, end_date)) |
            models.Q(end_time__range=(start_date, end_date))
        )

    def get_conflicting_events(self, start_time, end_time, exclude_id=None):
        """Find conflicting events in the given time range"""
        queryset = self.get_queryset()
        if exclude_id:
            queryset = queryset.exclude(id=exclude_id)

        return queryset.filter(
            models.Q(start_time__lt=end_time) &
            models.Q(end_time__gt=start_time)
        )

class Event(models.Model):
    """
    Event model with improved calendar integration and recurrence handling
    """

    EVENT_TYPES = [
        ('meeting', 'Meeting'),
        ('task', 'Task'),
        ('call', 'Phone Call'),
        ('reminder', 'Reminder'),
        ('appointment', 'Appointment'),
        ('custom', 'Custom Event')
    ]

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rescheduled', 'Rescheduled')
    ]

    RECURRENCE_CHOICES = [
        ('none', 'None'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('custom', 'Custom')
    ]

    # Basic event information
    title = models.CharField(
        max_length=255,
        help_text="Event title"
    )

    description = models.TextField(
        blank=True,
        null=True,
        help_text="Event description"
    )

    location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Event location"
    )

    # Timing information
    start_time = models.DateTimeField(
        help_text="Event start time"
    )

    end_time = models.DateTimeField(
        help_text="Event end time"
    )

    # Event classification
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPES,
        default='custom',
        help_text="Type of event"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='scheduled'
    )

    # Recurrence settings
    is_recurring = models.BooleanField(
        default=False,
        help_text="Whether this event repeats"
    )

    recurrence_type = models.CharField(
        max_length=20,
        choices=RECURRENCE_CHOICES,
        default='none'
    )

    recurrence_rule = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="iCal RRULE format for recurring events"
    )

    recurrence_end = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the recurrence ends"
    )

    # Participants
    created_by = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='created_events'
    )

    attendees = models.ManyToManyField(
        'Employee',
        related_name='attending_events',
        blank=True
    )

    customer = models.ForeignKey(
        'Customer',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="customer_events"
    )

    # UI customization
    color = models.CharField(
        max_length=7,
        default="#3788d8",
        help_text="Event color in calendar"
    )

    # Reminder settings
    reminder_sent = models.BooleanField(
        default=False
    )

    reminder_minutes = models.IntegerField(
        default=15,
        help_text="Minutes before event to send reminder"
    )

    # Tracking fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom manager
    objects = EventManager()

    class Meta:
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['start_time', 'end_time']),
            models.Index(fields=['event_type', 'status']),
            models.Index(fields=['created_by', 'is_recurring']),
        ]
        permissions = [
            ("can_manage_events", "Can manage events"),
            ("can_view_all_events", "Can view all events"),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_event_type_display()}) - {self.start_time.strftime('%Y-%m-%d %H:%M')}"

    def clean(self):
        """Validate event data"""
        if self.start_time and self.end_time:
            # Validate event times
            if self.start_time >= self.end_time:
                raise ValidationError("End time must be after start time")

            # Check for conflicts
            conflicts = self._get_conflicts()
            if conflicts:
                raise ValidationError(
                    f"Event conflicts with existing events: {', '.join(str(e) for e in conflicts)}"
                )

        # Validate recurrence
        if self.is_recurring and not self.recurrence_rule:
            raise ValidationError("Recurrence rule is required for recurring events")

        if self.is_recurring and self.recurrence_rule:
            try:
                rrulestr(self.recurrence_rule)
            except ValueError as e:
                raise ValidationError(f"Invalid recurrence rule: {str(e)}")

    def save(self, *args, **kwargs):
        """Override save for additional processing"""
        self.full_clean()

        # Update status based on time
        self._update_status_based_on_time()

        super().save(*args, **kwargs)

    def _get_conflicts(self) -> List['Event']:
        """Get conflicting events"""
        return Event.objects.get_conflicting_events(
            self.start_time,
            self.end_time,
            exclude_id=self.pk
        )

    def _update_status_based_on_time(self):
        """Update event status based on current time"""
        if self.status not in ['cancelled', 'rescheduled']:
            now = timezone.now()
            if now < self.start_time:
                self.status = 'scheduled'
            elif self.start_time <= now <= self.end_time:
                self.status = 'in_progress'
            else:
                self.status = 'completed'

    def get_absolute_url(self):
        """Get URL for event detail view"""
        return reverse('event-detail', kwargs={'pk': self.pk})

    def get_calendar_event_data(self):
        """Return event data formatted for FullCalendar"""
        return {
            'id': self.id,
            'title': self.title,
            'start': self.start_time.isoformat(),
            'end': self.end_time.isoformat(),
            'description': self.description or '',
            'location': self.location or '',
            'eventType': self.event_type,
            'status': self.status,
            'color': self.color,
            'url': self.get_absolute_url(),
            'extendedProps': {
                'createdBy': self.created_by.get_full_name(),
                'customer': self.customer.company_name if self.customer else None,
                'attendees': [att.get_full_name() for att in self.attendees.all()],
                'isRecurring': self.is_recurring,
                'recurrenceRule': self.recurrence_rule
            }
        }

    def cancel(self, reason: Optional[str] = None):
        """Cancel the event"""
        self.status = 'cancelled'
        if reason:
            self.description = f"{self.description}\n\nCancelled: {reason}"
        self.save()

    def reschedule(self, new_start_time, new_end_time):
        """Reschedule the event"""
        old_start = self.start_time
        old_end = self.end_time

        self.start_time = new_start_time
        self.end_time = new_end_time
        self.status = 'rescheduled'

        try:
            self.save()
            logger.info(f"Event {self.pk} rescheduled from {old_start} to {new_start_time}")
        except ValidationError as e:
            self.start_time = old_start
            self.end_time = old_end
            raise ValidationError(f"Could not reschedule event: {str(e)}")

    def get_recurrence_instances(self, start_date, end_date):
        """Get all recurrence instances between dates"""
        if not self.is_recurring or not self.recurrence_rule:
            return []

        try:
            rule = rrulestr(self.recurrence_rule, dtstart=self.start_time)
            instances = rule.between(start_date, end_date)
            return [self._create_instance_data(dt) for dt in instances]
        except Exception as e:
            logger.error(f"Error calculating recurrence instances: {str(e)}")
            return []

    def _create_instance_data(self, start_datetime):
        """Create event data for a recurrence instance"""
        duration = self.end_time - self.start_time
        return {
            'title': self.title,
            'start': start_datetime,
            'end': start_datetime + duration,
            'recurring_event_id': self.pk
        }

    @property
    def duration_minutes(self):
        """Get event duration in minutes"""
        return int((self.end_time - self.start_time).total_seconds() / 60)

    @property
    def is_upcoming(self):
        """Check if event is upcoming"""
        return self.start_time > timezone.now()

    @property
    def is_ongoing(self):
        """Check if event is currently ongoing"""
        now = timezone.now()
        return self.start_time <= now <= self.end_time

    @property
    def is_past(self):
        """Check if event is in the past"""
        return self.end_time < timezone.now()

    @property
    def can_be_modified(self):
        """Check if event can be modified"""
        return self.status not in ['completed', 'cancelled'] and not self.is_past


# IP Address Tracking Cookie Stuff:

class IPAccess(models.Model):
    ip_address = models.GenericIPAddressField()
    user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    path = models.CharField(max_length=255)
    access_time = models.DateTimeField(default=timezone.now)
    user_agent = models.TextField(null=True, blank=True)
    method = models.CharField(max_length=10)  # GET, POST, etc.
    is_ajax = models.BooleanField(default=False)
    is_secure = models.BooleanField(default=False)

    class Meta:
        ordering = ['-access_time']
        indexes = [
            models.Index(fields=['ip_address', 'access_time']),
            models.Index(fields=['user', 'access_time']),
        ]

    def __str__(self):
        return f"{self.ip_address} - {self.access_time}"



class ScheduleException(models.Model):
    """
    Allows marking specific dates as unavailable or having special rules
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='schedule_exceptions')
    date = models.DateField()
    is_available = models.BooleanField(default=False)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Exception for {self.user.username} on {self.date}"


class ScheduleRuleManager(models.Manager):
    def get_active_rules_for_user(self, user: User) -> models.QuerySet:
        """Get all active scheduling rules for a user"""
        return self.filter(user=user, is_active=True)

    def get_rules_for_date(self, user: User, date) -> models.QuerySet:
        """Get applicable rules for a specific date"""
        weekday = date.strftime('%A').lower()
        return self.filter(
            user=user,
            is_active=True,
        ).filter(
            models.Q(recurrence_type='daily') |
            models.Q(recurrence_type='weekly', day_of_week=weekday) |
            models.Q(recurrence_type='monthly', day_of_month=date.day) |
            models.Q(recurrence_type='yearly', month=date.month, day_of_month=date.day)
        )

class ScheduleRuleManager(models.Manager):
    def get_active_rules_for_user(self, user: User) -> models.QuerySet:
        """Get all active scheduling rules for a user"""
        return self.filter(user=user, is_active=True)

    def get_rules_for_date(self, user: User, date) -> models.QuerySet:
        """Get applicable rules for a specific date"""
        weekday = date.strftime('%A').lower()
        return self.filter(
            user=user,
            is_active=True,
        ).filter(
            models.Q(recurrence_type='daily') |
            models.Q(recurrence_type='weekly', day_of_week=weekday) |
            models.Q(recurrence_type='monthly', day_of_month=date.day) |
            models.Q(recurrence_type='yearly', month=date.month, day_of_month=date.day)
        )

class ScheduleRule(models.Model):
    """
    Schedule Rule model for managing availability and booking rules
    """

    RECURRENCE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly')
    ]

    DAYS_OF_WEEK = [
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday')
    ]

    MONTHS = [
        (1, 'January'), (2, 'February'), (3, 'March'),
        (4, 'April'), (5, 'May'), (6, 'June'),
        (7, 'July'), (8, 'August'), (9, 'September'),
        (10, 'October'), (11, 'November'), (12, 'December')
    ]

    # Basic Information
    name = models.CharField(
        max_length=100,
        help_text="Name of the scheduling rule"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='schedule_rules'
    )

    # Recurrence Settings
    recurrence_type = models.CharField(
        max_length=10,
        choices=RECURRENCE_CHOICES,
        help_text="How often this rule repeats"
    )

    # Time Constraints
    start_time = models.TimeField(
        help_text="Daily start time for availability"
    )

    end_time = models.TimeField(
        help_text="Daily end time for availability"
    )

    # Recurrence Pattern Details
    day_of_week = models.CharField(
        max_length=10,
        choices=DAYS_OF_WEEK,
        null=True,
        blank=True,
        help_text="Specific day for weekly recurrence"
    )

    day_of_month = models.IntegerField(
        null=True,
        blank=True,
        help_text="Day of month (1-31) for monthly/yearly recurrence"
    )

    month = models.IntegerField(
        choices=MONTHS,
        null=True,
        blank=True,
        help_text="Month for yearly recurrence"
    )

    # Booking Constraints
    max_bookings_per_day = models.IntegerField(
        default=5,
        help_text="Maximum number of bookings allowed per day"
    )

    min_booking_duration = models.IntegerField(
        default=30,
        help_text="Minimum booking duration in minutes"
    )

    max_booking_duration = models.IntegerField(
        default=240,
        help_text="Maximum booking duration in minutes"
    )

    # Buffer Times
    buffer_before = models.IntegerField(
        default=15,
        help_text="Required buffer time before bookings (minutes)"
    )

    buffer_after = models.IntegerField(
        default=15,
        help_text="Required buffer time after bookings (minutes)"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this rule is currently active"
    )

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom manager
    objects = ScheduleRuleManager()

    class Meta:
        ordering = ['recurrence_type', 'start_time']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['recurrence_type', 'day_of_week']),
            models.Index(fields=['start_time', 'end_time']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(max_booking_duration__gt=models.F('min_booking_duration')),
                name='max_duration_greater_than_min'
            ),
            models.CheckConstraint(
                check=models.Q(day_of_month__gte=1) & models.Q(day_of_month__lte=31),
                name='valid_day_of_month'
            )
        ]

    def __str__(self):
        return f"{self.name} - {self.get_recurrence_type_display()}"

    def clean(self):
        """Validate schedule rule data"""
        # Validate time constraints
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time")

        # Validate duration constraints
        if self.min_booking_duration >= self.max_booking_duration:
            raise ValidationError("Maximum duration must be greater than minimum duration")

        # Validate recurrence-specific fields
        self._validate_recurrence_fields()

        # Validate buffer times
        total_buffer = self.buffer_before + self.buffer_after
        available_minutes = (
            datetime.combine(timezone.now(), self.end_time) -
            datetime.combine(timezone.now(), self.start_time)
        ).seconds / 60

        if total_buffer + self.min_booking_duration > available_minutes:
            raise ValidationError("Buffer times plus minimum booking duration exceed available time")

    def _validate_recurrence_fields(self):
        """Validate fields specific to recurrence type"""
        if self.recurrence_type == 'weekly':
            if not self.day_of_week:
                raise ValidationError("Day of week is required for weekly recurrence")
            if self.day_of_month or self.month:
                raise ValidationError("Monthly/Yearly fields should not be set for weekly recurrence")

        elif self.recurrence_type == 'monthly':
            if not self.day_of_month:
                raise ValidationError("Day of month is required for monthly recurrence")
            if self.day_of_week or self.month:
                raise ValidationError("Weekly/Yearly fields should not be set for monthly recurrence")

        elif self.recurrence_type == 'yearly':
            if not all([self.month, self.day_of_month]):
                raise ValidationError("Month and day of month are required for yearly recurrence")
            if self.day_of_week:
                raise ValidationError("Weekly fields should not be set for yearly recurrence")

        elif self.recurrence_type == 'daily':
            if any([self.day_of_week, self.day_of_month, self.month]):
                raise ValidationError("Recurrence fields should not be set for daily recurrence")

    def check_availability(self, start_time, end_time) -> Dict[str, bool]:
        """
        Check if a time slot is available according to this rule
        Returns a dict with availability status and reason if unavailable
        """
        if not self.is_active:
            return {'available': False, 'reason': 'Rule is inactive'}

        # Check if date matches recurrence pattern
        if not self._date_matches_recurrence(start_time.date()):
            return {'available': False, 'reason': 'Date does not match recurrence pattern'}

        # Check time constraints
        if not (self.start_time <= start_time.time() and end_time.time() <= self.end_time):
            return {'available': False, 'reason': 'Time outside allowed hours'}

        # Check duration constraints
        duration = (end_time - start_time).total_seconds() / 60
        if not (self.min_booking_duration <= duration <= self.max_booking_duration):
            return {'available': False, 'reason': 'Duration outside allowed range'}

        # Check booking count for the day
        if not self._check_booking_count(start_time.date()):
            return {'available': False, 'reason': 'Maximum bookings reached for this day'}

        # Check buffer conflicts
        if not self._check_buffer_times(start_time, end_time):
            return {'available': False, 'reason': 'Conflicts with buffer time requirements'}

        return {'available': True, 'reason': None}

    def _date_matches_recurrence(self, date) -> bool:
        """Check if a date matches the recurrence pattern"""
        if self.recurrence_type == 'daily':
            return True
        elif self.recurrence_type == 'weekly':
            return date.strftime('%A').lower() == self.day_of_week
        elif self.recurrence_type == 'monthly':
            return date.day == self.day_of_month
        elif self.recurrence_type == 'yearly':
            return date.month == self.month and date.day == self.day_of_month
        return False

    def _check_booking_count(self, date) -> bool:
        """Check if more bookings are allowed for the day"""
        from .models import Event
        current_bookings = Event.objects.filter(
            created_by__user=self.user,
            start_time__date=date
        ).count()
        return current_bookings < self.max_bookings_per_day

    def _check_buffer_times(self, start_time, end_time) -> bool:
        """Check if the time slot respects buffer times"""
        from .models import Event
        buffer_start = start_time - timedelta(minutes=self.buffer_after)
        buffer_end = end_time + timedelta(minutes=self.buffer_before)

        conflicting_events = Event.objects.filter(
            created_by__user=self.user,
            end_time__gt=buffer_start,
            start_time__lt=buffer_end
        ).exists()

        return not conflicting_events

    def get_available_slots(self, date) -> List[Dict[str, time]]:
        """Get all available time slots for a given date"""
        if not self._date_matches_recurrence(date):
            return []

        slots = []
        current_time = datetime.combine(date, self.start_time)
        end_of_day = datetime.combine(date, self.end_time)

        while current_time + timedelta(minutes=self.min_booking_duration) <= end_of_day:
            slot_end = current_time + timedelta(minutes=self.min_booking_duration)
            if self.check_availability(current_time, slot_end)['available']:
                slots.append({
                    'start': current_time.time(),
                    'end': slot_end.time()
                })
            current_time += timedelta(minutes=15)  # 15-minute intervals

        return slots

    @property
    def available_hours(self) -> float:
        """Calculate total available hours per occurrence"""
        start = datetime.combine(timezone.now(), self.start_time)
        end = datetime.combine(timezone.now(), self.end_time)
        return (end - start).total_seconds() / 3600

    @property
    def is_weekend_rule(self) -> bool:
        """Check if rule applies to weekends"""
        return self.day_of_week in ['saturday', 'sunday']


class ChatSession(models.Model):
    participants = models.ManyToManyField(Employee, related_name='chat_sessions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_group_chat = models.BooleanField(default=False)
    name = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Chat Session {self.id} - {self.name or 'Direct Message'}"

    def get_messages(self):
        return self.messages.all().order_by('timestamp')

    def get_last_message(self):
        return self.messages.order_by('-timestamp').first()

class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, related_name='messages', on_delete=models.CASCADE)
    sender = models.ForeignKey(Employee, related_name='sent_messages', on_delete=models.CASCADE)
    receiver = models.ForeignKey(Employee, related_name='received_messages', on_delete=models.CASCADE)  # Add this line
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    # Message type for special messages (system notifications, alerts, etc.)
    MESSAGE_TYPES = [
        ('text', 'Text Message'),
        ('system', 'System Notification'),
        ('alert', 'Alert'),
    ]
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES, default='text')

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['session', 'timestamp']),
            models.Index(fields=['sender', 'timestamp']),
            models.Index(fields=['is_read', 'timestamp']),
        ]

    def __str__(self):
        return f"Message from {self.sender} at {self.timestamp}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()


class ChatNotification(models.Model):
    recipient = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='chat_notifications')
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE)
    is_seen = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_seen']),
            models.Index(fields=['created_at']),
        ]

    def mark_as_seen(self):
        self.is_seen = True
        self.seen_at = timezone.now()
        self.save()


class EmailProvider(models.Model):
    name = models.CharField(max_length=100)
    smtp_server = models.CharField(max_length=255)
    smtp_port = models.IntegerField()
    imap_server = models.CharField(max_length=255)
    imap_port = models.IntegerField()
    requires_auth = models.BooleanField(default=True)
    uses_tls = models.BooleanField(default=True)
    domain = models.CharField(max_length=100)  # e.g., "@gmail.com"

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

    @classmethod
    def get_provider_for_email(cls, email):
        """Get the provider based on email domain"""
        domain = f"@{email.split('@')[1]}" if '@' in email else None
        return cls.objects.filter(domain=domain).first()

# Default providers to be added via migrations
DEFAULT_EMAIL_PROVIDERS = [
    {
        'name': 'Gmail',
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'imap_server': 'imap.gmail.com',
        'imap_port': 993,
        'domain': '@gmail.com'
    },
    {
        'name': 'Outlook/Hotmail',
        'smtp_server': 'smtp.office365.com',
        'smtp_port': 587,
        'imap_server': 'outlook.office365.com',
        'imap_port': 993,
        'domain': '@outlook.com'
    },
    {
        'name': 'Yahoo',
        'smtp_server': 'smtp.mail.yahoo.com',
        'smtp_port': 587,
        'imap_server': 'imap.mail.yahoo.com',
        'imap_port': 993,
        'domain': '@yahoo.com'
    }
]


# Update EmailAccount model
class EmailAccount(models.Model):
    """Email account configuration for employees"""
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='email_account')
    email_address = models.EmailField(unique=True, validators=[EmailValidator()])
    provider = models.ForeignKey(EmailProvider, on_delete=models.SET_NULL, null=True, blank=True)
    smtp_server = models.CharField(max_length=255, blank=True)
    smtp_port = models.IntegerField(null=True, blank=True)
    imap_server = models.CharField(max_length=255, blank=True)
    imap_port = models.IntegerField(null=True, blank=True)
    requires_auth = models.BooleanField(default=True)
    uses_tls = models.BooleanField(default=True)
    username = models.CharField(max_length=255, blank=True)
    password = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Auto-populate provider details if a provider is selected
        if self.provider and not self.smtp_server:
            self.smtp_server = self.provider.smtp_server
            self.smtp_port = self.provider.smtp_port
            self.imap_server = self.provider.imap_server
            self.imap_port = self.provider.imap_port
            self.requires_auth = self.provider.requires_auth
            self.uses_tls = self.provider.uses_tls
            self.username = self.email_address

        super().save(*args, **kwargs)


class EmailTemplate(models.Model):
    """Reusable email templates"""

    name = models.CharField(max_length=100)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    created_by = models.ForeignKey(Employee, on_delete=models.CASCADE)
    is_shared = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class EmailMessage(models.Model):
    """Store all sent and received emails"""

    MESSAGE_TYPE_CHOICES = [
        ('incoming', 'Incoming'),
        ('outgoing', 'Outgoing'),
        ('draft', 'Draft')
    ]

    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled')
    ]

    message_id = models.UUIDField(default=uuid.uuid4, editable=False)
    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')

    from_email = models.EmailField()
    to_emails = models.JSONField()  # Store multiple recipients as JSON
    cc_emails = models.JSONField(blank=True, null=True)
    bcc_emails = models.JSONField(blank=True, null=True)

    subject = models.CharField(max_length=255)
    body_text = models.TextField()
    body_html = models.TextField(blank=True, null=True)

    # Relationships to CRM entities
    related_customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL)
    related_lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL)

    # Email threading
    thread_id = models.CharField(max_length=255, blank=True, null=True)
    in_reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    # Flags
    is_read = models.BooleanField(default=False)
    is_starred = models.BooleanField(default=False)
    is_spam = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['message_type', 'status']),
            models.Index(fields=['account', 'created_at']),
            models.Index(fields=['thread_id']),
        ]

    def __str__(self):
        return f"{self.subject} - {self.created_at}"

class EmailAttachment(models.Model):
    """Store email attachments"""

    email = models.ForeignKey(EmailMessage, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='email_attachments/%Y/%m/')
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.IntegerField()  # Size in bytes

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.filename

class EmailFolder(models.Model):
    """Custom email folders/labels"""

    SYSTEM_FOLDERS = [
        ('inbox', 'Inbox'),
        ('sent', 'Sent'),
        ('drafts', 'Drafts'),
        ('spam', 'Spam'),
        ('trash', 'Trash'),
        ('archived', 'Archived')
    ]

    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    is_system = models.BooleanField(default=False)
    system_type = models.CharField(max_length=20, choices=SYSTEM_FOLDERS, null=True, blank=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        unique_together = ['account', 'name', 'parent']

    def __str__(self):
        return self.name

class EmailFolderMessage(models.Model):
    """Many-to-many relationship between messages and folders"""

    folder = models.ForeignKey(EmailFolder, on_delete=models.CASCADE)
    message = models.ForeignKey(EmailMessage, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['folder', 'message']

class EmailTracker(models.Model):
    """Track email opens and link clicks"""

    email = models.ForeignKey(EmailMessage, on_delete=models.CASCADE)
    tracker_id = models.UUIDField(default=uuid.uuid4, editable=False)
    recipient_email = models.EmailField()

    opened_at = models.DateTimeField(null=True, blank=True)
    opened_count = models.IntegerField(default=0)

    first_opened_ip = models.GenericIPAddressField(null=True, blank=True)
    last_opened_ip = models.GenericIPAddressField(null=True, blank=True)

    user_agent = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Tracker for {self.email.subject} - {self.recipient_email}"


# Add this to your core/models.py file

class GeneralNotifier(models.Model):
    """
    Model for storing notifications for various CRM entities like meetings, tasks, etc.
    """
    NOTIFICATION_TYPES = [
        ('meeting', 'Meeting'),
        ('task', 'Task'),
        ('project', 'Project'),
        ('event', 'Event'),
        ('document', 'Document'),
        ('video_conference', 'Video Conference'),
        ('deadline', 'Deadline'),
        ('chat', 'Chat Message'),
        ('reminder', 'Reminder'),
        ('other', 'Other')
    ]

    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ]

    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS, default='medium')
    reference_id = models.IntegerField(null=True, blank=True, help_text="ID of the referenced object (meeting, task, event)")

    # Link to relevant objects via generic foreign key
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Target user(s)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    event_datetime = models.DateTimeField(help_text="When the event is happening or due")
    read_at = models.DateTimeField(null=True, blank=True)

    # Status flags
    is_read = models.BooleanField(default=False)
    is_dismissed = models.BooleanField(default=False)

    # Action URL - where to direct the user when they click the notification
    action_url = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-event_datetime', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['event_datetime']),
        ]

    def __str__(self):
        return f"{self.title} - {self.user.username}"

    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def dismiss(self):
        """Dismiss the notification"""
        self.is_dismissed = True
        self.save(update_fields=['is_dismissed'])

    @property
    def is_upcoming(self):
        """Check if this notification is for an upcoming event"""
        return self.event_datetime > timezone.now()

    @property
    def time_until_event(self):
        """Get time until the event in minutes"""
        if not self.is_upcoming:
            return 0

        delta = self.event_datetime - timezone.now()
        return int(delta.total_seconds() / 60)

    @property
    def urgency_level(self):
        """Calculate urgency level based on proximity to event time"""
        minutes_until = self.time_until_event

        if minutes_until <= 5:
            return 'immediate'  # Within 5 minutes
        elif minutes_until <= 30:
            return 'very_soon'  # Within 30 minutes
        elif minutes_until <= 60:
            return 'soon'       # Within an hour
        elif minutes_until <= 1440:
            return 'today'      # Within 24 hours
        elif minutes_until <= 10080:
            return 'week'       # Within a week
        else:
            return 'future'     # More than a week away
