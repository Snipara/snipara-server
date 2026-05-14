"""Deterministic TypeScript code graph extractor using lightweight parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .common import (
    CODE_GRAPH_EXTRACTOR_VERSION,
    CodeGraphBuilder,
    ResolvedReference,
    derive_dotted_module_path,
    derive_relative_module_path,
)
from .models import CodeGraphNode, ExtractedCodeGraph

TYPESCRIPT_EXTRACTOR_VERSION = CODE_GRAPH_EXTRACTOR_VERSION
TYPESCRIPT_FORMATS = ("ts", "tsx", "mts", "cts")

_CLASS_HEADER_RE = re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)\b")
_FUNCTION_HEADER_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("
)
_ARROW_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{"
)
_FUNCTION_EXPR_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function\b"
)
_METHOD_HEADER_RE = re.compile(
    r"^\s*(?:public|private|protected|static|readonly|override|abstract|async|get|set|\s)*"
    r"(#?[A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?::\s*([^{]+))?\s*\{"
)
_IMPORT_FROM_RE = re.compile(r"^\s*(?:import|export)\s+(.+?)\s+from\s+['\"]([^'\"]+)['\"]")
_IMPORT_SIDE_EFFECT_RE = re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]")
_CALL_RE = re.compile(r"\b([A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*)\s*\(")
_IGNORED_CALLEES = {"if", "for", "while", "switch", "catch", "function", "return", "typeof"}


@dataclass
class _RoutineBlock:
    node: CodeGraphNode
    start_line: int
    end_line: int
    class_symbol_key: str | None = None


@dataclass(frozen=True)
class _ImportSpecifier:
    local_name: str
    imported_name: str | None = None
    kind: str = "named"


class TypeScriptCodeExtractor:
    """Extract a lightweight structural graph from TypeScript source."""

    language = "typescript"
    extractor_version = TYPESCRIPT_EXTRACTOR_VERSION

    def __init__(self, document_path: str, source: str):
        self.document_path = document_path
        self.source = source
        self.lines = source.splitlines()
        self.builder = CodeGraphBuilder(
            language=self.language,
            document_path=document_path,
            source=source,
            module_path=self._derive_module_path(document_path),
        )
        self._module_bindings: dict[str, str] = {}
        self._named_import_targets: dict[str, str] = {}
        self._namespace_import_targets: dict[str, str] = {}
        self._class_methods: dict[str, dict[str, str]] = {}
        self._routines: list[_RoutineBlock] = []

    def extract(self) -> ExtractedCodeGraph:
        self._collect_imports()
        self._collect_top_level_declarations()
        self._collect_call_edges()
        return self.builder.build()

    @staticmethod
    def _derive_module_path(path: str) -> str:
        return derive_dotted_module_path(path, suffixes=tuple(f".{fmt}" for fmt in TYPESCRIPT_FORMATS))

    def _collect_imports(self) -> None:
        index = 0
        while index < len(self.lines):
            line = self.lines[index].strip()
            if not line.startswith(("import", "export")):
                index += 1
                continue

            statement_lines = [self.lines[index]]
            while index + 1 < len(self.lines) and ";" not in statement_lines[-1]:
                index += 1
                statement_lines.append(self.lines[index])

            statement = " ".join(part.strip() for part in statement_lines)
            line_number = index - len(statement_lines) + 2
            self._register_import_statement(statement, line_number)
            index += 1

    def _register_import_statement(self, statement: str, line_number: int) -> None:
        side_effect_match = _IMPORT_SIDE_EFFECT_RE.match(statement)
        if side_effect_match:
            module_name = side_effect_match.group(1)
            import_node = self.builder.create_import_node(
                self.builder.module_node,
                local_name=module_name.split("/")[-1],
                qualified_name=module_name,
                line_number=line_number,
            )
            self._module_bindings[import_node.local_name] = import_node.symbol_key
            return

        match = _IMPORT_FROM_RE.match(statement)
        if match is None:
            return

        specifiers = match.group(1).strip()
        module_name = match.group(2)
        relative_module_path = derive_relative_module_path(
            self.document_path,
            module_name,
            suffixes=tuple(f".{fmt}" for fmt in TYPESCRIPT_FORMATS),
        )
        for specifier in self._parse_import_specifiers(specifiers, module_name):
            import_node = self.builder.create_import_node(
                self.builder.module_node,
                local_name=specifier.local_name,
                qualified_name=module_name,
                line_number=line_number,
            )
            self._module_bindings[specifier.local_name] = import_node.symbol_key
            if not relative_module_path:
                continue
            if specifier.kind == "named" and specifier.imported_name:
                self._named_import_targets[specifier.local_name] = ".".join(
                    [relative_module_path, specifier.imported_name]
                )
            elif specifier.kind == "namespace":
                self._namespace_import_targets[specifier.local_name] = relative_module_path

    @staticmethod
    def _parse_import_specifiers(specifiers: str, module_name: str) -> list[_ImportSpecifier]:
        if specifiers.startswith("* as "):
            return [_ImportSpecifier(local_name=specifiers.split(" ", 2)[-1].strip(), kind="namespace")]

        normalized = specifiers.strip()
        if "{" not in normalized:
            return [
                _ImportSpecifier(
                    local_name=normalized,
                    imported_name=None,
                    kind="default",
                )
            ]

        result: list[_ImportSpecifier] = []
        prefix, _, suffix = normalized.partition("{")
        default_name = prefix.replace(",", "").strip()
        if default_name:
            result.append(_ImportSpecifier(local_name=default_name, imported_name=None, kind="default"))

        named_block = suffix.rsplit("}", 1)[0]
        for part in named_block.split(","):
            name = part.strip()
            if not name:
                continue
            if " as " in name:
                imported_name, local_name = [token.strip() for token in name.split(" as ", 1)]
            else:
                imported_name = name
                local_name = name
            result.append(
                _ImportSpecifier(local_name=local_name, imported_name=imported_name, kind="named")
            )

        if not result:
            result.append(
                _ImportSpecifier(local_name=module_name.split("/")[-1], imported_name=None, kind="default")
            )
        return result

    def _collect_top_level_declarations(self) -> None:
        index = 0
        while index < len(self.lines):
            line = self.lines[index]
            if _CLASS_HEADER_RE.match(line):
                _, end_index = self._register_class(index)
                index = end_index + 1
                continue
            if _FUNCTION_HEADER_RE.match(line) or _ARROW_FUNCTION_RE.match(line) or _FUNCTION_EXPR_RE.match(
                line
            ):
                _, end_index = self._register_function(index, self.builder.module_node, kind="FUNCTION")
                index = end_index + 1
                continue
            index += 1

    def _register_class(self, start_index: int) -> tuple[CodeGraphNode, int]:
        header, end_index = self._collect_block(start_index)
        match = _CLASS_HEADER_RE.match(header)
        if match is None:
            raise ValueError(f"Invalid class declaration at line {start_index + 1}")

        class_name = match.group(1)
        class_node = self.builder.create_symbol_node(
            kind="CLASS",
            qualified_name=self.builder.compose_qualified_name(self.builder.module_node, class_name),
            local_name=class_name,
            start_line=start_index + 1,
            end_line=end_index + 1,
        )
        self.builder.add_edge(self.builder.module_node.symbol_key, class_node.symbol_key, "CONTAINS")
        self._module_bindings[class_name] = class_node.symbol_key

        class_bindings: dict[str, str] = {}
        index = start_index + 1
        while index < end_index:
            line = self.lines[index]
            if _METHOD_HEADER_RE.match(line):
                method_node, method_end = self._register_function(
                    index,
                    class_node,
                    kind="METHOD",
                )
                class_bindings[method_node.local_name.lstrip("#")] = method_node.symbol_key
                self._routines.append(
                    _RoutineBlock(
                        node=method_node,
                        start_line=index + 1,
                        end_line=method_end + 1,
                        class_symbol_key=class_node.symbol_key,
                    )
                )
                index = method_end + 1
                continue
            index += 1

        self._class_methods[class_node.symbol_key] = class_bindings
        return class_node, end_index

    def _register_function(
        self,
        start_index: int,
        owner: CodeGraphNode,
        *,
        kind: str,
    ) -> tuple[CodeGraphNode, int]:
        header, end_index = self._collect_block(start_index)
        parsed = self._parse_callable_header(header, kind)
        function_node = self.builder.create_symbol_node(
            kind=kind,
            qualified_name=self.builder.compose_qualified_name(owner, parsed["name"]),
            local_name=parsed["name"],
            start_line=start_index + 1,
            end_line=end_index + 1,
            signature=parsed["signature"],
        )
        self.builder.add_edge(owner.symbol_key, function_node.symbol_key, "CONTAINS")
        if kind == "FUNCTION":
            self._module_bindings[parsed["name"]] = function_node.symbol_key
            self._routines.append(
                _RoutineBlock(node=function_node, start_line=start_index + 1, end_line=end_index + 1)
            )
        return function_node, end_index

    @staticmethod
    def _parse_callable_header(header: str, kind: str) -> dict[str, str]:
        cleaned = " ".join(part.strip() for part in header.splitlines())

        if kind == "METHOD":
            match = _METHOD_HEADER_RE.match(cleaned)
            if match is None:
                raise ValueError(f"Invalid method declaration: {cleaned}")
            name = match.group(1).lstrip("#")
            args = match.group(2).strip()
            returns = match.group(3).strip() if match.group(3) else ""
            return {"name": name, "signature": TypeScriptCodeExtractor._render_signature(args, returns)}

        for pattern in (_FUNCTION_HEADER_RE, _ARROW_FUNCTION_RE, _FUNCTION_EXPR_RE):
            match = pattern.match(cleaned)
            if match is None:
                continue
            name = match.group(1)
            args_match = re.search(r"\((.*?)\)", cleaned)
            args = args_match.group(1).strip() if args_match else ""
            returns_match = re.search(r"\)\s*:\s*([^={]+)", cleaned)
            returns = returns_match.group(1).strip() if returns_match else ""
            return {"name": name, "signature": TypeScriptCodeExtractor._render_signature(args, returns)}

        raise ValueError(f"Invalid function declaration: {cleaned}")

    @staticmethod
    def _render_signature(args: str, returns: str) -> str:
        if returns:
            return f"({args}) -> {returns}"
        return f"({args})"

    def _collect_call_edges(self) -> None:
        for routine in self._routines:
            body = "\n".join(self.lines[routine.start_line - 1 : routine.end_line])
            for match in _CALL_RE.finditer(body):
                callee = re.sub(r"\s+", "", match.group(1))
                root = callee.split(".", 1)[0]
                if root in _IGNORED_CALLEES:
                    continue
                target = self._resolve_callee(callee, routine.class_symbol_key)
                if target is None:
                    self.builder.add_reference_hint(
                        routine.node.symbol_key,
                        "CALLS",
                        callee=callee,
                        state="unresolved",
                        reason="unknown_binding",
                    )
                    continue
                if target.symbol_key == routine.node.symbol_key:
                    continue
                if target.target_qualified_name:
                    self.builder.add_reference_hint(
                        routine.node.symbol_key,
                        "CALLS",
                        callee=callee,
                        target_qualified_name=target.target_qualified_name,
                        state="cross_file_candidate",
                        reason="relative_import",
                    )
                    continue
                if target.symbol_key is None:
                    continue
                target_node = self.builder._nodes.get(target.symbol_key)
                if target_node is None:
                    continue
                if target_node.kind == "IMPORT":
                    self.builder.add_edge(
                        routine.node.symbol_key,
                        target.symbol_key,
                        "REFERENCES",
                        confidence=0.5,
                    )
                    continue
                self.builder.add_edge(routine.node.symbol_key, target.symbol_key, "CALLS")

    def _resolve_callee(self, callee: str, class_symbol_key: str | None) -> ResolvedReference | None:
        if callee.startswith("this.") and class_symbol_key is not None:
            method_name = callee.split(".", 1)[1].split(".", 1)[0]
            symbol_key = self._class_methods.get(class_symbol_key, {}).get(method_name)
            return ResolvedReference(symbol_key=symbol_key) if symbol_key else None

        if "." in callee:
            root, member = callee.split(".", 1)
            namespace_target = self._namespace_import_targets.get(root)
            if namespace_target:
                return ResolvedReference(
                    target_qualified_name=".".join([namespace_target, member.split(".", 1)[0]])
                )
        else:
            named_target = self._named_import_targets.get(callee)
            if named_target:
                return ResolvedReference(target_qualified_name=named_target)

        root = callee.split(".", 1)[0]
        target_symbol_key = self._module_bindings.get(root)
        if target_symbol_key is None:
            return None

        target_node = self.builder._nodes.get(target_symbol_key)
        if target_node is None:
            return None

        if "." in callee and target_node.kind == "CLASS":
            method_name = callee.split(".", 1)[1].split(".", 1)[0]
            method_symbol_key = self._class_methods.get(target_symbol_key, {}).get(method_name)
            return ResolvedReference(symbol_key=method_symbol_key) if method_symbol_key else None

        return ResolvedReference(symbol_key=target_symbol_key)

    def _collect_block(self, start_index: int) -> tuple[str, int]:
        header_lines: list[str] = []
        brace_depth = 0
        end_index = start_index

        while end_index < len(self.lines):
            line = self.lines[end_index]
            header_lines.append(line)
            brace_depth += line.count("{") - line.count("}")
            if "{" in line and brace_depth == 0:
                return "\n".join(header_lines), end_index
            if "{" in line and brace_depth > 0:
                break
            end_index += 1

        if brace_depth <= 0:
            return "\n".join(header_lines), end_index

        end_index += 1
        while end_index < len(self.lines):
            line = self.lines[end_index]
            header_lines.append(line)
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                return "\n".join(header_lines), end_index
            end_index += 1

        return "\n".join(header_lines), len(self.lines) - 1
