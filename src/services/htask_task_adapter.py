"""Compatibility adapter from legacy rlm_task_* tools to hierarchical tasks.

The flat SwarmTask queue is no longer an active runtime path for MCP task tools.
Legacy rlm_task_* calls write and read canonical HierarchicalTask rows so agents
use one task surface with owners, evidence, blockers, policy, and audit events.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

try:
    from prisma import Json
except ImportError:

    def Json(x):  # noqa: N802
        return x

from ..db import get_db
from .htask_coordinator import complete_task as complete_htask
from .htask_coordinator import create_htask
from .htask_events import log_htask_event
from .htask_policy import get_compat_mode, get_policy


async def get_task_compat_mode(swarm_id: str) -> str:
    """Return the normalized task compatibility mode for a swarm."""
    policy = await get_policy(swarm_id)
    return str(get_compat_mode(policy) or "HTASK").upper()


def legacy_priority_to_htask(priority: int | str | None) -> str:
    """Map flat queue integer priority to htask priority."""
    try:
        value = int(priority or 0)
    except (TypeError, ValueError):
        value = 0
    if value >= 2:
        return "P0"
    if value >= 1:
        return "P1"
    return "P2"


def htask_priority_to_legacy(priority: str | None) -> int:
    """Map htask priority to the legacy queue integer scale."""
    return {"P0": 2, "P1": 1, "P2": 0}.get(str(priority or "P2"), 0)


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _legacy_status_to_htask(status: str | None) -> str | None:
    if not status:
        return None
    normalized = status.upper()
    if normalized == "CLAIMED":
        return "IN_PROGRESS"
    if normalized == "DONE":
        return "COMPLETED"
    return normalized


def _htask_status_to_legacy(status: str | None) -> str:
    normalized = str(status or "PENDING").upper()
    if normalized == "IN_PROGRESS":
        return "claimed"
    if normalized == "COMPLETED":
        return "completed"
    if normalized == "CANCELLED":
        return "cancelled"
    if normalized == "BLOCKED":
        return "blocked"
    if normalized == "FAILED":
        return "failed"
    return "pending"


def _parse_result(result: Any | None) -> Any | None:
    if not isinstance(result, str):
        return result
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"raw": result}


def _task_attr(task: Any, name: str, default: Any = None) -> Any:
    return getattr(task, name, default)


def _iso_value(value: Any | None) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _latest_task_time(task: Any) -> Any | None:
    for name in ("completedAt", "startedAt", "updatedAt", "createdAt"):
        value = _task_attr(task, name)
        if value:
            return value
    return None


def _legacy_task_dict(task: Any) -> dict[str, Any]:
    return {
        "task_id": task.id,
        "id": task.id,
        "title": task.title,
        "description": _task_attr(task, "description"),
        "status": _htask_status_to_legacy(task.status),
        "priority": htask_priority_to_legacy(task.priority),
        "htask_priority": task.priority,
        "depends_on": [],
        "assigned_to": _task_attr(task, "owner"),
        "owner": _task_attr(task, "owner"),
        "created_at": _iso_value(_task_attr(task, "createdAt")),
        "updated_at": _iso_value(_task_attr(task, "updatedAt")),
        "deadline": _iso_value(_task_attr(task, "etaTarget")),
        "canonical_surface": "htask",
        "level": task.level,
    }


async def create_task_as_htask(
    *,
    swarm_id: str,
    agent_id: str,
    title: str,
    description: str | None = None,
    priority: int = 0,
    deadline: datetime | str | None = None,
    depends_on: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    for_agent_id: str | None = None,
) -> dict[str, Any]:
    """Create a legacy queue task as a canonical N3 htask."""
    mode = await get_task_compat_mode(swarm_id)
    context_refs = [f"legacy-task-created-by:{agent_id}"]
    context_refs.extend(f"legacy-task-depends:{dep}" for dep in (depends_on or []))
    if metadata:
        context_refs.append("legacy-task-metadata:result")

    result = await create_htask(
        swarm_id=swarm_id,
        level="N3_TASK",
        title=title,
        description=description or "",
        owner=for_agent_id or "unassigned",
        priority=legacy_priority_to_htask(priority),
        eta_target=_parse_datetime(deadline),
        context_refs=context_refs,
    )
    if not result.get("success"):
        result.setdefault("canonical_surface", "htask")
        result.setdefault("compat_mode", mode)
        return result

    return {
        "success": True,
        "task_id": result["task_id"],
        "htask_id": result["task_id"],
        "title": title,
        "priority": priority,
        "htask_priority": result.get("priority") or legacy_priority_to_htask(priority),
        "deadline": _iso_value(_parse_datetime(deadline)) if deadline else None,
        "depends_on": depends_on or [],
        "for_agent_id": for_agent_id,
        "assigned_to": for_agent_id or None,
        "assigned": bool(for_agent_id),
        "created_by": agent_id,
        "canonical_surface": "htask",
        "compat_mode": mode,
        "legacy_tool": "rlm_task_create",
        "message": "Task created as hierarchical N3 task",
    }


async def create_tasks_bulk_as_htask(
    *,
    swarm_id: str,
    agent_id: str,
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create multiple legacy queue tasks as canonical N3 htasks."""
    created_ids: list[str] = []
    failed: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        title = task.get("title", "")
        if not title:
            failed.append({"index": index, "error": "title is required"})
            continue
        result = await create_task_as_htask(
            swarm_id=swarm_id,
            agent_id=agent_id,
            title=title,
            description=task.get("description"),
            priority=task.get("priority", 0),
            deadline=task.get("deadline"),
            depends_on=task.get("depends_on"),
            metadata=task.get("metadata"),
            for_agent_id=task.get("for_agent_id"),
        )
        if result.get("success"):
            created_ids.append(result["task_id"])
        else:
            failed.append({"index": index, "title": title, "error": result.get("error")})

    return {
        "success": True,
        "created_count": len(created_ids),
        "task_ids": created_ids,
        "failed_count": len(failed),
        "failed": failed if failed else None,
        "canonical_surface": "htask",
        "compat_mode": await get_task_compat_mode(swarm_id),
    }


async def claim_task_as_htask(
    *,
    swarm_id: str,
    agent_id: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Claim a canonical htask through the legacy rlm_task_claim surface."""
    db = await get_db()
    if task_id:
        task = await db.hierarchicaltask.find_first(
            where={"id": task_id, "swarmId": swarm_id, "archivedAt": None}
        )
    else:
        candidates = await db.hierarchicaltask.find_many(
            where={
                "swarmId": swarm_id,
                "level": "N3_TASK",
                "status": "PENDING",
                "archivedAt": None,
            },
            order=[{"priority": "asc"}, {"sequenceNumber": "asc"}],
            take=50,
        )
        task = next(
            (
                candidate
                for candidate in candidates
                if _task_attr(candidate, "owner") in {agent_id, "unassigned"}
            ),
            candidates[0] if candidates else None,
        )

    if not task:
        return {"success": False, "error": "No available htask found", "canonical_surface": "htask"}
    if task.status != "PENDING":
        return {
            "success": False,
            "error": f"Task is {task.status}, cannot claim",
            "task_id": task.id,
            "canonical_surface": "htask",
        }
    task_owner = _task_attr(task, "owner")
    if task_owner not in {agent_id, "unassigned"}:
        return {
            "success": False,
            "error": "Task is assigned to another agent",
            "task_id": task.id,
            "assigned_to": task_owner,
            "canonical_surface": "htask",
        }

    await db.hierarchicaltask.update(
        where={"id": task.id},
        data={"owner": agent_id, "status": "IN_PROGRESS", "startedAt": datetime.now(UTC)},
    )
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task.id,
        event_type="claim",
        payload={"agent_id": agent_id, "legacy_tool": "rlm_task_claim"},
    )
    return {
        "success": True,
        "task_id": task.id,
        "htask_id": task.id,
        "title": task.title,
        "description": task.description,
        "status": "claimed",
        "priority": htask_priority_to_legacy(task.priority),
        "htask_priority": task.priority,
        "deadline": _iso_value(_task_attr(task, "etaTarget")),
        "assigned_to": agent_id,
        "was_preassigned": task_owner == agent_id,
        "canonical_surface": "htask",
        "compat_mode": await get_task_compat_mode(swarm_id),
        "message": "Task claimed as hierarchical task",
    }


async def complete_task_as_htask(
    *,
    swarm_id: str,
    agent_id: str,
    task_id: str,
    result: Any | None = None,
    success: bool = True,
) -> dict[str, Any]:
    """Complete or fail a canonical htask through the legacy task surface."""
    db = await get_db()
    task = await db.hierarchicaltask.find_first(
        where={"id": task_id, "swarmId": swarm_id, "archivedAt": None}
    )
    if not task:
        return {"success": False, "error": "Task not found", "canonical_surface": "htask"}
    task_owner = _task_attr(task, "owner")
    if task_owner != agent_id:
        return {
            "success": False,
            "error": "Task not assigned to agent",
            "task_id": task_id,
            "assigned_to": task_owner,
            "canonical_surface": "htask",
        }

    parsed_result = _parse_result(result)
    if success:
        evidence = [
            {
                "type": "legacy_task_result",
                "description": "Completed through rlm_task_complete compatibility wrapper",
            }
        ]
        completion = await complete_htask(
            swarm_id=swarm_id,
            task_id=task_id,
            evidence=evidence,
            result=parsed_result,
            create_memory=True,
        )
        completion["canonical_surface"] = "htask"
        completion["compat_mode"] = await get_task_compat_mode(swarm_id)
        completion["status"] = "completed" if completion.get("success") else task.status.lower()
        completion["completed"] = bool(completion.get("success"))
        completion["htask_id"] = task_id
        completion.setdefault("message", "Task completed successfully")
        return completion

    update_data: dict[str, Any] = {
        "status": "FAILED",
        "completedAt": datetime.now(UTC),
    }
    if parsed_result is not None:
        update_data["result"] = Json(parsed_result)
        update_data["error"] = json.dumps(parsed_result) if not isinstance(parsed_result, str) else parsed_result

    await db.hierarchicaltask.update(where={"id": task_id}, data=update_data)
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task_id,
        event_type="fail",
        payload={"agent_id": agent_id, "result": parsed_result, "legacy_tool": "rlm_task_complete"},
    )
    return {
        "success": True,
        "task_id": task_id,
        "htask_id": task_id,
        "status": "failed",
        "canonical_surface": "htask",
        "compat_mode": await get_task_compat_mode(swarm_id),
        "message": "Task marked as failed",
    }


async def list_tasks_as_htask(
    *,
    swarm_id: str,
    status: str | None = None,
    assigned_to: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    enhanced: bool = False,
) -> dict[str, Any]:
    """List canonical htasks through legacy list surfaces."""
    db = await get_db()
    limit = min(max(1, int(limit or 50)), 100)
    where: dict[str, Any] = {"swarmId": swarm_id, "level": "N3_TASK", "archivedAt": None}
    mapped_status = _legacy_status_to_htask(status)
    if mapped_status:
        where["status"] = mapped_status
    if assigned_to:
        where["owner"] = assigned_to
    if cursor:
        where["id"] = {"gt": cursor}

    tasks = await db.hierarchicaltask.find_many(
        where=where,
        order=[{"createdAt": "asc"}, {"id": "asc"}] if enhanced else [{"priority": "asc"}, {"createdAt": "asc"}],
        take=limit + 1 if enhanced else limit,
    )
    has_more = enhanced and len(tasks) > limit
    if has_more:
        tasks = tasks[:limit]
    next_cursor = tasks[-1].id if tasks and has_more else None

    if enhanced:
        items = [
            {
                "id": task.id,
                "title": task.title,
                "status": _htask_status_to_legacy(task.status),
                "updated_at": _iso_value(_latest_task_time(task)),
                "owner": _task_attr(task, "owner"),
                "canonical_surface": "htask",
                "level": task.level,
            }
            for task in tasks
        ]
        return {
            "tasks": items,
            "total": len(items),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "canonical_surface": "htask",
            "compat_mode": await get_task_compat_mode(swarm_id),
        }

    return {
        "tasks": [_legacy_task_dict(task) for task in tasks],
        "total": len(tasks),
        "canonical_surface": "htask",
        "compat_mode": await get_task_compat_mode(swarm_id),
    }


async def get_task_stats_as_htask(swarm_id: str) -> dict[str, Any]:
    """Return legacy task stats from canonical htask rows."""
    db = await get_db()
    tasks = await db.hierarchicaltask.find_many(
        where={"swarmId": swarm_id, "level": "N3_TASK", "archivedAt": None}
    )
    counts = {
        "done": 0,
        "in_progress": 0,
        "blocked": 0,
        "pending": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for task in tasks:
        status = str(task.status).upper()
        if status == "COMPLETED":
            counts["done"] += 1
        elif status == "IN_PROGRESS":
            counts["in_progress"] += 1
        elif status == "BLOCKED":
            counts["blocked"] += 1
        elif status == "FAILED":
            counts["failed"] += 1
        elif status == "CANCELLED":
            counts["cancelled"] += 1
        else:
            counts["pending"] += 1
    return {"swarm_id": swarm_id, **counts, "total": len(tasks), "canonical_surface": "htask"}


async def unclaim_task_as_htask(
    *,
    swarm_id: str,
    task_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Return an in-progress htask to pending through the legacy surface."""
    db = await get_db()
    task = await db.hierarchicaltask.find_first(where={"id": task_id, "swarmId": swarm_id})
    if not task:
        return {"success": False, "error": "Task not found", "canonical_surface": "htask"}
    if task.status != "IN_PROGRESS":
        return {
            "success": False,
            "error": f"Task is {task.status}, cannot unclaim",
            "canonical_surface": "htask",
        }
    await db.hierarchicaltask.update(
        where={"id": task_id},
        data={"status": "PENDING", "owner": "unassigned", "startedAt": None},
    )
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task_id,
        event_type="unclaim",
        payload={"reason": reason, "legacy_tool": "rlm_task_unclaim"},
    )
    return {
        "success": True,
        "task_id": task_id,
        "previous_status": task.status,
        "previous_agent": _task_attr(task, "owner"),
        "reason": reason,
        "canonical_surface": "htask",
        "message": "Task unclaimed and returned to PENDING",
    }


async def recover_stuck_tasks_as_htask(
    *,
    swarm_id: str,
    stuck_threshold_minutes: int = 30,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Find and optionally recover in-progress htasks with stale start times."""
    db = await get_db()
    threshold = datetime.now(UTC) - timedelta(minutes=stuck_threshold_minutes)
    tasks = await db.hierarchicaltask.find_many(
        where={
            "swarmId": swarm_id,
            "level": "N3_TASK",
            "status": "IN_PROGRESS",
            "startedAt": {"lt": threshold},
            "archivedAt": None,
        }
    )
    recoveries: list[dict[str, Any]] = []
    if not dry_run:
        for task in tasks:
            recoveries.append(
                await unclaim_task_as_htask(
                    swarm_id=swarm_id,
                    task_id=task.id,
                    reason="Auto-recovered: stuck threshold exceeded",
                )
            )
    return {
        "success": True,
        "stuck_count": len(tasks),
        "stuck_tasks": [_legacy_task_dict(task) for task in tasks],
        "recovered": recoveries if not dry_run else None,
        "dry_run": dry_run,
        "canonical_surface": "htask",
    }


async def list_task_events_as_htask(
    *,
    swarm_id: str,
    since: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List htask events through the legacy rlm_task_events shape."""
    db = await get_db()
    where: dict[str, Any] = {"swarmId": swarm_id}
    if since:
        where["createdAt"] = {"gte": _parse_datetime(since)}
    events = await db.htaskevent.find_many(
        where=where,
        order={"createdAt": "desc"},
        take=limit,
    )
    return {
        "events": [
            {
                "event_id": event.id,
                "event_type": event.eventType,
                "task_id": event.taskId,
                "timestamp": event.createdAt.isoformat() if event.createdAt else None,
                "payload": event.payload,
                "canonical_surface": "htask",
            }
            for event in events
        ],
        "total": len(events),
        "canonical_surface": "htask",
    }


async def reassign_task_as_htask(
    *,
    swarm_id: str,
    task_id: str,
    new_agent_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Reassign an htask through the legacy rlm_task_reassign surface."""
    db = await get_db()
    task = await db.hierarchicaltask.find_first(where={"id": task_id, "swarmId": swarm_id})
    if not task:
        return {"success": False, "error": f"Task '{task_id}' not found in swarm '{swarm_id}'"}
    if task.status == "IN_PROGRESS" and not force:
        return {"success": False, "error": "Cannot reassign IN_PROGRESS task. Use force=true to override."}
    await db.hierarchicaltask.update(
        where={"id": task_id},
        data={"owner": new_agent_id or "unassigned", "status": "PENDING"},
    )
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task_id,
        event_type="reassign",
        payload={"new_agent_id": new_agent_id, "legacy_tool": "rlm_task_reassign"},
    )
    return {
        "success": True,
        "task_id": task_id,
        "previous_status": task.status,
        "new_status": "PENDING",
        "assigned_to": new_agent_id or "(unassigned)",
        "canonical_surface": "htask",
    }


async def delete_task_as_htask(
    *,
    swarm_id: str,
    task_id: str,
    force: bool = False,
) -> dict[str, Any]:
    """Archive an htask through the legacy rlm_task_delete surface."""
    db = await get_db()
    task = await db.hierarchicaltask.find_first(where={"id": task_id, "swarmId": swarm_id})
    if not task:
        return {"success": False, "error": f"Task '{task_id}' not found in swarm '{swarm_id}'"}
    allowed_statuses = {"PENDING", "FAILED", "CANCELLED"}
    if force:
        allowed_statuses.update({"COMPLETED", "IN_PROGRESS", "BLOCKED"})
    if task.status not in allowed_statuses:
        return {"success": False, "error": f"Cannot delete task with status '{task.status}'. Use force=true."}
    await db.hierarchicaltask.update(
        where={"id": task_id},
        data={"archivedAt": datetime.now(UTC), "status": "CANCELLED" if task.status != "COMPLETED" else task.status},
    )
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task_id,
        event_type="delete",
        payload={"force": force, "legacy_tool": "rlm_task_delete"},
    )
    return {
        "success": True,
        "task_id": task_id,
        "title": task.title,
        "status": task.status,
        "canonical_surface": "htask",
        "message": f"Task '{task.title}' archived successfully",
    }


async def update_task_as_htask(
    *,
    swarm_id: str,
    task_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Update an htask through the legacy rlm_task_update surface."""
    db = await get_db()
    task = await db.hierarchicaltask.find_first(where={"id": task_id, "swarmId": swarm_id})
    if not task:
        return {"success": False, "error": f"Task '{task_id}' not found in swarm '{swarm_id}'"}

    update_data: dict[str, Any] = {}
    if "title" in params:
        update_data["title"] = params["title"]
    if "description" in params:
        update_data["description"] = params["description"]
    if "priority" in params:
        update_data["priority"] = legacy_priority_to_htask(params["priority"])
    if "status" in params:
        status = _legacy_status_to_htask(params["status"])
        valid = {"PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED", "BLOCKED"}
        if status not in valid:
            return {"success": False, "error": f"Invalid status '{params['status']}'"}
        update_data["status"] = status
        if status in {"COMPLETED", "FAILED"}:
            update_data["completedAt"] = datetime.now(UTC)

    if not update_data:
        return {"success": False, "error": "No fields to update. Provide: title, description, priority, or status"}

    updated = await db.hierarchicaltask.update(where={"id": task_id}, data=update_data)
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task_id,
        event_type="update",
        payload={"fields": list(update_data.keys()), "legacy_tool": "rlm_task_update"},
    )
    return {
        "success": True,
        "task_id": task_id,
        "updated_fields": list(update_data.keys()),
        "canonical_surface": "htask",
        "task": {
            "id": updated.id,
            "title": updated.title,
            "status": _htask_status_to_legacy(updated.status),
            "priority": htask_priority_to_legacy(updated.priority),
        },
    }
