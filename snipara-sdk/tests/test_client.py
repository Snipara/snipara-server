"""Tests for snipara.client — async Snipara SDK client.

Tests cover:
- Client initialization and config resolution
- Lazy SniparaClient instantiation
- All SDK methods (query, search, plan, multi_query, shared_context)
- Document management (upload, sync_documents)
- Agent memory (remember, recall)
- Code execution (execute) with rlm-runtime import handling
- Auto-feedback loop (run)
- Context manager lifecycle (aenter/aexit)
- Error handling for missing API key / project slug
- Config parameter forwarding (max_tokens, search_mode)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from snipara.client import (
    ExecuteResult,
    MemoryResult,
    PlanResult,
    QueryResult,
    RunResult,
    SearchResult,
    Snipara,
    SyncResult,
    UploadResult,
)
from snipara.config import SniparaConfig

# ===================================================================
# Result dataclasses
# ===================================================================


class TestResultTypes:
    """Verify all result dataclass constructors and properties."""

    def test_query_result_defaults(self) -> None:
        r = QueryResult()
        assert r.sections == []
        assert r.total_tokens == 0
        assert r.suggestions == []
        assert r.raw == {}

    def test_search_result(self) -> None:
        r = SearchResult(matches=[{"line": 1}], total_matches=1)
        assert r.total_matches == 1

    def test_plan_result(self) -> None:
        r = PlanResult(steps=[{"query": "step 1"}], total_tokens=500)
        assert len(r.steps) == 1

    def test_memory_result(self) -> None:
        r = MemoryResult(memory_id="mem_123")
        assert r.memory_id == "mem_123"

    def test_upload_result(self) -> None:
        r = UploadResult(path="docs/new.md", status="created")
        assert r.status == "created"

    def test_sync_result(self) -> None:
        r = SyncResult(created=2, updated=1, deleted=0)
        assert r.created == 2

    def test_execute_result_summary(self) -> None:
        r = ExecuteResult(response="Line one\nLine two\nLine three")
        assert r.summary == "Line one"
        assert len(r.summary) <= 200

    def test_execute_result_empty_summary(self) -> None:
        r = ExecuteResult(response="")
        assert r.summary == ""

    def test_run_result(self) -> None:
        r = RunResult()
        assert r.context is None
        assert r.execution is None
        assert r.memories_stored == []


# ===================================================================
# Client initialization
# ===================================================================


class TestClientInit:
    """Test Snipara client initialization and config handling."""

    def test_init_with_explicit_params(self) -> None:
        s = Snipara(
            api_key="rlm_explicit",
            project_slug="explicit-proj",
            api_url="https://custom.api.com",
        )
        assert s._api_key == "rlm_explicit"
        assert s._project_slug == "explicit-proj"
        assert s._api_url == "https://custom.api.com"

    def test_init_from_config(self) -> None:
        cfg = SniparaConfig()
        cfg.project.api_key = "rlm_from_config"
        cfg.project.slug = "config-proj"
        cfg.project.api_url = "https://config.api.com"
        s = Snipara(config=cfg)
        assert s._api_key == "rlm_from_config"
        assert s._project_slug == "config-proj"
        assert s._api_url == "https://config.api.com"

    def test_explicit_params_override_config(self) -> None:
        cfg = SniparaConfig()
        cfg.project.api_key = "rlm_config_key"
        cfg.project.slug = "config-slug"
        s = Snipara(api_key="rlm_override", project_slug="override-slug", config=cfg)
        assert s._api_key == "rlm_override"
        assert s._project_slug == "override-slug"

    def test_client_lazy_init(self) -> None:
        s = Snipara(api_key="rlm_test", project_slug="test")
        assert s._client is None  # Not initialized yet

    def test_config_property(self) -> None:
        cfg = SniparaConfig()
        s = Snipara(config=cfg)
        assert s.config is cfg


# ===================================================================
# Client validation
# ===================================================================


class TestClientValidation:
    """Test error handling for missing required configuration."""

    def test_missing_api_key_raises(self) -> None:
        # Use explicit clean config to prevent loading from real files
        cfg = SniparaConfig()
        cfg.project.slug = "test"
        s = Snipara(config=cfg)
        with pytest.raises(ValueError, match="No API key"):
            s._ensure_client()

    def test_missing_project_slug_raises(self) -> None:
        cfg = SniparaConfig()
        cfg.project.api_key = "rlm_test"
        s = Snipara(config=cfg)
        with pytest.raises(ValueError, match="No project slug"):
            s._ensure_client()


# ===================================================================
# Context methods
# ===================================================================


class TestContextMethods:
    """Test context optimization methods with mocked SniparaClient."""

    @pytest.fixture(autouse=True)
    def _patch_client(self, mock_snipara_client: MagicMock) -> Any:
        """Patch SniparaClient import to return our mock."""
        with patch("snipara.client.Snipara._ensure_client", return_value=mock_snipara_client):
            self.mock = mock_snipara_client
            yield

    @pytest.mark.asyncio
    async def test_query_basic(self) -> None:
        async with Snipara(api_key="k", project_slug="p") as s:
            await s.query("how does auth work?")
        self.mock.call_tool.assert_called_once()
        call_args = self.mock.call_tool.call_args
        assert call_args[0][0] == "rlm_context_query"
        assert call_args[0][1]["query"] == "how does auth work?"

    @pytest.mark.asyncio
    async def test_query_with_max_tokens(self) -> None:
        async with Snipara(api_key="k", project_slug="p") as s:
            await s.query("test", max_tokens=8000)
        params = self.mock.call_tool.call_args[0][1]
        assert params["max_tokens"] == 8000

    @pytest.mark.asyncio
    async def test_query_with_search_mode(self) -> None:
        async with Snipara(api_key="k", project_slug="p") as s:
            await s.query("test", search_mode="keyword")
        params = self.mock.call_tool.call_args[0][1]
        assert params["search_mode"] == "keyword"

    @pytest.mark.asyncio
    async def test_query_config_max_tokens_forwarded(self) -> None:
        """Non-default config max_tokens should be forwarded automatically."""
        cfg = SniparaConfig()
        cfg.project.api_key = "k"
        cfg.project.slug = "p"
        cfg.context.max_tokens = 6000  # Non-default
        async with Snipara(config=cfg) as s:
            await s.query("test")
        params = self.mock.call_tool.call_args[0][1]
        assert params["max_tokens"] == 6000

    @pytest.mark.asyncio
    async def test_search(self) -> None:
        async with Snipara(api_key="k", project_slug="p") as s:
            await s.search("rate.limit", max_results=10)
        call_args = self.mock.call_tool.call_args
        assert call_args[0][0] == "rlm_search"
        assert call_args[0][1]["pattern"] == "rate.limit"
        assert call_args[0][1]["max_results"] == 10

    @pytest.mark.asyncio
    async def test_plan(self) -> None:
        async with Snipara(api_key="k", project_slug="p") as s:
            await s.plan("implement OAuth2", strategy="depth_first", max_tokens=20000)
        call_args = self.mock.call_tool.call_args
        assert call_args[0][0] == "rlm_plan"
        assert call_args[0][1]["strategy"] == "depth_first"
        assert call_args[0][1]["max_tokens"] == 20000

    @pytest.mark.asyncio
    async def test_multi_query(self) -> None:
        async with Snipara(api_key="k", project_slug="p") as s:
            await s.multi_query(["q1", "q2"], max_tokens=10000)
        call_args = self.mock.call_tool.call_args
        assert call_args[0][0] == "rlm_multi_query"
        queries = call_args[0][1]["queries"]
        assert len(queries) == 2
        assert queries[0] == {"query": "q1"}

    @pytest.mark.asyncio
    async def test_shared_context(self) -> None:
        async with Snipara(api_key="k", project_slug="p") as s:
            await s.shared_context(categories=["MANDATORY"], max_tokens=3000)
        call_args = self.mock.call_tool.call_args
        assert call_args[0][0] == "rlm_shared_context"
        assert call_args[0][1]["categories"] == ["MANDATORY"]


# ===================================================================
# Document methods
# ===================================================================


class TestDocumentMethods:
    """Test document upload and sync methods."""

    @pytest.fixture(autouse=True)
    def _patch_client(self, mock_snipara_client: MagicMock) -> Any:
        with patch("snipara.client.Snipara._ensure_client", return_value=mock_snipara_client):
            self.mock = mock_snipara_client
            yield

    @pytest.mark.asyncio
    async def test_upload(self) -> None:
        async with Snipara(api_key="k", project_slug="p") as s:
            await s.upload("docs/new.md", content="# New Doc")
        call_args = self.mock.call_tool.call_args
        assert call_args[0][0] == "rlm_upload_document"
        assert call_args[0][1]["path"] == "docs/new.md"
        assert call_args[0][1]["content"] == "# New Doc"

    @pytest.mark.asyncio
    async def test_sync_documents(self) -> None:
        docs = [
            {"path": "docs/a.md", "content": "# A"},
            {"path": "docs/b.md", "content": "# B"},
        ]
        async with Snipara(api_key="k", project_slug="p") as s:
            await s.sync_documents(docs, delete_missing=True)
        call_args = self.mock.call_tool.call_args
        assert call_args[0][0] == "rlm_sync_documents"
        assert call_args[0][1]["delete_missing"] is True
        assert len(call_args[0][1]["documents"]) == 2


# ===================================================================
# Memory methods
# ===================================================================


class TestMemoryMethods:
    """Test agent memory (remember/recall) methods."""

    @pytest.fixture(autouse=True)
    def _patch_client(self, mock_snipara_client: MagicMock) -> Any:
        with patch("snipara.client.Snipara._ensure_client", return_value=mock_snipara_client):
            self.mock = mock_snipara_client
            yield

    @pytest.mark.asyncio
    async def test_remember(self) -> None:
        async with Snipara(api_key="k", project_slug="p") as s:
            await s.remember(
                "Chose JWT for auth",
                type="decision",
                scope="project",
                category="architecture",
                ttl_days=90,
            )
        call_args = self.mock.call_tool.call_args
        assert call_args[0][0] == "rlm_remember"
        params = call_args[0][1]
        assert params["content"] == "Chose JWT for auth"
        assert params["type"] == "decision"
        assert params["category"] == "architecture"
        assert params["ttl_days"] == 90

    @pytest.mark.asyncio
    async def test_recall(self) -> None:
        async with Snipara(api_key="k", project_slug="p") as s:
            await s.recall("auth decisions", limit=10, min_relevance=0.7, type="decision")
        call_args = self.mock.call_tool.call_args
        assert call_args[0][0] == "rlm_recall"
        params = call_args[0][1]
        assert params["query"] == "auth decisions"
        assert params["limit"] == 10
        assert params["type"] == "decision"


# ===================================================================
# Execution methods
# ===================================================================


class TestExecutionMethods:
    """Test rlm-runtime execution integration."""

    @pytest.mark.asyncio
    async def test_execute_import_error(self) -> None:
        """execute() should raise helpful ImportError when rlm-runtime missing."""
        with patch.dict("sys.modules", {"rlm": None}):
            s = Snipara(api_key="k", project_slug="p")
            with pytest.raises(ImportError, match="rlm-runtime is required"):
                await s.execute("test task")

    @pytest.mark.asyncio
    async def test_execute_with_context(self) -> None:
        """execute() should prepend context to the prompt."""
        mock_rlm_class = MagicMock()
        mock_rlm_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.response = "Done!"
        mock_result.trajectory = []
        mock_result.total_tokens = 100
        mock_result.total_cost = 0.01
        mock_result.duration_ms = 500
        mock_rlm_instance.completion = AsyncMock(return_value=mock_result)
        mock_rlm_class.return_value = mock_rlm_instance

        with patch.dict("sys.modules", {"rlm": MagicMock(RLM=mock_rlm_class)}):
            cfg = SniparaConfig()
            cfg.project.api_key = "k"
            cfg.project.slug = "p"
            s = Snipara(config=cfg)
            result = await s.execute(
                "implement auth",
                context={"sections": [{"content": "JWT docs here"}]},
            )
            assert isinstance(result, ExecuteResult)
            assert result.response == "Done!"
            # Verify context was prepended
            prompt = mock_rlm_instance.completion.call_args[0][0]
            assert "JWT docs here" in prompt
            assert "implement auth" in prompt


# ===================================================================
# Auto-feedback loop
# ===================================================================


class TestAutoFeedbackLoop:
    """Test the run() method: query → execute → remember."""

    @pytest.mark.asyncio
    async def test_run_full_loop(self) -> None:
        """run() should chain query, execute, and remember."""
        mock_client = MagicMock()
        query_response = {
            "sections": [{"content": "Relevant context"}],
            "total_tokens": 500,
        }
        remember_response = {"memory_id": "mem_abc"}

        call_count = 0

        async def _call_tool(tool_name: str, params: dict) -> Any:
            nonlocal call_count
            call_count += 1
            if tool_name == "rlm_context_query":
                return query_response
            elif tool_name == "rlm_remember":
                return remember_response
            return {}

        mock_client.call_tool = AsyncMock(side_effect=_call_tool)
        mock_client.close = AsyncMock()

        # Mock execute
        mock_rlm_class = MagicMock()
        mock_rlm_instance = MagicMock()
        mock_exec_result = MagicMock()
        mock_exec_result.response = "Fixed the bug"
        mock_exec_result.trajectory = []
        mock_exec_result.total_tokens = 200
        mock_exec_result.total_cost = 0.02
        mock_exec_result.duration_ms = 1000
        mock_rlm_instance.completion = AsyncMock(return_value=mock_exec_result)
        mock_rlm_class.return_value = mock_rlm_instance

        with (
            patch("snipara.client.Snipara._ensure_client", return_value=mock_client),
            patch.dict("sys.modules", {"rlm": MagicMock(RLM=mock_rlm_class)}),
        ):
            cfg = SniparaConfig()
            cfg.project.api_key = "k"
            cfg.project.slug = "p"
            s = Snipara(config=cfg)
            result = await s.run("fix rate limiting bug")

            assert isinstance(result, RunResult)
            assert result.context is not None
            assert result.context.total_tokens == 500
            assert result.execution is not None
            assert result.execution.response == "Fixed the bug"
            assert len(result.memories_stored) == 1
            assert result.memories_stored[0] == "mem_abc"


# ===================================================================
# Lifecycle
# ===================================================================


class TestLifecycle:
    """Test context manager and close behavior."""

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_snipara_client: MagicMock) -> None:
        with patch("snipara.client.Snipara._ensure_client", return_value=mock_snipara_client):
            async with Snipara(api_key="k", project_slug="p") as s:
                await s.query("test")
                # Manually set _client so close() finds it
                s._client = mock_snipara_client
            # close() should have been called via __aexit__
            mock_snipara_client.close.assert_called()

    @pytest.mark.asyncio
    async def test_close_without_init(self) -> None:
        """Closing a never-used client should not error."""
        s = Snipara(api_key="k", project_slug="p")
        await s.close()  # Should not raise
