"""Shared debug logging utility."""

import config as cfg


def debug_log(message: str):
    """Print debug message only in development environment."""
    if cfg.ENVIRONMENT == "development":
        print(message)
