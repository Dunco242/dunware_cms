class ChatManager {
    constructor(sessionId, currentEmployee) {
        this.sessionId = sessionId;
        this.currentEmployee = currentEmployee;
        this.ws = null;
        this.messageContainer = document.getElementById('messageContainer');
        this.messageForm = document.getElementById('messageForm');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;

        this.initWebSocket();
        this.initEventListeners();
    }

    initWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/chat/${this.sessionId}/`;

        console.log('Connecting to WebSocket:', wsUrl);

        this.ws = new WebSocket(wsUrl);
        this.ws.onopen = this.handleWebSocketOpen.bind(this);
        this.ws.onmessage = this.handleWebSocketMessage.bind(this);
        this.ws.onclose = this.handleWebSocketClose.bind(this);
        this.ws.onerror = this.handleWebSocketError.bind(this);
    }

    initEventListeners() {
        this.messageForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.handleMessageSubmit(e);
        });

        // Scroll to bottom on load
        this.scrollToBottom();
    }

    async handleMessageSubmit(event) {
        const form = event.target;
        const content = form.content.value.trim();
        const receiverId = form.receiver_id.value;

        if (!content) return;

        if (this.ws.readyState !== WebSocket.OPEN) {
            alert('Connection lost. Attempting to reconnect...');
            this.initWebSocket();
            return;
        }

        try {
            // Only send via WebSocket
            this.ws.send(JSON.stringify({
                type: 'new_message',
                content: content,
                receiver_id: receiverId,
                session_id: this.sessionId,
                sender_id: this.currentEmployee
            }));

            // Clear input only after successful send
            form.content.value = '';
            form.content.focus();
        } catch (error) {
            console.error('Error sending message:', error);
            alert('Failed to send message. Please try again.');
        }
    }

    handleWebSocketMessage(event) {
        try {
            const data = JSON.parse(event.data);
            console.log('Received WebSocket message:', data);

            switch (data.type) {
                case 'chat_message':
                    this.displayMessage(data.message);
                    break;
                case 'messages_read':
                    this.updateReadStatus(data.reader_id);
                    break;
                case 'error':
                    console.error('Server error:', data.message);
                    alert(data.message);
                    break;
                default:
                    console.warn('Unknown message type:', data.type);
            }
        } catch (error) {
            console.error('Error handling WebSocket message:', error);
        }
    }

    displayMessage(message) {
        // Check if message already exists to prevent duplicates
        const messageId = `message-${message.id}`;
        if (document.getElementById(messageId)) {
            return;
        }

        const isOwnMessage = message.sender.id === this.currentEmployee;
        const messageHtml = `
            <div id="${messageId}" class="message ${isOwnMessage ? 'sent' : 'received'} ${message.is_read ? 'read' : ''}">
                <div class="message-content">
                    ${this.escapeHtml(message.content)}
                </div>
                <div class="message-footer">
                    <span class="message-time">
                        ${new Date(message.timestamp).toLocaleTimeString()}
                    </span>
                    ${isOwnMessage ? `
                        <span class="message-status">
                            ${message.is_read ? '✓✓' : '✓'}
                        </span>
                    ` : ''}
                </div>
            </div>
        `;

        this.messageContainer.insertAdjacentHTML('beforeend', messageHtml);
        this.scrollToBottom();
    }

    handleWebSocketOpen() {
        console.log('WebSocket connection established');
        this.updateConnectionStatus('connected');
        this.reconnectAttempts = 0;
    }

    handleWebSocketClose(event) {
        console.log('WebSocket connection closed:', event);
        this.updateConnectionStatus('disconnected');

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
            this.reconnectAttempts++;

            console.log(`Attempting to reconnect in ${delay}ms... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
            setTimeout(() => this.initWebSocket(), delay);
        } else {
            alert('Connection lost. Please refresh the page.');
        }
    }

    handleWebSocketError(error) {
        console.error('WebSocket error:', error);
        this.updateConnectionStatus('error');
    }

    updateConnectionStatus(status) {
        if (this.connectionStatus) {
            this.connectionStatus.className = `connection-status ${status}`;
            this.connectionStatus.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        }
    }

    updateReadStatus(readerId) {
        if (readerId !== this.currentEmployee) {
            const unreadMessages = this.messageContainer.querySelectorAll('.message.sent:not(.read)');
            unreadMessages.forEach(message => message.classList.add('read'));
        }
    }

    scrollToBottom() {
        this.messageContainer.scrollTop = this.messageContainer.scrollHeight;
    }

    escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
}
