"""Tests for the local SVG companion context builder."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "svg_context_builder.py"

SVG_SAMPLE = """
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <title>Conseil Municipal AV</title>
  <desc>Topologie audiovisuelle avec DSP, matrice HDMI, et Dante VLAN.</desc>
  <text x="10" y="20">Switch PoE</text>
  <text x="10" y="50">Dante VLAN</text>
  <text x="10" y="80">DSP</text>
</svg>
""".strip()


def _load_builder_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("svg_context_builder_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_artifact_set_links_local_and_upload_companions_by_bundle_id(tmp_path: Path):
    builder = _load_builder_module()
    project_dir = tmp_path / "mairie-2024"
    source_svg = project_dir / "schema-audiovisuel.svg"
    source_svg.parent.mkdir()
    source_svg.write_text(SVG_SAMPLE, encoding="utf-8")

    artifact_sets = builder.build_artifact_sets(
        input_path=project_dir,
        output_dir=tmp_path / "out",
        recursive=True,
        write_enriched_svg=True,
        upload_prefix="projets/mairie-2024/svg-context",
    )

    assert len(artifact_sets) == 1
    artifact_set = artifact_sets[0]
    bundle_id = artifact_set.bundle_id
    assert bundle_id.startswith("svgctx_")

    local_paths = {path.name: path for path in artifact_set.written_paths}
    assert set(local_paths) == {
        "schema-audiovisuel.context.md",
        "schema-audiovisuel.enriched.svg",
        "schema-audiovisuel.manifest.json",
    }

    manifest = json.loads(local_paths["schema-audiovisuel.manifest.json"].read_text())
    context = local_paths["schema-audiovisuel.context.md"].read_text(encoding="utf-8")
    enriched = local_paths["schema-audiovisuel.enriched.svg"].read_text(encoding="utf-8")

    assert manifest["bundleId"] == bundle_id
    assert f"Bundle ID: `{bundle_id}`" in context
    assert f'data-snipara-bundle-id="{bundle_id}"' in enriched

    upload_paths = {document["path"] for document in artifact_set.upload_documents}
    assert upload_paths == {
        "projets/mairie-2024/svg-context/schema-audiovisuel.context.md",
        "projets/mairie-2024/svg-context/schema-audiovisuel.enriched-svg.md",
        "projets/mairie-2024/svg-context/schema-audiovisuel.manifest.md",
    }
    assert all(bundle_id in document["content"] for document in artifact_set.upload_documents)
    bundle_document_paths = [document["path"] for document in artifact_set.upload_documents]
    assert {document["metadata"]["artifactRole"] for document in artifact_set.upload_documents} == {
        "context",
        "enriched_svg",
        "manifest",
    }
    assert all(
        document["metadata"]["bundleId"] == bundle_id
        and document["metadata"]["bundleDocumentPaths"] == bundle_document_paths
        for document in artifact_set.upload_documents
    )


def test_dry_run_summary_reports_payload_without_document_content(tmp_path: Path):
    builder = _load_builder_module()
    source_svg = tmp_path / "schema-reseau.svg"
    source_svg.write_text(SVG_SAMPLE, encoding="utf-8")
    artifact_sets = builder.build_artifact_sets(
        input_path=source_svg,
        output_dir=tmp_path / "out",
        recursive=False,
        write_enriched_svg=True,
        upload_prefix="svg-context",
    )

    summary = builder.build_dry_run_summary(
        artifact_sets=artifact_sets,
        api_url="https://api.snipara.com",
        project="mairie-2024",
        upload_enabled=True,
        upload_prefix="svg-context",
    )

    assert summary["dryRun"] is True
    assert summary["project"] == "mairie-2024"
    assert summary["upload"] is True
    assert summary["svgCount"] == 1
    assert summary["totals"]["localFiles"] == 3
    assert summary["totals"]["uploadDocuments"] == 3
    assert summary["totals"]["uploadBytes"] > 0
    assert summary["totals"]["estimatedTokens"] > 0
    assert "content" not in summary["bundles"][0]["uploadDocuments"][0]


def test_cli_dry_run_does_not_require_api_key_or_call_upload(tmp_path: Path):
    source_svg = tmp_path / "schema.svg"
    source_svg.write_text(SVG_SAMPLE, encoding="utf-8")
    env = os.environ.copy()
    env.pop("SNIPARA_API_KEY", None)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            str(source_svg),
            "--dry-run",
            "--upload",
            "--project",
            "mairie-2024",
            "--output-dir",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        check=True,
        env=env,
        text=True,
    )

    summary = json.loads(result.stdout)
    assert summary["dryRun"] is True
    assert summary["upload"] is True
    assert summary["totals"]["uploadDocuments"] == 3
    assert not result.stderr
