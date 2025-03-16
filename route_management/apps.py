from django.apps import AppConfig


class RouteManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'route_management'

    def ready(self):
        """Import signals when app is ready to ensure signal handlers are registered"""
        import route_management.signals
