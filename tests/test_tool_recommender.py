"""Tests for high-level tool recommendations."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "src/services/tool_recommender.py"
SPEC = spec_from_file_location("test_tool_recommender_module", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
recommend_tools = MODULE.recommend_tools


def test_recommend_tools_prefers_end_of_task_memory_workflow():
    """High-level durable memory requests should prefer orchestration tools."""
    recommendations = recommend_tools(
        query="Persist durable knowledge at the end of a task without duplicates",
        limit=5,
        include_admin=True,
    )

    tools = [item["tool"] for item in recommendations]

    assert tools[0] == "rlm_end_of_task_commit"
    assert "rlm_remember_if_novel" in tools[:3]
    assert "rlm_agent_profile_get" not in tools[:5]
    assert "rlm_remember" not in tools[:2]


def test_recommend_tools_prefers_session_bootstrap_tools():
    """Session bootstrap requests should surface auto-load memory tools first."""
    recommendations = recommend_tools(
        query="Bootstrap session memory on resume and load workspace profile automatically",
        limit=5,
        include_team=True,
    )

    tools = [item["tool"] for item in recommendations]

    assert tools[0] == "rlm_session_memories"
    assert "rlm_tenant_profile_get" in tools[:3]
    assert "rlm_remember" not in tools[:3]


def test_recommend_tools_prefers_daily_brief_for_active_constraints():
    """Daily brief intent should prefer the explicit brief tool."""
    recommendations = recommend_tools(
        query="Generate a daily brief of active constraints and pending todos",
        limit=3,
    )

    assert recommendations[0]["tool"] == "rlm_memory_daily_brief"


def test_recommend_tools_prefers_reindex_for_low_coverage():
    """Index maintenance queries should surface rlm_reindex first."""
    recommendations = recommend_tools(
        query="Index coverage is low and many documents are missing chunks, how do I reindex the project?",
        limit=3,
        include_admin=True,
    )

    assert recommendations[0]["tool"] == "rlm_reindex"


def test_recommend_tools_prefers_fast_context_retry_after_timeout():
    """Timeout recovery should steer back to Snipara before local grep."""
    recommendations = recommend_tools(
        query="rlm_context_query timed out, retry smarter before fallback to rg",
        limit=4,
        include_team=True,
        include_admin=True,
    )

    tools = [item["tool"] for item in recommendations]

    assert tools[0] == "rlm_context_query"
    assert "rlm_search" in tools[:3]
    assert any(tool.startswith("rlm_code_") for tool in tools)


def test_recommend_tools_prefers_workflow_orchestration_for_roadmap():
    """Roadmap/workflow requests should prefer orchestration over raw primitives."""
    recommendations = recommend_tools(
        query="Plan roadmap workflow for MCP contract deployment validation and memory automation tasks",
        limit=8,
        include_team=True,
        include_admin=True,
    )

    tools = [item["tool"] for item in recommendations]

    assert tools[0] == "rlm_plan"
    assert "rlm_htask_create_feature" in tools[:3]
    assert "rlm_htask_recommend_batch" in tools[:4]
    assert "rlm_orchestrate" in tools[:8] or "rlm_memory_health" in tools[:8]
    assert "rlm_search" not in tools[:5]
    assert "rlm_read" not in tools[:5]
