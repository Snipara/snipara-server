from __future__ import annotations

from typing import Any

import pytest

from snipara_mcp import server as server_module


def _tool_by_name(tools: list[Any], name: str) -> Any:
    return next(tool for tool in tools if tool.name == name)


@pytest.mark.asyncio
async def test_list_tools_exposes_graveyard_lite_memory_surface():
    tools = await server_module.list_tools()

    recall = _tool_by_name(tools, "rlm_recall")
    memories = _tool_by_name(tools, "rlm_memories")
    invalidate = _tool_by_name(tools, "rlm_memory_invalidate")
    supersede = _tool_by_name(tools, "rlm_memory_supersede")

    recall_props = recall.inputSchema["properties"]
    assert "include_inactive" in recall_props
    assert recall_props["include_inactive"]["default"] is False
    assert "warning_threshold" in recall_props
    assert recall_props["warning_threshold"]["default"] == 0.72

    memories_props = memories.inputSchema["properties"]
    assert memories_props["status"]["enum"] == ["ACTIVE", "INVALIDATED", "SUPERSEDED"]
    assert memories_props["include_inactive"]["default"] is False

    assert invalidate.inputSchema["required"] == ["memory_id"]
    assert "invalidated_at" in invalidate.inputSchema["properties"]
    assert supersede.inputSchema["required"] == ["old_memory_id", "new_memory_id"]


@pytest.mark.asyncio
async def test_call_tool_forwards_recall_warning_controls(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def fake_call_api(tool: str, params: dict[str, Any]) -> dict[str, Any]:
        captured["tool"] = tool
        captured["params"] = params
        return {
            "success": True,
            "result": {
                "memories": [
                    {
                        "memory_id": "mem_active",
                        "content": "Bearer auth is the current path.",
                        "type": "decision",
                        "status": "ACTIVE",
                        "relevance": 0.91,
                        "confidence": 1.0,
                        "access_count": 3,
                    }
                ],
                "warnings": [
                    {
                        "memory_id": "mem_old",
                        "status": "SUPERSEDED",
                        "content": "Use API key only.",
                        "reason": "Replaced by bearer-auth decision",
                        "relevance": 0.84,
                    }
                ],
                "total_searched": 2,
            },
        }

    monkeypatch.setattr(server_module, "call_api", fake_call_api)

    contents = await server_module.call_tool(
        "rlm_recall",
        {
            "query": "auth flow",
            "include_inactive": True,
            "warning_threshold": 0.8,
        },
    )

    assert captured["tool"] == "rlm_recall"
    assert captured["params"]["include_inactive"] is True
    assert captured["params"]["warning_threshold"] == 0.8
    assert "Inactive memory warnings" in contents[0].text
    assert "SUPERSEDED" in contents[0].text


@pytest.mark.asyncio
async def test_call_tool_supports_memory_lifecycle_mutations(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_call_api(tool: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool, params))
        if tool == "rlm_memory_invalidate":
            return {
                "success": True,
                "result": {
                    "memory_id": "mem_123",
                    "status": "INVALIDATED",
                    "invalidated_at": "2026-04-22T06:00:00Z",
                },
            }
        if tool == "rlm_memory_supersede":
            return {
                "success": True,
                "result": {
                    "old_memory_id": "mem_123",
                    "new_memory_id": "mem_456",
                    "old_status": "SUPERSEDED",
                    "new_status": "ACTIVE",
                },
            }
        raise AssertionError(f"Unexpected tool {tool}")

    monkeypatch.setattr(server_module, "call_api", fake_call_api)

    invalidate = await server_module.call_tool(
        "rlm_memory_invalidate",
        {"memory_id": "mem_123", "reason": "obsolete"},
    )
    supersede = await server_module.call_tool(
        "rlm_memory_supersede",
        {
            "old_memory_id": "mem_123",
            "new_memory_id": "mem_456",
            "reason": "OAuth rollout",
        },
    )

    assert calls[0] == (
        "rlm_memory_invalidate",
        {"memory_id": "mem_123", "reason": "obsolete"},
    )
    assert calls[1][0] == "rlm_memory_supersede"
    assert calls[1][1]["old_memory_id"] == "mem_123"
    assert calls[1][1]["new_memory_id"] == "mem_456"

    assert "Memory invalidated" in invalidate[0].text
    assert "Memory superseded" in supersede[0].text
    assert "mem_456" in supersede[0].text
