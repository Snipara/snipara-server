"""Tests for smart routing decisions, including structural code queries."""

from src.services.query_router import QueryMode, assess_query_complexity, route_query


def test_route_query_recommends_code_callers_for_structural_lookup():
    decision = route_query("who calls src.rlm_engine.RLMEngine._handle_context_query?")

    assert decision.mode == QueryMode.DIRECT
    assert decision.recommended_tool == "rlm_code_callers"
    assert decision.recommended_tool_arguments == {
        "qualified_name": "src.rlm_engine.RLMEngine._handle_context_query",
        "depth": 1,
        "limit": 50,
    }


def test_route_query_recommends_code_imports_for_file_path():
    decision = route_query("what does src/services/query_router.py import?")

    assert decision.mode == QueryMode.DIRECT
    assert decision.recommended_tool == "rlm_code_imports"
    assert decision.recommended_tool_arguments == {
        "file_path": "src/services/query_router.py",
        "direction": "out",
        "limit": 50,
    }


def test_route_query_recommends_shortest_path_for_symbol_pair():
    decision = route_query(
        "path from src.rlm_engine.RLMEngine.run to src.rlm_engine.helper"
    )

    assert decision.mode == QueryMode.DIRECT
    assert decision.recommended_tool == "rlm_code_shortest_path"
    assert decision.recommended_tool_arguments == {
        "from": "src.rlm_engine.RLMEngine.run",
        "to": "src.rlm_engine.helper",
        "max_hops": 6,
    }


def test_route_query_keeps_code_generation_in_rlm_mode():
    decision = route_query("implement OAuth token refresh flow for the FastAPI backend")

    assert decision.mode == QueryMode.RLM_RUNTIME
    assert decision.recommended_tool is None


def test_assess_query_complexity_surfaces_tool_hint():
    analysis = assess_query_complexity(
        "neighbors of src.rlm_engine.RLMEngine._handle_context_query"
    )

    assert analysis["recommended_mode"] == "direct"
    assert analysis["recommended_tool"] == "rlm_code_neighbors"
    assert analysis["recommended_tool_arguments"]["depth"] == 2


def test_route_query_keeps_rlm_mode_but_adds_graph_hint_for_mixed_symbol_query():
    decision = route_query(
        "Explain how src.rlm_engine.RLMEngine._handle_context_query works during request handling"
    )

    assert decision.mode == QueryMode.RLM_RUNTIME
    assert decision.recommended_tool == "rlm_code_neighbors"
    assert decision.recommended_tool_arguments == {
        "qualified_name": "src.rlm_engine.RLMEngine._handle_context_query",
        "depth": 2,
        "limit": 24,
    }
