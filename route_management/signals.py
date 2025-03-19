import logging
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    Route, RouteStop, ServiceRequest, ServiceCompletion, ServiceArea,
    CustomerFeedback, OptimizationSettings, ServiceLocation, ServiceLocationType, TechnicianProfile
)
from core.models import Customer, Employee
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

@receiver(post_save, sender=Customer)
def create_service_location(sender, instance, created, **kwargs):
    """
    Signal handler to automatically create or update a ServiceLocation
    whenever a Customer is created or updated.
    """
    # Get or create default service location type
    default_type, _ = ServiceLocationType.objects.get_or_create(
        name="Main Office",
        defaults={"description": "Customer's main office or primary location"}
    )

    # Try to find an existing default service location for this customer
    default_location = ServiceLocation.objects.filter(
        customer=instance,
        name=f"{instance.company_name} - Main Office"
    ).first()

    # Get the nearest service area if available (simplified approach)
    service_area = ServiceArea.objects.filter(is_active=True).first()

    if not default_location:
        # Create a new service location
        ServiceLocation.objects.create(
            customer=instance,
            name=f"{instance.company_name} - Main Office",
            location_type=default_type,
            address=instance.address,
            city=instance.city,
            state=instance.state,
            zip_code=instance.zip_code,
            country="United States",  # Default value, adjust as needed
            service_area=service_area,
            access_instructions=""
        )
    else:
        # Update existing location if customer address changed
        address_changed = (
            default_location.address != instance.address or
            default_location.city != instance.city or
            default_location.state != instance.state or
            default_location.zip_code != instance.zip_code
        )

        if address_changed:
            default_location.address = instance.address
            default_location.city = instance.city
            default_location.state = instance.state
            default_location.zip_code = instance.zip_code
            default_location.save()

@receiver(post_save, sender=Employee)
def create_technician_profile(sender, instance, created, **kwargs):
    """
    Signal handler to automatically create a TechnicianProfile
    whenever an Employee with a relevant role is created.
    """
    # Check if the employee is in a relevant department that should have a technician profile
    technician_departments = ['engineering', 'support', 'field_service']
    technician_positions = ['technician', 'field_tech', 'engineer', 'senior', 'lead']

    is_technician = (
        instance.department in technician_departments or
        any(tech_role in instance.position.lower() for tech_role in technician_positions)
    )

    # If this is a technician role but doesn't have a profile yet, create one
    if is_technician:
        # Check if a profile already exists
        from route_management.models import TechnicianProfile
        profile_exists = TechnicianProfile.objects.filter(employee=instance).exists()

        if not profile_exists:
            # Create a default technician profile
            from route_management.models import TechnicianProfile
            TechnicianProfile.objects.create(
                employee=instance,
                max_travel_distance_miles=50,
                enable_location_tracking=False
            )
# You can add more signal handlers as needed for other models
