"""Request validation for the self-hosted MCP transport."""

from ..auth import (
    get_effective_plan,
    get_project_with_team,
    validate_api_key,
    validate_local_api_key,
)
from ..config import settings
from ..models import Plan
from ..usage import (
    check_plan_ip_rate_limit,
    check_rate_limit,
    check_usage_limits,
    is_scan_blocked,
    log_security_event,
)


async def validate_request(
    project_id_or_slug: str, api_key: str, client_ip: str | None = None
) -> tuple[dict | None, Plan, str | None, str | None]:
    """Validate authentication and check usage limits.

    Supports a local operator key and a compatibility database API key.

    Args:
        project_id_or_slug: Project ID or slug from URL
        api_key: local operator key or compatibility database key
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

    # A configured local key is the OSS authentication boundary.
    if settings.snipara_local_api_key.strip():
        auth_info = await validate_local_api_key(api_key, project_id_or_slug)
        if not auth_info:
            return None, Plan.FREE, "Invalid local API key.", None
    else:
        # Compatibility path for an existing private installation. New OSS
        # installs should configure SNIPARA_LOCAL_API_KEY.
        auth_info = await validate_api_key(api_key, project_id_or_slug)
        if not auth_info:
            return (
                None,
                Plan.FREE,
                "Invalid API key.",
                None,
            )

    project = await get_project_with_team(project_id_or_slug)
    if not project:
        return None, Plan.FREE, "Project not found", None

    # Use actual database ID for all operations
    actual_project_id = project.id
    auth_info["project_id"] = actual_project_id
    auth_info["project"] = auth_info.get("project") or project
    auth_info["team_id"] = getattr(project, "teamId", None)

    # Local operator mode is unrestricted by commercial plan entitlements.
    plan = (
        Plan.ENTERPRISE
        if auth_info.get("auth_type") == "local"
        else get_effective_plan(project.team.subscription if project.team else None)
    )

    rate_limit_plan = plan.value

    # Check rate limit with plan-based limits
    if not await check_rate_limit(auth_info["id"], client_ip=client_ip, plan=rate_limit_plan):
        max_requests = settings.plan_rate_limits.get(rate_limit_plan, settings.rate_limit_requests)
        log_security_event(
            "rate_limit.exceeded",
            "api_key",
            auth_info["id"],
            auth_info.get("user_id", auth_info["id"]),
        )
        return None, plan, f"Rate limit exceeded: {max_requests}/min", None

    if not await check_plan_ip_rate_limit(client_ip, rate_limit_plan):
        log_security_event(
            "rate_limit.ip_exceeded",
            "ip",
            client_ip or "unknown",
            auth_info.get("user_id", auth_info["id"]),
            team_id=getattr(project, "teamId", None),
            details={"plan": rate_limit_plan, "api_key_id": auth_info["id"]},
            ip_address=client_ip,
        )
        return (
            None,
            plan,
            f"IP rate limit exceeded: {settings.ip_rate_limit_requests} requests per minute",
            None,
        )

    limits = await check_usage_limits(actual_project_id, plan)
    if limits.exceeded:
        return None, plan, f"Monthly limit exceeded: {limits.current}/{limits.max}", None

    return auth_info, plan, None, actual_project_id
