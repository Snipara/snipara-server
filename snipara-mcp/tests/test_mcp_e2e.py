"""E2E-style tests for the packaged MCP server and SDK transport client."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from snipara_mcp import server as mcp_server
from snipara_mcp.rlm_tools import SniparaClient


class LocalMcpBackend:
    """Small remote-MCP fixture that records real HTTP requests."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        self.requests.append(
            {
                "method": request.method,
                "path": request.url.path,
                "headers": dict(request.headers),
                "body": body,
            }
        )

        if request.url.path.endswith("/api/mcp/e2e-project"):
            return self._tool_response(body)

        if request.url.path != "/v1/e2e-project/mcp":
            return httpx.Response(404, json={"success": False, "error": "not found"})

        return self._tool_response(body)

    def _tool_response(self, body: dict[str, Any]) -> httpx.Response:
        tool = body["tool"]
        params = body.get("params") or {}
        if tool == "rlm_context_query":
            payload = {
                "sections": [
                    {
                        "title": "SDK Endpoint Contract",
                        "file": "docs/sdk.md",
                        "content": f"Context for {params['query']}",
                        "relevance_score": 0.97,
                    }
                ],
                "total_tokens": 42,
            }
        elif tool == "rlm_remember_if_novel":
            payload = {
                "stored": True,
                "reason": "novel",
                "memory_id": "mem_e2e",
            }
        elif tool == "rlm_memory_health":
            payload = {
                "status": "healthy",
                "orphaned_memories": 0,
            }
        elif tool == "rlm_htask_get":
            payload = {
                "task_id": params.get("task_id"),
                "title": "E2E htask",
                "status": "OPEN",
            }
        else:
            return httpx.Response(400, json={"success": False, "error": f"unknown tool {tool}"})
        return httpx.Response(200, json={"success": True, "result": payload})


def _install_mock_transport(monkeypatch, backend: LocalMcpBackend) -> None:
    original_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(backend)

    def async_client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", async_client_factory)


def _disable_bootstrap(monkeypatch) -> None:
    async def settings() -> dict[str, Any]:
        return {
            "maxTokensPerQuery": 4000,
            "searchMode": "hybrid",
            "includeSummaries": True,
            "memoryAutoRecallOnSessionStart": False,
            "memoryAutoRecallOnResume": False,
        }

    monkeypatch.setattr(mcp_server, "get_project_settings", settings)
    monkeypatch.setattr(mcp_server, "_get_shared_context_bootstrap_config", lambda: (False, 30))
    monkeypatch.setattr(mcp_server, "_session_initialized", False)
    monkeypatch.setattr(mcp_server, "_shared_context_bootstrapped", False)
    monkeypatch.setattr(mcp_server, "_session_context", "")


def test_server_e2e_list_tools_and_real_tool_calls(monkeypatch) -> None:
    """The stdio server should list tools and execute real HTTP tool payloads."""
    backend = LocalMcpBackend()
    _install_mock_transport(monkeypatch, backend)
    _disable_bootstrap(monkeypatch)
    monkeypatch.setattr(mcp_server, "API_URL", "https://fixture.snipara.test")
    monkeypatch.setattr(mcp_server, "PROJECT_ID", "e2e-project")
    monkeypatch.setattr(mcp_server, "_auth_type", "api_key")
    monkeypatch.setattr(mcp_server, "_auth_token", "rlm_e2e_key")
    monkeypatch.setattr(mcp_server, "API_KEY", "")

    async def run_calls() -> tuple[set[str], Any, Any, Any, Any]:
        tools = {tool.name for tool in await mcp_server.list_tools()}
        context = await mcp_server.call_tool("rlm_context_query", {"query": "endpoint contract"})
        remember = await mcp_server.call_tool(
            "rlm_remember_if_novel",
            {"text": "The SDK prefers the remote MCP endpoint.", "type": "learning"},
        )
        health = await mcp_server.call_tool("rlm_memory_health", {})
        htask = await mcp_server.call_tool("rlm_htask_get", {"task_id": "task-e2e"})
        return tools, context, remember, health, htask

    tools, context, remember, health, htask = asyncio.run(run_calls())
    assert {
        "rlm_context_query",
        "rlm_remember_if_novel",
        "rlm_memory_health",
        "rlm_htask_get",
    }.issubset(tools)

    assert "SDK Endpoint Contract" in context[0].text
    assert "Context for endpoint contract" in context[0].text
    assert "**Memory stored**" in remember[0].text
    assert "mem_e2e" in remember[0].text
    assert "**rlm_memory_health**" in health[0].text
    assert '"orphaned_memories": 0' in health[0].text
    assert "**rlm_htask_get**" in htask[0].text
    assert '"task_id": "task-e2e"' in htask[0].text

    assert [request["body"]["tool"] for request in backend.requests] == [
        "rlm_context_query",
        "rlm_remember_if_novel",
        "rlm_memory_health",
        "rlm_htask_get",
    ]
    assert all(request["path"] == "/v1/e2e-project/mcp" for request in backend.requests)
    assert all(request["headers"]["x-api-key"] == "rlm_e2e_key" for request in backend.requests)


def test_snipara_client_endpoint_contract_prefers_remote_mcp_and_falls_back(
    monkeypatch,
) -> None:
    """SDK transport should target /v1/{project}/mcp before legacy /api/mcp/{project}."""
    backend = LocalMcpBackend()
    original_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(backend)

    def async_client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", async_client_factory)
    client = SniparaClient(
        api_key="rlm_sdk_key",
        project_slug="e2e-project",
        api_url="https://fixture.snipara.test",
    )

    result = asyncio.run(client.call_tool("rlm_memory_health", {}))

    assert result == {"status": "healthy", "orphaned_memories": 0}
    assert [request["path"] for request in backend.requests] == ["/v1/e2e-project/mcp"]
    assert backend.requests[0]["headers"]["x-api-key"] == "rlm_sdk_key"

    backend_404_first = LocalMcpBackend()
    first_call = True

    def fallback_backend(request: httpx.Request) -> httpx.Response:
        nonlocal first_call
        if first_call:
            first_call = False
            backend_404_first.requests.append({"path": request.url.path})
            return httpx.Response(404, json={"success": False, "error": "not found"})
        return backend_404_first(request)

    transport = httpx.MockTransport(fallback_backend)
    fallback_client = SniparaClient(
        api_key="rlm_sdk_key",
        project_slug="e2e-project",
        api_url="https://fixture.snipara.test",
    )

    fallback_result = asyncio.run(
        fallback_client.call_tool("rlm_htask_get", {"task_id": "task-e2e"})
    )

    assert fallback_result["task_id"] == "task-e2e"
    assert [request["path"] for request in backend_404_first.requests] == [
        "/v1/e2e-project/mcp",
        "/api/mcp/e2e-project",
    ]
