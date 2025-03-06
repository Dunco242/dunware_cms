from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from django.db.models import Q
from .models import IPAccess, PrivacyPolicyAcceptance, LegalDocument, GeneralNotifier
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

class IPTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.excluded_paths = ['/static/', '/media/', '/favicon.ico']

    def should_track(self, path):
        return not any(path.startswith(excluded) for excluded in self.excluded_paths)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    def __call__(self, request):
        response = self.get_response(request)

        if self.should_track(request.path):
            try:
                # Rate limiting - max 100 records per IP per hour
                ip = self.get_client_ip(request)
                cache_key = f'ip_tracking_{ip}'
                if not cache.get(cache_key):
                    IPAccess.objects.create(
                        ip_address=ip,
                        user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
                        path=request.path[:255],  # Ensure path length doesn't exceed field max length
                        user_agent=request.META.get('HTTP_USER_AGENT', '')[:1000],  # Limit user agent length
                        method=request.method[:10],
                        is_ajax=request.headers.get('x-requested-with') == 'XMLHttpRequest',
                        is_secure=request.is_secure(),
                    )
                    cache.set(cache_key, True, 3600)  # Cache for 1 hour
            except Exception as e:
                logger.error(f"Error in IPTrackingMiddleware: {str(e)}", exc_info=True)

        return response

class PrivacyPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Paths that don't require policy acceptance
            exempt_paths = [
                '/privacy-policy/',
                '/accept-privacy-policy/',
                '/logout/',
                '/admin/',
            ]

            # Check if current path is exempt
            if not any(request.path.startswith(path) for path in exempt_paths):
                # Check if user has accepted current policy
                current_version = "1.0.0"  # Consider making this configurable
                if not PrivacyPolicyAcceptance.objects.filter(
                    user=request.user,
                    policy_version=current_version
                ).exists():
                    messages.warning(
                        request,
                        'Please accept our Privacy Policy to continue.'
                    )
                    return redirect('privacy_policy')

        return self.get_response(request)

class NotificationMiddleware:
    """
    Middleware to process notifications for each request
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        Process notifications before view execution
        """
        if request.user.is_authenticated:
            # Add notifications to the request context
            active_notifications = self.get_active_notifications(request.user)
            request.notifications = active_notifications

            # Add notification counts to the request context
            request.notification_counts = {
                'total': active_notifications.count(),
                'upcoming': self.get_upcoming_notifications_count(request.user),
                'urgent': self.get_urgent_notifications_count(request.user),
            }

        # Process the request and get the response
        response = self.get_response(request)
        return response

    def get_active_notifications(self, user):
        """
        Get active notifications for a user
        """
        return GeneralNotifier.objects.filter(
            user=user,
            is_read=False,
            is_dismissed=False
        ).order_by('event_datetime')

    def get_upcoming_notifications_count(self, user):
        """
        Get count of upcoming notifications (events in the next 24 hours)
        """
        now = timezone.now()
        tomorrow = now + timezone.timedelta(days=1)

        return GeneralNotifier.objects.filter(
            user=user,
            is_read=False,
            is_dismissed=False,
            event_datetime__gt=now,
            event_datetime__lt=tomorrow
        ).count()

    def get_urgent_notifications_count(self, user):
        """
        Get count of urgent notifications (high priority or very soon)
        """
        now = timezone.now()
        soon = now + timezone.timedelta(minutes=30)

        return GeneralNotifier.objects.filter(
            user=user,
            is_read=False,
            is_dismissed=False
        ).filter(
            # High priority items or items happening very soon
            Q(priority='high') |
            Q(event_datetime__gt=now, event_datetime__lt=soon)
        ).count()
