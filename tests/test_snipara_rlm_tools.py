"""Tests for snipara_mcp.rlm_tools endpoint resolution."""

from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNIPARA_MCP_SRC = PROJECT_ROOT / "snipara-mcp/src"

if str(SNIPARA_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(SNIPARA_MCP_SRC))

from snipara_mcp.rlm_tools import SniparaClient, get_snipara_tools
from snipara_mcp.tool_contract import TOOL_DEFINITIONS


class FakeTool:
    """Minimal stand-in for rlm.backends.base.Tool in tests."""

    def __init__(self, name: str, description: str, parameters: dict, handler):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler


def _install_fake_rlm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a fake rlm.backends.base.Tool import for get_snipara_tools."""
    rlm_module = types.ModuleType("rlm")
    backends_module = types.ModuleType("rlm.backends")
    base_module = types.ModuleType("rlm.backends.base")
    base_module.Tool = FakeTool
    monkeypatch.setitem(sys.modules, "rlm", rlm_module)
    monkeypatch.setitem(sys.modules, "rlm.backends", backends_module)
    monkeypatch.setitem(sys.modules, "rlm.backends.base", base_module)


def _response(status_code: int, payload: dict) -> httpx.Response:
    request = httpx.Request("POST", "https://api.snipara.com/test")
    return httpx.Response(status_code, json=payload, request=request)


@pytest.mark.asyncio
async def test_call_tool_prefers_hosted_v1_endpoint():
    """Hosted API calls should target the v1 MCP endpoint first."""
    http_client = MagicMock()
    http_client.is_closed = False
    http_client.post = AsyncMock(
        return_value=_response(200, {"success": True, "result": {"ok": True}})
    )

    client = SniparaClient(api_key="rlm_test", project_slug="snipara")
    client._client = http_client

    result = await client.call_tool("rlm_stats", {})

    assert result == {"ok": True}
    assert http_client.post.await_args_list[0].args[0] == "https://api.snipara.com/v1/snipara/mcp"
    assert client._tool_endpoint_url == "https://api.snipara.com/v1/snipara/mcp"


@pytest.mark.asyncio
async def test_call_tool_falls_back_to_proxy_endpoint_on_404():
    """Clients should fall back to the proxy route when v1 is unavailable."""
    http_client = MagicMock()
    http_client.is_closed = False
    http_client.post = AsyncMock(
        side_effect=[
            _response(404, {"detail": "not found"}),
            _response(200, {"success": True, "result": {"mode": "proxy"}}),
            _response(200, {"success": True, "result": {"mode": "proxy-cached"}}),
        ]
    )

    client = SniparaClient(api_key="rlm_test", project_slug="self-hosted", api_url="https://snipara.example.com")
    client._client = http_client

    first = await client.call_tool("rlm_stats", {})
    second = await client.call_tool("rlm_stats", {})

    assert first == {"mode": "proxy"}
    assert second == {"mode": "proxy-cached"}
    assert http_client.post.await_args_list[0].args[0] == "https://snipara.example.com/v1/self-hosted/mcp"
    assert http_client.post.await_args_list[1].args[0] == "https://snipara.example.com/api/mcp/self-hosted"
    assert http_client.post.await_args_list[2].args[0] == "https://snipara.example.com/api/mcp/self-hosted"
    assert client._tool_endpoint_url == "https://snipara.example.com/api/mcp/self-hosted"


@pytest.mark.asyncio
async def test_call_tool_does_not_fallback_on_non_404_errors():
    """Authentication and server errors should surface immediately."""
    http_client = MagicMock()
    http_client.is_closed = False
    http_client.post = AsyncMock(
        return_value=_response(401, {"detail": "unauthorized"})
    )

    client = SniparaClient(api_key="rlm_test", project_slug="snipara")
    client._client = http_client

    with pytest.raises(httpx.HTTPStatusError):
        await client.call_tool("rlm_stats", {})

    assert http_client.post.await_count == 1


def test_get_snipara_tools_includes_full_backend_contract(monkeypatch: pytest.MonkeyPatch):
    """rlm-runtime integration should expose every hosted rlm_* tool."""
    _install_fake_rlm(monkeypatch)

    tools = get_snipara_tools(api_key="rlm_test", project_slug="snipara")
    tool_names = {tool.name for tool in tools}
    contract_names = {tool["name"] for tool in TOOL_DEFINITIONS}

    assert contract_names <= tool_names
    assert {"context_query", "remember", "task_create"} <= tool_names


@pytest.mark.asyncio
async def test_generated_contract_tool_handler_forwards_arguments(monkeypatch: pytest.MonkeyPatch):
    """Generated rlm_* handlers should forward kwargs verbatim to the hosted API."""
    _install_fake_rlm(monkeypatch)
    calls: list[tuple[str, dict]] = []

    async def fake_call_tool(self, tool_name: str, params: dict):
        calls.append((tool_name, params))
        return {"ok": True}

    monkeypatch.setattr(SniparaClient, "call_tool", fake_call_tool)

    tools = get_snipara_tools(api_key="rlm_test", project_slug="snipara")
    end_of_task_commit = next(tool for tool in tools if tool.name == "rlm_end_of_task_commit")

    result = await end_of_task_commit.handler(
        summary="Standardized memory-first automation.",
        persist_types=["workflow", "decision"],
        outcome="completed",
    )

    assert result == {"ok": True}
    assert calls == [
        (
            "rlm_end_of_task_commit",
            {
                "summary": "Standardized memory-first automation.",
                "persist_types": ["workflow", "decision"],
                "outcome": "completed",
            },
        )
    ]
