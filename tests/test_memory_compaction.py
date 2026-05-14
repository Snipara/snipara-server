"""Regression tests for memory compaction hygiene rules."""

from __future__ import annotations

import importlib
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(scope="module")
def agent_memory_module():
    """Import the service from the apps/mcp-server package context."""
    project_root = Path(__file__).resolve().parents[1]
    previous_cwd = Path.cwd()
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    os.chdir(project_root)
    try:
        sys.modules.pop("src.services.agent_memory", None)
        sys.modules.pop("src.services", None)
        module = importlib.import_module("src.services.agent_memory")
        yield importlib.reload(module)
    finally:
        os.chdir(previous_cwd)


def _memory(**overrides):
    now = datetime.now(UTC)
    payload = {
        "id": "mem_default",
        "content": "durable memory",
        "type": "FACT",
        "scope": "PROJECT",
        "category": "general",
        "confidence": 1.0,
        "accessCount": 0,
        "documentRefs": [],
        "createdAt": now,
        "lastAccessedAt": None,
        "reviewStatus": "APPROVED",
        "tier": "DAILY",
    }
    payload.update(overrides)
    return type("MemoryRow", (), payload)()


def test_classify_low_signal_memory_targets_safe_noise_patterns(agent_memory_module):
    """Compaction should only prune patterns we have explicitly classified as noise."""
    assert (
        agent_memory_module._classify_low_signal_memory(
            _memory(
                id="superseded",
                type="LEARNING",
                category="workspace-learning-0000:superseded:superseded",
                content="Old operational learning",
            )
        )
        == agent_memory_module.LOW_SIGNAL_REASON_SUPERSEDED_WORKSPACE_LEARNING
    )
    assert (
        agent_memory_module._classify_low_signal_memory(
            _memory(
                id="tombstone",
                type="FACT",
                scope="AGENT",
                category="agent-jarvis",
                content="[DELETED memory mem_123]",
            )
        )
        == agent_memory_module.LOW_SIGNAL_REASON_DELETED_TOMBSTONE
    )
    assert (
        agent_memory_module._classify_low_signal_memory(
            _memory(
                id="sync",
                type="LEARNING",
                category="workspace-learning-0000",
                content="SYNCTEST-prod-103420 simple task: Created by backend-only sync test.",
            )
        )
        == agent_memory_module.LOW_SIGNAL_REASON_SYNC_TEST
    )
    assert (
        agent_memory_module._classify_low_signal_memory(
            _memory(
                id="task",
                type="LEARNING",
                category="task-learning",
                content='Task "Publish next social post" completed by Max: Liens utiles: - [Open file in Drive](...)',
            )
        )
        == agent_memory_module.LOW_SIGNAL_REASON_TASK_JOURNAL
    )
    assert (
        agent_memory_module._classify_low_signal_memory(
            _memory(
                id="upload",
                type="DECISION",
                category="auto-remember",
                source="auto",
                content="Uploaded document: CLAUDE.md",
            )
        )
        == agent_memory_module.LOW_SIGNAL_REASON_AUTO_DOCUMENT_UPLOAD
    )
    assert (
        agent_memory_module._classify_low_signal_memory(
            _memory(
                id="decompose",
                type="DECISION",
                category="auto-remember",
                content="Decomposed 'Compare memory tools' into 1 sub-queries",
            )
        )
        == agent_memory_module.LOW_SIGNAL_REASON_TRIVIAL_DECOMPOSITION
    )
    assert (
        agent_memory_module._classify_low_signal_memory(
            _memory(
                id="plan",
                type="DECISION",
                category="auto-remember",
                source="auto",
                content="Created execution plan for 'Ship memory hygiene' with 3 steps",
            )
        )
        == agent_memory_module.LOW_SIGNAL_REASON_EXECUTION_PLAN_RECEIPT
    )
    assert (
        agent_memory_module._classify_low_signal_memory(
            _memory(
                id="keep",
                type="LEARNING",
                category="workspace-learning-0000",
                content="Use Bun because startup time and install surface are lower than Node.",
            )
        )
        is None
    )


@pytest.mark.asyncio
async def test_compact_memories_prunes_low_signal_noise_and_cleans_embeddings(
    monkeypatch,
    agent_memory_module,
):
    """Compaction should drop known-noise memories before the generic phases run."""

    memories = [
        _memory(
            id="superseded",
            type="LEARNING",
            category="workspace-learning-0000:superseded:superseded",
            content="Old operational learning",
        ),
        _memory(
            id="tombstone",
            type="FACT",
            scope="AGENT",
            category="agent-jarvis",
            content="[DELETED memory mem_123]",
        ),
        _memory(
            id="sync",
            type="LEARNING",
            category="workspace-learning-0000",
            content="SYNCTEST-prod-103420 simple task: Created by backend-only sync test.",
        ),
        _memory(
            id="task",
            type="LEARNING",
            category="task-learning",
            content='Task "Publish next social post" completed by Max: Liens utiles: - [Open file in Drive](...)',
        ),
        _memory(
            id="upload",
            type="DECISION",
            category="auto-remember",
            source="auto",
            content="Uploaded document: AGENTS.md",
        ),
        _memory(
            id="decompose",
            type="DECISION",
            category="auto-remember",
            content="Decomposed 'Compare memory tools' into 1 sub-queries",
        ),
        _memory(
            id="plan",
            type="DECISION",
            category="auto-remember",
            source="auto",
            content="Created execution plan for 'Ship memory hygiene' with 3 steps",
        ),
        _memory(
            id="keep",
            type="FACT",
            category="models",
            content="Use Haiku for lightweight sub-agents.",
        ),
    ]

    find_many = AsyncMock(side_effect=[memories, [], []])
    delete_many = AsyncMock(return_value=6)
    update = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {
            "agentmemory": type(
                "AgentMemoryRepo",
                (),
                {
                    "find_many": find_many,
                    "delete_many": delete_many,
                    "update": update,
                },
            )()
        },
    )()

    delete_embedding = AsyncMock()

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "_delete_memory_embedding", delete_embedding)

    result = await agent_memory_module.compact_memories(
        project_id="proj_test",
        deduplicate=False,
        promote_threshold=99,
        archive_older_than_days=3650,
        dry_run=False,
        normalize_dates=False,
        validate_refs=False,
        conflict_strategy="",
    )

    delete_many.assert_awaited_once_with(
        where={
            "id": {
                "in": [
                    "superseded",
                    "tombstone",
                    "sync",
                    "task",
                    "upload",
                    "decompose",
                    "plan",
                ]
            }
        }
    )
    assert delete_embedding.await_count == 7
    assert result["noise_pruned"] == 7
    assert result["superseded_workspace_learning_removed"] == 1
    assert result["deleted_tombstones_removed"] == 1
    assert result["sync_test_noise_removed"] == 1
    assert result["task_journals_removed"] == 1
    assert result["auto_document_uploads_removed"] == 1
    assert result["trivial_decompositions_removed"] == 1
    assert result["execution_plan_receipts_removed"] == 1
    assert result["message"].startswith("Successfully: pruned 7 low-signal memories")


@pytest.mark.asyncio
async def test_compact_memories_dry_run_reports_noise_without_deleting(
    monkeypatch,
    agent_memory_module,
):
    """Dry runs should surface the same hygiene counts without mutating storage."""

    memories = [
        _memory(
            id="tombstone",
            type="FACT",
            scope="AGENT",
            category="agent-jarvis",
            content="[DELETED memory mem_123]",
        ),
        _memory(
            id="keep",
            type="FACT",
            category="models",
            content="Use Haiku for lightweight sub-agents.",
        ),
    ]

    find_many = AsyncMock(side_effect=[memories, [], []])
    delete_many = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {
            "agentmemory": type(
                "AgentMemoryRepo",
                (),
                {
                    "find_many": find_many,
                    "delete_many": delete_many,
                    "update": AsyncMock(),
                },
            )()
        },
    )()

    delete_embedding = AsyncMock()

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "_delete_memory_embedding", delete_embedding)

    result = await agent_memory_module.compact_memories(
        project_id="proj_test",
        deduplicate=False,
        promote_threshold=99,
        archive_older_than_days=3650,
        dry_run=True,
        normalize_dates=False,
        validate_refs=False,
        conflict_strategy="",
    )

    delete_many.assert_not_awaited()
    delete_embedding.assert_not_awaited()
    assert result["noise_pruned"] == 1
    assert result["deleted_tombstones_removed"] == 1
    assert result["message"].startswith("Would have: pruned 1 low-signal memories")


@pytest.mark.asyncio
async def test_memory_health_reports_counts_and_hygiene_samples(monkeypatch, agent_memory_module):
    """Memory health should surface active counts and known anomaly samples without mutation."""

    memories = [
        _memory(
            id="plan",
            type="DECISION",
            scope="PROJECT",
            category="auto-remember",
            source="auto",
            status="ACTIVE",
            tier="DAILY",
            content="Created execution plan for 'Ship memory hygiene' with 3 steps",
        ),
        _memory(
            id="category",
            type="LEARNING",
            scope="PROJECT",
            category="debugging:superseded",
            status="ACTIVE",
            tier="ARCHIVE",
            content="Useful but category was corrupted by old compaction.",
        ),
        _memory(
            id="user",
            type="PREFERENCE",
            scope="USER",
            category="workflow",
            status="ACTIVE",
            tier="CRITICAL",
            content="User prefers testing before docs.",
        ),
    ]

    find_many = AsyncMock(return_value=memories)
    mock_db = type(
        "MockDb",
        (),
        {
            "agentmemory": type(
                "AgentMemoryRepo",
                (),
                {"find_many": find_many},
            )()
        },
    )()

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))

    result = await agent_memory_module.get_memory_health(
        project_id="proj_test",
        sample_limit=2,
    )

    assert result["total_scanned"] == 3
    assert result["counts"]["by_scope"] == {"project": 2, "user": 1}
    assert result["counts"]["by_type"]["decision"] == 1
    assert result["counts"]["by_tier"]["archive"] == 1
    assert result["hygiene"]["anomaly_count"] == 2
    assert result["hygiene"]["by_reason"]["execution_plan_receipt"] == 1
    assert result["hygiene"]["by_reason"]["active_superseded_category"] == 1
    assert len(result["hygiene"]["samples"]) == 2
    assert "active_hygiene_anomalies_detected" in result["warnings"]


@pytest.mark.asyncio
async def test_memory_duplicate_candidates_are_read_only(monkeypatch, agent_memory_module):
    """Duplicate review should group candidates without mutating memory rows."""

    now = datetime.now(UTC)
    memories = [
        _memory(id="old", content="Prefer remote MCP for Codex memory workflow.", createdAt=now - timedelta(days=1)),
        _memory(id="new", content="Prefer remote MCP for Codex memory workflow.", createdAt=now),
    ]
    find_many = AsyncMock(return_value=memories)
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"find_many": find_many})()},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))

    result = await agent_memory_module.get_memory_duplicate_candidates("proj_test")

    assert result["mutated"] is False
    assert result["group_count"] == 1
    assert result["groups"][0]["suggested_keep_memory_id"] == "new"
    assert result["groups"][0]["suggested_supersede_memory_ids"] == ["old"]


@pytest.mark.asyncio
async def test_memory_clean_candidates_groups_hygiene_buckets(monkeypatch, agent_memory_module):
    """Clean candidates should expose all buckets required for manual review automation."""

    now = datetime.now(UTC)
    memories = [
        _memory(
            id="noise",
            category="auto-remember",
            source="auto",
            content="Created execution plan for 'Ship memory hygiene' with 3 steps",
        ),
        _memory(
            id="dup1",
            content="Use remote MCP for project memory workflow.",
            createdAt=now - timedelta(days=1),
        ),
        _memory(id="dup2", content="Use remote MCP for project memory workflow.", createdAt=now),
        _memory(id="stale", type="TODO", content="Old follow-up", createdAt=now - timedelta(days=45)),
        _memory(id="category", category="debugging:superseded", status="ACTIVE"),
        _memory(id="pending", reviewStatus="PENDING", content="Needs review"),
    ]
    find_many = AsyncMock(return_value=memories)
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"find_many": find_many})()},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))

    result = await agent_memory_module.get_memory_clean_candidates("proj_test", limit_per_bucket=5)

    assert result["mutated"] is False
    assert set(result["candidates"]) == {
        "noise",
        "possibly_stale",
        "category_anomalies",
        "needs_human_review",
        "duplicates",
    }
    assert result["counts"]["noise"] == 1
    assert result["counts"]["duplicates"] == 1
    assert result["counts"]["possibly_stale"] == 1
    assert result["counts"]["category_anomalies"] == 1
    assert result["counts"]["needs_human_review"] == 1


@pytest.mark.asyncio
async def test_auto_compact_uses_safe_non_semantic_strategy(monkeypatch, agent_memory_module):
    """Automatic compaction should not run broad semantic conflict resolution."""

    count = AsyncMock(return_value=251)
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"count": count})()},
    )()
    compact = AsyncMock(return_value={"duplicates_merged": 1, "archived": 0})

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "get_redis", AsyncMock(return_value=None))
    monkeypatch.setattr(agent_memory_module, "compact_memories", compact)

    result = await agent_memory_module.maybe_auto_compact("proj_test")

    assert result["auto_triggered"] is True
    assert compact.await_args.kwargs["conflict_strategy"] == ""
    assert compact.await_args.kwargs["deduplicate"] is True


@pytest.mark.asyncio
async def test_resolve_conflict_marks_archived_memory_inactive(monkeypatch, agent_memory_module):
    """Archived conflict losers should not continue to appear as active memories."""

    update = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"update": update})()},
    )()
    older = _memory(id="old", content="Old memory", category="debugging")
    newer = _memory(id="new", content="New memory", category="debugging")

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))

    result = await agent_memory_module.resolve_conflict(
        older=older,
        newer=newer,
        similarity=0.91,
        strategy=agent_memory_module.CONFLICT_STRATEGY_NEWER,
        dry_run=False,
    )

    assert result["action"] == "archived_older"
    update_payload = update.await_args.kwargs
    assert update_payload["where"] == {"id": "old"}
    assert update_payload["data"]["status"] == "SUPERSEDED"
    assert update_payload["data"]["tier"] == "ARCHIVE"
    assert update_payload["data"]["supersededByMemoryId"] == "new"
