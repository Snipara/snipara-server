from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from snipara_mcp import rlm_tools


class FakeTool:
    def __init__(self, *, name: str, description: str, parameters: dict[str, Any], handler: Any):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler


class FakeSniparaClient:
    instances: list["FakeSniparaClient"] = []

    def __init__(self, api_key: str, project_slug: str, api_url: str | None = None):
        self.api_key = api_key
        self.project_slug = project_slug
        self.api_url = api_url
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.__class__.instances.append(self)

    async def call_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, params))
        return {"tool_name": tool_name, "params": params}


@pytest.fixture
def fake_runtime_module(monkeypatch: pytest.MonkeyPatch):
    base = types.ModuleType("rlm.backends.base")
    base.Tool = FakeTool

    monkeypatch.setitem(sys.modules, "rlm", types.ModuleType("rlm"))
    monkeypatch.setitem(sys.modules, "rlm.backends", types.ModuleType("rlm.backends"))
    monkeypatch.setitem(sys.modules, "rlm.backends.base", base)


@pytest.fixture(autouse=True)
def reset_fake_client():
    FakeSniparaClient.instances = []
    yield
    FakeSniparaClient.instances = []


@pytest.mark.asyncio
async def test_memory_tools_forward_new_lifecycle_params(
    monkeypatch: pytest.MonkeyPatch,
    fake_runtime_module: None,
):
    monkeypatch.setattr(rlm_tools, "SniparaClient", FakeSniparaClient)
    tools = rlm_tools.get_snipara_tools(api_key="rlm_test", project_slug="snipara")
    tool_map = {tool.name: tool for tool in tools}

    assert "memory_invalidate" in tool_map
    assert "memory_supersede" in tool_map

    await tool_map["recall"].handler(
        "auth decisions",
        include_inactive=True,
        warning_threshold=0.81,
    )
    await tool_map["memories"].handler(status="SUPERSEDED", include_inactive=True)
    await tool_map["memory_invalidate"].handler("mem_123", reason="Outdated flow")
    await tool_map["memory_supersede"].handler(
        "mem_123",
        "mem_456",
        reason="OAuth rollout",
    )

    client = FakeSniparaClient.instances[0]
    assert client.calls[0] == (
        "rlm_recall",
        {
            "query": "auth decisions",
            "limit": 5,
            "min_relevance": 0.5,
            "include_expired": False,
            "include_inactive": True,
            "warning_threshold": 0.81,
        },
    )
    assert client.calls[1] == (
        "rlm_memories",
        {
            "limit": 20,
            "offset": 0,
            "include_expired": False,
            "include_inactive": True,
            "status": "SUPERSEDED",
        },
    )
    assert client.calls[2] == (
        "rlm_memory_invalidate",
        {"memory_id": "mem_123", "reason": "Outdated flow"},
    )
    assert client.calls[3][0] == "rlm_memory_supersede"
    assert client.calls[3][1]["old_memory_id"] == "mem_123"
    assert client.calls[3][1]["new_memory_id"] == "mem_456"


@pytest.mark.asyncio
async def test_ask_uses_query_shape_for_backend(
    monkeypatch: pytest.MonkeyPatch,
    fake_runtime_module: None,
):
    monkeypatch.setattr(rlm_tools, "SniparaClient", FakeSniparaClient)
    tools = rlm_tools.get_snipara_tools(api_key="rlm_test", project_slug="snipara")
    tool_map = {tool.name: tool for tool in tools}

    await tool_map["ask"].handler("How does auth work?")

    client = FakeSniparaClient.instances[0]
    assert client.calls[0] == (
        "rlm_ask",
        {"query": "How does auth work?"},
    )
