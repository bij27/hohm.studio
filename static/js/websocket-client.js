class PostureWSClient {
    constructor() {
        this.socket = null;
        this.onMessage = null;
        this.onConnectionChange = null;
        this.reconnectAttempts = 0;
    }

    async connect() {
        // Initialize device auth first
        const deviceToken = await DeviceAuth.initAuth();

        // Auto-detect secure WebSocket based on page protocol
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.socket = new WebSocket(`${protocol}//${window.location.host}/ws`);

        this.socket.onopen = () => {
            console.log("[WS] Connected");
            this.reconnectAttempts = 0;
            if (this.onConnectionChange) this.onConnectionChange(true, false);

            // Send device token for session ownership
            if (deviceToken) {
                this.socket.send(JSON.stringify({ action: 'set_device_token', token: deviceToken }));
                console.log("[WS] Device token sent");
            }

            // Send stored profile from localStorage if available
            const storedProfile = localStorage.getItem('hohm_profile');
            if (storedProfile) {
                try {
                    const profile = JSON.parse(storedProfile);
                    this.sendProfile(profile);
                } catch (e) {
                    console.warn("[WS] Invalid stored profile, clearing");
                    localStorage.removeItem('hohm_profile');
                }
            }
        };

        this.socket.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);

                // Auto-save profile to localStorage when calibration completes
                if (message.type === 'calibration_complete' && message.data?.profile) {
                    localStorage.setItem('hohm_profile', JSON.stringify(message.data.profile));
                    console.log("[WS] Profile saved to localStorage");
                }

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
                setTimeout(() => {
                    this.connect().catch(e => console.error("[WS] Reconnect failed:", e));
                }, 2000);
            }
        };

        this.socket.onerror = (e) => console.error("[WS] Error:", e);
    }

    sendProfile(profile) {
        if (this.socket?.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({ action: 'set_profile', profile }));
        }
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

    hasStoredProfile() {
        return localStorage.getItem('hohm_profile') !== null;
    }

    clearProfile() {
        localStorage.removeItem('hohm_profile');
    }
}

window.wsClient = new PostureWSClient();
