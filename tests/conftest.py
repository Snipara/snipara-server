"""Shared pytest fixtures and configuration."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_validate_api_key_invalid():
    """Mock validate_api_key to return None (invalid key) without DB access."""
    with patch("src.server.validate_api_key", new_callable=AsyncMock) as mock:
        mock.return_value = None
        yield mock


@pytest.fixture
def mock_db_connection():
    """Mock get_db to prevent actual database connections."""
    with patch("src.db.get_db", new_callable=AsyncMock) as mock:
        mock.side_effect = Exception("Database not available in tests")
        yield mock
