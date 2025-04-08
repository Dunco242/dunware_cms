import logging
import random
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from django.db.models import Q, F, Sum, Count, Max, Min
from django.db import transaction
from django.conf import settings
from django.core.mail import EmailMessage
from .models import InvoiceLineItem

from .models import (
    Customer, ServiceSubscription, Invoice, Payment,
    Service, Transaction, Employee
)
from .notification_service import SmartNotificationService

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
    def __init__(self):
        self.notification_service = SmartNotificationService()
        self.tax_rate = Decimal('0.13')  # 13% tax rate - configure as needed

    def generate_invoice_number(self):
        while True:
            year_month = timezone.now().strftime("%Y%m")
            random_suffix = str(random.randint(1000, 9999))
            invoice_number = f"INV-{year_month}-{random_suffix}"

            if not Invoice.objects.filter(invoice_number=invoice_number).exists():
                return invoice_number

    def generate_subscription_invoices(self, specific_date=None):
        processing_date = specific_date or timezone.now().date()
        subscriptions_to_bill = []
        active_subscriptions = ServiceSubscription.objects.filter(
            is_active=True,
            status='active'
        )

        for subscription in active_subscriptions:
            should_bill = False

            if subscription.billing_cycle == 'monthly':
                start_of_month = processing_date.replace(day=1)
                end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)

                existing_invoice = Invoice.objects.filter(
                    services=subscription,
                    issue_date__range=[start_of_month, end_of_month]
                ).exists()

                if not existing_invoice and processing_date.day <= 5:
                    should_bill = True

            elif subscription.billing_cycle == 'quarterly':
                quarter_months = [1, 4, 7, 10]

                if processing_date.month in quarter_months and processing_date.day <= 5:
                    quarter_start = processing_date.replace(day=1, month=processing_date.month)
                    quarter_end = (quarter_start + timedelta(days=92)).replace(day=1) - timedelta(days=1)

                    existing_invoice = Invoice.objects.filter(
                        services=subscription,
                        issue_date__range=[quarter_start, quarter_end]
                    ).exists()

                    if not existing_invoice:
                        should_bill = True

            elif subscription.billing_cycle == 'yearly':
                if (subscription.start_date.month == processing_date.month and
                    subscription.start_date.day <= processing_date.day <= subscription.start_date.day + 5):

                    year_start = processing_date.replace(month=subscription.start_date.month,
                                                      day=subscription.start_date.day)
                    year_end = year_start + timedelta(days=10)

                    existing_invoice = Invoice.objects.filter(
                        services=subscription,
                        issue_date__range=[year_start, year_end]
                    ).exists()

                    if not existing_invoice:
                        should_bill = True

            if should_bill:
                subscriptions_to_bill.append(subscription)

        invoices_created = 0

        for subscription in subscriptions_to_bill:
            invoice = self._generate_subscription_invoice(subscription, processing_date)
            if invoice:
                invoices_created += 1
                subscription.invoice_generated = True
                subscription.save(update_fields=['invoice_generated'])

                if subscription.customer.assigned_to:
                    self.notification_service.create_invoice_notification(invoice)

        logger.info(f"Generated {invoices_created} subscription invoices")
        return invoices_created

    def _generate_subscription_invoice(self, subscription, processing_date):
        try:
            with transaction.atomic():
                total_amount = subscription.calculate_total()

                invoice = Invoice.objects.create(
                    customer=subscription.customer,
                    invoice_number=self.generate_invoice_number(),
                    issue_date=processing_date,
                    due_date=processing_date + timedelta(days=30),
                    total_amount=total_amount,
                    amount_due=total_amount,
                    status='pending'
                )

                invoice.services.add(subscription)
                return invoice

        except Exception as e:
            logger.error(f"Error generating subscription invoice: {str(e)}")
            return None

    def generate_project_invoices(self, specific_date=None):
        if not CUSTOMER_PROJECTS_AVAILABLE:
            logger.error("Cannot generate project invoices: customer_projects app not available")
            return 0

        processing_date = specific_date or timezone.now().date()

        customers_with_entries = Customer.objects.filter(
            projects__phases__tasks__time_entries__is_billable=True,
            projects__phases__tasks__time_entries__is_invoiced=False
        ).distinct()

        logger.info(f"Found {customers_with_entries.count()} customers with uninvoiced entries")

        invoices_created = 0

        for customer in customers_with_entries:
            try:
                uninvoiced_entries = TimeEntry.objects.filter(
                    is_billable=True,
                    is_invoiced=False,
                    task__phase__project__customer=customer
                ).select_related(
                    'task',
                    'task__phase',
                    'task__phase__project'
                )

                total_hours = uninvoiced_entries.aggregate(total=Sum('hours'))['total'] or 0
                logger.info(f"Customer {customer.id}: Found {uninvoiced_entries.count()} entries, {total_hours} hours")

                if uninvoiced_entries.exists():
                    projects_data = {}
                    for entry in uninvoiced_entries:
                        project = entry.task.phase.project
                        if project.id not in projects_data:
                            projects_data[project.id] = {
                                'project': project,
                                'entries': [],
                                'total_hours': Decimal('0.00')
                            }
                        projects_data[project.id]['entries'].append(entry)
                        projects_data[project.id]['total_hours'] += entry.hours

                    invoice = self._generate_project_invoice(customer, projects_data, processing_date)
                    if invoice:
                        invoices_created += 1
                        uninvoiced_entries.update(is_invoiced=True)

                        if customer.assigned_to:
                            self.notification_service.create_invoice_notification(invoice)

            except Exception as e:
                logger.error(f"Error generating invoice for customer {customer.id}: {str(e)}")

        logger.info(f"Generated {invoices_created} project invoices")
        return invoices_created

    def generate_project_invoices(self, specific_date=None):
        if not CUSTOMER_PROJECTS_AVAILABLE:
            logger.error("Cannot generate project invoices: customer_projects app not available")
            return 0

        processing_date = specific_date or timezone.now().date()

        # Find customers with uninvoiced billable time entries
        customers_with_entries = Customer.objects.filter(
            projects__phases__tasks__time_entries__is_billable=True,
            projects__phases__tasks__time_entries__is_invoiced=False
        ).distinct()

        logger.info(f"Found {customers_with_entries.count()} customers with uninvoiced entries")

        invoices_created = 0

        for customer in customers_with_entries:
            try:
                # Get all projects with uninvoiced entries for this customer
                projects_with_entries = Project.objects.filter(
                    customer=customer,
                    phases__tasks__time_entries__is_billable=True,
                    phases__tasks__time_entries__is_invoiced=False
                ).distinct()

                logger.info(f"Customer {customer.id}: Found {projects_with_entries.count()} projects with uninvoiced entries")

                # Create a separate invoice for EACH project
                for project in projects_with_entries:
                    # Get uninvoiced entries for this specific project
                    uninvoiced_entries = TimeEntry.objects.filter(
                        is_billable=True,
                        is_invoiced=False,
                        task__phase__project=project
                    ).select_related(
                        'task',
                        'task__phase',
                        'task__phase__project'
                    )

                    total_hours = uninvoiced_entries.aggregate(total=Sum('hours'))['total'] or 0
                    logger.info(f"Project {project.id}: Found {uninvoiced_entries.count()} entries, {total_hours} hours")

                    if uninvoiced_entries.exists():
                        # Create a project-specific data structure
                        project_data = {
                            project.id: {
                                'project': project,
                                'entries': list(uninvoiced_entries),
                                'total_hours': total_hours
                            }
                        }

                        # Generate invoice for this specific project
                        invoice = self._generate_project_invoice(customer, project_data, processing_date, project)
                        if invoice:
                            invoices_created += 1
                            uninvoiced_entries.update(is_invoiced=True)

                            if customer.assigned_to:
                                try:
                                    self.notification_service.create_invoice_notification(invoice)
                                except Exception as e:
                                    logger.error(f"Error creating invoice notification: {str(e)}")

            except Exception as e:
                logger.error(f"Error generating invoice for customer {customer.id}: {str(e)}")

        logger.info(f"Generated {invoices_created} project invoices")
        return invoices_created

    def _generate_project_invoice(self, customer, projects_data, processing_date, project=None):
        """
        Generate invoice for a specific project
        """
        try:
            with transaction.atomic():
                # Create the invoice with fields that exist in our model
                invoice = Invoice.objects.create(
                    customer=customer,
                    project=project,  # Associate the invoice directly with the project
                    invoice_number=self.generate_invoice_number(),
                    issue_date=processing_date,
                    due_date=processing_date + timedelta(days=30),
                    status='draft'
                )

                subtotal = Decimal('0.00')

                # Process this project's entries
                for project_id, data in projects_data.items():
                    project = data['project']
                    entries = data['entries']

                    # Group entries by task for cleaner invoice
                    tasks_data = {}
                    for entry in entries:
                        task = entry.task
                        task_key = task.id

                        if task_key not in tasks_data:
                            tasks_data[task_key] = {
                                'task': task,
                                'total_hours': Decimal('0.00'),
                                'entries': []
                            }

                        tasks_data[task_key]['total_hours'] += entry.hours
                        tasks_data[task_key]['entries'].append(entry)

                    # Create line items for each task with proper descriptions
                    for task_key, task_data in tasks_data.items():
                        task = task_data['task']
                        total_hours = task_data['total_hours']

                        # Use project's hourly rate or default to 100
                        hourly_rate = project.hourly_rate if project.hourly_rate else Decimal('100.00')
                        line_amount = total_hours * hourly_rate

                        # Create a descriptive line item
                        InvoiceLineItem.objects.create(
                            invoice=invoice,
                            project_name=project.name,
                            project_code=project.project_code,
                            task_description=task.title,
                            product_or_service=f"Project: {project.name} ({project.project_code})",
                            description=f"Task: {task.title}\n{total_hours} hours @ ${hourly_rate}/hour",
                            quantity=total_hours,
                            unit_price=hourly_rate,
                            amount=line_amount
                        )

                        subtotal += line_amount

                # Calculate final amounts
                tax_amount = subtotal * self.tax_rate
                total_amount = subtotal + tax_amount

                # Update invoice with final amounts
                invoice.subtotal = subtotal
                invoice.tax_amount = tax_amount
                invoice.total = total_amount
                invoice.save(update_fields=['subtotal', 'tax_amount', 'total'])

                return invoice

        except Exception as e:
            logger.error(f"Error generating project invoice: {str(e)}")
            return None

    def process_overdue_invoices(self):
        today = timezone.now().date()
        overdue_invoices = Invoice.objects.filter(
            due_date__lt=today,
            status__in=['pending', 'partial']
        )

        count = 0
        for invoice in overdue_invoices:
            invoice.status = 'overdue'
            invoice.save(update_fields=['status'])
            count += 1

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
        today = timezone.now().date()

        upcoming_due = Invoice.objects.filter(
            due_date__range=[today, today + timedelta(days=3)],
            status__in=['pending', 'partial']
        )

        overdue = Invoice.objects.filter(
            due_date__lt=today,
            status='overdue'
        )

        reminder_count = 0

        for invoice in upcoming_due:
            days_until = (invoice.due_date - today).days
            if invoice.customer.assigned_to:
                self.notification_service.create_invoice_due_notification(
                    invoice, days_before=days_until
                )
                reminder_count += 1

        for invoice in overdue:
            days_overdue = (today - invoice.due_date).days
            if days_overdue in [1, 3, 7, 14, 30] and invoice.customer.assigned_to:
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
        self.generate_subscription_invoices()
        if CUSTOMER_PROJECTS_AVAILABLE:
            self.generate_project_invoices()
        self.process_overdue_invoices()
        self.send_invoice_reminders()
