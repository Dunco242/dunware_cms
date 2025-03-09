# Add this to your core/context_processors.py file

from django.utils import timezone
from .models import GeneralNotifier, ChatMessage

def notification_processor(request):
    """
    Context processor to add notifications to all templates
    """
    if not request.user.is_authenticated:
        return {
            'notifications': [],
            'notification_counts': {
                'total': 0,
                'upcoming': 0,
                'urgent': 0,
                'immediate': 0
            },
            'unread_count': 0
        }

    # Get active notifications
    notifications = GeneralNotifier.objects.filter(
        user=request.user,
        is_read=False,
        is_dismissed=False
    ).order_by('event_datetime')

    now = timezone.now()

    # Calculate various time frames for notifications
    immediate_notifs = notifications.filter(event_datetime__lte=now + timezone.timedelta(minutes=5))
    very_soon_notifs = notifications.filter(
        event_datetime__gt=now + timezone.timedelta(minutes=5),
        event_datetime__lte=now + timezone.timedelta(minutes=30)
    )
    soon_notifs = notifications.filter(
        event_datetime__gt=now + timezone.timedelta(minutes=30),
        event_datetime__lte=now + timezone.timedelta(hours=1)
    )
    today_notifs = notifications.filter(
        event_datetime__gt=now + timezone.timedelta(hours=1),
        event_datetime__lte=now + timezone.timedelta(days=1)
    )
    upcoming_notifs = notifications.filter(
        event_datetime__gt=now + timezone.timedelta(days=1)
    )

    # Group notifications by urgency
    grouped_notifications = {
        'immediate': immediate_notifs,
        'very_soon': very_soon_notifs,
        'soon': soon_notifs,
        'today': today_notifs,
        'upcoming': upcoming_notifs
    }

    # Count notifications by type
    notification_types = {}
    for notif_type, _ in GeneralNotifier.NOTIFICATION_TYPES:
        notification_types[notif_type] = notifications.filter(notification_type=notif_type).count()

    # Calculate total counts
    notification_counts = {
        'total': notifications.count(),
        'immediate': immediate_notifs.count(),
        'very_soon': very_soon_notifs.count(),
        'soon': soon_notifs.count(),
        'today': today_notifs.count(),
        'upcoming': upcoming_notifs.count(),
        'types': notification_types
    }

    # Get unread chat message count for the chat badge
    unread_count = 0
    try:
        if hasattr(request.user, 'employee_profile'):
            unread_count = ChatMessage.objects.filter(
                receiver=request.user.employee_profile,
                is_read=False
            ).count()
    except Exception as e:
        # Log error but don't break page rendering
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting unread chat count: {str(e)}")

    return {
        'notifications': notifications,
        'grouped_notifications': grouped_notifications,
        'notification_counts': notification_counts,
        'unread_count': unread_count
    }
