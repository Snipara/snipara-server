"""DOCX parser that extracts document structure into markdown-like content."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from .base import BinaryParseResult, decode_binary_content


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
CORE_NS = {"dc": "http://purl.org/dc/elements/1.1/"}


class DocxDocumentParser:
    """Extract headings, paragraphs, lists, and table cells from DOCX files."""

    format = "docx"
    parser_name = "docx"
    parser_version = 1

    def parse(self, *, content: str, path: str) -> BinaryParseResult:
        archive = ZipFile(BytesIO(decode_binary_content(content)))
        metadata = self._read_core_metadata(archive)
        lines = ["# DOCX Document", f"Source path: `{path}`"]

        if metadata:
            lines.extend(["", "## Metadata"])
            lines.extend(f"- {key}: {value}" for key, value in metadata.items())

        document_xml = archive.read("word/document.xml")
        root = ET.fromstring(document_xml)
        body = root.find("w:body", WORD_NS)
        content_lines: list[str] = []
        if body is not None:
            for child in body:
                local = self._local_name(child.tag)
                if local == "p":
                    rendered = self._render_paragraph(child)
                    if rendered:
                        content_lines.append(rendered)
                elif local == "tbl":
                    rendered_table = self._render_table(child)
                    if rendered_table:
                        content_lines.extend(["## Table", *rendered_table])

        if content_lines:
            lines.extend(["", "## Extracted Content", *content_lines])
        else:
            lines.extend(["", "## Extracted Content", "- No readable body text was found in this DOCX."])

        return BinaryParseResult(
            content="\n".join(lines).strip(),
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            metadata=metadata,
        )

    def _render_paragraph(self, paragraph: ET.Element) -> str | None:
        text = self._normalize_text(" ".join(paragraph.itertext()))
        if not text:
            return None

        style = paragraph.find("w:pPr/w:pStyle", WORD_NS)
        style_name = style.attrib.get(f"{{{WORD_NS['w']}}}val") if style is not None else None

        if style_name and style_name.lower().startswith("heading"):
            level = "".join(ch for ch in style_name if ch.isdigit()) or "2"
            depth = min(max(int(level), 1), 6)
            return f"{'#' * depth} {text}"

        if paragraph.find("w:pPr/w:numPr", WORD_NS) is not None:
            return f"- {text}"

        return text

    def _render_table(self, table: ET.Element) -> list[str]:
        rows: list[str] = []
        for row in table.findall("w:tr", WORD_NS):
            cells: list[str] = []
            for cell in row.findall("w:tc", WORD_NS):
                cell_text = self._normalize_text(" ".join(cell.itertext()))
                if cell_text:
                    cells.append(cell_text)
            if cells:
                rows.append("| " + " | ".join(cells) + " |")
        return rows

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
            metadata["title"] = " ".join(title.split())
        if creator.strip():
            metadata["creator"] = " ".join(creator.split())
        return metadata

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(value.split()).strip()
