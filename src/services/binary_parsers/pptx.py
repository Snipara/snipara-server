"""PPTX parser that extracts slide text and notes into markdown-like content."""

from __future__ import annotations

import re
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from .base import BinaryParseResult, decode_binary_content


SLIDE_TEXT_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
CORE_NS = {"dc": "http://purl.org/dc/elements/1.1/"}


class PptxDocumentParser:
    """Extract slide titles, body text, and speaker notes from PPTX files."""

    format = "pptx"
    parser_name = "pptx"
    parser_version = 1

    def parse(self, *, content: str, path: str) -> BinaryParseResult:
        archive = ZipFile(BytesIO(decode_binary_content(content)))
        metadata = self._read_core_metadata(archive)
        lines = ["# PPTX Deck", f"Source path: `{path}`"]

        if metadata:
            lines.extend(["", "## Metadata"])
            lines.extend(f"- {key}: {value}" for key, value in metadata.items())

        slide_paths = sorted(
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        )

        for slide_index, slide_path in enumerate(slide_paths, start=1):
            slide_root = ET.fromstring(archive.read(slide_path))
            texts = self._extract_text_runs(slide_root)
            if not texts:
                continue

            title = texts[0]
            body = texts[1:]
            lines.extend(["", f"## Slide {slide_index}: {title}"])
            if body:
                lines.extend(f"- {value}" for value in body)

            notes_path = f"ppt/notesSlides/notesSlide{slide_index}.xml"
            if notes_path in archive.namelist():
                notes_root = ET.fromstring(archive.read(notes_path))
                notes = self._extract_text_runs(notes_root)
                if notes:
                    lines.extend(["", "### Speaker Notes"])
                    lines.extend(f"- {value}" for value in notes)

        if len(lines) <= 2 + (2 + len(metadata) if metadata else 0):
            lines.extend(["", "## Extracted Content", "- No readable slide text was found in this deck."])

        metadata["slideCount"] = len(slide_paths)
        return BinaryParseResult(
            content="\n".join(lines).strip(),
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            metadata=metadata,
        )

    def _read_core_metadata(self, archive: ZipFile) -> dict[str, str | int]:
        try:
            core_xml = archive.read("docProps/core.xml")
        except KeyError:
            return {}

        root = ET.fromstring(core_xml)
        metadata: dict[str, str | int] = {}
        title = root.findtext("dc:title", default="", namespaces=CORE_NS)
        creator = root.findtext("dc:creator", default="", namespaces=CORE_NS)
        if title.strip():
            metadata["title"] = " ".join(title.split())
        if creator.strip():
            metadata["creator"] = " ".join(creator.split())
        return metadata

    def _extract_text_runs(self, root: ET.Element) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for node in root.findall(".//a:t", SLIDE_TEXT_NS):
            value = " ".join((node.text or "").split()).strip()
            if value and value not in seen:
                seen.add(value)
                values.append(value)
        return values
