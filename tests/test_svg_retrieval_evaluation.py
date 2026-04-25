"""Retrieval evaluation for SVG context bundles."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.engine.core import DocumentationIndex
from src.models import Plan
from src.rlm_engine import RLMEngine
from src.services.svg_bundle_ingest import SvgBundleIngestPayload, build_svg_bundle_ingest_payload

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "svg_retrieval"


def _load_fixture_bundle() -> SvgBundleIngestPayload:
    return build_svg_bundle_ingest_payload(
        svg_content=(FIXTURE_DIR / "mairie-av-network.svg").read_text(encoding="utf-8"),
        source_path="projets/mairie-2024/schema-reseau-av.svg",
        upload_prefix="clients/mairie-2024/svg-context",
    )


def _build_indexed_engine(bundle: SvgBundleIngestPayload) -> RLMEngine:
    engine = RLMEngine("test-project", plan=Plan.TEAM)
    engine.index = DocumentationIndex()

    for document in bundle.documents:
        document_lines = document.content.split("\n")
        line_offset = len(engine.index.lines)
        engine.index.files.append(document.path)
        engine.index.lines.extend(document_lines)
        engine.index.total_chars += len(document.content)
        engine.index.file_boundaries[document.path] = (
            line_offset,
            line_offset + len(document_lines),
        )
        engine._parse_sections(document_lines, line_offset, document.path)

    engine._compute_ubiquitous_keywords("mairie-2024")
    return engine


def _load_benchmark_prompts() -> list[dict]:
    return json.loads((FIXTURE_DIR / "benchmark_prompts.json").read_text(encoding="utf-8"))


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt", _load_benchmark_prompts(), ids=lambda prompt: prompt["id"])
async def test_svg_bundle_retrieval_returns_linked_companion_artifacts(prompt, monkeypatch):
    bundle = _load_fixture_bundle()
    role_paths = {document.role: document.path for document in bundle.documents}
    engine = _build_indexed_engine(bundle)
    fake_cache = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(return_value=True),
        invalidate=AsyncMock(return_value=0),
    )

    monkeypatch.setattr("src.rlm_engine.get_cache", lambda *args, **kwargs: fake_cache)
    monkeypatch.setattr(
        "src.rlm_engine.get_db",
        AsyncMock(side_effect=RuntimeError("database not available in retrieval evaluation")),
    )

    result = await engine._handle_context_query(
        {
            "query": prompt["query"],
            "max_tokens": 6000,
            "search_mode": "keyword",
            "include_shared_context": False,
            "prefer_summaries": False,
            "auto_decompose": False,
        }
    )

    returned_paths = {section["file"] for section in result.data["sections"]}
    expected_paths = {role_paths[role] for role in prompt["expected_artifact_roles"]}

    assert expected_paths <= returned_paths
    linked_sections = [
        section
        for section in result.data["sections"]
        if section["file"] in expected_paths and bundle.bundle_id in section["content"]
    ]
    assert {section["file"] for section in linked_sections} == expected_paths
    assert result.data["total_tokens"] <= result.data["max_tokens"]
