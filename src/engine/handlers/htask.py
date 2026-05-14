"""Hierarchical Task tool handlers for multi-level task management.

Handles:
- rlm_htask_create: Create a task at any level (N0-N3)
- rlm_htask_create_feature: Create N1 feature with standard workstreams
- rlm_htask_get: Get task with children
- rlm_htask_tree: Get full tree from a node
- rlm_htask_update: Update task fields (whitelist by status)
- rlm_htask_block: Block task with detailed payload
- rlm_htask_unblock: Unblock task
- rlm_htask_complete: Complete N3 task with evidence
- rlm_htask_verify_closure: Verify if parent can close
- rlm_htask_close: Close parent task (with optional waiver)
- rlm_htask_delete: Delete task (soft/hard)
- rlm_htask_recommend_batch: Get recommended N3 tasks to work on
"""

import json
from typing import Any

from ...models import ToolResult
from ...services.htask_coordinator import (
    block_task,
    close_task,
    complete_task,
    create_feature_with_workstreams,
    create_htask,
    delete_htask,
    get_htask,
    get_htask_tree,
    recommend_batch,
    unblock_task,
    update_htask,
    verify_closure,
)
from ...services.htask_events import (
    get_checkpoint_delta,
    get_htask_metrics,
    get_task_audit_trail,
)
from ...services.htask_policy import (
    get_policy,
    update_policy,
)
from .base import HandlerContext, count_tokens


async def handle_htask_create(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Create a hierarchical task at any level.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - level: Task level (N0_INITIATIVE, N1_FEATURE, N2_WORKSTREAM, N3_TASK)
            - title: Task title (required)
            - description: Task description (required)
            - owner: Task owner (required)
            - parent_id: Parent task ID (required for N1-N3)
            - priority: P0, P1, P2 (default P1)
            - eta_target: Target completion date (ISO format)
            - execution_target: LOCAL, CLOUD, HYBRID, EXTERNAL
            - workstream_type: Type for N2 tasks
            - acceptance_criteria: List of criteria dicts
            - context_refs: List of reference strings
            - context_query: Auto-fetch relevant docs query (optional)
            - evidence_required: List of evidence requirements
            - is_blocking: Whether task blocks parent closure (default true)

    Returns:
        ToolResult with task ID and info
    """
    swarm_id = params.get("swarm_id", "")
    level = params.get("level", "N3_TASK")
    title = params.get("title", "")
    description = params.get("description", "")
    owner = params.get("owner", "")

    if not swarm_id or not title or not description or not owner:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not title:
            missing.append("title")
        if not description:
            missing.append("description")
        if not owner:
            missing.append("owner")
        return ToolResult(
            data={"error": f"rlm_htask_create: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    # Parse JSON fields if they arrive as strings from MCP
    acceptance_criteria = params.get("acceptance_criteria")
    if acceptance_criteria and isinstance(acceptance_criteria, str):
        try:
            acceptance_criteria = json.loads(acceptance_criteria)
        except json.JSONDecodeError:
            return ToolResult(
                data={"error": "acceptance_criteria must be valid JSON"},
                input_tokens=0,
                output_tokens=0,
            )

    evidence_required = params.get("evidence_required")
    if evidence_required and isinstance(evidence_required, str):
        try:
            evidence_required = json.loads(evidence_required)
        except json.JSONDecodeError:
            return ToolResult(
                data={"error": "evidence_required must be valid JSON"},
                input_tokens=0,
                output_tokens=0,
            )

    context_refs = params.get("context_refs")
    if context_refs and isinstance(context_refs, str):
        try:
            context_refs = json.loads(context_refs)
        except json.JSONDecodeError:
            return ToolResult(
                data={"error": "context_refs must be valid JSON"},
                input_tokens=0,
                output_tokens=0,
            )

    # P2 Feature: Auto-fetch relevant docs if context_query is provided
    context_query = params.get("context_query")
    if context_query and ctx.index:
        try:
            search_result = await ctx.index.search_similar(
                project_id=ctx.project_id,
                query=context_query,
                limit=5,  # Top 5 relevant docs
                track_access=False,  # Don't pollute access stats
            )
            # Extract unique document paths from search results
            auto_refs = []
            seen_paths = set()
            for chunk in search_result.get("results", []):
                doc_path = chunk.get("document_path") or chunk.get("file_path")
                if doc_path and doc_path not in seen_paths:
                    seen_paths.add(doc_path)
                    auto_refs.append(f"snipara://{ctx.project_id}/{doc_path}")
            # Merge with existing context_refs (auto-fetched first, then manual)
            if context_refs:
                context_refs = auto_refs + [r for r in context_refs if r not in auto_refs]
            else:
                context_refs = auto_refs
        except Exception:
            # If search fails, continue without auto-refs (non-blocking)
            pass

    result = await create_htask(
        swarm_id=swarm_id,
        level=level,
        title=title,
        description=description,
        owner=owner,
        parent_id=params.get("parent_id"),
        priority=params.get("priority", "P1"),
        eta_target=params.get("eta_target"),
        execution_target=params.get("execution_target"),
        workstream_type=params.get("workstream_type"),
        custom_workstream_type=params.get("custom_workstream_type"),
        acceptance_criteria=acceptance_criteria,
        context_refs=context_refs,
        evidence_required=evidence_required,
        is_blocking=params.get("is_blocking", True),
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(title + description),
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_create_feature(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Create a N1 feature with standard workstreams.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - title: Feature title (required)
            - description: Feature description (required)
            - owner: Feature owner (required)
            - parent_id: Optional N0 parent
            - workstreams: List of workstream types to create
              Defaults to: API, FRONTEND, QA, BUGFIX_HARDENING, DEPLOY_PROD_VERIFY

    Returns:
        ToolResult with feature ID and created workstreams
    """
    swarm_id = params.get("swarm_id", "")
    title = params.get("title", "")
    description = params.get("description", "")
    owner = params.get("owner", "")

    if not swarm_id or not title or not description or not owner:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not title:
            missing.append("title")
        if not description:
            missing.append("description")
        if not owner:
            missing.append("owner")
        return ToolResult(
            data={"error": f"rlm_htask_create_feature: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await create_feature_with_workstreams(
        swarm_id=swarm_id,
        title=title,
        description=description,
        owner=owner,
        parent_id=params.get("parent_id"),
        include_workstreams=params.get("workstreams"),  # Map "workstreams" from tool to "include_workstreams" in backend
        workstream_owners=params.get("workstream_owners"),  # Also pass workstream_owners if provided
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(title + description),
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_get(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get a hierarchical task with its children.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - task_id: Task ID (required)
            - include_children: Include direct children (default true)

    Returns:
        ToolResult with task data and optional children
    """
    swarm_id = params.get("swarm_id", "")
    task_id = params.get("task_id", "")

    if not swarm_id or not task_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not task_id:
            missing.append("task_id")
        return ToolResult(
            data={"error": f"rlm_htask_get: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await get_htask(
        swarm_id=swarm_id,
        task_id=task_id,
        include_children=params.get("include_children", True),
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_tree(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get full hierarchical tree from a node.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - task_id: Root task ID (optional, defaults to all root tasks)
            - max_depth: Maximum depth to traverse (default 4)
            - include_archived: Include archived tasks (default false)

    Returns:
        ToolResult with recursive tree structure
    """
    swarm_id = params.get("swarm_id", "")

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_htask_tree: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await get_htask_tree(
        swarm_id=swarm_id,
        task_id=params.get("task_id"),
        max_depth=params.get("max_depth", 4),
        include_archived=params.get("include_archived", False),
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_update(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Update task fields (whitelist enforced by status).

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - task_id: Task ID (required)
            - updates: Dict of fields to update
            - is_admin: Whether caller has admin privileges (for structural updates)

    Returns:
        ToolResult with updated task
    """
    swarm_id = params.get("swarm_id", "")
    task_id = params.get("task_id", "")
    updates = params.get("updates", {})

    if not swarm_id or not task_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not task_id:
            missing.append("task_id")
        return ToolResult(
            data={"error": f"rlm_htask_update: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    if not updates:
        return ToolResult(
            data={"error": "rlm_htask_update: no updates provided"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await update_htask(
        swarm_id=swarm_id,
        task_id=task_id,
        updates=updates,
        is_admin=params.get("is_admin", False),
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(str(updates)),
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_block(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Block a task with detailed payload.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - task_id: Task ID (required)
            - blocker_type: TECH, DEPENDENCY, ACCESS, PRODUCT, INFRA, SECURITY, OTHER (required)
            - blocker_reason: Detailed explanation (required)
            - blocked_by_task_id: ID of blocking task (optional)
            - required_input: What's needed to unblock (optional)
            - eta_recovery: Expected unblock date (optional)
            - escalation_to: Who to escalate to (optional)

    Returns:
        ToolResult with block confirmation and affected ancestors
    """
    swarm_id = params.get("swarm_id", "")
    task_id = params.get("task_id", "")
    blocker_type = params.get("blocker_type", "")
    blocker_reason = params.get("blocker_reason", "")

    if not swarm_id or not task_id or not blocker_type or not blocker_reason:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not task_id:
            missing.append("task_id")
        if not blocker_type:
            missing.append("blocker_type")
        if not blocker_reason:
            missing.append("blocker_reason")
        return ToolResult(
            data={"error": f"rlm_htask_block: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await block_task(
        swarm_id=swarm_id,
        task_id=task_id,
        blocker_type=blocker_type,
        blocker_reason=blocker_reason,
        blocked_by_task_id=params.get("blocked_by_task_id"),
        required_input=params.get("required_input"),
        eta_recovery=params.get("eta_recovery"),
        escalation_to=params.get("escalation_to"),
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(blocker_reason),
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_unblock(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Unblock a task.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - task_id: Task ID (required)
            - resolution: How the blocker was resolved (optional)

    Returns:
        ToolResult with unblock confirmation
    """
    swarm_id = params.get("swarm_id", "")
    task_id = params.get("task_id", "")

    if not swarm_id or not task_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not task_id:
            missing.append("task_id")
        return ToolResult(
            data={"error": f"rlm_htask_unblock: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await unblock_task(
        swarm_id=swarm_id,
        task_id=task_id,
        resolution=params.get("resolution"),
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_complete(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Complete an N3 task with evidence and optional memory creation.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - task_id: Task ID (required)
            - evidence: List of evidence dicts [{type, description, ...}] (optional but may be required by policy)
            - result: Task result data (optional)
            - learnings: List of lessons learned from this task (optional)
            - decision_impact: How this task affects future decisions (optional)
            - create_memory: Whether to create a memory with task outcome (default: True)

    Returns:
        ToolResult with completion confirmation and optional linked_memory_id
    """
    swarm_id = params.get("swarm_id", "")
    task_id = params.get("task_id", "")

    if not swarm_id or not task_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not task_id:
            missing.append("task_id")
        return ToolResult(
            data={"error": f"rlm_htask_complete: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await complete_task(
        swarm_id=swarm_id,
        task_id=task_id,
        evidence=params.get("evidence"),
        result=params.get("result"),
        learnings=params.get("learnings"),
        decision_impact=params.get("decision_impact"),
        create_memory=params.get("create_memory", True),
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(str(params.get("evidence", []))),
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_verify_closure(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Verify if a parent task can be closed.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - task_id: Task ID (required)

    Returns:
        ToolResult with:
            - can_close: Boolean
            - blockers: List of blocking reasons
            - needs_waiver: Whether waiver is required
    """
    swarm_id = params.get("swarm_id", "")
    task_id = params.get("task_id", "")

    if not swarm_id or not task_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not task_id:
            missing.append("task_id")
        return ToolResult(
            data={"error": f"rlm_htask_verify_closure: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await verify_closure(
        swarm_id=swarm_id,
        task_id=task_id,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_close(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Close a parent task (optionally with waiver).

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - task_id: Task ID (required)
            - waiver_reason: Reason for waiver if closing with exceptions (optional)
            - waiver_approved_by: Who approved the waiver (optional)

    Returns:
        ToolResult with closure confirmation
    """
    swarm_id = params.get("swarm_id", "")
    task_id = params.get("task_id", "")

    if not swarm_id or not task_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not task_id:
            missing.append("task_id")
        return ToolResult(
            data={"error": f"rlm_htask_close: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await close_task(
        swarm_id=swarm_id,
        task_id=task_id,
        waiver_reason=params.get("waiver_reason"),
        waiver_approved_by=params.get("waiver_approved_by"),
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_delete(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Delete a task (soft by default, hard with force flag).

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - task_id: Task ID (required)
            - force: Hard delete (requires policy + admin) (default false)
            - cascade: Delete all descendants (default false)
            - is_admin: Whether caller has admin privileges

    Returns:
        ToolResult with deletion confirmation
    """
    swarm_id = params.get("swarm_id", "")
    task_id = params.get("task_id", "")

    if not swarm_id or not task_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not task_id:
            missing.append("task_id")
        return ToolResult(
            data={"error": f"rlm_htask_delete: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await delete_htask(
        swarm_id=swarm_id,
        task_id=task_id,
        force=params.get("force", False),
        cascade=params.get("cascade", False),
        is_admin=params.get("is_admin", False),
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_recommend_batch(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get recommended batch of N3 tasks ready to work on.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - limit: Maximum tasks to return (default 5)
            - owner: Filter by owner (optional)
            - exclude_blocked: Exclude blocked tasks (default true)

    Returns:
        ToolResult with list of recommended tasks
    """
    swarm_id = params.get("swarm_id", "")

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_htask_recommend_batch: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await recommend_batch(
        swarm_id=swarm_id,
        feature_id=params.get("feature_id"),
        workstream_type=params.get("workstream_type"),
        owner=params.get("owner"),
        limit=params.get("limit", 5),
        exclude_blocked=params.get("exclude_blocked", True),
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


# ============ ADDITIONAL HANDLERS FOR POLICY & METRICS ============


async def handle_htask_policy_get(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get the htask policy for a swarm.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)

    Returns:
        ToolResult with policy configuration
    """
    swarm_id = params.get("swarm_id", "")

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_htask_policy_get: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await get_policy(swarm_id=swarm_id)

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_policy_update(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Update the htask policy for a swarm.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - updates: Policy fields to update
            - is_admin: Whether caller has admin privileges

    Returns:
        ToolResult with updated policy
    """
    swarm_id = params.get("swarm_id", "")
    updates = params.get("updates", {})

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_htask_policy_update: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    if not updates:
        return ToolResult(
            data={"error": "rlm_htask_policy_update: no updates provided"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await update_policy(
        swarm_id=swarm_id,
        updates=updates,
        is_admin=params.get("is_admin", False),
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_metrics(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get comprehensive metrics for htasks in a swarm.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - period_hours: Period for time-based metrics (default 24)

    Returns:
        ToolResult with metrics (throughput, aging, blocked ratio, etc.)
    """
    swarm_id = params.get("swarm_id", "")

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_htask_metrics: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await get_htask_metrics(
        swarm_id=swarm_id,
        period_hours=params.get("period_hours", 24),
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_audit_trail(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get audit trail for a specific task.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - task_id: Task ID (required)

    Returns:
        ToolResult with list of events
    """
    swarm_id = params.get("swarm_id", "")
    task_id = params.get("task_id", "")

    if not swarm_id or not task_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not task_id:
            missing.append("task_id")
        return ToolResult(
            data={"error": f"rlm_htask_audit_trail: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await get_task_audit_trail(
        swarm_id=swarm_id,
        task_id=task_id,
    )

    return ToolResult(
        data={"events": result},
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_htask_checkpoint_delta(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get delta report since last checkpoint.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - since: ISO timestamp of last checkpoint (required)

    Returns:
        ToolResult with delta report (closures, blocks, events)
    """
    from datetime import datetime

    swarm_id = params.get("swarm_id", "")
    since_str = params.get("since", "")

    if not swarm_id or not since_str:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not since_str:
            missing.append("since")
        return ToolResult(
            data={"error": f"rlm_htask_checkpoint_delta: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    try:
        since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
    except ValueError:
        return ToolResult(
            data={"error": "rlm_htask_checkpoint_delta: invalid 'since' timestamp format"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await get_checkpoint_delta(
        swarm_id=swarm_id,
        since=since,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )
