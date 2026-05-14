"""Binary parser helpers for non-code documents."""

from .base import BinaryDocumentParser, BinaryParseResult, decode_binary_content
from .docx import DocxDocumentParser
from .pdf import PdfDocumentParser
from .pptx import PptxDocumentParser
from .registry import (
    PLANNED_BINARY_FORMATS,
    SUPPORTED_BINARY_FORMATS,
    extract_binary_document_content,
    get_binary_parser,
    get_rag_ready_document_content,
    is_rag_indexable_document,
    supports_binary_document,
)
from .svg import SvgDocumentParser
from .svg_context import SvgContextBundle, build_svg_context, enrich_svg_content, manifest_to_json
from .vsdx import VsdxDocumentParser

__all__ = [
    "BinaryDocumentParser",
    "BinaryParseResult",
    "DocxDocumentParser",
    "PLANNED_BINARY_FORMATS",
    "PdfDocumentParser",
    "PptxDocumentParser",
    "SUPPORTED_BINARY_FORMATS",
    "SvgDocumentParser",
    "SvgContextBundle",
    "build_svg_context",
    "decode_binary_content",
    "enrich_svg_content",
    "extract_binary_document_content",
    "get_binary_parser",
    "get_rag_ready_document_content",
    "is_rag_indexable_document",
    "manifest_to_json",
    "supports_binary_document",
    "VsdxDocumentParser",
]
