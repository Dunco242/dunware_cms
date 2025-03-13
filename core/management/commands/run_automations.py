# core/management/commands/run_automations.py
import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.notification_service import SmartNotificationService
from core.customer_lifecycle import CustomerLifecycleManager
from core.invoice_automation import InvoiceGenerator
from core.scheduling_service import SchedulingService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run automated processes for the CRM system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--process',
            type=str,
            choices=['all', 'notifications', 'customer-lifecycle', 'invoices', 'scheduling'],
            default='all',
            help='Specify which automation process to run'
        )

        parser.add_argument(
            '--customer',
            type=int,
            help='Specify a customer ID to run processes for a specific customer'
        )

        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable debug output'
        )

    def handle(self, *args, **options):
        process = options['process']
        customer_id = options['customer']
        debug = options['debug']

        if debug:
            logger.setLevel(logging.DEBUG)
            self.stdout.write(self.style.SUCCESS('Debug logging enabled'))

        self.stdout.write(f"Running {process} automation processes")

        # Initialize services
        notification_service = SmartNotificationService()
        customer_lifecycle = CustomerLifecycleManager()
        invoice_generator = InvoiceGenerator()

        # Get specific customer if requested
        customer = None
        if customer_id:
            from core.models import Customer
            try:
                customer = Customer.objects.get(id=customer_id)
                self.stdout.write(f"Running for customer: {customer.company_name}")
            except Customer.DoesNotExist:
                raise CommandError(f"Customer with ID {customer_id} does not exist")

        # Run requested process(es)
        if process in ['all', 'notifications']:
            self.stdout.write("Processing notifications...")
            notification_service.send_batch_notifications()
            self.stdout.write(self.style.SUCCESS("✓ Notifications processed"))

        if process in ['all', 'customer-lifecycle']:
            self.stdout.write("Processing customer lifecycle...")
            if customer:
                customer_lifecycle.evaluate_customer_health(customer)
                self.stdout.write(f"Health evaluation completed for {customer.company_name}")
            else:
                customer_lifecycle.evaluate_customer_health()
                customer_lifecycle.check_for_client_inactivity()
                customer_lifecycle.schedule_customer_checkup()
                self.stdout.write("Customer lifecycle processes completed")
            self.stdout.write(self.style.SUCCESS("✓ Customer lifecycle processed"))

        if process in ['all', 'invoices']:
            self.stdout.write("Processing invoices...")
            if customer:
                # Find the customer's subscriptions
                from core.models import ServiceSubscription
                subscriptions = ServiceSubscription.objects.filter(
                    customer=customer,
                    is_active=True
                )

                for subscription in subscriptions:
                    invoice = invoice_generator._generate_subscription_invoice(
                        subscription, timezone.now().date()
                    )
                    if invoice:
                        self.stdout.write(f"Generated invoice {invoice.invoice_number}")

                try:
                    # Try to generate project invoices if available
                    invoice_generator._generate_project_invoice(
                        {'customer': customer, 'projects': []},
                        timezone.now().date()
                    )
                except Exception as e:
                    self.stderr.write(f"Error generating project invoice: {str(e)}")

            else:
                invoice_generator.run_regular_processes()
                self.stdout.write("Invoice processes completed")
            self.stdout.write(self.style.SUCCESS("✓ Invoices processed"))

        if process in ['all', 'scheduling']:
            self.stdout.write("Processing scheduling automation...")
            if customer and customer.assigned_to:
                # Get assigned employee's user
                user = customer.assigned_to.user
                try:
                    scheduling_service = SchedulingService(user)
                    today = timezone.now().date()
                    availability = scheduling_service.get_availability(today, detailed=True)
                    if availability['available']:
                        self.stdout.write(f"Found {len(availability['slots'])} available slots for {user.username}")
                    else:
                        self.stdout.write(f"No availability for {user.username} today: {availability.get('reason')}")
                except Exception as e:
                    self.stderr.write(f"Error processing scheduling: {str(e)}")
            else:
                self.stdout.write("No customer specified, skipping scheduling automation")
            self.stdout.write(self.style.SUCCESS("✓ Scheduling processed"))

        self.stdout.write(self.style.SUCCESS('All requested automation processes completed successfully'))
