"""Hierarchical Task Coordinator Service.

Main service for managing hierarchical tasks with 4-level hierarchy:
- N0: Initiative (optional, big program)
- N1: Feature (business deliverable)
- N2: Workstream (API, Frontend, QA, etc.)
- N3: Task (atomic, single owner)

Implements:
- Hard gate closure rules
- Blocking propagation
- Policy-driven behavior
- Anti-cycle validation
- Evidence management
"""

import logging
from datetime import UTC, datetime
from typing import Any

try:
    from prisma import Json
except ImportError:
    def Json(x):  # noqa: N802
        return x

from ..db import get_db
from .htask_events import log_htask_event
from .htask_policy import (
    allows_hard_delete,
    allows_structural_update,
    get_max_depth,
    get_policy,
    is_blocking_default,
    requires_evidence_on_complete,
)

logger = logging.getLogger(__name__)

# Standard workstreams for create_feature_with_workstreams
DEFAULT_WORKSTREAMS = [
    "API",
    "FRONTEND",
    "QA",
    "BUGFIX_HARDENING",
    "DEPLOY_PROD_VERIFY",
]

# Update whitelist by status
UPDATE_WHITELIST = {
    "PENDING": [
        "title", "description", "owner", "priority", "etaTarget",
        "executionTarget", "acceptanceCriteria", "contextRefs",
        "evidenceRequired", "isBlocking",
    ],
    "IN_PROGRESS": [
        "description", "etaTarget", "acceptanceCriteria",
        "contextRefs", "evidenceProvided",
    ],
    "BLOCKED": [
        "blockerReason", "requiredInput", "etaRecovery", "escalationTo",
    ],
    "COMPLETED": [],
    "FAILED": ["error"],
    "CANCELLED": [],
}

# Structural fields (admin only with allowStructuralUpdate)
STRUCTURAL_FIELDS = ["level", "parentId", "sequenceNumber"]


# =============================================================================
# VALIDATION HELPERS
# =============================================================================


async def _validate_no_cycle(task_id: str | None, new_parent_id: str) -> bool:
    """Validate that setting new_parent_id won't create a cycle.

    Args:
        task_id: The task being updated (None for new tasks)
        new_parent_id: The proposed parent ID

    Returns:
        True if no cycle would be created
    """
    if not new_parent_id:
        return True

    if task_id and task_id == new_parent_id:
        return False

    db = await get_db()
    visited = {task_id} if task_id else set()
    current = new_parent_id

    while current:
        if current in visited:
            return False
        visited.add(current)

        parent = await db.hierarchicaltask.find_unique(where={"id": current})
        if not parent:
            break
        current = parent.parentId

    return True


async def _calculate_depth(task_id: str) -> int:
    """Calculate the depth of a task in the hierarchy.

    Args:
        task_id: The task ID

    Returns:
        Depth (1 for root tasks)
    """
    db = await get_db()
    depth = 1
    current = task_id

    while current:
        task = await db.hierarchicaltask.find_unique(where={"id": current})
        if not task or not task.parentId:
            break
        depth += 1
        current = task.parentId

    return depth


async def _get_next_sequence(swarm_id: str, parent_id: str | None) -> int:
    """Get the next sequence number for a new child task.

    Args:
        swarm_id: The swarm ID
        parent_id: The parent task ID (or None for root)

    Returns:
        Next sequence number
    """
    db = await get_db()

    # Find max sequence number among siblings
    siblings = await db.hierarchicaltask.find_many(
        where={"swarmId": swarm_id, "parentId": parent_id},
        order={"sequenceNumber": "desc"},
        take=1,
    )

    if siblings:
        return siblings[0].sequenceNumber + 1
    return 1


# =============================================================================
# TASK CREATION
# =============================================================================


async def create_htask(
    swarm_id: str,
    level: str,
    title: str,
    description: str,
    owner: str,
    parent_id: str | None = None,
    priority: str = "P1",
    eta_target: datetime | None = None,
    acceptance_criteria: list[dict] | None = None,
    context_refs: list[str] | None = None,
    evidence_required: list[dict] | None = None,
    workstream_type: str | None = None,
    custom_workstream_type: str | None = None,
    execution_target: str | None = None,
    is_blocking: bool | None = None,
    sequence_number: int | None = None,
) -> dict[str, Any]:
    """Create a hierarchical task.

    Args:
        swarm_id: The swarm ID
        level: Task level (N0_INITIATIVE, N1_FEATURE, N2_WORKSTREAM, N3_TASK)
        title: Task title
        description: Task description (objective + scope)
        owner: Task owner (never null)
        parent_id: Parent task ID
        priority: Priority (P0, P1, P2)
        eta_target: Target completion date
        acceptance_criteria: List of acceptance criteria
        context_refs: List of context references (docs, repos)
        evidence_required: List of required evidence types
        workstream_type: Workstream type (for N2 level)
        custom_workstream_type: Custom workstream name
        execution_target: Execution target (LOCAL, CLOUD, HYBRID, EXTERNAL)
        is_blocking: Whether this task blocks parent on failure
        sequence_number: Explicit sequence number (auto-generated if None)

    Returns:
        Created task dict or error
    """
    # Validate owner (never null)
    if not owner or not owner.strip():
        return {"success": False, "error": "owner is required and cannot be empty"}

    # Get policy
    policy = await get_policy(swarm_id)

    # Validate level
    valid_levels = ["N0_INITIATIVE", "N1_FEATURE", "N2_WORKSTREAM", "N3_TASK"]
    if level not in valid_levels:
        return {"success": False, "error": f"Invalid level '{level}'. Must be one of {valid_levels}"}

    # Validate hierarchy constraints
    if level == "N0_INITIATIVE" and parent_id:
        return {"success": False, "error": "N0_INITIATIVE cannot have a parent"}

    if level == "N2_WORKSTREAM" and not workstream_type:
        return {"success": False, "error": "workstream_type is required for N2_WORKSTREAM"}

    # Validate max depth
    if parent_id:
        parent_depth = await _calculate_depth(parent_id)
        max_depth = get_max_depth(policy)
        if parent_depth >= max_depth:
            return {
                "success": False,
                "error": f"Max depth {max_depth} exceeded. Parent is at depth {parent_depth}",
            }

    # Validate no cycle
    if parent_id and not await _validate_no_cycle(None, parent_id):
        return {"success": False, "error": "Cycle detected in task hierarchy"}

    # Auto-generate sequence number if not provided
    if sequence_number is None:
        sequence_number = await _get_next_sequence(swarm_id, parent_id)

    # Default isBlocking from policy
    if is_blocking is None:
        is_blocking = is_blocking_default(policy)

    db = await get_db()

    # Create task
    # NOTE: Prisma-Python uses direct FK fields, NOT nested relation writes like Prisma-JS
    task = await db.hierarchicaltask.create(
        data={
            "swarmId": swarm_id,  # Use direct FK (Prisma-Python syntax)
            "level": level,
            "parentId": parent_id,
            "sequenceNumber": sequence_number,
            "workstreamType": workstream_type,
            "customWorkstreamType": custom_workstream_type,
            "title": title,
            "description": description,
            "owner": owner.strip(),
            "executionTarget": execution_target,
            "priority": priority,
            "etaTarget": eta_target,
            "acceptanceCriteria": Json(acceptance_criteria or []),  # Wrap empty list in Json()
            "contextRefs": context_refs or [],
            "evidenceRequired": Json(evidence_required or []),  # Wrap empty list in Json()
            "status": "PENDING",
            "isBlocking": is_blocking,
        }
    )

    # Log event
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task.id,
        event_type="create",
        payload={
            "level": level,
            "title": title,
            "owner": owner,
            "parent_id": parent_id,
        },
    )

    logger.info(f"Created htask {task.id} ({level}) in swarm {swarm_id}")

    return {
        "success": True,
        "task_id": task.id,
        "level": level,
        "title": title,
        "owner": owner,
        "sequence_number": sequence_number,
    }


async def create_feature_with_workstreams(
    swarm_id: str,
    title: str,
    description: str,
    owner: str,
    parent_id: str | None = None,
    include_workstreams: list[str] | None = None,
    workstream_owners: dict[str, str] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Create a Feature (N1) with standard workstreams (N2).

    Args:
        swarm_id: The swarm ID
        title: Feature title
        description: Feature description
        owner: Feature owner
        parent_id: Parent initiative ID (optional)
        include_workstreams: List of workstream types to create (default: all standard)
        workstream_owners: Dict mapping workstream type to owner
        **kwargs: Additional args for the feature

    Returns:
        Feature and workstreams creation result
    """
    if include_workstreams is None:
        include_workstreams = DEFAULT_WORKSTREAMS

    if workstream_owners is None:
        workstream_owners = {}

    # Create feature
    feature_result = await create_htask(
        swarm_id=swarm_id,
        level="N1_FEATURE",
        title=title,
        description=description,
        owner=owner,
        parent_id=parent_id,
        **kwargs,
    )

    if not feature_result.get("success"):
        return feature_result

    feature_id = feature_result["task_id"]

    # Create workstreams
    workstreams = []
    for ws_type in include_workstreams:
        ws_owner = workstream_owners.get(ws_type, owner)

        ws_result = await create_htask(
            swarm_id=swarm_id,
            level="N2_WORKSTREAM",
            title=f"{title} - {ws_type}",
            description=f"Workstream {ws_type} for feature: {title}",
            owner=ws_owner,
            parent_id=feature_id,
            workstream_type=ws_type,
        )

        workstreams.append({
            "workstream_type": ws_type,
            "task_id": ws_result.get("task_id"),
            "success": ws_result.get("success", False),
            "error": ws_result.get("error"),
        })

    return {
        "success": True,
        "feature_id": feature_id,
        "title": title,
        "owner": owner,
        "workstreams": workstreams,
    }


# =============================================================================
# TASK RETRIEVAL
# =============================================================================


async def get_htask(
    swarm_id: str,
    task_id: str,
    include_children: bool = True,
) -> dict[str, Any]:
    """Get a task with optional children.

    Args:
        swarm_id: The swarm ID
        task_id: The task ID
        include_children: Whether to include direct children

    Returns:
        Task dict or error
    """
    db = await get_db()

    task = await db.hierarchicaltask.find_first(
        where={"id": task_id, "swarmId": swarm_id}
    )

    if not task:
        return {"success": False, "error": f"Task {task_id} not found"}

    result = _task_to_dict(task)

    if include_children:
        children = await db.hierarchicaltask.find_many(
            where={"swarmId": swarm_id, "parentId": task_id, "archivedAt": None},
            order={"sequenceNumber": "asc"},
        )
        result["children"] = [_task_to_dict(c) for c in children]

    return {"success": True, "task": result}


async def get_htask_tree(
    swarm_id: str,
    root_id: str | None = None,
    include_completed: bool = False,
    max_depth: int = 4,
) -> dict[str, Any]:
    """Get full hierarchical tree from a root node.

    Args:
        swarm_id: The swarm ID
        root_id: Root task ID (None for all roots)
        include_completed: Include completed tasks
        max_depth: Maximum depth to traverse

    Returns:
        Tree structure with progress rollups
    """
    db = await get_db()

    # Get all tasks for this swarm
    where: dict[str, Any] = {"swarmId": swarm_id}
    if not include_completed:
        where["status"] = {"not_in": ["COMPLETED", "CANCELLED"]}
    if root_id is None:
        where["archivedAt"] = None

    all_tasks = await db.hierarchicaltask.find_many(
        where=where,
        order={"sequenceNumber": "asc"},
    )

    # Build tree structure
    task_map = {t.id: _task_to_dict(t) for t in all_tasks}
    roots = []

    for task_id, task_dict in task_map.items():
        task_dict["children"] = []

    for task_id, task_dict in task_map.items():
        parent_id = task_dict.get("parent_id")
        if parent_id and parent_id in task_map:
            task_map[parent_id]["children"].append(task_dict)
        elif not parent_id or (root_id and task_id == root_id):
            if root_id is None or task_id == root_id:
                roots.append(task_dict)

    # Calculate progress for each node
    def calculate_progress(node: dict) -> dict:
        children = node.get("children", [])
        if not children:
            # Leaf node
            node["progress"] = {
                "total": 1,
                "completed": 1 if node.get("status") == "COMPLETED" else 0,
                "in_progress": 1 if node.get("status") == "IN_PROGRESS" else 0,
                "blocked": 1 if node.get("status") == "BLOCKED" else 0,
                "pending": 1 if node.get("status") == "PENDING" else 0,
                "failed": 1 if node.get("status") == "FAILED" else 0,
            }
        else:
            totals = {
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "blocked": 0,
                "pending": 0,
                "failed": 0,
            }
            for child in children:
                calculate_progress(child)
                child_progress = child.get("progress", {})
                for key in totals:
                    totals[key] += child_progress.get(key, 0)

            totals["percent"] = round(
                (totals["completed"] / totals["total"] * 100) if totals["total"] > 0 else 0,
                1
            )
            node["progress"] = totals

        return node

    for root in roots:
        calculate_progress(root)

    if root_id and roots:
        return {"success": True, "tree": roots[0]}

    return {"success": True, "trees": roots, "total_roots": len(roots)}


def _task_to_dict(task) -> dict[str, Any]:
    """Convert a task object to dict."""
    return {
        "id": task.id,
        "level": task.level,
        "parent_id": task.parentId,
        "sequence_number": task.sequenceNumber,
        "workstream_type": task.workstreamType,
        "custom_workstream_type": task.customWorkstreamType,
        "title": task.title,
        "description": task.description,
        "owner": task.owner,
        "execution_target": task.executionTarget,
        "priority": task.priority,
        "eta_target": task.etaTarget.isoformat() if task.etaTarget else None,
        "acceptance_criteria": task.acceptanceCriteria,
        "context_refs": task.contextRefs,
        "evidence_required": task.evidenceRequired,
        "evidence_provided": task.evidenceProvided,
        "status": task.status,
        "is_blocking": task.isBlocking,
        "blocker_type": task.blockerType,
        "blocker_reason": task.blockerReason,
        "blocked_by_task_id": task.blockedByTaskId,
        "required_input": task.requiredInput,
        "eta_recovery": task.etaRecovery.isoformat() if task.etaRecovery else None,
        "escalation_to": task.escalationTo,
        "blocked_at": task.blockedAt.isoformat() if task.blockedAt else None,
        "waiver_reason": task.waiverReason,
        "waiver_approved_by": task.waiverApprovedBy,
        "waiver_approved_at": task.waiverApprovedAt.isoformat() if task.waiverApprovedAt else None,
        "result": task.result,
        "error": task.error,
        "created_at": task.createdAt.isoformat() if task.createdAt else None,
        "updated_at": task.updatedAt.isoformat() if task.updatedAt else None,
        "started_at": task.startedAt.isoformat() if task.startedAt else None,
        "completed_at": task.completedAt.isoformat() if task.completedAt else None,
        "archived_at": task.archivedAt.isoformat() if task.archivedAt else None,
    }


# =============================================================================
# BLOCKING & PROPAGATION
# =============================================================================


async def block_task(
    swarm_id: str,
    task_id: str,
    blocker_type: str,
    blocker_reason: str,
    blocked_by_task_id: str | None = None,
    required_input: str | None = None,
    eta_recovery: datetime | None = None,
    escalation_to: str | None = None,
) -> dict[str, Any]:
    """Block a task with full blocking payload.

    Args:
        swarm_id: The swarm ID
        task_id: The task ID to block
        blocker_type: Type of blocker (TECH, DEPENDENCY, etc.)
        blocker_reason: Reason for blocking (1-2 sentences)
        blocked_by_task_id: ID of blocking task (if DEPENDENCY)
        required_input: What's needed to unblock
        eta_recovery: Estimated recovery date
        escalation_to: Escalation owner

    Returns:
        Result with affected ancestor IDs
    """
    # Validate required fields
    if not blocker_type:
        return {"success": False, "error": "blocker_type is required"}
    if not blocker_reason:
        return {"success": False, "error": "blocker_reason is required"}

    valid_blocker_types = ["TECH", "DEPENDENCY", "ACCESS", "PRODUCT", "INFRA", "SECURITY", "OTHER"]
    if blocker_type not in valid_blocker_types:
        return {"success": False, "error": f"Invalid blocker_type. Must be one of {valid_blocker_types}"}

    db = await get_db()

    # Get task
    task = await db.hierarchicaltask.find_first(
        where={"id": task_id, "swarmId": swarm_id}
    )
    if not task:
        return {"success": False, "error": f"Task {task_id} not found"}

    # Update task
    await db.hierarchicaltask.update(
        where={"id": task_id},
        data={
            "status": "BLOCKED",
            "blockerType": blocker_type,
            "blockerReason": blocker_reason,
            "blockedByTaskId": blocked_by_task_id,
            "requiredInput": required_input,
            "etaRecovery": eta_recovery,
            "escalationTo": escalation_to,
            "blockedAt": datetime.now(UTC),
        },
    )

    # Propagate if blocking
    affected = []
    if task.isBlocking:
        affected = await _propagate_blocked_status(swarm_id, task_id)

    # Log event
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task_id,
        event_type="block",
        payload={
            "blocker_type": blocker_type,
            "blocker_reason": blocker_reason,
            "affected_ancestors": affected,
        },
    )

    logger.info(f"Blocked htask {task_id} ({blocker_type}), affected ancestors: {len(affected)}")

    return {
        "success": True,
        "task_id": task_id,
        "blocker_type": blocker_type,
        "affected_ancestors": affected,
    }


async def _propagate_blocked_status(swarm_id: str, task_id: str) -> list[str]:
    """Propagate BLOCKED status to all ancestors.

    Args:
        swarm_id: The swarm ID
        task_id: The blocked task ID

    Returns:
        List of affected ancestor IDs
    """
    db = await get_db()
    affected = []

    task = await db.hierarchicaltask.find_unique(where={"id": task_id})
    if not task:
        return affected

    current_id = task.parentId

    while current_id:
        parent = await db.hierarchicaltask.find_unique(where={"id": current_id})
        if not parent:
            break

        # Don't update if already in a terminal state
        if parent.status in ("BLOCKED", "COMPLETED", "CANCELLED"):
            current_id = parent.parentId
            continue

        # Update parent to BLOCKED
        await db.hierarchicaltask.update(
            where={"id": parent.id},
            data={"status": "BLOCKED"},
        )
        affected.append(parent.id)

        current_id = parent.parentId

    return affected


async def unblock_task(swarm_id: str, task_id: str) -> dict[str, Any]:
    """Clear blocking state from a task.

    Args:
        swarm_id: The swarm ID
        task_id: The task ID to unblock

    Returns:
        Result with re-evaluated ancestors
    """
    db = await get_db()

    task = await db.hierarchicaltask.find_first(
        where={"id": task_id, "swarmId": swarm_id}
    )
    if not task:
        return {"success": False, "error": f"Task {task_id} not found"}

    if task.status != "BLOCKED":
        return {"success": False, "error": f"Task is not blocked (status: {task.status})"}

    # Clear blocking fields and set to IN_PROGRESS
    await db.hierarchicaltask.update(
        where={"id": task_id},
        data={
            "status": "IN_PROGRESS",
            "blockerType": None,
            "blockerReason": None,
            "blockedByTaskId": None,
            "requiredInput": None,
            "etaRecovery": None,
            "escalationTo": None,
            "blockedAt": None,
            "startedAt": datetime.now(UTC),
        },
    )

    # Re-evaluate ancestor statuses
    reevaluated = await _reevaluate_ancestor_status(swarm_id, task_id)

    # Log event
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task_id,
        event_type="unblock",
        payload={"reevaluated_ancestors": reevaluated},
    )

    logger.info(f"Unblocked htask {task_id}, reevaluated ancestors: {len(reevaluated)}")

    return {
        "success": True,
        "task_id": task_id,
        "new_status": "IN_PROGRESS",
        "reevaluated_ancestors": reevaluated,
    }


async def _reevaluate_ancestor_status(swarm_id: str, task_id: str) -> list[str]:
    """Re-evaluate ancestor statuses after unblocking.

    If all children of a parent are no longer blocked, the parent
    can transition from BLOCKED to IN_PROGRESS.

    Args:
        swarm_id: The swarm ID
        task_id: The unblocked task ID

    Returns:
        List of ancestor IDs that were re-evaluated
    """
    db = await get_db()
    reevaluated = []

    task = await db.hierarchicaltask.find_unique(where={"id": task_id})
    if not task or not task.parentId:
        return reevaluated

    current_id = task.parentId

    while current_id:
        parent = await db.hierarchicaltask.find_unique(where={"id": current_id})
        if not parent:
            break

        # Only re-evaluate BLOCKED parents
        if parent.status != "BLOCKED":
            current_id = parent.parentId
            continue

        # Check if any children are still blocking
        children = await db.hierarchicaltask.find_many(
            where={"swarmId": swarm_id, "parentId": parent.id, "archivedAt": None}
        )

        has_blocking_child = any(
            c.status in ("BLOCKED", "FAILED") and c.isBlocking
            for c in children
        )

        if not has_blocking_child:
            # Unblock parent
            await db.hierarchicaltask.update(
                where={"id": parent.id},
                data={"status": "IN_PROGRESS"},
            )
            reevaluated.append(parent.id)

        current_id = parent.parentId

    return reevaluated


# =============================================================================
# TASK COMPLETION
# =============================================================================


async def complete_task(
    swarm_id: str,
    task_id: str,
    evidence: list[dict] | None = None,
    result: dict | None = None,
    learnings: list[str] | None = None,
    decision_impact: str | None = None,
    create_memory: bool = True,
) -> dict[str, Any]:
    """Complete an N3 task with evidence and optional memory creation.

    Args:
        swarm_id: The swarm ID
        task_id: The task ID
        evidence: List of evidence items [{type, url, description}]
        result: Optional result data
        learnings: Optional list of lessons learned from this task
        decision_impact: Optional description of how this task affects future decisions
        create_memory: Whether to auto-create a memory with task outcome (default: True)

    Returns:
        Completion result with optional linked_memory_id
    """
    db = await get_db()
    policy = await get_policy(swarm_id)

    task = await db.hierarchicaltask.find_first(
        where={"id": task_id, "swarmId": swarm_id},
        include={"swarm": True},
    )
    if not task:
        return {"success": False, "error": f"Task {task_id} not found"}

    # Only N3 tasks can be directly completed
    if task.level != "N3_TASK":
        return {
            "success": False,
            "error": f"Only N3_TASK can be directly completed. Use close_task for {task.level}",
        }

    # Check evidence requirement
    if requires_evidence_on_complete(policy):
        if not evidence:
            return {
                "success": False,
                "error": "Evidence is required for task completion",
            }

    # Build update data
    update_data = {
        "status": "COMPLETED",
        "completedAt": datetime.now(UTC),
        "evidenceProvided": Json(evidence) if evidence else None,
        "result": Json(result) if result else None,
    }

    # Create linked memory if requested
    linked_memory_id = None
    if create_memory and task.swarm and task.swarm.projectId:
        from .agent_memory import store_memory

        # Build memory content
        memory_parts = [
            f"## Task Completed: {task.title}",
            f"**Status:** COMPLETED",
            f"**Owner:** {task.owner}",
            f"**Completed:** {datetime.now(UTC).isoformat()}",
        ]

        if evidence:
            memory_parts.append("\n### Evidence Provided")
            for ev in evidence:
                ev_type = ev.get("type", "unknown")
                ev_desc = ev.get("description", "")
                memory_parts.append(f"- **{ev_type}**: {ev_desc}")

        if result:
            memory_parts.append(f"\n### Result\n```json\n{json.dumps(result, indent=2)}\n```")

        if learnings:
            memory_parts.append("\n### Learnings")
            for learning in learnings:
                memory_parts.append(f"- {learning}")

        if decision_impact:
            memory_parts.append(f"\n### Decision Impact\n{decision_impact}")

        memory_content = "\n".join(memory_parts)

        # Store the memory
        memory_result = await store_memory(
            project_id=task.swarm.projectId,
            content=memory_content,
            memory_type="LEARNING" if learnings else "FACT",
            scope="PROJECT",
            category=f"htask:{task_id}",
            document_refs=[f"htask:{task_id}"],
        )

        if memory_result.get("memory_id"):
            linked_memory_id = memory_result["memory_id"]
            update_data["linkedMemoryId"] = linked_memory_id

    # Complete the task
    await db.hierarchicaltask.update(
        where={"id": task_id},
        data=update_data,
    )

    # Log event
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task_id,
        event_type="complete",
        payload={
            "evidence_count": len(evidence) if evidence else 0,
            "has_result": result is not None,
            "has_learnings": learnings is not None and len(learnings) > 0,
            "linked_memory_id": linked_memory_id,
        },
    )

    logger.info(f"Completed htask {task_id}" + (f" with memory {linked_memory_id}" if linked_memory_id else ""))

    # Check if parent can auto-close
    auto_closed = None
    if task.parentId:
        verification = await verify_closure(swarm_id, task.parentId)
        if verification.get("can_close") and not verification.get("needs_waiver"):
            close_result = await close_task(swarm_id, task.parentId)
            if close_result.get("success"):
                auto_closed = task.parentId

    return {
        "success": True,
        "task_id": task_id,
        "status": "COMPLETED",
        "auto_closed_parent": auto_closed,
        "linked_memory_id": linked_memory_id,
    }


# =============================================================================
# CLOSURE VALIDATION & EXECUTION
# =============================================================================


async def verify_closure(swarm_id: str, task_id: str) -> dict[str, Any]:
    """Verify if a task can be closed.

    Args:
        swarm_id: The swarm ID
        task_id: The task ID

    Returns:
        Dict with can_close, blockers, needs_waiver
    """
    db = await get_db()
    policy = await get_policy(swarm_id)

    task = await db.hierarchicaltask.find_first(
        where={"id": task_id, "swarmId": swarm_id}
    )
    if not task:
        return {"success": False, "error": f"Task {task_id} not found"}

    # Get active children
    children = await db.hierarchicaltask.find_many(
        where={"swarmId": swarm_id, "parentId": task_id, "archivedAt": None}
    )

    blockers = []
    needs_waiver = False

    # Check incomplete children
    incomplete = [c for c in children if c.status != "COMPLETED"]

    closure_policy = policy.get("closure_policy", "STRICT_ALL_CHILDREN")

    if closure_policy == "STRICT_ALL_CHILDREN":
        if incomplete:
            blockers.append(f"{len(incomplete)} children not completed")
    else:  # ALLOW_EXCEPTIONS
        blocking_incomplete = [c for c in incomplete if c.isBlocking]
        if blocking_incomplete:
            if policy.get("allow_parent_close_with_waiver", False):
                needs_waiver = True
                blockers.append(f"{len(blocking_incomplete)} blocking children need waiver")
            else:
                blockers.append(f"{len(blocking_incomplete)} blocking children not completed")

    # Level-specific DoD validation
    level_blockers = await _validate_dod_by_level(task, children)
    blockers.extend(level_blockers)

    can_close = len(blockers) == 0 or (needs_waiver and len([b for b in blockers if "blocking" in b.lower()]) == 0)

    return {
        "success": True,
        "task_id": task_id,
        "can_close": can_close,
        "blockers": blockers,
        "needs_waiver": needs_waiver,
        "incomplete_children": len(incomplete),
        "total_children": len(children),
    }


async def _validate_dod_by_level(task, children) -> list[str]:
    """Validate Definition of Done by task level.

    Args:
        task: The task object
        children: List of child tasks

    Returns:
        List of blocker messages
    """
    blockers = []

    if task.level == "N2_WORKSTREAM":
        # N2: all N3 closed + 0 P0/P1 bugs open
        p0_p1_open = [
            c for c in children
            if c.status not in ("COMPLETED", "CANCELLED")
            and c.priority in ("P0", "P1")
        ]
        if p0_p1_open:
            blockers.append(f"{len(p0_p1_open)} P0/P1 tasks still open")

    elif task.level == "N1_FEATURE":
        # N1: all N2 closed + QA pass + PROD_OK
        qa_ws = next((c for c in children if c.workstreamType == "QA"), None)
        deploy_ws = next(
            (c for c in children if c.workstreamType == "DEPLOY_PROD_VERIFY"),
            None
        )

        if qa_ws and qa_ws.status != "COMPLETED":
            blockers.append("QA workstream not completed")
        if deploy_ws and deploy_ws.status != "COMPLETED":
            blockers.append("Deploy/PROD verify workstream not completed")

    elif task.level == "N0_INITIATIVE":
        # N0: all Features closed + KPIs met
        if task.acceptanceCriteria:
            criteria = task.acceptanceCriteria
            if isinstance(criteria, list):
                unchecked = [c for c in criteria if not c.get("checked")]
                if unchecked:
                    blockers.append(f"{len(unchecked)} KPIs not met")

    return blockers


async def close_task(
    swarm_id: str,
    task_id: str,
    waiver_reason: str | None = None,
    waiver_approved_by: str | None = None,
) -> dict[str, Any]:
    """Close a parent task (N0, N1, N2).

    Args:
        swarm_id: The swarm ID
        task_id: The task ID
        waiver_reason: Reason for closing with exceptions
        waiver_approved_by: Who approved the waiver

    Returns:
        Closure result
    """
    # Verify closure
    verification = await verify_closure(swarm_id, task_id)
    if not verification.get("success"):
        return verification

    if not verification.get("can_close"):
        if verification.get("needs_waiver") and waiver_reason and waiver_approved_by:
            # Close with waiver
            db = await get_db()
            await db.hierarchicaltask.update(
                where={"id": task_id},
                data={
                    "status": "COMPLETED",
                    "completedAt": datetime.now(UTC),
                    "waiverReason": waiver_reason,
                    "waiverApprovedBy": waiver_approved_by,
                    "waiverApprovedAt": datetime.now(UTC),
                },
            )

            # Log waiver event
            await log_htask_event(
                swarm_id=swarm_id,
                task_id=task_id,
                event_type="waiver",
                payload={
                    "reason": waiver_reason,
                    "approved_by": waiver_approved_by,
                },
            )

            logger.info(f"Closed htask {task_id} with waiver by {waiver_approved_by}")

            return {
                "success": True,
                "task_id": task_id,
                "status": "COMPLETED",
                "closed_with_waiver": True,
            }
        else:
            return {
                "success": False,
                "error": "Cannot close task",
                "blockers": verification.get("blockers", []),
                "needs_waiver": verification.get("needs_waiver", False),
            }

    # Normal closure
    db = await get_db()
    await db.hierarchicaltask.update(
        where={"id": task_id},
        data={
            "status": "COMPLETED",
            "completedAt": datetime.now(UTC),
        },
    )

    # Log event
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task_id,
        event_type="close",
        payload={},
    )

    logger.info(f"Closed htask {task_id}")

    return {
        "success": True,
        "task_id": task_id,
        "status": "COMPLETED",
        "closed_with_waiver": False,
    }


# =============================================================================
# UPDATE & DELETE
# =============================================================================


async def update_htask(
    swarm_id: str,
    task_id: str,
    updates: dict[str, Any],
    is_admin: bool = False,
) -> dict[str, Any]:
    """Update a task with whitelist validation.

    Args:
        swarm_id: The swarm ID
        task_id: The task ID
        updates: Dict of fields to update
        is_admin: Whether the caller has admin privileges

    Returns:
        Update result
    """
    db = await get_db()
    policy = await get_policy(swarm_id)

    task = await db.hierarchicaltask.find_first(
        where={"id": task_id, "swarmId": swarm_id}
    )
    if not task:
        return {"success": False, "error": f"Task {task_id} not found"}

    # Get allowed fields for current status
    allowed = UPDATE_WHITELIST.get(task.status, [])

    # Validate fields
    prisma_updates = {}
    for field, value in updates.items():
        # Map snake_case to camelCase
        prisma_field = _to_camel_case(field)

        if field in STRUCTURAL_FIELDS or prisma_field in STRUCTURAL_FIELDS:
            if not (allows_structural_update(policy) and is_admin):
                return {
                    "success": False,
                    "error": f"Cannot update structural field '{field}' without admin privileges",
                }
        elif field not in allowed and prisma_field not in allowed:
            return {
                "success": False,
                "error": f"Cannot update '{field}' when status is {task.status}",
            }

        prisma_updates[prisma_field] = value

    # Validate parentId change (anti-cycle)
    if "parentId" in prisma_updates:
        new_parent = prisma_updates["parentId"]
        if new_parent != task.parentId:
            if not await _validate_no_cycle(task_id, new_parent):
                return {"success": False, "error": "Cycle detected in task hierarchy"}

    if not prisma_updates:
        return {"success": False, "error": "No valid fields to update"}

    # Handle JSON fields
    for json_field in ["acceptanceCriteria", "evidenceRequired", "evidenceProvided", "result"]:
        if json_field in prisma_updates:
            prisma_updates[json_field] = Json(prisma_updates[json_field])

    # Apply update
    await db.hierarchicaltask.update(
        where={"id": task_id},
        data=prisma_updates,
    )

    # Log event
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task_id,
        event_type="update",
        payload={"fields": list(updates.keys())},
    )

    logger.info(f"Updated htask {task_id}: {list(updates.keys())}")

    return {
        "success": True,
        "task_id": task_id,
        "updated_fields": list(updates.keys()),
    }


async def delete_htask(
    swarm_id: str,
    task_id: str,
    force: bool = False,
    cascade: bool = False,
    is_admin: bool = False,
) -> dict[str, Any]:
    """Delete a task (soft by default, hard with force).

    Args:
        swarm_id: The swarm ID
        task_id: The task ID
        force: True for hard delete
        cascade: True to delete children too
        is_admin: Whether the caller has admin privileges

    Returns:
        Delete result
    """
    db = await get_db()
    policy = await get_policy(swarm_id)

    # Check permissions for hard delete
    if force and not (allows_hard_delete(policy) and is_admin):
        return {"success": False, "error": "Hard delete not allowed"}

    task = await db.hierarchicaltask.find_first(
        where={"id": task_id, "swarmId": swarm_id}
    )
    if not task:
        return {"success": False, "error": f"Task {task_id} not found"}

    # Collect task IDs to delete
    task_ids = [task_id]
    if cascade:
        descendants = await _get_all_descendants(swarm_id, task_id)
        task_ids.extend([d.id for d in descendants])

    if force:
        # Hard delete
        await db.hierarchicaltask.delete_many(
            where={"id": {"in": task_ids}}
        )
        delete_type = "hard"
    else:
        # Soft delete
        await db.hierarchicaltask.update_many(
            where={"id": {"in": task_ids}},
            data={
                "status": "CANCELLED",
                "archivedAt": datetime.now(UTC),
            },
        )
        delete_type = "soft"

    # Log event
    await log_htask_event(
        swarm_id=swarm_id,
        task_id=task_id,
        event_type="delete",
        payload={
            "type": delete_type,
            "cascade": cascade,
            "count": len(task_ids),
        },
    )

    logger.info(f"Deleted ({delete_type}) htask {task_id} and {len(task_ids)-1} descendants")

    return {
        "success": True,
        "type": delete_type,
        "deleted": task_ids,
        "count": len(task_ids),
    }


async def _get_all_descendants(swarm_id: str, task_id: str) -> list:
    """Get all descendant tasks recursively.

    Args:
        swarm_id: The swarm ID
        task_id: The root task ID

    Returns:
        List of descendant task objects
    """
    db = await get_db()
    descendants = []
    queue = [task_id]

    while queue:
        parent_id = queue.pop(0)
        children = await db.hierarchicaltask.find_many(
            where={"swarmId": swarm_id, "parentId": parent_id}
        )
        for child in children:
            descendants.append(child)
            queue.append(child.id)

    return descendants


# =============================================================================
# RECOMMEND BATCH
# =============================================================================


async def recommend_batch(
    swarm_id: str,
    feature_id: str | None = None,
    workstream_type: str | None = None,
    owner: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Get recommended N3 tasks ready for work.

    Criteria:
    - Status = PENDING (not blocked, not in progress)
    - All dependencies complete
    - No blocking ancestor
    - Ordered by priority (P0 > P1 > P2), then sequence

    Args:
        swarm_id: The swarm ID
        feature_id: Filter by feature
        workstream_type: Filter by workstream type
        owner: Filter by owner
        limit: Maximum tasks to return

    Returns:
        List of recommended tasks
    """
    db = await get_db()

    # Build base query
    where: dict[str, Any] = {
        "swarmId": swarm_id,
        "level": "N3_TASK",
        "status": "PENDING",
        "archivedAt": None,
    }

    if owner:
        where["owner"] = owner

    if workstream_type:
        # Get all workstreams of this type
        workstreams = await db.hierarchicaltask.find_many(
            where={
                "swarmId": swarm_id,
                "level": "N2_WORKSTREAM",
                "workstreamType": workstream_type,
            }
        )
        ws_ids = [ws.id for ws in workstreams]
        if ws_ids:
            where["parentId"] = {"in": ws_ids}
        else:
            return {"success": True, "tasks": [], "total": 0}

    if feature_id:
        # Get all workstreams under this feature
        workstreams = await db.hierarchicaltask.find_many(
            where={
                "swarmId": swarm_id,
                "level": "N2_WORKSTREAM",
                "parentId": feature_id,
            }
        )
        ws_ids = [ws.id for ws in workstreams]
        if ws_ids:
            if "parentId" in where:
                # Intersect with existing filter
                where["parentId"] = {"in": list(set(ws_ids) & set(where["parentId"]["in"]))}
            else:
                where["parentId"] = {"in": ws_ids}

    # Get candidate tasks
    tasks = await db.hierarchicaltask.find_many(
        where=where,
        order=[{"priority": "asc"}, {"sequenceNumber": "asc"}],
        take=limit * 2,  # Get extra to filter blocked ancestors
    )

    # Filter tasks with blocked ancestors
    ready_tasks = []
    for task in tasks:
        if len(ready_tasks) >= limit:
            break

        # Check for blocked ancestors
        has_blocked_ancestor = await _has_blocked_ancestor(swarm_id, task.id)
        if not has_blocked_ancestor:
            ready_tasks.append(task)

    # Build result with path info
    result_tasks = []
    for task in ready_tasks:
        path = await _get_task_path(swarm_id, task.id)
        result_tasks.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "owner": task.owner,
            "priority": task.priority,
            "eta_target": task.etaTarget.isoformat() if task.etaTarget else None,
            "acceptance_criteria": task.acceptanceCriteria,
            "evidence_required": task.evidenceRequired,
            "context_refs": task.contextRefs,
            "path": path,
        })

    return {
        "success": True,
        "tasks": result_tasks,
        "total": len(result_tasks),
        "filtered_by": {
            "feature_id": feature_id,
            "workstream_type": workstream_type,
            "owner": owner,
        },
    }


async def _has_blocked_ancestor(swarm_id: str, task_id: str) -> bool:
    """Check if task has any blocked ancestor.

    Args:
        swarm_id: The swarm ID
        task_id: The task ID

    Returns:
        True if any ancestor is blocked
    """
    db = await get_db()

    task = await db.hierarchicaltask.find_unique(where={"id": task_id})
    if not task:
        return False

    current_id = task.parentId

    while current_id:
        parent = await db.hierarchicaltask.find_unique(where={"id": current_id})
        if not parent:
            break

        if parent.status == "BLOCKED":
            return True

        current_id = parent.parentId

    return False


async def _get_task_path(swarm_id: str, task_id: str) -> dict[str, Any]:
    """Get the path (initiative, feature, workstream) for a task.

    Args:
        swarm_id: The swarm ID
        task_id: The task ID

    Returns:
        Dict with path components
    """
    db = await get_db()
    path = {"initiative": None, "feature": None, "workstream": None}

    task = await db.hierarchicaltask.find_unique(where={"id": task_id})
    if not task:
        return path

    current_id = task.parentId

    while current_id:
        parent = await db.hierarchicaltask.find_unique(where={"id": current_id})
        if not parent:
            break

        if parent.level == "N0_INITIATIVE":
            path["initiative"] = parent.title
        elif parent.level == "N1_FEATURE":
            path["feature"] = parent.title
        elif parent.level == "N2_WORKSTREAM":
            path["workstream"] = parent.title

        current_id = parent.parentId

    return path


# =============================================================================
# HELPERS
# =============================================================================


def _to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase."""
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])
