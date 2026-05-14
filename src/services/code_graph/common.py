"""Shared helpers for deterministic code graph extractors."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import PurePosixPath

from .models import CodeGraphEdge, CodeGraphNode, CodeGraphReferenceHint, ExtractedCodeGraph

CODE_GRAPH_EXTRACTOR_VERSION = 2


def normalize_repo_path(path: str) -> str:
    """Normalize a repository-relative path for stable graph identifiers."""
    return path.replace("\\", "/").lstrip("./")


def path_identity(path: str) -> str:
    """Build a fallback path identity when no logical module path exists."""
    return normalize_repo_path(path).replace("/", "::")


def derive_dotted_module_path(path: str, *, suffixes: tuple[str, ...]) -> str:
    """Convert a source path into a dotted module-like identity."""
    normalized = normalize_repo_path(path)
    pure_path = PurePosixPath(normalized)
    if pure_path.suffix not in suffixes:
        return ""

    without_suffix = pure_path.with_suffix("")
    return ".".join(without_suffix.parts)


def derive_relative_module_path(
    document_path: str,
    import_path: str,
    *,
    suffixes: tuple[str, ...],
) -> str:
    """Resolve a relative import target to the dotted identity used by graph nodes."""
    if not import_path.startswith("."):
        return ""

    normalized_document = PurePosixPath(normalize_repo_path(document_path))
    base_dir = normalized_document.parent
    import_target = PurePosixPath(import_path)
    candidate = PurePosixPath(posixpath.normpath(str(base_dir.joinpath(import_target))))
    derived = derive_dotted_module_path(str(candidate), suffixes=suffixes)
    if derived:
        return derived
    if candidate.suffix:
        return ""
    return ".".join(part for part in candidate.parts if part not in {"."})


def dotted_import_module_path(import_path: str) -> str:
    """Convert an import-like path into a stable dotted module identity."""
    normalized = normalize_repo_path(import_path)
    pure_path = PurePosixPath(normalized)
    if pure_path.suffix:
        pure_path = pure_path.with_suffix("")
    return ".".join(part for part in pure_path.parts if part)


def is_likely_repo_local_import(import_path: str) -> bool:
    """Best-effort heuristic for imports that likely refer to repo-local code."""
    if import_path.startswith("."):
        return True
    first_segment = import_path.split("/", 1)[0]
    return "/" in import_path and "." not in first_segment


@dataclass(frozen=True)
class ResolvedReference:
    """Result of resolving a call/reference target inside an extractor."""

    symbol_key: str | None = None
    target_qualified_name: str | None = None


class CodeGraphBuilder:
    """Convenience wrapper for building deterministic code graph payloads."""

    def __init__(self, *, language: str, document_path: str, source: str, module_path: str):
        self.language = language
        self.document_path = normalize_repo_path(document_path)
        self.source = source
        self.module_path = module_path
        self.module_identity = module_path or path_identity(document_path)
        self._nodes: dict[str, CodeGraphNode] = {}
        self._edges: set[tuple[str, str, str, str, float]] = set()
        self._reference_hints: dict[
            tuple[str, str, str, str | None, str, str | None, float],
            CodeGraphReferenceHint,
        ] = {}

        self.module_node = self.create_symbol_node(
            kind="MODULE",
            qualified_name=self.module_identity,
            local_name=self.module_identity.split(".")[-1] if self.module_identity else "<module>",
            start_line=1,
            end_line=max(1, len(source.splitlines())),
        )

    def create_symbol_node(
        self,
        *,
        kind: str,
        qualified_name: str,
        local_name: str,
        start_line: int,
        end_line: int,
        signature: str | None = None,
        docstring: str | None = None,
    ) -> CodeGraphNode:
        symbol_key = self.symbol_key(kind, qualified_name)
        existing = self._nodes.get(symbol_key)
        if existing is not None:
            return existing

        node = CodeGraphNode(
            symbol_key=symbol_key,
            kind=kind,
            language=self.language,
            module_path=self.module_path,
            qualified_name=qualified_name,
            local_name=local_name,
            start_line=start_line,
            end_line=end_line,
            signature=signature,
            docstring=docstring,
        )
        self._nodes[symbol_key] = node
        return node

    def create_import_node(
        self,
        owner: CodeGraphNode,
        *,
        local_name: str,
        qualified_name: str,
        line_number: int,
    ) -> CodeGraphNode:
        scoped_name = f"{owner.qualified_name}::{local_name}"
        symbol_key = (
            f"{self.language}::{self.module_identity}::import::{scoped_name}::{qualified_name}"
        )
        import_node = self._nodes.get(symbol_key)
        if import_node is None:
            import_node = CodeGraphNode(
                symbol_key=symbol_key,
                kind="IMPORT",
                language=self.language,
                module_path=self.module_path,
                qualified_name=qualified_name,
                local_name=local_name,
                start_line=line_number,
                end_line=line_number,
            )
            self._nodes[symbol_key] = import_node

        self.add_edge(owner.symbol_key, import_node.symbol_key, "CONTAINS")
        self.add_edge(owner.symbol_key, import_node.symbol_key, "IMPORTS")
        return import_node

    def compose_qualified_name(self, owner: CodeGraphNode, child_name: str) -> str:
        if owner.kind == "MODULE":
            return ".".join(part for part in [self.module_identity, child_name] if part)
        return f"{owner.qualified_name}.{child_name}"

    def symbol_key(self, kind: str, qualified_name: str) -> str:
        return f"{self.language}::{self.module_identity}::{kind.lower()}::{qualified_name}"

    def add_edge(
        self,
        from_symbol_key: str,
        to_symbol_key: str,
        kind: str,
        *,
        source: str = "AST",
        confidence: float = 1.0,
    ) -> None:
        self._edges.add((from_symbol_key, to_symbol_key, kind, source, confidence))

    def add_reference_hint(
        self,
        from_symbol_key: str,
        relationship: str,
        *,
        callee: str,
        target_qualified_name: str | None = None,
        state: str = "unresolved",
        reason: str | None = None,
        confidence: float = 0.5,
    ) -> None:
        key = (
            from_symbol_key,
            relationship,
            callee,
            target_qualified_name,
            state,
            reason,
            confidence,
        )
        self._reference_hints[key] = CodeGraphReferenceHint(
            from_symbol_key=from_symbol_key,
            relationship=relationship,
            callee=callee,
            target_qualified_name=target_qualified_name,
            state=state,
            reason=reason,
            confidence=confidence,
        )

    def build(self) -> ExtractedCodeGraph:
        nodes = sorted(
            self._nodes.values(),
            key=lambda node: (node.start_line, node.end_line, node.symbol_key),
        )
        edges = sorted(
            (
                CodeGraphEdge(
                    from_symbol_key=from_symbol_key,
                    to_symbol_key=to_symbol_key,
                    kind=kind,
                    source=source,
                    confidence=confidence,
                )
                for from_symbol_key, to_symbol_key, kind, source, confidence in self._edges
            ),
            key=lambda edge: (
                edge.from_symbol_key,
                edge.kind,
                edge.to_symbol_key,
                edge.source,
                edge.confidence,
            ),
        )
        reference_hints = sorted(
            self._reference_hints.values(),
            key=lambda hint: (
                hint.from_symbol_key,
                hint.relationship,
                hint.callee,
                hint.target_qualified_name or "",
                hint.state,
                hint.reason or "",
                hint.confidence,
            ),
        )
        return ExtractedCodeGraph(
            nodes=nodes,
            edges=edges,
            reference_hints=reference_hints,
            extractor_version=CODE_GRAPH_EXTRACTOR_VERSION,
        )
