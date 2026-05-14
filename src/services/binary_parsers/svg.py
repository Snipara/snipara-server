"""SVG parser that converts diagram content into markdown-like context."""

from __future__ import annotations

from .base import BinaryParseResult, decode_binary_content
from .svg_context import build_svg_context


class SvgDocumentParser:
    """Extract LLM-readable context from SVG documents."""

    format = "svg"
    parser_name = "svg"
    parser_version = 2

    def parse(self, *, content: str, path: str) -> BinaryParseResult:
        svg_content = decode_binary_content(content).decode("utf-8")
        bundle = build_svg_context(content=svg_content, path=path)
        return BinaryParseResult(
            content=bundle.markdown.strip(),
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            metadata=bundle.metadata,
        )
