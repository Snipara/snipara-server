"""Tests for legacy rlm_task_* compatibility over htasks."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def adapter_module():
    """Load the adapter fresh so tests can patch module globals directly."""
    sys.modules.pop("src.services.htask_task_adapter", None)
    return importlib.import_module("src.services.htask_task_adapter")


def make_task(
    *,
    task_id: str = "task-1",
    owner: str = "unassigned",
    status: str = "PENDING",
):
    return SimpleNamespace(
        id=task_id,
        level="N3_TASK",
        title="Review deploy",
        description="Check deployment plan",
        owner=owner,
        priority="P1",
        status=status,
        etaTarget=None,
        createdAt=None,
        updatedAt=None,
        startedAt=None,
        completedAt=None,
    )


class FakeHierarchicalTaskTable:
    def __init__(self, task=None):
        self.task = task
        self.updates: list[dict] = []

    async def find_first(self, **kwargs):
        return self.task

    async def update(self, **kwargs):
        self.updates.append(kwargs)
        if self.task:
            for key, value in kwargs.get("data", {}).items():
                setattr(self.task, key, value)
        return self.task


@pytest.mark.asyncio
async def test_create_task_as_htask_uses_unassigned_owner_by_default(monkeypatch, adapter_module):
    calls: list[dict] = []

    async def fake_create_htask(**kwargs):
        calls.append(kwargs)
        return {"success": True, "task_id": "htask-1", "priority": kwargs["priority"]}

    monkeypatch.setattr(adapter_module, "create_htask", fake_create_htask)
    monkeypatch.setattr(adapter_module, "get_task_compat_mode", AsyncMock(return_value="HTASK"))

    result = await adapter_module.create_task_as_htask(
        swarm_id="swarm-1",
        agent_id="coordinator",
        title="Review deploy",
        priority=2,
        depends_on=["dep-1"],
    )

    assert result["success"] is True
    assert result["canonical_surface"] == "htask"
    assert result["task_id"] == "htask-1"
    assert result["assigned"] is False
    assert result["created_by"] == "coordinator"
    assert calls[0]["level"] == "N3_TASK"
    assert calls[0]["owner"] == "unassigned"
    assert calls[0]["priority"] == "P0"
    assert calls[0]["context_refs"] == [
        "legacy-task-created-by:coordinator",
        "legacy-task-depends:dep-1",
    ]


@pytest.mark.asyncio
async def test_claim_task_as_htask_rejects_wrong_affinity(monkeypatch, adapter_module):
    table = FakeHierarchicalTaskTable(make_task(owner="agent-b"))
    db = SimpleNamespace(hierarchicaltask=table)

    async def fake_get_db():
        return db

    monkeypatch.setattr(adapter_module, "get_db", fake_get_db)

    result = await adapter_module.claim_task_as_htask(
        swarm_id="swarm-1",
        agent_id="agent-a",
        task_id="task-1",
    )

    assert result["success"] is False
    assert result["error"] == "Task is assigned to another agent"
    assert result["assigned_to"] == "agent-b"
    assert table.updates == []


@pytest.mark.asyncio
async def test_claim_task_as_htask_claims_unassigned_task(monkeypatch, adapter_module):
    table = FakeHierarchicalTaskTable(make_task(owner="unassigned"))
    db = SimpleNamespace(hierarchicaltask=table)

    async def fake_get_db():
        return db

    monkeypatch.setattr(adapter_module, "get_db", fake_get_db)
    monkeypatch.setattr(adapter_module, "log_htask_event", AsyncMock())
    monkeypatch.setattr(adapter_module, "get_task_compat_mode", AsyncMock(return_value="HTASK"))

    result = await adapter_module.claim_task_as_htask(
        swarm_id="swarm-1",
        agent_id="agent-a",
        task_id="task-1",
    )

    assert result["success"] is True
    assert result["status"] == "claimed"
    assert result["was_preassigned"] is False
    assert result["canonical_surface"] == "htask"
    assert table.updates[0]["data"]["owner"] == "agent-a"
    assert table.updates[0]["data"]["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_complete_task_as_htask_adds_compatibility_evidence(monkeypatch, adapter_module):
    table = FakeHierarchicalTaskTable(make_task(owner="agent-a", status="IN_PROGRESS"))
    db = SimpleNamespace(hierarchicaltask=table)
    completions: list[dict] = []

    async def fake_get_db():
        return db

    async def fake_complete_htask(**kwargs):
        completions.append(kwargs)
        return {"success": True, "task_id": kwargs["task_id"], "status": "COMPLETED"}

    monkeypatch.setattr(adapter_module, "get_db", fake_get_db)
    monkeypatch.setattr(adapter_module, "complete_htask", fake_complete_htask)
    monkeypatch.setattr(adapter_module, "get_task_compat_mode", AsyncMock(return_value="HTASK"))

    result = await adapter_module.complete_task_as_htask(
        swarm_id="swarm-1",
        agent_id="agent-a",
        task_id="task-1",
        result={"files": ["deploy.md"]},
    )

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["completed"] is True
    assert result["canonical_surface"] == "htask"
    assert result["htask_id"] == "task-1"
    assert completions[0]["evidence"][0]["type"] == "legacy_task_result"
    assert completions[0]["result"] == {"files": ["deploy.md"]}
