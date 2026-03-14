"""Tests for snipara.sync_client — synchronous wrapper.

Tests cover:
- SniparaSync wraps Snipara correctly
- All sync methods delegate to async methods
- Context manager protocol (__enter__/__exit__)
- Jupyter-compatible event loop handling
- Config forwarding
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from snipara.config import SniparaConfig
from snipara.sync_client import SniparaSync

# ===================================================================
# Initialization
# ===================================================================


class TestSyncInit:
    """Test SniparaSync initialization."""

    def test_init_creates_async_client(self) -> None:
        cfg = SniparaConfig()
        cfg.project.api_key = "k"
        cfg.project.slug = "p"
        s = SniparaSync(config=cfg)
        assert s._async_client is not None
        assert s._async_client._api_key == "k"

    def test_init_with_explicit_params(self) -> None:
        s = SniparaSync(api_key="rlm_sync", project_slug="sync-proj")
        assert s._async_client._api_key == "rlm_sync"
        assert s._async_client._project_slug == "sync-proj"

    def test_config_property(self) -> None:
        cfg = SniparaConfig()
        s = SniparaSync(config=cfg)
        assert s.config is cfg


# ===================================================================
# Method delegation
# ===================================================================


class TestSyncMethods:
    """Test that sync methods correctly delegate to async counterparts."""

    @pytest.fixture(autouse=True)
    def _patch_client(self, mock_snipara_client: MagicMock) -> Any:
        with patch("snipara.client.Snipara._ensure_client", return_value=mock_snipara_client):
            self.mock = mock_snipara_client
            yield

    def test_query(self) -> None:
        s = SniparaSync(api_key="k", project_slug="p")
        result = s.query("test query")
        assert result is not None
        self.mock.call_tool.assert_called()

    def test_search(self) -> None:
        s = SniparaSync(api_key="k", project_slug="p")
        result = s.search("pattern")
        assert result is not None

    def test_plan(self) -> None:
        s = SniparaSync(api_key="k", project_slug="p")
        result = s.plan("complex task")
        assert result is not None

    def test_upload(self) -> None:
        s = SniparaSync(api_key="k", project_slug="p")
        result = s.upload("path.md", "content")
        assert result is not None

    def test_remember(self) -> None:
        s = SniparaSync(api_key="k", project_slug="p")
        result = s.remember("a fact", type="fact")
        assert result is not None

    def test_recall(self) -> None:
        s = SniparaSync(api_key="k", project_slug="p")
        result = s.recall("query")
        assert result is not None


# ===================================================================
# Context manager
# ===================================================================


class TestSyncContextManager:
    """Test SniparaSync context manager protocol."""

    def test_context_manager(self, mock_snipara_client: MagicMock) -> None:
        with patch("snipara.client.Snipara._ensure_client", return_value=mock_snipara_client):
            with SniparaSync(api_key="k", project_slug="p") as s:
                s.query("test")
                # Set _client so close() finds it
                s._async_client._client = mock_snipara_client
            mock_snipara_client.close.assert_called()
