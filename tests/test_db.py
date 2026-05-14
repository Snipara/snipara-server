"""Tests for database URL normalization."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.db as db_module
from src.db import _normalize_database_url


def test_normalize_database_url_removes_schema_param() -> None:
    url = (
        "postgresql://user:pass@example.com:5433/postgres"
        "?sslmode=disable&schema=tenant_snipara&connect_timeout=10"
    )

    assert _normalize_database_url(url) == (
        "postgresql://user:pass@example.com:5433/postgres"
        "?sslmode=disable&connect_timeout=10"
    )


def test_normalize_database_url_keeps_other_urls_unchanged() -> None:
    url = "postgresql://user:pass@example.com:5433/postgres?sslmode=disable"

    assert _normalize_database_url(url) == url


@pytest.mark.asyncio
async def test_get_db_skips_sql_ping_when_recently_verified(monkeypatch) -> None:
    fake_client = SimpleNamespace(is_connected=lambda: True)

    monkeypatch.setattr(db_module, "_client", fake_client)
    monkeypatch.setattr(db_module, "_last_healthcheck_monotonic", 100.0)
    monkeypatch.setattr(db_module.time, "monotonic", lambda: 120.0)
    is_connected_mock = AsyncMock(return_value=True)
    create_client_mock = AsyncMock()
    monkeypatch.setattr(db_module, "_is_connected", is_connected_mock)
    monkeypatch.setattr(db_module, "_create_client", create_client_mock)

    client = await db_module.get_db()

    assert client is fake_client
    is_connected_mock.assert_not_awaited()
    create_client_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_db_revalidates_after_interval(monkeypatch) -> None:
    fake_client = SimpleNamespace(is_connected=lambda: True)

    monkeypatch.setattr(db_module, "_client", fake_client)
    monkeypatch.setattr(db_module, "_last_healthcheck_monotonic", 100.0)
    monkeypatch.setattr(
        db_module.time,
        "monotonic",
        lambda: 100.0 + db_module.HEALTHCHECK_INTERVAL_SECONDS + 1.0,
    )
    is_connected_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(db_module, "_is_connected", is_connected_mock)

    client = await db_module.get_db()

    assert client is fake_client
    is_connected_mock.assert_awaited_once()
