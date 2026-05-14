"""Deterministic Go code graph extractor using lightweight parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .common import (
    CODE_GRAPH_EXTRACTOR_VERSION,
    CodeGraphBuilder,
    ResolvedReference,
    derive_dotted_module_path,
    dotted_import_module_path,
    is_likely_repo_local_import,
)
from .models import CodeGraphNode, ExtractedCodeGraph

GO_EXTRACTOR_VERSION = CODE_GRAPH_EXTRACTOR_VERSION
GO_FORMATS = ("go",)

_TYPE_HEADER_RE = re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+(?:struct|interface)\b")
_FUNCTION_HEADER_RE = re.compile(r"^\s*func\s+([A-Za-z_]\w*)\s*\(")
_METHOD_HEADER_RE = re.compile(
    r"^\s*func\s*\(\s*([A-Za-z_]\w*)\s+(?:\*?\s*)?([A-Za-z_]\w*)\s*\)\s*([A-Za-z_]\w*)\s*\("
)
_IMPORT_SINGLE_RE = re.compile(r'^\s*import\s+(?:([A-Za-z_]\w*|_|\.)\s+)?["]([^"]+)["]')
_IMPORT_BLOCK_ENTRY_RE = re.compile(r'^\s*(?:([A-Za-z_]\w*|_|\.)\s+)?["]([^"]+)["]')
_CALL_RE = re.compile(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\(")
_IGNORED_CALLEES = {"if", "for", "switch", "return", "go", "defer", "func"}


@dataclass
class _GoRoutineBlock:
    node: CodeGraphNode
    start_line: int
    end_line: int
    receiver_name: str | None = None
    receiver_type: str | None = None


class GoCodeExtractor:
    """Extract a lightweight structural graph from Go source."""

    language = "go"
    extractor_version = GO_EXTRACTOR_VERSION

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
        self._import_module_paths: dict[str, str] = {}
        self._class_methods: dict[str, dict[str, str]] = {}
        self._routines: list[_GoRoutineBlock] = []

    def extract(self) -> ExtractedCodeGraph:
        self._collect_imports()
        self._collect_top_level_declarations()
        self._collect_call_edges()
        return self.builder.build()

    @staticmethod
    def _derive_module_path(path: str) -> str:
        return derive_dotted_module_path(path, suffixes=tuple(f".{fmt}" for fmt in GO_FORMATS))

    def _collect_imports(self) -> None:
        index = 0
        while index < len(self.lines):
            line = self.lines[index]
            single_match = _IMPORT_SINGLE_RE.match(line)
            if single_match is not None:
                self._register_import(single_match.group(1), single_match.group(2), index + 1)
                index += 1
                continue

            if line.strip() == "import (":
                index += 1
                while index < len(self.lines) and self.lines[index].strip() != ")":
                    entry = _IMPORT_BLOCK_ENTRY_RE.match(self.lines[index])
                    if entry is not None:
                        self._register_import(entry.group(1), entry.group(2), index + 1)
                    index += 1
            index += 1

    def _register_import(self, alias: str | None, module_name: str, line_number: int) -> None:
        local_name = alias or module_name.split("/")[-1]
        if local_name in {"_", "."}:
            local_name = module_name.split("/")[-1]
        import_node = self.builder.create_import_node(
            self.builder.module_node,
            local_name=local_name,
            qualified_name=module_name,
            line_number=line_number,
        )
        self._module_bindings[local_name] = import_node.symbol_key
        if is_likely_repo_local_import(module_name):
            self._import_module_paths[local_name] = dotted_import_module_path(module_name)

    def _collect_top_level_declarations(self) -> None:
        index = 0
        while index < len(self.lines):
            line = self.lines[index]
            if _TYPE_HEADER_RE.match(line):
                _, end_index = self._register_type(index)
                index = end_index + 1
                continue
            if _METHOD_HEADER_RE.match(line):
                _, end_index = self._register_method(index)
                index = end_index + 1
                continue
            if _FUNCTION_HEADER_RE.match(line):
                _, end_index = self._register_function(index)
                index = end_index + 1
                continue
            index += 1

    def _register_type(self, start_index: int) -> tuple[CodeGraphNode, int]:
        header, end_index = self._collect_block(start_index)
        match = _TYPE_HEADER_RE.match(header)
        if match is None:
            raise ValueError(f"Invalid Go type declaration at line {start_index + 1}")

        type_name = match.group(1)
        type_node = self.builder.create_symbol_node(
            kind="CLASS",
            qualified_name=self.builder.compose_qualified_name(self.builder.module_node, type_name),
            local_name=type_name,
            start_line=start_index + 1,
            end_line=end_index + 1,
        )
        self.builder.add_edge(self.builder.module_node.symbol_key, type_node.symbol_key, "CONTAINS")
        self._module_bindings[type_name] = type_node.symbol_key
        self._class_methods.setdefault(type_node.symbol_key, {})
        return type_node, end_index

    def _register_function(self, start_index: int) -> tuple[CodeGraphNode, int]:
        header, end_index = self._collect_block(start_index)
        match = _FUNCTION_HEADER_RE.match(header)
        if match is None:
            raise ValueError(f"Invalid Go function declaration at line {start_index + 1}")

        name = match.group(1)
        function_node = self.builder.create_symbol_node(
            kind="FUNCTION",
            qualified_name=self.builder.compose_qualified_name(self.builder.module_node, name),
            local_name=name,
            start_line=start_index + 1,
            end_line=end_index + 1,
            signature=self._render_function_signature(header),
        )
        self.builder.add_edge(self.builder.module_node.symbol_key, function_node.symbol_key, "CONTAINS")
        self._module_bindings[name] = function_node.symbol_key
        self._routines.append(
            _GoRoutineBlock(node=function_node, start_line=start_index + 1, end_line=end_index + 1)
        )
        return function_node, end_index

    def _register_method(self, start_index: int) -> tuple[CodeGraphNode, int]:
        header, end_index = self._collect_block(start_index)
        match = _METHOD_HEADER_RE.match(header)
        if match is None:
            raise ValueError(f"Invalid Go method declaration at line {start_index + 1}")

        receiver_name, receiver_type, method_name = match.groups()
        owner_symbol_key = self._module_bindings.get(receiver_type)
        owner = (
            self.builder._nodes.get(owner_symbol_key)
            if owner_symbol_key is not None
            else self.builder.module_node
        )
        method_node = self.builder.create_symbol_node(
            kind="METHOD",
            qualified_name=self.builder.compose_qualified_name(owner, method_name),
            local_name=method_name,
            start_line=start_index + 1,
            end_line=end_index + 1,
            signature=self._render_method_signature(header),
        )
        self.builder.add_edge(owner.symbol_key, method_node.symbol_key, "CONTAINS")
        if owner_symbol_key is not None:
            self._class_methods.setdefault(owner_symbol_key, {})[method_name] = method_node.symbol_key
        self._routines.append(
            _GoRoutineBlock(
                node=method_node,
                start_line=start_index + 1,
                end_line=end_index + 1,
                receiver_name=receiver_name,
                receiver_type=receiver_type,
            )
        )
        return method_node, end_index

    @staticmethod
    def _render_function_signature(header: str) -> str:
        compact = " ".join(header.split())
        match = re.search(
            r"^\s*func\s+[A-Za-z_]\w*\s*\((.*?)\)\s*(?:\((.*?)\)|([A-Za-z0-9_*.\[\]]+))?\s*\{",
            compact,
        )
        if match is None:
            return "()"
        args = match.group(1).strip()
        returns = match.group(2).strip() if match.group(2) else (match.group(3).strip() if match.group(3) else "")
        if returns:
            return f"({args}) -> {returns}"
        return f"({args})"

    @staticmethod
    def _render_method_signature(header: str) -> str:
        compact = " ".join(header.split())
        match = re.search(
            r"^\s*func\s*\((.*?)\)\s*[A-Za-z_]\w*\s*\((.*?)\)\s*(?:\((.*?)\)|([A-Za-z0-9_*.\[\]]+))?\s*\{",
            compact,
        )
        if match is None:
            return "()"
        receiver = match.group(1).strip()
        args = match.group(2).strip()
        rendered_args = ", ".join(part for part in [receiver, args] if part)
        returns = match.group(3).strip() if match.group(3) else (match.group(4).strip() if match.group(4) else "")
        if returns:
            return f"({rendered_args}) -> {returns}"
        return f"({rendered_args})"

    def _collect_call_edges(self) -> None:
        for routine in self._routines:
            body = "\n".join(self.lines[routine.start_line - 1 : routine.end_line])
            for match in _CALL_RE.finditer(body):
                callee = match.group(1)
                root = callee.split(".", 1)[0]
                if root in _IGNORED_CALLEES:
                    continue
                target = self._resolve_callee(callee, routine)
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
                        reason="repo_local_import",
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

    def _resolve_callee(self, callee: str, routine: _GoRoutineBlock) -> ResolvedReference | None:
        if "." in callee:
            receiver, member = callee.split(".", 1)
            if receiver == routine.receiver_name and routine.receiver_type is not None:
                owner_symbol_key = self._module_bindings.get(routine.receiver_type)
                if owner_symbol_key is not None:
                    method_symbol_key = self._class_methods.get(owner_symbol_key, {}).get(member)
                    return ResolvedReference(symbol_key=method_symbol_key) if method_symbol_key else None

            target_symbol_key = self._module_bindings.get(receiver)
            if target_symbol_key is None:
                return None
            target_node = self.builder._nodes.get(target_symbol_key)
            if target_node is not None and target_node.kind == "CLASS":
                method_symbol_key = self._class_methods.get(target_symbol_key, {}).get(member)
                return ResolvedReference(symbol_key=method_symbol_key) if method_symbol_key else None
            target_module_path = self._import_module_paths.get(receiver)
            if target_module_path:
                return ResolvedReference(target_qualified_name=".".join([target_module_path, member]))
            return ResolvedReference(symbol_key=target_symbol_key)

        target_symbol_key = self._module_bindings.get(callee)
        return ResolvedReference(symbol_key=target_symbol_key) if target_symbol_key else None

    def _collect_block(self, start_index: int) -> tuple[str, int]:
        block_lines: list[str] = []
        brace_depth = 0
        end_index = start_index

        while end_index < len(self.lines):
            line = self.lines[end_index]
            block_lines.append(line)
            brace_depth += line.count("{") - line.count("}")
            if "{" in line and brace_depth == 0:
                return "\n".join(block_lines), end_index
            if "{" in line and brace_depth > 0:
                break
            end_index += 1

        if brace_depth <= 0:
            return "\n".join(block_lines), end_index

        end_index += 1
        while end_index < len(self.lines):
            line = self.lines[end_index]
            block_lines.append(line)
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                return "\n".join(block_lines), end_index
            end_index += 1

        return "\n".join(block_lines), len(self.lines) - 1
