import logging
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    Route, RouteStop, ServiceRequest, ServiceCompletion,
    CustomerFeedback, OptimizationSettings, ServiceLocation
)
from .services.notifications import RouteNotifier
from .services.geocoding import GeocodingService

logger = logging.getLogger(__name__)

# Initialize notification service
route_notifier = RouteNotifier()

@receiver(post_save, sender=Route)
def handle_route_assigned(sender, instance, created, **kwargs):
    """Handle notifications when a route is created or updated"""
    if created:
        logger.info(f"New route created: {instance.route_id}")

        # Create a notification for the assigned technician
        if instance.technician:
            route_notifier.create_route_assigned_notification(instance)
    else:
        # Check if specific fields were updated
        if kwargs.get('update_fields'):
            update_fields = kwargs['update_fields']

            # If date was changed, notify about schedule change
            if 'date' in update_fields:
                # We don't have access to the old date here, but the notification will still be useful
                route_notifier.create_route_schedule_change_notification(instance)

            # If technician was changed, notify the new technician
            if 'technician_id' in update_fields and instance.technician:
                route_notifier.create_route_assigned_notification(instance)


@receiver(pre_save, sender=RouteStop)
def store_old_stop_status(sender, instance, **kwargs):
    """Store the old status before save for comparison"""
    if instance.pk:  # Only for existing objects
        try:
            # Get the old instance from the database
            old_instance = RouteStop.objects.get(pk=instance.pk)
            # Store the old status on the instance temporarily
            instance._old_status = old_instance.status
        except RouteStop.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=RouteStop)
def handle_route_stop_status_change(sender, instance, created, **kwargs):
    """Handle notifications when a route stop status changes"""
    if not created:
        # Check if status changed
        old_status = getattr(instance, '_old_status', None)
        if old_status and instance.status != old_status:
            logger.info(f"RouteStop {instance.id} status changed from {old_status} to {instance.status}")

            # Create status change notification
            route_notifier.create_stop_status_notification(instance, old_status)

            # Special handling for specific status changes
            if instance.status == 'en_route' and old_status != 'en_route':
                # Technician is now en route to this location
                route_notifier.create_technician_enroute_notification(instance)


@receiver(post_save, sender=ServiceCompletion)
def handle_service_completion(sender, instance, created, **kwargs):
    """Handle notifications when a service is completed"""
    if created:
        logger.info(f"Service completion recorded for request {instance.service_request.request_number}")

        # Create completion notification
        route_notifier.create_completion_notification(instance)


@receiver(post_save, sender=CustomerFeedback)
def handle_customer_feedback(sender, instance, created, **kwargs):
    """Handle notifications when customer feedback is submitted"""
    if created:
        logger.info(f"Customer feedback received for request {instance.service_request.request_number}")

        # Create feedback notification
        route_notifier.create_customer_feedback_notification(instance)


@receiver(post_save, sender=ServiceLocation)
def handle_service_location_geocoding(sender, instance, created, **kwargs):
    """Handle automatic geocoding of service locations"""
    # Check if latitude/longitude is missing
    if not instance.latitude or not instance.longitude:
        try:
            # Queue geocoding as a background task if possible, or do it synchronously
            GeocodingService.geocode_location(instance)
        except Exception as e:
            logger.error(f"Error geocoding service location {instance.id}: {str(e)}")


# You can add more signal handlers as needed for other models
