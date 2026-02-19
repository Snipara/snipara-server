"""FastAPI MCP Server for RLM SaaS."""

import json
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from . import __version__
from .api.deps import (
    execute_multi_project_query,
    get_api_key,
    get_client_ip,
    sanitize_error_message,
    validate_and_rate_limit,
    validate_team_and_rate_limit,
)
from .auth import (
    get_effective_plan,
    get_team_by_slug_or_id,
    validate_team_api_key,
)
from .config import settings
from .db import close_db, get_db
from .mcp import jsonrpc_error, jsonrpc_response
from .mcp_transport import router as mcp_router
from .middleware import IPRateLimitMiddleware, SecurityHeadersMiddleware
from .models import (
    HealthResponse,
    LimitsInfo,
    MCPRequest,
    MCPResponse,
    Plan,
    ReadyResponse,
    ToolName,
    UsageInfo,
)
from .rlm_engine import RLMEngine
from .services.agent_memory import semantic_recall, store_memory
from .usage import (
    _is_demo_key,
    check_rate_limit,
    check_usage_limits,
    close_redis,
    get_demo_analytics,
    get_usage_stats,
    log_security_event,
    track_demo_query,
    track_usage,
)

logger = logging.getLogger(__name__)

# ============ SENTRY INITIALIZATION ============


def _filter_sentry_event(event: dict) -> dict:
    """Remove sensitive data from Sentry events."""
    if "request" in event and "headers" in event["request"]:
        headers = event["request"]["headers"]
        for key in ["authorization", "x-api-key"]:
            if key in headers:
                headers[key] = "[REDACTED]"
    return event


# Initialize Sentry if DSN is configured
if settings.sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=0.1 if settings.environment == "production" else 1.0,
            integrations=[
                FastApiIntegration(),
                StarletteIntegration(),
            ],
            before_send=lambda event, hint: _filter_sentry_event(event),
        )
        logger.info("Sentry error tracking initialized")
    except ImportError:
        logger.warning("Sentry DSN configured but sentry-sdk not installed")
else:
    logger.debug("Sentry DSN not configured - error tracking disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info(f"Starting RLM MCP Server v{__version__}")

    # Validate CORS configuration in production
    if not settings.debug and settings.cors_allowed_origins == "*":
        logger.warning(
            "SECURITY WARNING: CORS is configured to allow all origins ('*'). "
            "Set CORS_ALLOWED_ORIGINS to specific domains in production."
        )

    await get_db()  # Initialize database connection

    # Pre-load embedding models to avoid cold-start blocking workers
    # Primary (bge-large) for pgvector + Light (bge-small) for on-the-fly fallback
    from .services.embeddings import EmbeddingsService

    try:
        EmbeddingsService.preload_all()
    except Exception as e:
        logger.warning(f"Embedding model preload failed (will retry on first use): {e}")

    # Start background job processor for async indexing
    from .services.background_jobs import start_job_processor, stop_job_processor

    await start_job_processor()

    yield
    # Shutdown
    await stop_job_processor()
    await close_db()
    await close_redis()


app = FastAPI(
    title="RLM MCP Server",
    description="Hosted MCP endpoint for RLM SaaS - Context-efficient documentation queries",
    version=__version__,
    lifespan=lifespan,
)

# IP-based rate limiting middleware (applied before other middleware)
app.add_middleware(IPRateLimitMiddleware)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware - use configured origins instead of wildcard
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# Mount MCP Streamable HTTP transport
app.include_router(mcp_router)


# ============ EXCEPTION HANDLERS ============


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent response format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "usage": {"latency_ms": 0},
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions with sanitized error messages."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "An internal server error occurred. Please try again.",
            "usage": {"latency_ms": 0},
        },
    )


# ============ HEALTH ENDPOINTS ============


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Health check endpoint (lightweight liveness check)."""
    return HealthResponse(
        status="healthy",
        version=__version__,
        timestamp=datetime.utcnow(),
    )


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Readiness check - verifies DB and embedding model are operational."""
    from .services.embeddings import EmbeddingsService

    checks: dict[str, bool] = {}
    all_ok = True

    # Check database connectivity
    try:
        db = await get_db()
        await db.query_raw("SELECT 1")
        checks["database"] = True
    except Exception:
        checks["database"] = False
        all_ok = False

    # Check embedding model is loaded
    checks["embedding_model"] = EmbeddingsService.get_instance().is_loaded()
    if not checks["embedding_model"]:
        all_ok = False

    response = ReadyResponse(
        status="ready" if all_ok else "not_ready",
        version=__version__,
        checks=checks,
    )
    return JSONResponse(
        content=response.model_dump(mode="json"),
        status_code=200 if all_ok else 503,
    )


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint with API info."""
    return {
        "name": "RLM MCP Server",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


# ============ MCP ENDPOINTS ============


@app.post("/v1/{project_id}/mcp", response_model=MCPResponse, tags=["MCP"])
async def mcp_endpoint(
    project_id: str,
    request: MCPRequest,
    api_key: Annotated[str, Depends(get_api_key)],
    raw_request: Request,
) -> MCPResponse:
    """
    Execute an RLM MCP tool.

    This endpoint validates the API key, checks usage limits,
    executes the requested tool, and tracks usage.

    Args:
        project_id: The project ID
        request: The MCP request with tool and parameters
        api_key: API key from X-API-Key header
        raw_request: The raw FastAPI request (for client IP)

    Returns:
        MCPResponse with result or error
    """
    start_time = time.perf_counter()

    # Validate API key, project, rate limit, and get settings
    client_ip = get_client_ip(raw_request)
    api_key_info, project, plan, project_settings = await validate_and_rate_limit(
        project_id, api_key, client_ip=client_ip
    )

    # Track demo queries for analytics (fire-and-forget)
    if _is_demo_key(api_key_info.get("id", "")):
        await track_demo_query(client_ip, request.tool.value)

    # Check usage limits
    limits = await check_usage_limits(project.id, plan)
    if limits.exceeded:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly usage limit exceeded: {limits.current}/{limits.max} queries. Upgrade your plan to continue.",
        )

    # Execute the tool with project settings from dashboard
    try:
        engine = RLMEngine(
            project.id,
            plan=plan,
            settings=project_settings,
            user_id=api_key_info.get("user_id"),
            access_level=api_key_info.get("access_level", "EDITOR"),
        )
        result = await engine.execute(request.tool, request.params)

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Track usage
        await track_usage(
            project_id=project.id,
            tool=request.tool.value,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
            success=True,
        )

        return MCPResponse(
            success=True,
            result=result.data,
            usage=UsageInfo(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_ms=latency_ms,
            ),
        )

    except Exception as e:
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Track failed request (log full error internally)
        await track_usage(
            project_id=project.id,
            tool=request.tool.value,
            input_tokens=0,
            output_tokens=0,
            latency_ms=latency_ms,
            success=False,
            error=str(e),  # Full error for internal logging
        )

        # Return sanitized error to client
        return MCPResponse(
            success=False,
            error=sanitize_error_message(e),
            usage=UsageInfo(latency_ms=latency_ms),
        )


@app.post("/v1/team/{team_slug}/mcp", response_model=MCPResponse, tags=["MCP"])
async def team_mcp_endpoint(
    team_slug: str,
    request: MCPRequest,
    api_key: Annotated[str, Depends(get_api_key)],
) -> MCPResponse:
    """
    Execute team-scoped MCP tools.

    This endpoint only allows rlm_multi_project_query with a team API key.
    """
    start_time = time.perf_counter()

    api_key_info, team, plan = await validate_team_and_rate_limit(team_slug, api_key)

    if request.tool != ToolName.RLM_MULTI_PROJECT_QUERY:
        raise HTTPException(status_code=400, detail="Invalid tool for team API key")

    try:
        result_payload, input_tokens, output_tokens = await execute_multi_project_query(
            team,
            plan,
            request.params,
            user_id=api_key_info.get("user_id"),
        )

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        return MCPResponse(
            success=True,
            result=result_payload,
            usage=UsageInfo(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return MCPResponse(
            success=False,
            error=sanitize_error_message(e),
            usage=UsageInfo(latency_ms=latency_ms),
        )


# ============ TEAM MCP TRANSPORT (JSON-RPC) ============

# Tool definition for team endpoint (only rlm_multi_project_query)
TEAM_TOOL_DEFINITION = {
    "name": "rlm_multi_project_query",
    "description": "Query across all projects in a team. Returns ranked context from multiple documentation sets.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The question to answer"},
            "max_tokens": {
                "type": "integer",
                "default": 16000,
                "description": "Total token budget across all projects",
            },
            "per_project_limit": {
                "type": "integer",
                "default": 10,
                "description": "Max sections per project",
            },
            "project_ids": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": "Filter to specific projects (empty = all)",
            },
            "exclude_project_ids": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": "Projects to exclude",
            },
        },
        "required": ["query"],
    },
}


@app.post("/mcp/team/{team_id}", tags=["MCP Transport"])
async def team_mcp_transport_endpoint(
    team_id: str,
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
):
    """
    Team MCP Streamable HTTP endpoint (JSON-RPC format).

    This endpoint supports the MCP protocol for team-scoped queries.
    Only the rlm_multi_project_query tool is available.

    Config example (Claude Code):
    ```json
    {"mcpServers": {"snipara-team": {"type": "http", "url": "https://api.snipara.com/mcp/team/{team_id}", "headers": {"X-API-Key": "rlm_team_..."}}}}
    ```
    """
    # Accept X-API-Key header (preferred) or Authorization: Bearer
    if x_api_key:
        api_key = x_api_key
    elif authorization:
        api_key = authorization[7:] if authorization.startswith("Bearer ") else authorization
    else:
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing authentication. Get started free (100 queries/month, no credit card):\n"
                "- Claude Code: Run /snipara:quickstart\n"
                "- VS Code: Install 'Snipara' extension and click 'Sign in with GitHub'\n"
                "- Manual: Get an API key at https://snipara.com/dashboard\n"
                "Docs: https://snipara.com/docs/quickstart"
            ),
        )

    # Validate team and API key
    team = await get_team_by_slug_or_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    api_key_info = await validate_team_api_key(api_key, team.id)
    if not api_key_info:
        log_security_event(
            "auth.failed",
            "team",
            team_id,
            api_key[:12],
            team_id=team.id,
            details={"reason": "invalid_team_api_key"},
        )
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Determine plan BEFORE rate limit check (plan-based limits)
    plan = get_effective_plan(team.subscription)

    # Check rate limit with plan-based limits
    if not await check_rate_limit(api_key_info["id"], plan=plan.value):
        max_requests = settings.plan_rate_limits.get(plan.value, settings.rate_limit_requests)
        log_security_event(
            "rate_limit.exceeded",
            "api_key",
            api_key_info["id"],
            api_key_info.get("user_id", api_key_info["id"]),
            team_id=team.id,
        )
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded: {max_requests}/min")

    # Parse JSON-RPC request
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(jsonrpc_error(None, -32700, "Parse error"), status_code=400)

    # Extract user_id for ACL checks
    team_user_id = api_key_info.get("user_id")

    # Handle batch requests
    if isinstance(body, list):
        responses = []
        for req in body:
            resp = await _handle_team_request(req, team, plan, user_id=team_user_id)
            if resp:  # Skip notifications (no id)
                responses.append(resp)
        return JSONResponse(responses)

    # Handle single request
    response = await _handle_team_request(body, team, plan, user_id=team_user_id)
    return JSONResponse(response) if response else Response(status_code=204)


async def _handle_team_request(
    body: dict, team: any, plan: Plan, user_id: str | None = None
) -> dict | None:
    """Handle a single JSON-RPC request for team endpoint."""
    method = body.get("method")
    id = body.get("id")
    params = body.get("params", {})

    if id is None:  # Notification - no response
        return None

    if method == "initialize":
        return jsonrpc_response(
            id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "snipara-team", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        )
    elif method == "tools/list":
        return jsonrpc_response(id, {"tools": [TEAM_TOOL_DEFINITION]})
    elif method == "tools/call":
        return await _handle_team_call_tool(id, params, team, plan, user_id=user_id)
    elif method == "ping":
        return jsonrpc_response(id, {})
    else:
        return jsonrpc_error(id, -32601, f"Method not found: {method}")


async def _handle_team_call_tool(
    id: any, params: dict, team: any, plan: Plan, user_id: str | None = None
) -> dict:
    """Handle MCP tools/call request for team endpoint."""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if tool_name != "rlm_multi_project_query":
        return jsonrpc_error(
            id,
            -32602,
            f"Tool not available on team endpoint: {tool_name}. Only rlm_multi_project_query is supported.",
        )

    try:
        result_payload, input_tokens, output_tokens = await execute_multi_project_query(
            team,
            plan,
            arguments,
            user_id=user_id,
        )

        return jsonrpc_response(
            id,
            {
                "content": [
                    {"type": "text", "text": json.dumps(result_payload, indent=2, default=str)}
                ],
            },
        )
    except HTTPException as e:
        return jsonrpc_error(id, -32000, e.detail)
    except Exception as e:
        return jsonrpc_error(id, -32000, str(e))


@app.get("/v1/{project_id}/context", tags=["MCP"])
async def get_context(
    project_id: str,
    api_key: Annotated[str, Depends(get_api_key)],
):
    """
    Get the current session context for a project.

    Args:
        project_id: The project ID
        api_key: API key from X-API-Key header

    Returns:
        Current session context
    """
    # Validate API key, project, and rate limit
    api_key_info, project, _, _ = await validate_and_rate_limit(project_id, api_key)

    engine = RLMEngine(
        project.id,
        user_id=api_key_info.get("user_id"),
        access_level=api_key_info.get("access_level", "EDITOR"),
    )
    await engine.load_session_context()

    return {
        "project_id": project.id,
        "context": engine.session_context,
        "has_context": bool(engine.session_context),
    }


@app.get("/v1/{project_id}/limits", response_model=LimitsInfo, tags=["MCP"])
async def get_limits(
    project_id: str,
    api_key: Annotated[str, Depends(get_api_key)],
) -> LimitsInfo:
    """
    Get current usage limits for a project.

    Args:
        project_id: The project ID
        api_key: API key from X-API-Key header

    Returns:
        Current usage and limits
    """
    # Validate API key, project, and rate limit
    _, _, plan, _ = await validate_and_rate_limit(project_id, api_key)

    return await check_usage_limits(project_id, plan)


@app.get("/v1/{project_id}/stats", tags=["MCP"])
async def get_stats(
    project_id: str,
    api_key: Annotated[str, Depends(get_api_key)],
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
):
    """
    Get usage statistics for a project.

    Args:
        project_id: The project ID
        api_key: API key from X-API-Key header
        days: Number of days to look back (default: 30, max: 365)

    Returns:
        Usage statistics
    """
    # Validate API key, project, and rate limit
    _, _, _, _ = await validate_and_rate_limit(project_id, api_key)

    stats = await get_usage_stats(project_id, days)
    return {"project_id": project_id, **stats}


@app.get("/v1/admin/demo-analytics", tags=["Admin"])
async def demo_analytics(
    x_internal_secret: Annotated[str | None, Header(alias="X-Internal-Secret")] = None,
):
    """
    Get demo usage analytics (internal endpoint).

    Tracks unique IPs, query counts, tool usage breakdown, and daily trends
    for queries made with the demo API key.

    Requires X-Internal-Secret header for authentication.

    Returns:
        Demo analytics data including:
        - unique_ips: Total unique IP addresses
        - total_queries: Total demo queries
        - today_unique_ips: Unique IPs today
        - tools_breakdown: Queries by tool type
        - daily_stats: Daily query counts (last 7 days)
        - top_users: Top 10 IPs by query count (masked for privacy)
    """
    # Require internal secret
    if not settings.internal_api_secret:
        raise HTTPException(status_code=500, detail="Internal API secret not configured")
    if not x_internal_secret or x_internal_secret != settings.internal_api_secret:
        raise HTTPException(status_code=401, detail="Invalid or missing internal secret")

    analytics = await get_demo_analytics()
    return {"success": True, "data": analytics}


@app.post("/v1/{project_id}/reindex", tags=["MCP"])
async def reindex_project(
    project_id: str,
    mode: str = Query(
        default="incremental",
        description="Index mode: 'incremental' (only unindexed docs) or 'full' (all docs)",
        pattern="^(incremental|full)$",
    ),
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    x_internal_secret: Annotated[str | None, Header(alias="X-Internal-Secret")] = None,
):
    """
    Trigger async re-indexing of documents in a project.

    This creates an index job that processes documents in the background.
    The endpoint returns immediately with a job ID that can be used to
    check progress via GET /v1/{project_id}/reindex/{job_id}.

    Index modes:
    - incremental (default): Only index documents that don't have chunks yet
    - full: Re-index all documents (deletes existing chunks first)

    Supports two authentication methods:
    1. X-API-Key header (normal API key authentication)
    2. X-Internal-Secret header (server-to-server authentication)

    Args:
        project_id: The project ID or slug
        mode: Index mode - "incremental" or "full"
        x_api_key: API key from X-API-Key header (optional)
        x_internal_secret: Internal secret for server-to-server calls (optional)

    Returns:
        Job info including job_id, status, index_mode, and status_url for polling
    """
    from .services.background_jobs import create_index_job

    db = await get_db()

    # Check authentication - either API key or internal secret
    triggered_via = None
    if x_internal_secret:
        # Internal server-to-server authentication
        if not settings.internal_api_secret:
            raise HTTPException(status_code=500, detail="Internal API secret not configured")
        if x_internal_secret != settings.internal_api_secret:
            raise HTTPException(status_code=401, detail="Invalid internal secret")

        # Look up project directly (no user context needed for internal calls)
        project = await db.project.find_first(where={"id": project_id})
        if not project:
            # Try by slug
            project = await db.project.find_first(where={"slug": project_id})
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        triggered_via = "internal"
    elif x_api_key:
        # Normal API key authentication
        _, project, _, _ = await validate_and_rate_limit(project_id, x_api_key)
        triggered_via = "api_key"
    else:
        raise HTTPException(
            status_code=401, detail="Authentication required: X-API-Key or X-Internal-Secret header"
        )

    # Map mode to IndexJobMode enum value
    index_mode = "FULL" if mode == "full" else "INCREMENTAL"

    # Create index job (returns immediately)
    job = await create_index_job(
        db,
        project.id,
        triggered_by=None,  # Could add user ID if available
        triggered_via=triggered_via,
        index_mode=index_mode,
    )

    logger.info(f"Created index job {job['id']} for project {project.id} (mode={index_mode})")

    return {
        "job_id": job["id"],
        "project_id": project.id,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "index_mode": job.get("index_mode", "INCREMENTAL").lower(),
        "created_at": job.get("created_at"),
        "status_url": f"/v1/{project.id}/reindex/{job['id']}",
        "already_exists": job.get("already_exists", False),
    }


@app.get("/v1/{project_id}/reindex/{job_id}", tags=["MCP"])
async def get_reindex_status(
    project_id: str,
    job_id: str,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    x_internal_secret: Annotated[str | None, Header(alias="X-Internal-Secret")] = None,
):
    """
    Get the status of an indexing job.

    Use this endpoint to poll for job completion after triggering
    a reindex via POST /v1/{project_id}/reindex.

    Args:
        project_id: The project ID or slug
        job_id: The job ID returned from the POST endpoint
        x_api_key: API key from X-API-Key header (optional)
        x_internal_secret: Internal secret for server-to-server calls (optional)

    Returns:
        Job status including progress, documents processed, chunks created, etc.
    """
    from .services.background_jobs import get_job_status

    db = await get_db()

    # Check authentication - either API key or internal secret
    if x_internal_secret:
        if not settings.internal_api_secret:
            raise HTTPException(status_code=500, detail="Internal API secret not configured")
        if x_internal_secret != settings.internal_api_secret:
            raise HTTPException(status_code=401, detail="Invalid internal secret")

        project = await db.project.find_first(where={"id": project_id})
        if not project:
            project = await db.project.find_first(where={"slug": project_id})
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
    elif x_api_key:
        _, project, _, _ = await validate_and_rate_limit(project_id, x_api_key)
    else:
        raise HTTPException(
            status_code=401, detail="Authentication required: X-API-Key or X-Internal-Secret header"
        )

    # Get job status
    job = await get_job_status(db, project.id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


# ============ MEMORY REST API (Automation Hooks) ============


@app.get("/v1/{project_id}/memories/recall", tags=["Memories"])
async def recall_memories(
    project_id: str,
    api_key: Annotated[str, Depends(get_api_key)],
    query: str = Query(..., description="Search query for semantic recall"),
    type: str | None = Query(default=None, description="Filter by memory type"),
    category: str | None = Query(default=None, description="Filter by category"),
    limit: int = Query(default=10, ge=1, le=50, description="Max memories to return"),
    min_relevance: float = Query(default=0.3, ge=0, le=1, description="Minimum relevance"),
):
    """
    Recall memories semantically based on a query.

    Used by SessionStart hooks to inject relevant memories into new sessions.

    Args:
        project_id: The project ID
        query: Search query for semantic matching
        type: Filter by memory type (fact, decision, learning, preference, todo, context)
        category: Filter by category
        limit: Maximum memories to return
        min_relevance: Minimum relevance score (0-1)

    Returns:
        List of relevant memories with content and metadata
    """
    # Validate API key, project, and rate limit
    _, project, _, _ = await validate_and_rate_limit(project_id, api_key)

    # Use resolved project ID, not the slug from URL
    resolved_project_id = project.id

    result = await semantic_recall(
        project_id=resolved_project_id,
        query=query,
        memory_type=type,
        category=category,
        limit=limit,
        min_relevance=min_relevance,
    )

    return {
        "project_id": resolved_project_id,
        "query": query,
        "memories": result.get("memories", []),
        "total_searched": result.get("total_searched", 0),
        "timing_ms": result.get("timing_ms", 0),
    }


@app.post("/v1/{project_id}/memories", tags=["Memories"])
async def create_memory(
    project_id: str,
    api_key: Annotated[str, Depends(get_api_key)],
    request: Request,
):
    """
    Store a new memory for later recall.

    Used by PreCompact hooks or directly by Claude to persist learnings.

    Request body:
        content: str - The memory content
        type: str - Memory type (fact, decision, learning, preference, todo, context)
        category: str - Optional grouping category
        ttl_days: int - Days until expiration (null = permanent)
        source: str - What created this memory (e.g., "hook", "claude", "manual")

    Returns:
        Created memory with ID and metadata
    """
    # Validate API key, project, and rate limit
    _, project, _, _ = await validate_and_rate_limit(project_id, api_key)

    body = await request.json()

    # Use resolved project ID, not the slug from URL
    resolved_project_id = project.id

    result = await store_memory(
        project_id=resolved_project_id,
        content=body.get("content", ""),
        memory_type=body.get("type", "learning"),
        scope=body.get("scope", "project"),
        category=body.get("category"),
        ttl_days=body.get("ttl_days"),
        source=body.get("source", "hook"),
    )

    return {
        "project_id": resolved_project_id,
        "memory_id": result.get("memory_id"),
        "type": result.get("type"),
        "created": result.get("created", False),
        "message": result.get("message"),
    }


# ============ SSE ENDPOINTS (Continue.dev Integration) ============


async def sse_event_generator(
    project_id: str,
    tool: ToolName,
    params: dict,
    plan: Plan,
    user_id: str | None = None,
    access_level: str = "EDITOR",
) -> AsyncGenerator[str, None]:
    """
    Generate Server-Sent Events for MCP tool execution.

    Yields SSE-formatted events:
    - start: Tool execution started
    - result: Tool execution complete with result
    - error: Error occurred during execution
    """
    start_time = time.perf_counter()

    # Send start event
    yield f"data: {json.dumps({'type': 'start', 'tool': tool.value})}\n\n"

    try:
        # Execute the tool
        engine = RLMEngine(project_id, plan=plan, user_id=user_id, access_level=access_level)
        result = await engine.execute(tool, params)

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Track usage
        await track_usage(
            project_id=project_id,
            tool=tool.value,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
            success=True,
        )

        # Send result event
        yield f"data: {json.dumps({'type': 'result', 'success': True, 'result': result.data, 'usage': {'input_tokens': result.input_tokens, 'output_tokens': result.output_tokens, 'latency_ms': latency_ms}})}\n\n"

    except Exception as e:
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Track failed request
        await track_usage(
            project_id=project_id,
            tool=tool.value,
            input_tokens=0,
            output_tokens=0,
            latency_ms=latency_ms,
            success=False,
            error=str(e),
        )

        # Send sanitized error event
        yield f"data: {json.dumps({'type': 'error', 'error': sanitize_error_message(e), 'usage': {'latency_ms': latency_ms}})}\n\n"

    # Send done event to signal stream end
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@app.get("/v1/{project_id}/mcp/sse", tags=["MCP", "SSE"])
async def mcp_sse_endpoint(
    project_id: str,
    api_key: Annotated[str, Depends(get_api_key)],
    tool: str = Query(..., description="Tool name to execute"),
    params: str = Query(default="{}", description="JSON-encoded parameters"),
):
    """
    Execute an RLM MCP tool via Server-Sent Events (SSE).

    This endpoint is designed for Continue.dev and other clients that
    support SSE transport. It streams the tool execution result.

    Args:
        project_id: The project ID
        api_key: API key from X-API-Key header
        tool: Tool name (e.g., rlm_ask, rlm_context_query)
        params: JSON-encoded parameters

    Returns:
        SSE stream with tool execution events
    """
    # Validate API key, project, and rate limit
    api_key_info, project, plan, _ = await validate_and_rate_limit(project_id, api_key)

    # Check usage limits
    limits = await check_usage_limits(project.id, plan)
    if limits.exceeded:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly usage limit exceeded: {limits.current}/{limits.max} queries. Upgrade your plan to continue.",
        )

    # Validate JSON payload size before parsing
    if len(params) > settings.max_json_payload_size:
        raise HTTPException(
            status_code=413,
            detail=f"JSON payload too large. Maximum size: {settings.max_json_payload_size} bytes",
        )

    # Parse tool name
    try:
        tool_name = ToolName(tool)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tool name: {tool}. Valid tools: {[t.value for t in ToolName]}",
        )

    # Parse params with error sanitization
    try:
        parsed_params = json.loads(params)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON format in params parameter",
        )

    # Return SSE stream
    return StreamingResponse(
        sse_event_generator(
            project.id,
            tool_name,
            parsed_params,
            plan,
            user_id=api_key_info.get("user_id"),
            access_level=api_key_info.get("access_level", "EDITOR"),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.post("/v1/{project_id}/mcp/sse", tags=["MCP", "SSE"])
async def mcp_sse_endpoint_post(
    project_id: str,
    request: MCPRequest,
    api_key: Annotated[str, Depends(get_api_key)],
):
    """
    Execute an RLM MCP tool via Server-Sent Events (SSE) using POST.

    Alternative to GET for clients that prefer POST requests with JSON body.

    Args:
        project_id: The project ID
        request: The MCP request with tool and parameters
        api_key: API key from X-API-Key header

    Returns:
        SSE stream with tool execution events
    """
    # Validate API key, project, and rate limit
    api_key_info, project, plan, _ = await validate_and_rate_limit(project_id, api_key)

    # Check usage limits
    limits = await check_usage_limits(project.id, plan)
    if limits.exceeded:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly usage limit exceeded: {limits.current}/{limits.max} queries. Upgrade your plan to continue.",
        )

    # Return SSE stream
    return StreamingResponse(
        sse_event_generator(
            project.id,
            request.tool,
            request.params,
            plan,
            user_id=api_key_info.get("user_id"),
            access_level=api_key_info.get("access_level", "EDITOR"),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ============ MAIN ============


def main():
    """Run the server with uvicorn."""
    import uvicorn

    uvicorn.run(
        "src.server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
