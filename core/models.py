# core/models.py

from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from zoom_integration.models import ZoomMeeting
from django.conf import settings
from zoomus import ZoomClient
from datetime import timedelta



class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    employee_id = models.CharField(max_length=10, unique=True)
    department = models.CharField(max_length=100, default="General")  # ✅ Default
    position = models.CharField(max_length=100, default="Unassigned")  # ✅ Default
    phone = models.CharField(max_length=15, default="000-000-0000")  # ✅ Default
    hire_date = models.DateField(null=True, blank=True)  # ✅ Allow NULL to prevent errors
    profile_picture = models.ImageField(upload_to='employee_photos/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.employee_id}"

    def get_absolute_url(self):
        return reverse('employee-detail', kwargs={'pk': self.pk})

class Customer(models.Model):
    CUSTOMER_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('pending', 'Pending')
    ]

    company_name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=10)
    website = models.URLField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=CUSTOMER_STATUS, default='active')
    assigned_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='customers')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.company_name

    def get_absolute_url(self):
        return reverse('customer-detail', kwargs={'pk': self.pk})

class Lead(models.Model):
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
        ('other', 'Other')
    ]

    company_name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    source = models.CharField(max_length=20, choices=LEAD_SOURCE)
    status = models.CharField(max_length=20, choices=LEAD_STATUS, default='new')
    notes = models.TextField(blank=True)
    assigned_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='leads')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.company_name} - {self.status}"

    def get_absolute_url(self):
        return reverse('lead-detail', kwargs={'pk': self.pk})

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

class Meeting(models.Model):
    MEETING_TYPES = [
        ('zoom', 'Zoom Meeting'),
        ('in_person', 'In Person'),
        ('phone', 'Phone Call')
    ]

    title = models.CharField(max_length=200)
    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPES)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    description = models.TextField()
    zoom_meeting_id = models.CharField(max_length=200, blank=True, null=True)
    zoom_meeting_password = models.CharField(max_length=20, blank=True, null=True)
    zoom_join_url = models.URLField(blank=True, null=True)
    organizer = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='organized_meetings')
    attendees = models.ManyToManyField('Employee', related_name='meetings')
    customers = models.ManyToManyField('Customer', blank=True, related_name='meetings')
    leads = models.ManyToManyField('Lead', blank=True, related_name='meetings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.start_time}"

    def get_absolute_url(self):
        return reverse('meeting-detail', kwargs={'pk': self.pk})

    def create_zoom_meeting(self):
        """Create a Zoom meeting if meeting type is 'zoom'"""
        if self.meeting_type != 'zoom':
            return

        client = ZoomClient(
        api_key=settings.ZOOM_API_KEY,
        api_secret=settings.ZOOM_API_SECRET,

    )

        meeting_data = {
            "topic": self.title,
            "type": 2,  # Scheduled meeting
            "start_time": self.start_time.isoformat(),
            "duration": (self.end_time - self.start_time).seconds // 60,
            "timezone": "UTC",
            "agenda": self.description,
            "settings": {
                "host_video": True,
                "participant_video": True,
                "mute_upon_entry": True,
            },
        }

        response = client.meeting.create(**meeting_data)

        if response:
            self.zoom_meeting_id = response.get('id')
            self.zoom_meeting_password = response.get('password')
            self.zoom_join_url = response.get('join_url')
            self.save()

    def update_zoom_meeting(self):
        """Update Zoom meeting details if meeting type is 'zoom'"""
        if self.meeting_type == 'zoom' and self.zoom_meeting_id:
            client = ZoomClient(settings.ZOOM_API_KEY, settings.ZOOM_API_SECRET)
            duration = int((self.end_time - self.start_time).total_seconds() / 60)

            try:
                client.meeting.update(
                    meeting_id=self.zoom_meeting_id,
                    topic=self.title,
                    start_time=self.start_time.isoformat(),
                    duration=duration
                )
                return True
            except Exception as e:
                print(f"Error updating Zoom meeting: {str(e)}")
                return False

    def delete_zoom_meeting(self):
        """Delete associated Zoom meeting if it exists"""
        if self.zoom_meeting_id:
            client = ZoomClient(settings.ZOOM_API_KEY, settings.ZOOM_API_SECRET)
            try:
                client.meeting.delete(meeting_id=self.zoom_meeting_id)
                return True
            except Exception as e:
                print(f"Error deleting Zoom meeting: {str(e)}")
                return False

    def save(self, *args, **kwargs):
        """Override save to handle Zoom meeting creation/updates"""
        is_new = self.pk is None
        old_instance = None if is_new else Meeting.objects.get(pk=self.pk)

        super().save(*args, **kwargs)

        if self.meeting_type == 'zoom':
            if is_new:
                self.create_zoom_meeting()
            else:
                # Check if relevant fields have changed
                fields_changed = (
                    old_instance.title != self.title or
                    old_instance.start_time != self.start_time or
                    old_instance.end_time != self.end_time
                )
                if fields_changed:
                    self.update_zoom_meeting()

    def delete(self, *args, **kwargs):
        """Override delete to handle Zoom meeting deletion"""
        if self.meeting_type == 'zoom':
            self.delete_zoom_meeting()
        super().delete(*args, **kwargs)

    def get_duration(self):
        """Get meeting duration in minutes"""
        duration = self.end_time - self.start_time
        return int(duration.total_seconds() / 60)

    def is_ongoing(self):
        """Check if meeting is currently ongoing"""
        now = timezone.now()
        return self.start_time <= now <= self.end_time

    def get_status(self):
        """Get current meeting status"""
        now = timezone.now()
        if self.start_time > now:
            return 'upcoming'
        elif self.end_time < now:
            return 'completed'
        else:
            return 'ongoing'

    def get_meeting_type_color(self):
        """Get color class for meeting type"""
        colors = {
            'zoom': 'primary',
            'in_person': 'success',
            'phone': 'info'
        }
        return colors.get(self.meeting_type, 'secondary')

    def get_all_participants_emails(self):
        """Get list of all participant emails"""
        emails = set()

        # Add employee emails
        emails.update(self.attendees.values_list('user__email', flat=True))

        # Add customer emails
        emails.update(self.customers.values_list('email', flat=True))

        # Add lead emails
        emails.update(self.leads.values_list('email', flat=True))

        return list(filter(None, emails))
