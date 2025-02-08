# core/schedulers.py
from django.core.management import call_command
from threading import Thread
import time
import logging

logger = logging.getLogger(__name__)

class ReminderScheduler(Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True  # Thread will exit when main program exits
        self._running = True

    def run(self):
        while self._running:
            try:
                logger.info("Looking for Meetings/Reminders and Tasks...")
                call_command('check_reminders')
                # Sleep for 5 minutes
                time.sleep(300)
            except Exception as e:
                logger.error(f"Error in reminder scheduler: {e}")
                time.sleep(60)  # Wait a minute before retrying if there's an error

    def stop(self):
        self._running = False

def initialize_scheduler():
    try:
        scheduler = ReminderScheduler()
        scheduler.start()
        logger.info("Reminder scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start reminder scheduler: {e}")
