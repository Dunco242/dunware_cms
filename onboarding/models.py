from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class OnboardingPlan(models.Model):
    """
    Defines different onboarding plans based on subscription tier or user type
    """
    TIER_CHOICES = [
        ('starter', 'Starter'),
        ('professional', 'Professional'),
        ('enterprise', 'Enterprise'),
    ]

    name = models.CharField(max_length=100)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    estimated_days = models.PositiveIntegerField(default=7,
                           help_text="Estimated days to complete onboarding")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_tier_display()})"

    class Meta:
        ordering = ['tier', 'name']


class OnboardingStep(models.Model):
    """
    Individual steps that make up an onboarding plan
    """
    STEP_TYPE_CHOICES = [
        ('welcome', 'Welcome'),
        ('account_setup', 'Account Setup'),
        ('data_import', 'Data Import'),
        ('feature_configuration', 'Feature Configuration'),
        ('team_setup', 'Team Setup'),
        ('integration', 'Integration Setup'),
        ('training', 'Training'),
        ('success_check', 'Success Check'),
    ]

    plan = models.ForeignKey(OnboardingPlan, on_delete=models.CASCADE, related_name='steps')
    name = models.CharField(max_length=100)
    step_type = models.CharField(max_length=30, choices=STEP_TYPE_CHOICES)
    description = models.TextField()
    order = models.PositiveIntegerField(help_text="Order in which step appears")
    is_required = models.BooleanField(default=True)
    estimated_minutes = models.PositiveIntegerField(default=10,
                               help_text="Estimated time to complete in minutes")
    url_name = models.CharField(max_length=100, blank=True,
                   help_text="URL name for this step's view")

    # Resources for this step
    video_url = models.URLField(blank=True, null=True)
    documentation_url = models.URLField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['plan', 'order']
        unique_together = ['plan', 'order']

    def __str__(self):
        return f"{self.plan.name} - {self.name} (Step {self.order})"

    def get_absolute_url(self):
        if self.url_name:
            from django.urls import reverse
            return reverse(f"onboarding:{self.url_name}")
        return None


class CustomerOnboarding(models.Model):
    """
    Tracks a customer's progress through their onboarding plan
    """
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('paused', 'Paused'),
        ('abandoned', 'Abandoned'),
    ]

    customer = models.OneToOneField('core.Customer', on_delete=models.CASCADE,
                                     related_name='onboarding')
    plan = models.ForeignKey(OnboardingPlan, on_delete=models.PROTECT,
                             related_name='customer_onboardings')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')

    # Progress tracking
    current_step = models.ForeignKey(OnboardingStep, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='current_customers')
    progress_percentage = models.PositiveIntegerField(default=0,
                                validators=[MinValueValidator(0), MaxValueValidator(100)])

    # Dates for tracking
    start_date = models.DateTimeField(null=True, blank=True)
    completed_date = models.DateTimeField(null=True, blank=True)
    last_activity_date = models.DateTimeField(null=True, blank=True)

    # Assigned representative
    assigned_to = models.ForeignKey('core.Employee', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='assigned_onboardings')

    # Notifications
    next_reminder_date = models.DateField(null=True, blank=True)
    send_reminders = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Onboarding for {self.customer.company_name} - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        # Set start date if transitioning to in_progress
        if self.status == 'in_progress' and not self.start_date:
            self.start_date = timezone.now()

        # Set completion date if status is completed
        if self.status == 'completed' and not self.completed_date:
            self.completed_date = timezone.now()
            self.progress_percentage = 100

        # Update last activity
        self.last_activity_date = timezone.now()

        super().save(*args, **kwargs)

    def calculate_progress(self):
        """Calculate progress based on completed steps"""
        completed_count = self.step_completions.filter(is_completed=True).count()
        total_required_count = self.plan.steps.filter(is_required=True).count()

        if total_required_count == 0:
            return 0

        percentage = int((completed_count / total_required_count) * 100)
        self.progress_percentage = min(percentage, 100)
        self.save(update_fields=['progress_percentage'])
        return self.progress_percentage

    def get_next_step(self):
        """Get the next incomplete step"""
        completed_steps = self.step_completions.filter(
            is_completed=True).values_list('step_id', flat=True)

        next_step = self.plan.steps.exclude(
            id__in=completed_steps).order_by('order').first()

        return next_step

    def update_current_step(self):
        """Update the current step based on progress"""
        next_step = self.get_next_step()
        if next_step:
            self.current_step = next_step
            self.save(update_fields=['current_step'])
        elif self.step_completions.filter(is_completed=True).count() == self.plan.steps.count():
            # All steps completed
            self.status = 'completed'
            self.completed_date = timezone.now()
            self.progress_percentage = 100
            self.save(update_fields=['status', 'completed_date', 'progress_percentage'])


class OnboardingStepCompletion(models.Model):
    """
    Tracks completion status of individual onboarding steps for a customer
    """
    customer_onboarding = models.ForeignKey(CustomerOnboarding, on_delete=models.CASCADE,
                                           related_name='step_completions')
    step = models.ForeignKey(OnboardingStep, on_delete=models.CASCADE,
                             related_name='completions')
    is_completed = models.BooleanField(default=False)
    completed_date = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='completed_onboarding_steps')
    notes = models.TextField(blank=True)

    # Optional satisfaction rating
    satisfaction_rating = models.PositiveIntegerField(null=True, blank=True,
                                   validators=[MinValueValidator(1), MaxValueValidator(5)],
                                   help_text="1-5 satisfaction rating")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['customer_onboarding', 'step']
        ordering = ['step__order']

    def __str__(self):
        status = "Completed" if self.is_completed else "Pending"
        return f"{self.step.name} - {status}"

    def mark_completed(self, user=None, rating=None, notes=None):
        """Mark a step as completed"""
        self.is_completed = True
        self.completed_date = timezone.now()

        if user:
            self.completed_by = user

        if rating is not None:
            self.satisfaction_rating = rating

        if notes:
            self.notes = notes

        self.save()

        # Update the overall onboarding progress
        self.customer_onboarding.calculate_progress()
        self.customer_onboarding.update_current_step()


class DataImportJob(models.Model):
    """
    Tracks data import jobs initiated during onboarding
    """
    IMPORT_TYPE_CHOICES = [
        ('customers', 'Customers'),
        ('leads', 'Leads'),
        ('contacts', 'Contacts'),
        ('products', 'Products/Services'),
        ('other', 'Other')
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled')
    ]

    customer_onboarding = models.ForeignKey(CustomerOnboarding, on_delete=models.CASCADE,
                                           related_name='import_jobs')
    import_type = models.CharField(max_length=20, choices=IMPORT_TYPE_CHOICES)
    source_name = models.CharField(max_length=100, help_text="Source system name")
    source_file = models.FileField(upload_to='onboarding/imports/%Y/%m/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Job details
    records_total = models.PositiveIntegerField(default=0)
    records_processed = models.PositiveIntegerField(default=0)
    records_succeeded = models.PositiveIntegerField(default=0)
    records_failed = models.PositiveIntegerField(default=0)

    notes = models.TextField(blank=True)
    error_details = models.TextField(blank=True)

    # Related onboarding step if applicable
    related_step = models.ForeignKey(OnboardingStep, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='import_jobs')

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                  null=True, related_name='created_import_jobs')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_import_type_display()} Import - {self.source_name} ({self.get_status_display()})"

    @property
    def progress_percentage(self):
        """Calculate progress percentage"""
        if self.records_total == 0:
            return 0
        return min(int((self.records_processed / self.records_total) * 100), 100)


class OnboardingChecklistItem(models.Model):
    """
    Checklist items for customers to complete during onboarding
    """
    step = models.ForeignKey(OnboardingStep, on_delete=models.CASCADE,
                            related_name='checklist_items')
    text = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['step', 'order']

    def __str__(self):
        return f"{self.text} ({self.step.name})"


class ChecklistItemCompletion(models.Model):
    """
    Tracks completion of individual checklist items
    """
    onboarding_step_completion = models.ForeignKey(OnboardingStepCompletion,
                                                 on_delete=models.CASCADE,
                                                 related_name='checklist_completions')
    checklist_item = models.ForeignKey(OnboardingChecklistItem, on_delete=models.CASCADE,
                                      related_name='completions')
    is_completed = models.BooleanField(default=False)
    completed_date = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['onboarding_step_completion', 'checklist_item']

    def __str__(self):
        status = "Completed" if self.is_completed else "Pending"
        return f"{self.checklist_item.text} - {status}"


class OnboardingFeedback(models.Model):
    """
    Collects feedback about the onboarding process
    """
    customer_onboarding = models.ForeignKey(CustomerOnboarding, on_delete=models.CASCADE,
                                           related_name='feedback')
    feedback_type = models.CharField(max_length=50, default='overall',
                                    help_text="Type of feedback (overall, step specific, etc.)")
    step = models.ForeignKey(OnboardingStep, on_delete=models.SET_NULL,
                            null=True, blank=True, related_name='feedback')

    # Rating fields
    overall_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1-5 rating"
    )
    ease_of_use_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1-5 rating"
    )
    support_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1-5 rating",
        null=True, blank=True
    )

    # Feedback fields
    what_worked_well = models.TextField(blank=True)
    what_could_improve = models.TextField(blank=True)
    additional_comments = models.TextField(blank=True)

    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        if self.step:
            return f"Feedback - {self.customer_onboarding.customer.company_name} - {self.step.name}"
        return f"Feedback - {self.customer_onboarding.customer.company_name} - Overall"


class OnboardingNotification(models.Model):
    """
    Notifications related to onboarding process
    """
    NOTIFICATION_TYPE_CHOICES = [
        ('reminder', 'Reminder'),
        ('completion', 'Step Completion'),
        ('milestone', 'Milestone'),
        ('task', 'Task Assignment'),
        ('welcome', 'Welcome'),
        ('plan_change', 'Plan Change'),
    ]

    customer_onboarding = models.ForeignKey(CustomerOnboarding, on_delete=models.CASCADE,
                                           related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    related_step = models.ForeignKey(OnboardingStep, on_delete=models.SET_NULL,
                                    null=True, blank=True)

    # For targeted notifications
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='onboarding_notifications')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    # For email notifications
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.notification_type} - {self.title}"

    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])

    def send_email(self):
        """Send email notification"""
        from django.core.mail import send_mail
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags

        subject = f'DunWare CRM: {self.title}'
        context = {
            'notification': self,
            'customer': self.customer_onboarding.customer,
        }

        # Render email templates
        html_message = render_to_string(
            'onboarding/emails/notification.html', context)
        plain_message = strip_tags(html_message)

        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.recipient.email],
                html_message=html_message,
                fail_silently=False,
            )

            self.email_sent = True
            self.email_sent_at = timezone.now()
            self.save(update_fields=['email_sent', 'email_sent_at'])
            return True
        except Exception as e:
            # Log the error but don't raise
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send onboarding notification email: {str(e)}")
            return False


class DataRequest(models.Model):
    """Stores requests for data access, deletion, etc. for privacy compliance"""
    REQUEST_TYPES = [
        ('access', 'Access My Data'),
        ('export', 'Export My Data'),
        ('correct', 'Correct My Data'),
        ('delete', 'Delete My Data'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('denied', 'Denied'),
    ]

    request_type = models.CharField(max_length=20, choices=REQUEST_TYPES)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    company_name = models.CharField(max_length=100)
    customer_id = models.CharField(max_length=50, blank=True, null=True, help_text="Customer ID if known")
    details = models.TextField(blank=True, help_text="Additional details to help identify the data")
    verification_code = models.CharField(max_length=10)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_request_type_display()} request by {self.name} ({self.email})"
