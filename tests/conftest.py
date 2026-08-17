"""Shared pytest fixtures and configuration."""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNIPARA_MCP_SRC = PROJECT_ROOT / "snipara-mcp" / "src"

if SNIPARA_MCP_SRC.exists() and str(SNIPARA_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(SNIPARA_MCP_SRC))

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
            detail="Invalid local API key.",
        )
        yield mock


@pytest.fixture
def mock_db_connection():
    """Mock get_db to prevent actual database connections."""
    with patch("src.db.get_db", new_callable=AsyncMock) as mock:
        mock.side_effect = Exception("Database not available in tests")
        yield mock
