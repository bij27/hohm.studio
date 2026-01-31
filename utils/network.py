"""Network utility functions."""

from typing import Union
from fastapi import Request, WebSocket


def get_client_ip(connection: Union[Request, WebSocket]) -> str:
    """Extract client IP from Request or WebSocket connection.

    Handles proxy headers (X-Forwarded-For, X-Real-IP) for deployments
    behind load balancers or reverse proxies.
    """
    forwarded = connection.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = connection.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if connection.client:
        return connection.client.host
    return "unknown"
