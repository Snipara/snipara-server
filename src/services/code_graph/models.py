"""In-memory models for code graph extraction."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CodeGraphNode:
    """A graph node extracted from a single source file."""

    symbol_key: str
    kind: str
    language: str
    module_path: str
    qualified_name: str
    local_name: str
    start_line: int
    end_line: int
    signature: str | None = None
    docstring: str | None = None


@dataclass(frozen=True)
class CodeGraphEdge:
    """A directed relationship between two graph nodes."""

    from_symbol_key: str
    to_symbol_key: str
    kind: str
    source: str = "AST"
    confidence: float = 1.0


@dataclass(frozen=True)
class CodeGraphReferenceHint:
    """A deferred graph relationship that may resolve outside the current document."""

    from_symbol_key: str
    relationship: str
    callee: str
    target_qualified_name: str | None = None
    state: str = "unresolved"
    reason: str | None = None
    confidence: float = 0.5


@dataclass
class ExtractedCodeGraph:
    """A full graph extracted from one document."""

    nodes: list[CodeGraphNode] = field(default_factory=list)
    edges: list[CodeGraphEdge] = field(default_factory=list)
    reference_hints: list[CodeGraphReferenceHint] = field(default_factory=list)
    extractor_version: int = 1
