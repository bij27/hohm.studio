"""
Security middleware for hohm.studio

Implements:
- Content Security Policy (CSP) headers
- Security headers (X-Frame-Options, X-Content-Type-Options, etc.)
- Rate limiting per IP
- Request size limits
- HTTPS enforcement (production)
"""

import time
import hashlib
from collections import defaultdict
from typing import Callable, Dict, Tuple
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import config as cfg


# === RATE LIMITER ===

class IPRateLimiter:
    """
    IP-based rate limiter with sliding window.
    Tracks requests per IP address and blocks excessive traffic.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_second: int = 10,
        burst_limit: int = 20,
        block_duration_seconds: int = 60
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_second = requests_per_second
        self.burst_limit = burst_limit
        self.block_duration = block_duration_seconds

        # Storage: {ip: [(timestamp, count), ...]}
        self.request_log: Dict[str, list] = defaultdict(list)
        self.blocked_ips: Dict[str, float] = {}
        self.burst_tracker: Dict[str, Tuple[float, int]] = {}

    def _clean_old_entries(self, ip: str, now: float):
        """Remove entries older than 1 minute."""
        cutoff = now - 60
        self.request_log[ip] = [
            (ts, count) for ts, count in self.request_log[ip]
            if ts > cutoff
        ]

    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP, considering proxies."""
        # Check X-Forwarded-For header (from reverse proxy)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Take the first IP (original client)
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct connection IP
        if request.client:
            return request.client.host

        return "unknown"

    def is_allowed(self, request: Request) -> Tuple[bool, str]:
        """
        Check if request is allowed.
        Returns (is_allowed, reason_if_blocked)
        """
        ip = self._get_client_ip(request)
        now = time.time()

        # Check if IP is currently blocked
        if ip in self.blocked_ips:
            if now < self.blocked_ips[ip]:
                remaining = int(self.blocked_ips[ip] - now)
                return False, f"Rate limited. Try again in {remaining} seconds."
            else:
                del self.blocked_ips[ip]

        # Check burst limit (too many requests in very short time)
        if ip in self.burst_tracker:
            last_burst_time, burst_count = self.burst_tracker[ip]
            if now - last_burst_time < 1.0:  # Within 1 second
                if burst_count >= self.burst_limit:
                    self.blocked_ips[ip] = now + self.block_duration
                    return False, "Too many requests. Please slow down."
                self.burst_tracker[ip] = (last_burst_time, burst_count + 1)
            else:
                self.burst_tracker[ip] = (now, 1)
        else:
            self.burst_tracker[ip] = (now, 1)

        # Clean old entries
        self._clean_old_entries(ip, now)

        # Count requests in last minute
        total_requests = sum(count for _, count in self.request_log[ip])

        if total_requests >= self.requests_per_minute:
            self.blocked_ips[ip] = now + self.block_duration
            return False, "Rate limit exceeded. Please try again later."

        # Log this request
        self.request_log[ip].append((now, 1))

        return True, ""


# Global rate limiter instance
rate_limiter = IPRateLimiter(
    requests_per_minute=120,  # 2 requests/second average
    requests_per_second=15,
    burst_limit=30,
    block_duration_seconds=60
)


# === SECURITY HEADERS ===

def get_csp_header(nonce: str = None) -> str:
    """
    Generate Content Security Policy header.
    Configured to allow Google AdSense while blocking malicious content.
    """
    directives = [
        # Default: block everything not explicitly allowed
        "default-src 'self'",

        # Scripts: self, Google AdSense, Google Analytics, MediaPipe CDN, and inline for essential functionality
        # 'wasm-unsafe-eval' required for WebAssembly (MediaPipe pose detection)
        "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://pagead2.googlesyndication.com https://ep1.adtrafficquality.google https://ep2.adtrafficquality.google https://www.googletagservices.com https://adservice.google.com https://www.google-analytics.com https://www.googletagmanager.com https://cdn.jsdelivr.net",

        # Styles: self and inline (needed for dynamic styling)
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",

        # Images: self, data URIs (for screenshots), and Google ad images
        "img-src 'self' data: blob: https://pagead2.googlesyndication.com https://ep1.adtrafficquality.google https://ep2.adtrafficquality.google https://www.google.com https://www.google-analytics.com https://*.googleusercontent.com",

        # Fonts: self and Google Fonts
        "font-src 'self' https://fonts.gstatic.com",

        # Connect: self, WebSocket, analytics, and MediaPipe model files
        "connect-src 'self' ws: wss: https://pagead2.googlesyndication.com https://ep1.adtrafficquality.google https://ep2.adtrafficquality.google https://www.google-analytics.com https://cdn.jsdelivr.net https://storage.googleapis.com",

        # Frames: Google ads only
        "frame-src https://googleads.g.doubleclick.net https://tpc.googlesyndication.com https://www.google.com https://ep1.adtrafficquality.google https://ep2.adtrafficquality.google",

        # Media: self and blob (for webcam)
        "media-src 'self' blob:",

        # Object/embed: none (block plugins)
        "object-src 'none'",

        # Base URI: self only
        "base-uri 'self'",

        # Form actions: self only
        "form-action 'self'",

        # Frame ancestors: self only (prevents clickjacking)
        "frame-ancestors 'self'",

        # Worker: self and blob (for MediaPipe WASM workers)
        "worker-src 'self' blob:",

        # Upgrade insecure requests in production
        "upgrade-insecure-requests" if cfg.ENVIRONMENT == "production" else "",
    ]

    return "; ".join(d for d in directives if d)


def get_security_headers() -> Dict[str, str]:
    """
    Generate all security headers.
    """
    headers = {
        # Prevent MIME type sniffing
        "X-Content-Type-Options": "nosniff",

        # Prevent clickjacking
        "X-Frame-Options": "SAMEORIGIN",

        # XSS protection (legacy, but still useful)
        "X-XSS-Protection": "1; mode=block",

        # Referrer policy - don't leak sensitive info
        "Referrer-Policy": "strict-origin-when-cross-origin",

        # Permissions policy - restrict browser features
        "Permissions-Policy": "camera=(self), microphone=(), geolocation=(), payment=()",

        # Content Security Policy
        "Content-Security-Policy": get_csp_header(),

        # Cache control for dynamic content
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",

        # Prevent caching of sensitive data
        "Pragma": "no-cache",
    }

    # Add HSTS in production (force HTTPS)
    if cfg.ENVIRONMENT == "production":
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    return headers


# === MIDDLEWARE ===

class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Security middleware that adds headers and enforces rate limiting.
    """

    # Paths that bypass rate limiting (for static assets)
    BYPASS_PATHS = {"/static/", "/health", "/yoga/remote", "/ws/yoga/"}

    # Maximum request body size (1MB - sufficient for JSON requests)
    MAX_BODY_SIZE = 1 * 1024 * 1024

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip rate limiting for static assets
        skip_rate_limit = any(path.startswith(p) for p in self.BYPASS_PATHS)

        # Rate limiting for non-static requests
        if not skip_rate_limit:
            allowed, reason = rate_limiter.is_allowed(request)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": reason},
                    headers={"Retry-After": "60"}
                )

        # Check content length
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request entity too large"}
            )

        # HTTPS enforcement in production (skip for localhost/local IPs)
        if cfg.ENVIRONMENT == "production":
            host = request.headers.get("host", "").split(":")[0]
            is_local = host in ["localhost", "127.0.0.1", "0.0.0.0"]
            
            forwarded_proto = request.headers.get("x-forwarded-proto", "http")
            if forwarded_proto != "https" and path not in ["/health"] and not is_local:
                # Redirect to HTTPS
                https_url = str(request.url).replace("http://", "https://", 1)
                return Response(
                    status_code=301,
                    headers={"Location": https_url}
                )

        # Process request
        response = await call_next(request)

        # Add security headers to all responses
        security_headers = get_security_headers()
        for header, value in security_headers.items():
            response.headers[header] = value

        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """
    Validates incoming requests for common attack patterns.
    """

    # Suspicious patterns that might indicate attacks
    SUSPICIOUS_PATTERNS = [
        "<script",
        "javascript:",
        "onerror=",
        "onclick=",
        "onload=",
        "eval(",
        "document.cookie",
        "window.location",
        "../",  # Path traversal
        "..\\",  # Windows path traversal
        "%2e%2e",  # URL-encoded path traversal
        "' OR ",  # SQL injection
        "\" OR ",  # SQL injection
        "; DROP ",  # SQL injection
        "UNION SELECT",  # SQL injection
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check URL path for suspicious patterns
        path = request.url.path.lower()
        query = str(request.url.query).lower()

        for pattern in self.SUSPICIOUS_PATTERNS:
            if pattern.lower() in path or pattern.lower() in query:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid request"}
                )

        # Check User-Agent for common attack tools
        user_agent = request.headers.get("user-agent", "").lower()
        blocked_agents = ["sqlmap", "nikto", "nessus", "acunetix", "nmap"]
        if any(agent in user_agent for agent in blocked_agents):
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden"}
            )

        return await call_next(request)
