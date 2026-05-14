"""Tests for task handler routing to htask compatibility adapters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# IMPORTANT: Import conftest_handlers first to set up mocks before handler imports.
import tests.conftest_handlers  # noqa: F401
from src.engine.handlers import HandlerContext
from src.engine.handlers.swarm import handle_task_create
from src.models import Plan, ProjectSettings


@pytest.fixture
def mock_context():
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


@pytest.mark.asyncio
@patch("src.engine.handlers.swarm.create_task_as_htask")
async def test_task_create_routes_to_htask_adapter(mock_create, mock_context):
    """rlm_task_create should write through the htask adapter."""
    mock_create.return_value = {
        "success": True,
        "task_id": "htask-1",
        "canonical_surface": "htask",
    }

    result = await handle_task_create(
        {
            "swarm_id": "swarm-1",
            "agent_id": "coordinator",
            "title": "Review deploy",
            "priority": 2,
            "for_agent_id": "agent-a",
        },
        mock_context,
    )

    assert result.data["canonical_surface"] == "htask"
    mock_create.assert_awaited_once()
    assert mock_create.await_args.kwargs["swarm_id"] == "swarm-1"
    assert mock_create.await_args.kwargs["agent_id"] == "coordinator"
    assert mock_create.await_args.kwargs["for_agent_id"] == "agent-a"
