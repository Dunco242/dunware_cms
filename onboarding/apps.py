from django.apps import AppConfig


class OnboardingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'onboarding'
    verbose_name = 'Customer Onboarding'

    def ready(self):
        """
        Import signal handlers when the app is ready.
        """
        import onboarding.signals
