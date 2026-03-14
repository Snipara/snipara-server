"""Pytest configuration for handler tests.

This module sets up mocks for modules that require external dependencies
(database, redis, etc.) before the test modules are imported.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

# Set required environment variables before importing any modules
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["NEON_DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["NEXTAUTH_SECRET"] = "test-secret"


def setup_module_mocks():
    """Set up module mocks for testing handlers without external dependencies."""
    # Mock the config module
    mock_settings = MagicMock()
    mock_settings.database_url = os.environ["DATABASE_URL"]
    mock_settings.neon_database_url = os.environ["NEON_DATABASE_URL"]
    mock_settings.redis_url = os.environ["REDIS_URL"]
    mock_settings.env = "test"

    config_mock = MagicMock()
    config_mock.settings = mock_settings
    config_mock.get_settings = MagicMock(return_value=mock_settings)
    config_mock.Settings = MagicMock(return_value=mock_settings)

    # Pre-register mocked modules
    sys.modules["src.config"] = config_mock

    # Mock db module
    db_mock = MagicMock()
    db_mock.get_db = AsyncMock()
    sys.modules["src.db"] = db_mock

    # Mock services modules that require config/db
    services_mock = MagicMock()
    sys.modules["src.services"] = services_mock
    sys.modules["src.services.cache"] = MagicMock()

    # Create agent_memory service mock with async functions
    agent_memory_mock = MagicMock()
    agent_memory_mock.store_memory = AsyncMock(
        return_value={"memory_id": "test", "success": True}
    )
    agent_memory_mock.semantic_recall = AsyncMock(
        return_value={"memories": [], "total": 0}
    )
    agent_memory_mock.list_memories = AsyncMock(
        return_value={"memories": [], "total": 0}
    )
    agent_memory_mock.delete_memories = AsyncMock(return_value={"deleted": 0})
    sys.modules["src.services.agent_memory"] = agent_memory_mock

    # Create memory service mock with async functions
    memory_mock = MagicMock()
    memory_mock.check_memory_limits = AsyncMock(return_value=(True, None))
    memory_mock.store_memory = AsyncMock(return_value={"id": "test", "success": True})
    memory_mock.semantic_recall = AsyncMock(return_value={"memories": [], "total": 0})
    memory_mock.list_memories = AsyncMock(return_value={"memories": [], "total": 0})
    memory_mock.delete_memories = AsyncMock(return_value={"deleted": 0})
    sys.modules["src.services.memory"] = memory_mock

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
    sys.modules["src.services.swarm"] = swarm_mock


# Run setup when this module is imported
setup_module_mocks()
