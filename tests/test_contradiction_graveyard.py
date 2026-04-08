"""Tests for contradiction detection and graveyard system.

Tests the new memory features:
- Write-time contradiction detection
- Graveyard bury/unbury/scan

NOTE: We do NOT import conftest_handlers here because it replaces
src.services.agent_memory with a MagicMock. We mock dependencies directly.
"""

import os

# Set required env vars before any imports
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("NEON_DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("NEXTAUTH_SECRET", "test-secret")

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.agent_memory import (
    _check_write_time_contradictions,
    _scan_graveyard,
    bury_memory,
    unbury_memory,
)


def _make_db_mock(**overrides):
    """Create a properly-structured async DB mock."""
    db = MagicMock()
    db.agentmemory = MagicMock()
    db.agentmemory.find_many = AsyncMock(return_value=[])
    db.agentmemory.find_first = AsyncMock(return_value=None)
    db.agentmemory.create = AsyncMock()
    db.agentmemory.update = AsyncMock()
    db.agentmemory.update_many = AsyncMock()
    db.agentmemory.delete_many = AsyncMock(return_value=0)
    for k, v in overrides.items():
        setattr(db.agentmemory, k, v)
    return db


def _make_redis_mock(**overrides):
    """Create a properly-structured async Redis mock."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    for k, v in overrides.items():
        setattr(redis, k, v)
    return redis


# ============ CONTRADICTION DETECTION TESTS ============


class TestWriteTimeContradiction:
    """Tests for _check_write_time_contradictions()."""

    @pytest.mark.asyncio
    @patch("src.services.agent_memory.get_embeddings_service")
    @patch("src.services.agent_memory._get_memory_embeddings_batch", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    async def test_no_contradiction_when_no_candidates(self, mock_db, mock_batch, mock_emb_svc):
        """No contradiction if no same-type memories exist."""
        db = _make_db_mock()
        mock_db.return_value = db

        result = await _check_write_time_contradictions(
            project_id="proj_1",
            new_memory_id="mem_new",
            new_content="User prefers React",
            new_embedding=[0.1] * 1024,
            memory_type="PREFERENCE",
        )

        assert result is None

    @pytest.mark.asyncio
    @patch("src.services.agent_memory.get_embeddings_service")
    @patch("src.services.agent_memory._get_memory_embeddings_batch", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    async def test_contradiction_detected(self, mock_db, mock_batch, mock_emb_svc):
        """Detects contradiction when a similar same-type memory exists."""
        old_memory = MagicMock()
        old_memory.id = "mem_old"
        old_memory.content = "User prefers Vue for frontend"
        old_memory.type = "PREFERENCE"

        db = _make_db_mock(find_many=AsyncMock(return_value=[old_memory]))
        mock_db.return_value = db

        mock_batch.return_value = {"mem_old": [0.1] * 1024}

        emb_svc = MagicMock()
        emb_svc.cosine_similarity.return_value = [0.91]
        mock_emb_svc.return_value = emb_svc

        result = await _check_write_time_contradictions(
            project_id="proj_1",
            new_memory_id="mem_new",
            new_content="User prefers React for frontend",
            new_embedding=[0.1] * 1024,
            memory_type="PREFERENCE",
        )

        assert result is not None
        assert result["contradicts_memory_id"] == "mem_old"
        assert result["similarity"] == 0.91
        assert db.agentmemory.update.call_count == 2

    @pytest.mark.asyncio
    @patch("src.services.agent_memory.get_embeddings_service")
    @patch("src.services.agent_memory._get_memory_embeddings_batch", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    async def test_no_contradiction_below_threshold(self, mock_db, mock_batch, mock_emb_svc):
        """No contradiction if similarity is below 0.85."""
        old_memory = MagicMock()
        old_memory.id = "mem_old"
        old_memory.content = "Something unrelated"
        old_memory.type = "PREFERENCE"

        db = _make_db_mock(find_many=AsyncMock(return_value=[old_memory]))
        mock_db.return_value = db

        mock_batch.return_value = {"mem_old": [0.1] * 1024}

        emb_svc = MagicMock()
        emb_svc.cosine_similarity.return_value = [0.60]
        mock_emb_svc.return_value = emb_svc

        result = await _check_write_time_contradictions(
            project_id="proj_1",
            new_memory_id="mem_new",
            new_content="User prefers React",
            new_embedding=[0.1] * 1024,
            memory_type="PREFERENCE",
        )

        assert result is None

    @pytest.mark.asyncio
    @patch("src.services.agent_memory.get_embeddings_service")
    @patch("src.services.agent_memory._get_memory_embeddings_batch", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    async def test_no_contradiction_for_near_duplicates(self, mock_db, mock_batch, mock_emb_svc):
        """No contradiction if similarity >= 0.98 (near-duplicate)."""
        old_memory = MagicMock()
        old_memory.id = "mem_old"
        old_memory.content = "Same content"
        old_memory.type = "FACT"

        db = _make_db_mock(find_many=AsyncMock(return_value=[old_memory]))
        mock_db.return_value = db

        mock_batch.return_value = {"mem_old": [0.1] * 1024}

        emb_svc = MagicMock()
        emb_svc.cosine_similarity.return_value = [0.99]
        mock_emb_svc.return_value = emb_svc

        result = await _check_write_time_contradictions(
            project_id="proj_1",
            new_memory_id="mem_new",
            new_content="Same content",
            new_embedding=[0.1] * 1024,
            memory_type="FACT",
        )

        assert result is None


# ============ GRAVEYARD TESTS ============


class TestBuryMemory:
    """Tests for bury_memory()."""

    @pytest.mark.asyncio
    async def test_bury_requires_id_or_content(self):
        """Bury requires either memory_id or content."""
        result = await bury_memory(
            project_id="proj_1",
            reason="Failed approach",
        )
        assert "error" in result

    @pytest.mark.asyncio
    @patch("src.services.agent_memory.get_redis", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    async def test_bury_existing_memory(self, mock_db, mock_redis):
        """Bury an existing memory by ID."""
        memory = MagicMock()
        memory.id = "mem_123"
        memory.content = "Tried Redis for search"

        db = _make_db_mock(find_first=AsyncMock(return_value=memory))
        mock_db.return_value = db

        mock_redis.return_value = _make_redis_mock()

        result = await bury_memory(
            project_id="proj_1",
            reason="Too slow for our dataset",
            memory_id="mem_123",
        )

        assert result["memory_id"] == "mem_123"
        assert result["was_existing"] is True
        assert result["buried_reason"] == "Too slow for our dataset"
        db.agentmemory.update.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.agent_memory.get_redis", new_callable=AsyncMock)
    @patch("src.services.agent_memory._store_memory_embedding", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_embeddings_service")
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    async def test_bury_new_content(self, mock_db, mock_emb_svc, mock_store_emb, mock_redis):
        """Bury new content directly (no existing memory)."""
        memory = MagicMock()
        memory.id = "mem_new"

        db = _make_db_mock(create=AsyncMock(return_value=memory))
        mock_db.return_value = db

        emb_svc = MagicMock()
        emb_svc.embed_text_async = AsyncMock(return_value=[0.1] * 1024)
        mock_emb_svc.return_value = emb_svc

        mock_store_emb.return_value = True
        mock_redis.return_value = _make_redis_mock()

        result = await bury_memory(
            project_id="proj_1",
            reason="Didn't scale",
            content="Tried MongoDB for time-series data",
        )

        assert result["memory_id"] == "mem_new"
        assert result["was_existing"] is False
        db.agentmemory.create.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    async def test_bury_nonexistent_memory(self, mock_db):
        """Bury a non-existent memory returns error."""
        db = _make_db_mock()
        mock_db.return_value = db

        result = await bury_memory(
            project_id="proj_1",
            reason="Failed",
            memory_id="mem_nonexistent",
        )

        assert "error" in result


class TestUnburyMemory:
    """Tests for unbury_memory()."""

    @pytest.mark.asyncio
    @patch("src.services.agent_memory.get_redis", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    async def test_unbury_success(self, mock_db, mock_redis):
        """Successfully unbury a graveyard memory."""
        memory = MagicMock()
        memory.id = "mem_123"
        memory.content = "Previously buried approach"

        db = _make_db_mock(find_first=AsyncMock(return_value=memory))
        mock_db.return_value = db

        mock_redis.return_value = _make_redis_mock()

        result = await unbury_memory(
            project_id="proj_1",
            memory_id="mem_123",
        )

        assert result["memory_id"] == "mem_123"
        assert result["reinstated_tier"] == "archive"
        db.agentmemory.update.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    async def test_unbury_nonexistent(self, mock_db):
        """Unbury non-existent graveyard memory returns error."""
        db = _make_db_mock()
        mock_db.return_value = db

        result = await unbury_memory(
            project_id="proj_1",
            memory_id="mem_nonexistent",
        )

        assert "error" in result


class TestGraveyardScan:
    """Tests for _scan_graveyard()."""

    @pytest.mark.asyncio
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_redis", new_callable=AsyncMock)
    async def test_scan_empty_graveyard(self, mock_redis, mock_db):
        """Empty graveyard returns no warnings."""
        mock_redis.return_value = _make_redis_mock(get=AsyncMock(return_value="0"))

        result = await _scan_graveyard("proj_1", [0.1] * 1024)

        assert result == []

    @pytest.mark.asyncio
    @patch("src.services.agent_memory._get_memory_embeddings_batch", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_embeddings_service")
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_redis", new_callable=AsyncMock)
    async def test_scan_finds_matching_graveyard(self, mock_redis, mock_db, mock_emb_svc, mock_batch):
        """Scan finds matching graveyard entries and returns warnings."""
        mock_redis.return_value = _make_redis_mock()

        graveyard_mem = MagicMock()
        graveyard_mem.id = "mem_buried"
        graveyard_mem.content = "Tried Redis for full-text search"
        graveyard_mem.buriedReason = "Too slow for large datasets"
        graveyard_mem.buriedAt = datetime(2026, 1, 15, tzinfo=UTC)

        db = _make_db_mock(find_many=AsyncMock(return_value=[graveyard_mem]))
        mock_db.return_value = db

        mock_batch.return_value = {"mem_buried": [0.1] * 1024}

        emb_svc = MagicMock()
        emb_svc.cosine_similarity.return_value = [0.82]
        mock_emb_svc.return_value = emb_svc

        result = await _scan_graveyard("proj_1", [0.1] * 1024)

        assert len(result) == 1
        assert result[0]["memory_id"] == "mem_buried"
        assert result[0]["buried_reason"] == "Too slow for large datasets"
        assert result[0]["similarity"] == 0.82
        assert "Previously abandoned" in result[0]["warning"]

    @pytest.mark.asyncio
    @patch("src.services.agent_memory._get_memory_embeddings_batch", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_embeddings_service")
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_redis", new_callable=AsyncMock)
    async def test_scan_skips_low_similarity(self, mock_redis, mock_db, mock_emb_svc, mock_batch):
        """Scan skips graveyard entries below 0.70 similarity."""
        mock_redis.return_value = _make_redis_mock()

        graveyard_mem = MagicMock()
        graveyard_mem.id = "mem_buried"
        graveyard_mem.content = "Unrelated approach"
        graveyard_mem.buriedReason = "Some reason"
        graveyard_mem.buriedAt = datetime(2026, 1, 15, tzinfo=UTC)

        db = _make_db_mock(find_many=AsyncMock(return_value=[graveyard_mem]))
        mock_db.return_value = db

        mock_batch.return_value = {"mem_buried": [0.1] * 1024}

        emb_svc = MagicMock()
        emb_svc.cosine_similarity.return_value = [0.50]
        mock_emb_svc.return_value = emb_svc

        result = await _scan_graveyard("proj_1", [0.1] * 1024)

        assert result == []

    @pytest.mark.asyncio
    @patch("src.services.agent_memory._get_memory_embeddings_batch", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_embeddings_service")
    @patch("src.services.agent_memory.get_db", new_callable=AsyncMock)
    @patch("src.services.agent_memory.get_redis", new_callable=AsyncMock)
    async def test_scan_returns_max_3(self, mock_redis, mock_db, mock_emb_svc, mock_batch):
        """Scan returns at most 3 warnings."""
        mock_redis.return_value = _make_redis_mock()

        graveyard_mems = []
        embeddings = {}
        for i in range(5):
            mem = MagicMock()
            mem.id = f"mem_{i}"
            mem.content = f"Approach {i}"
            mem.buriedReason = f"Reason {i}"
            mem.buriedAt = datetime(2026, 1, 15, tzinfo=UTC)
            graveyard_mems.append(mem)
            embeddings[f"mem_{i}"] = [0.1] * 1024

        db = _make_db_mock(find_many=AsyncMock(return_value=graveyard_mems))
        mock_db.return_value = db

        mock_batch.return_value = embeddings

        emb_svc = MagicMock()
        emb_svc.cosine_similarity.return_value = [0.85]
        mock_emb_svc.return_value = emb_svc

        result = await _scan_graveyard("proj_1", [0.1] * 1024)

        assert len(result) <= 3
