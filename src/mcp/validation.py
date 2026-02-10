"""Request validation for MCP transport.

This module handles authentication validation and usage limit checks
for MCP requests. Supports both API keys and OAuth tokens.
"""

from ..auth import get_effective_plan, get_project_with_team, validate_api_key, validate_oauth_token
from ..config import settings
from ..models import Plan
from ..usage import (
    check_rate_limit,
    check_usage_limits,
    is_scan_blocked,
    log_security_event,
)


async def validate_request(
    project_id_or_slug: str, api_key: str, client_ip: str | None = None
) -> tuple[dict | None, Plan, str | None, str | None]:
    """Validate authentication and check usage limits.

    Supports both API keys (rlm_...) and OAuth tokens (snipara_at_...).

    Args:
        project_id_or_slug: Project ID or slug from URL
        api_key: API key or OAuth token from header
        client_ip: Optional client IP for rate limiting

    Returns:
        Tuple of (auth_info, plan, error_message, actual_project_id)
        - auth_info: Dict with API key info if valid, None otherwise
        - plan: Subscription plan (FREE, PRO, TEAM, ENTERPRISE)
        - error_message: Error string if validation failed, None if success
        - actual_project_id: Database ID (not slug) for operations
    """
    # Anti-scan check
    key_prefix = api_key[:12]
    if await is_scan_blocked(key_prefix):
        log_security_event("scan.blocked", "api_key", key_prefix, key_prefix)
        return None, Plan.FREE, "Too many failed requests. Try again later.", None

    auth_info = None

    # Check if it's an OAuth token
    if api_key.startswith("snipara_at_"):
        auth_info = await validate_oauth_token(api_key, project_id_or_slug)
        if not auth_info:
            return (
                None,
                Plan.FREE,
                "Invalid or expired OAuth token. Re-authenticate at https://snipara.com/dashboard or run /snipara:quickstart",
                None,
            )
    else:
        # Fall back to API key validation
        auth_info = await validate_api_key(api_key, project_id_or_slug)
        if not auth_info:
            return (
                None,
                Plan.FREE,
                "Invalid API key. Get a free key at https://snipara.com/dashboard (100 queries/month, no credit card)",
                None,
            )

    project = await get_project_with_team(project_id_or_slug)
    if not project:
        return None, Plan.FREE, "Project not found", None

    # Use actual database ID for all operations
    actual_project_id = project.id

    if not await check_rate_limit(auth_info["id"], client_ip=client_ip):
        log_security_event(
            "rate_limit.exceeded",
            "api_key",
            auth_info["id"],
            auth_info.get("user_id", auth_info["id"]),
        )
        return None, Plan.FREE, f"Rate limit exceeded: {settings.rate_limit_requests}/min", None

    plan = get_effective_plan(project.team.subscription if project.team else None)
    limits = await check_usage_limits(actual_project_id, plan)
    if limits.exceeded:
        return None, plan, f"Monthly limit exceeded: {limits.current}/{limits.max}", None

    return auth_info, plan, None, actual_project_id
