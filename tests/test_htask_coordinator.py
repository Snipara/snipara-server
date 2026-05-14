"""Tests for hierarchical task coordinator contract compatibility."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest


class FakeHierarchicalTaskTable:
    def __init__(self, tasks):
        self.tasks = tasks
        self.calls = []

    async def find_many(self, **kwargs):
        self.calls.append(kwargs)
        return self.tasks


def make_task(task_id: str, parent_id: str | None = None, status: str = "PENDING"):
    return SimpleNamespace(
        id=task_id,
        level=1 if parent_id is None else 2,
        parentId=parent_id,
        sequenceNumber=1,
        workstreamType=None,
        customWorkstreamType=None,
        title=f"Task {task_id}",
        description="",
        owner="agent",
        executionTarget=None,
        priority="P1",
        etaTarget=None,
        acceptanceCriteria=[],
        contextRefs=[],
        evidenceRequired=[],
        evidenceProvided=[],
        status=status,
        isBlocking=False,
        blockerType=None,
        blockerReason=None,
        blockedByTaskId=None,
        requiredInput=None,
        etaRecovery=None,
        escalationTo=None,
        blockedAt=None,
        waiverReason=None,
        waiverApprovedBy=None,
        waiverApprovedAt=None,
        result=None,
        error=None,
        createdAt=None,
        updatedAt=None,
        startedAt=None,
        completedAt=None,
        archivedAt=None,
    )


@pytest.fixture
def htask_coordinator_module():
    """Load the real service module even if handler tests installed service mocks."""
    sys.modules.pop("src.services.htask_coordinator", None)
    return importlib.import_module("src.services.htask_coordinator")


@pytest.mark.asyncio
async def test_get_htask_tree_accepts_public_task_id_alias(monkeypatch, htask_coordinator_module):
    """The service should accept the task_id keyword exposed by tools/list."""
    table = FakeHierarchicalTaskTable([make_task("root-1"), make_task("child-1", "root-1")])
    db = SimpleNamespace(hierarchicaltask=table)

    async def fake_get_db():
        return db

    monkeypatch.setattr(htask_coordinator_module, "get_db", fake_get_db)

    result = await htask_coordinator_module.get_htask_tree(
        swarm_id="swarm-1",
        task_id="root-1",
        include_archived=True,
        max_depth=2,
    )

    assert result["success"] is True
    assert result["tree"]["id"] == "root-1"
    assert result["tree"]["children"][0]["id"] == "child-1"
    assert table.calls[0]["where"] == {"swarmId": "swarm-1", "status": {"not_in": ["COMPLETED", "CANCELLED"]}}


@pytest.mark.asyncio
async def test_get_htask_tree_without_root_returns_all_roots(monkeypatch, htask_coordinator_module):
    """Omitting task_id/root_id should still return all unarchived root tasks."""
    table = FakeHierarchicalTaskTable([make_task("root-1"), make_task("root-2")])
    db = SimpleNamespace(hierarchicaltask=table)

    async def fake_get_db():
        return db

    monkeypatch.setattr(htask_coordinator_module, "get_db", fake_get_db)

    result = await htask_coordinator_module.get_htask_tree(swarm_id="swarm-1")

    assert result["success"] is True
    assert result["total_roots"] == 2
    assert table.calls[0]["where"]["archivedAt"] is None
