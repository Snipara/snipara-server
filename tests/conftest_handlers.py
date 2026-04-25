"""Pytest configuration for handler tests.

This module sets up mocks for modules that require external dependencies
(database, redis, etc.) before the test modules are imported.
"""

import os
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Set required environment variables before importing any modules
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["NEON_DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["NEXTAUTH_SECRET"] = "test-secret"


def setup_module_mocks():
    """Set up module mocks for testing handlers without external dependencies."""
    # Mock services modules that require external dependencies.
    services_mock = types.ModuleType("src.services")
    services_mock.__path__ = [
        str(Path(__file__).resolve().parent.parent / "src" / "services")
    ]
    sys.modules["src.services"] = services_mock
    sys.modules["src.services.cache"] = MagicMock()

    agent_limits_mock = MagicMock()
    agent_limits_mock.check_memory_limits = AsyncMock(return_value=(True, None))
    sys.modules["src.services.agent_limits"] = agent_limits_mock

    # Create agent_memory service mock with async functions
    agent_memory_mock = MagicMock()
    agent_memory_mock.store_memory = AsyncMock(
        return_value={"memory_id": "test", "success": True}
    )
    agent_memory_mock.remember_if_novel = AsyncMock(
        return_value={"memory_id": "test", "stored": True}
    )
    agent_memory_mock.end_of_task_commit = AsyncMock(
        return_value={"stored_count": 1, "skipped_count": 0, "candidates": []}
    )
    agent_memory_mock.semantic_recall = AsyncMock(
        return_value={"memories": [], "total": 0}
    )
    agent_memory_mock.list_memories = AsyncMock(
        return_value={"memories": [], "total": 0}
    )
    agent_memory_mock.store_memories_bulk = AsyncMock(
        return_value={"created": 0, "memory_ids": []}
    )
    agent_memory_mock.invalidate_memory = AsyncMock(
        return_value={"memory_id": "test", "status": "INVALIDATED"}
    )
    agent_memory_mock.supersede_memory = AsyncMock(
        return_value={
            "old_memory_id": "old",
            "new_memory_id": "new",
            "old_status": "SUPERSEDED",
            "new_status": "ACTIVE",
        }
    )
    agent_memory_mock.delete_memories = AsyncMock(return_value={"deleted": 0})
    agent_memory_mock.append_journal = AsyncMock(
        return_value={"entry_id": "journal-test"}
    )
    agent_memory_mock.get_journal = AsyncMock(return_value={"entries": [], "total": 0})
    agent_memory_mock.summarize_journal = AsyncMock(
        return_value={"summary": "", "entry_count": 0}
    )
    agent_memory_mock.get_session_memories = AsyncMock(return_value={"memories": []})
    agent_memory_mock.compact_memories = AsyncMock(
        return_value={"promoted": 0, "archived": 0, "deduplicated": 0}
    )
    agent_memory_mock.get_daily_brief = AsyncMock(return_value={"brief": ""})
    agent_memory_mock.create_tenant_profile = AsyncMock(
        return_value={"profile_id": "tenant-profile-test"}
    )
    agent_memory_mock.get_tenant_profile = AsyncMock(return_value={"profile": None})
    sys.modules["src.services.agent_memory"] = agent_memory_mock

    # Create agent_limits mock used by handler modules
    agent_limits_mock = MagicMock()
    agent_limits_mock.check_memory_limits = AsyncMock(return_value=(True, None))
    sys.modules["src.services.agent_limits"] = agent_limits_mock

    # Create swarm service mock with async functions
    swarm_mock = MagicMock()
    swarm_mock.create_swarm = AsyncMock(return_value={"id": "test", "name": "test"})
    swarm_mock.join_swarm = AsyncMock(return_value={"joined": True})
    swarm_mock.acquire_claim = AsyncMock(return_value={"claim_id": "test"})
    swarm_mock.release_claim = AsyncMock(return_value={"released": True})
    swarm_mock.get_state = AsyncMock(return_value={"value": None, "version": 0})
    swarm_mock.set_state = AsyncMock(return_value={"version": 1})
    swarm_mock.broadcast_event = AsyncMock(return_value={"delivered": 0})
    swarm_mock.create_task = AsyncMock(return_value={"task_id": "test"})
    swarm_mock.claim_task = AsyncMock(return_value={"task": None})
    swarm_mock.complete_task = AsyncMock(return_value={"completed": True})
    swarm_mock.list_tasks = AsyncMock(return_value={"tasks": []})
    swarm_mock.task_stats = AsyncMock(return_value={"stats": {}})
    swarm_mock.task_events = AsyncMock(return_value={"events": []})
    sys.modules["src.services.swarm"] = swarm_mock

    htask_coordinator_mock = MagicMock()
    htask_coordinator_mock.create_htask = AsyncMock(return_value={"task_id": "test"})
    htask_coordinator_mock.create_feature_with_workstreams = AsyncMock(
        return_value={"task_id": "feature-test"}
    )
    htask_coordinator_mock.get_htask = AsyncMock(return_value={"task_id": "test"})
    htask_coordinator_mock.get_htask_tree = AsyncMock(return_value={"task_id": "test"})
    htask_coordinator_mock.update_htask = AsyncMock(return_value={"updated": True})
    htask_coordinator_mock.block_task = AsyncMock(return_value={"blocked": True})
    htask_coordinator_mock.unblock_task = AsyncMock(return_value={"unblocked": True})
    htask_coordinator_mock.complete_task = AsyncMock(return_value={"completed": True})
    htask_coordinator_mock.verify_closure = AsyncMock(return_value={"can_close": True})
    htask_coordinator_mock.close_task = AsyncMock(return_value={"closed": True})
    htask_coordinator_mock.delete_htask = AsyncMock(return_value={"deleted": True})
    htask_coordinator_mock.recommend_batch = AsyncMock(return_value={"tasks": []})
    sys.modules["src.services.htask_coordinator"] = htask_coordinator_mock

    htask_events_mock = MagicMock()
    htask_events_mock.get_htask_metrics = AsyncMock(return_value={"metrics": {}})
    htask_events_mock.get_task_audit_trail = AsyncMock(return_value={"events": []})
    htask_events_mock.get_checkpoint_delta = AsyncMock(return_value={"changes": []})
    sys.modules["src.services.htask_events"] = htask_events_mock

    htask_policy_mock = MagicMock()
    htask_policy_mock.get_policy = AsyncMock(return_value={"policy": {}})
    htask_policy_mock.update_policy = AsyncMock(return_value={"updated": True})
    sys.modules["src.services.htask_policy"] = htask_policy_mock


# Run setup when this module is imported
setup_module_mocks()
