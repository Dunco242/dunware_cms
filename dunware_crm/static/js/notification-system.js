// static/js/notification-system.js

class NotificationSystem {
    constructor() {
        this.container = this.createContainer();
        this.notifications = new Map();
        this.counter = 0;
    }

    createContainer() {
        let container = document.getElementById('notification-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notification-container';
            container.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 9999;
            `;
            document.body.appendChild(container);
        }
        return container;
    }

    show(options = {}) {
        const defaults = {
            title: '',
            message: '',
            type: 'info',
            duration: 5000,
            dismissible: true,
            position: 'top-right'
        };

        const settings = { ...defaults, ...options };
        const id = this.counter++;

        const notification = this.createNotification(id, settings);
        this.notifications.set(id, notification);

        this.container.appendChild(notification);

        // Trigger animation
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);

        if (settings.duration) {
            setTimeout(() => {
                this.dismiss(id);
            }, settings.duration);
        }

        return id;
    }

    createNotification(id, settings) {
        const notification = document.createElement('div');
        notification.className = `notification notification-${settings.type}`;
        notification.id = `notification-${id}`;
        notification.style.cssText = `
            opacity: 0;
            transition: opacity 0.3s ease-in-out;
            margin-bottom: 10px;
            padding: 15px;
            border-radius: 4px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            min-width: 300px;
            max-width: 400px;
        `;

        let html = '';
        if (settings.title) {
            html += `<h6 class="notification-title">${settings.title}</h6>`;
        }
        html += `<div class="notification-message">${settings.message}</div>`;

        if (settings.dismissible) {
            html += `
                <button type="button" class="notification-close" aria-label="Close">
                    <span aria-hidden="true">&times;</span>
                </button>
            `;
        }

        notification.innerHTML = html;

        if (settings.dismissible) {
            const closeButton = notification.querySelector('.notification-close');
            closeButton.addEventListener('click', () => this.dismiss(id));
        }

        return notification;
    }

    dismiss(id) {
        const notification = this.notifications.get(id);
        if (notification) {
            notification.classList.remove('show');
            setTimeout(() => {
                notification.remove();
                this.notifications.delete(id);
            }, 300);
        }
    }

    success(message, title = '') {
        return this.show({
            title,
            message,
            type: 'success'
        });
    }

    error(message, title = '') {
        return this.show({
            title,
            message,
            type: 'error',
            duration: 0 // Error messages stay until dismissed
        });
    }

    warning(message, title = '') {
        return this.show({
            title,
            message,
            type: 'warning'
        });
    }

    info(message, title = '') {
        return this.show({
            title,
            message,
            type: 'info'
        });
    }

    clear() {
        this.notifications.forEach((_, id) => this.dismiss(id));
    }
}

// Initialize notification system
const notificationSystem = new NotificationSystem();
export default notificationSystem;
