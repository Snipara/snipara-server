"""Structured SVG context extraction for diagram reuse workflows."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

MEANINGFUL_ELEMENT_TAGS = {
    "circle",
    "ellipse",
    "g",
    "image",
    "line",
    "path",
    "polygon",
    "polyline",
    "rect",
    "text",
    "tspan",
    "use",
}
CONNECTOR_TAGS = {"line", "path", "polyline"}
LABEL_ATTRIBUTE_NAMES = {
    "aria-label",
    "data-label",
    "data-name",
    "data-title",
    "inkscape:label",
    "label",
    "name",
    "title",
}
GEOMETRY_ATTRIBUTE_NAMES = {
    "cx",
    "cy",
    "height",
    "points",
    "r",
    "rx",
    "ry",
    "viewBox",
    "width",
    "x",
    "x1",
    "x2",
    "y",
    "y1",
    "y2",
}
STYLE_ATTRIBUTE_NAMES = {
    "class",
    "fill",
    "font-family",
    "font-size",
    "stroke",
    "stroke-width",
    "style",
    "transform",
}
RELATION_ATTRIBUTE_NAMES = {
    "data-from",
    "data-source",
    "data-target",
    "data-to",
    "from",
    "source",
    "target",
    "to",
}


@dataclass(frozen=True)
class SvgContextBundle:
    """Companion artifacts generated from one SVG."""

    manifest: dict[str, Any]
    markdown: str
    title: str
    description: str
    bundle_id: str
    source_hash: str
    metadata: dict[str, Any]
    warnings: list[str]


def build_svg_context(*, content: str, path: str) -> SvgContextBundle:
    """Extract deterministic, LLM-readable context from an SVG document."""

    root = ET.fromstring(content)
    source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    bundle_id = _build_bundle_id(path=path, source_hash=source_hash)

    titles = _collect_text(root, {"title"})
    descriptions = _collect_text(root, {"desc"})
    text_labels = _collect_text(root, {"text", "tspan"})
    accessibility_labels = _collect_attributes(root, LABEL_ATTRIBUTE_NAMES)
    elements = _collect_elements(root)
    connectors = _collect_connectors(elements)
    style_summary = _summarize_styles(elements)
    metadata = _collect_metadata(root)
    quality = _build_quality_report(
        titles=titles,
        descriptions=descriptions,
        text_labels=text_labels,
        accessibility_labels=accessibility_labels,
        elements=elements,
        connectors=connectors,
        metadata=metadata,
    )
    warnings = _build_warnings(
        titles=titles,
        descriptions=descriptions,
        text_labels=text_labels,
        accessibility_labels=accessibility_labels,
        elements=elements,
        quality=quality,
    )

    title = titles[0] if titles else f"SVG diagram: {Path(path).name}"
    description = _choose_description(descriptions, text_labels, accessibility_labels)

    manifest: dict[str, Any] = {
        "schemaVersion": "snipara.svg-context.v1",
        "bundleId": bundle_id,
        "sourcePath": path,
        "sourceHash": source_hash,
        "title": title,
        "description": description,
        "metadata": metadata,
        "content": {
            "titles": titles,
            "descriptions": descriptions,
            "textLabels": text_labels,
            "accessibilityLabels": accessibility_labels,
        },
        "elements": elements,
        "connectors": connectors,
        "styleSummary": style_summary,
        "quality": quality,
        "warnings": warnings,
    }

    return SvgContextBundle(
        manifest=manifest,
        markdown=_render_markdown(manifest),
        title=title,
        description=description,
        bundle_id=bundle_id,
        source_hash=source_hash,
        metadata={
            **metadata,
            "schemaVersion": manifest["schemaVersion"],
            "bundleId": bundle_id,
            "sourceHash": source_hash,
            "elementCount": len(elements),
            "connectorCount": len(connectors),
            "textLabelCount": len(text_labels),
            "qualityScore": quality["score"],
            "qualityStatus": quality["status"],
        },
        warnings=warnings,
    )


def enrich_svg_content(*, content: str, path: str) -> str:
    """Return an SVG copy with root title/description metadata when absent."""

    root = ET.fromstring(content)
    bundle = build_svg_context(content=content, path=path)
    namespace = _namespace_uri(root.tag)
    tag_prefix = f"{{{namespace}}}" if namespace else ""

    if namespace:
        ET.register_namespace("", namespace)

    insert_at = 0
    if _direct_child(root, "title") is None:
        title = ET.Element(f"{tag_prefix}title")
        title.text = bundle.title
        root.insert(insert_at, title)
        insert_at += 1

    if _direct_child(root, "desc") is None:
        desc = ET.Element(f"{tag_prefix}desc")
        desc.text = bundle.description
        root.insert(insert_at, desc)

    root.attrib["data-snipara-context"] = bundle.manifest["schemaVersion"]
    root.attrib["data-snipara-bundle-id"] = bundle.bundle_id
    root.attrib["data-snipara-source-sha256"] = bundle.source_hash
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def manifest_to_json(manifest: dict[str, Any]) -> str:
    """Serialize a manifest with stable formatting for companion files."""

    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _collect_metadata(root: ET.Element) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for name in ("viewBox", "width", "height"):
        value = root.attrib.get(name)
        if value:
            metadata[name] = value

    width = root.attrib.get("width")
    height = root.attrib.get("height")
    if width or height:
        metadata["size"] = f"{width or '?'} x {height or '?'}"

    return metadata


def _collect_elements(root: ET.Element) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for index, element in enumerate(root.iter()):
        tag = _local_name(element.tag)
        if tag not in MEANINGFUL_ELEMENT_TAGS:
            continue

        attributes = _normalized_attributes(element)
        direct_text = _normalized_text("".join(element.itertext())) if tag in {"text", "tspan"} else ""
        title = _direct_child_text(element, "title")
        desc = _direct_child_text(element, "desc")
        label = _choose_label(attributes, direct_text, title, desc)
        element_id = attributes.get("id")

        if not label and not element_id and tag in {"g", "path", "use"}:
            continue

        geometry = _pick_attributes(attributes, GEOMETRY_ATTRIBUTE_NAMES)
        style = _pick_attributes(attributes, STYLE_ATTRIBUTE_NAMES)
        relations = _pick_attributes(attributes, RELATION_ATTRIBUTE_NAMES)

        summary: dict[str, Any] = {
            "index": index,
            "tag": tag,
            "kind": _infer_kind(label=label, element_id=element_id, attributes=attributes, tag=tag),
        }
        if element_id:
            summary["id"] = element_id
        if label:
            summary["label"] = label
        if direct_text and direct_text != label:
            summary["text"] = direct_text
        if title:
            summary["title"] = title
        if desc:
            summary["description"] = desc
        if geometry:
            summary["geometry"] = geometry
        if style:
            summary["style"] = style
        if relations:
            summary["relations"] = relations

        href = attributes.get("href")
        if href:
            summary["href"] = href

        elements.append(summary)

    return elements


def _collect_connectors(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    connectors: list[dict[str, Any]] = []
    for element in elements:
        tag = str(element.get("tag", ""))
        if tag not in CONNECTOR_TAGS:
            continue

        connector: dict[str, Any] = {
            "tag": tag,
            "kind": element.get("kind", tag),
        }
        for key in ("id", "label", "geometry", "style", "relations"):
            if key in element:
                connector[key] = element[key]

        geometry = connector.get("geometry", {})
        if tag == "line" and isinstance(geometry, dict):
            connector["points"] = [
                {"x": geometry.get("x1"), "y": geometry.get("y1")},
                {"x": geometry.get("x2"), "y": geometry.get("y2")},
            ]
        elif tag == "polyline" and isinstance(geometry, dict) and "points" in geometry:
            connector["points"] = geometry["points"]
        elif tag == "path" and isinstance(geometry, dict) and "d" in geometry:
            connector["pathData"] = geometry["d"]

        connectors.append(connector)

    return connectors


def _summarize_styles(elements: list[dict[str, Any]]) -> dict[str, list[str]]:
    fills: set[str] = set()
    strokes: set[str] = set()
    stroke_widths: set[str] = set()
    fonts: set[str] = set()
    classes: set[str] = set()

    for element in elements:
        style = element.get("style")
        if not isinstance(style, dict):
            continue

        style_map = dict(style)
        inline_style = style_map.get("style")
        if isinstance(inline_style, str):
            style_map.update(_parse_inline_style(inline_style))

        _add_if_meaningful(fills, style_map.get("fill"))
        _add_if_meaningful(strokes, style_map.get("stroke"))
        _add_if_meaningful(stroke_widths, style_map.get("stroke-width"))
        _add_if_meaningful(fonts, style_map.get("font-family"))
        _add_if_meaningful(classes, style_map.get("class"))

    return {
        "fills": sorted(fills)[:20],
        "strokes": sorted(strokes)[:20],
        "strokeWidths": sorted(stroke_widths)[:10],
        "fonts": sorted(fonts)[:10],
        "classes": sorted(classes)[:20],
    }


def _render_markdown(manifest: dict[str, Any]) -> str:
    content = manifest["content"]
    metadata = manifest["metadata"]
    elements = manifest["elements"]
    connectors = manifest["connectors"]
    style_summary = manifest["styleSummary"]
    quality = manifest["quality"]
    warnings = manifest["warnings"]

    lines = [
        f"# {manifest['title']}",
        "",
        f"Bundle ID: `{manifest['bundleId']}`",
        f"Source path: `{manifest['sourcePath']}`",
        f"Source SHA-256: `{manifest['sourceHash']}`",
        f"Schema version: `{manifest['schemaVersion']}`",
        "",
        "## Summary",
        manifest["description"],
    ]

    if metadata:
        lines.extend(["", "## Canvas Metadata"])
        lines.extend(f"- {key}: {value}" for key, value in metadata.items())

    lines.extend(
        [
            "",
            "## Context Quality",
            f"- Status: {quality['status']}",
            f"- Score: {quality['score']}",
        ]
    )
    for key, value in quality["checks"].items():
        lines.append(f"- {key}: {value}")
    if quality["recommendations"]:
        lines.append("- Recommendations: " + "; ".join(quality["recommendations"]))

    _append_values(lines, "Titles", content["titles"], limit=5)
    _append_values(lines, "Descriptions", content["descriptions"], limit=8)
    _append_values(lines, "Text Labels", content["textLabels"], limit=80)
    _append_values(lines, "Accessibility Labels", content["accessibilityLabels"], limit=40)

    if elements:
        lines.extend(["", "## Diagram Elements"])
        for element in elements[:120]:
            label = element.get("label") or element.get("id") or f"{element['tag']} #{element['index']}"
            details = [f"kind={element['kind']}", f"tag={element['tag']}"]
            if "id" in element:
                details.append(f"id={element['id']}")
            if "geometry" in element:
                details.append(f"geometry={_compact_json(element['geometry'])}")
            if "relations" in element:
                details.append(f"relations={_compact_json(element['relations'])}")
            lines.append(f"- {label} ({'; '.join(details)})")
        if len(elements) > 120:
            lines.append(f"- ... {len(elements) - 120} additional elements omitted")

    if connectors:
        lines.extend(["", "## Connectors"])
        for connector in connectors[:80]:
            label = connector.get("label") or connector.get("id") or connector["tag"]
            details = [f"kind={connector['kind']}", f"tag={connector['tag']}"]
            if "relations" in connector:
                details.append(f"relations={_compact_json(connector['relations'])}")
            if "points" in connector:
                details.append(f"points={_compact_json(connector['points'])}")
            lines.append(f"- {label} ({'; '.join(details)})")
        if len(connectors) > 80:
            lines.append(f"- ... {len(connectors) - 80} additional connectors omitted")

    if any(style_summary.values()):
        lines.extend(["", "## Style Summary"])
        for key, values in style_summary.items():
            if values:
                lines.append(f"- {key}: {', '.join(values)}")

    if warnings:
        lines.extend(["", "## Context Quality Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)

    lines.extend(
        [
            "",
            "## Companion Artifacts",
            f"- Bundle ID: `{manifest['bundleId']}`",
            f"- Source SVG: `{manifest['sourcePath']}`",
            "- Local companions use the same base filename and this bundle ID.",
            "- Uploaded companions should preserve this bundle ID in their document body.",
            "",
            "## LLM Reuse Notes",
            "- Treat this SVG as the source of truth for layout, coordinates, labels, and visual conventions.",
            "- Use the manifest JSON for exact element metadata and this markdown file for semantic retrieval.",
            "- Prefer transforming the original SVG or enriched SVG when exact reproduction matters.",
        ]
    )

    return "\n".join(lines).strip() + "\n"


def _build_bundle_id(*, path: str, source_hash: str) -> str:
    stable_input = f"{path}\0{source_hash}".encode()
    return f"svgctx_{hashlib.sha256(stable_input).hexdigest()[:16]}"


def _append_values(lines: list[str], title: str, values: list[str], *, limit: int) -> None:
    if not values:
        return
    lines.extend(["", f"## {title}"])
    lines.extend(f"- {value}" for value in values[:limit])
    if len(values) > limit:
        lines.append(f"- ... {len(values) - limit} additional values omitted")


def _build_warnings(
    *,
    titles: list[str],
    descriptions: list[str],
    text_labels: list[str],
    accessibility_labels: list[str],
    elements: list[dict[str, Any]],
    quality: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if not titles:
        warnings.append("No root or embedded SVG title was found.")
    if not descriptions:
        warnings.append("No SVG description was found.")
    if not text_labels and not accessibility_labels:
        warnings.append("No text or accessibility labels were found; LLM context may be sparse.")
    if elements and len([element for element in elements if element.get("label")]) < max(3, len(elements) // 10):
        warnings.append("Most graphical elements are unlabeled; add ids, aria-labels, or data-labels for better reuse.")
    if quality["score"] < 0.55:
        warnings.append("SVG context quality is low; add labels, title, description, and accessibility metadata.")
    return warnings


def _build_quality_report(
    *,
    titles: list[str],
    descriptions: list[str],
    text_labels: list[str],
    accessibility_labels: list[str],
    elements: list[dict[str, Any]],
    connectors: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    labeled_elements = len([element for element in elements if element.get("label")])
    label_count = len(text_labels) + len(accessibility_labels)
    connector_labels = len(
        [
            connector
            for connector in connectors
            if connector.get("label") or connector.get("relations")
        ]
    )

    checks = {
        "title": 1.0 if titles else 0.0,
        "description": 1.0 if descriptions else 0.0,
        "visibleLabels": min(label_count / 8, 1.0),
        "elementLabelCoverage": _ratio(labeled_elements, len(elements), empty_value=0.7),
        "connectorMetadata": _ratio(connector_labels, len(connectors), empty_value=1.0),
        "canvasMetadata": 1.0 if any(key in metadata for key in ("viewBox", "width", "height")) else 0.0,
    }
    weights = {
        "title": 0.15,
        "description": 0.15,
        "visibleLabels": 0.25,
        "elementLabelCoverage": 0.25,
        "connectorMetadata": 0.10,
        "canvasMetadata": 0.10,
    }
    score = round(sum(checks[key] * weights[key] for key in checks), 3)
    recommendations: list[str] = []
    if checks["title"] < 1:
        recommendations.append("Add a root <title> naming the diagram.")
    if checks["description"] < 1:
        recommendations.append("Add a root <desc> describing the technical purpose.")
    if checks["visibleLabels"] < 0.5:
        recommendations.append("Add visible <text> labels for important equipment and zones.")
    if checks["elementLabelCoverage"] < 0.4:
        recommendations.append("Add ids, aria-labels, or data-labels to important SVG groups and shapes.")
    if connectors and checks["connectorMetadata"] < 0.5:
        recommendations.append("Add labels or data-from/data-to metadata to connectors.")
    if checks["canvasMetadata"] < 1:
        recommendations.append("Add viewBox or width/height metadata for layout reference.")

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


def _ratio(numerator: int, denominator: int, *, empty_value: float) -> float:
    if denominator <= 0:
        return empty_value
    return min(numerator / denominator, 1.0)


def _choose_description(
    descriptions: list[str],
    text_labels: list[str],
    accessibility_labels: list[str],
) -> str:
    if descriptions:
        return descriptions[0]

    labels = list(dict.fromkeys([*text_labels, *accessibility_labels]))
    if labels:
        preview = ", ".join(labels[:12])
        return f"SVG diagram containing these detected labels: {preview}."

    return "SVG diagram with no human-readable labels detected."


def _choose_label(
    attributes: dict[str, str],
    direct_text: str,
    title: str,
    desc: str,
) -> str:
    for name in LABEL_ATTRIBUTE_NAMES:
        value = attributes.get(name)
        if value:
            return value
    for value in (direct_text, title, desc):
        if value:
            return value

    element_id = attributes.get("id")
    if element_id and _looks_descriptive(element_id):
        return _humanize_identifier(element_id)

    return ""


def _infer_kind(
    *,
    label: str,
    element_id: str | None,
    attributes: dict[str, str],
    tag: str,
) -> str:
    haystack = " ".join(
        value
        for value in [
            label,
            element_id or "",
            attributes.get("class", ""),
            attributes.get("data-kind", ""),
            attributes.get("data-type", ""),
        ]
        if value
    ).lower()

    keyword_map = [
        (("switch", "poe"), "network_switch"),
        (("routeur", "router"), "router"),
        (("firewall", "pare-feu"), "firewall"),
        (("dante", "aes67"), "audio_network"),
        (("vlan",), "network_segment"),
        (("dsp", "processeur audio"), "audio_dsp"),
        (("matrice", "matrix", "hdmi"), "video_matrix"),
        (("camera", "caméra", "ptz"), "camera"),
        (("micro", "mic", "microphone"), "microphone"),
        (("haut-parleur", "speaker", "enceinte"), "speaker"),
        (("écran", "ecran", "display", "screen", "projecteur"), "display"),
        (("rack", "baie"), "rack"),
        (("rj45", "ethernet"), "ethernet_link"),
        (("server", "serveur"), "server"),
        (("control", "contrôle", "controle"), "control_system"),
    ]
    for keywords, kind in keyword_map:
        if any(keyword in haystack for keyword in keywords):
            return kind

    if tag in CONNECTOR_TAGS:
        return "connector"
    return tag


def _collect_text(root: ET.Element, names: set[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for element in root.iter():
        if _local_name(element.tag) not in names:
            continue
        value = _normalized_text("".join(element.itertext()))
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _collect_attributes(root: ET.Element, names: set[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for element in root.iter():
        attrs = _normalized_attributes(element)
        for attr_name, attr_value in attrs.items():
            if attr_name not in names:
                continue
            value = _normalized_text(attr_value)
            if value and value not in seen:
                seen.add(value)
                values.append(value)
    return values


def _normalized_attributes(element: ET.Element) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for name, value in element.attrib.items():
        local_name = _local_name(name)
        normalized_value = _normalized_text(value)
        if normalized_value:
            attrs[local_name] = _truncate(normalized_value)
    return attrs


def _pick_attributes(attributes: dict[str, str], names: set[str]) -> dict[str, str]:
    picked = {name: value for name, value in attributes.items() if name in names}
    if "d" in attributes:
        picked["d"] = _truncate(attributes["d"], limit=500)
    return picked


def _parse_inline_style(style: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for declaration in style.split(";"):
        if ":" not in declaration:
            continue
        key, value = declaration.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _direct_child(root: ET.Element, name: str) -> ET.Element | None:
    for child in list(root):
        if _local_name(child.tag) == name:
            return child
    return None


def _direct_child_text(root: ET.Element, name: str) -> str:
    child = _direct_child(root, name)
    if child is None:
        return ""
    return _normalized_text("".join(child.itertext()))


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    if ":" in tag:
        return tag.rsplit(":", 1)[-1]
    return tag


def _namespace_uri(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def _normalized_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _truncate(value: str, *, limit: int = 240) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _add_if_meaningful(values: set[str], value: Any) -> None:
    if not isinstance(value, str):
        return
    normalized = value.strip()
    if normalized and normalized.lower() not in {"none", "transparent"}:
        values.add(normalized)


def _looks_descriptive(identifier: str) -> bool:
    return bool(re.search(r"[A-Za-z]{3,}", identifier)) and not re.fullmatch(r"[A-Za-z]*\d+", identifier)


def _humanize_identifier(identifier: str) -> str:
    return re.sub(r"[-_]+", " ", identifier).strip()
