"""Regression tests for public agent memory parameter validation."""

from __future__ import annotations

import importlib
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import ANY, AsyncMock

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


def test_normalize_memory_type_accepts_case_insensitive_values(agent_memory_module):
    """Public memory APIs should accept canonical values regardless of case."""
    assert (
        agent_memory_module._normalize_memory_type("DECISION")
        == agent_memory_module.AgentMemoryType.DECISION
    )
    assert (
        agent_memory_module._normalize_memory_scope("PROJECT")
        == agent_memory_module.AgentMemoryScope.PROJECT
    )
    assert agent_memory_module._normalize_review_status("pending") == "PENDING"


def test_extract_task_commit_candidates_filters_receipts(agent_memory_module):
    """Task commits should keep durable statements and explain receipt skips."""
    result = agent_memory_module._extract_task_commit_candidates(
        summary=(
            "- Files modified: apps/mcp-server/src/services/agent_memory.py\n"
            "- Decided to expose bootstrap status as a read-only session lifecycle surface.\n"
            "- Learned that operational receipts were polluting durable memory.\n"
            "- TODO: add integration coverage for remote client bootstrap status."
        ),
        outcome="completed",
        persist_types=["decision", "learning", "todo"],
    )

    assert [candidate["candidate_type"] for candidate in result["candidates"]] == [
        "decision",
        "learning",
        "todo",
    ]
    assert any(skip["reason"] == "operational_receipt" for skip in result["skipped"])


def test_memory_durability_classifier_routes_operational_auto_writes(agent_memory_module):
    """Automated operational receipts should go to review; explicit preferences should not."""
    auto = agent_memory_module.classify_memory_durability(
        "Created execution plan for 'Ship memory hygiene' with 3 steps",
        "context",
        category="auto-remember",
        source="auto",
    )
    manual = agent_memory_module.classify_memory_durability(
        "User prefers project-scoped memory writes for Snipara workflow rules.",
        "preference",
        category="workflow",
        source="mcp",
    )

    assert auto["durability"] == "transient"
    assert auto["recommended_review_status"] == "PENDING"
    assert "execution_plan_receipt" in auto["reasons"]
    assert manual["durability"] == "durable"
    assert manual["recommended_review_status"] == "APPROVED"


def test_sensitive_memory_detector_flags_secret_patterns(agent_memory_module):
    """Credential-like memory content should be treated as unsafe durable memory."""
    reasons = agent_memory_module.detect_sensitive_memory_reasons(
        "Use password=example-secret-value for local-only smoke testing."
    )

    assert "credential_assignment" in reasons
    assert agent_memory_module.memory_content_has_sensitive_material(
        "Authorization: Bearer exampleBearerToken12345"
    )
    assert not agent_memory_module.memory_content_has_sensitive_material(
        "Use a token budget of 2500 for runtime validation."
    )


def test_extract_task_commit_candidates_filters_sensitive_material(agent_memory_module):
    """Task commit extraction must never turn credentials into durable candidates."""
    result = agent_memory_module._extract_task_commit_candidates(
        summary=(
            "Decided to keep database credentials in a secret manager.\n"
            "Learned password=example-secret-value should not enter memory."
        ),
        outcome="completed",
        persist_types=["decision", "learning"],
    )

    assert [candidate["candidate_type"] for candidate in result["candidates"]] == ["decision"]
    assert any(
        skip["reason"] == agent_memory_module.LOW_SIGNAL_REASON_SENSITIVE_MATERIAL
        for skip in result["skipped"]
    )
    assert all("example-secret-value" not in skip["text"] for skip in result["skipped"])


def test_resolve_review_status_uses_classifier_before_auto_approval(agent_memory_module):
    """High-risk automated writes should be queued even when memory review mode is AUTO."""
    settings_obj = type("Settings", (), {"memory_review_mode": "AUTO"})()

    assert (
        agent_memory_module.resolve_review_status_for_source(
            settings_obj,
            source="auto",
            content="Uploaded document: docs/reference/API_REFERENCE.md",
            memory_type="context",
            category="auto-remember",
        )
        == "PENDING"
    )
    assert (
        agent_memory_module.resolve_review_status_for_source(
            settings_obj,
            source="mcp",
            content="Decided to keep remote MCP as the default Codex memory workflow.",
            memory_type="decision",
            category="workflow",
        )
        == "APPROVED"
    )


@pytest.mark.asyncio
async def test_store_memory_rejects_sensitive_content_before_db(monkeypatch, agent_memory_module):
    """Direct memory writes should fail before any DB write when content looks secret-bearing."""
    get_db = AsyncMock()
    monkeypatch.setattr(agent_memory_module, "get_db", get_db)

    with pytest.raises(ValueError, match="sensitive material"):
        await agent_memory_module.store_memory(
            project_id="proj_test",
            content="Runbook says password=example-secret-value.",
            memory_type="learning",
        )

    get_db.assert_not_called()


@pytest.mark.asyncio
async def test_remember_if_novel_rejects_sensitive_content_before_recall(
    monkeypatch,
    agent_memory_module,
):
    """Novelty checks should not query embeddings with secret-bearing content."""
    semantic_recall = AsyncMock()
    monkeypatch.setattr(agent_memory_module, "semantic_recall", semantic_recall)

    with pytest.raises(ValueError, match="sensitive material"):
        await agent_memory_module.remember_if_novel(
            project_id="proj_test",
            content="Use api_key=example-secret-value for smoke tests.",
            memory_type="learning",
        )

    semantic_recall.assert_not_called()


@pytest.mark.asyncio
async def test_end_of_task_commit_structures_results_without_auto_supersede(
    monkeypatch,
    agent_memory_module,
):
    """Commit writes should report stored/skipped candidates and avoid dangerous supersession."""
    remember_mock = AsyncMock(
        side_effect=[
            {"stored": True, "memory_id": "mem_decision", "reason": "stored"},
            {"stored": False, "reason": "duplicate", "memory_id": None},
        ]
    )
    monkeypatch.setattr(agent_memory_module, "remember_if_novel", remember_mock)

    result = await agent_memory_module.end_of_task_commit(
        project_id="proj_test",
        summary=(
            "Tests run: targeted memory unit tests passed.\n"
            "Decided to expose bootstrap status through a read-only MCP tool.\n"
            "Learned that receipts should be skipped before novelty checks."
        ),
    )

    assert result["stored_count"] == 1
    assert result["skipped_count"] == 2
    assert result["stored_candidates"][0]["memory_id"] == "mem_decision"
    assert any(skip["reason"] == "operational_receipt" for skip in result["skipped_candidates"])
    assert remember_mock.await_count == 2
    assert all(call.kwargs["allow_supersede"] is False for call in remember_mock.await_args_list)


@pytest.mark.asyncio
async def test_semantic_recall_excludes_pending_review_rows_by_default(
    monkeypatch,
    agent_memory_module,
):
    """Recall queries should only target approved memories unless widened explicitly."""

    find_many = AsyncMock(return_value=[])
    mock_db = type(
        "MockDb",
        (),
        {
            "memory": type("MemoryRepo", (), {"find_many": find_many})(),
            "project": None,
        },
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))

    result = await agent_memory_module.semantic_recall(
        project_id="proj_test",
        query="memory review queue",
    )

    assert result["memories"] == []
    assert find_many.await_count == 1
    assert {"status": "ACTIVE"} in find_many.await_args.kwargs["where"]["AND"]


@pytest.mark.asyncio
async def test_validate_document_refs_does_not_use_unsupported_select(
    monkeypatch,
    agent_memory_module,
):
    """Document ref validation should stay compatible with the deployed Prisma Python client."""

    docs = [type("Doc", (), {"path": "docs/a.md"})(), type("Doc", (), {"path": "docs/b.md"})()]
    find_many = AsyncMock(return_value=docs)
    mock_db = type(
        "MockDb",
        (),
        {"document": type("DocumentRepo", (), {"find_many": find_many})()},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))

    valid_refs, removed_count = await agent_memory_module.validate_document_refs(
        ["docs/a.md", "docs/missing.md"],
        "proj_test",
    )

    assert valid_refs == ["docs/a.md"]
    assert removed_count == 1
    assert find_many.await_args.kwargs == {"where": {"projectId": "proj_test"}}


@pytest.mark.asyncio
async def test_semantic_recall_falls_back_when_legacy_query_embedding_times_out(
    monkeypatch,
    agent_memory_module,
):
    """Legacy recall should degrade to text search instead of hanging on embeddings."""

    now = datetime.now(UTC)
    matching_memory = type(
        "Memory",
        (),
        {
            "id": "mem_timeout_fallback",
            "content": "Memory hygiene smoke uses strict active superseded category checks.",
            "category": "operations",
            "type": "LEARNING",
            "scope": "PROJECT",
            "tier": "CRITICAL",
            "confidence": 1.0,
            "createdAt": now,
            "lastAccessedAt": None,
            "accessCount": 0,
            "reviewStatus": "APPROVED",
            "status": "ACTIVE",
        },
    )()
    find_many = AsyncMock(side_effect=[[matching_memory], []])
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"find_many": find_many})()},
    )()
    embed_text_async = AsyncMock(side_effect=TimeoutError)
    embeddings = type(
        "EmbeddingsService",
        (),
        {"embed_text_async": embed_text_async},
    )()

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "get_embeddings_service", lambda: embeddings)
    monkeypatch.setattr(agent_memory_module.settings, "memory_v2_primary_read", False)
    monkeypatch.setattr(agent_memory_module.settings, "memory_v2_dual_read", False)

    result = await agent_memory_module.semantic_recall(
        project_id="proj_test",
        query="memory hygiene",
        limit=5,
        min_relevance=0.0,
    )

    assert result["memories"][0]["memory_id"] == "mem_timeout_fallback"
    assert result["total_searched"] == 1
    assert "timing_ms" in result
    assert embed_text_async.await_count == 1


@pytest.mark.asyncio
async def test_semantic_recall_falls_back_when_legacy_memory_embeddings_time_out(
    monkeypatch,
    agent_memory_module,
):
    """Legacy recall should degrade if cache misses cannot be embedded fast enough."""

    now = datetime.now(UTC)
    matching_memory = type(
        "Memory",
        (),
        {
            "id": "mem_memory_embedding_timeout",
            "content": "Live embedding timeout should not make recall empty.",
            "category": "operations",
            "type": "LEARNING",
            "scope": "PROJECT",
            "tier": "CRITICAL",
            "confidence": 1.0,
            "createdAt": now,
            "lastAccessedAt": None,
            "accessCount": 0,
            "reviewStatus": "APPROVED",
            "status": "ACTIVE",
        },
    )()
    find_many = AsyncMock(side_effect=[[matching_memory], []])
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"find_many": find_many})()},
    )()
    embed_text_async = AsyncMock(side_effect=[[0.1, 0.2], TimeoutError])
    embeddings = type(
        "EmbeddingsService",
        (),
        {"embed_text_async": embed_text_async},
    )()

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "get_embeddings_service", lambda: embeddings)
    monkeypatch.setattr(agent_memory_module.settings, "memory_v2_primary_read", False)
    monkeypatch.setattr(agent_memory_module.settings, "memory_v2_dual_read", False)
    monkeypatch.setattr(
        agent_memory_module,
        "_get_memory_embeddings_batch",
        AsyncMock(return_value={}),
    )

    result = await agent_memory_module.semantic_recall(
        project_id="proj_test",
        query="live embedding timeout recall empty",
        limit=5,
        min_relevance=0.0,
    )

    assert result["memories"][0]["memory_id"] == "mem_memory_embedding_timeout"
    assert result["total_searched"] == 1
    assert embed_text_async.await_count == 2


@pytest.mark.asyncio
async def test_get_session_memories_reports_bootstrap_status(
    monkeypatch,
    agent_memory_module,
):
    """Session memory bootstrap should report lifecycle timestamp and injected counts."""
    now = datetime.now(UTC)
    tenant_profile = type(
        "Memory",
        (),
        {
            "id": "mem_profile",
            "content": "Tenant profile content",
            "category": agent_memory_module.TENANT_PROFILE_CATEGORY,
            "type": "FACT",
            "scope": "PROJECT",
            "confidence": 0.95,
            "createdAt": now,
            "lastAccessedAt": None,
            "reviewStatus": "APPROVED",
        },
    )()
    decision = type(
        "Memory",
        (),
        {
            "id": "mem_decision",
            "content": "Use read-only status for bootstrap lifecycle.",
            "category": "architecture",
            "type": "DECISION",
            "scope": "PROJECT",
            "confidence": 0.9,
            "createdAt": now,
            "lastAccessedAt": None,
            "reviewStatus": "APPROVED",
        },
    )()
    find_many = AsyncMock(side_effect=[[tenant_profile, decision], []])
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"find_many": find_many})()},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module.settings, "memory_v2_primary_read", False)
    monkeypatch.setattr(agent_memory_module.settings, "memory_v2_dual_read", False)

    result = await agent_memory_module.get_session_memories(project_id="proj_test")

    assert result["bootstrap"]["ran"] is True
    assert result["bootstrap"]["timestamp"]
    assert result["bootstrap"]["injected_memory_count"] == 2
    assert result["bootstrap"]["injected_profile_count"] == 1
    assert result["bootstrap"]["scope_counts"] == {"project": 2}
    assert result["bootstrap"]["type_counts"] == {"decision": 1, "fact": 1}
    assert result["bootstrap"]["freshness"]["newest_age_days"] == 0
    assert result["bootstrap"]["injected"][0]["memory_id"] == "mem_profile"


@pytest.mark.asyncio
async def test_get_session_memories_filters_sensitive_rows(
    monkeypatch,
    agent_memory_module,
):
    """Session bootstrap must not inject active memories that look secret-bearing."""
    now = datetime.now(UTC)
    safe = type(
        "Memory",
        (),
        {
            "id": "mem_safe",
            "content": "Use secret managers for operational credentials.",
            "category": "security",
            "type": "DECISION",
            "scope": "PROJECT",
            "confidence": 0.9,
            "createdAt": now,
            "lastAccessedAt": None,
            "reviewStatus": "APPROVED",
        },
    )()
    sensitive = type(
        "Memory",
        (),
        {
            "id": "mem_sensitive",
            "content": "Legacy note password=example-secret-value.",
            "category": "database",
            "type": "FACT",
            "scope": "PROJECT",
            "confidence": 0.95,
            "createdAt": now,
            "lastAccessedAt": None,
            "reviewStatus": "APPROVED",
        },
    )()
    find_many = AsyncMock(side_effect=[[sensitive, safe], []])
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"find_many": find_many})()},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module.settings, "memory_v2_primary_read", False)
    monkeypatch.setattr(agent_memory_module.settings, "memory_v2_dual_read", False)

    result = await agent_memory_module.get_session_memories(project_id="proj_test")

    assert result["critical"]["count"] == 1
    assert result["critical"]["memories"][0]["id"] == "mem_safe"
    assert result["filtered_sensitive_count"] == 1
    assert result["warnings"] == ["sensitive_memory_filtered"]
    assert "example-secret-value" not in str(result)


@pytest.mark.asyncio
async def test_memory_health_flags_and_redacts_sensitive_samples(
    monkeypatch,
    agent_memory_module,
):
    """Memory health should reveal the anomaly without echoing the sensitive value."""
    now = datetime.now(UTC)
    sensitive = type(
        "Memory",
        (),
        {
            "id": "mem_sensitive",
            "content": "Legacy note password=example-secret-value.",
            "category": "database",
            "type": "FACT",
            "scope": "PROJECT",
            "status": "ACTIVE",
            "tier": "CRITICAL",
            "createdAt": now,
            "expiresAt": None,
        },
    )()
    find_many = AsyncMock(return_value=[sensitive])
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"find_many": find_many})()},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))

    result = await agent_memory_module.get_memory_health(project_id="proj_test", sample_limit=1)

    assert result["hygiene"]["anomaly_count"] == 1
    assert result["hygiene"]["by_reason"] == {
        agent_memory_module.LOW_SIGNAL_REASON_SENSITIVE_MATERIAL: 1
    }
    preview = result["hygiene"]["samples"][0]["preview"]
    assert agent_memory_module.SENSITIVE_MEMORY_REDACTION in preview
    assert "example-secret-value" not in preview


@pytest.mark.asyncio
async def test_remember_if_novel_dedupes_against_pending_review_rows(
    monkeypatch,
    agent_memory_module,
):
    """Novelty checks should look at inbox items too, to avoid duplicate pending candidates."""

    recall_mock = AsyncMock(return_value={"memories": []})
    store_mock = AsyncMock(return_value={"memory_id": "mem_123"})
    monkeypatch.setattr(agent_memory_module, "semantic_recall", recall_mock)
    monkeypatch.setattr(agent_memory_module, "store_memory", store_mock)

    await agent_memory_module.remember_if_novel(
        project_id="proj_test",
        content="Durable finding from task summary",
        memory_type="learning",
        scope="project",
    )

    assert recall_mock.await_args.kwargs["include_pending"] is True


@pytest.mark.asyncio
async def test_remember_if_novel_supersedes_similar_non_duplicate_memory(
    monkeypatch,
    agent_memory_module,
):
    """A close but non-duplicate write should become active truth and supersede the older match."""

    recall_mock = AsyncMock(
        return_value={
            "memories": [
                {
                    "memory_id": "mem_old",
                    "content": "SVG documents are not ingested directly.",
                    "relevance": 0.84,
                }
            ]
        }
    )
    store_mock = AsyncMock(return_value={"memory_id": "mem_new"})
    supersede_mock = AsyncMock(return_value={"superseded": True, "old_memory_id": "mem_old"})

    monkeypatch.setattr(agent_memory_module, "semantic_recall", recall_mock)
    monkeypatch.setattr(agent_memory_module, "store_memory", store_mock)
    monkeypatch.setattr(agent_memory_module, "supersede_memory_v2", supersede_mock)
    monkeypatch.setattr(agent_memory_module.settings, "memory_v2_primary_read", True)

    result = await agent_memory_module.remember_if_novel(
        project_id="proj_test",
        content="SVG documents are ingested through the binary parser lane.",
        memory_type="learning",
        scope="project",
        novelty_threshold=0.92,
        allow_supersede=True,
    )

    assert result["stored"] is True
    assert result["reason"] == "superseded"
    assert result["superseded_memory"]["old_memory_id"] == "mem_old"
    assert store_mock.await_args.kwargs["related_to"] == ["mem_old"]
    supersede_mock.assert_awaited_once_with(
        "mem_old",
        "mem_new",
        reason="Superseded by newer remember_if_novel write",
    )


@pytest.mark.asyncio
async def test_memory_invalidate_falls_back_to_legacy_rows(monkeypatch, agent_memory_module):
    """Lifecycle tools should still work for pre-Memory V2 legacy memories."""

    find_unique = AsyncMock(return_value=type("MemoryRow", (), {"id": "legacy_old"})())
    update = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {
            "agentmemory": type(
                "AgentMemoryRepo", (), {"find_unique": find_unique, "update": update}
            )()
        },
    )()

    monkeypatch.setattr(agent_memory_module, "_resolve_memory_v2_id", AsyncMock(return_value=None))
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))

    result = await agent_memory_module.invalidate_memory_v2(
        "legacy_old",
        reason="obsolete auto receipt",
    )

    assert result["invalidated"] is True
    assert result["status"] == "invalidated"
    assert result["memory_id"] == "legacy_old"
    update_payload = update.await_args.kwargs
    assert update_payload["where"] == {"id": "legacy_old"}
    assert update_payload["data"]["status"] == "INVALIDATED"
    assert update_payload["data"]["invalidatedReason"] == "obsolete auto receipt"


@pytest.mark.asyncio
async def test_memory_invalidate_marks_legacy_row_when_v2_mapping_exists(
    monkeypatch,
    agent_memory_module,
):
    """Dual-written legacy IDs should be hidden from legacy health scans too."""

    find_unique = AsyncMock(return_value=type("MemoryRow", (), {"id": "legacy_old"})())
    update = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {
            "agentmemory": type(
                "AgentMemoryRepo", (), {"find_unique": find_unique, "update": update}
            )()
        },
    )()
    invalidate_v2 = AsyncMock()

    monkeypatch.setattr(
        agent_memory_module, "_resolve_memory_v2_id", AsyncMock(return_value="v2_old")
    )
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module._memory_repository, "invalidate_memory", invalidate_v2)

    result = await agent_memory_module.invalidate_memory_v2(
        "legacy_old",
        reason="active superseded category cleanup",
    )

    invalidate_v2.assert_awaited_once()
    assert result["memory_id"] == "v2_old"
    assert result["legacy_memory_id"] == "legacy_old"
    assert result["legacy_invalidated"] is True
    update_payload = update.await_args.kwargs
    assert update_payload["where"] == {"id": "legacy_old"}
    assert update_payload["data"]["status"] == "INVALIDATED"
    assert update_payload["data"]["invalidatedReason"] == "active superseded category cleanup"


@pytest.mark.asyncio
async def test_memory_invalidate_marks_legacy_row_when_v2_id_matches(
    monkeypatch,
    agent_memory_module,
):
    """Legacy health scans must hide direct legacy IDs that also resolve in Memory V2."""

    find_unique = AsyncMock(return_value=type("MemoryRow", (), {"id": "legacy_old"})())
    update = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {
            "agentmemory": type(
                "AgentMemoryRepo", (), {"find_unique": find_unique, "update": update}
            )()
        },
    )()
    invalidate_v2 = AsyncMock()

    monkeypatch.setattr(
        agent_memory_module, "_resolve_memory_v2_id", AsyncMock(return_value="legacy_old")
    )
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module._memory_repository, "invalidate_memory", invalidate_v2)

    result = await agent_memory_module.invalidate_memory_v2(
        "legacy_old",
        reason="active superseded category cleanup",
    )

    invalidate_v2.assert_awaited_once_with("legacy_old", ANY)
    assert result["memory_id"] == "legacy_old"
    assert result["legacy_memory_id"] == "legacy_old"
    assert result["legacy_invalidated"] is True
    update_payload = update.await_args.kwargs
    assert update_payload["where"] == {"id": "legacy_old"}
    assert update_payload["data"]["status"] == "INVALIDATED"
    assert update_payload["data"]["invalidatedReason"] == "active superseded category cleanup"


@pytest.mark.asyncio
async def test_memory_supersede_falls_back_to_legacy_rows(monkeypatch, agent_memory_module):
    """Supersede should not fail when both visible memories are legacy rows."""

    old_row = type("MemoryRow", (), {"id": "legacy_old"})()
    new_row = type("MemoryRow", (), {"id": "legacy_new"})()
    find_unique = AsyncMock(side_effect=[old_row, new_row])
    update = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {
            "agentmemory": type(
                "AgentMemoryRepo", (), {"find_unique": find_unique, "update": update}
            )()
        },
    )()

    monkeypatch.setattr(agent_memory_module, "_resolve_memory_v2_id", AsyncMock(return_value=None))
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))

    result = await agent_memory_module.supersede_memory_v2(
        "legacy_old",
        "legacy_new",
        reason="newer correction",
    )

    assert result["superseded"] is True
    assert result["old_memory_id"] == "legacy_old"
    assert result["new_memory_id"] == "legacy_new"
    update_payload = update.await_args.kwargs
    assert update_payload["where"] == {"id": "legacy_old"}
    assert update_payload["data"]["status"] == "SUPERSEDED"
    assert update_payload["data"]["supersededByMemoryId"] == "legacy_new"


@pytest.mark.asyncio
async def test_store_memory_persists_review_status_fields(
    monkeypatch,
    agent_memory_module,
):
    """Memory V2 writes should persist review queue metadata as lifecycle status."""

    created_row = type(
        "Row",
        (),
        {"id": "mem_123", "content": "Queued memory", "status": "CANDIDATE"},
    )()
    create_mock = AsyncMock(return_value=created_row)
    repo = type(
        "Repo",
        (),
        {
            "create_memory": create_mock,
            "attach_evidence": AsyncMock(return_value=[]),
            "create_relations": AsyncMock(return_value=[]),
        },
    )()
    mock_db = type(
        "MockDb",
        (),
        {"project": None},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "_memory_repository", repo)
    monkeypatch.setattr(
        agent_memory_module, "get_memory_retention_limit", AsyncMock(return_value=-1)
    )
    monkeypatch.setattr(agent_memory_module, "_store_memory_embedding", AsyncMock())
    monkeypatch.setattr(
        agent_memory_module,
        "get_embeddings_service",
        lambda: type(
            "EmbeddingsService",
            (),
            {"embed_text_async": AsyncMock(return_value=[0.1, 0.2])},
        )(),
    )

    result = await agent_memory_module.store_memory(
        project_id="proj_test",
        content="Queued memory",
        memory_type="decision",
        scope="project",
        review_status="pending",
    )

    create_mock.assert_awaited_once()
    payload = create_mock.await_args.args[0]
    assert payload.status == agent_memory_module.MemoryStatus.CANDIDATE
    assert result["review_status"] == "pending"
    assert result["status"] == "candidate"


@pytest.mark.asyncio
async def test_list_memory_review_queue_returns_v2_and_legacy_candidates(
    monkeypatch,
    agent_memory_module,
):
    """The private review queue should surface Memory V2 candidates and legacy pending rows."""
    now = datetime.now(UTC)
    evidence = type(
        "Evidence",
        (),
        {
            "evidenceType": "PR",
            "documentId": None,
            "chunkId": None,
            "externalRef": "https://github.com/Snipara/snipara/pull/1",
            "snippet": "Reviewed GitHub evidence",
            "lineStart": None,
            "lineEnd": None,
            "weight": 1.0,
        },
    )()
    v2_row = type(
        "MemoryRow",
        (),
        {
            "id": "v2_candidate",
            "projectId": "proj_test",
            "teamId": None,
            "userId": None,
            "agentId": None,
            "content": "GitHub evidence candidate",
            "type": "LEARNING",
            "scope": "PROJECT",
            "category": "github",
            "source": "WEBHOOK",
            "status": "CANDIDATE",
            "confidence": 0.8,
            "createdAt": now,
            "updatedAt": now,
            "validUntil": None,
            "staleAt": None,
            "archivedAt": None,
            "lastAccessedAt": None,
            "evidenceLinks": [evidence],
        },
    )()
    legacy_row = type(
        "AgentMemoryRow",
        (),
        {
            "id": "legacy_pending",
            "projectId": "proj_test",
            "content": "Legacy pending candidate",
            "type": "DECISION",
            "scope": "PROJECT",
            "category": "workflow",
            "source": "transcript",
            "status": "ACTIVE",
            "reviewStatus": "PENDING",
            "reviewNotes": None,
            "confidence": 0.9,
            "createdAt": now,
            "updatedAt": now,
            "reviewedAt": None,
            "expiresAt": None,
            "lastAccessedAt": None,
            "accessCount": 0,
            "documentRefs": ["docs/spec.md"],
        },
    )()
    memory_count = AsyncMock(return_value=1)
    memory_find_many = AsyncMock(return_value=[v2_row])
    legacy_count = AsyncMock(return_value=1)
    legacy_find_many = AsyncMock(return_value=[legacy_row])
    mock_db = type(
        "MockDb",
        (),
        {
            "project": None,
            "memory": type(
                "MemoryRepo", (), {"count": memory_count, "find_many": memory_find_many}
            )(),
            "agentmemory": type(
                "AgentMemoryRepo", (), {"count": legacy_count, "find_many": legacy_find_many}
            )(),
        },
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))

    result = await agent_memory_module.list_memory_review_queue(project_id="proj_test")

    assert result["mutated"] is False
    assert [item["memory_id"] for item in result["items"]] == ["v2_candidate", "legacy_pending"]
    assert result["items"][0]["evidence"][0]["evidence_type"] == "pr"
    assert result["items"][1]["evidence"][0]["external_ref"] == "docs/spec.md"
    assert {"status": "CANDIDATE"} in memory_find_many.await_args.kwargs["where"]["AND"]
    assert legacy_find_many.await_args.kwargs["where"]["reviewStatus"] == "PENDING"


@pytest.mark.asyncio
async def test_resolve_memory_review_queue_item_accepts_v2_and_legacy(
    monkeypatch,
    agent_memory_module,
):
    """Accepting a queued item should activate Memory V2 and approve the legacy row."""
    v2_row = type("MemoryRow", (), {"id": "v2_candidate", "projectId": "proj_test"})()
    legacy_row = type("AgentMemoryRow", (), {"id": "legacy_candidate", "projectId": "proj_test"})()
    v2_find_unique = AsyncMock(return_value=v2_row)
    legacy_find_first = AsyncMock(return_value=legacy_row)
    legacy_update_many = AsyncMock(return_value=type("UpdateResult", (), {"count": 1})())
    mock_db = type(
        "MockDb",
        (),
        {
            "memory": type("MemoryRepo", (), {"find_unique": v2_find_unique})(),
            "agentmemory": type(
                "AgentMemoryRepo",
                (),
                {"find_first": legacy_find_first, "update_many": legacy_update_many},
            )(),
        },
    )()
    update_memory = AsyncMock()

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(
        agent_memory_module, "_resolve_memory_v2_id", AsyncMock(return_value="v2_candidate")
    )
    monkeypatch.setattr(agent_memory_module._memory_repository, "update_memory", update_memory)

    result = await agent_memory_module.resolve_memory_review_queue_item(
        project_id="proj_test",
        memory_id="legacy_candidate",
        action="accept",
        notes="confirmed",
        reviewed_by="user_123",
    )

    assert result["mutated"] is True
    assert result["status"] == "active"
    assert result["review_status"] == "approved"
    payload = update_memory.await_args.args[1]
    assert payload.status == agent_memory_module.MemoryStatus.ACTIVE
    legacy_update = legacy_update_many.await_args.kwargs["data"]
    assert legacy_update["reviewStatus"] == "APPROVED"
    assert legacy_update["status"] == "ACTIVE"
    assert legacy_update["reviewedBy"] == "user_123"


def test_memory_v2_user_scope_is_owned_by_user_not_team(agent_memory_module):
    """USER memories must stay personal to the authenticated user, even in team workspaces."""

    owner = agent_memory_module._memory_v2_owner_payload(
        project_id="proj_team",
        scope=agent_memory_module.AgentMemoryScope.USER,
        user_id="user_123",
        team_id="team_123",
        agent_id=None,
    )

    assert owner["project_id"] == "proj_team"
    assert owner["user_id"] == "user_123"
    assert owner["team_id"] is None
    assert owner["agent_id"] is None


def test_memory_v2_user_recall_filters_by_user_id_not_project_or_team(agent_memory_module):
    """A user-scope recall should be portable across projects but isolated by user."""

    where = agent_memory_module._build_memory_v2_where(
        project_id="proj_b",
        scope=agent_memory_module.AgentMemoryScope.USER,
        user_id="user_123",
        team_id="team_123",
        agent_id=None,
    )

    owner_clause = where["AND"][0]["OR"]
    assert owner_clause == [{"userId": "user_123", "scope": "USER"}]
    assert "projectId" not in owner_clause[0]
    assert "teamId" not in owner_clause[0]


def test_memory_v2_default_recall_combines_project_team_and_personal_user(agent_memory_module):
    """Unscoped recall should include project, team, and the current user's private memory."""

    where = agent_memory_module._build_memory_v2_where(
        project_id="proj_a",
        scope=None,
        user_id="user_123",
        team_id="team_123",
        agent_id=None,
    )

    owner_clause = where["AND"][0]["OR"]
    assert {"projectId": "proj_a", "scope": "PROJECT"} in owner_clause
    assert {"teamId": "team_123", "scope": "TEAM"} in owner_clause
    assert {"userId": "user_123", "scope": "USER"} in owner_clause


def test_memory_v2_user_scope_requires_authenticated_user(agent_memory_module):
    """A USER memory without a user id would be shared ambiguously and must fail."""

    assert (
        agent_memory_module.get_memory_scope_owner_error(
            "user",
            user_id=None,
            team_id="team_123",
        )
        == "scope=user requires an authenticated user_id"
    )


@pytest.mark.asyncio
async def test_store_memory_clamps_ttl_and_sets_critical_tier(
    monkeypatch,
    agent_memory_module,
):
    """Explicit TTLs should respect plan retention on Memory V2 rows."""

    created_row = type(
        "Row",
        (),
        {"id": "mem_123", "content": "Queued memory", "status": "ACTIVE"},
    )()
    create_mock = AsyncMock(return_value=created_row)
    repo = type(
        "Repo",
        (),
        {
            "create_memory": create_mock,
            "attach_evidence": AsyncMock(return_value=[]),
            "create_relations": AsyncMock(return_value=[]),
        },
    )()
    mock_db = type(
        "MockDb",
        (),
        {"project": None},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "_memory_repository", repo)
    monkeypatch.setattr(agent_memory_module, "_store_memory_embedding", AsyncMock())
    monkeypatch.setattr(
        agent_memory_module, "get_memory_retention_limit", AsyncMock(return_value=7)
    )
    monkeypatch.setattr(
        agent_memory_module,
        "get_embeddings_service",
        lambda: type(
            "EmbeddingsService",
            (),
            {"embed_text_async": AsyncMock(return_value=[0.1, 0.2])},
        )(),
    )

    before = datetime.now(UTC)
    result = await agent_memory_module.store_memory(
        project_id="proj_test",
        content="Promote this decision",
        memory_type="decision",
        scope="project",
        ttl_days=30,
    )
    after = datetime.now(UTC)

    create_mock.assert_awaited_once()
    payload = create_mock.await_args.args[0]
    assert payload.type == agent_memory_module.AgentMemoryType.DECISION
    assert payload.valid_until is not None
    assert (
        before + timedelta(days=6, hours=23)
        <= payload.valid_until
        <= after + timedelta(days=7, minutes=1)
    )
    assert result["expires_at"] is not None


@pytest.mark.asyncio
async def test_store_memory_applies_default_ttl_for_learning(
    monkeypatch,
    agent_memory_module,
):
    """Volatile knowledge types should get a default TTL even when callers omit one."""

    created_row = type(
        "Row",
        (),
        {"id": "mem_456", "content": "Learned memory", "status": "ACTIVE"},
    )()
    create_mock = AsyncMock(return_value=created_row)
    repo = type(
        "Repo",
        (),
        {
            "create_memory": create_mock,
            "attach_evidence": AsyncMock(return_value=[]),
            "create_relations": AsyncMock(return_value=[]),
        },
    )()
    mock_db = type(
        "MockDb",
        (),
        {"project": None},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "_memory_repository", repo)
    monkeypatch.setattr(agent_memory_module, "_store_memory_embedding", AsyncMock())
    monkeypatch.setattr(
        agent_memory_module, "get_memory_retention_limit", AsyncMock(return_value=90)
    )
    monkeypatch.setattr(
        agent_memory_module,
        "get_embeddings_service",
        lambda: type(
            "EmbeddingsService",
            (),
            {"embed_text_async": AsyncMock(return_value=[0.1, 0.2])},
        )(),
    )

    before = datetime.now(UTC)
    await agent_memory_module.store_memory(
        project_id="proj_test",
        content="Learned that smaller prompts work better.",
        memory_type="learning",
        scope="project",
    )
    after = datetime.now(UTC)

    payload = create_mock.await_args.args[0]
    assert payload.type == agent_memory_module.AgentMemoryType.LEARNING
    assert payload.valid_until is not None
    assert (
        before + timedelta(days=29, hours=23)
        <= payload.valid_until
        <= after + timedelta(days=30, minutes=1)
    )


@pytest.mark.asyncio
async def test_remember_if_novel_rejects_workflow_type_before_recall(
    monkeypatch,
    agent_memory_module,
):
    """workflow is only valid for end_of_task_commit.persist_types, not direct memory writes."""
    recall_mock = AsyncMock()
    monkeypatch.setattr(agent_memory_module, "semantic_recall", recall_mock)

    with pytest.raises(
        ValueError,
        match=(
            "Invalid parameter 'type': unsupported memory type 'workflow'. "
            "Expected one of: fact, decision, learning, preference, todo, context"
        ),
    ):
        await agent_memory_module.remember_if_novel(
            project_id="proj_test",
            content="Prefer workflow persistence through task commit.",
            memory_type="workflow",
            scope="project",
        )

    recall_mock.assert_not_called()


@pytest.mark.asyncio
async def test_store_memory_rejects_invalid_scope_before_db_call(
    monkeypatch,
    agent_memory_module,
):
    """Invalid scopes should fail fast with a client-safe validation error."""
    get_db_mock = AsyncMock()
    monkeypatch.setattr(agent_memory_module, "get_db", get_db_mock)

    with pytest.raises(
        ValueError,
        match=(
            "Invalid parameter 'scope': unsupported scope 'workspace'. "
            "Expected one of: agent, project, team, user"
        ),
    ):
        await agent_memory_module.store_memory(
            project_id="proj_test",
            content="Test durable memory",
            memory_type="decision",
            scope="workspace",
        )

    get_db_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_semantic_recall_filters_transient_session_noise_without_category(
    monkeypatch,
    agent_memory_module,
):
    """Default recall should ignore low-signal hook/session markers."""

    now = datetime.now(UTC)
    session_memory = type(
        "Memory",
        (),
        {
            "id": "mem_session",
            "content": "Session ended at 2026-04-17T19:28:52.000Z. Session ID: sess_123",
            "category": "session",
            "type": "CONTEXT",
            "scope": "PROJECT",
            "confidence": 0.9,
            "createdAt": now,
            "lastAccessedAt": None,
            "accessCount": 0,
            "reviewStatus": "APPROVED",
            "status": "ACTIVE",
        },
    )()
    relevant_memory = type(
        "Memory",
        (),
        {
            "id": "mem_real",
            "content": "Use Haiku for lightweight sub-agents by default.",
            "category": "models",
            "type": "FACT",
            "scope": "PROJECT",
            "confidence": 0.95,
            "createdAt": now,
            "lastAccessedAt": None,
            "accessCount": 0,
            "reviewStatus": "APPROVED",
            "status": "ACTIVE",
        },
    )()

    find_many = AsyncMock(return_value=[session_memory, relevant_memory])
    update_many = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {
            "memory": type(
                "MemoryRepo",
                (),
                {"find_many": find_many, "update_many": update_many},
            )(),
            "project": None,
        },
    )()

    embeddings = type(
        "EmbeddingsService",
        (),
        {
            "embed_text_async": AsyncMock(return_value=[0.1, 0.2]),
            "cosine_similarity": lambda self, query_embedding, doc_embeddings: [0.95],
        },
    )()

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "get_embeddings_service", lambda: embeddings)
    monkeypatch.setattr(
        agent_memory_module,
        "_get_memory_embeddings_batch",
        AsyncMock(return_value={"mem_real": [0.2, 0.3]}),
    )

    result = await agent_memory_module.semantic_recall(
        project_id="proj_test",
        query="sub-agent model choice",
    )

    assert len(result["memories"]) == 1
    assert result["memories"][0]["memory_id"] == "mem_real"


@pytest.mark.asyncio
async def test_semantic_recall_boosts_user_preference_intent(
    monkeypatch,
    agent_memory_module,
):
    """Preference intent should let a slightly weaker semantic match outrank generic memory."""

    now = datetime.now(UTC)
    preference = type(
        "Memory",
        (),
        {
            "id": "mem_preference",
            "content": "Prefer Helix editor for quick terminal edits.",
            "category": "workflow",
            "type": "PREFERENCE",
            "scope": "USER",
            "tier": "CRITICAL",
            "confidence": 1.0,
            "createdAt": now,
            "lastAccessedAt": None,
            "accessCount": 0,
            "reviewStatus": "APPROVED",
            "status": "ACTIVE",
        },
    )()
    generic = type(
        "Memory",
        (),
        {
            "id": "mem_generic",
            "content": "Editor configuration is documented in the repo.",
            "category": "docs",
            "type": "FACT",
            "scope": "PROJECT",
            "tier": "CRITICAL",
            "confidence": 1.0,
            "createdAt": now,
            "lastAccessedAt": None,
            "accessCount": 0,
            "reviewStatus": "APPROVED",
            "status": "ACTIVE",
        },
    )()

    update_many = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {
            "memory": type(
                "MemoryRepo",
                (),
                {
                    "find_many": AsyncMock(return_value=[preference, generic]),
                    "update_many": update_many,
                },
            )(),
            "project": None,
        },
    )()

    embeddings = type(
        "EmbeddingsService",
        (),
        {
            "embed_text_async": AsyncMock(return_value=[0.1, 0.2]),
            "cosine_similarity": lambda self, query_embedding, doc_embeddings: [0.79, 0.83],
        },
    )()

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "get_embeddings_service", lambda: embeddings)
    monkeypatch.setattr(
        agent_memory_module,
        "_get_memory_embeddings_batch",
        AsyncMock(
            return_value={
                "mem_preference": [0.2, 0.3],
                "mem_generic": [0.3, 0.4],
            }
        ),
    )

    result = await agent_memory_module.semantic_recall(
        project_id="proj_test",
        query="user preference editor",
        min_relevance=0.0,
    )

    assert result["memories"][0]["memory_id"] == "mem_preference"
    assert result["memories"][0]["ranking_boosts"] == ["preference_intent"]


@pytest.mark.asyncio
async def test_semantic_recall_queries_only_active_v2_candidates_by_default(
    monkeypatch,
    agent_memory_module,
):
    """Memory V2 recall should query only active memories by default."""

    now = datetime.now(UTC)
    active_memory = type(
        "Memory",
        (),
        {
            "id": "mem_active",
            "content": "Use the active memory first.",
            "category": "models",
            "type": "FACT",
            "scope": "PROJECT",
            "confidence": 0.95,
            "createdAt": now,
            "lastAccessedAt": None,
            "accessCount": 0,
            "status": "ACTIVE",
        },
    )()

    find_many = AsyncMock(return_value=[active_memory])
    update_many = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {
            "memory": type(
                "MemoryRepo",
                (),
                {"find_many": find_many, "update_many": update_many},
            )(),
            "project": None,
        },
    )()

    embeddings = type(
        "EmbeddingsService",
        (),
        {
            "embed_text_async": AsyncMock(return_value=[0.1, 0.2]),
            "cosine_similarity": lambda self, query_embedding, doc_embeddings: [0.95],
        },
    )()

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "get_embeddings_service", lambda: embeddings)
    monkeypatch.setattr(
        agent_memory_module,
        "_get_memory_embeddings_batch",
        AsyncMock(return_value={"mem_active": [0.2, 0.3]}),
    )

    result = await agent_memory_module.semantic_recall(
        project_id="proj_test",
        query="memory choice",
        category="models",
    )

    assert find_many.await_count == 1
    assert {"status": "ACTIVE"} in find_many.await_args.kwargs["where"]["AND"]
    assert result["memories"][0]["memory_id"] == "mem_active"
