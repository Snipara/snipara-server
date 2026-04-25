"""VSDX parser that extracts Visio page topology into markdown-like context."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from .base import BinaryParseResult, decode_binary_content


SCHEMA_VERSION = "snipara.vsdx-context.v1"
CORE_NS = {"dc": "http://purl.org/dc/elements/1.1/"}


@dataclass(frozen=True)
class VsdxPageContext:
    """Extracted context for one Visio page."""

    index: int
    name: str
    path: str
    shapes: list[dict[str, str]]
    connectors: list[dict[str, str]]


class VsdxDocumentParser:
    """Extract page names, shape labels, connectors, and topology from VSDX files."""

    format = "vsdx"
    parser_name = "vsdx"
    parser_version = 1

    def parse(self, *, content: str, path: str) -> BinaryParseResult:
        raw_content = decode_binary_content(content)
        source_hash = hashlib.sha256(raw_content).hexdigest()
        bundle_id = _build_bundle_id(path=path, source_hash=source_hash)

        with ZipFile(BytesIO(raw_content)) as archive:
            metadata = self._read_core_metadata(archive)
            pages = self._read_pages(archive)

        shape_count = sum(len(page.shapes) for page in pages)
        connector_count = sum(len(page.connectors) for page in pages)
        labeled_shape_count = sum(
            1 for page in pages for shape in page.shapes if shape.get("label")
        )
        quality = _build_quality_report(
            page_count=len(pages),
            shape_count=shape_count,
            connector_count=connector_count,
            labeled_shape_count=labeled_shape_count,
        )
        warnings = _build_warnings(
            page_count=len(pages),
            shape_count=shape_count,
            connector_count=connector_count,
            labeled_shape_count=labeled_shape_count,
            quality=quality,
        )
        title = metadata.get("title") or f"VSDX diagram: {Path(path).name}"
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "bundleId": bundle_id,
            "sourcePath": path,
            "sourceHash": source_hash,
            "title": title,
            "metadata": metadata,
            "pages": [
                {
                    "index": page.index,
                    "name": page.name,
                    "path": page.path,
                    "shapes": page.shapes,
                    "connectors": page.connectors,
                }
                for page in pages
            ],
            "quality": quality,
            "warnings": warnings,
        }

        return BinaryParseResult(
            content=_render_markdown(manifest),
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            metadata={
                **metadata,
                "schemaVersion": SCHEMA_VERSION,
                "bundleId": bundle_id,
                "sourceHash": source_hash,
                "sourcePath": path,
                "assetClass": "DIAGRAM",
                "pageCount": len(pages),
                "shapeCount": shape_count,
                "connectorCount": connector_count,
                "textLabelCount": labeled_shape_count,
                "qualityScore": quality["score"],
                "qualityStatus": quality["status"],
                "parser": {"name": self.parser_name, "version": self.parser_version},
            },
        )

    def _read_core_metadata(self, archive: ZipFile) -> dict[str, str]:
        try:
            core_xml = archive.read("docProps/core.xml")
        except KeyError:
            return {}

        root = ET.fromstring(core_xml)
        metadata: dict[str, str] = {}
        title = root.findtext("dc:title", default="", namespaces=CORE_NS)
        creator = root.findtext("dc:creator", default="", namespaces=CORE_NS)
        if title.strip():
            metadata["title"] = _normalize_text(title)
        if creator.strip():
            metadata["creator"] = _normalize_text(creator)
        return metadata

    def _read_pages(self, archive: ZipFile) -> list[VsdxPageContext]:
        page_names = self._read_page_names(archive)
        page_paths = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"visio/pages/page\d+\.xml", name)),
            key=_natural_sort_key,
        )

        pages: list[VsdxPageContext] = []
        for index, page_path in enumerate(page_paths, start=1):
            root = ET.fromstring(archive.read(page_path))
            shapes = self._extract_shapes(root)
            connectors = self._extract_connectors(root, shapes)
            page_name = page_names.get(index) or f"Page {index}"
            pages.append(
                VsdxPageContext(
                    index=index,
                    name=page_name,
                    path=page_path,
                    shapes=shapes,
                    connectors=connectors,
                )
            )

        return pages

    def _read_page_names(self, archive: ZipFile) -> dict[int, str]:
        try:
            pages_xml = archive.read("visio/pages/pages.xml")
        except KeyError:
            return {}

        root = ET.fromstring(pages_xml)
        names: dict[int, str] = {}
        for index, page in enumerate(
            (node for node in root.iter() if _local_name(node.tag) == "Page"), start=1
        ):
            name = page.attrib.get("Name") or page.attrib.get("NameU") or f"Page {index}"
            names[index] = _normalize_text(name)
        return names

    def _extract_shapes(self, root: ET.Element) -> list[dict[str, str]]:
        shapes: list[dict[str, str]] = []
        for shape in (node for node in root.iter() if _local_name(node.tag) == "Shape"):
            shape_id = shape.attrib.get("ID")
            if not shape_id:
                continue

            text = _normalize_text(
                " ".join(
                    " ".join(text_node.itertext()) for text_node in _children(shape, "Text")
                )
            )
            name = _normalize_text(shape.attrib.get("Name") or shape.attrib.get("NameU") or "")
            label = text or name
            shape_type = _normalize_text(shape.attrib.get("Type") or "")
            master = shape.attrib.get("Master") or ""
            geometry = self._extract_geometry(shape)

            summary = {
                "id": shape_id,
                "label": label,
            }
            if name and name != label:
                summary["name"] = name
            if shape_type:
                summary["type"] = shape_type
            if master:
                summary["master"] = master
            summary.update(geometry)
            shapes.append(summary)
        return shapes

    def _extract_connectors(
        self, root: ET.Element, shapes: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        label_by_id = {
            shape["id"]: shape.get("label") or shape.get("name") or shape["id"] for shape in shapes
        }
        links: dict[str, dict[str, str]] = {}

        for connect in (node for node in root.iter() if _local_name(node.tag) == "Connect"):
            from_sheet = connect.attrib.get("FromSheet")
            to_sheet = connect.attrib.get("ToSheet")
            if not from_sheet or not to_sheet:
                continue

            endpoint = _endpoint_from_cell(connect.attrib.get("FromCell", ""))
            if not endpoint:
                continue

            connector = links.setdefault(from_sheet, {"connectorId": from_sheet})
            connector[endpoint] = to_sheet

        connectors: list[dict[str, str]] = []
        for connector_id, link in sorted(links.items(), key=lambda item: _natural_sort_key(item[0])):
            source_id = link.get("sourceId")
            target_id = link.get("targetId")
            connector = {"connectorId": connector_id}
            if source_id:
                connector["sourceId"] = source_id
                connector["sourceLabel"] = label_by_id.get(source_id, source_id)
            if target_id:
                connector["targetId"] = target_id
                connector["targetLabel"] = label_by_id.get(target_id, target_id)
            if source_id and target_id:
                connector["summary"] = (
                    f"{connector['sourceLabel']} -> {connector['targetLabel']}"
                )
            connectors.append(connector)
        return connectors

    def _extract_geometry(self, shape: ET.Element) -> dict[str, str]:
        cells = {
            cell.attrib.get("N", ""): cell.attrib.get("V", "")
            for cell in shape
            if _local_name(cell.tag) == "Cell"
        }
        geometry: dict[str, str] = {}
        for key in ("PinX", "PinY", "Width", "Height", "BeginX", "BeginY", "EndX", "EndY"):
            value = cells.get(key)
            if value:
                geometry[key] = value
        return geometry


def _render_markdown(manifest: dict[str, object]) -> str:
    pages = list(manifest["pages"])  # type: ignore[index]
    quality = manifest["quality"]  # type: ignore[index]
    warnings = manifest["warnings"]  # type: ignore[index]
    lines = [
        f"# {manifest['title']}",
        "",
        f"Bundle ID: `{manifest['bundleId']}`",
        f"Source path: `{manifest['sourcePath']}`",
        f"Source SHA-256: `{manifest['sourceHash']}`",
        f"Schema version: `{manifest['schemaVersion']}`",
        "",
        "## Context Quality",
        f"- Status: {quality['status']}",
        f"- Score: {quality['score']}",
    ]

    for key, value in quality["checks"].items():
        lines.append(f"- {key}: {value}")
    if quality["recommendations"]:
        lines.append("- Recommendations: " + "; ".join(quality["recommendations"]))

    if pages:
        lines.extend(["", "## Pages"])
        for page in pages:
            shapes = page["shapes"]
            connectors = page["connectors"]
            lines.extend(
                [
                    "",
                    f"### Page {page['index']}: {page['name']}",
                    f"- Page path: `{page['path']}`",
                    f"- Shapes: {len(shapes)}",
                    f"- Connectors: {len(connectors)}",
                ]
            )

            if shapes:
                lines.extend(["", "#### Shapes"])
                for shape in shapes[:120]:
                    label = shape.get("label") or shape.get("name") or shape["id"]
                    details = [f"id={shape['id']}"]
                    for key in ("type", "master", "PinX", "PinY", "Width", "Height"):
                        if key in shape:
                            details.append(f"{key}={shape[key]}")
                    lines.append(f"- {label} ({'; '.join(details)})")
                if len(shapes) > 120:
                    lines.append(f"- ... {len(shapes) - 120} additional shapes omitted")

            if connectors:
                lines.extend(["", "#### Connectors"])
                for connector in connectors[:120]:
                    summary = connector.get("summary") or connector.get("connectorId")
                    lines.append(f"- {summary} ({_compact_json(connector)})")
                if len(connectors) > 120:
                    lines.append(f"- ... {len(connectors) - 120} additional connectors omitted")
    else:
        lines.extend(["", "## Pages", "- No readable Visio page XML was found."])

    if warnings:
        lines.extend(["", "## Context Quality Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)

    lines.extend(
        [
            "",
            "## LLM Reuse Notes",
            "- Treat VSDX labels and connectors as deterministic diagram topology.",
            "- Use current client context as authority and historical VSDX diagrams as precedent.",
            "- Prefer editing the original VSDX when exact visual fidelity matters.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _build_quality_report(
    *,
    page_count: int,
    shape_count: int,
    connector_count: int,
    labeled_shape_count: int,
) -> dict[str, object]:
    checks = {
        "pages": 1.0 if page_count else 0.0,
        "shapes": min(shape_count / 8, 1.0),
        "shapeLabelCoverage": _ratio(labeled_shape_count, shape_count, empty_value=0.0),
        "connectors": 1.0 if connector_count else 0.5,
    }
    weights = {
        "pages": 0.25,
        "shapes": 0.25,
        "shapeLabelCoverage": 0.35,
        "connectors": 0.15,
    }
    score = round(sum(checks[key] * weights[key] for key in checks), 3)
    recommendations: list[str] = []
    if not page_count:
        recommendations.append("Export a VSDX with readable visio/pages XML parts.")
    if shape_count and checks["shapeLabelCoverage"] < 0.5:
        recommendations.append("Add text labels or descriptive names to important Visio shapes.")
    if not connector_count:
        recommendations.append("Use Visio connectors for relationships when topology matters.")

    if score >= 0.75:
        status = "good"
    elif score >= 0.55:
        status = "usable"
    else:
        status = "poor"

    return {
        "score": score,
        "status": status,
        "checks": {key: round(value, 3) for key, value in checks.items()},
        "recommendations": recommendations,
    }


def _build_warnings(
    *,
    page_count: int,
    shape_count: int,
    connector_count: int,
    labeled_shape_count: int,
    quality: dict[str, object],
) -> list[str]:
    warnings: list[str] = []
    if not page_count:
        warnings.append("No readable VSDX pages were found.")
    if shape_count and labeled_shape_count < max(2, shape_count // 4):
        warnings.append("Most Visio shapes are unlabeled; retrieval quality may be low.")
    if not connector_count:
        warnings.append("No Visio connectors were found; topology may be incomplete.")
    if quality["score"] < 0.55:
        warnings.append("VSDX context quality is low; add labels and connectors.")
    return warnings


def _build_bundle_id(*, path: str, source_hash: str) -> str:
    stable_input = f"{path}\0{source_hash}".encode()
    return f"vsdxctx_{hashlib.sha256(stable_input).hexdigest()[:16]}"


def _children(element: ET.Element, local_name: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child.tag) == local_name]


def _endpoint_from_cell(value: str) -> str | None:
    normalized = value.lower()
    if normalized.startswith("begin"):
        return "sourceId"
    if normalized.startswith("end"):
        return "targetId"
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def _natural_sort_key(value: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value))


def _ratio(numerator: int, denominator: int, *, empty_value: float) -> float:
    if denominator <= 0:
        return empty_value
    return min(numerator / denominator, 1.0)


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
