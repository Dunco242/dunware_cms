// Add this to your static/js/notifications.js file

document.addEventListener('DOMContentLoaded', function() {
    // Initialize notification refresh
    initNotifications();

    // Set up notification item flashing based on urgency
    setupNotificationFlashing();

    // Set up notification actions
    setupNotificationActions();
});

// Global variable to store notification data
let notificationData = {
    notifications: [],
    counts: {}
};

/**
 * Initialize notification system
 */
function initNotifications() {
    // Fetch notifications on page load
    fetchNotifications();

    // Set up automatic refresh every 60 seconds
    setInterval(fetchNotifications, 60000);

    // Flash the appropriate tab items based on urgency
    highlightUrgentItems();
}

/**
 * Fetch notifications data from the server
 */
function fetchNotifications() {
    fetch('/notifications/json/')
        .then(response => response.json())
        .then(data => {
            notificationData = data;
            updateNotificationUI();
        })
        .catch(error => console.error('Error fetching notifications:', error));
}

/**
 * Update the UI with the latest notification data
 */
function updateNotificationUI() {
    // Update badge count
    updateNotificationBadge();

    // Update dropdown content if it exists
    updateNotificationDropdown();

    // Highlight urgent items in the navbar
    highlightUrgentItems();
}

/**
 * Update the notification badge count
 */
function updateNotificationBadge() {
    const badge = document.getElementById('notificationCountBadge');
    if (!badge) return;

    if (notificationData.counts.total > 0) {
        badge.textContent = notificationData.counts.total;
        badge.classList.remove('d-none');
    } else {
        badge.classList.add('d-none');
    }
}

/**
 * Update the notification dropdown content
 */
function updateNotificationDropdown() {
    const dropdown = document.querySelector('.notification-dropdown');
    if (!dropdown) return;

    // This would typically involve a more complex template rendering
    // For simplicity, we'll just reload the page if the dropdown is open
    // and there are new notifications

    if (dropdown.classList.contains('show') &&
        notificationData.counts.total > parseInt(document.getElementById('notificationBadge').textContent || '0')) {
        location.reload();
    }
}

/**
 * Highlight urgent items in the navbar based on notifications
 */
function highlightUrgentItems() {
    // Reset all highlights
    document.querySelectorAll('.nav-item').forEach(item => {
        if (!item.querySelector('#chatNavIcon')) { // Don't remove pulse from chat notifications
            item.classList.remove('pulse');
        }
    });

    // Add pulse class to the related nav items for immediate notifications
    if (notificationData.counts && notificationData.counts.immediate > 0) {
        // Highlight items based on notification types
        notificationData.notifications.forEach(notification => {
            if (notification.urgency_class === 'immediate') {
                highlightNavItem(notification.type);
            }
        });
    }
}

/**
 * Highlight a specific nav item based on notification type
 */
function highlightNavItem(type) {
    let selector = '';

    switch(type) {
        case 'meeting':
            selector = '.nav-link[href*="meeting"]';
            break;
        case 'task':
            selector = '.nav-link[href*="task"]';
            break;
        case 'event':
            selector = '.nav-link[href*="calendar"]';
            break;
        case 'document':
            selector = '.nav-link[href*="document"]';
            break;
        case 'video_conference':
            selector = '.nav-link[href*="video"]';
            break;
        case 'deadline':
            selector = '.nav-link[href*="project"]';
            break;
    }

    if (selector) {
        const navItems = document.querySelectorAll(selector);
        navItems.forEach(navItem => {
            const parent = navItem.closest('.nav-item');
            if (parent) {
                parent.classList.add('pulse');
            }
        });
    }
}

/**
 * Set up flashing for notification items based on urgency
 */
function setupNotificationFlashing() {
    // Add pulse animation to immediate notifications
    document.querySelectorAll('.immediate').forEach(item => {
        item.classList.add('pulse');
    });
}

/**
 * Set up notification action handlers
 */
function setupNotificationActions() {
    // Mark as read button handlers
    document.querySelectorAll('[data-action="mark-read"]').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const notificationId = this.dataset.notificationId;

            fetch(`/notifications/${notificationId}/read/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // Remove notification from UI
                    document.querySelector(`[data-notification-id="${notificationId}"]`).remove();

                    // Update counts
                    fetchNotifications();
                }
            })
            .catch(error => console.error('Error marking notification as read:', error));
        });
    });

    // Mark all as read button handler
    const markAllButton = document.querySelector('[data-action="mark-all-read"]');
    if (markAllButton) {
        markAllButton.addEventListener('click', function(e) {
            e.preventDefault();

            fetch('/notifications/mark-all-read/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // Remove all notifications from UI
                    document.querySelectorAll('.notification-item').forEach(item => {
                        item.remove();
                    });

                    // Update empty state
                    const dropdown = document.querySelector('.notification-dropdown');
                    if (dropdown) {
                        dropdown.innerHTML = `
                            <div class="text-center py-4">
                                <i class="fas fa-bell-slash fa-2x text-muted mb-2"></i>
                                <p class="mb-0 text-muted">No new notifications</p>
                            </div>
                        `;
                    }

                    // Update badge
                    const badge = document.getElementById('notificationCountBadge');
                    if (badge) {
                        badge.classList.add('d-none');
                    }
                }
            })
            .catch(error => console.error('Error marking all as read:', error));
        });
    }

    // Dismiss notification handlers
    document.querySelectorAll('[data-action="dismiss"]').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const notificationId = this.dataset.notificationId;

            fetch(`/notifications/${notificationId}/dismiss/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // Remove notification from UI
                    document.querySelector(`[data-notification-id="${notificationId}"]`).remove();

                    // Update counts
                    fetchNotifications();
                }
            })
            .catch(error => console.error('Error dismissing notification:', error));
        });
    });
}

/**
 * Get CSRF token from cookie
 */
function getCsrfToken() {
    let csrfToken = null;

    // Try to get from meta tag first
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
        csrfToken = metaTag.getAttribute('content');
    }

    // If not found, try to get from cookie
    if (!csrfToken) {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.startsWith('csrftoken=')) {
                csrfToken = cookie.substring('csrftoken='.length, cookie.length);
                break;
            }
        }
    }

    return csrfToken;
}

/**
 * Format relative time (e.g., "5 minutes ago", "in 2 hours")
 */
function formatRelativeTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = date - now;
    const diffSecs = Math.round(diffMs / 1000);
    const diffMins = Math.round(diffSecs / 60);
    const diffHours = Math.round(diffMins / 60);
    const diffDays = Math.round(diffHours / 24);

    if (diffMs >= 0) {
        // Future date
        if (diffMins < 1) {
            return 'Just now';
        } else if (diffMins < 60) {
            return `In ${diffMins} minute${diffMins !== 1 ? 's' : ''}`;
        } else if (diffHours < 24) {
            return `In ${diffHours} hour${diffHours !== 1 ? 's' : ''}`;
        } else {
            return `In ${diffDays} day${diffDays !== 1 ? 's' : ''}`;
        }
    } else {
        // Past date
        if (diffMins > -1) {
            return 'Just now';
        } else if (diffMins > -60) {
            return `${Math.abs(diffMins)} minute${Math.abs(diffMins) !== 1 ? 's' : ''} ago`;
        } else if (diffHours > -24) {
            return `${Math.abs(diffHours)} hour${Math.abs(diffHours) !== 1 ? 's' : ''} ago`;
        } else {
            return `${Math.abs(diffDays)} day${Math.abs(diffDays) !== 1 ? 's' : ''} ago`;
        }
    }
}

/**
 * Format date with time (e.g., "Jan 5, 2023 at 2:30 PM")
 */
function formatDateTime(dateString) {
    const date = new Date(dateString);
    const options = {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    };
    return date.toLocaleDateString('en-US', options).replace(',', ' at');
}
