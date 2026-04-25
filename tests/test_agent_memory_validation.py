"""Regression tests for public agent memory parameter validation."""

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
        {"agentmemory": type("AgentMemoryRepo", (), {"find_many": find_many})()},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))

    result = await agent_memory_module.semantic_recall(
        project_id="proj_test",
        query="memory review queue",
    )

    assert result["memories"] == []
    assert find_many.await_count == 2
    assert find_many.await_args_list[0].kwargs["where"]["reviewStatus"] == "APPROVED"
    assert find_many.await_args_list[0].kwargs["where"]["status"] == "ACTIVE"


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
    update_mock = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"update": update_mock})()},
    )()

    monkeypatch.setattr(agent_memory_module, "semantic_recall", recall_mock)
    monkeypatch.setattr(agent_memory_module, "store_memory", store_mock)
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module.settings, "memory_v2_dual_write", False)

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
    update_payload = update_mock.await_args.kwargs
    assert update_payload["where"] == {"id": "mem_old"}
    assert update_payload["data"]["status"] == "SUPERSEDED"
    assert update_payload["data"]["supersededByMemoryId"] == "mem_new"


@pytest.mark.asyncio
async def test_store_memory_persists_review_status_fields(
    monkeypatch,
    agent_memory_module,
):
    """Legacy AgentMemory writes should persist review queue metadata."""

    created_row = type("Row", (), {"id": "mem_123", "content": "Queued memory"})()
    create_mock = AsyncMock(return_value=created_row)
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"create": create_mock})()},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "get_memory_retention_limit", AsyncMock(return_value=-1))
    monkeypatch.setattr(agent_memory_module, "_store_memory_embedding", AsyncMock())
    monkeypatch.setattr(agent_memory_module, "_safe_auto_compact", AsyncMock())
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
    assert create_mock.await_args.kwargs["data"]["reviewStatus"] == "PENDING"
    assert result["review_status"] == "pending"


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
    """Explicit TTLs should respect plan retention, and decisions should land in CRITICAL."""

    created_row = type("Row", (), {"id": "mem_123", "content": "Queued memory"})()
    create_mock = AsyncMock(return_value=created_row)
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"create": create_mock})()},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "_store_memory_embedding", AsyncMock())
    monkeypatch.setattr(agent_memory_module, "_safe_auto_compact", AsyncMock())
    monkeypatch.setattr(agent_memory_module, "get_memory_retention_limit", AsyncMock(return_value=7))
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
    payload = create_mock.await_args.kwargs["data"]
    assert payload["tier"] == "CRITICAL"
    assert payload["expiresAt"] is not None
    assert before + timedelta(days=6, hours=23) <= payload["expiresAt"] <= after + timedelta(days=7, minutes=1)
    assert result["expires_at"] is not None


@pytest.mark.asyncio
async def test_store_memory_applies_default_ttl_for_learning(
    monkeypatch,
    agent_memory_module,
):
    """Volatile knowledge types should get a default TTL even when callers omit one."""

    created_row = type("Row", (), {"id": "mem_456", "content": "Learned memory"})()
    create_mock = AsyncMock(return_value=created_row)
    mock_db = type(
        "MockDb",
        (),
        {"agentmemory": type("AgentMemoryRepo", (), {"create": create_mock})()},
    )()
    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "_store_memory_embedding", AsyncMock())
    monkeypatch.setattr(agent_memory_module, "_safe_auto_compact", AsyncMock())
    monkeypatch.setattr(agent_memory_module, "get_memory_retention_limit", AsyncMock(return_value=90))
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

    payload = create_mock.await_args.kwargs["data"]
    assert payload["tier"] == "ARCHIVE"
    assert payload["expiresAt"] is not None
    assert before + timedelta(days=29, hours=23) <= payload["expiresAt"] <= after + timedelta(days=30, minutes=1)


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
        },
    )()

    find_many = AsyncMock(return_value=[session_memory, relevant_memory])
    update_many = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {
            "agentmemory": type(
                "AgentMemoryRepo",
                (),
                {"find_many": find_many, "update_many": update_many},
            )()
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
async def test_semantic_recall_prefers_non_archive_candidates_before_archive(
    monkeypatch,
    agent_memory_module,
):
    """Recall should query active tiers first and only fall back to ARCHIVE when needed."""

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
            "tier": "CRITICAL",
            "confidence": 0.95,
            "createdAt": now,
            "lastAccessedAt": None,
            "accessCount": 0,
            "reviewStatus": "APPROVED",
        },
    )()
    archived_memory = type(
        "Memory",
        (),
        {
            "id": "mem_archive",
            "content": "Archived fallback memory.",
            "category": "models",
            "type": "LEARNING",
            "scope": "PROJECT",
            "tier": "ARCHIVE",
            "confidence": 0.8,
            "createdAt": now - timedelta(days=60),
            "lastAccessedAt": None,
            "accessCount": 0,
            "reviewStatus": "APPROVED",
        },
    )()

    find_many = AsyncMock(side_effect=[[active_memory], [archived_memory]])
    update_many = AsyncMock()
    mock_db = type(
        "MockDb",
        (),
        {
            "agentmemory": type(
                "AgentMemoryRepo",
                (),
                {"find_many": find_many, "update_many": update_many},
            )()
        },
    )()

    embeddings = type(
        "EmbeddingsService",
        (),
        {
            "embed_text_async": AsyncMock(return_value=[0.1, 0.2]),
            "cosine_similarity": lambda self, query_embedding, doc_embeddings: [0.95, 0.7],
        },
    )()

    monkeypatch.setattr(agent_memory_module, "get_db", AsyncMock(return_value=mock_db))
    monkeypatch.setattr(agent_memory_module, "get_embeddings_service", lambda: embeddings)
    monkeypatch.setattr(
        agent_memory_module,
        "_get_memory_embeddings_batch",
        AsyncMock(return_value={"mem_active": [0.2, 0.3], "mem_archive": [0.3, 0.4]}),
    )

    result = await agent_memory_module.semantic_recall(
        project_id="proj_test",
        query="memory choice",
        category="models",
    )

    assert find_many.await_count == 2
    assert find_many.await_args_list[0].kwargs["where"]["tier"] == {"not": "ARCHIVE"}
    assert find_many.await_args_list[1].kwargs["where"]["tier"] == "ARCHIVE"
    assert result["memories"][0]["memory_id"] == "mem_active"
