"""Usage tracking and rate limiting module."""

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta

import redis.asyncio as redis

from .config import settings
from .db import get_db
from .models import LimitsInfo, Plan

logger = logging.getLogger(__name__)

# Redis client for rate limiting
_redis: redis.Redis | None = None
_redis_available: bool | None = None

# In-memory rate limiting fallback (per-process)
_local_rate_limits: dict[str, list[float]] = defaultdict(list)
_fallback_warning_logged: bool = False


async def get_redis() -> redis.Redis | None:
    """Get or create Redis client. Returns None if Redis is not configured."""
    global _redis, _redis_available

    # If we already know Redis is unavailable, skip
    if _redis_available is False:
        return None

    if _redis is None:
        if not settings.redis_url:
            _redis_available = False
            return None
        try:
            _redis = redis.from_url(settings.redis_url)
            # Test connection
            await _redis.ping()
            _redis_available = True
        except Exception as e:
            print(f"[Warning] Redis connection failed, rate limiting disabled: {e}")
            _redis_available = False
            _redis = None
            return None
    return _redis


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis, _redis_available
    if _redis is not None:
        await _redis.close()
        _redis = None
    _redis_available = None


async def check_rate_limit(api_key_id: str) -> bool:
    """
    Check if the API key has exceeded rate limits.

    Uses Redis when available, falls back to in-memory sliding window.

    Args:
        api_key_id: The API key ID

    Returns:
        True if within limits, False if exceeded
    """
    global _fallback_warning_logged

    r = await get_redis()

    # In-memory fallback when Redis unavailable
    if r is None:
        return _check_rate_limit_memory(api_key_id)

    try:
        key = f"rate_limit:{api_key_id}"

        # Get current count
        count = await r.get(key)
        if count is None:
            # First request, set counter with expiry
            await r.setex(key, settings.rate_limit_window, 1)
            return True

        count = int(count)
        if count >= settings.rate_limit_requests:
            logger.warning(f"Rate limit exceeded for {api_key_id[:8]}...")
            return False

        # Increment counter
        await r.incr(key)
        return True
    except Exception as e:
        # Redis error - fall back to in-memory
        logger.error(f"Redis rate limit check failed: {e}")
        return _check_rate_limit_memory(api_key_id)


def _check_rate_limit_memory(api_key_id: str) -> bool:
    """
    In-memory rate limit check (fallback).

    Uses a sliding window algorithm. Note: This is per-process only and
    won't work correctly with multiple server instances.

    Args:
        api_key_id: The API key ID

    Returns:
        True if within limits, False if exceeded
    """
    global _fallback_warning_logged

    if not _fallback_warning_logged:
        logger.warning(
            "Redis unavailable - using in-memory rate limiting. "
            "This is per-process only and won't work correctly "
            "with multiple server instances."
        )
        _fallback_warning_logged = True

    now = time.time()
    window_seconds = settings.rate_limit_window
    window = _local_rate_limits[api_key_id]

    # Remove expired entries (sliding window)
    window[:] = [t for t in window if now - t < window_seconds]

    if len(window) >= settings.rate_limit_requests:
        logger.warning(f"Rate limit exceeded for {api_key_id[:8]}... (in-memory)")
        return False

    window.append(now)
    return True


async def check_usage_limits(project_id: str, plan: Plan) -> LimitsInfo:
    """
    Check if the project has exceeded monthly usage limits.

    Args:
        project_id: The project ID
        plan: The subscription plan

    Returns:
        LimitsInfo with current usage and limits
    """
    db = await get_db()

    # Get the start of the current month
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)

    # Count queries this month
    query_count = await db.query.count(
        where={
            "projectId": project_id,
            "createdAt": {"gte": month_start},
        }
    )

    # Get plan limit
    max_queries = settings.plan_limits.get(plan.value, 100)

    return LimitsInfo(
        current=query_count,
        max=max_queries,
        exceeded=max_queries != -1 and query_count >= max_queries,
        resets_at=next_month,
    )


async def track_usage(
    project_id: str,
    tool: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool,
    error: str | None = None,
) -> None:
    """
    Track a query for usage analytics and billing.

    Args:
        project_id: The project ID
        tool: The tool that was executed
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        latency_ms: Request latency in milliseconds
        success: Whether the request succeeded
        error: Error message if failed
    """
    db = await get_db()

    await db.query.create(
        data={
            "projectId": project_id,
            "tool": tool,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "latencyMs": latency_ms,
            "success": success,
            "errorMessage": error,
        }
    )


async def get_usage_stats(project_id: str, days: int = 30) -> dict:
    """
    Get usage statistics for a project.

    Args:
        project_id: The project ID
        days: Number of days to look back

    Returns:
        Usage statistics dictionary
    """
    db = await get_db()
    since = datetime.utcnow() - timedelta(days=days)

    # Get query counts
    queries = await db.query.find_many(
        where={
            "projectId": project_id,
            "createdAt": {"gte": since},
        }
    )

    total_queries = len(queries)
    successful_queries = sum(1 for q in queries if q.success)
    total_input_tokens = sum(q.inputTokens for q in queries)
    total_output_tokens = sum(q.outputTokens for q in queries)
    avg_latency = sum(q.latencyMs for q in queries) / total_queries if total_queries > 0 else 0

    # Group by tool
    tool_counts: dict[str, int] = {}
    for q in queries:
        tool_counts[q.tool] = tool_counts.get(q.tool, 0) + 1

    return {
        "total_queries": total_queries,
        "successful_queries": successful_queries,
        "failed_queries": total_queries - successful_queries,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "avg_latency_ms": round(avg_latency, 2),
        "queries_by_tool": tool_counts,
        "period_days": days,
    }
