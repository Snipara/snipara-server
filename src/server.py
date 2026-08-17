"""FastAPI application for Snipara Server."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from . import __version__
from .api.deps import (
    get_api_key,
    get_client_ip,
    sanitize_error_message,
    validate_and_rate_limit,
)
from .api.graphify import router as graphify_router
from .auth import (
    enforce_tool_scope,
    validate_internal_secret,
)
from .config import settings
from .contract import public_capabilities
from .db import close_db, get_db
from .mcp import MCP_TOOL_NAME_SET
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
from .services.swarm_events import subscribe_to_swarm, unsubscribe_from_swarm
from .usage import (
    check_usage_limits,
    close_redis,
    get_usage_stats,
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
sentry_dsn = (settings.sentry_dsn or "").strip()
if sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=sentry_dsn,
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
    except Exception as exc:
        logger.warning(f"Sentry DSN configured but initialization failed: {exc}")
else:
    logger.debug("Sentry DSN not configured - error tracking disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup. The OSS runtime has no commercial license gate or telemetry
    # handshake; all state remains in the operator's database.
    logger.info("Starting Snipara Server v%s (self-hosted OSS mode)", __version__)

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

    if settings.preload_embeddings:
        try:
            EmbeddingsService.preload_all()
        except Exception as e:
            logger.warning(f"Embedding model preload failed (will retry on first use): {e}")
    else:
        logger.info("Embedding preload disabled; models will load lazily on demand")

    # Start background job processor for async indexing
    from .services.background_jobs import start_job_processor, stop_job_processor

    await start_job_processor()

    yield
    # Shutdown
    await stop_job_processor()
    await close_db()
    await close_redis()


app = FastAPI(
    title="Snipara Server",
    description="Self-hosted MCP and project memory runtime for local and self-hosted workflows",
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
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-Id"],
)

# Mount MCP Streamable HTTP transport
app.include_router(mcp_router)

# Mount Graphify-compatible export surface
app.include_router(graphify_router)


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
    from .services.embeddings import LIGHT_MODEL_NAME, EmbeddingsService

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

    # Readiness depends on DB plus either the internal embedding service or
    # primary local embeddings when eager preload is enabled.
    primary_loaded = EmbeddingsService.get_instance().is_loaded()
    light_loaded = EmbeddingsService.get_instance(LIGHT_MODEL_NAME).is_loaded()
    checks["embedding_preload_enabled"] = settings.preload_embeddings
    checks["embedding_service_configured"] = bool(settings.embedding_service_url)
    checks["embedding_primary_loaded"] = primary_loaded
    checks["embedding_light_loaded"] = light_loaded
    if settings.embedding_service_url:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{settings.embedding_service_url.rstrip('/')}/ready")
            checks["embedding_service_ready"] = response.status_code == 200
        except Exception:
            checks["embedding_service_ready"] = False
        checks["embeddings_ready"] = checks["embedding_service_ready"]
    else:
        checks["embeddings_ready"] = primary_loaded if settings.preload_embeddings else True
    if not checks["embeddings_ready"]:
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


@app.get("/capabilities", tags=["Health"])
async def capabilities():
    """Expose only the non-secret OSS contract used by compatible adapters."""
    return public_capabilities()


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Snipara Server",
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

    # Check usage limits
    limits = await check_usage_limits(project.id, plan)
    if limits.exceeded:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Local usage limit exceeded: {limits.current}/{limits.max} queries. "
                "Adjust the operator's local limits or retention policy."
            ),
        )

    # Execute the tool with project settings from dashboard
    try:
        if request.tool.value not in MCP_TOOL_NAME_SET:
            raise HTTPException(
                status_code=404,
                detail=f"Tool not available in OSS mode: {request.tool.value}",
            )
        enforce_tool_scope(request.tool.value, api_key_info)
        effective_user_id = api_key_info.get("user_id")
        engine = RLMEngine(
            project.id,
            plan=plan,
            settings=project_settings,
            user_id=effective_user_id,
            team_id=getattr(project, "teamId", None),
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
        team_id=getattr(project, "teamId", None),
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


@app.post("/v1/{project_id}/reindex", tags=["MCP"])
async def reindex_project(
    project_id: str,
    mode: str = Query(
        default="incremental",
        description="Index mode: 'incremental' (only unindexed docs) or 'full' (all docs)",
        pattern="^(incremental|full)$",
    ),
    kind: str = Query(
        default="doc",
        description="Index kind: 'doc' for document chunks, 'code' for code graph indexing",
        pattern="^(doc|code)$",
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
        kind: Index kind - "doc" or "code"
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
        if not validate_internal_secret(x_internal_secret):
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
    index_kind = "CODE" if kind == "code" else "DOC"

    if index_kind == "CODE" and not settings.enable_code_ingestion:
        raise HTTPException(status_code=409, detail="Code ingestion is not enabled")

    # Create index job (returns immediately)
    job = await create_index_job(
        db,
        project.id,
        triggered_by=None,  # Could add user ID if available
        triggered_via=triggered_via,
        index_mode=index_mode,
        index_kind=index_kind,
    )

    logger.info(
        "Created %s index job %s for project %s (mode=%s)",
        index_kind.lower(),
        job["id"],
        project.id,
        index_mode,
    )

    return {
        "job_id": job["id"],
        "project_id": project.id,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "index_mode": job.get("index_mode", "INCREMENTAL").lower(),
        "index_kind": job.get("index_kind", "DOC").lower(),
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
        if not validate_internal_secret(x_internal_secret):
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
    scope: str | None = Query(default=None, description="Filter by memory scope"),
    category: str | None = Query(default=None, description="Filter by category"),
    limit: int = Query(default=10, ge=1, le=50, description="Max memories to return"),
    min_relevance: float = Query(default=0.3, ge=0, le=1, description="Minimum relevance"),
    include_inactive: bool = Query(default=False, description="Include inactive memories"),
    warning_threshold: float = Query(
        default=0.72, ge=0, le=1, description="Minimum relevance for inactive-memory warnings"
    ),
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
    auth_info, project, _, _ = await validate_and_rate_limit(project_id, api_key)

    try:
        enforce_tool_scope("rlm_recall", auth_info)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # Use resolved project ID, not the slug from URL
    resolved_project_id = project.id
    effective_user_id = auth_info.get("user_id")

    result = await semantic_recall(
        project_id=resolved_project_id,
        query=query,
        memory_type=type,
        scope=scope,
        category=category,
        limit=limit,
        min_relevance=min_relevance,
        include_inactive=include_inactive,
        warning_threshold=warning_threshold,
        user_id=effective_user_id,
        team_id=getattr(project, "teamId", None),
    )

    return {
        "project_id": resolved_project_id,
        "query": query,
        "memories": result.get("memories", []),
        "warnings": result.get("warnings", []),
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

    Used by PreCompact hooks or directly by MCP client to persist learnings.

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
    auth_info, project, _, _ = await validate_and_rate_limit(project_id, api_key)

    try:
        enforce_tool_scope("rlm_remember", auth_info)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    body = await request.json()

    # Use resolved project ID, not the slug from URL
    resolved_project_id = project.id
    effective_user_id = auth_info.get("user_id")

    result = await store_memory(
        project_id=resolved_project_id,
        content=body.get("content", ""),
        memory_type=body.get("type", "learning"),
        scope=body.get("scope", "project"),
        category=body.get("category"),
        ttl_days=body.get("ttl_days"),
        source=body.get("source", "hook"),
        user_id=effective_user_id,
        team_id=getattr(project, "teamId", None),
        agent_id=body.get("agent_id"),
    )

    return {
        "project_id": resolved_project_id,
        "memory_id": result.get("memory_id"),
        "type": result.get("type"),
        "status": result.get("status"),
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
    team_id: str | None = None,
    access_level: str = "EDITOR",
    auth_info: dict | None = None,
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
        if tool.value not in MCP_TOOL_NAME_SET:
            raise HTTPException(
                status_code=404,
                detail=f"Tool not available in OSS mode: {tool.value}",
            )
        enforce_tool_scope(tool.value, auth_info)
        effective_user_id = user_id
        engine = RLMEngine(
            project_id,
            plan=plan,
            user_id=effective_user_id,
            team_id=team_id,
            access_level=access_level,
        )
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
            team_id=getattr(project, "teamId", None),
            access_level=api_key_info.get("access_level", "EDITOR"),
            auth_info=api_key_info,
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
            team_id=getattr(project, "teamId", None),
            access_level=api_key_info.get("access_level", "EDITOR"),
            auth_info=api_key_info,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ============ SWARM SSE ENDPOINTS ============


async def swarm_sse_event_generator(
    swarm_id: str,
    project_id: str,
) -> AsyncGenerator[str, None]:
    """
    Generate Server-Sent Events for swarm real-time updates.

    Subscribes to Redis pub/sub channel and streams events to client.

    Yields SSE-formatted events:
    - connected: Connection established
    - event: Swarm event (task_created, task_completed, agent_joined, etc.)
    - heartbeat: Keep-alive ping every 30 seconds
    - error: Error occurred
    """
    pubsub = None
    try:
        # Send connection established event
        yield f"data: {json.dumps({'type': 'connected', 'swarm_id': swarm_id})}\n\n"

        # Subscribe to swarm events
        pubsub = await subscribe_to_swarm(swarm_id)
        if not pubsub:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Redis unavailable, use polling instead'})}\n\n"
            return

        # Listen for events with heartbeat
        heartbeat_interval = 30  # seconds
        last_heartbeat = time.time()

        while True:
            try:
                # Non-blocking get with timeout
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=1.0,
                )

                if message and message.get("type") == "message":
                    data = message.get("data")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    event_data = json.loads(data) if isinstance(data, str) else data
                    yield f"data: {json.dumps({'type': 'event', 'event': event_data})}\n\n"

                # Send heartbeat every 30 seconds
                if time.time() - last_heartbeat >= heartbeat_interval:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                    last_heartbeat = time.time()

            except TimeoutError:
                # Timeout is normal, check for heartbeat
                if time.time() - last_heartbeat >= heartbeat_interval:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                    last_heartbeat = time.time()
                continue

    except asyncio.CancelledError:
        # Client disconnected
        logger.debug(f"SSE client disconnected from swarm {swarm_id}")
    except Exception as e:
        logger.error(f"Swarm SSE error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    finally:
        if pubsub:
            await unsubscribe_from_swarm(pubsub, swarm_id)


@app.get("/v1/{project_id}/swarm/{swarm_id}/sse", tags=["Swarm", "SSE"])
async def swarm_sse_endpoint(
    project_id: str,
    swarm_id: str,
    api_key: Annotated[str, Depends(get_api_key)],
):
    """
    Subscribe to real-time swarm events via Server-Sent Events (SSE).

    This endpoint streams swarm events in real-time using Redis pub/sub.
    Useful for dashboards, monitoring, and real-time coordination.

    Events include:
    - task_created, task_claimed, task_completed, task_failed
    - agent_joined, agent_left
    - state_changed
    - claim_acquired, claim_released

    Args:
        project_id: The project ID
        swarm_id: The swarm ID to subscribe to
        api_key: API key from X-API-Key header

    Returns:
        SSE stream with swarm events
    """
    # Validate API key and project
    api_key_info, project, plan, _ = await validate_and_rate_limit(project_id, api_key)

    # Verify swarm exists and belongs to project
    db = await get_db()
    swarm = await db.swarm.find_first(where={"id": swarm_id, "projectId": project.id})
    if not swarm:
        raise HTTPException(status_code=404, detail=f"Swarm {swarm_id} not found")

    # Return SSE stream
    return StreamingResponse(
        swarm_sse_event_generator(swarm_id, project.id),
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
