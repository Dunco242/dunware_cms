/**
 * ChatManager handles WebSocket connections and messaging for the chat system
 */
class ChatManager {
    /**
     * Initialize the chat manager
     * @param {string} sessionId - The chat session ID
     * @param {string} employeeId - The current user's employee ID
     * @param {string} wsBaseUrl - Base URL for WebSocket (with protocol)
     * @param {boolean} isGroupChat - Whether this is a group chat
     */
    constructor(sessionId, employeeId, wsBaseUrl = null, isGroupChat = false) {
        this.sessionId = sessionId;
        this.employeeId = employeeId;
        this.isGroupChat = isGroupChat;
        this.messageContainer = document.getElementById('messageContainer');
        this.messageForm = document.getElementById('messageForm');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.isConnected = false;

        // If wsBaseUrl is not provided, determine it based on page protocol
        if (!wsBaseUrl) {
            const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            wsBaseUrl = protocol + window.location.host;
        }

        // Check if we're in production (deployed)
        const isProduction = window.location.hostname !== 'localhost' &&
                           !window.location.hostname.startsWith('127.0.0.1');

        // Use correct path based on environment
        const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
this.wsUrl = `${protocol}${window.location.host}/ws/chat/${sessionId}/`;

        // Initialize the connection
        this.connect();

        // Set up event listeners
        this.setupEventListeners();

        // Scroll to bottom of messages
        this.scrollToBottom();
    }

    /**
     * Connect to the WebSocket server
     */
    connect() {
        this.updateConnectionStatus('connecting');

        try {
            this.socket = new WebSocket(this.wsUrl);

            this.socket.onopen = () => {
                console.log('WebSocket connected');
                this.updateConnectionStatus('connected');
                this.isConnected = true;
            };

            this.socket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('Received WebSocket message:', data);
                this.handleMessage(data);
            };

            this.socket.onclose = (event) => {
                console.log('WebSocket disconnected:', event.code, event.reason);
                this.updateConnectionStatus('disconnected');
                this.isConnected = false;

                // Try to reconnect after a delay
                setTimeout(() => {
                    this.connect();
                }, 3000);
            };

            this.socket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateConnectionStatus('disconnected');
                this.isConnected = false;
            };
        } catch (error) {
            console.error('Error creating WebSocket connection:', error);
            this.updateConnectionStatus('disconnected');
            this.isConnected = false;
        }
    }

    /**
     * Set up event listeners for the message form
     */
    setupEventListeners() {
        if (this.messageForm) {
            this.messageForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.sendMessage();
            });
        }

        // Leave chat button
        const leaveButton = document.getElementById('leaveChatBtn');
        if (leaveButton) {
            leaveButton.addEventListener('click', () => {
                if (confirm("Are you sure you want to leave this chat?")) {
                    this.leaveChat();
                }
            });
        }
    }

    /**
     * Send a message through the WebSocket
     */
    sendMessage() {
        if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
            console.error('WebSocket is not connected');
            this.addSystemMessageToDOM('Cannot send message, connection lost.', 'error');
            return;
        }

        const formData = new FormData(this.messageForm);
        const content = formData.get('content').trim();
        const receiverId = formData.get('receiver_id');

        if (!content) return;

        // Create message data
        const messageData = {
            type: 'new_message',
            session_id: this.sessionId,
            sender_id: this.employeeId,
            receiver_id: receiverId,
            content: content
        };

        // Send the message
        this.socket.send(JSON.stringify(messageData));

        // Clear the input field
        this.messageForm.reset();
    }

    /**
     * Leave the current chat
     */
    leaveChat() {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            // Create leave chat data
            const leaveData = {
                type: 'leave_chat',
                session_id: this.sessionId,
                employee_id: this.employeeId
            };

            // Send the leave message through WebSocket
            this.socket.send(JSON.stringify(leaveData));

            // Show system message
            this.addSystemMessageToDOM('Leaving chat...', 'info');
        } else {
            // Fallback to HTTP if WebSocket is not available
            window.location.href = `/chat/leave/${this.sessionId}/${this.employeeId}/`;
        }
    }

    /**
     * Handle incoming messages
     * @param {Object} data - The message data
     */
    handleMessage(data) {
        if (data.type === 'chat_message') {
            console.log('Message details:', data.message);
            this.addMessageToDOM(data.message);
        } else if (data.type === 'user_left') {
            console.log('User left chat:', data.user_id, data.message);
            this.addSystemMessageToDOM(data.message);

            // If current user is the one who left, redirect to chat list
            if (data.user_id === this.employeeId) {
                setTimeout(() => {
                    window.location.href = '/chat/';
                }, 2000);
            }
        } else if (data.type === 'error') {
            console.error('Error from server:', data.message);
            this.addSystemMessageToDOM('Error: ' + data.message, 'error');
        }
    }

    /**
     * Add a message to the DOM
     * @param {Object} message - The message data
     */
    addMessageToDOM(message) {
        const isSent = message.sender.id === this.employeeId;

        // Create message elements
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${isSent ? 'sent' : 'received'}`;
        messageDiv.dataset.id = message.id;

        // Add sender name badge for received messages or in group chats
        if ((this.isGroupChat || !isSent) && message.sender.name) {
            const messageSender = document.createElement('div');
            messageSender.className = 'message-sender';
            messageSender.textContent = message.sender.name;
            messageDiv.appendChild(messageSender);
        }

        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.textContent = message.content;

        const messageFooter = document.createElement('div');
        messageFooter.className = 'message-footer';

        const messageTime = document.createElement('span');
        messageTime.className = 'message-time';

        // Format the time
        const date = new Date(message.timestamp);
        messageTime.textContent = date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

        messageFooter.appendChild(messageTime);

        // Add read status for sent messages
        if (isSent) {
            const messageStatus = document.createElement('span');
            messageStatus.className = 'message-status';
            messageStatus.textContent = message.is_read ? '✓✓' : '✓';
            messageFooter.appendChild(messageStatus);
        }

        // Assemble the message
        messageDiv.appendChild(messageContent);
        messageDiv.appendChild(messageFooter);

        // Add to the container
        this.messageContainer.appendChild(messageDiv);

        // Scroll to the new message
        this.scrollToBottom();
    }

    /**
     * Add a system message to the DOM
     * @param {string} text - The message text
     * @param {string} type - Message type (default, error, info)
     */
    addSystemMessageToDOM(text, type = 'default') {
        // Create system message element
        const messageDiv = document.createElement('div');
        messageDiv.className = `message system ${type}`;

        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.textContent = text;

        // Assemble the message
        messageDiv.appendChild(messageContent);

        // Add to the container
        this.messageContainer.appendChild(messageDiv);

        // Scroll to the new message
        this.scrollToBottom();
    }

    /**
     * Scroll to the bottom of the message container
     */
    scrollToBottom() {
        if (this.messageContainer) {
            this.messageContainer.scrollTop = this.messageContainer.scrollHeight;
        }
    }

    /**
     * Update the connection status indicator
     * @param {string} status - The connection status (connecting, connected, disconnected)
     */
    updateConnectionStatus(status) {
        if (!this.connectionStatus) return;

        this.connectionStatus.className = status;

        switch (status) {
            case 'connected':
                this.connectionStatus.textContent = 'Connected';
                break;
            case 'connecting':
                this.connectionStatus.textContent = 'Connecting...';
                break;
            case 'disconnected':
                this.connectionStatus.textContent = 'Disconnected';
                break;
        }
    }
}

/**
 * Set up notification WebSocket for real-time chat notifications
 */
function setupNotifications() {
    const userInfo = document.getElementById('userInfo');
    if (userInfo && userInfo.dataset.employeeId) {
        setupNotificationSocket(userInfo.dataset.employeeId);
    }
}

/**
 * Setup notification WebSocket connection
 * @param {string} employeeId - Current employee ID
 */
function setupNotificationSocket(employeeId) {
    // Determine WebSocket protocol and path
    const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';

    // Check if we're in production (deployed)
    const isProduction = window.location.hostname !== 'localhost' &&
                        !window.location.hostname.startsWith('127.0.0.1');

    // Use correct WebSocket path based on environment
    const wsPath = isProduction ? 'wss' : 'ws';
    const wsUrl = `${protocol}${window.location.host}/${wsPath}/notifications/${employeeId}/`;

    console.log(`Setting up notification WebSocket: ${wsUrl}`);

    let socket;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;

    function connect() {
        try {
            socket = new WebSocket(wsUrl);

            socket.onopen = function() {
                console.log('Notification WebSocket connected');
                reconnectAttempts = 0;
            };

            socket.onmessage = function(event) {
                const data = JSON.parse(event.data);
                console.log('Notification received:', data);

                if (data.type === 'new_message') {
                    // Update notification badge
                    updateNotificationBadge();

                    // Show notification if not in the chat session already
                    const currentPath = window.location.pathname;
                    const chatSessionPath = `/chat/session/${data.message.session_id}/`;

                    if (!currentPath.startsWith(chatSessionPath)) {
                        showNotification(data.message);
                    }
                }
            };

            socket.onclose = function(event) {
                console.log('Notification WebSocket closed:', event.code, event.reason);

                // Try to reconnect with exponential backoff
                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);

                    setTimeout(function() {
                        connect();
                    }, delay);
                }
            };

            socket.onerror = function(error) {
                console.error('Notification WebSocket error:', error);
            };
        } catch (error) {
            console.error('Error setting up notification WebSocket:', error);
        }
    }

    // Initial connection
    connect();
}

/**
 * Update notification badge with new count
 */
function updateNotificationBadge() {
    const badge = document.getElementById('notificationBadge');
    if (badge) {
        let count = parseInt(badge.textContent) || 0;
        count++;

        badge.textContent = count;
        badge.classList.remove('d-none');
    }
}

/**
 * Show browser notification for new message
 * @param {Object} message - Message data
 */
function showNotification(message) {
    // Check if browser supports notifications
    if (!("Notification" in window)) {
        console.log("This browser does not support desktop notifications");
        return;
    }

    // Check notification permission
    if (Notification.permission === "granted") {
        createNotification(message);
    } else if (Notification.permission !== "denied") {
        // Request permission
        Notification.requestPermission().then(function(permission) {
            if (permission === "granted") {
                createNotification(message);
            }
        });
    }
}

/**
 * Create and display desktop notification
 * @param {Object} message - Message data
 */
function createNotification(message) {
    const title = `New message from ${message.sender.name}`;
    const options = {
        body: message.content,
        icon: '/static/img/notification-icon.png', // Replace with your actual icon
        tag: `chat-${message.session_id}`
    };

    const notification = new Notification(title, options);

    notification.onclick = function() {
        window.focus();
        window.location.href = `/chat/session/${message.session_id}/`;
        notification.close();
    };

    // Auto close after 5 seconds
    setTimeout(function() {
        notification.close();
    }, 5000);
}

// Initialize chat manager and notifications when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Initialize chat if on a chat page
    const messageContainer = document.querySelector('#messageContainer');
    if (messageContainer) {
        const sessionId = messageContainer.dataset.sessionId;
        const employeeId = messageContainer.dataset.employeeId;
        const isGroupChat = messageContainer.dataset.isGroup === 'true';

        if (sessionId && employeeId) {
            window.chatManager = new ChatManager(sessionId, employeeId, null, isGroupChat);
        } else {
            console.error('Missing required data attributes for chat initialization');
        }
    }

    // Initialize notifications on every page
    setupNotifications();
});
