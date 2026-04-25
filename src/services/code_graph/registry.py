"""Extractor registry for supported code graph languages."""

from __future__ import annotations

from typing import Any

from .common import CODE_GRAPH_EXTRACTOR_VERSION
from .go import GO_FORMATS, GoCodeExtractor
from .python import PythonCodeExtractor
from .typescript import TYPESCRIPT_FORMATS, TypeScriptCodeExtractor

EXTRACTOR_BY_LANGUAGE = {
    "python": PythonCodeExtractor,
    "typescript": TypeScriptCodeExtractor,
    "go": GoCodeExtractor,
}

FORMAT_TO_LANGUAGE = {
    "py": "python",
    "pyi": "python",
    **{fmt: "typescript" for fmt in TYPESCRIPT_FORMATS},
    **{fmt: "go" for fmt in GO_FORMATS},
}

SUPPORTED_CODE_LANGUAGES = set(EXTRACTOR_BY_LANGUAGE)
SUPPORTED_CODE_FORMATS = set(FORMAT_TO_LANGUAGE)


def infer_document_language(document: Any) -> str | None:
    """Infer the extractor language for a CODE document."""
    language = str(getattr(document, "language", "") or "").lower()
    if language in EXTRACTOR_BY_LANGUAGE:
        return language

    fmt = str(getattr(document, "format", "") or "").lower().lstrip(".")
    if fmt in FORMAT_TO_LANGUAGE:
        return FORMAT_TO_LANGUAGE[fmt]

    path = str(getattr(document, "path", "") or "").lower()
    for suffix, inferred_language in FORMAT_TO_LANGUAGE.items():
        if path.endswith(f".{suffix}"):
            return inferred_language

    return None


def get_extractor_for_document(document: Any):
    """Instantiate the correct extractor for a CODE document."""
    language = infer_document_language(document)
    if language is None:
        return None

    extractor_cls = EXTRACTOR_BY_LANGUAGE[language]
    return extractor_cls(document.path, document.content or "")
