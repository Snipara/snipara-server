"""Tests for MCP document upload and sync contracts."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.models import Plan
from src.rlm_engine import RLMEngine


def _payload(raw: bytes) -> str:
    return f"base64:{base64.b64encode(raw).decode('ascii')}"


def _fake_cache():
    return SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(return_value=True),
        invalidate=AsyncMock(return_value=1),
    )


@pytest.mark.asyncio
async def test_upload_document_accepts_binary_parser_documents(monkeypatch):
    engine = RLMEngine("test-project", plan=Plan.TEAM)
    fake_cache = _fake_cache()
    fake_db = SimpleNamespace(
        document=SimpleNamespace(
            find_first=AsyncMock(return_value=None),
            create=AsyncMock(return_value=None),
        ),
        documentchunk=SimpleNamespace(delete_many=AsyncMock(return_value=None)),
    )

    monkeypatch.setattr("src.rlm_engine.get_cache", lambda *args, **kwargs: fake_cache)
    monkeypatch.setattr("src.rlm_engine.get_db", AsyncMock(return_value=fake_db))

    result = await engine._handle_upload_document(
        {
            "path": "diagrams/network.vsdx",
            "content": _payload(b"vsdx-bytes"),
            "kind": "BINARY",
            "format": "vsdx",
            "metadata": {"assetClass": "DIAGRAM", "usageMode": "historical_reference"},
        }
    )

    assert result.data["action"] == "created"
    created = fake_db.document.create.await_args.kwargs["data"]
    assert created["path"] == "diagrams/network.vsdx"
    assert created["kind"] == "BINARY"
    assert created["format"] == "vsdx"
    assert created["language"] is None
    metadata = getattr(created["metadata"], "data", created["metadata"])
    assert metadata["assetClass"] == "DIAGRAM"


@pytest.mark.asyncio
async def test_upload_document_rejects_raw_binary_payload(monkeypatch):
    engine = RLMEngine("test-project", plan=Plan.TEAM)
    get_db = AsyncMock()
    monkeypatch.setattr("src.rlm_engine.get_db", get_db)

    result = await engine._handle_upload_document(
        {
            "path": "diagrams/network.vsdx",
            "content": "raw-vsdx-bytes",
            "kind": "BINARY",
            "format": "vsdx",
        }
    )

    assert "base64" in result.data["error"]
    get_db.assert_not_called()


@pytest.mark.asyncio
async def test_sync_documents_accepts_text_and_binary_documents(monkeypatch):
    engine = RLMEngine("test-project", plan=Plan.TEAM)
    fake_cache = _fake_cache()
    fake_db = SimpleNamespace(
        document=SimpleNamespace(
            find_many=AsyncMock(return_value=[]),
            create=AsyncMock(return_value=None),
        ),
        documentchunk=SimpleNamespace(delete_many=AsyncMock(return_value=None)),
    )

    monkeypatch.setattr("src.rlm_engine.get_cache", lambda *args, **kwargs: fake_cache)
    monkeypatch.setattr("src.rlm_engine.get_db", AsyncMock(return_value=fake_db))

    result = await engine._handle_sync_documents(
        {
            "documents": [
                {"path": "docs/spec.md", "content": "# Spec"},
                {
                    "path": "diagrams/network.vsdx",
                    "content": _payload(b"vsdx-bytes"),
                    "kind": "BINARY",
                    "format": "vsdx",
                },
                {"path": "images/logo.png", "content": _payload(b"png")},
            ]
        }
    )

    assert result.data["created"] == 2
    assert result.data["total"] == 2
    created_docs = [call.kwargs["data"] for call in fake_db.document.create.await_args_list]
    assert [(doc["path"], doc["kind"], doc["format"]) for doc in created_docs] == [
        ("docs/spec.md", "DOC", "md"),
        ("diagrams/network.vsdx", "BINARY", "vsdx"),
    ]
