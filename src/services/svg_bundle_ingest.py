"""Build upload-ready SVG companion bundles for hosted Snipara ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from src.services.binary_parsers import build_svg_context, enrich_svg_content
from src.services.binary_parsers.svg_context import manifest_to_json


@dataclass(frozen=True)
class SvgBundleDocument:
    """One upload-ready document generated from an SVG bundle."""

    path: str
    role: str
    content: str

    @property
    def byte_count(self) -> int:
        return len(self.content.encode("utf-8"))

    @property
    def estimated_tokens(self) -> int:
        if not self.content:
            return 0
        return max(1, self.byte_count // 4)

    def summary(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "role": self.role,
            "bytes": self.byte_count,
            "estimated_tokens": self.estimated_tokens,
        }


@dataclass(frozen=True)
class SvgBundleIngestPayload:
    """Upload-ready companion payload generated from one SVG."""

    bundle_id: str
    source_hash: str
    source_path: str
    schema_version: str
    title: str
    warnings: list[str]
    quality: dict[str, Any]
    documents: list[SvgBundleDocument]

    def summary(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "source_hash": self.source_hash,
            "source_path": self.source_path,
            "schema_version": self.schema_version,
            "title": self.title,
            "warnings": self.warnings,
            "quality": self.quality,
            "document_count": len(self.documents),
            "documents": [document.summary() for document in self.documents],
            "totals": {
                "bytes": sum(document.byte_count for document in self.documents),
                "estimated_tokens": sum(document.estimated_tokens for document in self.documents),
            },
        }


def build_svg_bundle_ingest_payload(
    *,
    svg_content: str,
    source_path: str,
    upload_prefix: str = "svg-context",
    include_enriched_svg: bool = True,
) -> SvgBundleIngestPayload:
    """Create markdown upload documents for one source SVG."""

    bundle = build_svg_context(content=svg_content, path=source_path)
    upload_base = _upload_base_path(source_path=source_path, upload_prefix=upload_prefix)
    documents = [
        SvgBundleDocument(
            path=f"{upload_base}.context.md",
            role="context",
            content=bundle.markdown,
        ),
        SvgBundleDocument(
            path=f"{upload_base}.manifest.md",
            role="manifest",
            content=_render_manifest_markdown(bundle),
        ),
    ]

    if include_enriched_svg:
        enriched_svg = enrich_svg_content(content=svg_content, path=source_path)
        documents.append(
            SvgBundleDocument(
                path=f"{upload_base}.enriched-svg.md",
                role="enriched_svg",
                content=_render_enriched_svg_markdown(bundle=bundle, enriched_svg=enriched_svg),
            )
        )

    return SvgBundleIngestPayload(
        bundle_id=bundle.bundle_id,
        source_hash=bundle.source_hash,
        source_path=source_path,
        schema_version=bundle.manifest["schemaVersion"],
        title=bundle.title,
        warnings=bundle.warnings,
        quality=bundle.manifest["quality"],
        documents=documents,
    )


def _upload_base_path(*, source_path: str, upload_prefix: str) -> str:
    normalized_source = source_path.replace("\\", "/").lstrip("/")
    source_base = PurePosixPath(normalized_source).with_suffix("").as_posix()
    prefix = upload_prefix.strip("/")
    return f"{prefix}/{source_base}" if prefix else source_base


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
