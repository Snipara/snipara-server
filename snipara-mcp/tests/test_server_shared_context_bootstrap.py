from __future__ import annotations

from typing import Any

import pytest

from snipara_mcp import server as server_module


@pytest.mark.asyncio
async def test_shared_context_bootstraps_even_when_memory_recall_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_call_api(
        tool: str,
        params: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        calls.append((tool, params))
        if tool == "rlm_shared_context":
            return {
                "success": True,
                "result": {
                    "documents": [
                        {
                            "title": "Coding Standards",
                            "category": "MANDATORY",
                            "token_count": 120,
                        },
                        {
                            "title": "Snipara Workflow",
                            "category": "BEST_PRACTICES",
                            "token_count": 80,
                        },
                    ],
                    "merged_content": "MANDATORY: Use typed APIs.\nBEST_PRACTICES: Prefer explicit retries.",
                    "collections_loaded": 1,
                    "context_hash": "abc123",
                },
            }
        raise AssertionError(f"Unexpected tool call: {tool}")

    async def fake_settings() -> dict[str, Any]:
        return {
            "memoryAutoRecallOnSessionStart": False,
            "memoryAutoRecallOnResume": False,
            "memoryWorkspaceProfileEnabled": False,
            "memoryResumeWindowMinutes": 180,
            "maxTokensPerQuery": 4000,
        }

    monkeypatch.setattr(server_module, "call_api", fake_call_api)
    monkeypatch.setattr(server_module, "get_project_settings", fake_settings)
    monkeypatch.setattr(server_module, "_get_shared_context_bootstrap_config", lambda: (True, 30))
    monkeypatch.setattr(server_module, "_session_initialized", False, raising=False)
    monkeypatch.setattr(server_module, "_session_context", "", raising=False)
    monkeypatch.setattr(server_module, "_session_last_bootstrap_at", 0.0, raising=False)
    monkeypatch.setattr(server_module, "_shared_context_bootstrapped", False, raising=False)

    await server_module.ensure_session_bootstrap()

    assert calls == [
        (
            "rlm_shared_context",
            {
                "max_tokens": 1200,
                "include_content": True,
            },
        )
    ]
    assert server_module._session_initialized is True
    assert server_module._shared_context_bootstrapped is True
    assert "Shared Context:" in server_module._session_context
    assert "MANDATORY: Use typed APIs." in server_module._session_context
    assert "Workspace Profile:" not in server_module._session_context

