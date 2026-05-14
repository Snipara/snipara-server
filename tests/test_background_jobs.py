"""Tests for index job creation and discovery deduplication."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services import background_jobs


class _FakeTransactionContext:
    def __init__(self, transaction: AsyncMock):
        self._transaction = transaction

    async def __aenter__(self) -> AsyncMock:
        return self._transaction

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.asyncio
async def test_create_index_job_uses_advisory_lock_before_reusing_existing_job():
    """Job creation should serialize on a project/kind advisory lock."""
    transaction = AsyncMock()
    transaction.execute_raw = AsyncMock(return_value=1)
    transaction.query_raw = AsyncMock(
        return_value=[
            {
                "id": "job-existing",
                "status": "PENDING",
                "progress": 0,
                "indexMode": "INCREMENTAL",
                "kind": "CODE",
                "createdAt": None,
            }
        ]
    )

    db = AsyncMock()
    db.tx = MagicMock(return_value=_FakeTransactionContext(transaction))

    result = await background_jobs.create_index_job(
        db,
        "proj-1",
        index_kind="CODE",
    )

    assert result["id"] == "job-existing"
    assert result["already_exists"] is True
    transaction.execute_raw.assert_awaited_once()
    assert "pg_advisory_xact_lock" in transaction.execute_raw.await_args.args[0]
    assert transaction.query_raw.await_count == 1


@pytest.mark.asyncio
async def test_create_index_job_inserts_new_job_under_advisory_lock():
    """New jobs should be inserted only after the advisory lock is acquired."""
    transaction = AsyncMock()
    transaction.execute_raw = AsyncMock(return_value=1)
    transaction.query_raw = AsyncMock(
        side_effect=[
            [],
            [
                {
                    "id": "job-new",
                    "projectId": "proj-1",
                    "status": "PENDING",
                    "progress": 0,
                    "indexMode": "FULL",
                    "kind": "CODE",
                    "createdAt": None,
                }
            ],
        ]
    )

    db = AsyncMock()
    db.tx = MagicMock(return_value=_FakeTransactionContext(transaction))

    result = await background_jobs.create_index_job(
        db,
        "proj-1",
        triggered_by="system",
        triggered_via="auto_discovery",
        index_mode="FULL",
        index_kind="CODE",
    )

    assert result["id"] == "job-new"
    assert result["already_exists"] is False
    assert result["index_kind"] == "CODE"
    transaction.execute_raw.assert_awaited_once()
    assert transaction.query_raw.await_count == 2
    assert "INSERT INTO index_jobs" in transaction.query_raw.await_args_list[1].args[0]


@pytest.mark.asyncio
async def test_enqueue_discovered_index_jobs_routes_through_create_index_job(monkeypatch):
    """Auto-discovery should reuse the locked job creation path."""
    create_job = AsyncMock(return_value={"id": "job-1", "already_exists": False})
    monkeypatch.setattr(background_jobs, "create_index_job", create_job)
    db = AsyncMock()

    await background_jobs._enqueue_discovered_index_jobs(
        db,
        [
            {
                "projectId": "proj-1",
                "project_slug": "snipara",
                "unindexed_count": 3,
            }
        ],
        index_kind="CODE",
    )

    create_job.assert_awaited_once_with(
        db,
        "proj-1",
        triggered_by="system",
        triggered_via="auto_discovery",
        index_mode="INCREMENTAL",
        index_kind="CODE",
    )
