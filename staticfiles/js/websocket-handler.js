// static/js/websocket-handler.js

class WebSocketHandler {
    constructor() {
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.handlers = new Map();
        this.connected = false;
        this.pendingMessages = [];
    }

    connect(url = null) {
        if (!url && window.wsUrl) {
            url = window.wsUrl;
        }

        if (!url) {
            console.error('WebSocket URL not provided');
            return;
        }

        try {
            this.socket = new WebSocket(url);
            this.setupEventHandlers();
        } catch (error) {
            console.error('WebSocket connection error:', error);
            this.handleConnectionError();
        }
    }

    setupEventHandlers() {
        this.socket.addEventListener('open', () => this.handleConnection());
        this.socket.addEventListener('message', (event) => this.handleMessage(event));
        this.socket.addEventListener('close', () => this.handleDisconnection());
        this.socket.addEventListener('error', (error) => this.handleError(error));
    }

    handleConnection() {
        this.connected = true;
        this.reconnectAttempts = 0;
        console.log('WebSocket connected');

        // Send any pending messages
        while (this.pendingMessages.length > 0) {
            const message = this.pendingMessages.shift();
            this.send(message);
        }

        // Trigger connect handlers
        this.triggerHandler('connect');
    }

    handleDisconnection() {
        this.connected = false;
        console.log('WebSocket disconnected');

        this.triggerHandler('disconnect');

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            setTimeout(() => {
                this.reconnectAttempts++;
                this.connect();
            }, this.reconnectDelay * Math.pow(2, this.reconnectAttempts));
        } else {
            console.error('Max reconnection attempts reached');
            this.triggerHandler('maxReconnectAttempts');
        }
    }

    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);
            const { type, payload } = data;

            if (this.handlers.has(type)) {
                this.handlers.get(type).forEach(handler => handler(payload));
            }

            // Trigger general message handlers
            this.triggerHandler('message', data);
        } catch (error) {
            console.error('Error processing message:', error);
        }
    }

    handleError(error) {
        console.error('WebSocket error:', error);
        this.triggerHandler('error', error);
    }

    handleConnectionError() {
        this.triggerHandler('connectionError');

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            setTimeout(() => {
                this.reconnectAttempts++;
                this.connect();
            }, this.reconnectDelay * Math.pow(2, this.reconnectAttempts));
        }
    }

    send(message) {
        if (!this.connected) {
            this.pendingMessages.push(message);
            return;
        }

        try {
            if (typeof message === 'object') {
                message = JSON.stringify(message);
            }
            this.socket.send(message);
        } catch (error) {
            console.error('Error sending message:', error);
            this.handleError(error);
        }
    }

    subscribe(channel) {
        this.send({
            type: 'subscribe',
            channel
        });
    }

    unsubscribe(channel) {
        this.send({
            type: 'unsubscribe',
            channel
        });
    }

    on(type, handler) {
        if (!this.handlers.has(type)) {
            this.handlers.set(type, new Set());
        }
        this.handlers.get(type).add(handler);
    }

    off(type, handler) {
        if (this.handlers.has(type)) {
            this.handlers.get(type).delete(handler);
        }
    }

    triggerHandler(type, data = null) {
        if (this.handlers.has(type)) {
            this.handlers.get(type).forEach(handler => handler(data));
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
    }
}

// Initialize WebSocket handler
const wsHandler = new WebSocketHandler();

// Example usage:
// wsHandler.connect('ws://your-server/ws');
// wsHandler.on('notification', (data) => {
//     notificationSystem.show({
//         title: data.title,
//         message: data.message,
//         type: data.type
//     });
// });

export default wsHandler;
