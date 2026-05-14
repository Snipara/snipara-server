"""Targeted regression tests for agent memory limits."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(scope="module")
def agent_limits_module():
    """Import the service from the apps/mcp-server package context."""
    project_root = Path(__file__).resolve().parents[1]
    previous_cwd = Path.cwd()
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    os.chdir(project_root)
    try:
        sys.modules.pop("src.services.agent_limits", None)
        sys.modules.pop("src.services", None)
        module = importlib.import_module("src.services.agent_limits")
        yield importlib.reload(module)
    finally:
        os.chdir(previous_cwd)


@pytest.mark.asyncio
async def test_check_memory_limits_ignores_expired_memories(monkeypatch, agent_limits_module):
    """Expired rows should not continue counting against active memory quotas."""

    count_mock = AsyncMock(return_value=42)
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"count": count_mock})()},
    )()
    monkeypatch.setattr(agent_limits_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(
        agent_limits_module,
        "get_agents_subscription",
        AsyncMock(return_value={"memory_limit": 1000}),
    )

    allowed, error = await agent_limits_module.check_memory_limits("proj_test", "user_123")

    assert allowed is True
    assert error is None
    count_mock.assert_awaited_once()
    where = count_mock.await_args.kwargs["where"]
    assert where["projectId"] == "proj_test"
    assert where["OR"][0] == {"expiresAt": None}
    assert "gt" in where["OR"][1]["expiresAt"]
