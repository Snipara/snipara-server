"""Swarm services - re-exports from coordinator and events modules.

This module provides a unified interface for swarm functionality,
re-exporting functions from swarm_coordinator and swarm_events.
"""

from .swarm_coordinator import (
    acquire_claim,
    check_claim,
    claim_task,
    complete_task,
    create_swarm,
    create_task,
    get_agent_profile,
    get_state,
    get_swarm_info,
    get_task_stats,
    join_swarm,
    leave_swarm,
    list_tasks,
    list_tasks_enhanced,
    recover_stuck_tasks,
    release_claim,
    set_state,
    unclaim_task,
    update_agent_profile,
)
from .swarm_events import (
    broadcast_agent_event,
    broadcast_claim_event,
    broadcast_event,
    broadcast_state_event,
    broadcast_task_event,
    get_recent_events,
    get_task_events,
    subscribe_to_swarm,
    unsubscribe_from_swarm,
)

__all__ = [
    # Coordinator functions
    "create_swarm",
    "join_swarm",
    "leave_swarm",
    "get_swarm_info",
    "get_agent_profile",
    "update_agent_profile",
    "acquire_claim",
    "release_claim",
    "check_claim",
    "get_state",
    "set_state",
    "create_task",
    "claim_task",
    "complete_task",
    "list_tasks",
    "list_tasks_enhanced",
    "unclaim_task",
    "recover_stuck_tasks",
    "get_task_stats",
    # Event functions
    "broadcast_event",
    "broadcast_task_event",
    "broadcast_claim_event",
    "broadcast_agent_event",
    "broadcast_state_event",
    "get_recent_events",
    "get_task_events",
    "subscribe_to_swarm",
    "unsubscribe_from_swarm",
]
