from django.core.management import call_command
from django.core.cache import cache
from django.conf import settings
from threading import Thread, Event
import time
import logging
import signal
import sys
from contextlib import contextmanager

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

def initialize_scheduler():
    """Initialize the scheduler with proper error handling"""
    scheduler = None
    try:
        # Check if DEBUG mode
        if settings.DEBUG:
            logger.warning("Running scheduler in DEBUG mode")

        # Check if scheduler is already running
        if cache.get('reminder_scheduler_running'):
            logger.warning("Scheduler appears to be already running")
            return

        scheduler = ReminderScheduler()
        scheduler.start()
        cache.set('reminder_scheduler_running', True, timeout=300)

        logger.info("Reminder scheduler initialized successfully")

        # Register cleanup for system exit
        def cleanup(signum, frame):
            if scheduler:
                logger.info("Shutting down scheduler...")
                scheduler.stop()
            sys.exit(0)

        signal.signal(signal.SIGTERM, cleanup)
        signal.signal(signal.SIGINT, cleanup)

    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {str(e)}", exc_info=True)
        if scheduler:
            scheduler.stop()
        raise
