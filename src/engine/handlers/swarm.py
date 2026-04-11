"""Swarm tool handlers for multi-agent coordination.

Handles:
- rlm_swarm_create: Create a new agent swarm
- rlm_swarm_join: Join an existing swarm
- rlm_claim: Claim exclusive access to a resource
- rlm_release: Release a claimed resource
- rlm_state_get: Read shared swarm state
- rlm_state_set: Write shared swarm state
- rlm_broadcast: Broadcast event to all agents
- rlm_task_create: Create a task in the queue
- rlm_task_claim: Claim a task from the queue
- rlm_task_complete: Mark a task as complete
- rlm_tasks: List tasks in a swarm
"""

from typing import Any

from ...models import ToolResult
from ...services.swarm import (
    acquire_claim,
    broadcast_event,
    claim_task,
    complete_task,
    create_swarm,
    create_task,
    get_agent_profile,
    get_state,
    get_task_events,
    get_task_stats,
    join_swarm,
    list_tasks,
    list_tasks_enhanced,
    recover_stuck_tasks,
    release_claim,
    set_state,
    unclaim_task,
    update_agent_profile,
)
from .base import HandlerContext, count_tokens


async def handle_swarm_create(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Create a new agent swarm.

    Args:
        params: Dict containing:
            - name: Swarm name
            - description: Optional description
            - max_agents: Maximum agents allowed
            - config: Optional swarm configuration

    Returns:
        ToolResult with swarm ID and info
    """
    name = params.get("name", "")
    description = params.get("description")
    max_agents = params.get("max_agents", 10)
    config = params.get("config")

    if not name:
        return ToolResult(
            data={"error": "rlm_swarm_create: missing required parameter 'name'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await create_swarm(
        project_id=ctx.project_id,
        name=name,
        description=description,
        max_agents=max_agents,
        config=config,
        user_id=ctx.user_id,
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(name + (description or "")),
        output_tokens=count_tokens(str(result)),
    )


async def handle_swarm_join(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Join an existing swarm as an agent.

    Args:
        params: Dict containing:
            - swarm_id: Swarm to join
            - agent_id: Unique agent identifier
            - role: Agent role (coordinator, worker, observer)
            - capabilities: List of capabilities

    Returns:
        ToolResult with join status
    """
    swarm_id = params.get("swarm_id", "")
    agent_id = params.get("agent_id", "")
    role = params.get("role", "worker")
    capabilities = params.get("capabilities")

    if not swarm_id or not agent_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not agent_id:
            missing.append("agent_id")
        return ToolResult(
            data={"error": f"rlm_swarm_join: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await join_swarm(
        swarm_id=swarm_id,
        agent_id=agent_id,
        role=role,
        capabilities=capabilities,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_claim(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Claim exclusive access to a resource.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID
            - agent_id: Agent identifier
            - resource_type: Type of resource
            - resource_id: Resource identifier
            - timeout_seconds: Claim timeout

    Returns:
        ToolResult with claim status
    """
    swarm_id = params.get("swarm_id", "")
    agent_id = params.get("agent_id", "")
    resource_type = params.get("resource_type", "")
    resource_id = params.get("resource_id", "")
    timeout_seconds = params.get("timeout_seconds", 300)

    if not all([swarm_id, agent_id, resource_type, resource_id]):
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not agent_id:
            missing.append("agent_id")
        if not resource_type:
            missing.append("resource_type")
        if not resource_id:
            missing.append("resource_id")
        return ToolResult(
            data={"error": f"rlm_claim: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await acquire_claim(
        swarm_id=swarm_id,
        agent_id=agent_id,
        resource_type=resource_type,
        resource_id=resource_id,
        timeout_seconds=timeout_seconds,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_release(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Release a claimed resource.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID
            - agent_id: Agent identifier
            - claim_id: Claim ID (optional)
            - resource_type: Resource type (alternative)
            - resource_id: Resource ID (alternative)

    Returns:
        ToolResult with release status
    """
    swarm_id = params.get("swarm_id", "")
    agent_id = params.get("agent_id", "")
    claim_id = params.get("claim_id")
    resource_type = params.get("resource_type")
    resource_id = params.get("resource_id")

    if not swarm_id or not agent_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not agent_id:
            missing.append("agent_id")
        return ToolResult(
            data={"error": f"rlm_release: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await release_claim(
        swarm_id=swarm_id,
        agent_id=agent_id,
        claim_id=claim_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_state_get(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Read shared swarm state.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID
            - key: State key to read

    Returns:
        ToolResult with state value and version
    """
    swarm_id = params.get("swarm_id", "")
    key = params.get("key", "")

    if not swarm_id or not key:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not key:
            missing.append("key")
        return ToolResult(
            data={"error": f"rlm_state_get: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await get_state(swarm_id=swarm_id, key=key)

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_state_set(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Write shared swarm state with optimistic locking.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID
            - agent_id: Agent identifier
            - key: State key
            - value: Value to set
            - expected_version: Optional version for optimistic locking

    Returns:
        ToolResult with new version
    """
    swarm_id = params.get("swarm_id", "")
    agent_id = params.get("agent_id", "")
    key = params.get("key", "")
    value = params.get("value")
    expected_version = params.get("expected_version")

    if not swarm_id or not agent_id or not key:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not agent_id:
            missing.append("agent_id")
        if not key:
            missing.append("key")
        return ToolResult(
            data={"error": f"rlm_state_set: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await set_state(
        swarm_id=swarm_id,
        agent_id=agent_id,
        key=key,
        value=value,
        expected_version=expected_version,
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(str(value) if value else ""),
        output_tokens=count_tokens(str(result)),
    )


async def handle_broadcast(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Broadcast an event to all agents in the swarm.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID
            - agent_id: Sending agent identifier
            - event_type: Type of event
            - payload: Optional event data

    Returns:
        ToolResult with delivery count
    """
    swarm_id = params.get("swarm_id", "")
    agent_id = params.get("agent_id", "")
    event_type = params.get("event_type", "")
    payload = params.get("payload")

    if not swarm_id or not agent_id or not event_type:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not agent_id:
            missing.append("agent_id")
        if not event_type:
            missing.append("event_type")
        return ToolResult(
            data={"error": f"rlm_broadcast: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await broadcast_event(
        swarm_id=swarm_id,
        agent_id=agent_id,
        event_type=event_type,
        payload=payload,
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(str(payload) if payload else ""),
        output_tokens=count_tokens(str(result)),
    )


async def handle_task_create(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Create a task in the swarm's distributed task queue.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID
            - agent_id: Creating agent identifier
            - title: Task title
            - description: Optional description
            - priority: Task priority (higher = more urgent)
            - depends_on: Task IDs this depends on
            - metadata: Additional task data
            - for_agent_id: Pre-assign task to specific agent (task affinity)

    Returns:
        ToolResult with task ID
    """
    swarm_id = params.get("swarm_id", "")
    agent_id = params.get("agent_id", "")
    title = params.get("title", "")
    description = params.get("description")
    priority = params.get("priority", 0)
    deadline = params.get("deadline")
    depends_on = params.get("depends_on")
    metadata = params.get("metadata")
    for_agent_id = params.get("for_agent_id")

    if not swarm_id or not agent_id or not title:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not agent_id:
            missing.append("agent_id")
        if not title:
            missing.append("title")
        return ToolResult(
            data={"error": f"rlm_task_create: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await create_task(
        swarm_id=swarm_id,
        agent_id=agent_id,
        title=title,
        description=description,
        priority=priority,
        deadline=deadline,
        depends_on=depends_on,
        metadata=metadata,
        for_agent_id=for_agent_id,
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(title + (description or "")),
        output_tokens=count_tokens(str(result)),
    )


async def handle_task_claim(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Claim a task from the queue.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID
            - agent_id: Claiming agent identifier
            - task_id: Optional specific task to claim
            - timeout_seconds: Task timeout

    Returns:
        ToolResult with claimed task details
    """
    swarm_id = params.get("swarm_id", "")
    agent_id = params.get("agent_id", "")
    task_id = params.get("task_id")
    timeout_seconds = params.get("timeout_seconds", 600)

    if not swarm_id or not agent_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not agent_id:
            missing.append("agent_id")
        return ToolResult(
            data={"error": f"rlm_task_claim: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await claim_task(
        swarm_id=swarm_id,
        agent_id=agent_id,
        task_id=task_id,
        timeout_seconds=timeout_seconds,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_task_complete(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Mark a claimed task as completed or failed.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID
            - agent_id: Completing agent identifier
            - task_id: Task to complete
            - success: Whether task succeeded
            - result: Optional result data

    Returns:
        ToolResult with completion confirmation
    """
    swarm_id = params.get("swarm_id", "")
    agent_id = params.get("agent_id", "")
    task_id = params.get("task_id", "")
    success = params.get("success", True)
    result_data = params.get("result")

    if not swarm_id or not agent_id or not task_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not agent_id:
            missing.append("agent_id")
        if not task_id:
            missing.append("task_id")
        return ToolResult(
            data={
                "error": f"rlm_task_complete: missing required parameter(s): {', '.join(missing)}"
            },
            input_tokens=0,
            output_tokens=0,
        )

    result = await complete_task(
        swarm_id=swarm_id,
        agent_id=agent_id,
        task_id=task_id,
        success=success,
        result=result_data,
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(str(result_data) if result_data else ""),
        output_tokens=count_tokens(str(result)),
    )


async def handle_tasks(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """List tasks in a swarm's task queue.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID
            - status: Optional filter by status (pending, claimed, completed, failed)
            - assigned_to: Optional filter by assigned agent ID
            - limit: Max tasks to return (default 50)

    Returns:
        ToolResult with list of tasks
    """
    swarm_id = params.get("swarm_id", "")
    status = params.get("status")
    assigned_to = params.get("assigned_to")
    limit = params.get("limit", 50)

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_tasks: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await list_tasks(
        swarm_id=swarm_id,
        status=status,
        assigned_to=assigned_to,
        limit=limit,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_task_list(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """List tasks with cursor-based pagination.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - status: Optional filter by status (pending, in_progress, completed, failed, cancelled)
            - limit: Max tasks to return (default 50, max 100)
            - cursor: Cursor for pagination (task ID to start after)

    Returns:
        ToolResult with tasks: [{id, status, updated_at, owner}], has_more, next_cursor
    """
    swarm_id = params.get("swarm_id", "")
    status = params.get("status")
    limit = params.get("limit", 50)
    cursor = params.get("cursor")

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_task_list: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await list_tasks_enhanced(
        swarm_id=swarm_id,
        status=status,
        limit=limit,
        cursor=cursor,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_task_stats(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get aggregated task statistics for a swarm.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)

    Returns:
        ToolResult with {done, in_progress, blocked, pending, failed, cancelled, total}
    """
    swarm_id = params.get("swarm_id", "")

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_task_stats: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await get_task_stats(swarm_id=swarm_id)

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_task_events(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get task status change events for a swarm.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - since: ISO timestamp - only return events after this time
            - limit: Max events to return (default 100)

    Returns:
        ToolResult with task events: [{event_id, event_type, task_id, timestamp}]
    """
    swarm_id = params.get("swarm_id", "")
    since = params.get("since")
    limit = params.get("limit", 100)

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_task_events: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await get_task_events(
        swarm_id=swarm_id,
        since=since,
        limit=limit,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_task_unclaim(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Return a claimed/in-progress task to the pending queue."""
    swarm_id = params.get("swarm_id", "")
    task_id = params.get("task_id", "")
    reason = params.get("reason")

    if not swarm_id or not task_id:
        missing = []
        if not swarm_id:
            missing.append("swarm_id")
        if not task_id:
            missing.append("task_id")
        return ToolResult(
            data={"error": f"rlm_task_unclaim: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await unclaim_task(
        swarm_id=swarm_id,
        task_id=task_id,
        reason=reason,
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(reason or ""),
        output_tokens=count_tokens(str(result)),
    )


async def handle_task_recover(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Find and optionally recover stuck tasks in a swarm."""
    swarm_id = params.get("swarm_id", "")
    stuck_threshold_minutes = params.get("stuck_threshold_minutes", 30)
    dry_run = params.get("dry_run", True)

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_task_recover: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await recover_stuck_tasks(
        swarm_id=swarm_id,
        stuck_threshold_minutes=int(stuck_threshold_minutes),
        dry_run=bool(dry_run),
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


# ============ AGENT PROFILE HANDLERS ============


async def handle_agent_profile_get(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get an agent's profile (identity, personality, boundaries).

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - agent_id: Agent identifier (required)

    Returns:
        ToolResult with agent profile
    """
    swarm_id = params.get("swarm_id", "")
    agent_id = params.get("agent_id", "")

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_agent_profile_get: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    if not agent_id:
        return ToolResult(
            data={"error": "rlm_agent_profile_get: missing required parameter 'agent_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await get_agent_profile(
        swarm_id=swarm_id,
        agent_id=agent_id,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_agent_profile_update(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Update an agent's profile.

    Args:
        params: Dict containing:
            - swarm_id: Swarm ID (required)
            - agent_id: Agent identifier (required)
            - profile: Profile data to update (merged with existing)
                - display_name: str
                - personality: str
                - role_description: str
                - boundaries: list[str]
                - communication_style: str
                - decision_making: str
                - soul_document_path: str
                - memory_scope: "agent" | "project" | "team"
                - custom: dict

    Returns:
        ToolResult with updated profile
    """
    swarm_id = params.get("swarm_id", "")
    agent_id = params.get("agent_id", "")
    profile = params.get("profile", {})

    if not swarm_id:
        return ToolResult(
            data={"error": "rlm_agent_profile_update: missing required parameter 'swarm_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    if not agent_id:
        return ToolResult(
            data={"error": "rlm_agent_profile_update: missing required parameter 'agent_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    if not profile:
        return ToolResult(
            data={"error": "rlm_agent_profile_update: missing required parameter 'profile'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await update_agent_profile(
        swarm_id=swarm_id,
        agent_id=agent_id,
        profile=profile,
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(str(profile)),
        output_tokens=count_tokens(str(result)),
    )
