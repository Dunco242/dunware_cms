# core/schedulers.py
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.management import call_command
from django.core.cache import cache
from django.conf import settings
from threading import Thread, Event
import time
import signal
import sys
from contextlib import contextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore

from .scheduling_service import SchedulingService
from .notification_service import SmartNotificationService
from .customer_lifecycle import CustomerLifecycleManager
from .invoice_automation import InvoiceGenerator

logger = logging.getLogger(__name__)

class GracefulKiller:
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args):
        self.kill_now = True

class ReminderScheduler(Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self._stop_event = Event()
        self._running = True
        self.killer = GracefulKiller()

    def stop(self):
        """Stop the scheduler gracefully"""
        self._running = False
        self._stop_event.set()
        self.join(timeout=60)  # Wait up to 60 seconds for thread to finish

    @contextmanager
    def lock_scheduler(self):
        """Ensure only one scheduler is running using cache lock"""
        lock_id = 'reminder_scheduler_lock'
        got_lock = False
        try:
            got_lock = cache.add(lock_id, 'true', timeout=300)  # 5 minute timeout
            if got_lock:
                yield True
            else:
                logger.warning("Another scheduler instance is already running")
                yield False
        finally:
            if got_lock:
                cache.delete(lock_id)

    def process_reminders(self):
        """Process reminders with error handling and logging"""
        try:
            with self.lock_scheduler() as got_lock:
                if got_lock:
                    logger.info("Processing reminders...")
                    call_command('check_reminders')
                    logger.info("Reminder processing completed")
        except Exception as e:
            logger.error(f"Error processing reminders: {str(e)}", exc_info=True)

    def run(self):
        """Main scheduler loop with improved error handling"""
        logger.info("Reminder scheduler starting...")

        while self._running and not self.killer.kill_now:
            try:
                self.process_reminders()

                # Sleep in small intervals to allow for graceful shutdown
                for _ in range(60):  # 5 minutes = 60 * 5 seconds
                    if self._stop_event.is_set() or self.killer.kill_now:
                        break
                    time.sleep(5)

            except Exception as e:
                logger.error(f"Critical error in scheduler: {str(e)}", exc_info=True)
                time.sleep(60)  # Wait before retrying after critical error

        logger.info("Reminder scheduler shutting down...")

def initialize_reminder_scheduler():
    """Initialize the reminder scheduler with proper error handling"""
    scheduler = None
    try:
        # Check if DEBUG mode
        if settings.DEBUG:
            logger.warning("Running reminder scheduler in DEBUG mode")

        # Check if scheduler is already running
        if cache.get('reminder_scheduler_running'):
            logger.warning("Reminder scheduler appears to be already running")
            return

        scheduler = ReminderScheduler()
        scheduler.start()
        cache.set('reminder_scheduler_running', True, timeout=300)

        logger.info("Reminder scheduler initialized successfully")

        # Register cleanup for system exit
        def cleanup(signum, frame):
            if scheduler:
                logger.info("Shutting down reminder scheduler...")
                scheduler.stop()
            sys.exit(0)

        signal.signal(signal.SIGTERM, cleanup)
        signal.signal(signal.SIGINT, cleanup)

    except Exception as e:
        logger.error(f"Failed to initialize reminder scheduler: {str(e)}", exc_info=True)
        if scheduler:
            scheduler.stop()
        raise

class AutomationScheduler:
    """
    Centralized scheduler for all automated processes in the CRM system
    Uses APScheduler to manage recurring tasks
    """

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_jobstore(DjangoJobStore(), "default")

        # Initialize services
        self.notification_service = SmartNotificationService()
        self.customer_lifecycle = CustomerLifecycleManager()
        self.invoice_generator = InvoiceGenerator()

        # Track if scheduler is running
        self.is_running = False

    def start(self):
        """Start the scheduler if not already running"""
        if self.is_running:
            logger.warning("Automation scheduler already running")
            return False

        logger.info("Starting automation scheduler")

        # Schedule notification batch processing (every 30 minutes)
        self.scheduler.add_job(
            self.process_notifications,
            trigger=CronTrigger(minute="*/30"),  # Every 30 minutes
            id="process_notifications",
            max_instances=1,
            replace_existing=True
        )

        # Schedule customer lifecycle processes (daily at 1:00 AM)
        self.scheduler.add_job(
            self.process_customer_lifecycle,
            trigger=CronTrigger(hour=1, minute=0),  # 1:00 AM
            id="process_customer_lifecycle",
            max_instances=1,
            replace_existing=True
        )

        # Schedule invoice processes (daily at 2:00 AM)
        self.scheduler.add_job(
            self.process_invoices,
            trigger=CronTrigger(hour=2, minute=0),  # 2:00 AM
            id="process_invoices",
            max_instances=1,
            replace_existing=True
        )

        # Schedule old notification cleanup (weekly on Monday at 3:00 AM)
        self.scheduler.add_job(
            self.cleanup_old_notifications,
            trigger=CronTrigger(day_of_week="mon", hour=3, minute=0),  # Monday at 3:00 AM
            id="cleanup_old_notifications",
            max_instances=1,
            replace_existing=True
        )

        # Start the scheduler
        try:
            self.scheduler.start()
            self.is_running = True
            logger.info("Automation scheduler started successfully")
            return True
        except Exception as e:
            logger.error(f"Error starting automation scheduler: {str(e)}")
            return False

    def shutdown(self):
        """Shutdown the scheduler"""
        if not self.is_running:
            logger.warning("Automation scheduler not running")
            return

        logger.info("Shutting down automation scheduler")
        self.scheduler.shutdown()
        self.is_running = False

    def process_notifications(self):
        """Process all pending notifications"""
        try:
            logger.info("Processing scheduled notifications")
            self.notification_service.send_batch_notifications()
        except Exception as e:
            logger.error(f"Error processing notifications: {str(e)}")

    def process_customer_lifecycle(self):
        """Process customer lifecycle automations"""
        try:
            logger.info("Processing customer lifecycle automation")

            # Evaluate health for all customers
            self.customer_lifecycle.evaluate_customer_health()

            # Check for expiring subscriptions
            from .models import ServiceSubscription
            expiring_soon = ServiceSubscription.objects.filter(
                is_active=True,
                end_date__range=[
                    timezone.now().date(),
                    timezone.now().date() + timedelta(days=14)
                ]
            )

            for subscription in expiring_soon:
                self.customer_lifecycle.handle_subscription_expiry(subscription)

            # Schedule regular customer check-ups
            self.customer_lifecycle.schedule_customer_checkup(days_interval=90)

            # Run customer inactivity check
            self.customer_lifecycle.check_for_client_inactivity()

        except Exception as e:
            logger.error(f"Error in customer lifecycle processing: {str(e)}")

    def process_invoices(self):
        """Process invoice generation and reminders"""
        try:
            logger.info("Processing invoice automation")

            # Run all invoice processes
            self.invoice_generator.run_regular_processes()

        except Exception as e:
            logger.error(f"Error in invoice processing: {str(e)}")

    def cleanup_old_notifications(self):
        """Clean up old notifications to prevent database bloat"""
        try:
            logger.info("Cleaning up old notifications")
            self.notification_service.dismiss_old_notifications(days_old=30)
        except Exception as e:
            logger.error(f"Error cleaning up notifications: {str(e)}")

    def add_custom_job(self, func, trigger, id, **kwargs):
        """Add a custom job to the scheduler"""
        try:
            self.scheduler.add_job(
                func,
                trigger=trigger,
                id=id,
                replace_existing=True,
                **kwargs
            )
            logger.info(f"Added custom job: {id}")
            return True
        except Exception as e:
            logger.error(f"Error adding custom job {id}: {str(e)}")
            return False

# Create a singleton instance
automation_scheduler = AutomationScheduler()

def start_automation_scheduler():
    """Start the automation scheduler"""
    if getattr(settings, 'ENABLE_AUTOMATION', False):
        automation_scheduler.start()
    else:
        logger.info("Automation disabled via settings. Set ENABLE_AUTOMATION=True to enable.")

def initialize_schedulers():
    """Initialize both schedulers"""
    # Initialize reminder scheduler
    initialize_reminder_scheduler()

    # Initialize automation scheduler
    start_automation_scheduler()
