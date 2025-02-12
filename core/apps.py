from django.apps import AppConfig
from django.db.models.signals import post_migrate
import sys
import logging

logger = logging.getLogger(__name__)

def startup_scheduler(sender, **kwargs):
    """
    Ensures the scheduler starts only after migrations are completed.
    """
    from core.schedulers import initialize_scheduler
    initialize_scheduler()

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        """
        Ensures the scheduler starts only when Django is fully ready
        and imports signals.
        """
        try:
            # Import signals
            import core.signals
            logger.info("Signals registered successfully")
        except Exception as e:
            logger.error(f"Error registering signals: {str(e)}")

        # Initialize scheduler if running server
        if 'runserver' in sys.argv:
            post_migrate.connect(startup_scheduler, sender=self)
