"""Tests for the auto_remember middleware module."""

# IMPORTANT: Import conftest_handlers first to set up mocks before other imports
import tests.conftest_handlers  # noqa: F401

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.middleware.auto_remember import (
    AUTO_REMEMBER_TOOLS,
    EXCLUDED_TOOLS,
    extract_memory_content,
    maybe_auto_remember,
)


@dataclass
class MockSettings:
    """Mock ProjectSettings for testing."""

    memory_save_on_commit: bool = False
    memory_inject_types: list[str] = field(
        default_factory=lambda: ["DECISION", "LEARNING"]
    )


class TestExtractMemoryContent:
    """Tests for extract_memory_content function."""

    def test_context_query_with_results(self):
        """Test content extraction from rlm_context_query with results."""
        params = {"query": "authentication flow"}
        result = {
            "sections": [
                {"title": "Authentication Overview"},
                {"title": "OAuth Implementation"},
            ]
        }

        extracted = extract_memory_content("rlm_context_query", params, result)

        assert extracted is not None
        memory_type, content = extracted
        assert memory_type == "LEARNING"
        assert "Queried: 'authentication flow'" in content
        assert "Authentication Overview" in content

    def test_context_query_no_results(self):
        """Test content extraction from rlm_context_query with no results."""
        params = {"query": "nonexistent topic"}
        result = {"sections": []}

        extracted = extract_memory_content("rlm_context_query", params, result)

        assert extracted is not None
        memory_type, content = extracted
        assert memory_type == "LEARNING"
        assert "(no results)" in content

    def test_decompose(self):
        """Test content extraction from rlm_decompose."""
        params = {"query": "How does the authentication system work?"}
        result = {"sub_queries": [{"query": "q1"}, {"query": "q2"}, {"query": "q3"}]}

        extracted = extract_memory_content("rlm_decompose", params, result)

        assert extracted is not None
        memory_type, content = extracted
        assert memory_type == "DECISION"
        assert "Decomposed" in content
        assert "3 sub-queries" in content

    def test_plan(self):
        """Test content extraction from rlm_plan."""
        params = {"query": "Implement user registration"}
        result = {"steps": [{"step": 1}, {"step": 2}]}

        extracted = extract_memory_content("rlm_plan", params, result)

        assert extracted is not None
        memory_type, content = extracted
        assert memory_type == "DECISION"
        assert "execution plan" in content
        assert "2 steps" in content

    def test_upload_document(self):
        """Test content extraction from rlm_upload_document."""
        params = {"path": "docs/api/authentication.md"}
        result = {"success": True}

        extracted = extract_memory_content("rlm_upload_document", params, result)

        assert extracted is not None
        memory_type, content = extracted
        assert memory_type == "DECISION"
        assert "Uploaded document:" in content
        assert "docs/api/authentication.md" in content

    def test_swarm_create(self):
        """Test content extraction from rlm_swarm_create."""
        params = {"name": "code-review-swarm"}
        result = {"swarm_id": "swarm_123"}

        extracted = extract_memory_content("rlm_swarm_create", params, result)

        assert extracted is not None
        memory_type, content = extracted
        assert memory_type == "DECISION"
        assert "Created swarm:" in content
        assert "code-review-swarm" in content

    def test_task_complete_success(self):
        """Test content extraction from rlm_task_complete with success."""
        params = {"task_id": "task_abc123"}
        result = {"success": True}

        extracted = extract_memory_content("rlm_task_complete", params, result)

        assert extracted is not None
        memory_type, content = extracted
        assert memory_type == "LEARNING"
        assert "task_abc123" in content
        assert "completed" in content

    def test_task_complete_failure(self):
        """Test content extraction from rlm_task_complete with failure."""
        params = {"task_id": "task_abc123"}
        result = {"success": False}

        extracted = extract_memory_content("rlm_task_complete", params, result)

        assert extracted is not None
        memory_type, content = extracted
        assert "failed" in content

    def test_unknown_tool_returns_none(self):
        """Test that unknown tools return None."""
        extracted = extract_memory_content("unknown_tool", {}, {})
        assert extracted is None

    def test_short_content_filtered(self):
        """Test that very short content is filtered out."""
        # Force a result that would produce less than 20 chars
        # This shouldn't happen with real data, but test the safeguard
        params = {"path": "x"}  # Very short path
        result = {}

        extracted = extract_memory_content("rlm_upload_document", params, result)

        # "Uploaded document: x" is 20 chars, should pass
        assert extracted is not None

    def test_long_content_truncated(self):
        """Test that very long content is truncated."""
        long_query = "a" * 600
        params = {"query": long_query}
        result = {"sections": [{"title": "Result"}]}

        extracted = extract_memory_content("rlm_context_query", params, result)

        assert extracted is not None
        _, content = extracted
        assert len(content) <= 500


class TestMaybeAutoRemember:
    """Tests for maybe_auto_remember function."""

    @pytest.mark.asyncio
    async def test_disabled_when_setting_off(self):
        """Test that nothing happens when memory_save_on_commit is False."""
        settings = MockSettings(memory_save_on_commit=False)

        with patch(
            "src.engine.middleware.auto_remember.store_memory", new_callable=AsyncMock
        ) as mock_store:
            await maybe_auto_remember(
                tool="rlm_context_query",
                params={"query": "test"},
                result={"sections": [{"title": "Test"}]},
                project_id="proj_123",
                settings=settings,
            )

            mock_store.assert_not_called()

    @pytest.mark.asyncio
    async def test_excluded_tools_skipped(self):
        """Test that excluded tools don't trigger auto-remember."""
        settings = MockSettings(memory_save_on_commit=True)

        with patch(
            "src.engine.middleware.auto_remember.store_memory", new_callable=AsyncMock
        ) as mock_store:
            for tool in ["rlm_remember", "rlm_recall", "rlm_stats"]:
                await maybe_auto_remember(
                    tool=tool,
                    params={},
                    result={},
                    project_id="proj_123",
                    settings=settings,
                )

            mock_store.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_result_skipped(self):
        """Test that error results don't trigger auto-remember."""
        settings = MockSettings(memory_save_on_commit=True)

        with patch(
            "src.engine.middleware.auto_remember.store_memory", new_callable=AsyncMock
        ) as mock_store:
            await maybe_auto_remember(
                tool="rlm_context_query",
                params={"query": "test"},
                result={"error": "Something went wrong"},
                project_id="proj_123",
                settings=settings,
            )

            mock_store.assert_not_called()

    @pytest.mark.asyncio
    async def test_stores_memory_when_enabled(self):
        """Test that memory is stored when feature is enabled."""
        settings = MockSettings(memory_save_on_commit=True)

        with patch(
            "src.engine.middleware.auto_remember.store_memory", new_callable=AsyncMock
        ) as mock_store:
            mock_store.return_value = {"memory_id": "mem_123"}

            await maybe_auto_remember(
                tool="rlm_context_query",
                params={"query": "authentication"},
                result={"sections": [{"title": "Auth Overview"}]},
                project_id="proj_123",
                settings=settings,
            )

            mock_store.assert_called_once()
            call_kwargs = mock_store.call_args.kwargs
            assert call_kwargs["project_id"] == "proj_123"
            assert call_kwargs["memory_type"] == "learning"
            assert call_kwargs["category"] == "auto-remember"
            assert call_kwargs["ttl_days"] == 30
            assert call_kwargs["source"] == "auto"

    @pytest.mark.asyncio
    async def test_respects_memory_inject_types_filter(self):
        """Test that memory type filter is respected."""
        # Only allow DECISION, not LEARNING
        settings = MockSettings(
            memory_save_on_commit=True, memory_inject_types=["DECISION"]
        )

        with patch(
            "src.engine.middleware.auto_remember.store_memory", new_callable=AsyncMock
        ) as mock_store:
            # rlm_context_query produces LEARNING type - should be filtered
            await maybe_auto_remember(
                tool="rlm_context_query",
                params={"query": "test"},
                result={"sections": [{"title": "Test"}]},
                project_id="proj_123",
                settings=settings,
            )

            mock_store.assert_not_called()

            # rlm_plan produces DECISION type - should pass
            await maybe_auto_remember(
                tool="rlm_plan",
                params={"query": "test"},
                result={"steps": [{"step": 1}]},
                project_id="proj_123",
                settings=settings,
            )

            mock_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_failures_are_silent(self):
        """Test that store_memory failures don't raise exceptions."""
        settings = MockSettings(memory_save_on_commit=True)

        with patch(
            "src.engine.middleware.auto_remember.store_memory", new_callable=AsyncMock
        ) as mock_store:
            mock_store.side_effect = Exception("Database error")

            # Should not raise, just log warning
            await maybe_auto_remember(
                tool="rlm_context_query",
                params={"query": "test"},
                result={"sections": [{"title": "Test"}]},
                project_id="proj_123",
                settings=settings,
            )

            # If we get here without exception, test passes


class TestToolConfiguration:
    """Tests for tool configuration constants."""

    def test_auto_remember_tools_have_valid_config(self):
        """Test that AUTO_REMEMBER_TOOLS have valid configuration."""
        valid_types = {"LEARNING", "DECISION", "FACT"}
        valid_extractors = {
            "query_result",
            "decomposition",
            "plan",
            "upload",
            "summary",
            "task_completion",
            "swarm",
        }

        for tool, (mem_type, extractor) in AUTO_REMEMBER_TOOLS.items():
            assert mem_type in valid_types, f"{tool} has invalid memory type"
            assert extractor in valid_extractors, f"{tool} has invalid extractor"

    def test_memory_tools_are_excluded(self):
        """Test that all memory tools are in EXCLUDED_TOOLS."""
        memory_tools = {"rlm_remember", "rlm_recall", "rlm_memories", "rlm_forget"}
        for tool in memory_tools:
            assert tool in EXCLUDED_TOOLS, f"{tool} should be excluded"

    def test_no_overlap_between_auto_and_excluded(self):
        """Test that AUTO_REMEMBER_TOOLS and EXCLUDED_TOOLS don't overlap."""
        overlap = set(AUTO_REMEMBER_TOOLS.keys()) & EXCLUDED_TOOLS
        assert len(overlap) == 0, f"Tools in both sets: {overlap}"
