"""FastAPI dependency injection functions.

This module contains shared dependencies for API endpoints:
- API key extraction and validation
- Rate limiting
- Error sanitization
"""

import logging
from typing import Annotated

from fastapi import Header, HTTPException
from fastapi import Request as FastAPIRequest

from ..auth import (
    get_effective_plan,
    get_project_settings,
    get_project_with_team,
    validate_api_key,
    validate_local_api_key,
)
from ..config import settings
from ..models import Plan
from ..usage import (
    check_auth_failure_rate_limit,
    check_plan_ip_rate_limit,
    check_rate_limit,
    is_scan_blocked,
    log_security_event,
    record_access_denial,
)

logger = logging.getLogger(__name__)


async def _reject_failed_auth(
    *,
    client_ip: str | None,
    key_prefix: str,
    detail: str,
) -> None:
    allowed = await check_auth_failure_rate_limit(client_ip, key_prefix)
    log_security_event(
        "auth.failed",
        "api_key",
        key_prefix,
        key_prefix,
        details={"rate_limited": not allowed},
        ip_address=client_ip,
    )

    if not allowed:
        raise HTTPException(status_code=429, detail="Too many failed authentication attempts.")

    raise HTTPException(status_code=401, detail=detail)


async def _enforce_authenticated_ip_rate_limit(
    *,
    auth_info: dict,
    client_ip: str | None,
    rate_limit_plan: str,
    team_id: str | None = None,
) -> None:
    """Apply aggregate IP throttling only after auth, and only for configured plans."""
    if await check_plan_ip_rate_limit(client_ip, rate_limit_plan):
        return

    actor_id = auth_info.get("user_id", auth_info["id"])
    log_security_event(
        "rate_limit.ip_exceeded",
        "ip",
        client_ip or "unknown",
        actor_id,
        team_id=team_id,
        details={"plan": rate_limit_plan, "api_key_id": auth_info["id"]},
        ip_address=client_ip,
    )
    raise HTTPException(
        status_code=429,
        detail=f"IP rate limit exceeded: {settings.ip_rate_limit_requests} requests per minute",
    )


# ============ ERROR SANITIZATION ============


def sanitize_error_message(error: Exception) -> str:
    """
    Sanitize error messages to prevent information disclosure.

    Returns a generic message for unexpected errors while preserving
    useful information for known error types.
    """
    error_str = str(error)

    # Known safe error patterns that can be returned to client
    safe_patterns = [
        "Invalid API key",
        "Project not found",
        "Rate limit exceeded",
        "Monthly usage limit exceeded",
        "requires context scope",
        "requires memory scope",
        "Invalid tool name",
        "Invalid regex pattern",
        "No documentation loaded",
        "Unknown tool",
        "Invalid parameter",
        "Token budget",
        "Plan does not support",
    ]

    for pattern in safe_patterns:
        if pattern.lower() in error_str.lower():
            return error_str

    # Log the actual error for debugging
    logger.error(f"Tool execution error: {error}", exc_info=True)

    # Return generic message for unknown errors
    return "An error occurred processing your request. Please try again."


# ============ HEADER EXTRACTORS ============


async def get_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Extract auth credentials from X-API-Key or Authorization."""
    if x_api_key:
        return x_api_key
    if authorization:
        return authorization[7:] if authorization.startswith("Bearer ") else authorization
    raise HTTPException(status_code=401, detail="Authentication required")


def get_client_ip(request: FastAPIRequest) -> str | None:
    """Extract client IP from X-Forwarded-For header or direct connection."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


# ============ VALIDATION DEPENDENCIES ============


async def validate_and_rate_limit(
    project_id: str,
    api_key: str,
    client_ip: str | None = None,
) -> tuple[dict, any, Plan, dict | None]:
    """
    Common validation logic for all endpoints.
    Validates the local operator key (or a legacy database key when the local
    key is not configured), gets the project, checks rate limits, and fetches
    settings.

    Returns:
        Tuple of (auth_info, project, plan, project_settings)

    Raises:
        HTTPException on validation failure
    """
    # 0. Anti-scan: check if this key prefix is blocked
    key_prefix = api_key[:12]
    if await is_scan_blocked(key_prefix):
        log_security_event("scan.blocked", "api_key", key_prefix, key_prefix)
        raise HTTPException(status_code=429, detail="Too many failed requests. Try again later.")

    # 1. Validate the local API key (or a project-bound compatibility key)
    auth_info = None

    # A configured local key is the OSS authentication boundary. The OSS
    # runtime has no hosted identity or integrator state.
    if settings.snipara_local_api_key.strip():
        auth_info = await validate_local_api_key(api_key, project_id)
        if not auth_info:
            await _reject_failed_auth(
                client_ip=client_ip,
                key_prefix=key_prefix,
                detail="Invalid local API key.",
            )
    else:
        # Temporary compatibility path for an existing private installation.
        # New OSS installs should always set SNIPARA_LOCAL_API_KEY.
        auth_info = await validate_api_key(api_key, project_id)
        if not auth_info:
            await _reject_failed_auth(
                client_ip=client_ip,
                key_prefix=key_prefix,
                detail="Invalid API key.",
            )

    # 2. Check for a denied compatibility key.
    if auth_info.get("access_denied"):
        await record_access_denial(key_prefix, project_id)
        log_security_event(
            "access.denied",
            "project",
            project_id,
            auth_info.get("id", key_prefix),
            details={"reason": "team_key_no_access"},
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied to this project. Use rlm_request_access tool to request access.",
        )

    # 3. Resolve the local workspace project.
    project = await get_project_with_team(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 4. Local operator mode is unrestricted by commercial plan entitlements.
    # Keep the enterprise enum internally so existing engine capability checks
    # remain useful without introducing a license or billing subsystem.
    plan = (
        Plan.ENTERPRISE
        if auth_info.get("auth_type") == "local"
        else get_effective_plan(project.team.subscription if project.team else None)
    )

    rate_limit_plan = plan.value

    # 5. Check rate limit with plan-based limits
    rate_ok = await check_rate_limit(auth_info["id"], client_ip=client_ip, plan=rate_limit_plan)
    if not rate_ok:
        max_requests = settings.plan_rate_limits.get(rate_limit_plan, settings.rate_limit_requests)
        log_security_event(
            "rate_limit.exceeded",
            "api_key",
            auth_info["id"],
            auth_info.get("user_id", auth_info["id"]),
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {max_requests} requests per minute",
        )

    await _enforce_authenticated_ip_rate_limit(
        auth_info=auth_info,
        client_ip=client_ip,
        rate_limit_plan=rate_limit_plan,
        team_id=getattr(project, "teamId", None),
    )

    # 6. Get project automation settings (from dashboard)
    project_settings = await get_project_settings(project_id)

    return auth_info, project, plan, project_settings
