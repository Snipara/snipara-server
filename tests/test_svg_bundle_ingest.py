"""Tests for native SVG bundle ingestion contract."""

from __future__ import annotations

from types import MethodType

import pytest

from src.mcp.tool_defs import TOOL_DEFINITIONS
from src.models import Plan, ToolName, ToolResult
from src.rlm_engine import RLMEngine
from src.services.svg_bundle_ingest import build_svg_bundle_ingest_payload

SVG_SAMPLE = """
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <title>Conseil Municipal AV</title>
  <desc>Topologie audiovisuelle avec DSP, matrice HDMI, et Dante VLAN.</desc>
  <text x="10" y="20">Switch PoE</text>
  <text x="10" y="50">Dante VLAN</text>
  <text x="10" y="80">DSP</text>
</svg>
""".strip()


def test_svg_bundle_ingest_payload_links_generated_documents():
    payload = build_svg_bundle_ingest_payload(
        svg_content=SVG_SAMPLE,
        source_path="projets/mairie-2024/schema-audiovisuel.svg",
        upload_prefix="clients/mairie-2024/svg-context",
    )

    assert payload.bundle_id.startswith("svgctx_")
    assert len(payload.source_hash) == 64
    assert payload.source_path == "projets/mairie-2024/schema-audiovisuel.svg"
    assert payload.quality["status"] == "good"
    assert payload.quality["score"] >= 0.75
    assert [document.role for document in payload.documents] == [
        "context",
        "manifest",
        "enriched_svg",
    ]
    assert [document.path for document in payload.documents] == [
        "clients/mairie-2024/svg-context/projets/mairie-2024/schema-audiovisuel.context.md",
        "clients/mairie-2024/svg-context/projets/mairie-2024/schema-audiovisuel.manifest.md",
        "clients/mairie-2024/svg-context/projets/mairie-2024/schema-audiovisuel.enriched-svg.md",
    ]
    assert all(payload.bundle_id in document.content for document in payload.documents)


def test_tool_definition_exposes_svg_bundle_ingest_contract():
    assert ToolName.RLM_SVG_BUNDLE_INGEST.value == "rlm_svg_bundle_ingest"

    tool = next((item for item in TOOL_DEFINITIONS if item["name"] == "rlm_svg_bundle_ingest"), None)

    assert tool is not None
    schema = tool["inputSchema"]
    assert schema["required"] == ["svg_content", "source_path"]
    assert "upload_prefix" in schema["properties"]
    assert "dry_run" in schema["properties"]
    assert "reindex" in schema["properties"]
    assert schema["properties"]["reindex_mode"]["enum"] == ["incremental", "full"]


@pytest.mark.asyncio
async def test_svg_bundle_ingest_dry_run_returns_summary_without_upload():
    engine = RLMEngine("proj-1", plan=Plan.TEAM)

    async def fail_sync(_self, _params):
        raise AssertionError("dry-run must not upload documents")

    engine._handle_sync_documents = MethodType(fail_sync, engine)

    result = await engine._handle_svg_bundle_ingest(
        {
            "svg_content": SVG_SAMPLE,
            "source_path": "schema-reseau.svg",
            "upload_prefix": "svg-context",
            "dry_run": True,
        }
    )

    assert result.data["action"] == "dry_run"
    assert result.data["dry_run"] is True
    assert result.data["bundle"]["document_count"] == 3
    assert result.data["bundle"]["quality"]["status"] == "good"
    assert "upload" not in result.data


@pytest.mark.asyncio
async def test_svg_bundle_ingest_upload_uses_document_sync():
    engine = RLMEngine("proj-1", plan=Plan.TEAM)
    calls: list[dict] = []

    async def fake_sync(_self, params):
        calls.append(params)
        return ToolResult(
            data={
                "created": len(params["documents"]),
                "updated": 0,
                "unchanged": 0,
                "deleted": 0,
                "total": len(params["documents"]),
                "message": "ok",
            }
        )

    engine._handle_sync_documents = MethodType(fake_sync, engine)

    result = await engine._handle_svg_bundle_ingest(
        {
            "svg_content": SVG_SAMPLE,
            "source_path": "schema-reseau.svg",
            "upload_prefix": "svg-context",
        }
    )

    assert result.data["action"] == "uploaded"
    assert result.data["upload"]["created"] == 3
    assert len(calls) == 1
    assert calls[0]["delete_missing"] is False
    assert [document["path"] for document in calls[0]["documents"]] == [
        "svg-context/schema-reseau.context.md",
        "svg-context/schema-reseau.manifest.md",
        "svg-context/schema-reseau.enriched-svg.md",
    ]
    metadata = calls[0]["documents"][0]["metadata"]
    assert metadata["bundleId"] == result.data["bundle"]["bundle_id"]
    assert metadata["sourceHash"] == result.data["bundle"]["source_hash"]
    assert metadata["sourcePath"] == "schema-reseau.svg"
    assert metadata["artifactRole"] == "context"
    assert metadata["bundleDocumentPaths"] == [
        "svg-context/schema-reseau.context.md",
        "svg-context/schema-reseau.manifest.md",
        "svg-context/schema-reseau.enriched-svg.md",
    ]


@pytest.mark.asyncio
async def test_svg_bundle_ingest_can_trigger_reindex_after_upload():
    engine = RLMEngine("proj-1", plan=Plan.TEAM)
    reindex_calls: list[dict] = []

    async def fake_sync(_self, params):
        return ToolResult(
            data={
                "created": len(params["documents"]),
                "updated": 0,
                "unchanged": 0,
                "deleted": 0,
                "total": len(params["documents"]),
                "message": "ok",
            }
        )

    async def fake_reindex(_self, params):
        reindex_calls.append(params)
        return ToolResult(data={"job_id": "job_123", "status": "pending"})

    engine._handle_sync_documents = MethodType(fake_sync, engine)
    engine._handle_reindex = MethodType(fake_reindex, engine)

    result = await engine._handle_svg_bundle_ingest(
        {
            "svg_content": SVG_SAMPLE,
            "source_path": "schema-reseau.svg",
            "reindex": True,
            "reindex_mode": "incremental",
        }
    )

    assert reindex_calls == [{"kind": "doc", "mode": "incremental"}]
    assert result.data["reindex_job"]["job_id"] == "job_123"


def test_document_metadata_matching_keeps_repeated_ingest_idempotent():
    metadata = {
        "bundleId": "svgctx_123",
        "sourceHash": "abc",
        "artifactRole": "context",
    }

    assert RLMEngine._document_metadata_matches(metadata, metadata) is True
    assert RLMEngine._document_metadata_matches({"bundleId": "other"}, metadata) is False
