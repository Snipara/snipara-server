"""Tests for database URL normalization."""

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
