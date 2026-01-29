/**
 * Device Token Authentication for hohm.studio
 *
 * Manages anonymous device-based authentication:
 * - Generates/retrieves device token from localStorage
 * - Adds token to all fetch requests
 * - Provides token for WebSocket authentication
 */

const DEVICE_TOKEN_KEY = 'hohm_device_token';
const TOKEN_HEADER = 'X-Device-Token';

/**
 * Get or create a device token.
 * Tokens are stored in localStorage for persistence.
 */
async function getDeviceToken() {
    // Check localStorage first
    let token = localStorage.getItem(DEVICE_TOKEN_KEY);

    if (token && token.length === 64) {
        return token;
    }

    // Generate new token from server
    try {
        const response = await fetch('/api/auth/device-token', {
            method: 'POST'
        });
        const data = await response.json();

        if (data.token) {
            localStorage.setItem(DEVICE_TOKEN_KEY, data.token);
            return data.token;
        }
    } catch (error) {
        console.error('Failed to get device token:', error);
    }

    // Fallback: generate client-side (less secure but functional)
    token = generateClientToken();
    localStorage.setItem(DEVICE_TOKEN_KEY, token);
    return token;
}

/**
 * Generate a token client-side as fallback.
 * Uses crypto API for randomness.
 */
function generateClientToken() {
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
}

/**
 * Get the current device token (sync version).
 * Returns null if not yet initialized.
 */
function getDeviceTokenSync() {
    return localStorage.getItem(DEVICE_TOKEN_KEY);
}

/**
 * Authenticated fetch wrapper.
 * Automatically adds device token header to requests.
 */
async function authFetch(url, options = {}) {
    const token = await getDeviceToken();

    const headers = new Headers(options.headers || {});
    headers.set(TOKEN_HEADER, token);

    return fetch(url, {
        ...options,
        headers
    });
}

/**
 * Initialize authentication.
 * Call this on page load to ensure token exists.
 */
async function initAuth() {
    const token = await getDeviceToken();
    console.log('[Auth] Device token initialized');
    return token;
}

// Export for use in other modules
window.DeviceAuth = {
    getDeviceToken,
    getDeviceTokenSync,
    authFetch,
    initAuth,
    TOKEN_HEADER
};
