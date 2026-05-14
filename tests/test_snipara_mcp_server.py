"""Tests for snipara-mcp session bootstrap behavior."""

import httpx
import pytest
import snipara_mcp.server as mcp_server

from src.mcp.tool_defs import MCP_TOOL_DEFINITIONS, TOOL_DEFINITIONS
from tests.mcp_contract_surface import (
    CODE_GRAPH_TOOL_SURFACE,
    ESSENTIAL_TOOL_SURFACE,
    HTASK_CRITICAL_TOOL_SURFACE,
    INDEX_TOOL_SURFACE,
)


@pytest.fixture
def reset_mcp_server_state(monkeypatch):
    """Reset global state between tests."""
    monkeypatch.setattr(mcp_server, "_session_context", "")
    monkeypatch.setattr(mcp_server, "_session_initialized", False)
    monkeypatch.setattr(mcp_server, "_session_last_bootstrap_at", 0.0)
    monkeypatch.setattr(mcp_server, "_shared_context_bootstrapped", False)
    monkeypatch.setattr(mcp_server, "_settings_cache", {})
    monkeypatch.setattr(mcp_server, "_settings_cache_time", 0.0)
    yield mcp_server


@pytest.mark.asyncio
async def test_list_tools_contains_critical_workflow_surface():
    """The MCP client should expose the critical workflow tools we rely on."""
    backend_tools = {tool["name"] for tool in TOOL_DEFINITIONS}
    listed_tools = {tool.name for tool in await mcp_server.list_tools()}

    assert ESSENTIAL_TOOL_SURFACE <= backend_tools
    assert ESSENTIAL_TOOL_SURFACE <= listed_tools


@pytest.mark.asyncio
async def test_list_tools_contains_code_graph_surface():
    """The MCP client should expose the code graph tools end to end."""
    backend_tools = {tool["name"] for tool in TOOL_DEFINITIONS}
    listed_tools = {tool.name for tool in await mcp_server.list_tools()}

    assert CODE_GRAPH_TOOL_SURFACE <= backend_tools
    assert CODE_GRAPH_TOOL_SURFACE <= listed_tools


@pytest.mark.asyncio
async def test_list_tools_contains_index_maintenance_surface():
    """The MCP client should expose the index maintenance tools end to end."""
    backend_tools = {tool["name"] for tool in TOOL_DEFINITIONS}
    listed_tools = {tool.name for tool in await mcp_server.list_tools()}

    assert INDEX_TOOL_SURFACE <= backend_tools
    assert INDEX_TOOL_SURFACE <= listed_tools


@pytest.mark.asyncio
async def test_list_tools_contains_htask_critical_surface():
    """The MCP client should expose critical hierarchical task tools end to end."""
    backend_tools = {tool["name"] for tool in TOOL_DEFINITIONS}
    listed_tools = {tool.name for tool in await mcp_server.list_tools()}

    assert HTASK_CRITICAL_TOOL_SURFACE <= backend_tools
    assert HTASK_CRITICAL_TOOL_SURFACE <= listed_tools


@pytest.mark.asyncio
async def test_list_tools_matches_backend_contract_exactly():
    """The packaged MCP server should expose the full backend tool contract."""
    listed_tools = {tool.name: tool.inputSchema for tool in await mcp_server.list_tools()}
    backend_tools = {tool["name"]: tool["inputSchema"] for tool in MCP_TOOL_DEFINITIONS}

    assert set(listed_tools) == set(backend_tools)
    for name, schema in backend_tools.items():
        assert listed_tools[name] == schema


@pytest.mark.asyncio
async def test_context_query_bootstraps_session_context(monkeypatch, reset_mcp_server_state):
    """Context queries should auto-bootstrap session memory before querying."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_get_project_settings():
        return {
            "maxTokensPerQuery": 5000,
            "searchMode": "hybrid",
            "includeSummaries": True,
            "memoryAutoRecallOnSessionStart": True,
            "memoryAutoRecallOnResume": True,
            "memoryWorkspaceProfileEnabled": True,
            "memoryResumeWindowMinutes": 180,
        }

    async def fake_call_api(tool: str, params: dict, *, timeout: float = 60.0):
        calls.append((tool, params))
        if tool == "rlm_session_memories":
            return {
                "success": True,
                "result": {
                    "critical": {
                        "memories": [{"content": "Prefer project-scoped durable memory writes."}]
                    },
                    "daily": {
                        "memories": [{"content": "Currently dogfooding memory automation flows."}]
                    },
                },
            }
        if tool == "rlm_tenant_profile_get":
            return {
                "success": True,
                "result": {
                    "profiles": [{"content": "Workspace defaults to mempalace-like automation."}]
                },
            }
        if tool == "rlm_shared_context":
            return {
                "success": True,
                "result": {
                    "merged_content": "MANDATORY: Keep shared standards visible.",
                    "documents": [],
                },
            }
        if tool == "rlm_context_query":
            return {
                "success": True,
                "result": {
                    "sections": [
                        {
                            "title": "Memory Automation",
                            "file": "docs/memory.md",
                            "relevance_score": 0.96,
                            "content": "Session bootstrap happens before the query runs.",
                        }
                    ],
                    "total_tokens": 120,
                },
            }
        raise AssertionError(f"Unexpected tool call: {tool}")

    monkeypatch.setattr(server, "get_project_settings", fake_get_project_settings)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool(
        "rlm_context_query",
        {"query": "How does session bootstrap work?"},
    )

    assert [tool for tool, _ in calls[:4]] == [
        "rlm_session_memories",
        "rlm_tenant_profile_get",
        "rlm_shared_context",
        "rlm_context_query",
    ]
    forwarded_query = calls[3][1]["query"]
    assert forwarded_query == "How does session bootstrap work?"
    assert "Session Context" in response[0].text
    assert "Shared Context:" in response[0].text
    assert "Workspace Profile:" in response[0].text
    assert "Critical Memories:" in response[0].text
    assert "Recent Context:" in response[0].text
    assert "Relevant Documentation" in response[0].text


@pytest.mark.asyncio
async def test_context_query_formats_references_mode(monkeypatch, reset_mcp_server_state):
    """References mode should render chunk IDs instead of looking empty."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_get_project_settings():
        return {"maxTokensPerQuery": 4000, "searchMode": "hybrid", "includeSummaries": True}

    async def fake_call_api(tool: str, params: dict, *, timeout: float = 60.0):
        calls.append((tool, params))
        return {
            "success": True,
            "result": {
                "sections": [],
                "section_refs": [
                    {
                        "chunk_id": "chunk-auth-1",
                        "title": "Authentication",
                        "file": "docs/auth.md",
                        "lines": [10, 20],
                        "relevance_score": 0.91,
                        "preview": "Auth context preview",
                    }
                ],
                "total_tokens": 24,
                "recovery_guidance": [
                    "Retry with fast_context_parameters if this is still too broad."
                ],
                "fast_context_parameters": {"query": "auth middleware", "max_tokens": 1200},
                "narrower_queries": ["auth middleware"],
            },
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "get_project_settings", fake_get_project_settings)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool(
        "rlm_context_query",
        {"query": "authentication", "return_references": True},
    )

    assert calls[0][0] == "rlm_context_query"
    assert calls[0][1]["return_references"] is True
    assert "Relevant Documentation References" in response[0].text
    assert "chunk-auth-1" in response[0].text
    assert "Recovery Hints" in response[0].text
    assert "No relevant documentation found" not in response[0].text


@pytest.mark.asyncio
async def test_context_query_timeout_uses_fast_retry(monkeypatch, reset_mcp_server_state):
    """Timeouts should automatically retry with the fast context path."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_get_project_settings():
        return {"maxTokensPerQuery": 4000, "searchMode": "hybrid", "includeSummaries": True}

    async def fake_call_api(tool: str, params: dict, *, timeout: float = 60.0):
        calls.append((tool, params))
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out")
        assert params["search_mode"] == "keyword"
        assert params["return_references"] is True
        assert params["auto_decompose"] is False
        assert params["include_all_tiers"] is False
        assert params["max_tokens"] == 1200
        return {
            "success": True,
            "result": {
                "sections": [],
                "section_refs": [
                    {
                        "chunk_id": "chunk-architecture-1",
                        "title": "Architecture Overview",
                        "file": "docs/architecture.md",
                        "lines": [1, 10],
                        "relevance_score": 0.88,
                        "preview": "Architecture overview preview",
                    }
                ],
                "total_tokens": 18,
            },
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "get_project_settings", fake_get_project_settings)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool("rlm_context_query", {"query": "broad architecture question"})

    assert len(calls) == 2
    assert calls[0][1]["query"] == "broad architecture question"
    assert calls[1][1]["query"] == "broad architecture question"
    assert "Relevant Documentation References" in response[0].text
    assert "chunk-architecture-1" in response[0].text
    assert "automatic fast retry" in response[0].text


@pytest.mark.asyncio
async def test_remember_passthrough_accepts_text_alias(monkeypatch, reset_mcp_server_state):
    """remember should accept the remote contract's text/content aliasing."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        calls.append((tool, params))
        return {
            "success": True,
            "result": {
                "memory_id": "mem_456",
                "type": params.get("type", "fact"),
                "scope": params.get("scope", "project"),
            },
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool(
        "rlm_remember",
        {
            "text": "PostgreSQL hosts the production Snipara database.",
            "type": "fact",
            "scope": "project",
        },
    )

    assert calls[0][0] == "rlm_remember"
    assert calls[0][1]["text"] == "PostgreSQL hosts the production Snipara database."
    assert calls[0][1]["scope"] == "project"
    assert "Memory stored" in response[0].text


@pytest.mark.asyncio
async def test_remember_if_novel_passthrough(monkeypatch, reset_mcp_server_state):
    """remember_if_novel should forward the novelty settings to the API."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        calls.append((tool, params))
        return {
            "success": True,
            "result": {
                "stored": True,
                "reason": "novel",
                "memory_id": "mem_123",
                "matched_memories": [],
            },
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool(
        "rlm_remember_if_novel",
        {
            "text": "Use novelty-gated writes for durable memory.",
            "type": "decision",
            "scope": "project",
            "novelty_threshold": 0.91,
            "dedupe_limit": 7,
        },
    )

    assert calls[0][0] == "rlm_remember_if_novel"
    assert calls[0][1]["text"] == "Use novelty-gated writes for durable memory."
    assert calls[0][1]["novelty_threshold"] == 0.91
    assert calls[0][1]["dedupe_limit"] == 7
    assert "Memory stored" in response[0].text


@pytest.mark.asyncio
async def test_remember_if_novel_workflow_error_adds_guidance(monkeypatch, reset_mcp_server_state):
    """workflow errors should point callers at end_of_task_commit."""
    server = reset_mcp_server_state

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        assert tool == "rlm_remember_if_novel"
        return {
            "success": False,
            "error": (
                "Invalid parameter 'type': unsupported memory type 'workflow'. "
                "Expected one of: fact, decision, learning, preference, todo, context"
            ),
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool(
        "rlm_remember_if_novel",
        {
            "text": "Persist workflow rules directly",
            "type": "workflow",
        },
    )

    assert "workflow" in response[0].text
    assert "rlm_end_of_task_commit.persist_types" in response[0].text


@pytest.mark.asyncio
async def test_end_of_task_commit_passthrough(monkeypatch, reset_mcp_server_state):
    """end_of_task_commit should forward task summary payloads to the API."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        calls.append((tool, params))
        return {
            "success": True,
            "result": {
                "stored_count": 2,
                "skipped_count": 1,
            },
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool(
        "rlm_end_of_task_commit",
        {
            "summary": "Standardized session bootstrap and novelty-gated writes.",
            "outcome": "completed",
            "files_touched": ["apps/mcp-server/src/services/tool_recommender.py"],
            "persist_types": ["decision", "workflow"],
            "category": "dogfooding-memory-automation",
        },
    )

    assert calls[0][0] == "rlm_end_of_task_commit"
    assert calls[0][1]["summary"] == "Standardized session bootstrap and novelty-gated writes."
    assert calls[0][1]["persist_types"] == ["decision", "workflow"]
    assert calls[0][1]["category"] == "dogfooding-memory-automation"
    assert "Stored: 2 | Skipped: 1" in response[0].text


@pytest.mark.asyncio
async def test_help_passthrough_and_rendering(monkeypatch, reset_mcp_server_state):
    """rlm_help should proxy recommendations and render them readably."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        calls.append((tool, params))
        return {
            "success": True,
            "result": {
                "query": "persist durable memory without duplicates",
                "recommendations": [
                    {
                        "tool": "rlm_end_of_task_commit",
                        "tier": "power_user",
                        "description": "Persist durable knowledge from a task summary",
                    },
                    {
                        "tool": "rlm_remember_if_novel",
                        "tier": "power_user",
                        "description": "Store a memory only when it is sufficiently novel",
                    },
                ],
                "tip": "Use rlm_help(tool='tool_name') for details.",
            },
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool(
        "rlm_help",
        {"query": "persist durable memory without duplicates", "limit": 2},
    )

    assert calls[0][0] == "rlm_help"
    assert calls[0][1]["query"] == "persist durable memory without duplicates"
    assert calls[0][1]["limit"] == 2
    assert "`rlm_end_of_task_commit`" in response[0].text
    assert "`rlm_remember_if_novel`" in response[0].text


@pytest.mark.asyncio
async def test_reindex_passthrough_formats_job_creation(monkeypatch, reset_mcp_server_state):
    """reindex should forward arguments and render a polling hint."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        calls.append((tool, params))
        return {
            "success": True,
            "result": {
                "action": "trigger",
                "job_id": "job_123",
                "status": "pending",
                "progress": 0,
                "index_mode": "full",
                "index_kind": "doc",
                "already_exists": False,
            },
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool("rlm_reindex", {"mode": "full", "kind": "doc"})

    assert calls[0] == ("rlm_reindex", {"mode": "full", "kind": "doc"})
    assert "job_123" in response[0].text
    assert 'Poll via: rlm_reindex(job_id="job_123")' in response[0].text


@pytest.mark.asyncio
async def test_memory_daily_brief_passthrough(monkeypatch, reset_mcp_server_state):
    """rlm_memory_daily_brief should proxy to the backend and return the brief."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        calls.append((tool, params))
        return {
            "success": True,
            "result": {
                "date": "2026-04-15",
                "brief": "# Daily Brief\n\n## Active Decisions\n- Prefer novelty-gated writes",
                "counts": {"decisions": 1, "todos": 0, "learnings": 0},
            },
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool(
        "rlm_memory_daily_brief",
        {"date": "2026-04-15", "max_items": 6},
    )

    assert calls[0][0] == "rlm_memory_daily_brief"
    assert calls[0][1]["date"] == "2026-04-15"
    assert calls[0][1]["max_items"] == 6
    assert "# Daily Brief" in response[0].text


@pytest.mark.asyncio
async def test_ask_accepts_query_shape_and_proxies_backend_tool(
    monkeypatch, reset_mcp_server_state
):
    """rlm_ask should accept the backend's query parameter and call the matching tool."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        calls.append((tool, params))
        return {
            "success": True,
            "result": {
                "query": params["query"],
                "sections": [
                    {
                        "title": "Auth",
                        "file_path": "docs/auth.md",
                        "content": "Authentication uses JWT.",
                    }
                ],
            },
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool("rlm_ask", {"query": "How does auth work?"})

    assert calls[0][0] == "rlm_ask"
    assert calls[0][1]["query"] == "How does auth work?"
    assert "Authentication uses JWT." in response[0].text


@pytest.mark.asyncio
async def test_remember_if_novel_requires_text_or_content(monkeypatch, reset_mcp_server_state):
    """Novelty-gated writes should fail fast before hitting the backend when content is missing."""
    server = reset_mcp_server_state

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        raise AssertionError("Backend should not be called when content is missing")

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool("rlm_remember_if_novel", {"type": "fact"})

    assert "requires `text` or legacy `content`" in response[0].text


@pytest.mark.asyncio
async def test_generic_passthrough_supports_backend_only_tools(monkeypatch, reset_mcp_server_state):
    """Tools exposed only by the backend contract should still proxy through the packaged client."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        calls.append((tool, params))
        return {
            "success": True,
            "result": {
                "projects": [{"project_id": "snipara", "matches": 3}],
                "total_tokens": 321,
            },
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool(
        "rlm_multi_project_query",
        {"query": "rate limiting", "per_project_limit": 2},
    )

    assert calls[0] == (
        "rlm_multi_project_query",
        {"query": "rate limiting", "per_project_limit": 2},
    )
    assert '"projects"' in response[0].text


@pytest.mark.asyncio
async def test_state_set_forwards_ttl_seconds(monkeypatch, reset_mcp_server_state):
    """rlm_state_set should pass through optional TTL support from the backend schema."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        calls.append((tool, params))
        return {"success": True, "result": {"message": "updated", "version": 4}}

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    response = await server.call_tool(
        "rlm_state_set",
        {
            "swarm_id": "sw_123",
            "agent_id": "agent_a",
            "key": "plan",
            "value": {"step": 1},
            "ttl_seconds": 600,
        },
    )

    assert calls[0][1]["ttl_seconds"] == 600
    assert "v4" in response[0].text


@pytest.mark.asyncio
async def test_task_create_forwards_deadline_and_affinity(monkeypatch, reset_mcp_server_state):
    """rlm_task_create should preserve the newer backend task fields."""
    server = reset_mcp_server_state
    calls: list[tuple[str, dict]] = []

    async def fake_bootstrap(force: bool = False):
        return None

    async def fake_call_api(tool: str, params: dict):
        calls.append((tool, params))
        return {
            "success": True,
            "result": {"task_id": "task_123", "priority": 2, "depends_on": []},
        }

    monkeypatch.setattr(server, "ensure_session_bootstrap", fake_bootstrap)
    monkeypatch.setattr(server, "call_api", fake_call_api)

    await server.call_tool(
        "rlm_task_create",
        {
            "swarm_id": "sw_123",
            "agent_id": "agent_a",
            "title": "Review deploy",
            "priority": 2,
            "deadline": "2026-04-17T10:00:00Z",
            "for_agent_id": "agent_b",
        },
    )

    assert calls[0][1]["deadline"] == "2026-04-17T10:00:00Z"
    assert calls[0][1]["for_agent_id"] == "agent_b"
