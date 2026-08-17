"""API utilities and dependencies.

This package contains shared API utilities:
- deps: FastAPI dependency injection functions
"""

from .deps import (
    get_api_key,
    get_client_ip,
    sanitize_error_message,
    validate_and_rate_limit,
)

__all__ = [
    "get_api_key",
    "get_client_ip",
    "validate_and_rate_limit",
    "sanitize_error_message",
]
