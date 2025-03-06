// notifications.js - Updated with WebSocket support

document.addEventListener('DOMContentLoaded', function() {
    // Initialize notification system
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

// WebSocket connection and state
let socket = null;
let isConnected = false;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

/**
 * Initialize notification system
 */
function initNotifications() {
    // Get the employee ID
    const userInfo = document.getElementById('userInfo');
    if (userInfo) {
        const employeeId = userInfo.dataset.employeeId;
        if (employeeId) {
            // Connect to WebSocket
            connectWebSocket(employeeId);
        }
    }

    // As a fallback, fetch notifications via HTTP once initially
    fetchNotifications();

    // Flash the appropriate tab items based on urgency
    highlightUrgentItems();
}

/**
 * Connect to the notification WebSocket
 * @param {string} employeeId - The employee ID to connect with
 */
function connectWebSocket(employeeId) {
    // Create WebSocket URL (using wss:// for HTTPS sites, ws:// otherwise)
    const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    const wsUrl = `${protocol}${window.location.host}/wss/notifications/${employeeId}/`;

    try {
        console.log('Connecting to notification WebSocket...');
        socket = new WebSocket(wsUrl);

        socket.onopen = function() {
            console.log('Notification WebSocket connected!');
            isConnected = true;
            reconnectAttempts = 0;

            // Request current notifications
            sendWebSocketMessage({
                type: 'get_notifications'
            });
        };

        socket.onmessage = function(event) {
            const data = JSON.parse(event.data);

            // Handle different message types
            if (data.type === 'notification_update') {
                notificationData.notifications = data.notifications;
                notificationData.counts = data.counts;
                updateNotificationUI();
            } else if (data.type === 'notification_created') {
                // Handle new notification (maybe play a sound)
                playNotificationSound(data.notification);

                // Request a full update
                sendWebSocketMessage({
                    type: 'get_notifications'
                });
            }
        };

        socket.onclose = function(event) {
            console.log('Notification WebSocket closed:', event.code, event.reason);
            isConnected = false;

            // Try to reconnect with exponential backoff
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                const delay = Math.min(3000 * reconnectAttempts, 15000);
                console.log(`Attempting to reconnect in ${delay}ms (attempt ${reconnectAttempts})`);

                setTimeout(function() {
                    connectWebSocket(employeeId);
                }, delay);
            } else {
                console.log('Max reconnect attempts reached, falling back to HTTP polling');
                // Fall back to regular HTTP polling
                setInterval(fetchNotifications, 60000);
            }
        };

        socket.onerror = function(error) {
            console.error('Notification WebSocket error:', error);
            // The socket will close automatically after an error
        };
    } catch (error) {
        console.error('Error creating WebSocket:', error);

        // Fall back to HTTP polling if WebSocket fails
        setInterval(fetchNotifications, 60000);
    }
}

/**
 * Send a message through the WebSocket
 * @param {Object} data - The message to send
 */
function sendWebSocketMessage(data) {
    if (!socket || !isConnected) {
        console.log('WebSocket not connected, cannot send message');
        return false;
    }

    socket.send(JSON.stringify(data));
    return true;
}

/**
 * Play a sound for important notifications
 * @param {Object} notification - The notification object
 */
function playNotificationSound(notification) {
    // Only play for immediate urgency
    if (notification.urgency_class === 'immediate') {
        try {
            const sound = new Audio('/static/sounds/notification.mp3');
            sound.play().catch(e => console.log('Could not play notification sound', e));
        } catch (e) {
            console.log('Error playing notification sound', e);
        }
    }
}

/**
 * Fetch notifications data from the server (HTTP fallback)
 */
function fetchNotifications() {
    // Skip HTTP fetch if WebSocket is connected
    if (isConnected) return;

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

    if (notificationData.counts && notificationData.counts.total > 0) {
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

    if (dropdown.classList.contains('show')) {
        const currentCount = parseInt(document.getElementById('notificationCountBadge').textContent || '0');
        if (notificationData.counts && Math.abs(notificationData.counts.total - currentCount) > 2) {
            location.reload();
        }
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
    if (notificationData.notifications && notificationData.notifications.length > 0) {
        // Highlight items based on notification types
        notificationData.notifications.forEach(notification => {
            if (notification.urgency_class === 'immediate') {
                highlightNavItem(notification.notification_type);
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

            // Try to use WebSocket first
            if (sendWebSocketMessage({
                type: 'mark_read',
                notification_id: notificationId
            })) {
                // If sent via WebSocket, we're done
                return;
            }

            // Fallback to HTTP
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

            // Try to use WebSocket first
            if (sendWebSocketMessage({
                type: 'mark_all_read'
            })) {
                // If sent via WebSocket, we're done
                return;
            }

            // Fallback to HTTP
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

            // Try to use WebSocket first
            if (sendWebSocketMessage({
                type: 'dismiss',
                notification_id: notificationId
            })) {
                // If sent via WebSocket, we're done
                return;
            }

            // Fallback to HTTP
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
