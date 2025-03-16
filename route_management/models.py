from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.urls import reverse
from django.conf import settings

from core.models import Employee, Customer
import uuid


class ServiceArea(models.Model):
    """Geographic regions for service coverage"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    # Geographic boundaries - could be more complex with GeoDjango
    center_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Center latitude of service area"
    )
    center_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Center longitude of service area"
    )
    radius_miles = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Approximate service radius in miles"
    )

    # Who can service this area
    technicians = models.ManyToManyField(
        Employee,
        related_name='service_areas',
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class ServiceLocationType(models.Model):
    """Type of service location (residential, commercial, etc.)"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class ServiceLocation(models.Model):
    """Physical location where services are performed"""
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='service_locations'
    )
    name = models.CharField(max_length=100, help_text="Name or description of this location")
    location_type = models.ForeignKey(
        ServiceLocationType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Address fields
    address = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default="United States")

    # Geocoded coordinates
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Service area this location belongs to
    service_area = models.ForeignKey(
        ServiceArea,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locations'
    )

    # Access information
    access_instructions = models.TextField(
        blank=True,
        help_text="Instructions for accessing the location (gate codes, etc.)"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.customer.company_name}"

    def get_full_address(self):
        address = self.address
        if self.address_line2:
            address += f", {self.address_line2}"
        return f"{address}, {self.city}, {self.state} {self.zip_code}"

    def get_geocoding_address(self):
        """Return address formatted for geocoding API"""
        return f"{self.address}, {self.city}, {self.state} {self.zip_code}, {self.country}"

    def save(self, *args, **kwargs):
        # This would be a good place to trigger geocoding if coordinates are missing
        # But we'll implement that in a service to avoid API calls on every save
        super().save(*args, **kwargs)


class ServiceType(models.Model):
    """Types of service offered (cleaning, repair, inspection, etc.)"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    estimated_duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Typical time needed to complete this service"
    )
    color = models.CharField(
        max_length=7,
        default="#3498db",
        help_text="Color for calendar display (hex code)"
    )
    is_active = models.BooleanField(default=True)

    # Skill requirements
    requires_certification = models.BooleanField(default=False)
    certification_type = models.CharField(max_length=100, blank=True)

    # Rate information
    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Base price for this service type"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class ServiceRequest(models.Model):
    """Customer requests for service"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    # Basic information
    request_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text="Unique identifier for this service request"
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='service_requests'
    )
    service_location = models.ForeignKey(
        ServiceLocation,
        on_delete=models.CASCADE,
        related_name='service_requests'
    )
    service_type = models.ForeignKey(
        ServiceType,
        on_delete=models.CASCADE,
        related_name='service_requests'
    )

    # Request details
    description = models.TextField(help_text="Description of service needed")
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # Scheduling information
    preferred_date = models.DateField(null=True, blank=True)
    preferred_time_start = models.TimeField(null=True, blank=True)
    preferred_time_end = models.TimeField(null=True, blank=True)
    estimated_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Estimated duration for this specific request"
    )

    # Customer contact for this request
    contact_name = models.CharField(max_length=100, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)

    # Technician assignment
    assigned_technician = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_service_requests'
    )

    # Tracking fields
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_service_requests'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    scheduled_start_time = models.DateTimeField(null=True, blank=True)
    scheduled_end_time = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"SR-{self.request_number}: {self.service_type.name} for {self.customer.company_name}"

    def save(self, *args, **kwargs):
        # Generate unique request number if not set
        if not self.request_number:
            prefix = 'SR'
            year = timezone.now().strftime('%y')
            month = timezone.now().strftime('%m')

            # Get count of requests this month
            count = ServiceRequest.objects.filter(
                created_at__year=timezone.now().year,
                created_at__month=timezone.now().month
            ).count()

            # Format: SR-YY-MM-XXXX (e.g., SR-23-01-0001)
            self.request_number = f"{prefix}-{year}-{month}-{(count + 1):04d}"

        # Set estimated duration based on service type if not specified
        if not self.estimated_duration_minutes and self.service_type:
            self.estimated_duration_minutes = self.service_type.estimated_duration_minutes

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('route_management:service_request_detail', kwargs={'pk': self.pk})

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['service_location', 'status']),
            models.Index(fields=['created_at']),
        ]


class TechnicianSkill(models.Model):
    """Skills that technicians can have"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class TechnicianProfile(models.Model):
    """Extension of Employee model for technician-specific information"""
    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name='technician_profile'
    )
    skills = models.ManyToManyField(
        TechnicianSkill,
        related_name='technicians',
        blank=True
    )

    # Work and travel info
    vehicle_type = models.CharField(max_length=100, blank=True)
    license_plate = models.CharField(max_length=20, blank=True)
    max_travel_distance_miles = models.PositiveIntegerField(default=50)

    # Certifications
    certifications = models.TextField(blank=True)

    # Location tracking
    enable_location_tracking = models.BooleanField(default=False)
    last_known_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    last_known_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    last_location_update = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Technician: {self.employee.get_full_name()}"

    def update_location(self, latitude, longitude):
        """Update the technician's last known location"""
        self.last_known_latitude = latitude
        self.last_known_longitude = longitude
        self.last_location_update = timezone.now()
        self.save(update_fields=[
            'last_known_latitude',
            'last_known_longitude',
            'last_location_update'
        ])


class TechnicianAvailability(models.Model):
    """When technicians are available for work"""
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    technician = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='availability'
    )

    # Regular weekly availability
    day_of_week = models.IntegerField(
        choices=DAY_CHOICES,
        null=True,
        blank=True,
        help_text="Day of week for recurring availability"
    )
    start_time = models.TimeField()
    end_time = models.TimeField()

    # For specific date availability overrides
    specific_date = models.DateField(
        null=True,
        blank=True,
        help_text="Specific date for one-time availability"
    )

    is_available = models.BooleanField(
        default=True,
        help_text="Set to false to indicate unavailability during this time"
    )

    # For unavailability reasons (vacation, sick day, etc.)
    unavailability_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.specific_date:
            date_str = self.specific_date.strftime('%Y-%m-%d')
            return f"{self.technician.get_full_name()} - {date_str}: {self.start_time} to {self.end_time}"
        else:
            return f"{self.technician.get_full_name()} - {self.get_day_of_week_display()}: {self.start_time} to {self.end_time}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if not (self.day_of_week is not None or self.specific_date):
            raise ValidationError("Either day of week or specific date must be provided")
        if self.day_of_week is not None and self.specific_date:
            raise ValidationError("Cannot provide both day of week and specific date")
        if self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['day_of_week', 'specific_date', 'start_time']
        verbose_name_plural = 'Technician availabilities'
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(day_of_week__isnull=False, specific_date__isnull=True) |
                    models.Q(day_of_week__isnull=True, specific_date__isnull=False)
                ),
                name='either_day_of_week_or_specific_date'
            ),
            models.CheckConstraint(
                check=models.Q(start_time__lt=models.F('end_time')),
                name='end_time_after_start_time'
            )
        ]


class RouteSchedule(models.Model):
    """Daily/weekly schedule of routes"""
    name = models.CharField(max_length=100)
    date = models.DateField()
    description = models.TextField(blank=True)

    # Who created and owns this schedule
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_route_schedules'
    )

    # Status tracking
    is_published = models.BooleanField(
        default=False,
        help_text="Whether this schedule has been published to technicians"
    )
    published_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.date}"

    def publish(self):
        """Publish this schedule to technicians"""
        self.is_published = True
        self.published_at = timezone.now()
        self.save(update_fields=['is_published', 'published_at'])

    class Meta:
        ordering = ['-date']
        unique_together = ['name', 'date']


class Route(models.Model):
    """A specific path for a technician on a given day"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    route_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text="Unique identifier for this route"
    )

    name = models.CharField(max_length=100)
    schedule = models.ForeignKey(
        RouteSchedule,
        on_delete=models.CASCADE,
        related_name='routes'
    )
    technician = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='assigned_routes'
    )

    # Route details
    date = models.DateField()
    start_location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Starting point for the route (usually technician's home or office)"
    )
    start_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    start_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    end_location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Ending point for the route"
    )
    end_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    end_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Route metrics
    estimated_start_time = models.TimeField(null=True, blank=True)
    estimated_end_time = models.TimeField(null=True, blank=True)
    estimated_total_miles = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated total miles for this route"
    )
    estimated_drive_time_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Estimated driving time in minutes"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )

    # Optimization settings
    is_optimized = models.BooleanField(
        default=False,
        help_text="Whether this route has been optimized"
    )
    optimization_timestamp = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.route_id}: {self.name} - {self.date} ({self.technician.get_full_name()})"

    def save(self, *args, **kwargs):
        # Generate unique route ID if not set
        if not self.route_id:
            prefix = 'RT'
            year = timezone.now().strftime('%y')
            month = timezone.now().strftime('%m')

            # Get count of routes created this month
            count = Route.objects.filter(
                created_at__year=timezone.now().year,
                created_at__month=timezone.now().month
            ).count()

            # Format: RT-YY-MM-XXXX (e.g., RT-23-01-0001)
            self.route_id = f"{prefix}-{year}-{month}-{(count + 1):04d}"

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('route_management:route_detail', kwargs={'pk': self.pk})

    def optimize(self):
        """Optimize this route's stops for efficiency"""
        # This would call a service to perform the optimization
        # For now, we'll just mark it as optimized
        self.is_optimized = True
        self.optimization_timestamp = timezone.now()
        self.save(update_fields=['is_optimized', 'optimization_timestamp'])

    def calculate_metrics(self):
        """Calculate route metrics based on stops"""
        # This would calculate miles, drive time, etc. based on the stops
        # For now, just a placeholder
        from .services.optimization import RouteOptimizationService
        metrics = RouteOptimizationService.calculate_route_metrics(self)

        if metrics:
            self.estimated_total_miles = metrics.get('total_miles')
            self.estimated_drive_time_minutes = metrics.get('drive_time_minutes')
            self.save(update_fields=['estimated_total_miles', 'estimated_drive_time_minutes'])

        return metrics

    class Meta:
        ordering = ['date', 'estimated_start_time']
        indexes = [
            models.Index(fields=['date', 'technician']),
            models.Index(fields=['status']),
        ]


class RouteStop(models.Model):
    """Individual stops within a route"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('en_route', 'En Route'),
        ('arrived', 'Arrived'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
        ('cancelled', 'Cancelled'),
    ]

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name='stops'
    )
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='route_stops'
    )

    # Stop details
    stop_number = models.PositiveIntegerField(
        help_text="Order of this stop in the route"
    )

    # Time windows
    scheduled_arrival_time = models.TimeField(null=True, blank=True)
    scheduled_departure_time = models.TimeField(null=True, blank=True)
    estimated_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Estimated time at this stop in minutes"
    )

    # Navigation info
    distance_from_previous_miles = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Distance from previous stop in miles"
    )
    drive_time_from_previous_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Drive time from previous stop in minutes"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    actual_arrival_time = models.DateTimeField(null=True, blank=True)
    actual_departure_time = models.DateTimeField(null=True, blank=True)
    actual_duration_minutes = models.PositiveIntegerField(null=True, blank=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Stop #{self.stop_number} - {self.service_request.service_location.name}"

    def update_status(self, status, timestamp=None):
        """Update the status of this stop with timestamp"""
        if status not in dict(self.STATUS_CHOICES):
            raise ValueError(f"Invalid status: {status}")

        self.status = status
        if timestamp is None:
            timestamp = timezone.now()

        # Update timestamps based on status
        if status == 'arrived':
            self.actual_arrival_time = timestamp
        elif status == 'completed' or status == 'skipped':
            self.actual_departure_time = timestamp
            # Calculate actual duration if we have arrival time
            if self.actual_arrival_time:
                duration = timestamp - self.actual_arrival_time
                self.actual_duration_minutes = int(duration.total_seconds() / 60)

        # Update service request status as well
        sr_status_mapping = {
            'en_route': 'in_progress',
            'arrived': 'in_progress',
            'in_progress': 'in_progress',
            'completed': 'completed',
            'cancelled': 'cancelled',
        }

        if status in sr_status_mapping:
            self.service_request.status = sr_status_mapping[status]
            if status == 'completed':
                self.service_request.completed_at = timestamp
            elif status == 'cancelled':
                self.service_request.cancelled_at = timestamp
            self.service_request.save()

        self.save()

    class Meta:
        ordering = ['route', 'stop_number']
        unique_together = ['route', 'stop_number']
        indexes = [
            models.Index(fields=['route', 'stop_number']),
            models.Index(fields=['service_request', 'status']),
        ]


class RouteLog(models.Model):
    """Log entries for route events"""
    LOG_TYPE_CHOICES = [
        ('status_change', 'Status Change'),
        ('location_update', 'Location Update'),
        ('note', 'Note'),
        ('issue', 'Issue'),
        ('delay', 'Delay'),
        ('system', 'System Event'),
    ]

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    route_stop = models.ForeignKey(
        RouteStop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs'
    )

    timestamp = models.DateTimeField(default=timezone.now)
    log_type = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES)

    # Data fields
    message = models.TextField()
    old_value = models.CharField(max_length=100, blank=True)
    new_value = models.CharField(max_length=100, blank=True)

    # Location data (for location updates)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # User who created this log (if applicable)
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='route_logs'
    )

    def __str__(self):
        return f"{self.timestamp} - {self.log_type}: {self.message[:50]}"

    class Meta:
        ordering = ['-timestamp']


class ServiceCompletion(models.Model):
    """Record of completed service with details"""
    route_stop = models.OneToOneField(
        RouteStop,
        on_delete=models.CASCADE,
        related_name='service_completion'
    )
    service_request = models.OneToOneField(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='service_completion'
    )

    # Details of work performed
    work_performed = models.TextField(help_text="Description of work performed")
    materials_used = models.TextField(blank=True, help_text="Materials used during service")

    # Time tracking
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(
        help_text="Actual time spent performing the service"
    )

    # Billing info
    billable_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Billable hours for this service"
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Customer sign-off
    customer_name = models.CharField(max_length=100, blank=True)
    customer_signature = models.ImageField(
        upload_to='service_completions/signatures/%Y/%m/%d/',
        null=True,
        blank=True
    )
    customer_email = models.EmailField(blank=True)

    # Record keeping
    notes = models.TextField(blank=True)
    technician_comments = models.TextField(blank=True)
    follow_up_required = models.BooleanField(default=False)
    follow_up_notes = models.TextField(blank=True)

    # Media
    before_photos = models.ManyToManyField(
        'ServicePhoto',
        related_name='before_service_completions',
        blank=True
    )
    after_photos = models.ManyToManyField(
        'ServicePhoto',
        related_name='after_service_completions',
        blank=True
    )

    # Invoice info
    invoice_number = models.CharField(max_length=50, blank=True)
    invoice_date = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_service_completions'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Completion for {self.service_request}"

    def save(self, *args, **kwargs):
        # Calculate duration if not set
        if not self.duration_minutes and self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            self.duration_minutes = int(duration.total_seconds() / 60)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-end_time']


class ServicePhoto(models.Model):
    """Photos taken during service visits"""
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='photos'
    )

    image = models.ImageField(
        upload_to='service_photos/%Y/%m/%d/'
    )

    # Metadata
    photo_type = models.CharField(
        max_length=20,
        choices=[
            ('before', 'Before Service'),
            ('after', 'After Service'),
            ('issue', 'Issue Documentation'),
            ('other', 'Other')
        ],
        default='other'
    )
    caption = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    # Location data
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    taken_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_service_photos'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_photo_type_display()} - {self.service_request.request_number}"


class CustomerNotification(models.Model):
    """Notifications sent to customers about service"""
    NOTIFICATION_TYPE_CHOICES = [
        ('appointment_scheduled', 'Appointment Scheduled'),
        ('appointment_reminder', 'Appointment Reminder'),
        ('technician_en_route', 'Technician En Route'),
        ('technician_arrival', 'Technician Arrival'),
        ('service_complete', 'Service Complete'),
        ('follow_up', 'Follow Up'),
        ('feedback_request', 'Feedback Request'),
        ('status_update', 'Status Update'),
    ]

    DELIVERY_METHOD_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('push', 'Push Notification'),
        ('in_app', 'In-App'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    ]

    # Relationship fields
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    route_stop = models.ForeignKey(
        RouteStop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )

    # Notification details
    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPE_CHOICES
    )
    delivery_method = models.CharField(
        max_length=10,
        choices=DELIVERY_METHOD_CHOICES
    )
    recipient_name = models.CharField(max_length=100)
    recipient_contact = models.CharField(
        max_length=100,
        help_text="Email address, phone number, or device ID"
    )

    # Content
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField()

    # Status tracking
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )
    scheduled_time = models.DateTimeField(null=True, blank=True)
    sent_time = models.DateTimeField(null=True, blank=True)
    delivery_time = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_notification_type_display()} to {self.recipient_name}"

    def send(self):
        """Send the notification using the appropriate service"""
        from .services.notifications import NotificationService
        success, message = NotificationService.send_notification(self)

        if success:
            self.status = 'sent'
            self.sent_time = timezone.now()
        else:
            self.status = 'failed'
            self.error_message = message

        self.save(update_fields=['status', 'sent_time', 'error_message'])
        return success

    class Meta:
        ordering = ['-created_at']


class CustomerFeedback(models.Model):
    """Customer feedback for completed service"""
    service_request = models.OneToOneField(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='feedback'
    )

    # Rating fields
    overall_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Overall rating from 1-5"
    )
    technician_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="Technician rating from 1-5"
    )
    punctuality_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="Punctuality rating from 1-5"
    )
    quality_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="Quality of work rating from 1-5"
    )

    # Feedback text
    comments = models.TextField(blank=True)

    # Would recommend
    would_recommend = models.BooleanField(null=True, blank=True)

    # Follow-up
    wants_follow_up = models.BooleanField(default=False)
    follow_up_contact_method = models.CharField(
        max_length=10,
        choices=[
            ('phone', 'Phone'),
            ('email', 'Email'),
            ('any', 'Any')
        ],
        blank=True
    )

    # Metadata
    submitted_by = models.CharField(max_length=100, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)

    # Internal tracking
    is_public = models.BooleanField(
        default=False,
        help_text="Whether this feedback can be shown publicly"
    )
    internal_notes = models.TextField(blank=True)

    def __str__(self):
        return f"Feedback for {self.service_request.request_number} ({self.overall_rating}/5)"

    class Meta:
        ordering = ['-submitted_at']


class OptimizationSettings(models.Model):
    """Settings for route optimization algorithms"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # Optimization parameters
    prioritize_choices = [
        ('distance', 'Minimize Distance'),
        ('time', 'Minimize Time'),
        ('stops', 'Maximize Stops'),
        ('revenue', 'Maximize Revenue'),
        ('balanced', 'Balanced Approach'),
    ]
    prioritize = models.CharField(
        max_length=20,
        choices=prioritize_choices,
        default='balanced'
    )

    # Constraints
    max_stops_per_route = models.PositiveIntegerField(
        default=12,
        help_text="Maximum number of stops per route"
    )
    max_drive_time_minutes = models.PositiveIntegerField(
        default=480,  # 8 hours
        help_text="Maximum total drive time in minutes"
    )
    max_route_duration_minutes = models.PositiveIntegerField(
        default=600,  # 10 hours
        help_text="Maximum total route duration (drive + service time) in minutes"
    )

    # Time windows
    service_time_buffer_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Buffer time between estimated and actual service time"
    )
    travel_time_buffer_percent = models.PositiveIntegerField(
        default=20,
        help_text="Buffer percentage added to estimated travel times"
    )

    # Algorithm settings
    use_historical_traffic = models.BooleanField(default=True)
    consider_technician_skills = models.BooleanField(default=True)
    consider_customer_priority = models.BooleanField(default=True)

    # Is default
    is_default = models.BooleanField(default=False)

    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_optimization_settings'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Ensure only one default setting
        if self.is_default:
            OptimizationSettings.objects.filter(
                is_default=True
            ).update(is_default=False)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Optimization settings"


class GeocodeCache(models.Model):
    """Cache for geocoded addresses to minimize API calls"""
    address = models.CharField(max_length=255, unique=True)
    formatted_address = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    # Metadata for geocoding result
    country = models.CharField(max_length=100, blank=True)
    administrative_area_1 = models.CharField(max_length=100, blank=True, help_text="State/Province")
    administrative_area_2 = models.CharField(max_length=100, blank=True, help_text="County")
    locality = models.CharField(max_length=100, blank=True, help_text="City")
    postal_code = models.CharField(max_length=20, blank=True)

    # Result quality
    geocode_quality = models.CharField(
        max_length=20,
        blank=True,
        help_text="Quality indicator from geocoding service"
    )

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.address} ({self.latitude}, {self.longitude})"

    class Meta:
        verbose_name_plural = "Geocode cache entries"


class DistanceMatrixCache(models.Model):
    """Cache for distance and time estimates between locations"""
    origin_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    origin_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    destination_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    destination_longitude = models.DecimalField(max_digits=9, decimal_places=6)

    # Mode of travel
    travel_mode = models.CharField(
        max_length=20,
        default='driving',
        choices=[
            ('driving', 'Driving'),
            ('walking', 'Walking'),
            ('bicycling', 'Bicycling'),
            ('transit', 'Transit')
        ]
    )

    # Distance and time
    distance_meters = models.PositiveIntegerField()
    duration_seconds = models.PositiveIntegerField()

    # With traffic (if available)
    duration_in_traffic_seconds = models.PositiveIntegerField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Distance from ({self.origin_latitude}, {self.origin_longitude}) to ({self.destination_latitude}, {self.destination_longitude})"

    class Meta:
        unique_together = [
            'origin_latitude', 'origin_longitude',
            'destination_latitude', 'destination_longitude',
            'travel_mode'
        ]
        verbose_name_plural = "Distance matrix cache entries"


class AnalyticsSnapshot(models.Model):
    """Daily snapshot of key metrics for reporting"""
    date = models.DateField(unique=True)

    # Route metrics
    total_routes = models.PositiveIntegerField(default=0)
    completed_routes = models.PositiveIntegerField(default=0)
    cancelled_routes = models.PositiveIntegerField(default=0)

    # Service request metrics
    total_service_requests = models.PositiveIntegerField(default=0)
    completed_service_requests = models.PositiveIntegerField(default=0)
    cancelled_service_requests = models.PositiveIntegerField(default=0)

    # Efficiency metrics
    avg_stops_per_route = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    avg_service_duration_minutes = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    avg_travel_time_minutes = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    avg_miles_per_route = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Customer metrics
    avg_customer_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Analytics Snapshot for {self.date}"

    @classmethod
    def generate_for_date(cls, date=None):
        """Generate analytics snapshot for a specific date"""
        if date is None:
            date = timezone.now().date() - timezone.timedelta(days=1)

        from .services.analytics import AnalyticsService
        metrics = AnalyticsService.calculate_daily_metrics(date)

        snapshot, created = cls.objects.update_or_create(
            date=date,
            defaults=metrics
        )
        return snapshot

    class Meta:
        ordering = ['-date']


class ServicePhotoUpload(models.Model):
    """Model to track photo upload sessions"""
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='photo_uploads'
    )

    # User who uploaded the photos
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='service_photo_uploads'
    )

    # Photo type
    photo_type = models.CharField(
        max_length=20,
        choices=[
            ('before', 'Before Service'),
            ('after', 'After Service'),
            ('issue', 'Issue Documentation'),
            ('other', 'Other')
        ],
        default='other'
    )

    # Optional caption or notes
    caption = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Number of photos uploaded in this session
    photo_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.photo_type} Photo Upload for {self.service_request.request_number}"

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Service Photo Uploads'
