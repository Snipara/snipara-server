"""Tests for implementation-aware rlm_plan output."""

import pytest

from src.engine.core.document import DocumentationIndex, Section
from src.models import Plan
from src.rlm_engine import RLMEngine


@pytest.mark.asyncio
async def test_plan_adds_repo_work_hints_for_implementation_tasks():
    """Repo implementation plans should expose likely targets and workflow tools."""
    engine = RLMEngine("test-project", plan=Plan.TEAM)

    result = await engine._handle_plan(
        {
            "query": (
                "Plan repo implementation work for MCP memory workflow contract tests "
                "and deployment validation"
            )
        }
    )

    data = result.data
    actions = [step["action"] for step in data["steps"]]

    assert "implementation_map" in actions
    assert "tool_workflow" in actions
    assert "apps/mcp-server/src/services/agent_memory.py" in data["likely_files"]
    assert "apps/mcp-server/tests/mcp_contract_surface.py" in data["likely_files"]
    assert "agent memory lifecycle" in data["likely_modules"]
    assert "MCP client and remote endpoint contract" in data["likely_modules"]
    assert "rlm_memory_health" in data["recommended_tools"]
    assert "rlm_htask_recommend_batch" in data["recommended_tools"]
    assert data["blocking_work"]
    assert data["sidecar_work"]


@pytest.mark.asyncio
async def test_decompose_preserves_roadmap_clauses_when_index_terms_are_sparse():
    """Roadmap prompts should not collapse to one generic matching keyword."""
    engine = RLMEngine("test-project", plan=Plan.TEAM)
    section = Section(
        id="roadmap",
        title="Roadmap Break",
        content="Roadmap break planning overview.",
        start_line=1,
        end_line=3,
        level=1,
    )
    engine.index = DocumentationIndex(
        files=["docs/roadmap.md"],
        lines=section.content.splitlines(),
        sections=[section],
        file_boundaries={"docs/roadmap.md": (0, 3)},
    )

    result = await engine._handle_decompose(
        {
            "query": (
                "Snipara GitHub-native agent-agnostic memory compiler roadmap: "
                "break into implementable phases covering GitHub ingestion/write-back, "
                "memory governance, agent adapters, Snipara workflow/RLM Runtime, "
                "evaluation harness, health observability, enterprise security, and launch demo."
            )
        }
    )

    queries = [sub_query["query"] for sub_query in result.data["sub_queries"]]

    assert len(queries) >= 5
    assert any("memory governance" in query.lower() for query in queries)
    assert any("agent adapters" in query.lower() for query in queries)
    assert any("enterprise security" in query.lower() for query in queries)
