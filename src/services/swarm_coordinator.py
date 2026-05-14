"""Swarm Coordinator Service for Phase 9.1.

Manages multi-agent swarms, resource claims, shared state, and task queues.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

try:
    from prisma import Json
except ImportError:
    # Fallback for when Json isn't available (use identity function)
    def Json(x):  # noqa: N802
        return x


from ..db import get_db
from .agent_limits import check_swarm_agent_limits, check_swarm_limits

logger = logging.getLogger(__name__)

# Default timeouts
DEFAULT_CLAIM_TIMEOUT_SECONDS = 300  # 5 minutes
DEFAULT_TASK_TIMEOUT_SECONDS = 600  # 10 minutes


# =============================================================================
# SWARM MANAGEMENT
# =============================================================================


async def create_swarm(
    project_id: str,
    name: str,
    description: str | None = None,
    max_agents: int = 10,
    config: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Create a new agent swarm.

    Args:
        project_id: The project ID
        name: Swarm name
        description: Optional description
        max_agents: Maximum agents allowed in swarm
        config: Optional swarm configuration
        user_id: The authenticated user's ID (for subscription lookup)

    Returns:
        Dict with swarm info and status
    """
    # Check limits
    allowed, error = await check_swarm_limits(project_id, user_id)
    if not allowed:
        return {
            "success": False,
            "error": error,
            "swarm_id": None,
        }

    db = await get_db()

    swarm = await db.agentswarm.create(
        data={
            "project": {"connect": {"id": project_id}},
            "name": name,
            "description": description,
            "maxAgents": max_agents,
            "isActive": True,
        }
    )

    logger.info(f"Created swarm {swarm.id} for project {project_id}")

    return {
        "success": True,
        "swarm_id": swarm.id,
        "name": swarm.name,
        "description": swarm.description,
        "max_agents": swarm.maxAgents,
        "message": f"Swarm '{name}' created successfully",
    }


async def join_swarm(
    swarm_id: str,
    agent_id: str,
    role: str = "worker",
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """Join an existing swarm as an agent.

    Args:
        swarm_id: The swarm to join
        agent_id: Unique identifier for this agent
        role: Agent role (coordinator, worker, observer)
        capabilities: List of agent capabilities

    Returns:
        Dict with join status and agent info
    """
    db = await get_db()

    # Check if swarm exists and is active
    swarm = await db.agentswarm.find_unique(where={"id": swarm_id})
    if not swarm:
        return {
            "success": False,
            "error": "Swarm not found",
            "agent_id": None,
        }

    if not swarm.isActive:
        return {
            "success": False,
            "error": "Swarm is not active",
            "agent_id": None,
        }

    # Check agent limits
    allowed, error = await check_swarm_agent_limits(swarm_id)
    if not allowed:
        return {
            "success": False,
            "error": error,
            "agent_id": None,
        }

    # Check if agent already in swarm
    existing = await db.swarmagent.find_first(
        where={
            "swarmId": swarm_id,
            "agentId": agent_id,
            "isActive": True,
        }
    )

    if existing:
        # Update last heartbeat
        await db.swarmagent.update(
            where={"id": existing.id},
            data={"lastHeartbeat": datetime.now(UTC)},
        )
        return {
            "success": True,
            "agent_id": existing.id,
            "swarm_id": swarm_id,
            "role": role,  # Return requested role (not stored in DB)
            "message": "Already in swarm, updated heartbeat",
        }

    # Join swarm
    agent = await db.swarmagent.create(
        data={
            "swarm": {"connect": {"id": swarm_id}},
            "agentId": agent_id,
            "name": agent_id,  # Use agent_id as name
            "isActive": True,
            "lastHeartbeat": datetime.now(UTC),
        }
    )

    logger.info(f"Agent {agent_id} joined swarm {swarm_id}")

    return {
        "success": True,
        "agent_id": agent.id,
        "swarm_id": swarm_id,
        "role": role,
        "capabilities": capabilities or [],
        "message": f"Joined swarm as {role}",
    }


async def leave_swarm(swarm_id: str, agent_id: str) -> dict[str, Any]:
    """Leave a swarm.

    Args:
        swarm_id: The swarm to leave
        agent_id: The agent's unique identifier

    Returns:
        Dict with leave status
    """
    db = await get_db()

    # Find agent in swarm
    agent = await db.swarmagent.find_first(
        where={
            "swarmId": swarm_id,
            "agentId": agent_id,
            "isActive": True,
        }
    )

    if not agent:
        return {
            "success": False,
            "error": "Agent not found in swarm",
        }

    # Mark as inactive (soft delete)
    await db.swarmagent.update(
        where={"id": agent.id},
        data={"isActive": False},
    )

    # Release any claims held by this agent
    await db.resourceclaim.update_many(
        where={
            "agentId": agent.id,
            "status": "ACTIVE",
        },
        data={
            "status": "RELEASED",
            "releasedAt": datetime.now(UTC),
        },
    )

    logger.info(f"Agent {agent_id} left swarm {swarm_id}")

    return {
        "success": True,
        "message": "Left swarm successfully",
    }


async def get_swarm_info(swarm_id: str) -> dict[str, Any]:
    """Get information about a swarm.

    Args:
        swarm_id: The swarm ID

    Returns:
        Dict with swarm info and agent list
    """
    db = await get_db()

    swarm = await db.agentswarm.find_unique(
        where={"id": swarm_id},
        include={"agents": {"where": {"isActive": True}}},
    )

    if not swarm:
        return {
            "success": False,
            "error": "Swarm not found",
        }

    agents = [
        {
            "agent_id": a.agentId,
            "name": a.name,
            "is_active": a.isActive,
            "last_heartbeat": a.lastHeartbeat.isoformat() if a.lastHeartbeat else None,
            "tasks_completed": a.tasksCompleted,
            "tasks_failed": a.tasksFailed,
            "joined_at": a.joinedAt.isoformat() if a.joinedAt else None,
        }
        for a in swarm.agents
    ]

    return {
        "success": True,
        "swarm_id": swarm.id,
        "name": swarm.name,
        "description": swarm.description,
        "max_agents": swarm.maxAgents,
        "is_active": swarm.isActive,
        "agent_count": len(agents),
        "agents": agents,
    }


async def get_agent_profile(
    swarm_id: str,
    agent_id: str,
) -> dict[str, Any]:
    """Get an agent's profile (identity, personality, boundaries).

    Args:
        swarm_id: The swarm ID
        agent_id: The agent's unique identifier

    Returns:
        Dict with agent profile or error
    """
    db = await get_db()

    # Find agent in swarm
    agent = await db.swarmagent.find_first(
        where={
            "swarmId": swarm_id,
            "agentId": agent_id,
        }
    )

    if not agent:
        return {
            "success": False,
            "error": f"Agent '{agent_id}' not found in swarm",
            "profile": None,
        }

    # Parse profile JSON if exists
    profile = agent.profile if agent.profile else {}
    if isinstance(profile, str):
        try:
            profile = json.loads(profile)
        except json.JSONDecodeError:
            profile = {}

    return {
        "success": True,
        "swarm_id": swarm_id,
        "agent_id": agent_id,
        "db_id": agent.id,
        "name": agent.name,
        "profile": profile,
        "is_active": agent.isActive,
        "joined_at": agent.joinedAt.isoformat() if agent.joinedAt else None,
    }


async def update_agent_profile(
    swarm_id: str,
    agent_id: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Update an agent's profile.

    Profile structure:
    {
        "display_name": str,       # "Jarvis ⚡"
        "personality": str,        # "INTJ - Strategic, decisive"
        "role_description": str,   # "Chief Coordinator"
        "boundaries": list[str],   # ["Never send without approval", ...]
        "communication_style": str, # "Direct, no fluff"
        "decision_making": str,    # "Analyze then decide"
        "soul_document_path": str, # "agents/jarvis/SOUL.md"
        "memory_scope": str,       # "agent" | "project" | "team"
        "custom": dict             # Any additional fields
    }

    Args:
        swarm_id: The swarm ID
        agent_id: The agent's unique identifier
        profile: The profile data to update (merged with existing)

    Returns:
        Dict with updated profile or error
    """
    db = await get_db()

    # Find agent in swarm
    agent = await db.swarmagent.find_first(
        where={
            "swarmId": swarm_id,
            "agentId": agent_id,
        }
    )

    if not agent:
        return {
            "success": False,
            "error": f"Agent '{agent_id}' not found in swarm",
            "profile": None,
        }

    # Merge with existing profile
    existing_profile = agent.profile if agent.profile else {}
    if isinstance(existing_profile, str):
        try:
            existing_profile = json.loads(existing_profile)
        except json.JSONDecodeError:
            existing_profile = {}

    merged_profile = {**existing_profile, **profile}

    # Update agent with new profile
    await db.swarmagent.update(
        where={"id": agent.id},
        data={"profile": Json(merged_profile)},
    )

    logger.info(f"Updated profile for agent {agent_id} in swarm {swarm_id}")

    return {
        "success": True,
        "swarm_id": swarm_id,
        "agent_id": agent_id,
        "profile": merged_profile,
        "message": "Profile updated successfully",
    }


# =============================================================================
# RESOURCE CLAIMS
# =============================================================================


async def acquire_claim(
    swarm_id: str,
    agent_id: str,
    resource_type: str,
    resource_id: str,
    timeout_seconds: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Acquire exclusive access to a resource.

    Args:
        swarm_id: The swarm ID
        agent_id: The agent's unique identifier
        resource_type: Type of resource (file, function, module, etc.)
        resource_id: Identifier of the resource
        timeout_seconds: Claim timeout in seconds

    Returns:
        Dict with claim status
    """
    db = await get_db()

    # Find agent in swarm
    agent = await db.swarmagent.find_first(
        where={
            "swarmId": swarm_id,
            "agentId": agent_id,
            "isActive": True,
        }
    )

    if not agent:
        return {
            "success": False,
            "error": "Agent not in swarm",
            "claim_id": None,
        }

    # Check for existing active claim (with lazy expiration)
    existing = await db.resourceclaim.find_first(
        where={
            "swarmId": swarm_id,
            "resourceType": resource_type,
            "resourceId": resource_id,
            "status": "ACTIVE",
        }
    )

    if existing:
        # Lazy expiration check
        if existing.expiresAt and existing.expiresAt < datetime.now(UTC):
            # Claim expired, mark it
            await db.resourceclaim.update(
                where={"id": existing.id},
                data={"status": "EXPIRED"},
            )
            logger.info(f"Expired stale claim {existing.id}")
        else:
            # Claim is still active
            if existing.agentId == agent.id:
                # Same agent, extend the claim
                new_expires = datetime.now(UTC) + timedelta(seconds=timeout_seconds)
                await db.resourceclaim.update(
                    where={"id": existing.id},
                    data={"expiresAt": new_expires},
                )
                return {
                    "success": True,
                    "claim_id": existing.id,
                    "extended": True,
                    "expires_at": new_expires.isoformat(),
                    "message": "Claim extended",
                }
            else:
                # Another agent has the claim
                return {
                    "success": False,
                    "error": "Resource already claimed by another agent",
                    "claim_id": None,
                    "claimed_by": existing.agentId,
                    "expires_at": existing.expiresAt.isoformat() if existing.expiresAt else None,
                }

    # Create new claim
    expires_at = datetime.now(UTC) + timedelta(seconds=timeout_seconds)

    claim = await db.resourceclaim.create(
        data={
            "swarm": {"connect": {"id": swarm_id}},
            "agent": {"connect": {"id": agent.id}},
            "resourceType": resource_type,
            "resourceId": resource_id,
            "status": "ACTIVE",
            "expiresAt": expires_at,
        }
    )

    logger.info(f"Agent {agent_id} claimed {resource_type}:{resource_id}")

    return {
        "success": True,
        "claim_id": claim.id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "expires_at": expires_at.isoformat(),
        "message": "Resource claimed successfully",
    }


async def release_claim(
    swarm_id: str,
    agent_id: str,
    claim_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> dict[str, Any]:
    """Release a resource claim.

    Args:
        swarm_id: The swarm ID
        agent_id: The agent's unique identifier
        claim_id: Specific claim ID to release
        resource_type: Type of resource (alternative to claim_id)
        resource_id: Resource identifier (alternative to claim_id)

    Returns:
        Dict with release status
    """
    db = await get_db()

    # Find agent in swarm
    agent = await db.swarmagent.find_first(
        where={
            "swarmId": swarm_id,
            "agentId": agent_id,
            "isActive": True,
        }
    )

    if not agent:
        return {
            "success": False,
            "error": "Agent not in swarm",
        }

    # Build query
    where: dict[str, Any] = {
        "swarmId": swarm_id,
        "agentId": agent.id,
        "status": "ACTIVE",
    }

    if claim_id:
        where["id"] = claim_id
    elif resource_type and resource_id:
        where["resourceType"] = resource_type
        where["resourceId"] = resource_id
    else:
        return {
            "success": False,
            "error": "Must provide claim_id or resource_type+resource_id",
        }

    # Find and release claim
    claim = await db.resourceclaim.find_first(where=where)

    if not claim:
        return {
            "success": False,
            "error": "Claim not found or not owned by agent",
        }

    await db.resourceclaim.update(
        where={"id": claim.id},
        data={
            "status": "RELEASED",
            "releasedAt": datetime.now(UTC),
        },
    )

    logger.info(f"Released claim {claim.id}")

    return {
        "success": True,
        "claim_id": claim.id,
        "message": "Claim released successfully",
    }


async def check_claim(
    swarm_id: str,
    resource_type: str,
    resource_id: str,
) -> dict[str, Any]:
    """Check if a resource is claimed.

    Args:
        swarm_id: The swarm ID
        resource_type: Type of resource
        resource_id: Resource identifier

    Returns:
        Dict with claim status
    """
    db = await get_db()

    claim = await db.resourceclaim.find_first(
        where={
            "swarmId": swarm_id,
            "resourceType": resource_type,
            "resourceId": resource_id,
            "status": "ACTIVE",
        },
        include={"agent": True},
    )

    if not claim:
        return {
            "claimed": False,
            "resource_type": resource_type,
            "resource_id": resource_id,
        }

    # Lazy expiration
    if claim.expiresAt and claim.expiresAt < datetime.now(UTC):
        await db.resourceclaim.update(
            where={"id": claim.id},
            data={"status": "EXPIRED"},
        )
        return {
            "claimed": False,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "note": "Previous claim expired",
        }

    return {
        "claimed": True,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "claim_id": claim.id,
        "claimed_by": claim.agent.agentId if claim.agent else None,
        "expires_at": claim.expiresAt.isoformat() if claim.expiresAt else None,
    }


# =============================================================================
# SHARED STATE
# =============================================================================


async def get_state(
    swarm_id: str,
    key: str,
) -> dict[str, Any]:
    """Get shared state value.

    Args:
        swarm_id: The swarm ID
        key: State key

    Returns:
        Dict with state value and metadata
    """
    db = await get_db()

    state = await db.sharedstate.find_first(
        where={
            "swarmId": swarm_id,
            "key": key,
        }
    )

    if not state:
        return {
            "found": False,
            "key": key,
            "value": None,
        }

    # Parse JSON value - Prisma Json fields return Python objects directly, not strings
    # So we need to handle both cases: already-deserialized dicts/lists and raw strings
    if state.value is None:
        value = None
    elif isinstance(state.value, (dict, list)):
        # Prisma already deserialized the Json field
        value = state.value
    elif isinstance(state.value, str):
        # Fallback: try to parse if it's somehow a string
        try:
            value = json.loads(state.value)
        except json.JSONDecodeError:
            value = state.value
    else:
        # Other types (int, float, bool) - use as-is
        value = state.value

    # Unwrap wrapper objects created by set_state for non-JSON types
    # set_state wraps scalars as {"value": X} and strings as {"raw": X}
    if isinstance(value, dict) and len(value) == 1:
        if "value" in value:
            value = value["value"]  # Unwrap scalar wrapper
        elif "raw" in value:
            value = value["raw"]  # Unwrap string wrapper

    return {
        "found": True,
        "key": key,
        "value": value,
        "version": state.version,
        "updated_at": state.updatedAt.isoformat() if state.updatedAt else None,
        "updated_by": state.updatedBy,
    }


async def poll_state(
    swarm_id: str,
    keys: list[str],
    last_versions: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Poll for state changes across multiple keys.

    Returns only keys that have changed since their last_versions.
    Efficient for monitoring multiple keys without individual get calls.

    Args:
        swarm_id: The swarm ID
        keys: List of state keys to monitor
        last_versions: Map of key -> last known version. Only keys with
                      newer versions are returned. Default {} means return all.

    Returns:
        Dict with changed keys and their current values/versions
    """
    db = await get_db()

    if last_versions is None:
        last_versions = {}

    # Fetch all requested keys in one query
    states = await db.sharedstate.find_many(
        where={
            "swarmId": swarm_id,
            "key": {"in": keys},
        }
    )

    # Build result with only changed keys
    changed: dict[str, dict[str, Any]] = {}
    unchanged_keys: list[str] = []
    missing_keys: list[str] = []

    # Track which keys were found
    found_keys = {s.key for s in states}

    for key in keys:
        if key not in found_keys:
            missing_keys.append(key)

    for state in states:
        last_ver = last_versions.get(state.key, 0)

        if state.version > last_ver:
            # Parse value (same logic as get_state)
            value = state.value
            if isinstance(value, dict) and len(value) == 1:
                if "value" in value:
                    value = value["value"]
                elif "raw" in value:
                    value = value["raw"]

            changed[state.key] = {
                "value": value,
                "version": state.version,
                "updated_at": state.updatedAt.isoformat() if state.updatedAt else None,
                "updated_by": state.updatedBy,
            }
        else:
            unchanged_keys.append(state.key)

    return {
        "swarm_id": swarm_id,
        "changed": changed,
        "unchanged_count": len(unchanged_keys),
        "missing_keys": missing_keys,
        "total_polled": len(keys),
        "has_changes": len(changed) > 0,
    }


async def set_state(
    swarm_id: str,
    agent_id: str,
    key: str,
    value: Any,
    expected_version: int | None = None,
    ttl_seconds: int | None = None,
) -> dict[str, Any]:
    """Set shared state value with optimistic locking.

    Args:
        swarm_id: The swarm ID
        agent_id: Agent setting the value
        key: State key
        value: Value to set (will be JSON serialized)
        expected_version: If provided, only update if version matches (optimistic lock)
        ttl_seconds: If provided, state expires after this many seconds

    Returns:
        Dict with new version and status
    """
    db = await get_db()

    # Calculate expiration time if TTL provided
    expires_at = None
    if ttl_seconds is not None and ttl_seconds > 0:
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

    # Ensure value is JSON-serializable - Prisma expects dict/list for Json fields
    if isinstance(value, str):
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            parsed_value = {"raw": value}
    elif isinstance(value, (dict, list)):
        parsed_value = value
    else:
        parsed_value = {"value": value}

    # Check existing state
    existing = await db.sharedstate.find_first(
        where={
            "swarmId": swarm_id,
            "key": key,
        }
    )

    if existing:
        # Version check (optimistic locking)
        if expected_version is not None and existing.version != expected_version:
            return {
                "success": False,
                "error": "Version mismatch (concurrent update)",
                "current_version": existing.version,
                "expected_version": expected_version,
            }

        # Update existing
        new_version = existing.version + 1
        update_data: dict[str, Any] = {
            "value": Json(parsed_value),
            "version": new_version,
            "updatedBy": agent_id,
        }
        if expires_at is not None:
            update_data["expiresAt"] = expires_at

        await db.sharedstate.update(
            where={"id": existing.id},
            data=update_data,
        )

        result: dict[str, Any] = {
            "success": True,
            "key": key,
            "version": new_version,
            "message": "State updated",
        }
        if expires_at is not None:
            result["expires_at"] = expires_at.isoformat()
        return result
    else:
        # Create new state
        create_data: dict[str, Any] = {
            "swarmId": swarm_id,
            "key": key,
            "value": Json(parsed_value),
            "version": 1,
            "updatedBy": agent_id,
        }
        if expires_at is not None:
            create_data["expiresAt"] = expires_at

        await db.sharedstate.create(data=create_data)

        result = {
            "success": True,
            "key": key,
            "version": 1,
            "message": "State created",
        }
        if expires_at is not None:
            result["expires_at"] = expires_at.isoformat()
        return result


# =============================================================================
# TASK QUEUE
# =============================================================================


async def create_task(
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
    """Create a task in the swarm's queue.

    Args:
        swarm_id: The swarm ID
        agent_id: Agent creating the task
        title: Task title
        description: Task description
        priority: Priority (higher = more urgent)
        deadline: Optional deadline (datetime or ISO string)
        depends_on: List of task IDs this task depends on
        metadata: Additional task metadata
        for_agent_id: Pre-assign task to specific agent (task affinity).
                      If set, only this agent can claim the task.

    Returns:
        Dict with task info
    """
    db = await get_db()

    # Verify swarm exists before attempting to create task
    swarm = await db.agentswarm.find_unique(where={"id": swarm_id})
    if not swarm:
        logger.warning(f"rlm_task_create: swarm '{swarm_id}' not found")
        return {"error": f"Swarm '{swarm_id}' not found"}

    if not swarm.isActive:
        logger.warning(f"rlm_task_create: swarm '{swarm_id}' is not active")
        return {"error": f"Swarm '{swarm_id}' is not active"}

    # Parse deadline if string
    due_at = None
    if deadline:
        if isinstance(deadline, str):
            due_at = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        else:
            due_at = deadline

    # Build task data
    task_data: dict[str, Any] = {
        "swarm": {"connect": {"id": swarm_id}},
        "title": title,
        "description": description,
        "status": "PENDING",
        "priority": priority,
        "dueAt": due_at,
        "dependsOn": depends_on or [],
    }

    # Pre-assign to specific agent if for_agent_id is provided
    assigned_agent_db_id = None
    if for_agent_id:
        # Find the agent's DB record (SwarmAgent.id, not the agentId string)
        target_agent = await db.swarmagent.find_first(
            where={
                "swarmId": swarm_id,
                "agentId": for_agent_id,
                "isActive": True,
            }
        )
        if target_agent:
            task_data["agent"] = {"connect": {"id": target_agent.id}}
            assigned_agent_db_id = target_agent.id
        else:
            logger.warning(f"for_agent_id '{for_agent_id}' not found in swarm {swarm_id}, task will be unassigned")

    task = await db.swarmtask.create(data=task_data)

    logger.info(f"Created task {task.id} in swarm {swarm_id}" + (f" for agent {for_agent_id}" if for_agent_id else ""))

    return {
        "success": True,
        "task_id": task.id,
        "title": title,
        "priority": priority,
        "deadline": due_at.isoformat() if due_at else None,
        "depends_on": depends_on or [],
        "for_agent_id": for_agent_id,
        "assigned": assigned_agent_db_id is not None,
        "message": "Task created" + (f" for agent {for_agent_id}" if for_agent_id else ""),
    }


async def create_tasks_bulk(
    swarm_id: str,
    agent_id: str,
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create multiple tasks in bulk.

    Args:
        swarm_id: The swarm ID
        agent_id: Agent creating the tasks
        tasks: List of task objects with title, description, priority, deadline,
               depends_on, metadata, for_agent_id

    Returns:
        Dict with created task IDs and stats
    """
    db = await get_db()

    # Verify swarm exists before attempting to create tasks
    swarm = await db.agentswarm.find_unique(where={"id": swarm_id})
    if not swarm:
        logger.warning(f"rlm_task_bulk_create: swarm '{swarm_id}' not found")
        return {"error": f"Swarm '{swarm_id}' not found", "created": 0, "failed": len(tasks)}

    if not swarm.isActive:
        logger.warning(f"rlm_task_bulk_create: swarm '{swarm_id}' is not active")
        return {"error": f"Swarm '{swarm_id}' is not active", "created": 0, "failed": len(tasks)}

    created_ids: list[str] = []
    failed: list[dict[str, Any]] = []

    # Pre-fetch all target agents for task affinity (batch lookup)
    target_agent_ids = {t.get("for_agent_id") for t in tasks if t.get("for_agent_id")}
    agent_id_to_db_id: dict[str, str] = {}
    if target_agent_ids:
        target_agents = await db.swarmagent.find_many(
            where={
                "swarmId": swarm_id,
                "agentId": {"in": list(target_agent_ids)},
                "isActive": True,
            }
        )
        agent_id_to_db_id = {a.agentId: a.id for a in target_agents}

    for i, task_data in enumerate(tasks):
        title = task_data.get("title", "")
        if not title:
            failed.append({"index": i, "error": "title is required"})
            continue

        try:
            # Parse deadline if provided
            due_at = None
            deadline = task_data.get("deadline")
            if deadline:
                if isinstance(deadline, str):
                    due_at = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
                else:
                    due_at = deadline

            # Build task data
            create_data: dict[str, Any] = {
                "swarm": {"connect": {"id": swarm_id}},
                "title": title,
                "description": task_data.get("description"),
                "status": "PENDING",
                "priority": task_data.get("priority", 0),
                "dueAt": due_at,
                "dependsOn": task_data.get("depends_on") or [],
            }

            # Handle task affinity (for_agent_id)
            for_agent_id = task_data.get("for_agent_id")
            if for_agent_id:
                db_id = agent_id_to_db_id.get(for_agent_id)
                if db_id:
                    create_data["agent"] = {"connect": {"id": db_id}}
                else:
                    logger.warning(f"for_agent_id '{for_agent_id}' not found for task {i}")

            task = await db.swarmtask.create(data=create_data)
            created_ids.append(task.id)
        except Exception as e:
            failed.append({"index": i, "title": title, "error": str(e)})

    logger.info(f"Bulk created {len(created_ids)} tasks in swarm {swarm_id}")

    return {
        "success": True,
        "created_count": len(created_ids),
        "task_ids": created_ids,
        "failed_count": len(failed),
        "failed": failed if failed else None,
    }


async def claim_task(
    swarm_id: str,
    agent_id: str,
    task_id: str | None = None,
    timeout_seconds: int = DEFAULT_TASK_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Claim a task from the queue.

    If task_id is not provided, claims the highest priority available task
    (one whose dependencies are all completed).

    Task affinity rules:
    - If task has assignedTo set (pre-assigned), only that agent can claim it
    - If task has no assignedTo (null), any agent can claim it

    Args:
        swarm_id: The swarm ID
        agent_id: Agent claiming the task
        task_id: Specific task to claim (optional)
        timeout_seconds: Timeout for task completion

    Returns:
        Dict with task info or error
    """
    db = await get_db()

    # Find agent
    agent = await db.swarmagent.find_first(
        where={
            "swarmId": swarm_id,
            "agentId": agent_id,
            "isActive": True,
        }
    )

    if not agent:
        return {
            "success": False,
            "error": "Agent not in swarm",
            "task_id": None,
        }

    if task_id:
        # Claim specific task
        task = await db.swarmtask.find_first(
            where={
                "id": task_id,
                "swarmId": swarm_id,
                "status": "PENDING",
            }
        )

        if not task:
            return {
                "success": False,
                "error": "Task not found or not available",
                "task_id": None,
            }

        # Check task affinity - agent can only claim if assigned to them or unassigned
        if task.assignedTo is not None and task.assignedTo != agent.id:
            return {
                "success": False,
                "error": "Task is assigned to another agent",
                "task_id": task.id,
                "assigned_to": task.assignedTo,
            }
    else:
        # Find available task (dependencies completed + agent affinity filter)
        task = await _get_available_task(swarm_id, agent_db_id=agent.id)

        if not task:
            return {
                "success": False,
                "error": "No available tasks for this agent",
                "task_id": None,
            }

    # Check dependencies
    if task.dependsOn:
        deps_complete = await _check_dependencies_complete(swarm_id, task.dependsOn)
        if not deps_complete:
            return {
                "success": False,
                "error": "Task dependencies not yet completed",
                "task_id": task.id,
                "depends_on": task.dependsOn,
            }

    # Claim the task
    deadline = datetime.now(UTC) + timedelta(seconds=timeout_seconds)

    await db.swarmtask.update(
        where={"id": task.id},
        data={
            "status": "IN_PROGRESS",
            "agent": {"connect": {"id": agent.id}},  # Sets assignedTo via relation
            "startedAt": datetime.now(UTC),
            "claimedAt": datetime.now(UTC),
        },
    )

    logger.info(f"Agent {agent_id} claimed task {task.id}")

    return {
        "success": True,
        "task_id": task.id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "deadline": deadline.isoformat(),
        "was_preassigned": task.assignedTo is not None,
        "message": "Task claimed",
    }


async def complete_task(
    swarm_id: str,
    agent_id: str,
    task_id: str,
    result: Any | None = None,
    success: bool = True,
) -> dict[str, Any]:
    """Complete a claimed task.

    Args:
        swarm_id: The swarm ID
        agent_id: Agent completing the task
        task_id: Task to complete
        result: Task result data
        success: Whether task completed successfully

    Returns:
        Dict with completion status
    """
    db = await get_db()

    # Find agent
    agent = await db.swarmagent.find_first(
        where={
            "swarmId": swarm_id,
            "agentId": agent_id,
            "isActive": True,
        }
    )

    if not agent:
        return {
            "success": False,
            "error": "Agent not in swarm",
        }

    # Find task
    task = await db.swarmtask.find_first(
        where={
            "id": task_id,
            "swarmId": swarm_id,
            "assignedTo": agent.id,
            "status": "IN_PROGRESS",
        }
    )

    if not task:
        return {
            "success": False,
            "error": "Task not found or not assigned to agent",
        }

    # Update task
    status = "COMPLETED" if success else "FAILED"

    # Handle result - parse if string, use directly if dict/list
    parsed_result = result
    if isinstance(result, str):
        try:
            parsed_result = json.loads(result)
        except json.JSONDecodeError:
            parsed_result = {"raw": result}

    # Build update data - only include result if not None
    update_data: dict[str, Any] = {
        "status": status,
        "completedAt": datetime.now(UTC),
    }
    if parsed_result is not None:
        update_data["result"] = Json(parsed_result)

    await db.swarmtask.update(
        where={"id": task.id},
        data=update_data,
    )

    logger.info(f"Task {task_id} completed with status {status}")

    return {
        "success": True,
        "task_id": task_id,
        "status": status.lower(),
        "message": f"Task marked as {status.lower()}",
    }


async def list_tasks(
    swarm_id: str,
    status: str | None = None,
    assigned_to: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List tasks in a swarm.

    Args:
        swarm_id: The swarm ID
        status: Filter by status
        assigned_to: Filter by assigned agent
        limit: Maximum tasks to return

    Returns:
        Dict with tasks list
    """
    db = await get_db()

    where: dict[str, Any] = {"swarmId": swarm_id}

    if status:
        where["status"] = status.upper()

    if assigned_to:
        agent = await db.swarmagent.find_first(where={"swarmId": swarm_id, "agentId": assigned_to})
        if agent:
            where["assignedTo"] = agent.id

    tasks = await db.swarmtask.find_many(
        where=where,
        order=[{"priority": "desc"}, {"createdAt": "asc"}],
        take=limit,
        include={"agent": True},  # Include agent relation to get agentId
    )

    return {
        "tasks": [
            {
                "task_id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status.lower(),
                "priority": t.priority,
                "depends_on": t.dependsOn,
                "assigned_to": t.agent.agentId if t.agent else None,  # External agent ID
                "created_at": t.createdAt.isoformat() if t.createdAt else None,
                "deadline": t.dueAt.isoformat() if t.dueAt else None,
            }
            for t in tasks
        ],
        "total": len(tasks),
    }


async def list_tasks_enhanced(
    swarm_id: str,
    status: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    """List tasks in a swarm with cursor-based pagination.

    Args:
        swarm_id: The swarm ID
        status: Filter by status (pending, in_progress, completed, failed, cancelled)
        limit: Maximum tasks to return (default 50, max 100)
        cursor: Cursor for pagination (task ID to start after)

    Returns:
        Dict with tasks list, pagination info
    """
    db = await get_db()

    # Clamp limit
    limit = min(max(1, limit), 100)

    where: dict[str, Any] = {"swarmId": swarm_id}

    if status:
        where["status"] = status.upper()

    # Cursor-based pagination
    if cursor:
        where["id"] = {"gt": cursor}

    tasks = await db.swarmtask.find_many(
        where=where,
        order=[{"createdAt": "asc"}, {"id": "asc"}],
        take=limit + 1,  # Fetch one extra to check if there's more
        include={"agent": True},
    )

    # Check if there are more results
    has_more = len(tasks) > limit
    if has_more:
        tasks = tasks[:limit]

    # Get next cursor
    next_cursor = tasks[-1].id if tasks and has_more else None

    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status.lower() if hasattr(t.status, "lower") else str(t.status).lower(),
                "updated_at": (t.completedAt or t.startedAt or t.createdAt).isoformat()
                if (t.completedAt or t.startedAt or t.createdAt)
                else None,
                "owner": t.agent.agentId if t.agent else None,
            }
            for t in tasks
        ],
        "total": len(tasks),
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


async def get_task_stats(swarm_id: str) -> dict[str, Any]:
    """Get aggregated task statistics for a swarm.

    Args:
        swarm_id: The swarm ID

    Returns:
        Dict with counts by status: done, in_progress, blocked, pending
    """
    db = await get_db()

    # Get all tasks for this swarm
    # Note: Python Prisma doesn't support 'select', fetch all fields
    tasks = await db.swarmtask.find_many(
        where={"swarmId": swarm_id},
    )

    # Count by status
    counts = {
        "done": 0,  # COMPLETED
        "in_progress": 0,  # IN_PROGRESS or CLAIMED
        "blocked": 0,  # PENDING with unmet dependencies
        "pending": 0,  # PENDING with no dependencies or all deps complete
        "failed": 0,  # FAILED
        "cancelled": 0,  # CANCELLED
    }

    # Get completed task IDs for dependency checking
    completed_ids = {t.id for t in tasks if str(t.status).upper() == "COMPLETED"}

    for task in tasks:
        status = str(task.status).upper()

        if status == "COMPLETED":
            counts["done"] += 1
        elif status == "FAILED":
            counts["failed"] += 1
        elif status == "CANCELLED":
            counts["cancelled"] += 1
        elif status in ("IN_PROGRESS", "CLAIMED"):
            counts["in_progress"] += 1
        elif status == "PENDING":
            # Check if blocked by dependencies
            deps = task.dependsOn or []
            if deps and not all(dep_id in completed_ids for dep_id in deps):
                counts["blocked"] += 1
            else:
                counts["pending"] += 1

    return {
        "swarm_id": swarm_id,
        "done": counts["done"],
        "in_progress": counts["in_progress"],
        "blocked": counts["blocked"],
        "pending": counts["pending"],
        "failed": counts["failed"],
        "cancelled": counts["cancelled"],
        "total": len(tasks),
    }


async def _get_available_task(swarm_id: str, agent_db_id: str | None = None):
    """Get highest priority task with all dependencies completed.

    Task affinity rules:
    - If task has assignedTo set, only that agent can claim it
    - If task has no assignedTo (null), any agent can claim it

    Args:
        swarm_id: The swarm ID
        agent_db_id: The claiming agent's DB ID (SwarmAgent.id).
                     If provided, filters to tasks assigned to this agent OR unassigned tasks.
    """
    db = await get_db()

    # Build where clause with agent affinity filter
    where_clause: dict[str, Any] = {
        "swarmId": swarm_id,
        "status": "PENDING",
    }

    # Apply agent affinity filter: agent can only claim tasks assigned to them OR unassigned
    if agent_db_id:
        where_clause["OR"] = [
            {"assignedTo": agent_db_id},  # Tasks assigned to this agent
            {"assignedTo": None},          # Unassigned tasks (any agent can claim)
        ]

    # Get all pending tasks ordered by priority
    pending_tasks = await db.swarmtask.find_many(
        where=where_clause,
        order=[{"priority": "desc"}, {"createdAt": "asc"}],
    )

    for task in pending_tasks:
        if not task.dependsOn:
            return task

        # Check if all dependencies are completed
        deps_complete = await _check_dependencies_complete(swarm_id, task.dependsOn)
        if deps_complete:
            return task

    return None


async def _check_dependencies_complete(swarm_id: str, dep_ids: list[str]) -> bool:
    """Check if all dependency tasks are completed."""
    db = await get_db()

    completed_count = await db.swarmtask.count(
        where={
            "swarmId": swarm_id,
            "id": {"in": dep_ids},
            "status": "COMPLETED",
        }
    )

    return completed_count == len(dep_ids)


# ============================================
# Task Recovery Functions (P2)
# ============================================


async def unclaim_task(
    swarm_id: str,
    task_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Unclaim a task, returning it to PENDING status.

    Use this to recover tasks that are stuck (claimed but not progressing).

    Args:
        swarm_id: The swarm ID
        task_id: The task ID to unclaim
        reason: Optional reason for unclaiming

    Returns:
        Dict with unclaim confirmation
    """
    db = await get_db()

    # Get the task
    task = await db.swarmtask.find_first(
        where={"id": task_id, "swarmId": swarm_id}
    )

    if not task:
        return {"success": False, "error": "Task not found"}

    if task.status not in ["CLAIMED", "IN_PROGRESS"]:
        return {
            "success": False,
            "error": f"Task is {task.status}, cannot unclaim",
        }

    # Reset task to PENDING
    await db.swarmtask.update(
        where={"id": task_id},
        data={
            "status": "PENDING",
            "assignedTo": None,
            "claimedAt": None,
            "startedAt": None,
        },
    )

    return {
        "success": True,
        "task_id": task_id,
        "previous_status": task.status,
        "previous_agent": task.assignedTo,
        "reason": reason,
        "message": "Task unclaimed and returned to PENDING",
    }


async def recover_stuck_tasks(
    swarm_id: str,
    stuck_threshold_minutes: int = 30,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Find and optionally recover tasks that are stuck.

    A task is considered stuck if:
    - Status is CLAIMED or IN_PROGRESS
    - claimedAt or startedAt is older than threshold

    Args:
        swarm_id: The swarm ID
        stuck_threshold_minutes: Minutes after which a task is considered stuck
        dry_run: If True, only report stuck tasks without recovering them

    Returns:
        Dict with stuck tasks and recovery results
    """
    db = await get_db()

    threshold = datetime.now(UTC) - timedelta(minutes=stuck_threshold_minutes)

    # Find stuck tasks
    stuck_tasks = await db.swarmtask.find_many(
        where={
            "swarmId": swarm_id,
            "status": {"in": ["CLAIMED", "IN_PROGRESS"]},
            "OR": [
                {"claimedAt": {"lt": threshold}},
                {"startedAt": {"lt": threshold}},
            ],
        },
        order=[{"claimedAt": "asc"}],
    )

    result = {
        "swarm_id": swarm_id,
        "threshold_minutes": stuck_threshold_minutes,
        "stuck_count": len(stuck_tasks),
        "dry_run": dry_run,
        "stuck_tasks": [],
        "recovered": [],
    }

    for task in stuck_tasks:
        stuck_info = {
            "task_id": task.id,
            "title": task.title,
            "status": task.status,
            "assigned_to": task.assignedTo,
            "claimed_at": task.claimedAt.isoformat() if task.claimedAt else None,
            "stuck_for_minutes": int(
                (datetime.now(UTC) - (task.claimedAt or task.startedAt or datetime.now(UTC))).total_seconds() / 60
            ),
        }
        result["stuck_tasks"].append(stuck_info)

        if not dry_run:
            # Recover the task
            recovery = await unclaim_task(swarm_id, task.id, reason="Auto-recovered: stuck threshold exceeded")
            if recovery.get("success"):
                result["recovered"].append(task.id)

    result["recovered_count"] = len(result["recovered"])

    return result
