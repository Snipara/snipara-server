"""Hierarchical Task Events Service.

Handles event logging, audit trails, and observability metrics for htasks:
- Event logging (create, update, block, unblock, complete, close, delete, waiver)
- Checkpoint delta reports
- Comprehensive metrics (throughput, aging, blocked/recovered ratio)
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

try:
    from prisma import Json
except ImportError:
    def Json(x):  # noqa: N802
        return x

from ..db import get_db

logger = logging.getLogger(__name__)

# Event types
EVENT_TYPES = [
    "create",
    "update",
    "block",
    "unblock",
    "complete",
    "close",
    "delete",
    "waiver",
]


# =============================================================================
# EVENT LOGGING
# =============================================================================


async def log_htask_event(
    swarm_id: str,
    task_id: str,
    event_type: str,
    payload: dict[str, Any],
    actor_id: str | None = None,
) -> str:
    """Log an htask event for audit and observability.

    Args:
        swarm_id: The swarm ID
        task_id: The task ID
        event_type: Type of event (create, update, block, etc.)
        payload: Event payload data
        actor_id: Optional actor who triggered the event

    Returns:
        Event ID
    """
    db = await get_db()

    event = await db.htaskevent.create(
        data={
            "swarmId": swarm_id,
            "taskId": task_id,
            "eventType": event_type,
            "payload": Json(payload),
            "actorId": actor_id,
        }
    )

    logger.debug(f"Logged htask event: {event_type} for task {task_id}")

    return event.id


async def get_events_since(
    swarm_id: str,
    since: datetime,
    event_types: list[str] | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Get events since a given timestamp.

    Args:
        swarm_id: The swarm ID
        since: Start timestamp
        event_types: Optional filter by event types
        limit: Maximum events to return

    Returns:
        List of event dicts
    """
    db = await get_db()

    where = {
        "swarmId": swarm_id,
        "createdAt": {"gte": since},
    }

    if event_types:
        where["eventType"] = {"in": event_types}

    events = await db.htaskevent.find_many(
        where=where,
        order={"createdAt": "asc"},
        take=limit,
    )

    return [
        {
            "id": e.id,
            "task_id": e.taskId,
            "event_type": e.eventType,
            "payload": e.payload,
            "actor_id": e.actorId,
            "created_at": e.createdAt.isoformat() if e.createdAt else None,
        }
        for e in events
    ]


async def get_task_audit_trail(swarm_id: str, task_id: str) -> list[dict[str, Any]]:
    """Get complete audit trail for a task.

    Args:
        swarm_id: The swarm ID
        task_id: The task ID

    Returns:
        List of events in chronological order
    """
    db = await get_db()

    events = await db.htaskevent.find_many(
        where={"swarmId": swarm_id, "taskId": task_id},
        order={"createdAt": "asc"},
    )

    return [
        {
            "id": e.id,
            "event_type": e.eventType,
            "payload": e.payload,
            "actor_id": e.actorId,
            "created_at": e.createdAt.isoformat() if e.createdAt else None,
        }
        for e in events
    ]


# =============================================================================
# CHECKPOINT DELTA REPORTS
# =============================================================================


async def get_checkpoint_delta(swarm_id: str, since: datetime) -> dict[str, Any]:
    """Get comprehensive delta report since last checkpoint.

    Args:
        swarm_id: The swarm ID
        since: Last checkpoint timestamp

    Returns:
        Delta report with event counts, closures, blocks, etc.
    """
    now = datetime.now(UTC)
    events = await get_events_since(swarm_id, since)

    # Count by type
    by_type = {t: 0 for t in EVENT_TYPES}
    for e in events:
        if e["event_type"] in by_type:
            by_type[e["event_type"]] += 1

    # Extract task IDs for key events
    closures = [e["task_id"] for e in events if e["event_type"] == "close"]
    blocks = [e["task_id"] for e in events if e["event_type"] == "block"]
    unblocks = [e["task_id"] for e in events if e["event_type"] == "unblock"]
    deletes = [e["task_id"] for e in events if e["event_type"] == "delete"]

    return {
        "since": since.isoformat(),
        "until": now.isoformat(),
        "events_count": len(events),
        "by_type": by_type,
        "closures": closures,
        "blocks": blocks,
        "unblocks": unblocks,
        "deletes": deletes,
        "events": [
            {
                "task_id": e["task_id"],
                "type": e["event_type"],
                "at": e["created_at"],
            }
            for e in events
        ],
    }


# =============================================================================
# METRICS
# =============================================================================


async def get_htask_metrics(
    swarm_id: str,
    period_hours: int = 24,
) -> dict[str, Any]:
    """Get comprehensive metrics for a swarm.

    Args:
        swarm_id: The swarm ID
        period_hours: Period for time-based metrics (default 24h)

    Returns:
        Comprehensive metrics dict
    """
    now = datetime.now(UTC)
    period_start = now - timedelta(hours=period_hours)

    db = await get_db()

    # Get all active (non-archived) tasks
    tasks = await db.hierarchicaltask.find_many(
        where={"swarmId": swarm_id, "archivedAt": None}
    )

    # Get events in period
    events = await db.htaskevent.find_many(
        where={"swarmId": swarm_id, "createdAt": {"gte": period_start}}
    )

    # === Base counts ===
    by_status = {
        "pending": 0,
        "in_progress": 0,
        "blocked": 0,
        "failed": 0,
        "completed": 0,
        "cancelled": 0,
    }

    by_level = {
        "N0": 0,
        "N1": 0,
        "N2": 0,
        "N3": 0,
    }

    pending_unowned = 0
    failed_blocking = 0

    for t in tasks:
        # Status counts
        status_key = t.status.lower() if t.status else "pending"
        if status_key in by_status:
            by_status[status_key] += 1

        # Level counts
        level_map = {
            "N0_INITIATIVE": "N0",
            "N1_FEATURE": "N1",
            "N2_WORKSTREAM": "N2",
            "N3_TASK": "N3",
        }
        level_key = level_map.get(t.level, "N3")
        by_level[level_key] += 1

        # Special counts
        if t.status == "PENDING" and not t.owner:
            pending_unowned += 1
        if t.status == "FAILED" and t.isBlocking:
            failed_blocking += 1

    # === Throughput ===
    closures = [e for e in events if e.eventType == "close"]
    throughput_per_hour = len(closures) / period_hours if period_hours > 0 else 0

    # === Aging by level ===
    def avg_age(level_filter: str) -> float:
        level_tasks = [
            t for t in tasks
            if t.level == level_filter
            and t.status not in ("COMPLETED", "CANCELLED")
        ]
        if not level_tasks:
            return 0.0
        ages = [(now - t.createdAt).days for t in level_tasks if t.createdAt]
        return sum(ages) / len(ages) if ages else 0.0

    aging_by_level = {
        "N0": round(avg_age("N0_INITIATIVE"), 1),
        "N1": round(avg_age("N1_FEATURE"), 1),
        "N2": round(avg_age("N2_WORKSTREAM"), 1),
        "N3": round(avg_age("N3_TASK"), 1),
    }

    # === Blocked → Recovered ratio ===
    blocks = [e for e in events if e.eventType == "block"]
    unblocks = [e for e in events if e.eventType == "unblock"]
    blocked_recovered_ratio = len(unblocks) / len(blocks) if blocks else 1.0

    # === Top blockers ===
    blocked_tasks = [t for t in tasks if t.status == "BLOCKED"]
    blocked_tasks.sort(key=lambda t: t.blockedAt or t.createdAt or now)
    top_blockers = [
        {
            "id": t.id,
            "title": t.title,
            "blocked_days": (now - (t.blockedAt or t.createdAt or now)).days,
            "blocker_type": t.blockerType,
            "blocker_reason": t.blockerReason[:100] if t.blockerReason else None,
        }
        for t in blocked_tasks[:5]
    ]

    return {
        "total": len(tasks),
        "by_status": by_status,
        "by_level": by_level,
        "pending_unowned": pending_unowned,
        "failed_blocking": failed_blocking,
        "throughput": {
            "closures_total": len(closures),
            "per_hour": round(throughput_per_hour, 2),
            "period_hours": period_hours,
        },
        "aging_days": aging_by_level,
        "blocked_recovered_ratio": round(blocked_recovered_ratio, 2),
        "top_blockers": top_blockers,
        "timestamp": now.isoformat(),
    }


# =============================================================================
# CLEANUP
# =============================================================================


async def cleanup_old_events(
    swarm_id: str,
    older_than_days: int = 30,
    keep_minimum: int = 100,
) -> int:
    """Clean up old events to manage database size.

    Args:
        swarm_id: The swarm ID
        older_than_days: Delete events older than this
        keep_minimum: Always keep at least this many events

    Returns:
        Number of events deleted
    """
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    db = await get_db()

    # Count total events
    total = await db.htaskevent.count(where={"swarmId": swarm_id})

    if total <= keep_minimum:
        return 0

    # Delete old events
    result = await db.htaskevent.delete_many(
        where={
            "swarmId": swarm_id,
            "createdAt": {"lt": cutoff},
        }
    )

    deleted = result if isinstance(result, int) else getattr(result, "count", 0)

    if deleted > 0:
        logger.info(f"Cleaned up {deleted} old htask events for swarm {swarm_id}")

    return deleted
