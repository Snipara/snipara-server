"""Base types for binary document parsing."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class BinaryParseResult:
    """Normalized text extracted from a binary-ish document."""

    content: str
    parser_name: str
    parser_version: int
    metadata: dict[str, Any] = field(default_factory=dict)


class BinaryDocumentParser(Protocol):
    """Protocol for parsers that turn raw document content into markdown-ish text."""

    format: str
    parser_name: str
    parser_version: int

    def parse(self, *, content: str, path: str) -> BinaryParseResult: ...


def decode_binary_content(content: str) -> bytes:
    normalized = content.strip()

    if normalized.startswith("base64:"):
        return base64.b64decode(normalized.split(":", 1)[1])

    if normalized.startswith("data:") and ";base64," in normalized:
        return base64.b64decode(normalized.split(";base64,", 1)[1])

    return normalized.encode("utf-8")
