class ChatManager {
    constructor(sessionId, currentEmployee) {
        this.sessionId = sessionId;
        this.currentEmployee = currentEmployee;
        this.ws = null;
        this.messageContainer = document.getElementById('messageContainer');
        this.messageForm = document.getElementById('messageForm');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.receiverSelect = document.getElementById('receiverSelect');
        this.alertContainer = document.getElementById('alertContainer');
        this.isLoading = false;
        this.hasMore = true;
        this.lastTimestamp = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;

        this.initWebSocket();
        this.initEventListeners();
        this.initNotifications();
    }

    showAlert(message, type = 'danger', duration = 5000) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;

        this.alertContainer.appendChild(alertDiv);

        // Set up fade out and removal
        setTimeout(() => {
            alertDiv.classList.add('fade-out');
            setTimeout(() => {
                alertDiv.remove();
            }, 500);
        }, duration);

        // Allow manual dismissal
        alertDiv.querySelector('.btn-close').addEventListener('click', () => {
            alertDiv.remove();
        });
    }

    updateConnectionStatus(status) {
        if (this.connectionStatus) {
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
                default:
                    this.connectionStatus.textContent = 'Connection Error';
            }
        }
    }

    initWebSocket() {
        try {
            this.updateConnectionStatus('connecting');

            this.ws = new WebSocket(
                `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/chat/${this.sessionId}/`
            );

            this.ws.onmessage = this.handleWebSocketMessage.bind(this);
            this.ws.onopen = this.handleWebSocketOpen.bind(this);
            this.ws.onclose = this.handleWebSocketClose.bind(this);
            this.ws.onerror = this.handleWebSocketError.bind(this);
        } catch (error) {
            console.error('WebSocket initialization error:', error);
            this.showAlert('Failed to initialize chat connection', 'danger');
            this.scheduleReconnect();
        }
    }

    handleWebSocketMessage(event) {
        try {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'chat_message':
                    this.handleNewMessage(data.message);
                    break;
                case 'error':
                    this.showAlert(data.message, 'danger');
                    break;
                case 'success':
                    this.showAlert(data.message, 'success', 3000);
                    break;
                default:
                    console.warn('Unknown message type:', data.type);
            }
        } catch (error) {
            console.error('Error handling WebSocket message:', error);
            this.showAlert('Error processing message', 'danger');
        }
    }

    handleWebSocketOpen() {
        console.log("WebSocket connection established");
        this.updateConnectionStatus('connected');
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
    }

    handleWebSocketClose(event) {
        console.warn('WebSocket connection closed:', event);
        this.updateConnectionStatus('disconnected');
        this.scheduleReconnect();
    }

    handleWebSocketError(error) {
        console.error('WebSocket error:', error);
        this.updateConnectionStatus('error');
        this.showAlert('Connection error occurred', 'danger');
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            this.showAlert(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`, 'warning');

            setTimeout(() => {
                this.initWebSocket();
            }, this.reconnectDelay);

            this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
        } else {
            this.showAlert('Unable to establish connection. Please refresh the page.', 'danger');
        }
    }

    initEventListeners() {
        this.messageForm.addEventListener('submit', this.handleMessageSubmit.bind(this));

        this.messageContainer.addEventListener('scroll', () => {
            if (this.messageContainer.scrollTop === 0 && !this.isLoading && this.hasMore) {
                this.loadMoreMessages();
            }
        });

        if (this.receiverSelect) {
            this.receiverSelect.addEventListener('change', (e) => {
                const receiverId = e.target.value;
                const receiverName = e.target.options[e.target.selectedIndex].text;
                if (receiverId) {
                    this.setReceiver(receiverId, receiverName);
                }
            });
        }

        window.addEventListener('focus', () => {
            this.markMessagesRead();
        });
    }

    setReceiver(receiverId, receiverName) {
        this.currentReceiverId = receiverId;
        this.currentReceiverName = receiverName;
        // You might want to clear the message container when switching receivers
        // this.messageContainer.innerHTML = '';
        this.showAlert(`Now chatting with ${receiverName}`, 'info', 3000);
    }

    async handleMessageSubmit(event) {
        event.preventDefault();

        const form = event.target;
        const content = form.content.value.trim();

        if (!content) {
            this.showAlert("Message content cannot be empty", "warning");
            return;
        }

        if (!this.currentReceiverId) {
            this.showAlert("Please select a recipient", "warning");
            return;
        }

        try {
            await this.sendMessage(content, this.currentReceiverId);
            form.content.value = '';
            form.content.focus();
        } catch (error) {
            this.showAlert(`Failed to send message: ${error.message}`, 'danger');
        }
    }

    // ... rest of the methods (sendMessage, handleNewMessage, etc.) remain the same
}
