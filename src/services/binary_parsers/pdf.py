"""PDF parser that extracts page text into markdown-like content."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from .base import BinaryParseResult, decode_binary_content


class PdfDocumentParser:
    """Extract human-readable text from PDF documents."""

    format = "pdf"
    parser_name = "pdf"
    parser_version = 1

    def parse(self, *, content: str, path: str) -> BinaryParseResult:
        reader = PdfReader(BytesIO(decode_binary_content(content)))

        lines = ["# PDF Document", f"Source path: `{path}`"]
        metadata: dict[str, str | int] = {
            "pageCount": len(reader.pages),
        }

        title = self._normalize_value(reader.metadata.title if reader.metadata else None)
        author = self._normalize_value(reader.metadata.author if reader.metadata else None)

        if title or author:
            lines.extend(["", "## Metadata"])
            if title:
                lines.append(f"- title: {title}")
                metadata["title"] = title
            if author:
                lines.append(f"- author: {author}")
                metadata["author"] = author

        page_sections = 0
        for index, page in enumerate(reader.pages, start=1):
            extracted = self._normalize_text(page.extract_text() or "")
            if not extracted:
                continue
            page_sections += 1
            lines.extend(["", f"## Page {index}", extracted])

        if page_sections == 0:
            lines.extend(["", "## Extracted Content", "- No selectable text was found in this PDF."])

        return BinaryParseResult(
            content="\n".join(lines).strip(),
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            metadata=metadata,
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        lines = [" ".join(line.split()) for line in value.splitlines()]
        return "\n".join(line for line in lines if line).strip()

    @staticmethod
    def _normalize_value(value: object | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split()).strip()
        return normalized or None
