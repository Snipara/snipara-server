"""API utilities and dependencies.

This package contains shared API utilities:
- deps: FastAPI dependency injection functions
"""

from .deps import (
    execute_multi_project_query,
    get_api_key,
    get_client_ip,
    sanitize_error_message,
    validate_and_rate_limit,
    validate_team_and_rate_limit,
)

__all__ = [
    "get_api_key",
    "get_client_ip",
    "validate_and_rate_limit",
    "validate_team_and_rate_limit",
    "execute_multi_project_query",
    "sanitize_error_message",
]
