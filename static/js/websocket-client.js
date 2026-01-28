class PostureWSClient {
    constructor() {
        this.socket = null;
        this.onMessage = null;
        this.onConnectionChange = null;
        this.reconnectAttempts = 0;
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.socket = new WebSocket(`${protocol}//${window.location.host}/ws`);

        this.socket.onopen = () => {
            console.log("[WS] Connected");
            this.reconnectAttempts = 0;
            if (this.onConnectionChange) this.onConnectionChange(true, false);
        };

        this.socket.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                if (this.onMessage) this.onMessage(message);
            } catch (e) {
                console.error("[WS] Parse error:", e);
            }
        };

        this.socket.onclose = () => {
            console.log("[WS] Disconnected");
            if (this.onConnectionChange) this.onConnectionChange(false, true);
            if (this.reconnectAttempts < 5) {
                this.reconnectAttempts++;
                setTimeout(() => this.connect(), 2000);
            }
        };

        this.socket.onerror = (e) => console.error("[WS] Error:", e);
    }

    startSession() {
        if (this.socket?.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({ action: 'start_session' }));
        }
    }

    stopSession() {
        if (this.socket?.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({ action: 'stop_session' }));
        }
    }
}

window.wsClient = new PostureWSClient();
