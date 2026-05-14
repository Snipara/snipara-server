"""Shared pytest fixtures and configuration."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException


os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("NEON_DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("NEXTAUTH_SECRET", "test-secret")


@pytest.fixture
def mock_validate_api_key_invalid():
    """Mock route-level auth validation to fail with a 401 invalid key."""
    from fastapi import HTTPException

    with patch("src.server.validate_and_rate_limit", new_callable=AsyncMock) as mock:
        mock.side_effect = HTTPException(
            status_code=401,
            detail="Invalid API key. Get a free key at https://snipara.com/dashboard (100 queries/month, no credit card)",
        )
        yield mock


@pytest.fixture
def mock_db_connection():
    """Mock get_db to prevent actual database connections."""
    with patch("src.db.get_db", new_callable=AsyncMock) as mock:
        mock.side_effect = Exception("Database not available in tests")
        yield mock
