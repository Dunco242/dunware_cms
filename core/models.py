# core/models.py

from django.db import models, transaction
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from zoom_integration.models import ZoomMeeting
from django.conf import settings
from zoomus import ZoomClient
from datetime import timedelta
import uuid
from django.utils.crypto import get_random_string
from decimal import Decimal
from django.utils.timezone import make_aware
import pytz
import random
import logging

logger = logging.getLogger(__name__)

class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    employee_id = models.CharField(max_length=10, unique=True)
    department = models.CharField(max_length=100, default="General")  # ✅ Default
    position = models.CharField(max_length=100, default="Unassigned")  # ✅ Default
    phone = models.CharField(max_length=15, blank=True)
    carrier = models.CharField(
        max_length=20,
        choices=[
            ('att', 'AT&T'),
            ('tmobile', 'T-Mobile'),
            ('verizon', 'Verizon'),
            ('sprint', 'Sprint'),
            ('boost', 'Boost Mobile'),
            ('cricket', 'Cricket'),
            ('metro', 'Metro PCS'),
            ('virgin', 'Virgin Mobile'),
        ],
        blank=True
    )
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

# core/models.py (Invoice model updates)

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('canceled', 'Canceled')
    ]

    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='invoices')
    services = models.ManyToManyField('ServiceSubscription', blank=True, related_name='invoices')
    invoice_number = models.CharField(max_length=20, unique=True)
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    last_payment_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['invoice_number']),
            models.Index(fields=['due_date', 'status']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.customer.company_name}"

    def save(self, *args, **kwargs):
        """Enhanced save method with additional validations"""
        # Ensure due date is set if not provided
        if not self.due_date:
            self.due_date = self.issue_date + timedelta(days=30)

        # Set initial amount due if not set
        if not self.amount_due:
            self.amount_due = self.total_amount

        super().save(*args, **kwargs)

    @property
    def balance_due(self):
        """Calculate remaining balance dynamically"""
        total_paid = sum(payment.amount for payment in self.payments.filter(status='completed'))
        return max(self.total_amount - total_paid, Decimal('0.00'))

    def update_status(self):
        """Comprehensive invoice status management"""
        now = timezone.now().date()

        # Calculate total payments
        total_paid = sum(payment.amount for payment in self.payments.filter(status='completed'))

        # Update amount due
        self.amount_due = max(self.total_amount - total_paid, Decimal('0.00'))

        # Status transitions
        if total_paid >= self.total_amount:
            self.status = 'paid'
            self.last_payment_date = timezone.now()
        elif total_paid > Decimal('0.00') and total_paid < self.total_amount:
            self.status = 'partial'
        elif now > self.due_date and self.amount_due > Decimal('0.00'):
            self.status = 'overdue'
        else:
            self.status = 'pending'

        self.save()

    def can_generate_payment(self):
        """Check if payment can be generated"""
        return self.status in ['pending', 'partial', 'overdue']



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


class Event(models.Model):
    EVENT_TYPES = [
        ('meeting', 'Meeting'),
        ('task', 'Task'),
        ('call', 'Phone Call'),
        ('reminder', 'Reminder'),
        ('custom', 'Custom Event')
    ]

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled'),
    ]

    # Basic event information
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    # Event ownership and participants
    created_by = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='created_events')
    attendees = models.ManyToManyField('Employee', related_name='attending_events', blank=True)
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, null=True, blank=True, related_name="customer_events")

    # Event classification
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default='custom')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')

    # Recurring event support
    is_recurring = models.BooleanField(default=False)
    recurrence_rule = models.CharField(max_length=255, blank=True, null=True, help_text="RRULE format for recurring events")

    # UI customization
    color = models.CharField(max_length=7, default="#3788d8")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['start_time', 'end_time']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['created_by', 'status']),
        ]

    def save(self, *args, **kwargs):
        """Ensure end time is after start time."""
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        super().save(*args, **kwargs)

    def __str__(self):
        owner = self.customer.company_name if self.customer else self.created_by.user.get_full_name()
        return f"{self.title} ({self.get_event_type_display()}) - {owner} at {self.start_time.strftime('%Y-%m-%d %H:%M')}"

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
            'url': f'/event/{self.id}/',  # URL for event details
            'extendedProps': {
                'createdBy': self.created_by.user.get_full_name(),
                'customer': self.customer.company_name if self.customer else None,
                'attendees': [att.user.get_full_name() for att in self.attendees.all()],
                'isRecurring': self.is_recurring
            }
        }

    def can_edit(self, user):
        """Check if user can edit this event"""
        if not hasattr(user, 'employee'):
            return False
        return (user.employee == self.created_by or
                user.employee in self.attendees.all() or
                user.is_superuser)

    def is_upcoming(self):
        """Check if event is upcoming"""
        return self.start_time > timezone.now()

    def is_past(self):
        """Check if event is in the past"""
        return self.end_time < timezone.now()

    def is_ongoing(self):
        """Check if event is currently ongoing"""
        now = timezone.now()
        return self.start_time <= now <= self.end_time

    def get_duration_minutes(self):
        """Get event duration in minutes"""
        return int((self.end_time - self.start_time).total_seconds() / 60)

    def get_attendee_emails(self):
        """Get list of attendee email addresses"""
        return [attendee.user.email for attendee in self.attendees.all() if attendee.user.email]


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



class PrivacyPolicyAcceptance(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    policy_version = models.CharField(max_length=10)
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()

    class Meta:
        unique_together = ['user', 'policy_version']
        ordering = ['-accepted_at']
        indexes = [
            models.Index(fields=['user', 'policy_version']),
            models.Index(fields=['accepted_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - v{self.policy_version} - {self.accepted_at}"


class LegalDocument(models.Model):
    DOCUMENT_TYPES = (
        ('privacy_policy', 'Privacy Policy'),
        ('terms_of_service', 'Terms of Service'),
    )

    type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    version = models.CharField(max_length=10)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_current = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Ensure only one current version exists
        if self.is_current:
            LegalDocument.objects.filter(
                type=self.type,
                is_current=True
            ).update(is_current=False)

        super().save(*args, **kwargs)

    @classmethod
    def get_current_policy(cls):
        return cls.objects.filter(
            type='privacy_policy',
            is_current=True
        ).first()
