"""Tests for the engine.handlers module.

These tests verify the extracted handler modules work correctly.
Uses mocks for database and service calls.
"""

# IMPORTANT: Import conftest_handlers first to set up mocks before other imports
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import tests.conftest_handlers  # noqa: F401
from src.engine.handlers import HandlerContext, count_tokens
from src.engine.handlers.htask import handle_htask_tree
from src.engine.handlers.memory import (
    handle_end_of_task_commit,
    handle_forget,
    handle_memories,
    handle_recall,
    handle_remember,
    handle_remember_if_novel,
)
from src.engine.handlers.session import (
    handle_clear_context,
    handle_context,
    handle_inject,
)
from src.engine.handlers.swarm import (
    handle_claim,
    handle_release,
    handle_swarm_create,
    handle_swarm_join,
)
from src.models import Plan, ProjectSettings


@pytest.fixture
def mock_context():
    """Create a mock handler context."""
    settings = MagicMock(spec=ProjectSettings)
    settings.max_tokens_per_query = 4000
    settings.search_mode = "hybrid"
    settings.include_summaries = False
    settings.auto_inject_context = False

    return HandlerContext(
        project_id="test_project_123",
        user_id="user_123",
        team_id="team_123",
        plan=Plan.PRO,
        access_level="ADMIN",
        settings=settings,
        session_context="",
        tips_shown=False,
        index=None,
        db=None,
    )


class TestCountTokens:
    """Tests for the count_tokens utility."""

    def test_count_tokens_empty(self):
        """Test empty string returns 0."""
        assert count_tokens("") == 0

    def test_count_tokens_short(self):
        """Test short text returns at least 1."""
        assert count_tokens("hi") >= 1

    def test_count_tokens_approximation(self):
        """Test token count is approximately chars/4."""
        text = "This is a test sentence with about forty characters."
        tokens = count_tokens(text)
        expected = len(text) // 4
        assert tokens == expected


class TestMemoryHandlers:
    """Tests for memory handlers."""

    @pytest.mark.asyncio
    async def test_remember_requires_content(self, mock_context):
        """Test that remember requires content."""
        result = await handle_remember({}, mock_context)
        assert result.data["error"] == "rlm_remember: missing required parameter 'text' (or 'content')"

    @pytest.mark.asyncio
    @patch("src.engine.handlers.memory.check_memory_limits")
    @patch("src.engine.handlers.memory.store_memory")
    async def test_remember_success(self, mock_store, mock_limits, mock_context):
        """Test successful memory storage."""
        mock_limits.return_value = (True, None)
        mock_store.return_value = {"id": "mem_123", "success": True}

        result = await handle_remember(
            {"content": "Test memory", "type": "fact"},
            mock_context,
        )

        assert result.data["success"] is True
        mock_store.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.engine.handlers.memory.check_memory_limits")
    async def test_remember_limit_exceeded(self, mock_limits, mock_context):
        """Test memory limit exceeded returns error."""
        mock_limits.return_value = (False, "Memory limit exceeded")

        result = await handle_remember(
            {"content": "Test memory"},
            mock_context,
        )

        assert "error" in result.data
        assert "upgrade_url" in result.data

    @pytest.mark.asyncio
    async def test_recall_requires_query(self, mock_context):
        """Test that recall requires query."""
        result = await handle_recall({}, mock_context)
        assert result.data["error"] == "rlm_recall: missing required parameter 'query'"

    @pytest.mark.asyncio
    @patch("src.engine.handlers.memory.semantic_recall")
    async def test_recall_success(self, mock_recall, mock_context):
        """Test successful memory recall."""
        mock_recall.return_value = {"memories": [], "total": 0}

        result = await handle_recall(
            {"query": "test query"},
            mock_context,
        )

        assert "memories" in result.data
        mock_recall.assert_called_once()
        assert mock_recall.await_args.kwargs["min_relevance"] == 0.6

    @pytest.mark.asyncio
    @patch("src.engine.handlers.memory.check_memory_limits")
    @patch("src.engine.handlers.memory.remember_if_novel")
    async def test_remember_if_novel_success(self, mock_remember_if_novel, mock_limits, mock_context):
        """Test successful novelty-gated memory storage."""
        mock_limits.return_value = (True, None)
        mock_remember_if_novel.return_value = {"stored": True, "memory_id": "mem_123"}

        result = await handle_remember_if_novel(
            {"text": "Novel memory", "type": "decision"},
            mock_context,
        )

        assert result.data["stored"] is True
        mock_remember_if_novel.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.engine.handlers.memory.list_memories")
    async def test_memories_list(self, mock_list, mock_context):
        """Test listing memories."""
        mock_list.return_value = {"memories": [], "total": 0}

        result = await handle_memories({}, mock_context)

        assert "memories" in result.data

    @pytest.mark.asyncio
    @patch("src.engine.handlers.memory.end_of_task_commit")
    async def test_end_of_task_commit_success(self, mock_end_of_task_commit, mock_context):
        """Test durable task commit handler."""
        mock_context.settings.memory_end_of_task_commit_enabled = True
        mock_end_of_task_commit.return_value = {"stored_count": 1, "skipped_count": 0}

        result = await handle_end_of_task_commit(
            {"summary": "We decided to standardize on project-scoped memory writes."},
            mock_context,
        )

        assert result.data["stored_count"] == 1
        mock_end_of_task_commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_forget_requires_filter(self, mock_context):
        """Test that forget requires at least one filter."""
        result = await handle_forget({}, mock_context)
        assert "error" in result.data
        assert "filter" in result.data["error"].lower()

    @pytest.mark.asyncio
    @patch("src.engine.handlers.memory.delete_memories")
    async def test_forget_by_id(self, mock_delete, mock_context):
        """Test deleting memory by ID."""
        mock_delete.return_value = {"deleted": 1}

        result = await handle_forget(
            {"memory_id": "mem_123"},
            mock_context,
        )

        assert result.data["deleted"] == 1


class TestHtaskHandlers:
    """Tests for hierarchical task handlers."""

    @pytest.mark.asyncio
    @patch("src.engine.handlers.htask.get_htask_tree", new_callable=AsyncMock)
    async def test_htask_tree_forwards_optional_task_id(self, mock_get_tree, mock_context):
        """The public task_id contract should reach the htask service."""
        mock_get_tree.return_value = {"success": True, "tree": {"id": "root-1"}}

        result = await handle_htask_tree(
            {
                "swarm_id": "swarm-1",
                "task_id": "root-1",
                "max_depth": 2,
                "include_archived": True,
            },
            mock_context,
        )

        assert result.data["success"] is True
        mock_get_tree.assert_awaited_once_with(
            swarm_id="swarm-1",
            task_id="root-1",
            max_depth=2,
            include_archived=True,
        )

    @pytest.mark.asyncio
    @patch("src.engine.handlers.htask.get_htask_tree", new_callable=AsyncMock)
    async def test_htask_tree_supports_all_roots_without_task_id(self, mock_get_tree, mock_context):
        """Omitting task_id should request all root tasks for the swarm."""
        mock_get_tree.return_value = {"success": True, "trees": [], "total_roots": 0}

        result = await handle_htask_tree({"swarm_id": "swarm-1"}, mock_context)

        assert result.data["success"] is True
        mock_get_tree.assert_awaited_once_with(
            swarm_id="swarm-1",
            task_id=None,
            max_depth=4,
            include_archived=False,
        )


class TestSwarmHandlers:
    """Tests for swarm handlers."""

    @pytest.mark.asyncio
    async def test_swarm_create_requires_name(self, mock_context):
        """Test that swarm_create requires name."""
        result = await handle_swarm_create({}, mock_context)
        assert result.data["error"] == "rlm_swarm_create: missing required parameter 'name'"

    @pytest.mark.asyncio
    @patch("src.engine.handlers.swarm.create_swarm")
    async def test_swarm_create_success(self, mock_create, mock_context):
        """Test successful swarm creation."""
        mock_create.return_value = {"id": "swarm_123", "name": "test_swarm"}

        result = await handle_swarm_create(
            {"name": "test_swarm"},
            mock_context,
        )

        assert result.data["id"] == "swarm_123"

    @pytest.mark.asyncio
    async def test_swarm_join_requires_ids(self, mock_context):
        """Test that swarm_join requires swarm_id and agent_id."""
        result = await handle_swarm_join({}, mock_context)
        assert "error" in result.data
        assert "swarm_id" in result.data["error"]

    @pytest.mark.asyncio
    @patch("src.engine.handlers.swarm.join_swarm")
    async def test_swarm_join_success(self, mock_join, mock_context):
        """Test successful swarm join."""
        mock_join.return_value = {"joined": True}

        result = await handle_swarm_join(
            {"swarm_id": "swarm_123", "agent_id": "agent_456"},
            mock_context,
        )

        assert result.data["joined"] is True

    @pytest.mark.asyncio
    async def test_claim_requires_all_params(self, mock_context):
        """Test that claim requires all required parameters."""
        result = await handle_claim({}, mock_context)
        assert "error" in result.data

        result = await handle_claim(
            {"swarm_id": "s", "agent_id": "a"},
            mock_context,
        )
        assert "error" in result.data

    @pytest.mark.asyncio
    @patch("src.engine.handlers.swarm.acquire_claim")
    async def test_claim_success(self, mock_acquire, mock_context):
        """Test successful resource claim."""
        mock_acquire.return_value = {"claim_id": "claim_123"}

        result = await handle_claim(
            {
                "swarm_id": "swarm_123",
                "agent_id": "agent_456",
                "resource_type": "file",
                "resource_id": "/path/to/file",
            },
            mock_context,
        )

        assert result.data["claim_id"] == "claim_123"

    @pytest.mark.asyncio
    async def test_release_requires_ids(self, mock_context):
        """Test that release requires swarm_id and agent_id."""
        result = await handle_release({}, mock_context)
        assert "error" in result.data

    @pytest.mark.asyncio
    @patch("src.engine.handlers.swarm.release_claim")
    async def test_release_success(self, mock_release, mock_context):
        """Test successful resource release."""
        mock_release.return_value = {"released": True}

        result = await handle_release(
            {"swarm_id": "swarm_123", "agent_id": "agent_456", "claim_id": "claim_789"},
            mock_context,
        )

        assert result.data["released"] is True


class TestSessionHandlers:
    """Tests for session handlers."""

    @pytest.mark.asyncio
    async def test_inject_requires_context(self, mock_context):
        """Test that inject requires context string."""
        set_callback = MagicMock()
        result = await handle_inject({}, mock_context, set_callback)
        assert result.data["error"] == "rlm_inject: missing required parameter 'context'"

    @pytest.mark.asyncio
    async def test_inject_success(self, mock_context):
        """Test successful context injection."""
        set_callback = MagicMock()

        result = await handle_inject(
            {"context": "Test context"},
            mock_context,
            set_callback,
        )

        assert result.data["success"] is True
        set_callback.assert_called_once_with("Test context")

    @pytest.mark.asyncio
    async def test_inject_append(self, mock_context):
        """Test context append mode."""
        mock_context.session_context = "Existing context"
        set_callback = MagicMock()

        result = await handle_inject(
            {"context": "New context", "append": True},
            mock_context,
            set_callback,
        )

        assert result.data["success"] is True
        set_callback.assert_called_once()
        call_arg = set_callback.call_args[0][0]
        assert "Existing context" in call_arg
        assert "New context" in call_arg

    @pytest.mark.asyncio
    async def test_context_returns_current(self, mock_context):
        """Test getting current context."""
        mock_context.session_context = "Current session context"

        result = await handle_context({}, mock_context)

        assert result.data["context"] == "Current session context"
        assert result.data["token_count"] > 0

    @pytest.mark.asyncio
    async def test_clear_context_success(self, mock_context):
        """Test clearing context."""
        mock_context.session_context = "Context to clear"
        set_callback = MagicMock()

        result = await handle_clear_context({}, mock_context, set_callback)

        assert result.data["success"] is True
        set_callback.assert_called_once_with("")


class TestHandlerContext:
    """Tests for HandlerContext dataclass."""

    def test_context_creation(self, mock_context):
        """Test context can be created with all fields."""
        assert mock_context.project_id == "test_project_123"
        assert mock_context.plan == Plan.PRO
        assert mock_context.access_level == "ADMIN"

    def test_context_fields_accessible(self, mock_context):
        """Test all context fields are accessible."""
        assert hasattr(mock_context, "project_id")
        assert hasattr(mock_context, "user_id")
        assert hasattr(mock_context, "team_id")
        assert hasattr(mock_context, "plan")
        assert hasattr(mock_context, "access_level")
        assert hasattr(mock_context, "settings")
        assert hasattr(mock_context, "session_context")
        assert hasattr(mock_context, "tips_shown")
        assert hasattr(mock_context, "index")
        assert hasattr(mock_context, "db")
