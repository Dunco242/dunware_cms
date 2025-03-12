// static/js/calendar.js

class CRMCalendar {
    constructor() {
        this.calendar = null;
        this.events = [];
        this.filters = {
            showMeetings: true,
            showTasks: true,
            priorities: ['high', 'medium', 'low']
        };
        this.init();
    }

    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeCalendar();
            this.setupEventListeners();
            this.setupFilters();
        });
    }

    initializeCalendar() {
        const calendarEl = document.getElementById('calendar');
        if (!calendarEl) return;

        this.calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: 'dayGridMonth',
            headerToolbar: {
                left: 'prev,next today',
                center: 'title',
                right: 'dayGridMonth,timeGridWeek,timeGridDay'
            },
            editable: true,
            selectable: true,
            selectMirror: true,
            dayMaxEvents: true,
            eventTimeFormat: {
                hour: 'numeric',
                minute: '2-digit',
                meridiem: 'short'
            },
            eventSources: [
                {
                    url: '/calendar/events/',
                    method: 'GET',
                    extraParams: () => ({
                        filters: JSON.stringify(this.filters)
                    })
                }
            ],
            eventClick: (info) => this.handleEventClick(info),
            dateClick: (info) => this.handleDateClick(info),
            eventDrop: (info) => this.handleEventDrop(info),
            eventResize: (info) => this.handleEventResize(info),
            loading: (isLoading) => this.handleLoading(isLoading),
            select: (info) => this.handleSelect(info)
        });

        this.calendar.render();
    }

    setupEventListeners() {
        // Filter change handlers
        document.querySelectorAll('.calendar-filter').forEach(filter => {
            filter.addEventListener('change', () => this.updateFilters());
        });

        // Quick action buttons
        const quickAddMeeting = document.getElementById('quickAddMeeting');
        if (quickAddMeeting) {
            quickAddMeeting.addEventListener('click', () => this.quickAddMeeting());
        }
    }

    setupFilters() {
        // Initialize filter states
        const filterControls = {
            showMeetings: document.getElementById('showMeetings'),
            showTasks: document.getElementById('showTasks'),
            highPriority: document.getElementById('showHighPriority'),
            mediumPriority: document.getElementById('showMediumPriority'),
            lowPriority: document.getElementById('showLowPriority')
        };

        // Set up event listeners for filters
        Object.entries(filterControls).forEach(([key, control]) => {
            if (control) {
                control.addEventListener('change', () => {
                    this.updateFilters();
                });
            }
        });
    }

    updateFilters() {
        this.filters = {
            showMeetings: document.getElementById('showMeetings')?.checked ?? true,
            showTasks: document.getElementById('showTasks')?.checked ?? true,
            priorities: this.getSelectedPriorities()
        };
        this.calendar.refetchEvents();
    }

    getSelectedPriorities() {
        const priorities = [];
        if (document.getElementById('showHighPriority')?.checked) priorities.push('high');
        if (document.getElementById('showMediumPriority')?.checked) priorities.push('medium');
        if (document.getElementById('showLowPriority')?.checked) priorities.push('low');
        return priorities;
    }

    handleEventClick(info) {
        const event = info.event;
        const modal = new bootstrap.Modal(document.getElementById('eventModal'));

        // Update modal content
        document.querySelector('#eventModal .modal-title').textContent = event.title;
        document.querySelector('#eventModal .modal-body').innerHTML = this.generateEventModalContent(event);

        // Update action buttons
        const viewButton = document.querySelector('#eventModal .view-details-btn');
        if (viewButton) {
            viewButton.href = event.extendedProps.detailUrl;
        }

        modal.show();
    }

    generateEventModalContent(event) {
        const startTime = event.start ? event.start.toLocaleTimeString() : '';
        const endTime = event.end ? event.end.toLocaleTimeString() : '';

        let content = `
            <div class="event-details">
                <p><strong>Date:</strong> ${event.start.toLocaleDateString()}</p>
                <p><strong>Time:</strong> ${startTime} ${endTime ? '- ' + endTime : ''}</p>
        `;

        if (event.extendedProps.type === 'meeting') {
            content += `
                <p><strong>Type:</strong> ${event.extendedProps.meetingType}</p>
                <p><strong>Organizer:</strong> ${event.extendedProps.organizer}</p>
            `;
        } else if (event.extendedProps.type === 'task') {
            content += `
                <p><strong>Priority:</strong> ${event.extendedProps.priority}</p>
                <p><strong>Status:</strong> ${event.extendedProps.status}</p>
            `;
        }

        if (event.extendedProps.description) {
            content += `<p><strong>Description:</strong> ${event.extendedProps.description}</p>`;
        }

        content += '</div>';
        return content;
    }

    handleEventDrop(info) {
        this.updateEventDates(info.event);
    }

    handleEventResize(info) {
        this.updateEventDates(info.event);
    }

    async updateEventDates(event) {
        try {
            const response = await fetch(`/calendar/update-event/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    eventId: event.id,
                    eventType: event.extendedProps.type,
                    startTime: event.start.toISOString(),
                    endTime: event.end?.toISOString()
                })
            });

            if (!response.ok) {
                throw new Error('Failed to update event');
            }

            this.showNotification('Event updated successfully', 'success');
        } catch (error) {
            console.error('Error updating event:', error);
            this.showNotification('Failed to update event', 'error');
            info.revert();
        }
    }

    handleLoading(isLoading) {
        const loadingIndicator = document.getElementById('calendarLoading');
        if (loadingIndicator) {
            loadingIndicator.style.display = isLoading ? 'block' : 'none';
        }
    }

    showNotification(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type}`;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'assertive');
        toast.setAttribute('aria-atomic', 'true');

        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto"
                        data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        `;

        const container = document.getElementById('toastContainer') || document.body;
        container.appendChild(toast);

        const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
        bsToast.show();

        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    }

    getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    }
}

// Initialize calendar
const crmCalendar = new CRMCalendar();
