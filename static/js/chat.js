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
        this.addUserBtn = document.getElementById("addUserBtn");
        this.addUserSelect = document.getElementById("addUserSelect");
        this.leaveChatBtn = document.getElementById("leaveChatBtn");

        // Determine WebSocket protocol
        if (!wsBaseUrl) {
            const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            wsBaseUrl = protocol + window.location.host;
        }

        this.wsUrl = `${wsBaseUrl}/wss/chat/${sessionId}/`;

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

        this.socket = new WebSocket(this.wsUrl);

        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.updateConnectionStatus('connected');
        };

        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Received WebSocket message:', data);
            this.handleMessage(data);
        };

        this.socket.onclose = (event) => {
            console.log('WebSocket disconnected:', event.code, event.reason);
            this.updateConnectionStatus('disconnected');

            // Try to reconnect after a delay
            setTimeout(() => {
                this.connect();
            }, 3000);
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateConnectionStatus('disconnected');
        };
    }

    /**
     * Set up event listeners for the message form, add user, and leave chat
     */
    setupEventListeners() {
        if (this.messageForm) {
            this.messageForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.sendMessage();
            });
        }

        if (this.addUserBtn) {
            this.addUserBtn.addEventListener("click", () => {
                this.addUserToChat();
            });
        }

        if (this.leaveChatBtn) {
            this.leaveChatBtn.addEventListener("click", () => {
                this.leaveChat();
            });
        }
    }

    /**
     * Send a message through the WebSocket
     */
    sendMessage() {
        if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
            console.error('WebSocket is not connected');
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
            receiver_id: this.isGroupChat ? null : receiverId,
            content: content
        };

        // Send the message
        this.socket.send(JSON.stringify(messageData));

        // Clear the input field
        this.messageForm.reset();
    }

    /**
     * Handle incoming messages
     * @param {Object} data - The message data
     */
    handleMessage(data) {
        if (data.type === 'chat_message') {
            console.log('Message details:', data.message);
            this.addMessageToDOM(data.message);
        } else if (data.type === 'error') {
            console.error('Error from server:', data.message);
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

    /**
     * Add a user to the group chat
     */
    addUserToChat() {
        const selectedUserId = this.addUserSelect.value;
        if (!selectedUserId) {
            alert("Please select a user to add.");
            return;
        }

        fetch(`/chat/add-user/`, {
            method: "POST",
            headers: {
                "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value,
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                session_id: this.sessionId,
                user_id: selectedUserId,
            }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert("User added successfully!");
                location.reload();
            } else {
                alert("Error adding user: " + data.error);
            }
        });
    }

    /**
     * Leave a group chat
     */
    leaveChat() {
        fetch(`/chat/leave/${this.sessionId}/${this.employeeId}/`, {
            method: "POST",
            headers: { "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value }
        }).then(response => response.json())
        .then(data => {
            if (data.success) {
                alert("You have left the chat.");
                window.location.href = "/chat/inbox/"; // Redirect to chat inbox
            } else {
                alert("Error leaving chat: " + data.error);
            }
        });
    }
