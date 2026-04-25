"""Registry and helpers for binary parser support."""

from __future__ import annotations

from typing import Any

from .base import BinaryParseResult, BinaryDocumentParser
from .docx import DocxDocumentParser
from .pdf import PdfDocumentParser
from .pptx import PptxDocumentParser
from .svg import SvgDocumentParser
from .vsdx import VsdxDocumentParser

PLANNED_BINARY_FORMATS = ("pdf", "docx", "pptx", "svg", "vsdx")

_PARSERS: dict[str, BinaryDocumentParser] = {
    "docx": DocxDocumentParser(),
    "pdf": PdfDocumentParser(),
    "pptx": PptxDocumentParser(),
    "svg": SvgDocumentParser(),
    "vsdx": VsdxDocumentParser(),
}

SUPPORTED_BINARY_FORMATS = tuple(sorted(_PARSERS.keys()))


def get_binary_parser(format_name: str | None) -> BinaryDocumentParser | None:
    if not format_name:
        return None
    return _PARSERS.get(str(format_name).lower())


def supports_binary_document(document: Any) -> bool:
    return getattr(document, "kind", None) == "BINARY" and get_binary_parser(
        getattr(document, "format", None)
    ) is not None


def extract_binary_document_content(document: Any) -> BinaryParseResult | None:
    parser = get_binary_parser(getattr(document, "format", None))
    if parser is None:
        return None

    return parser.parse(
        content=getattr(document, "content", "") or "",
        path=getattr(document, "path", "(unknown)"),
    )


def is_rag_indexable_document(document: Any) -> bool:
    kind = getattr(document, "kind", "DOC")
    if kind == "DOC":
        return True
    return supports_binary_document(document)


def get_rag_ready_document_content(document: Any) -> str | None:
    if getattr(document, "kind", "DOC") == "DOC":
        return getattr(document, "content", "")

    parsed = extract_binary_document_content(document)
    if parsed is None:
        return None
    return parsed.content.strip() or None
