import logging
from django.utils import timezone
from django.urls import reverse
from core.notification_service import SmartNotificationService
from ..models import RouteStop, Route, ServiceRequest

logger = logging.getLogger(__name__)

class RouteNotificationService:
    """
    Service for sending route management specific notifications
    This service integrates with the core SmartNotificationService
    """

    def __init__(self):
        self.notification_service = SmartNotificationService()

    def create_route_notification(self, user, title, message,
                               event_datetime, priority='medium',
                               content_object=None, action_url=None):
        """
        Create a route-specific notification using the core notification service

        Args:
            user: User to receive notification
            title: Notification title
            message: Notification message
            event_datetime: When the event is happening
            priority: Priority level
            content_object: Optional related Django model object
            action_url: Optional URL to direct user when clicked
        """
        try:
            # Prefix title to indicate route management source
            prefixed_title = f"[Route] {title}"

            # Create notification using core service
            notification = self.notification_service.create_notification(
                user=user,
                title=prefixed_title,
                message=message,
                notification_type='task',  # Using 'task' type from core system
                event_datetime=event_datetime,
                priority=priority,
                content_object=content_object,
                action_url=action_url,
                reference_id=getattr(content_object, 'id', None)
            )

            return notification
        except Exception as e:
            logger.error(f"Error creating route notification: {str(e)}")
            return None

    def create_route_assigned_notification(self, route):
        """Create notification when technician is assigned to a route"""
        if not route.technician or not route.technician.user:
            logger.warning(f"Cannot create notification for route {route.route_id}: No technician assigned or user account")
            return None

        title = f"Route {route.route_id} Assigned"
        message = f"You have been assigned to route {route.route_id} on {route.date}"

        if route.stops.count() > 0:
            message += f" with {route.stops.count()} stops"

        action_url = reverse('route_management:route_detail', kwargs={'pk': route.pk})

        return self.create_route_notification(
            user=route.technician.user,
            title=title,
            message=message,
            event_datetime=timezone.now(),
            priority='medium',
            content_object=route,
            action_url=action_url
        )

    def create_route_reminder_notification(self, route):
        """Create a reminder notification for an upcoming route"""
        if not route.technician or not route.technician.user:
            return None

        title = f"Upcoming Route Tomorrow"
        message = f"Reminder: You have route {route.route_id} scheduled for tomorrow with {route.stops.count()} stops"

        action_url = reverse('route_management:route_detail', kwargs={'pk': route.pk})

        return self.create_route_notification(
            user=route.technician.user,
            title=title,
            message=message,
            event_datetime=route.date,
            priority='high',
            content_object=route,
            action_url=action_url
        )

    def create_route_schedule_change_notification(self, route, old_date=None):
        """Create a notification when a route schedule changes"""
        if not route.technician or not route.technician.user:
            return None

        title = f"Route Schedule Changed"

        if old_date:
            message = f"Your route {route.route_id} has been rescheduled from {old_date} to {route.date}"
        else:
            message = f"Your route {route.route_id} schedule has been updated to {route.date}"

        action_url = reverse('route_management:route_detail', kwargs={'pk': route.pk})

        return self.create_route_notification(
            user=route.technician.user,
            title=title,
            message=message,
            event_datetime=route.date,
            priority='high',
            content_object=route,
            action_url=action_url
        )

    def create_stop_status_notification(self, route_stop, old_status=None):
        """Create a notification when a stop status changes"""
        route = route_stop.route
        service_request = route_stop.service_request

        # Notify customer's assigned employee if available
        if service_request.customer and service_request.customer.assigned_to and service_request.customer.assigned_to.user:
            user = service_request.customer.assigned_to.user

            title = f"Service Request Status Update"

            if old_status:
                message = f"Service request {service_request.request_number} for {service_request.customer.company_name} status changed from {old_status} to {route_stop.get_status_display()}"
            else:
                message = f"Service request {service_request.request_number} for {service_request.customer.company_name} is now {route_stop.get_status_display()}"

            action_url = reverse('route_management:service_request_detail', kwargs={'pk': service_request.pk})

            return self.create_route_notification(
                user=user,
                title=title,
                message=message,
                event_datetime=timezone.now(),
                priority='medium',
                content_object=service_request,
                action_url=action_url
            )

        return None

    def create_completion_notification(self, service_completion):
        """Create a notification when a service is completed"""
        service_request = service_completion.service_request

        # Notify customer's assigned employee if available
        if service_request.customer and service_request.customer.assigned_to and service_request.customer.assigned_to.user:
            user = service_request.customer.assigned_to.user

            title = f"Service Completed: {service_request.service_type.name}"
            message = f"Service for {service_request.customer.company_name} has been completed by {service_completion.route_stop.route.technician.get_full_name()}"

            action_url = reverse('route_management:service_request_detail', kwargs={'pk': service_request.pk})

            return self.create_route_notification(
                user=user,
                title=title,
                message=message,
                event_datetime=timezone.now(),
                priority='medium',
                content_object=service_request,
                action_url=action_url
            )

        return None

    def create_technician_enroute_notification(self, route_stop):
        """Create notification when technician is en route to a service location"""
        service_request = route_stop.service_request

        # Notify customer's assigned employee if available
        if service_request.customer and service_request.customer.assigned_to and service_request.customer.assigned_to.user:
            user = service_request.customer.assigned_to.user

            title = f"Technician En Route"
            message = f"Technician {route_stop.route.technician.get_full_name()} is en route to {service_request.service_location.name} for {service_request.customer.company_name}"

            action_url = reverse('route_management:service_request_detail', kwargs={'pk': service_request.pk})

            return self.create_route_notification(
                user=user,
                title=title,
                message=message,
                event_datetime=timezone.now(),
                priority='high',
                content_object=service_request,
                action_url=action_url
            )

        return None

    def create_customer_feedback_notification(self, feedback):
        """Create notification when customer submits feedback"""
        service_request = feedback.service_request

        # Notify both the technician and customer's assigned employee
        recipients = []

        if service_request.assigned_technician and service_request.assigned_technician.user:
            recipients.append(service_request.assigned_technician.user)

        if service_request.customer and service_request.customer.assigned_to and service_request.customer.assigned_to.user:
            if service_request.customer.assigned_to.user not in recipients:
                recipients.append(service_request.customer.assigned_to.user)

        notifications = []
        for user in recipients:
            title = f"Customer Feedback Received"
            message = f"{service_request.customer.company_name} submitted feedback for service {service_request.request_number} with rating: {feedback.overall_rating}/5"

            action_url = reverse('route_management:service_request_detail', kwargs={'pk': service_request.pk})

            notification = self.create_route_notification(
                user=user,
                title=title,
                message=message,
                event_datetime=timezone.now(),
                priority='medium' if feedback.overall_rating >= 4 else 'high',
                content_object=service_request,
                action_url=action_url
            )

            if notification:
                notifications.append(notification)

        return notifications

# For backward compatibility and easy import
RouteNotifier = RouteNotificationService
