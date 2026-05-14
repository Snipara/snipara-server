"""Deterministic Python code graph extractor built on the stdlib AST."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .common import CODE_GRAPH_EXTRACTOR_VERSION
from .models import CodeGraphEdge, CodeGraphNode, ExtractedCodeGraph

PYTHON_EXTRACTOR_VERSION = CODE_GRAPH_EXTRACTOR_VERSION

_SKIP_WALK_TYPES = (
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.FunctionDef,
    ast.Lambda,
)


@dataclass
class _Scope:
    owner: CodeGraphNode
    parent: _Scope | None = None
    bindings: dict[str, str] = field(default_factory=dict)
    class_symbol_key: str | None = None
    class_method_bindings: dict[str, str] = field(default_factory=dict)


class PythonCodeExtractor:
    """Extract a lightweight structural graph from Python source."""

    language = "python"
    extractor_version = PYTHON_EXTRACTOR_VERSION

    def __init__(self, document_path: str, source: str):
        self.document_path = document_path
        self.source = source
        self._module_path = self._derive_module_path(document_path)
        self._module_identity = self._module_path or self._path_identity(document_path)
        self._nodes: dict[str, CodeGraphNode] = {}
        self._edges: set[tuple[str, str, str, str, float]] = set()
        self._class_methods: dict[str, dict[str, str]] = {}

        self._module_node = self._create_symbol_node(
            kind="MODULE",
            qualified_name=self._module_identity,
            local_name=self._module_identity.split(".")[-1] if self._module_identity else "<module>",
            start_line=1,
            end_line=max(1, len(source.splitlines())),
        )

    def extract(self) -> ExtractedCodeGraph:
        """Parse the source file and return a deterministic graph."""
        tree = ast.parse(self.source, filename=self.document_path)
        root_scope = _Scope(owner=self._module_node)
        self._collect_bindings(tree.body, root_scope)
        self._walk_body(tree.body, root_scope)

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

        return ExtractedCodeGraph(
            nodes=nodes,
            edges=edges,
            extractor_version=self.extractor_version,
        )

    def _collect_bindings(self, statements: list[ast.stmt], scope: _Scope) -> None:
        for statement in statements:
            if isinstance(statement, ast.ClassDef):
                class_node = self._register_class(statement, scope.owner)
                scope.bindings[statement.name] = class_node.symbol_key
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_node = self._register_function(
                    statement,
                    scope.owner,
                    kind="METHOD" if scope.class_symbol_key else "FUNCTION",
                )
                scope.bindings[statement.name] = function_node.symbol_key
                if scope.class_symbol_key:
                    scope.class_method_bindings[statement.name] = function_node.symbol_key
            elif isinstance(statement, ast.Import):
                self._register_imports(statement, scope)
            elif isinstance(statement, ast.ImportFrom):
                self._register_import_from(statement, scope)

    def _walk_body(self, statements: list[ast.stmt], scope: _Scope) -> None:
        for statement in statements:
            if isinstance(statement, ast.ClassDef):
                self._walk_class(statement, scope)
                continue
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._walk_function(statement, scope)
                continue
            if isinstance(statement, (ast.Import, ast.ImportFrom)):
                continue

            if scope.owner.kind in {"FUNCTION", "METHOD"}:
                for call_node in self._iter_calls(statement):
                    self._maybe_add_call_edge(scope.owner, call_node, scope)

    def _walk_class(self, statement: ast.ClassDef, parent_scope: _Scope) -> None:
        class_symbol_key = parent_scope.bindings.get(statement.name)
        if class_symbol_key is None:
            return

        class_node = self._nodes[class_symbol_key]
        class_scope = _Scope(
            owner=class_node,
            parent=parent_scope,
            class_symbol_key=class_symbol_key,
        )
        self._collect_bindings(statement.body, class_scope)
        self._class_methods[class_symbol_key] = dict(class_scope.class_method_bindings)
        self._walk_body(statement.body, class_scope)

    def _walk_function(
        self,
        statement: ast.FunctionDef | ast.AsyncFunctionDef,
        parent_scope: _Scope,
    ) -> None:
        function_symbol_key = parent_scope.bindings.get(statement.name)
        if function_symbol_key is None:
            return

        function_node = self._nodes[function_symbol_key]
        function_scope = _Scope(
            owner=function_node,
            parent=parent_scope,
            class_symbol_key=parent_scope.class_symbol_key,
            class_method_bindings=dict(parent_scope.class_method_bindings),
        )
        self._collect_bindings(statement.body, function_scope)
        self._walk_body(statement.body, function_scope)

    def _register_class(self, statement: ast.ClassDef, owner: CodeGraphNode) -> CodeGraphNode:
        qualified_name = self._compose_qualified_name(owner, statement.name)
        class_node = self._create_symbol_node(
            kind="CLASS",
            qualified_name=qualified_name,
            local_name=statement.name,
            start_line=getattr(statement, "lineno", owner.start_line),
            end_line=getattr(statement, "end_lineno", getattr(statement, "lineno", owner.end_line)),
            docstring=self._truncate_docstring(ast.get_docstring(statement)),
        )
        self._add_edge(owner.symbol_key, class_node.symbol_key, "CONTAINS")
        return class_node

    def _register_function(
        self,
        statement: ast.FunctionDef | ast.AsyncFunctionDef,
        owner: CodeGraphNode,
        kind: str,
    ) -> CodeGraphNode:
        qualified_name = self._compose_qualified_name(owner, statement.name)
        function_node = self._create_symbol_node(
            kind=kind,
            qualified_name=qualified_name,
            local_name=statement.name,
            start_line=getattr(statement, "lineno", owner.start_line),
            end_line=getattr(statement, "end_lineno", getattr(statement, "lineno", owner.end_line)),
            signature=self._function_signature(statement),
            docstring=self._truncate_docstring(ast.get_docstring(statement)),
        )
        self._add_edge(owner.symbol_key, function_node.symbol_key, "CONTAINS")
        return function_node

    def _register_imports(self, statement: ast.Import, scope: _Scope) -> None:
        for alias in statement.names:
            imported_name = alias.name
            local_name = alias.asname or imported_name.split(".")[0]
            import_node = self._create_import_node(
                scope.owner,
                local_name=local_name,
                qualified_name=imported_name,
                line_number=getattr(statement, "lineno", scope.owner.start_line),
            )
            scope.bindings[local_name] = import_node.symbol_key

    def _register_import_from(self, statement: ast.ImportFrom, scope: _Scope) -> None:
        base_module = self._resolve_relative_module(statement.module, statement.level)
        line_number = getattr(statement, "lineno", scope.owner.start_line)
        for alias in statement.names:
            imported_name = alias.name
            qualified_name = ".".join(part for part in [base_module, imported_name] if part)
            local_name = alias.asname or imported_name
            import_node = self._create_import_node(
                scope.owner,
                local_name=local_name,
                qualified_name=qualified_name or imported_name,
                line_number=line_number,
            )
            scope.bindings[local_name] = import_node.symbol_key

    def _create_import_node(
        self,
        owner: CodeGraphNode,
        *,
        local_name: str,
        qualified_name: str,
        line_number: int,
    ) -> CodeGraphNode:
        scoped_name = f"{owner.qualified_name}::{local_name}"
        symbol_key = f"python::{self._module_identity}::import::{scoped_name}::{qualified_name}"
        import_node = self._nodes.get(symbol_key)
        if import_node is None:
            import_node = CodeGraphNode(
                symbol_key=symbol_key,
                kind="IMPORT",
                language=self.language,
                module_path=self._module_path,
                qualified_name=qualified_name,
                local_name=local_name,
                start_line=line_number,
                end_line=line_number,
            )
            self._nodes[symbol_key] = import_node

        self._add_edge(owner.symbol_key, import_node.symbol_key, "CONTAINS")
        self._add_edge(owner.symbol_key, import_node.symbol_key, "IMPORTS")
        return import_node

    def _create_symbol_node(
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
        symbol_key = self._symbol_key(kind, qualified_name)
        existing = self._nodes.get(symbol_key)
        if existing is not None:
            return existing

        node = CodeGraphNode(
            symbol_key=symbol_key,
            kind=kind,
            language=self.language,
            module_path=self._module_path,
            qualified_name=qualified_name,
            local_name=local_name,
            start_line=start_line,
            end_line=end_line,
            signature=signature,
            docstring=docstring,
        )
        self._nodes[symbol_key] = node
        return node

    def _maybe_add_call_edge(self, owner: CodeGraphNode, call_node: ast.Call, scope: _Scope) -> None:
        target_symbol_key = self._resolve_call_target(call_node.func, scope)
        if not target_symbol_key or target_symbol_key == owner.symbol_key:
            return

        target_node = self._nodes.get(target_symbol_key)
        if target_node is None:
            return

        if target_node.kind == "IMPORT":
            self._add_edge(owner.symbol_key, target_symbol_key, "REFERENCES", confidence=0.5)
            return

        self._add_edge(owner.symbol_key, target_symbol_key, "CALLS")

    def _resolve_call_target(self, expression: ast.expr, scope: _Scope) -> str | None:
        if isinstance(expression, ast.Name):
            return self._resolve_name(expression.id, scope)

        if isinstance(expression, ast.Attribute):
            base_name = self._attribute_root_name(expression)
            if base_name == "self" and scope.class_symbol_key:
                return scope.class_method_bindings.get(expression.attr)
            if base_name is None:
                return None

            base_symbol_key = self._resolve_name(base_name, scope)
            if base_symbol_key is None:
                return None

            base_node = self._nodes.get(base_symbol_key)
            if base_node is None:
                return None
            if base_node.kind == "CLASS":
                return self._class_methods.get(base_symbol_key, {}).get(expression.attr)
            return base_symbol_key

        return None

    @staticmethod
    def _attribute_root_name(expression: ast.Attribute) -> str | None:
        current: ast.expr = expression
        while isinstance(current, ast.Attribute):
            current = current.value
        if isinstance(current, ast.Name):
            return current.id
        return None

    def _resolve_name(self, name: str, scope: _Scope | None) -> str | None:
        current_scope = scope
        while current_scope is not None:
            symbol_key = current_scope.bindings.get(name)
            if symbol_key is not None:
                return symbol_key
            current_scope = current_scope.parent
        return None

    def _iter_calls(self, node: ast.AST) -> list[ast.Call]:
        calls: list[ast.Call] = []

        def walk(current: ast.AST) -> None:
            if current is not node and isinstance(current, _SKIP_WALK_TYPES):
                return
            if isinstance(current, ast.Call):
                calls.append(current)
            for child in ast.iter_child_nodes(current):
                walk(child)

        walk(node)
        return calls

    def _resolve_relative_module(self, module: str | None, level: int) -> str:
        if level <= 0:
            return module or ""

        current_parts = self._module_path.split(".") if self._module_path else []
        if not self.document_path.endswith("/__init__.py") and current_parts:
            current_parts = current_parts[:-1]

        keep = max(0, len(current_parts) - (level - 1))
        resolved_parts = current_parts[:keep]
        if module:
            resolved_parts.extend(part for part in module.split(".") if part)
        return ".".join(resolved_parts)

    def _compose_qualified_name(self, owner: CodeGraphNode, child_name: str) -> str:
        if owner.kind == "MODULE":
            return ".".join(part for part in [self._module_identity, child_name] if part)
        return f"{owner.qualified_name}.{child_name}"

    def _symbol_key(self, kind: str, qualified_name: str) -> str:
        return f"python::{self._module_identity}::{kind.lower()}::{qualified_name}"

    @staticmethod
    def _path_identity(path: str) -> str:
        normalized = path.replace("\\", "/").lstrip("./")
        return normalized.replace("/", "::")

    @staticmethod
    def _derive_module_path(path: str) -> str:
        normalized = path.replace("\\", "/").lstrip("./")
        pure_path = PurePosixPath(normalized)
        if pure_path.suffix not in {".py", ".pyi"}:
            return ""

        without_suffix = pure_path.with_suffix("")
        parts = list(without_suffix.parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    @staticmethod
    def _truncate_docstring(docstring: str | None) -> str | None:
        if docstring is None:
            return None
        return docstring[:2048]

    def _function_signature(self, statement: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        args = list(statement.args.posonlyargs) + list(statement.args.args)
        rendered_args = [self._format_arg(arg) for arg in args]

        if statement.args.vararg is not None:
            rendered_args.append(f"*{self._format_arg(statement.args.vararg)}")
        elif statement.args.kwonlyargs:
            rendered_args.append("*")

        rendered_args.extend(self._format_arg(arg) for arg in statement.args.kwonlyargs)

        if statement.args.kwarg is not None:
            rendered_args.append(f"**{self._format_arg(statement.args.kwarg)}")

        returns = f" -> {ast.unparse(statement.returns)}" if statement.returns is not None else ""
        return f"({', '.join(rendered_args)}){returns}"

    @staticmethod
    def _format_arg(argument: ast.arg) -> str:
        if argument.annotation is None:
            return argument.arg
        return f"{argument.arg}: {ast.unparse(argument.annotation)}"

    def _add_edge(
        self,
        from_symbol_key: str,
        to_symbol_key: str,
        kind: str,
        *,
        source: str = "AST",
        confidence: float = 1.0,
    ) -> None:
        self._edges.add((from_symbol_key, to_symbol_key, kind, source, confidence))
