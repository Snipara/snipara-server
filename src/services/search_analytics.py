# apps/mcp-server/src/services/search_analytics.py
"""Search analytics and query performance tracking for Sprint 3."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class LatencyPercentiles:
    """Query latency percentiles in milliseconds."""

    p50: int = 0
    p75: int = 0
    p90: int = 0
    p95: int = 0
    p99: int = 0
    avg: int = 0
    min: int = 0
    max: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "p50": self.p50,
            "p75": self.p75,
            "p90": self.p90,
            "p95": self.p95,
            "p99": self.p99,
            "avg": self.avg,
            "min": self.min,
            "max": self.max,
        }


@dataclass
class ToolUsage:
    """Usage statistics for a single tool."""

    tool: str
    count: int
    success_count: int
    error_count: int
    total_input_tokens: int
    total_output_tokens: int
    avg_latency_ms: int
    success_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "count": self.count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "avg_latency_ms": self.avg_latency_ms,
            "success_rate": round(self.success_rate, 3),
        }


@dataclass
class DailyStats:
    """Daily query statistics."""

    date: str  # YYYY-MM-DD
    total_queries: int
    successful_queries: int
    failed_queries: int
    total_tokens: int
    avg_latency_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "total_queries": self.total_queries,
            "successful_queries": self.successful_queries,
            "failed_queries": self.failed_queries,
            "total_tokens": self.total_tokens,
            "avg_latency_ms": self.avg_latency_ms,
        }


@dataclass
class ErrorBreakdown:
    """Breakdown of errors by type."""

    type: str
    count: int
    last_seen: datetime | None
    example_message: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "count": self.count,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "example_message": self.example_message,
        }


@dataclass
class SearchAnalytics:
    """Comprehensive search analytics for a project."""

    # Time period
    period_start: datetime
    period_end: datetime
    period_days: int

    # Overall stats
    total_queries: int
    successful_queries: int
    failed_queries: int
    success_rate: float

    # Token usage
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    avg_tokens_per_query: int

    # Latency
    latency: LatencyPercentiles

    # Breakdown by tool
    tool_usage: list[ToolUsage]

    # Daily trends
    daily_stats: list[DailyStats]

    # Error analysis
    error_breakdown: list[ErrorBreakdown]

    # Top queries (if available)
    top_queries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
                "days": self.period_days,
            },
            "summary": {
                "total_queries": self.total_queries,
                "successful_queries": self.successful_queries,
                "failed_queries": self.failed_queries,
                "success_rate": round(self.success_rate, 3),
            },
            "tokens": {
                "total_input": self.total_input_tokens,
                "total_output": self.total_output_tokens,
                "total": self.total_tokens,
                "avg_per_query": self.avg_tokens_per_query,
            },
            "latency": self.latency.to_dict(),
            "tool_usage": [t.to_dict() for t in self.tool_usage],
            "daily_stats": [d.to_dict() for d in self.daily_stats],
            "error_breakdown": [e.to_dict() for e in self.error_breakdown],
            "top_queries": self.top_queries,
        }


async def compute_search_analytics(
    db: Any,
    project_id: str,
    days: int = 30,
) -> SearchAnalytics:
    """
    Compute comprehensive search analytics for a project.

    Args:
        db: Prisma database client
        project_id: Project to analyze
        days: Number of days to analyze

    Returns:
        SearchAnalytics with all metrics computed
    """
    now = datetime.now(tz=UTC)
    period_start = now - timedelta(days=days)

    # Get all queries in period
    queries = await db.query.find_many(
        where={
            "projectId": project_id,
            "createdAt": {"gte": period_start},
        },
        order={"createdAt": "desc"},
    )

    total_queries = len(queries)
    successful = [q for q in queries if q.success]
    failed = [q for q in queries if not q.success]

    # Token totals
    total_input = sum(q.inputTokens or 0 for q in queries)
    total_output = sum(q.outputTokens or 0 for q in queries)

    # Latency percentiles
    latencies = sorted([q.latencyMs for q in queries if q.latencyMs])
    latency = _compute_percentiles(latencies)

    # Tool usage breakdown
    tool_stats: dict[str, dict[str, Any]] = {}
    for q in queries:
        tool = q.tool or "unknown"
        if tool not in tool_stats:
            tool_stats[tool] = {
                "count": 0,
                "success": 0,
                "error": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_sum": 0,
            }
        tool_stats[tool]["count"] += 1
        if q.success:
            tool_stats[tool]["success"] += 1
        else:
            tool_stats[tool]["error"] += 1
        tool_stats[tool]["input_tokens"] += q.inputTokens or 0
        tool_stats[tool]["output_tokens"] += q.outputTokens or 0
        tool_stats[tool]["latency_sum"] += q.latencyMs or 0

    tool_usage = [
        ToolUsage(
            tool=tool,
            count=stats["count"],
            success_count=stats["success"],
            error_count=stats["error"],
            total_input_tokens=stats["input_tokens"],
            total_output_tokens=stats["output_tokens"],
            avg_latency_ms=stats["latency_sum"] // stats["count"] if stats["count"] > 0 else 0,
            success_rate=stats["success"] / stats["count"] if stats["count"] > 0 else 0,
        )
        for tool, stats in sorted(tool_stats.items(), key=lambda x: -x[1]["count"])
    ]

    # Daily stats
    daily_buckets: dict[str, dict[str, Any]] = {}
    for q in queries:
        date_str = q.createdAt.strftime("%Y-%m-%d")
        if date_str not in daily_buckets:
            daily_buckets[date_str] = {
                "total": 0,
                "success": 0,
                "failed": 0,
                "tokens": 0,
                "latency_sum": 0,
            }
        daily_buckets[date_str]["total"] += 1
        if q.success:
            daily_buckets[date_str]["success"] += 1
        else:
            daily_buckets[date_str]["failed"] += 1
        daily_buckets[date_str]["tokens"] += (q.inputTokens or 0) + (q.outputTokens or 0)
        daily_buckets[date_str]["latency_sum"] += q.latencyMs or 0

    daily_stats = [
        DailyStats(
            date=date,
            total_queries=stats["total"],
            successful_queries=stats["success"],
            failed_queries=stats["failed"],
            total_tokens=stats["tokens"],
            avg_latency_ms=stats["latency_sum"] // stats["total"] if stats["total"] > 0 else 0,
        )
        for date, stats in sorted(daily_buckets.items())
    ]

    # Error breakdown
    error_types: dict[str, dict[str, Any]] = {}
    for q in failed:
        error_msg = q.errorMessage or "Unknown error"
        # Extract error type from message
        error_type = _categorize_error(error_msg)
        if error_type not in error_types:
            error_types[error_type] = {
                "count": 0,
                "last_seen": None,
                "example": None,
            }
        error_types[error_type]["count"] += 1
        if error_types[error_type]["last_seen"] is None or q.createdAt > error_types[error_type]["last_seen"]:
            error_types[error_type]["last_seen"] = q.createdAt
            error_types[error_type]["example"] = error_msg[:200]

    error_breakdown = [
        ErrorBreakdown(
            type=error_type,
            count=info["count"],
            last_seen=info["last_seen"],
            example_message=info["example"],
        )
        for error_type, info in sorted(error_types.items(), key=lambda x: -x[1]["count"])
    ]

    return SearchAnalytics(
        period_start=period_start,
        period_end=now,
        period_days=days,
        total_queries=total_queries,
        successful_queries=len(successful),
        failed_queries=len(failed),
        success_rate=len(successful) / total_queries if total_queries > 0 else 1.0,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_input + total_output,
        avg_tokens_per_query=(total_input + total_output) // total_queries if total_queries > 0 else 0,
        latency=latency,
        tool_usage=tool_usage,
        daily_stats=daily_stats,
        error_breakdown=error_breakdown,
    )


def _compute_percentiles(latencies: list[int]) -> LatencyPercentiles:
    """Compute latency percentiles from a sorted list."""
    if not latencies:
        return LatencyPercentiles()

    n = len(latencies)

    def percentile(p: float) -> int:
        k = (n - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < n else f
        return int(latencies[f] + (k - f) * (latencies[c] - latencies[f]))

    return LatencyPercentiles(
        p50=percentile(50),
        p75=percentile(75),
        p90=percentile(90),
        p95=percentile(95),
        p99=percentile(99),
        avg=sum(latencies) // n,
        min=latencies[0],
        max=latencies[-1],
    )


def _categorize_error(message: str) -> str:
    """Categorize an error message into a type."""
    message_lower = message.lower()

    if "rate limit" in message_lower or "too many requests" in message_lower:
        return "rate_limit"
    if "timeout" in message_lower or "timed out" in message_lower:
        return "timeout"
    if "not found" in message_lower or "404" in message_lower:
        return "not_found"
    if "unauthorized" in message_lower or "401" in message_lower or "forbidden" in message_lower:
        return "auth_error"
    if "validation" in message_lower or "invalid" in message_lower:
        return "validation_error"
    if "connection" in message_lower or "network" in message_lower:
        return "network_error"
    if "database" in message_lower or "prisma" in message_lower:
        return "database_error"

    return "other"


async def get_query_trends(
    db: Any,
    project_id: str,
    days: int = 7,
    granularity: str = "hour",  # "hour", "day"
) -> list[dict[str, Any]]:
    """
    Get query trends over time with specified granularity.

    Returns list of time buckets with query counts.
    """
    now = datetime.now(tz=UTC)
    period_start = now - timedelta(days=days)

    # Note: Prisma Python doesn't support select like Prisma JS
    queries = await db.query.find_many(
        where={
            "projectId": project_id,
            "createdAt": {"gte": period_start},
        },
    )

    # Bucket by granularity
    buckets: dict[str, dict[str, Any]] = {}

    for q in queries:
        if granularity == "hour":
            bucket_key = q.createdAt.strftime("%Y-%m-%d %H:00")
        else:
            bucket_key = q.createdAt.strftime("%Y-%m-%d")

        if bucket_key not in buckets:
            buckets[bucket_key] = {"total": 0, "success": 0, "latency_sum": 0}

        buckets[bucket_key]["total"] += 1
        if q.success:
            buckets[bucket_key]["success"] += 1
        buckets[bucket_key]["latency_sum"] += q.latencyMs or 0

    return [
        {
            "timestamp": key,
            "total_queries": stats["total"],
            "successful_queries": stats["success"],
            "error_queries": stats["total"] - stats["success"],
            "avg_latency_ms": stats["latency_sum"] // stats["total"] if stats["total"] > 0 else 0,
        }
        for key, stats in sorted(buckets.items())
    ]


async def get_top_queries(
    db: Any,
    project_id: str,
    days: int = 7,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Get the most frequently used queries/tools.

    Note: This is a simplified version - in production you'd want
    to store the actual query text for analysis.
    """
    now = datetime.now(tz=UTC)
    period_start = now - timedelta(days=days)

    queries = await db.query.find_many(
        where={
            "projectId": project_id,
            "createdAt": {"gte": period_start},
        },
    )

    # Aggregate by tool (since we don't store query text)
    tool_counts: dict[str, dict[str, Any]] = {}
    for q in queries:
        tool = q.tool or "unknown"
        if tool not in tool_counts:
            tool_counts[tool] = {"count": 0, "success": 0, "latency_sum": 0}
        tool_counts[tool]["count"] += 1
        if q.success:
            tool_counts[tool]["success"] += 1
        tool_counts[tool]["latency_sum"] += q.latencyMs or 0

    sorted_tools = sorted(tool_counts.items(), key=lambda x: -x[1]["count"])[:limit]

    return [
        {
            "tool": tool,
            "count": stats["count"],
            "success_rate": stats["success"] / stats["count"] if stats["count"] > 0 else 0,
            "avg_latency_ms": stats["latency_sum"] // stats["count"] if stats["count"] > 0 else 0,
        }
        for tool, stats in sorted_tools
    ]
