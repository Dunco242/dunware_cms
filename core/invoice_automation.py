# core/invoice_automation.py
import logging
import random
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from django.db.models import Q, F, Sum, Count, Max, Min
from django.db import transaction
from django.conf import settings
from django.core.mail import EmailMessage

from .models import (
    Customer, ServiceSubscription, Invoice, Payment,
    Service, Transaction, Employee
)
from .notification_service import SmartNotificationService

# Import needed models from your customer_projects app
# You'll need to update these imports according to your actual app structure
try:
    from customer_projects.models import (
        Project, ProjectPhase, ProjectTask, TimeEntry
    )
    CUSTOMER_PROJECTS_AVAILABLE = True
except ImportError:
    CUSTOMER_PROJECTS_AVAILABLE = False
    logging.warning("customer_projects app not available - some invoice features will be disabled")

logger = logging.getLogger(__name__)

class InvoiceGenerator:
    """
    Automated invoice generation system that integrates with service subscriptions
    and customer projects
    """

    def __init__(self):
        self.notification_service = SmartNotificationService()
        self.tax_rate = Decimal('0.13')  # 13% tax rate - configure as needed

    def generate_invoice_number(self):
        """Generate a unique invoice number with collision checking"""
        while True:
            year_month = timezone.now().strftime("%Y%m")
            random_suffix = str(random.randint(1000, 9999))
            invoice_number = f"INV-{year_month}-{random_suffix}"

            if not Invoice.objects.filter(invoice_number=invoice_number).exists():
                return invoice_number

    def generate_subscription_invoices(self, specific_date=None):
        """
        Generate invoices for active subscriptions that need billing

        Args:
            specific_date: Optional date to use instead of today
        """
        processing_date = specific_date or timezone.now().date()

        # Find subscriptions that need to be invoiced
        # For monthly subscriptions, bill at the beginning of each month
        # For quarterly, every 3 months
        # For yearly, once per year

        subscriptions_to_bill = []

        # Get all active subscriptions
        active_subscriptions = ServiceSubscription.objects.filter(
            is_active=True,
            status='active'
        )

        for subscription in active_subscriptions:
            should_bill = False

            # Skip if an invoice has already been generated in the current period
            # This logic depends on the billing cycle
            if subscription.billing_cycle == 'monthly':
                # Check if we already billed this month
                start_of_month = processing_date.replace(day=1)
                end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)

                existing_invoice = Invoice.objects.filter(
                    services=subscription,
                    issue_date__range=[start_of_month, end_of_month]
                ).exists()

                if not existing_invoice and processing_date.day <= 5:  # Bill in first 5 days of month
                    should_bill = True

            elif subscription.billing_cycle == 'quarterly':
                # Check if we're in a quarter boundary (Jan, Apr, Jul, Oct)
                quarter_months = [1, 4, 7, 10]

                if processing_date.month in quarter_months and processing_date.day <= 5:
                    # Check for existing invoice this quarter
                    quarter_start = processing_date.replace(day=1, month=processing_date.month)
                    quarter_end = (quarter_start + timedelta(days=92)).replace(day=1) - timedelta(days=1)

                    existing_invoice = Invoice.objects.filter(
                        services=subscription,
                        issue_date__range=[quarter_start, quarter_end]
                    ).exists()

                    if not existing_invoice:
                        should_bill = True

            elif subscription.billing_cycle == 'yearly':
                # Check if we're at the subscription anniversary
                if (subscription.start_date.month == processing_date.month and
                    subscription.start_date.day <= processing_date.day <= subscription.start_date.day + 5):

                    # Check for existing invoice this year
                    year_start = processing_date.replace(month=subscription.start_date.month,
                                                      day=subscription.start_date.day)
                    year_end = year_start + timedelta(days=10)  # Small window to avoid duplicates

                    existing_invoice = Invoice.objects.filter(
                        services=subscription,
                        issue_date__range=[year_start, year_end]
                    ).exists()

                    if not existing_invoice:
                        should_bill = True

            if should_bill:
                subscriptions_to_bill.append(subscription)

        # Process billing for identified subscriptions
        invoices_created = 0

        for subscription in subscriptions_to_bill:
            invoice = self._generate_subscription_invoice(subscription, processing_date)
            if invoice:
                invoices_created += 1

                # Mark subscription as invoiced
                subscription.invoice_generated = True
                subscription.save(update_fields=['invoice_generated'])

                # Send notification
                if subscription.customer.assigned_to:
                    self.notification_service.create_invoice_notification(invoice)

        logger.info(f"Generated {invoices_created} subscription invoices")
        return invoices_created

    def _generate_subscription_invoice(self, subscription, processing_date):
        """Generate invoice for a single subscription"""
        try:
            with transaction.atomic():
                # Calculate the total amount
                total_amount = subscription.calculate_total()

                # Create the invoice
                invoice = Invoice.objects.create(
                    customer=subscription.customer,
                    invoice_number=self.generate_invoice_number(),
                    issue_date=processing_date,
                    due_date=processing_date + timedelta(days=30),
                    total_amount=total_amount,
                    amount_due=total_amount,
                    status='pending'
                )

                # Associate the subscription with the invoice
                invoice.services.add(subscription)

                return invoice

        except Exception as e:
            logger.error(f"Error generating subscription invoice: {str(e)}")
            return None

    def generate_project_invoices(self, specific_date=None):
        """
        Generate invoices for billable project work

        Args:
            specific_date: Optional date to use instead of today
        """
        if not CUSTOMER_PROJECTS_AVAILABLE:
            logger.error("Cannot generate project invoices: customer_projects app not available")
            return 0

        processing_date = specific_date or timezone.now().date()

        # Find projects with billable hours that haven't been invoiced
        # This implementation assumes:
        # 1. TimeEntry model has fields: task, employee, date, hours, is_billable, is_invoiced
        # 2. ProjectTask belongs to a ProjectPhase which belongs to a Project
        # 3. Project has a customer field

        # Get all projects with uninvoiced time entries
        uninvoiced_entries = TimeEntry.objects.filter(
            is_billable=True,
            is_invoiced=False,
            date__lt=processing_date  # Only invoice entries up to yesterday
        )

        if not uninvoiced_entries.exists():
            logger.info("No uninvoiced time entries found")
            return 0

        # Group entries by project and customer
        projects_data = {}

        for entry in uninvoiced_entries:
            try:
                project = entry.task.phase.project
                customer = project.customer

                if customer.id not in projects_data:
                    projects_data[customer.id] = {
                        'customer': customer,
                        'projects': {}
                    }

                if project.id not in projects_data[customer.id]['projects']:
                    projects_data[customer.id]['projects'][project.id] = {
                        'project': project,
                        'entries': [],
                        'total_hours': Decimal('0.00')
                    }

                projects_data[customer.id]['projects'][project.id]['entries'].append(entry)
                projects_data[customer.id]['projects'][project.id]['total_hours'] += entry.hours

            except (AttributeError, Exception) as e:
                logger.error(f"Error processing time entry {entry.id}: {str(e)}")

        # Generate invoices for each customer
        invoices_created = 0

        for customer_id, customer_data in projects_data.items():
            invoice = self._generate_project_invoice(customer_data, processing_date)
            if invoice:
                invoices_created += 1

                # Send notification
                if customer_data['customer'].assigned_to:
                    self.notification_service.create_invoice_notification(invoice)

        logger.info(f"Generated {invoices_created} project invoices")
        return invoices_created

    def _generate_project_invoice(self, customer_data, processing_date):
        """Generate invoice for project work for a single customer"""
        try:
            with transaction.atomic():
                customer = customer_data['customer']

                # Calculate totals
                subtotal = Decimal('0.00')
                line_items = []

                for project_id, project_data in customer_data['projects'].items():
                    project = project_data['project']
                    total_hours = project_data['total_hours']
                    entries = project_data['entries']

                    # If project has a defined hourly rate, use it
                    # Otherwise use a default rate
                    hourly_rate = getattr(project, 'hourly_rate', Decimal('100.00'))

                    project_total = total_hours * hourly_rate
                    subtotal += project_total

                    # Create line item data
                    line_items.append({
                        'project': project.name,
                        'description': f"Professional services - {project.name}",
                        'hours': float(total_hours),
                        'rate': float(hourly_rate),
                        'amount': float(project_total)
                    })

                    # Mark time entries as invoiced
                    for entry in entries:
                        entry.is_invoiced = True
                        entry.save(update_fields=['is_invoiced'])

                # Calculate tax and total
                tax_amount = subtotal * self.tax_rate
                total_amount = subtotal + tax_amount

                # Create the invoice
                invoice = Invoice.objects.create(
                    customer=customer,
                    invoice_number=self.generate_invoice_number(),
                    issue_date=processing_date,
                    due_date=processing_date + timedelta(days=30),
                    total_amount=total_amount,
                    amount_due=total_amount,
                    status='pending'
                )

                # Store line items as JSON in a notes field if available
                # This is a simple approach - ideally, you'd have a dedicated InvoiceLineItem model
                if hasattr(invoice, 'notes'):
                    import json
                    invoice_details = {
                        'line_items': line_items,
                        'subtotal': float(subtotal),
                        'tax_rate': float(self.tax_rate),
                        'tax_amount': float(tax_amount),
                        'total': float(total_amount)
                    }
                    invoice.notes = json.dumps(invoice_details)
                    invoice.save()

                return invoice

        except Exception as e:
            logger.error(f"Error generating project invoice: {str(e)}")
            return None

    def process_overdue_invoices(self):
        """
        Process invoices that are overdue and need status updates
        """
        today = timezone.now().date()

        # Find invoices that are overdue but not marked as such
        overdue_invoices = Invoice.objects.filter(
            due_date__lt=today,
            status__in=['pending', 'partial']
        )

        count = 0
        for invoice in overdue_invoices:
            invoice.status = 'overdue'
            invoice.save(update_fields=['status'])
            count += 1

            # Notify account manager
            if invoice.customer.assigned_to:
                self.notification_service.create_notification(
                    user=invoice.customer.assigned_to.user,
                    title="Invoice Overdue",
                    message=f"Invoice #{invoice.invoice_number} for {invoice.customer.company_name} is overdue (${invoice.amount_due}).",
                    notification_type="deadline",
                    event_datetime=timezone.now(),
                    priority="high",
                    content_object=invoice,
                    action_url=f"/invoices/{invoice.id}/"
                )

        logger.info(f"Marked {count} invoices as overdue")
        return count

    def send_invoice_reminders(self):
        """
        Send reminders for upcoming and overdue invoices
        """
        today = timezone.now().date()

        # Upcoming invoices (due in next 3 days)
        upcoming_due = Invoice.objects.filter(
            due_date__range=[today, today + timedelta(days=3)],
            status__in=['pending', 'partial']
        )

        # Overdue invoices
        overdue = Invoice.objects.filter(
            due_date__lt=today,
            status='overdue'
        )

        reminder_count = 0

        # Process upcoming invoices
        for invoice in upcoming_due:
            days_until = (invoice.due_date - today).days

            if invoice.customer.assigned_to:
                # Notify account manager
                self.notification_service.create_invoice_due_notification(
                    invoice, days_before=days_until
                )
                reminder_count += 1

        # Process overdue invoices
        for invoice in overdue:
            days_overdue = (today - invoice.due_date).days

            # Send reminders at different intervals
            if days_overdue in [1, 3, 7, 14, 30]:
                if invoice.customer.assigned_to:
                    # Notify account manager
                    self.notification_service.create_notification(
                        user=invoice.customer.assigned_to.user,
                        title=f"Invoice #{invoice.invoice_number} - {days_overdue} Days Overdue",
                        message=f"Invoice for {invoice.customer.company_name} is {days_overdue} days overdue (${invoice.amount_due}).",
                        notification_type="deadline",
                        event_datetime=timezone.now(),
                        priority="high",
                        content_object=invoice,
                        action_url=f"/invoices/{invoice.id}/"
                    )
                    reminder_count += 1

        logger.info(f"Sent {reminder_count} invoice reminders")
        return reminder_count

    def run_regular_processes(self):
        """
        Run all regular invoice-related processes
        This can be called from a scheduler or management command
        """
        # Generate subscription invoices
        self.generate_subscription_invoices()

        # Generate project invoices if available
        if CUSTOMER_PROJECTS_AVAILABLE:
            self.generate_project_invoices()

        # Process overdue invoices
        self.process_overdue_invoices()

        # Send reminders
        self.send_invoice_reminders()
