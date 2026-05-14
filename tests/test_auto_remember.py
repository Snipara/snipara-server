"""Tests for the auto_remember middleware module."""

# IMPORTANT: Import conftest_handlers first to set up mocks before other imports
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch

import pytest

import tests.conftest_handlers  # noqa: F401
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
    memory_capture_tool_results: bool = True
    memory_capture_failures: bool = False
    memory_deduplicate_before_write: bool = True
    memory_review_mode: str = "AUTO"
    memory_inject_types: list[str] = field(
        default_factory=lambda: ["DECISION", "LEARNING"]
    )
    memory_novelty_threshold: float = 0.92


class TestExtractMemoryContent:
    """Tests for extract_memory_content function."""

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

    def test_plan_is_not_auto_remembered(self):
        """Generic execution plans are operational receipts, not durable decisions."""
        params = {"query": "Implement user registration"}
        result = {"steps": [{"step": 1}, {"step": 2}]}

        extracted = extract_memory_content("rlm_plan", params, result)

        assert extracted is None

    def test_upload_document_is_not_auto_remembered(self):
        """Document uploads are indexed as documents and should not add memory receipts."""
        params = {"path": "docs/api/authentication.md"}
        result = {"success": True}

        extracted = extract_memory_content("rlm_upload_document", params, result)

        assert extracted is None

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

    def test_single_decomposition_filtered(self):
        """One-way decompositions are operational receipts, not durable decisions."""
        params = {"query": "Compare memory tooling"}
        result = {"sub_queries": [{"query": "Compare memory tooling"}]}

        extracted = extract_memory_content("rlm_decompose", params, result)

        assert extracted is None

    def test_long_content_truncated(self):
        """Test that very long content is truncated."""
        long_query = "a" * 600
        params = {"query": long_query}
        result = {"sub_queries": [{"query": "q1"}, {"query": "q2"}]}

        extracted = extract_memory_content("rlm_decompose", params, result)

        assert extracted is not None
        _, content = extracted
        assert len(content) <= 500


class TestMaybeAutoRemember:
    """Tests for maybe_auto_remember function."""

    @pytest.mark.asyncio
    async def test_disabled_when_setting_off(self):
        """Test that nothing happens when automatic tool capture is disabled."""
        settings = MockSettings(memory_capture_tool_results=False)

        with patch(
            "src.engine.middleware.auto_remember.remember_if_novel", new_callable=AsyncMock
        ) as mock_store:
            await maybe_auto_remember(
                tool="rlm_plan",
                params={"query": "test"},
                result={"steps": [{"step": 1}]},
                project_id="proj_123",
                settings=settings,
            )

            mock_store.assert_not_called()

    @pytest.mark.asyncio
    async def test_excluded_tools_skipped(self):
        """Test that excluded tools don't trigger auto-remember."""
        settings = MockSettings(memory_capture_tool_results=True)

        with patch(
            "src.engine.middleware.auto_remember.remember_if_novel", new_callable=AsyncMock
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
        settings = MockSettings(memory_capture_tool_results=True, memory_capture_failures=False)

        with patch(
            "src.engine.middleware.auto_remember.remember_if_novel", new_callable=AsyncMock
        ) as mock_store:
            await maybe_auto_remember(
                tool="rlm_plan",
                params={"query": "test"},
                result={"error": "Something went wrong"},
                project_id="proj_123",
                settings=settings,
            )

            mock_store.assert_not_called()

    @pytest.mark.asyncio
    async def test_stores_memory_when_enabled(self):
        """Test that memory is stored when feature is enabled."""
        settings = MockSettings(memory_capture_tool_results=True)

        with patch(
            "src.engine.middleware.auto_remember.remember_if_novel", new_callable=AsyncMock
        ) as mock_store:
            mock_store.return_value = {"memory_id": "mem_123"}

            await maybe_auto_remember(
                tool="rlm_decompose",
                params={"query": "authentication"},
                result={"sub_queries": [{"query": "q1"}, {"query": "q2"}]},
                project_id="proj_123",
                settings=settings,
            )

            mock_store.assert_called_once()
            call_kwargs = mock_store.call_args.kwargs
            assert call_kwargs["project_id"] == "proj_123"
            assert call_kwargs["novelty_threshold"] == 0.92

    @pytest.mark.asyncio
    async def test_null_novelty_threshold_falls_back_to_default(self):
        """Test that a null novelty threshold is normalized before remember_if_novel."""
        settings = MockSettings(memory_capture_tool_results=True, memory_novelty_threshold=None)

        with patch(
            "src.engine.middleware.auto_remember.remember_if_novel", new_callable=AsyncMock
        ) as mock_store:
            mock_store.return_value = {"memory_id": "mem_123"}

            await maybe_auto_remember(
                tool="rlm_decompose",
                params={"query": "authentication"},
                result={"sub_queries": [{"query": "q1"}, {"query": "q2"}]},
                project_id="proj_123",
                settings=settings,
            )

            call_kwargs = mock_store.call_args.kwargs
            assert call_kwargs["novelty_threshold"] == 0.92
            assert call_kwargs["memory_type"] == "decision"
            assert call_kwargs["category"] == "auto-remember"
            assert call_kwargs["ttl_days"] == 30
            assert call_kwargs["source"] == "auto"
            assert call_kwargs["novelty_threshold"] == 0.92

    @pytest.mark.asyncio
    async def test_respects_memory_inject_types_filter(self):
        """Test that memory type filter is respected."""
        # Only allow DECISION, not LEARNING
        settings = MockSettings(
            memory_capture_tool_results=True,
            memory_inject_types=["DECISION"],
        )

        with patch(
            "src.engine.middleware.auto_remember.remember_if_novel", new_callable=AsyncMock
        ) as mock_store:
            # rlm_task_complete produces LEARNING type - should be filtered
            await maybe_auto_remember(
                tool="rlm_task_complete",
                params={"task_id": "task_1"},
                result={"success": True},
                project_id="proj_123",
                settings=settings,
            )

            mock_store.assert_not_called()

            # rlm_decompose produces DECISION type when it has multiple sub-queries.
            await maybe_auto_remember(
                tool="rlm_decompose",
                params={"query": "test"},
                result={"sub_queries": [{"query": "q1"}, {"query": "q2"}]},
                project_id="proj_123",
                settings=settings,
            )

            mock_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_none_memory_inject_types_uses_default_allowlist(self):
        """Null project settings should not break auto-remember membership checks."""
        settings = MockSettings(memory_capture_tool_results=True, memory_inject_types=None)

        with patch(
            "src.engine.middleware.auto_remember.remember_if_novel", new_callable=AsyncMock
        ) as mock_store:
            mock_store.return_value = {"memory_id": "mem_123"}

            await maybe_auto_remember(
                tool="rlm_decompose",
                params={"query": "test"},
                result={"sub_queries": [{"query": "q1"}, {"query": "q2"}]},
                project_id="proj_123",
                settings=settings,
            )

            mock_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_failures_are_silent(self):
        """Test that remember_if_novel failures don't raise exceptions."""
        settings = MockSettings(memory_capture_tool_results=True)

        with patch(
            "src.engine.middleware.auto_remember.remember_if_novel", new_callable=AsyncMock
        ) as mock_store:
            mock_store.side_effect = Exception("Database error")

            # Should not raise, just log warning
            await maybe_auto_remember(
                tool="rlm_plan",
                params={"query": "test"},
                result={"steps": [{"step": 1}]},
                project_id="proj_123",
                settings=settings,
            )

            # If we get here without exception, test passes

    @pytest.mark.asyncio
    async def test_inbox_review_mode_marks_auto_captures_pending(self):
        """Automated captures should land in pending review when inbox mode is enabled."""
        settings = MockSettings(memory_capture_tool_results=True, memory_review_mode="INBOX")

        with (
            patch(
                "src.engine.middleware.auto_remember.remember_if_novel", new_callable=AsyncMock
            ) as mock_store,
            patch(
                "src.engine.middleware.auto_remember.resolve_review_status_for_source",
                return_value="PENDING",
            ),
        ):
            mock_store.return_value = {"memory_id": "mem_123"}

            await maybe_auto_remember(
                tool="rlm_decompose",
                params={"query": "authentication"},
                result={"sub_queries": [{"query": "q1"}, {"query": "q2"}]},
                project_id="proj_123",
                settings=settings,
            )

            assert mock_store.call_args.kwargs["review_status"] == "PENDING"
            assert mock_store.call_args.kwargs["source"] == "auto"

    @pytest.mark.asyncio
    async def test_can_capture_failures_when_enabled(self):
        """Failure captures should be persisted when the failure policy is enabled."""
        settings = MockSettings(memory_capture_tool_results=False, memory_capture_failures=True)

        with patch(
            "src.engine.middleware.auto_remember.remember_if_novel", new_callable=AsyncMock
        ) as mock_store:
            mock_store.return_value = {"memory_id": "mem_123"}

            await maybe_auto_remember(
                tool="rlm_plan",
                params={"query": "dangerous migration"},
                result={"error": "planning failed"},
                project_id="proj_123",
                settings=settings,
            )

            assert mock_store.call_args.kwargs["category"] == "auto-failure"
            assert mock_store.call_args.kwargs["source"] == "auto_failure"

    @pytest.mark.asyncio
    async def test_can_store_without_dedupe(self):
        """When dedupe is off, auto-remember should call store_memory directly."""
        settings = MockSettings(
            memory_capture_tool_results=True,
            memory_deduplicate_before_write=False,
        )

        with (
            patch(
                "src.engine.middleware.auto_remember.remember_if_novel", new_callable=AsyncMock
            ) as mock_remember,
            patch(
                "src.engine.middleware.auto_remember.store_memory", new_callable=AsyncMock
            ) as mock_store,
        ):
            mock_store.return_value = {"memory_id": "mem_456"}

            await maybe_auto_remember(
                tool="rlm_decompose",
                params={"query": "test"},
                result={"sub_queries": [{"query": "q1"}, {"query": "q2"}]},
                project_id="proj_123",
                settings=settings,
            )

            mock_remember.assert_not_called()
            mock_store.assert_called_once()


class TestToolConfiguration:
    """Tests for tool configuration constants."""

    def test_auto_remember_tools_have_valid_config(self):
        """Test that AUTO_REMEMBER_TOOLS have valid configuration."""
        valid_types = {"LEARNING", "DECISION", "FACT"}
        valid_extractors = {
            "decomposition",
            "summary",
            "task_completion",
            "swarm",
        }

        for tool, (mem_type, extractor) in AUTO_REMEMBER_TOOLS.items():
            assert mem_type in valid_types, f"{tool} has invalid memory type"
            assert extractor in valid_extractors, f"{tool} has invalid extractor"

    def test_memory_tools_are_excluded(self):
        """Test that all memory tools are in EXCLUDED_TOOLS."""
        memory_tools = {
            "rlm_remember",
            "rlm_recall",
            "rlm_memories",
            "rlm_memory_invalidate",
            "rlm_memory_supersede",
            "rlm_forget",
        }
        for tool in memory_tools:
            assert tool in EXCLUDED_TOOLS, f"{tool} should be excluded"

    def test_no_overlap_between_auto_and_excluded(self):
        """Test that AUTO_REMEMBER_TOOLS and EXCLUDED_TOOLS don't overlap."""
        overlap = set(AUTO_REMEMBER_TOOLS.keys()) & EXCLUDED_TOOLS
        assert len(overlap) == 0, f"Tools in both sets: {overlap}"
