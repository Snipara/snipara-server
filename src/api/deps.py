"""FastAPI dependency injection functions.

This module contains shared dependencies for API endpoints:
- API key extraction and validation
- Rate limiting
- Multi-project query execution
- Error sanitization
"""

import asyncio
import logging
import time
from typing import Annotated

from fastapi import Header, HTTPException
from fastapi import Request as FastAPIRequest
from pydantic import ValidationError

from ..auth import (
    check_team_key_project_access,
    get_effective_plan,
    get_project_settings,
    get_project_with_team,
    get_team_by_slug_or_id,
    validate_api_key,
    validate_client_api_key,
    validate_oauth_token,
    validate_team_api_key,
)
from ..config import settings
from ..models import MultiProjectQueryParams, Plan, ToolName
from ..rlm_engine import RLMEngine, count_tokens
from ..usage import (
    check_client_usage_limits,
    check_rate_limit,
    check_usage_limits,
    is_scan_blocked,
    log_security_event,
    record_access_denial,
    track_usage,
)

logger = logging.getLogger(__name__)


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
    x_api_key: Annotated[str, Header(alias="X-API-Key")],
) -> str:
    """Extract API key from header."""
    return x_api_key


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
    Validates API key or OAuth token, gets project, checks rate limit, and fetches settings.

    Supports both:
    - OAuth tokens (snipara_at_...)
    - API keys (rlm_...)

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

    # 1. Validate auth (OAuth token or API key)
    auth_info = None

    # Check if it's an OAuth token
    if api_key.startswith("snipara_at_"):
        auth_info = await validate_oauth_token(api_key, project_id)
        if not auth_info:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired OAuth token. Re-authenticate at https://snipara.com/dashboard or run /snipara:quickstart",
            )
    # Check if it's an integrator client key
    elif api_key.startswith("snipara_ic_"):
        auth_info = await validate_client_api_key(api_key, project_id)
        if not auth_info:
            raise HTTPException(
                status_code=401,
                detail="Invalid client API key. Contact your integrator for access.",
            )
    else:
        # Fall back to API key validation
        auth_info = await validate_api_key(api_key, project_id)
        if not auth_info:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key. Get a free key at https://snipara.com/dashboard (100 queries/month, no credit card)",
            )

    # 2. Check for access denial (team keys with NONE access level)
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

    # 3. Get project with team subscription
    project = await get_project_with_team(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 4. Determine plan BEFORE rate limit check (plan-based limits)
    plan = get_effective_plan(project.team.subscription if project.team else None)

    # 4.5 Use PARTNER rate limits for integrator clients (higher limits for heavy polling)
    rate_limit_plan = plan.value
    if auth_info.get("auth_type") == "integrator_client":
        rate_limit_plan = "PARTNER"

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

    # 5.5 Check bundle limits for integrator clients
    if auth_info.get("auth_type") == "integrator_client":
        client_id = auth_info.get("client_id")
        client_bundle = auth_info.get("client_bundle", "LITE")
        if client_id:
            bundle_limits = await check_client_usage_limits(client_id, client_bundle)
            if bundle_limits.exceeded:
                log_security_event(
                    "bundle_limit.exceeded",
                    "client",
                    client_id,
                    auth_info.get("user_id", auth_info["id"]),
                    details={"bundle": client_bundle, "current": bundle_limits.current, "max": bundle_limits.max},
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Monthly query limit exceeded for {client_bundle} bundle: {bundle_limits.current}/{bundle_limits.max}. Contact your provider to upgrade.",
                )

    # 6. Get project automation settings (from dashboard)
    project_settings = await get_project_settings(project_id)

    return auth_info, project, plan, project_settings


async def validate_team_and_rate_limit(
    team_slug_or_id: str,
    api_key: str,
    client_ip: str | None = None,
) -> tuple[dict, any, Plan]:
    """
    Validate team API key, resolve team, and check rate limits.

    Returns:
        Tuple of (api_key_info, team, plan)
    """
    # Anti-scan check
    key_prefix = api_key[:12]
    if await is_scan_blocked(key_prefix):
        log_security_event("scan.blocked", "api_key", key_prefix, key_prefix)
        raise HTTPException(status_code=429, detail="Too many failed requests. Try again later.")

    team = await get_team_by_slug_or_id(team_slug_or_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    api_key_info = await validate_team_api_key(api_key, team.id)
    if not api_key_info:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Determine plan BEFORE rate limit check (plan-based limits)
    plan = get_effective_plan(team.subscription)

    # Check rate limit with plan-based limits
    rate_ok = await check_rate_limit(api_key_info["id"], client_ip=client_ip, plan=plan.value)
    if not rate_ok:
        max_requests = settings.plan_rate_limits.get(plan.value, settings.rate_limit_requests)
        log_security_event(
            "rate_limit.exceeded",
            "api_key",
            api_key_info["id"],
            api_key_info.get("user_id", api_key_info["id"]),
            team_id=team.id,
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {max_requests} requests per minute",
        )

    return api_key_info, team, plan


# ============ MULTI-PROJECT QUERY ============


async def execute_multi_project_query(
    team: any,
    plan: Plan,
    params: dict,
    user_id: str | None = None,
) -> tuple[dict, int, int]:
    """
    Execute a multi-project query for a team.

    Args:
        team: Team object with projects
        plan: Subscription plan
        params: Query parameters
        user_id: Optional user ID for per-project ACL checks

    Returns:
        Tuple of (result_payload, total_input_tokens, total_output_tokens)
    """
    try:
        parsed = MultiProjectQueryParams.model_validate(params)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    projects = list(team.projects or [])
    include_ids = set(parsed.project_ids)
    exclude_ids = set(parsed.exclude_project_ids)

    if include_ids:
        projects = [
            project
            for project in projects
            if project.id in include_ids or project.slug in include_ids
        ]

    if exclude_ids:
        projects = [
            project
            for project in projects
            if project.id not in exclude_ids and project.slug not in exclude_ids
        ]

    if not projects:
        empty_result = {
            "query": parsed.query,
            "max_tokens": parsed.max_tokens,
            "per_project_limit": parsed.per_project_limit,
            "search_mode": parsed.search_mode.value,
            "projects_queried": 0,
            "projects_skipped": 0,
            "results": [],
        }
        return empty_result, count_tokens(parsed.query), 0

    per_project_budget = max(1, parsed.max_tokens // len(projects))

    async def execute_project(project: any) -> dict:
        # Per-project ACL check (when user_id is available)
        project_access_level = "EDITOR"
        if user_id:
            try:
                access_level_result, _ = await check_team_key_project_access(
                    user_id, project.id, team.id
                )
                if access_level_result == "NONE":
                    log_security_event(
                        "multi_project.access_denied",
                        "project",
                        project.id,
                        user_id,
                        team_id=team.id,
                        details={"project_slug": project.slug},
                    )
                    return {
                        "project_id": project.id,
                        "project_slug": project.slug,
                        "success": False,
                        "skipped": True,
                        "error": "Access denied to this project",
                        "input_tokens": 0,
                        "output_tokens": 0,
                    }
                project_access_level = access_level_result
            except Exception as e:
                logger.debug(f"ACL check failed for {project.slug}, defaulting to EDITOR: {e}")

        limits = await check_usage_limits(project.id, plan)
        if limits.exceeded:
            return {
                "project_id": project.id,
                "project_slug": project.slug,
                "success": False,
                "skipped": True,
                "error": f"Monthly usage limit exceeded: {limits.current}/{limits.max}",
                "input_tokens": 0,
                "output_tokens": 0,
            }

        project_settings = await get_project_settings(project.id)
        tool_params = {
            "query": parsed.query,
            "max_tokens": per_project_budget,
            "search_mode": parsed.search_mode.value,
            "include_metadata": parsed.include_metadata,
            "prefer_summaries": parsed.prefer_summaries,
        }

        start_time = time.perf_counter()

        try:
            engine = RLMEngine(
                project.id,
                plan=plan,
                settings=project_settings,
                user_id=user_id,
                access_level=project_access_level,
            )
            result = await engine.execute(ToolName.RLM_CONTEXT_QUERY, tool_params)

            latency_ms = int((time.perf_counter() - start_time) * 1000)
            await track_usage(
                project_id=project.id,
                tool=ToolName.RLM_MULTI_PROJECT_QUERY.value,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_ms=latency_ms,
                success=True,
            )

            result_data = result.data
            if isinstance(result_data, dict) and "sections" in result_data:
                result_data["sections"] = result_data["sections"][: parsed.per_project_limit]

            return {
                "project_id": project.id,
                "project_slug": project.slug,
                "success": True,
                "skipped": False,
                "result": result_data,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            }
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            await track_usage(
                project_id=project.id,
                tool=ToolName.RLM_MULTI_PROJECT_QUERY.value,
                input_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
                success=False,
                error=str(e),
            )
            return {
                "project_id": project.id,
                "project_slug": project.slug,
                "success": False,
                "skipped": False,
                "error": sanitize_error_message(e),
                "input_tokens": 0,
                "output_tokens": 0,
            }

    results = await asyncio.gather(*[execute_project(project) for project in projects])

    total_input_tokens = sum(item["input_tokens"] for item in results)
    total_output_tokens = sum(item["output_tokens"] for item in results)
    projects_queried = sum(1 for item in results if item["success"])
    projects_skipped = sum(1 for item in results if item.get("skipped"))

    payload = {
        "query": parsed.query,
        "max_tokens": parsed.max_tokens,
        "per_project_limit": parsed.per_project_limit,
        "search_mode": parsed.search_mode.value,
        "projects_queried": projects_queried,
        "projects_skipped": projects_skipped,
        "results": [
            {k: v for k, v in item.items() if k not in {"input_tokens", "output_tokens"}}
            for item in results
        ],
    }

    return payload, total_input_tokens, total_output_tokens
