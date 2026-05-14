"""Task-level webhook events for swarm and hierarchical task coordination.

Extends the integrator webhook infrastructure to emit events when tasks
change status (created, claimed, completed, failed, blocked, etc.).
These webhooks enable external clients (like Vutler) to implement
closed-loop verification, watchdog, and smart routing.
"""

import asyncio
import logging
from typing import Any

from ..db import get_db
from .integrator_webhooks import create_webhook_event

logger = logging.getLogger(__name__)

# ============ EVENT TYPE CONSTANTS ============

EVENT_TASK_CREATED = "task.created"
EVENT_TASK_CLAIMED = "task.claimed"
EVENT_TASK_COMPLETED = "task.completed"
EVENT_TASK_FAILED = "task.failed"
EVENT_TASK_BLOCKED = "task.blocked"
EVENT_TASK_TIMEOUT = "task.timeout"
EVENT_HTASK_COMPLETED = "htask.completed"
EVENT_HTASK_BLOCKED = "htask.blocked"
EVENT_HTASK_CLOSURE_READY = "htask.closure_ready"


# ============ WORKSPACE RESOLUTION ============


async def _resolve_workspace_for_swarm(swarm_id: str) -> str | None:
    """Resolve the IntegratorWorkspace ID from a swarm ID.

    Path: AgentSwarm -> Project -> IntegratorClient -> IntegratorWorkspace

    Returns:
        Workspace ID if found and has webhook URL, None otherwise.
    """
    try:
        db = await get_db()

        swarm = await db.agentswarm.find_first(
            where={"id": swarm_id},
            include={
                "project": {
                    "include": {
                        "integratorClient": True,
                    }
                }
            },
        )

        if not swarm or not swarm.project:
            return None

        client = swarm.project.integratorClient
        if not client:
            return None

        return client.workspaceId
    except Exception as e:
        logger.warning(f"Failed to resolve workspace for swarm {swarm_id}: {e}")
        return None


async def _resolve_workspace_for_htask(swarm_id: str) -> str | None:
    """Resolve workspace for htask (same path as swarm tasks)."""
    return await _resolve_workspace_for_swarm(swarm_id)


# ============ FIRE-AND-FORGET EMITTER ============


async def _emit(swarm_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Resolve workspace and emit webhook event. Safe to call as fire-and-forget."""
    try:
        workspace_id = await _resolve_workspace_for_swarm(swarm_id)
        if not workspace_id:
            return
        await create_webhook_event(workspace_id, event_type, data)
    except Exception as e:
        logger.warning(f"Failed to emit {event_type} webhook for swarm {swarm_id}: {e}")


def emit_async(swarm_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Schedule webhook emission as a background task. Non-blocking."""
    asyncio.create_task(_emit(swarm_id, event_type, data))


# ============ SWARM TASK CONVENIENCE FUNCTIONS ============


def emit_task_created(
    swarm_id: str,
    task_id: str,
    title: str,
    agent_id: str | None = None,
    priority: str | None = None,
) -> None:
    """Emit task.created webhook."""
    emit_async(swarm_id, EVENT_TASK_CREATED, {
        "task_id": task_id,
        "swarm_id": swarm_id,
        "title": title,
        "agent_id": agent_id,
        "priority": priority,
    })


def emit_task_claimed(
    swarm_id: str,
    task_id: str,
    agent_id: str,
) -> None:
    """Emit task.claimed webhook."""
    emit_async(swarm_id, EVENT_TASK_CLAIMED, {
        "task_id": task_id,
        "swarm_id": swarm_id,
        "agent_id": agent_id,
    })


def emit_task_completed(
    swarm_id: str,
    task_id: str,
    agent_id: str,
    status: str = "COMPLETED",
    result: Any = None,
) -> None:
    """Emit task.completed or task.failed webhook based on status."""
    event_type = EVENT_TASK_COMPLETED if status == "COMPLETED" else EVENT_TASK_FAILED
    emit_async(swarm_id, event_type, {
        "task_id": task_id,
        "swarm_id": swarm_id,
        "agent_id": agent_id,
        "status": status,
        "result": result,
    })


def emit_task_timeout(
    swarm_id: str,
    task_id: str,
    agent_id: str | None,
    reason: str = "execution_timeout",
    stalled_for_seconds: int | None = None,
) -> None:
    """Emit task.timeout webhook — task exceeded deadline or was never claimed."""
    emit_async(swarm_id, EVENT_TASK_TIMEOUT, {
        "task_id": task_id,
        "swarm_id": swarm_id,
        "agent_id": agent_id,
        "reason": reason,  # "execution_timeout" | "never_claimed" | "unclaimed" | "htask_stalled"
        "stalled_for_seconds": stalled_for_seconds,
    })


# ============ HTASK CONVENIENCE FUNCTIONS ============


def emit_htask_completed(
    swarm_id: str,
    task_id: str,
    owner: str,
    level: str,
    evidence_provided: list | None = None,
    result: Any = None,
) -> None:
    """Emit htask.completed webhook."""
    emit_async(swarm_id, EVENT_HTASK_COMPLETED, {
        "task_id": task_id,
        "swarm_id": swarm_id,
        "owner": owner,
        "level": level,
        "evidence_provided": evidence_provided,
        "result": result,
    })


def emit_htask_blocked(
    swarm_id: str,
    task_id: str,
    owner: str,
    blocker_type: str | None = None,
    blocker_reason: str | None = None,
) -> None:
    """Emit htask.blocked webhook."""
    emit_async(swarm_id, EVENT_HTASK_BLOCKED, {
        "task_id": task_id,
        "swarm_id": swarm_id,
        "owner": owner,
        "blocker_type": blocker_type,
        "blocker_reason": blocker_reason,
    })


def emit_htask_closure_ready(
    swarm_id: str,
    task_id: str,
    owner: str,
    level: str,
    waiver: bool = False,
) -> None:
    """Emit htask.closure_ready webhook (parent closed after children complete)."""
    emit_async(swarm_id, EVENT_HTASK_CLOSURE_READY, {
        "task_id": task_id,
        "swarm_id": swarm_id,
        "owner": owner,
        "level": level,
        "closed_with_waiver": waiver,
    })
