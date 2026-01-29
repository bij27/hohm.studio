"""
Device Token Authentication for hohm.studio

Implements anonymous device-based authentication:
- Each device gets a unique token stored in localStorage
- Sessions are tied to device tokens for isolation
- No accounts or personal data required
"""

import secrets
import re
from typing import Optional, Tuple
from fastapi import Request, HTTPException

# Token format: 64 character hex string (256 bits of entropy)
TOKEN_LENGTH = 64
TOKEN_PATTERN = re.compile(r'^[a-f0-9]{64}$')

# Header name for device token
TOKEN_HEADER = "X-Device-Token"


def generate_device_token() -> str:
    """Generate a cryptographically secure device token."""
    return secrets.token_hex(32)  # 32 bytes = 64 hex chars


def validate_token_format(token: str) -> bool:
    """Check if token matches expected format."""
    if not token or not isinstance(token, str):
        return False
    return bool(TOKEN_PATTERN.match(token))


def extract_device_token(request: Request) -> Optional[str]:
    """
    Extract device token from request headers.
    Returns None if no valid token found.
    """
    token = request.headers.get(TOKEN_HEADER)

    if token and validate_token_format(token):
        return token

    return None


def require_device_token(request: Request) -> str:
    """
    Extract and validate device token from request.
    Raises HTTPException if token is missing or invalid.
    """
    token = extract_device_token(request)

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )

    return token


def get_device_token_or_none(request: Request) -> Optional[str]:
    """
    Extract device token if present, return None otherwise.
    Use this for endpoints that work with or without authentication.
    """
    return extract_device_token(request)
