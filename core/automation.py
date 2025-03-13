# core/automation.py
import logging
from django.conf import settings
from django.utils import timezone
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AutomationSystem:
    """
    Main class for managing the CRM automation system
    """

    def __init__(self):
        self._initialized = False
        self._services = {}

    def initialize(self):
        """Initialize all automation components"""
        if self._initialized:
            logger.warning("Automation system already initialized")
            return False

        logger.info("Initializing CRM automation system")

        try:
            # Import services
            from .scheduling_service import SchedulingService
            from .notification_service import SmartNotificationService
            from .customer_lifecycle import CustomerLifecycleManager
            from .invoice_automation import InvoiceGenerator

            # Initialize services
            self._services['notification'] = SmartNotificationService()
            self._services['customer_lifecycle'] = CustomerLifecycleManager()
            self._services['invoice'] = InvoiceGenerator()

            # Initialize schedulers
            from .schedulers import initialize_schedulers
            initialize_schedulers()

            self._initialized = True
            logger.info("CRM automation system initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Error initializing automation system: {str(e)}")
            return False

    def get_service(self, service_name):
        """Get a service instance by name"""
        if not self._initialized:
            logger.warning("Automation system not initialized")
            return None

        return self._services.get(service_name)

    def shutdown(self):
        """Shutdown the automation system"""
        if not self._initialized:
            logger.warning("Automation system not initialized")
            return

        logger.info("Shutting down automation system")

        try:
            # Shutdown schedulers
            from .schedulers import automation_scheduler
            automation_scheduler.shutdown()

            self._initialized = False
            logger.info("Automation system shutdown successfully")

        except Exception as e:
            logger.error(f"Error shutting down automation system: {str(e)}")

    def run_manual_process(self, process_name, **kwargs):
        """Run a specific automation process manually"""
        if not self._initialized:
            logger.warning("Automation system not initialized")
            return False

        logger.info(f"Running manual process: {process_name}")

        try:
            if process_name == 'notifications':
                self._services['notification'].send_batch_notifications()
                return True

            elif process_name == 'customer_lifecycle':
                customer_id = kwargs.get('customer_id')
                if customer_id:
                    from .models import Customer
                    customer = Customer.objects.get(id=customer_id)
                    self._services['customer_lifecycle'].evaluate_customer_health(customer)
                else:
                    self._services['customer_lifecycle'].evaluate_customer_health()
                    self._services['customer_lifecycle'].check_for_client_inactivity()
                    self._services['customer_lifecycle'].schedule_customer_checkup()
                return True

            elif process_name == 'invoices':
                self._services['invoice'].run_regular_processes()
                return True

            else:
                logger.warning(f"Unknown process: {process_name}")
                return False

        except Exception as e:
            logger.error(f"Error running process {process_name}: {str(e)}")
            return False

# Create singleton instance
automation_system = AutomationSystem()

def initialize_automation():
    """Initialize the automation system if enabled"""
    if getattr(settings, 'ENABLE_AUTOMATION', False):
        return automation_system.initialize()
    else:
        logger.info("Automation disabled via settings")
        return False
