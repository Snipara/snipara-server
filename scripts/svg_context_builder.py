#!/usr/bin/env python3
"""Build Snipara companion context files from SVG diagrams."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
MCP_ROOT = SCRIPT_DIR.parent
SVG_CONTEXT_PATH = MCP_ROOT / "src" / "services" / "binary_parsers" / "svg_context.py"


def _load_svg_context_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("snipara_svg_context", SVG_CONTEXT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load SVG context module: {SVG_CONTEXT_PATH}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


svg_context = _load_svg_context_module()
build_svg_context = svg_context.build_svg_context
enrich_svg_content = svg_context.enrich_svg_content
manifest_to_json = svg_context.manifest_to_json


@dataclass(frozen=True)
class SvgArtifactSet:
    """Generated local files and upload-ready documents for one SVG."""

    source_svg: Path
    bundle_id: str
    written_paths: list[Path]
    upload_documents: list[dict[str, Any]]


def estimate_token_count(content: str) -> int:
    """Return a conservative token estimate for dry-run summaries."""

    if not content:
        return 0
    return max(1, len(content.encode("utf-8")) // 4)


def _iter_svg_files(input_path: Path, *, recursive: bool) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".svg":
            raise SystemExit(f"Input file is not an SVG: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise SystemExit(f"Input path not found: {input_path}")

    pattern = "**/*.svg" if recursive else "*.svg"
    return sorted(path for path in input_path.glob(pattern) if path.is_file())


def _target_base(svg_path: Path, *, input_root: Path, output_dir: Path | None) -> Path:
    if output_dir is None:
        return svg_path.with_suffix("")

    if input_root.is_dir():
        relative = svg_path.relative_to(input_root).with_suffix("")
    else:
        relative = Path(svg_path.stem)

    return output_dir / relative


def _source_ref(svg_path: Path, *, input_root: Path) -> str:
    if input_root.is_dir():
        return svg_path.relative_to(input_root).as_posix()

    try:
        return svg_path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return svg_path.name


def _upload_base_path(svg_path: Path, *, input_root: Path, upload_prefix: str) -> str:
    if input_root.is_dir():
        relative = svg_path.relative_to(input_root).with_suffix("")
    else:
        relative = Path(svg_path.stem)

    parts = [part for part in [upload_prefix.strip("/"), relative.as_posix()] if part]
    return "/".join(parts)


def _render_manifest_markdown(bundle: Any) -> str:
    return "\n".join(
        [
            f"# SVG Manifest: {bundle.title}",
            "",
            f"Bundle ID: `{bundle.bundle_id}`",
            f"Source path: `{bundle.manifest['sourcePath']}`",
            f"Source SHA-256: `{bundle.source_hash}`",
            f"Schema version: `{bundle.manifest['schemaVersion']}`",
            "",
            "This document stores the structured JSON manifest for the SVG companion bundle.",
            "",
            "```json",
            manifest_to_json(bundle.manifest).rstrip(),
            "```",
            "",
        ]
    )


def _render_enriched_svg_markdown(*, bundle: Any, enriched_svg: str) -> str:
    return "\n".join(
        [
            f"# Enriched SVG Source: {bundle.title}",
            "",
            f"Bundle ID: `{bundle.bundle_id}`",
            f"Source path: `{bundle.manifest['sourcePath']}`",
            f"Source SHA-256: `{bundle.source_hash}`",
            f"Schema version: `{bundle.manifest['schemaVersion']}`",
            "",
            "This document stores the enriched SVG XML for exact-layout reference.",
            "",
            "```xml",
            enriched_svg.rstrip(),
            "```",
            "",
        ]
    )


def build_artifact_sets(
    *,
    input_path: Path,
    output_dir: Path | None,
    recursive: bool,
    write_enriched_svg: bool,
    upload_prefix: str,
) -> list[SvgArtifactSet]:
    """Generate companion files and upload-ready markdown documents."""

    svg_files = _iter_svg_files(input_path, recursive=recursive)
    artifact_sets: list[SvgArtifactSet] = []

    for svg_path in svg_files:
        content = svg_path.read_text(encoding="utf-8")
        source_ref = _source_ref(svg_path, input_root=input_path)
        bundle = build_svg_context(content=content, path=source_ref)
        target_base = _target_base(svg_path, input_root=input_path, output_dir=output_dir)
        target_base.parent.mkdir(parents=True, exist_ok=True)
        upload_base = _upload_base_path(svg_path, input_root=input_path, upload_prefix=upload_prefix)

        written: list[Path] = []
        upload_documents: list[dict[str, Any]] = [
            {
                "path": f"{upload_base}.context.md",
                "role": "context",
                "content": bundle.markdown,
            },
            {
                "path": f"{upload_base}.manifest.md",
                "role": "manifest",
                "content": _render_manifest_markdown(bundle),
            },
        ]

        manifest_path = target_base.with_suffix(".manifest.json")
        manifest_path.write_text(manifest_to_json(bundle.manifest), encoding="utf-8")
        written.append(manifest_path)

        context_path = target_base.with_suffix(".context.md")
        context_path.write_text(bundle.markdown, encoding="utf-8")
        written.append(context_path)

        if write_enriched_svg:
            enriched_svg = enrich_svg_content(content=content, path=source_ref)
            enriched_path = target_base.with_suffix(".enriched.svg")
            enriched_path.write_text(enriched_svg, encoding="utf-8")
            written.append(enriched_path)
            upload_documents.append(
                {
                    "path": f"{upload_base}.enriched-svg.md",
                    "role": "enriched_svg",
                    "content": _render_enriched_svg_markdown(
                        bundle=bundle,
                        enriched_svg=enriched_svg,
                    ),
                }
            )

        bundle_document_paths = [document["path"] for document in upload_documents]
        for document in upload_documents:
            document["metadata"] = {
                "schemaVersion": "snipara.svg-context-builder.v1",
                "svgContextSchemaVersion": bundle.manifest["schemaVersion"],
                "bundleId": bundle.bundle_id,
                "sourceHash": bundle.source_hash,
                "sourcePath": source_ref,
                "artifactRole": document["role"],
                "bundleDocumentPaths": bundle_document_paths,
            }
            del document["role"]

        artifact_sets.append(
            SvgArtifactSet(
                source_svg=svg_path,
                bundle_id=bundle.bundle_id,
                written_paths=written,
                upload_documents=upload_documents,
            )
        )

    return artifact_sets


def build_files(
    *,
    input_path: Path,
    output_dir: Path | None,
    recursive: bool,
    write_enriched_svg: bool,
    upload_prefix: str = "",
) -> list[Path]:
    """Generate companion files and return paths written."""

    artifact_sets = build_artifact_sets(
        input_path=input_path,
        output_dir=output_dir,
        recursive=recursive,
        write_enriched_svg=write_enriched_svg,
        upload_prefix=upload_prefix,
    )
    return [path for artifact_set in artifact_sets for path in artifact_set.written_paths]


def build_dry_run_summary(
    *,
    artifact_sets: list[SvgArtifactSet],
    api_url: str,
    project: str | None,
    upload_enabled: bool,
    upload_prefix: str,
) -> dict[str, Any]:
    """Build a network-free summary of local artifacts and upload documents."""

    bundles: list[dict[str, Any]] = []
    total_upload_bytes = 0
    total_estimated_tokens = 0
    total_upload_documents = 0
    total_local_files = 0

    for artifact_set in artifact_sets:
        upload_documents: list[dict[str, Any]] = []
        for document in artifact_set.upload_documents:
            byte_count = len(document["content"].encode("utf-8"))
            estimated_tokens = estimate_token_count(document["content"])
            total_upload_bytes += byte_count
            total_estimated_tokens += estimated_tokens
            total_upload_documents += 1
            upload_documents.append(
                {
                    "path": document["path"],
                    "bytes": byte_count,
                    "estimatedTokens": estimated_tokens,
                }
            )

        local_files = [str(path) for path in artifact_set.written_paths]
        total_local_files += len(local_files)
        bundles.append(
            {
                "sourceSvg": str(artifact_set.source_svg),
                "bundleId": artifact_set.bundle_id,
                "localFiles": local_files,
                "uploadDocuments": upload_documents,
            }
        )

    warnings: list[str] = []
    if upload_enabled and not project:
        warnings.append("No project provided; dry-run skipped upload validation.")

    return {
        "dryRun": True,
        "apiUrl": api_url,
        "project": project,
        "upload": upload_enabled,
        "uploadPrefix": upload_prefix,
        "svgCount": len(artifact_sets),
        "bundles": bundles,
        "totals": {
            "localFiles": total_local_files,
            "uploadDocuments": total_upload_documents,
            "uploadBytes": total_upload_bytes,
            "estimatedTokens": total_estimated_tokens,
        },
        "warnings": warnings,
    }


def _call_mcp_tool(
    *,
    api_url: str,
    project: str,
    api_key: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    endpoint = f"{api_url.rstrip('/')}/mcp/{project}"
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }
    request = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {endpoint}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach {endpoint}: {exc.reason}") from exc

    data = json.loads(response_body)
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data


def upload_documents(
    *,
    api_url: str,
    project: str,
    api_key: str,
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """Upload generated markdown companions through hosted MCP."""

    return _call_mcp_tool(
        api_url=api_url,
        project=project,
        api_key=api_key,
        tool_name="rlm_sync_documents",
        arguments={"documents": documents, "delete_missing": False},
    )


def trigger_reindex(
    *,
    api_url: str,
    project: str,
    api_key: str,
    mode: str,
) -> dict[str, Any]:
    """Trigger document reindexing through hosted MCP."""

    return _call_mcp_tool(
        api_url=api_url,
        project=project,
        api_key=api_key,
        tool_name="rlm_reindex",
        arguments={"kind": "doc", "mode": mode},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="SVG file or directory containing SVG files")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Directory for generated companion files. Defaults to each SVG's directory.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively process SVG files when input is a directory.",
    )
    parser.add_argument(
        "--no-enriched-svg",
        action="store_true",
        help="Skip writing .enriched.svg copies.",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload generated markdown companion documents to Snipara through hosted MCP.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate local artifacts and print upload summary without calling Snipara.",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("SNIPARA_PROJECT") or os.environ.get("SNIPARA_PROJECT_ID"),
        help="Snipara project slug/id for upload. Defaults to SNIPARA_PROJECT or SNIPARA_PROJECT_ID.",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("SNIPARA_API_URL", "https://api.snipara.com"),
        help="Snipara API URL. Defaults to SNIPARA_API_URL or https://api.snipara.com.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("SNIPARA_API_KEY"),
        help="Snipara API key. Defaults to SNIPARA_API_KEY.",
    )
    parser.add_argument(
        "--upload-prefix",
        default="svg-context",
        help="Document path prefix for uploaded companion markdown files.",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Trigger an incremental document reindex after upload.",
    )
    parser.add_argument(
        "--reindex-mode",
        choices=("incremental", "full"),
        default="incremental",
        help="Document reindex mode when --reindex is set.",
    )
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    artifact_sets = build_artifact_sets(
        input_path=input_path,
        output_dir=args.output_dir.expanduser().resolve() if args.output_dir else None,
        recursive=args.recursive,
        write_enriched_svg=not args.no_enriched_svg,
        upload_prefix=args.upload_prefix,
    )

    written = [path for artifact_set in artifact_sets for path in artifact_set.written_paths]

    if args.dry_run:
        summary = build_dry_run_summary(
            artifact_sets=artifact_sets,
            api_url=args.api_url,
            project=args.project,
            upload_enabled=args.upload,
            upload_prefix=args.upload_prefix,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    if args.upload:
        if not args.project:
            raise SystemExit("--project or SNIPARA_PROJECT/SNIPARA_PROJECT_ID is required for upload")
        if not args.api_key:
            raise SystemExit("--api-key or SNIPARA_API_KEY is required for upload")

        documents = [
            document
            for artifact_set in artifact_sets
            for document in artifact_set.upload_documents
        ]
        if documents:
            result = upload_documents(
                api_url=args.api_url,
                project=args.project,
                api_key=args.api_key,
                documents=documents,
            )
            if args.reindex:
                reindex_result = trigger_reindex(
                    api_url=args.api_url,
                    project=args.project,
                    api_key=args.api_key,
                    mode=args.reindex_mode,
                )
                result = {"upload": result, "reindex": reindex_result}
            print(json.dumps(result, indent=2, sort_keys=True))

    for artifact_set in artifact_sets:
        print(f"# {artifact_set.source_svg} bundle={artifact_set.bundle_id}")
    for path in written:
        print(path)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
