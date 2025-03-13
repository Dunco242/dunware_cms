# core/signals.py
import logging
from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.apps import apps
from django.utils import timezone
from django.utils.timezone import now
from django.contrib.auth.models import User

from .models import (
    Customer, Lead, Meeting, Task, Event, Employee,
    ServiceSubscription, Invoice, ChatMessage, GeneralNotifier
)
from .notification_service import SmartNotificationService
from .customer_lifecycle import CustomerLifecycleManager
from .invoice_automation import InvoiceGenerator

logger = logging.getLogger(__name__)

# Initialize services
notification_service = SmartNotificationService()
customer_lifecycle = CustomerLifecycleManager()
invoice_generator = InvoiceGenerator()

# ===== User and Employee Signals =====

@receiver(post_save, sender=User)
def create_employee_profile(sender, instance, created, **kwargs):
    """Create Employee profile when a new user is created"""
    from .models import Employee  # Import here to avoid circular import

    if created:
        try:
            # Check if employee profile already exists
            if not hasattr(instance, 'employee_profile'):
                Employee.objects.create(
                    user=instance,
                    hire_date=now().date(),
                    employee_id=f"EMP{instance.id:04d}",
                    department="General",
                    position="Unassigned",
                    phone="000-000-0000",
                    is_active=True
                )
                logger.info(f"Created employee profile for user {instance.username}")
        except Exception as e:
            logger.error(f"Error creating employee profile for user {instance.username}: {str(e)}")

@receiver(post_save, sender=User)
def save_employee_profile(sender, instance, **kwargs):
    """Save Employee profile when user is updated"""
    try:
        if hasattr(instance, 'employee_profile'):
            instance.employee_profile.save()
    except Exception as e:
        logger.error(f"Error saving employee profile for user {instance.username}: {str(e)}")

# ===== Customer Lifecycle Signals =====

@receiver(post_save, sender=Customer)
def handle_new_customer(sender, instance, created, **kwargs):
    """Handle new customer creation"""
    if created:
        logger.info(f"New customer created: {instance.company_name}")
        customer_lifecycle.process_new_customer(instance)

@receiver(post_save, sender=Lead)
def handle_lead_update(sender, instance, created, **kwargs):
    """Handle lead conversion"""
    if not created and instance.status == 'converted' and instance.converted_to_customer:
        try:
            customer = instance.converted_to_customer
            logger.info(f"Lead converted to customer: {instance.company_name} -> {customer.company_name}")
            customer_lifecycle.convert_lead_to_customer(instance, customer)
        except Exception as e:
            logger.error(f"Error in lead conversion handler: {str(e)}")

@receiver(post_save, sender=ServiceSubscription)
def handle_service_subscription(sender, instance, created, **kwargs):
    """Handle new service subscription"""
    if created:
        logger.info(f"New service subscription: {instance.service.name} for {instance.customer.company_name}")
        customer_lifecycle.process_service_subscription(instance)

        # Generate invoice
        try:
            invoice = instance.generate_invoice()
            if invoice:
                logger.info(f"Generated invoice for new subscription: {invoice.invoice_number}")
        except Exception as e:
            logger.error(f"Error generating invoice for subscription: {str(e)}")

# ===== Notification Signals =====

@receiver(post_save, sender=Meeting)
def create_meeting_notification(sender, instance, created, **kwargs):
    """Create notifications for meetings"""
    if instance.is_past:
        return  # Don't create notifications for past meetings

    # Check if start time is in the future
    now = timezone.now()
    if instance.start_time <= now:
        return  # Don't create notifications for meetings that have already started

    # Process using the smart notification service
    try:
        logger.info(f"Creating notification for meeting: {instance.title}")
        notification_service.create_meeting_notification(instance)
    except Exception as e:
        logger.error(f"Error creating meeting notification: {str(e)}")

        # Fall back to legacy notification creation method
        participants = [instance.organizer]
        participants.extend(list(instance.attendees.all()))

        for participant in participants:
            user = participant.user

            # Look for an existing notification for this meeting and user
            existing_notification = GeneralNotifier.objects.filter(
                user=user,
                notification_type='meeting',
                title__contains=instance.title,
                reference_id=instance.id,
                is_dismissed=False
            ).first()

            if existing_notification:
                # Update existing notification
                existing_notification.message = f"Meeting: {instance.title} on {instance.start_time.strftime('%Y-%m-%d at %H:%M')}"
                existing_notification.event_datetime = instance.start_time
                existing_notification.action_url = f"/meetings/{instance.id}/"
                existing_notification.save()
            else:
                # Create new notification
                GeneralNotifier.objects.create(
                    user=user,
                    notification_type='meeting',
                    title=f"Upcoming Meeting: {instance.title}",
                    message=f"Meeting scheduled for {instance.start_time.strftime('%Y-%m-%d at %H:%M')}",
                    priority='normal',
                    event_datetime=instance.start_time,
                    action_url=f"/meetings/{instance.id}/",
                    reference_id=instance.id
                )

@receiver(post_save, sender=Task)
def handle_task_notification(sender, instance, created, **kwargs):
    """Create notifications for tasks"""
    if created or kwargs.get('update_fields') and 'due_date' in kwargs['update_fields']:
        try:
            logger.info(f"Creating notification for task: {instance.title}")
            notification_service.create_task_notification(instance)
        except Exception as e:
            logger.error(f"Error creating task notification: {str(e)}")

@receiver(post_save, sender=Event)
def handle_event_notification(sender, instance, created, **kwargs):
    """Create notifications for events"""
    if created or kwargs.get('update_fields') and 'start_time' in kwargs['update_fields']:
        try:
            logger.info(f"Creating notification for event: {instance.title}")
            notification_service.create_event_notification(instance)
        except Exception as e:
            logger.error(f"Error creating event notification: {str(e)}")

@receiver(post_save, sender=ChatMessage)
def handle_chat_notification(sender, instance, created, **kwargs):
    """Create notifications for chat messages"""
    if created and instance.receiver != instance.sender:
        try:
            logger.info(f"Creating notification for chat message")
            notification_service.create_chat_notification(instance)
        except Exception as e:
            logger.error(f"Error creating chat notification: {str(e)}")

            # Fall back to legacy notification creation method
            GeneralNotifier.objects.create(
                user=instance.receiver.user,
                notification_type='chat',
                title=f'New message from {instance.sender.get_full_name()}',
                message=instance.content[:50] + ('...' if len(instance.content) > 50 else ''),
                priority='normal',
                action_url=f'/chat/session/{instance.session.id}/',
                reference_id=instance.id,
                event_datetime=timezone.now()
            )

@receiver(post_save, sender=Invoice)
def handle_invoice_notification(sender, instance, created, **kwargs):
    """Create notifications for invoices"""
    if created:
        try:
            logger.info(f"Creating notification for invoice: {instance.invoice_number}")
            notification_service.create_invoice_notification(instance)
        except Exception as e:
            logger.error(f"Error creating invoice notification: {str(e)}")

# ===== Integration with customer_projects app if available =====

# Check if customer_projects app is installed
try:
    ProjectTask = apps.get_model('customer_projects', 'ProjectTask')
    TimeEntry = apps.get_model('customer_projects', 'TimeEntry')

    # Add signals for project-related notifications
    @receiver(post_save, sender=ProjectTask)
    def handle_project_task_notification(sender, instance, created, **kwargs):
        """Create notifications for project tasks"""
        if created or kwargs.get('update_fields') and 'due_date' in kwargs['update_fields']:
            logger.info(f"Creating notification for project task: {instance.title}")

            if instance.assigned_to and instance.assigned_to.user:
                notification_service.create_notification(
                    user=instance.assigned_to.user,
                    title=f"Project Task: {instance.title}",
                    message=f"You have been assigned a task for project {instance.phase.project.name}.",
                    notification_type="task",
                    event_datetime=instance.due_date,
                    priority="medium",
                    content_object=instance,
                    action_url=f"/projects/tasks/{instance.id}/"
                )

    @receiver(post_save, sender=TimeEntry)
    def handle_time_entry(sender, instance, created, **kwargs):
        """Handle billable time entries for invoice generation"""
        if created and instance.is_billable and not instance.is_invoiced:
            # We don't immediately generate invoices for each time entry
            # Just log for tracking
            logger.info(f"New billable time entry: {instance.hours} hours for {instance.task}")

except (LookupError, ImportError):
    logger.info("customer_projects app not available - skipping project signals")
