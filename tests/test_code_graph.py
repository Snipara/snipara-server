"""Tests for Python code graph extraction and indexing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.rlm_engine as rlm_engine_module
from src.rlm_engine import RLMEngine
from src.services.code_graph import (
    CODE_GRAPH_EXTRACTOR_VERSION,
    CodeGraphIndexer,
    CodeGraphQueryService,
    GoCodeExtractor,
    PythonCodeExtractor,
    TypeScriptCodeExtractor,
)

PYTHON_SAMPLE = """
import os


def helper() -> str:
    return "ok"


class RLMEngine:
    def run(self) -> str:
        return self._handle_context_query()

    def _handle_context_query(self) -> str:
        helper()
        return self._render()

    def _render(self) -> str:
        return os.path.join("a", "b")
""".strip()

TYPESCRIPT_SAMPLE = """
import path from "path";

export function helper(name: string): string {
  return name.toUpperCase();
}

export class Renderer {
  run(): string {
    return this.render();
  }

  render(): string {
    helper("ok");
    return path.join("a", "b");
  }
}
""".strip()

GO_SAMPLE = """
package main

import "fmt"

func helper() string {
    return "ok"
}

type Renderer struct{}

func (r *Renderer) Run() string {
    return r.Render()
}

func (r *Renderer) Render() string {
    helper()
    return fmt.Sprintf("%s", "ok")
}
""".strip()

TYPESCRIPT_CROSS_FILE_SAMPLE = """
import { formatResult as format } from "./helpers";
import * as math from "../lib/math";

export function run(): string {
  format("ok");
  math.round();
  missingCall();
  return "ok";
}
""".strip()

GO_CROSS_FILE_SAMPLE = """
package main

import helpers "snipara/shared/helpers"

func Run() string {
    helpers.Format("ok")
    missingCall()
    return "ok"
}
""".strip()


def test_python_extractor_builds_stable_symbol_graph():
    """The Python extractor should emit functions, methods, imports, and call edges."""
    extractor = PythonCodeExtractor("src/rlm_engine.py", PYTHON_SAMPLE)

    graph = extractor.extract()

    nodes = {node.symbol_key: node for node in graph.nodes}
    edges = {
        (edge.from_symbol_key, edge.kind, edge.to_symbol_key)
        for edge in graph.edges
    }

    module_key = "python::src.rlm_engine::module::src.rlm_engine"
    run_key = "python::src.rlm_engine::method::src.rlm_engine.RLMEngine.run"
    handle_key = (
        "python::src.rlm_engine::method::src.rlm_engine.RLMEngine._handle_context_query"
    )
    render_key = "python::src.rlm_engine::method::src.rlm_engine.RLMEngine._render"
    helper_key = "python::src.rlm_engine::function::src.rlm_engine.helper"
    os_import_key = "python::src.rlm_engine::import::src.rlm_engine::os::os"

    assert graph.extractor_version == CODE_GRAPH_EXTRACTOR_VERSION
    assert nodes[module_key].kind == "MODULE"
    assert nodes[run_key].signature == "(self) -> str"
    assert nodes[handle_key].kind == "METHOD"
    assert nodes[helper_key].kind == "FUNCTION"
    assert nodes[os_import_key].kind == "IMPORT"

    assert (module_key, "CONTAINS", helper_key) in edges
    assert (run_key, "CALLS", handle_key) in edges
    assert (handle_key, "CALLS", helper_key) in edges
    assert (handle_key, "CALLS", render_key) in edges
    assert (render_key, "REFERENCES", os_import_key) in edges


def test_typescript_extractor_builds_stable_symbol_graph():
    """The TypeScript extractor should emit class, method, import, and call edges."""
    extractor = TypeScriptCodeExtractor("apps/web/src/components/renderer.ts", TYPESCRIPT_SAMPLE)

    graph = extractor.extract()

    nodes = {node.symbol_key: node for node in graph.nodes}
    edges = {(edge.from_symbol_key, edge.kind, edge.to_symbol_key) for edge in graph.edges}

    module_key = (
        "typescript::apps.web.src.components.renderer::module::apps.web.src.components.renderer"
    )
    helper_key = (
        "typescript::apps.web.src.components.renderer::function::"
        "apps.web.src.components.renderer.helper"
    )
    renderer_key = (
        "typescript::apps.web.src.components.renderer::class::"
        "apps.web.src.components.renderer.Renderer"
    )
    run_key = (
        "typescript::apps.web.src.components.renderer::method::"
        "apps.web.src.components.renderer.Renderer.run"
    )
    render_key = (
        "typescript::apps.web.src.components.renderer::method::"
        "apps.web.src.components.renderer.Renderer.render"
    )
    path_import_key = (
        "typescript::apps.web.src.components.renderer::import::"
        "apps.web.src.components.renderer::path::path"
    )

    assert graph.extractor_version == CODE_GRAPH_EXTRACTOR_VERSION
    assert nodes[module_key].kind == "MODULE"
    assert nodes[helper_key].signature == "(name: string) -> string"
    assert nodes[renderer_key].kind == "CLASS"
    assert nodes[run_key].kind == "METHOD"
    assert nodes[path_import_key].kind == "IMPORT"

    assert (module_key, "CONTAINS", helper_key) in edges
    assert (module_key, "CONTAINS", renderer_key) in edges
    assert (renderer_key, "CONTAINS", run_key) in edges
    assert (run_key, "CALLS", render_key) in edges
    assert (render_key, "CALLS", helper_key) in edges
    assert (render_key, "REFERENCES", path_import_key) in edges


def test_go_extractor_builds_stable_symbol_graph():
    """The Go extractor should emit functions, methods, and import references."""
    extractor = GoCodeExtractor("cmd/server/main.go", GO_SAMPLE)

    graph = extractor.extract()

    nodes = {node.symbol_key: node for node in graph.nodes}
    edges = {(edge.from_symbol_key, edge.kind, edge.to_symbol_key) for edge in graph.edges}

    module_key = "go::cmd.server.main::module::cmd.server.main"
    helper_key = "go::cmd.server.main::function::cmd.server.main.helper"
    renderer_key = "go::cmd.server.main::class::cmd.server.main.Renderer"
    run_key = "go::cmd.server.main::method::cmd.server.main.Renderer.Run"
    render_key = "go::cmd.server.main::method::cmd.server.main.Renderer.Render"
    fmt_import_key = "go::cmd.server.main::import::cmd.server.main::fmt::fmt"

    assert graph.extractor_version == CODE_GRAPH_EXTRACTOR_VERSION
    assert nodes[module_key].kind == "MODULE"
    assert nodes[helper_key].kind == "FUNCTION"
    assert nodes[renderer_key].kind == "CLASS"
    assert nodes[run_key].signature == "(r *Renderer) -> string"
    assert nodes[fmt_import_key].kind == "IMPORT"

    assert (module_key, "CONTAINS", helper_key) in edges
    assert (renderer_key, "CONTAINS", run_key) in edges
    assert (run_key, "CALLS", render_key) in edges
    assert (render_key, "CALLS", helper_key) in edges
    assert (render_key, "REFERENCES", fmt_import_key) in edges


def test_typescript_extractor_tracks_cross_file_candidates_and_unresolved_calls():
    """Relative imports should emit cross-file hints and unresolved calls should be tracked."""
    extractor = TypeScriptCodeExtractor(
        "apps/web/src/components/renderer.ts",
        TYPESCRIPT_CROSS_FILE_SAMPLE,
    )

    graph = extractor.extract()
    hints = {
        (hint.callee, hint.state, hint.target_qualified_name, hint.reason)
        for hint in graph.reference_hints
    }

    assert (
        "format",
        "cross_file_candidate",
        "apps.web.src.components.helpers.formatResult",
        "relative_import",
    ) in hints
    assert (
        "math.round",
        "cross_file_candidate",
        "apps.web.src.lib.math.round",
        "relative_import",
    ) in hints
    assert ("missingCall", "unresolved", None, "unknown_binding") in hints


def test_go_extractor_tracks_repo_local_import_candidates_and_unresolved_calls():
    """Repo-local Go imports should emit cross-file hints while unknown calls stay tracked."""
    extractor = GoCodeExtractor("cmd/server/main.go", GO_CROSS_FILE_SAMPLE)

    graph = extractor.extract()
    hints = {
        (hint.callee, hint.state, hint.target_qualified_name, hint.reason)
        for hint in graph.reference_hints
    }

    assert (
        "helpers.Format",
        "cross_file_candidate",
        "snipara.shared.helpers.Format",
        "repo_local_import",
    ) in hints
    assert ("missingCall", "unresolved", None, "unknown_binding") in hints


@pytest.mark.asyncio
async def test_code_graph_indexer_skips_when_hash_and_version_match():
    """A matching state row should avoid deleting and rewriting graph rows."""
    db = AsyncMock()
    db.document.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            id="doc-1",
            projectId="proj-1",
            path="src/rlm_engine.py",
            content=PYTHON_SAMPLE,
            hash="abc123",
            kind="CODE",
            language="python",
            format="py",
        )
    )
    db.query_raw = AsyncMock(
        return_value=[{"documentHash": "abc123", "extractorVersion": CODE_GRAPH_EXTRACTOR_VERSION}]
    )
    db.execute_raw = AsyncMock()

    indexer = CodeGraphIndexer(db)
    result = await indexer.index_document("doc-1")

    assert result.skipped is True
    assert result.reason == "hash_match"
    db.execute_raw.assert_not_called()


@pytest.mark.asyncio
async def test_code_graph_indexer_supports_typescript_documents():
    """TypeScript CODE documents should route through the multi-language registry."""
    db = AsyncMock()
    db.document.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            id="doc-ts",
            projectId="proj-1",
            path="apps/web/src/components/renderer.ts",
            content=TYPESCRIPT_SAMPLE,
            hash="ts123",
            kind="CODE",
            language="typescript",
            format="ts",
        )
    )
    db.query_raw = AsyncMock(return_value=[])
    db.execute_raw = AsyncMock()

    indexer = CodeGraphIndexer(db)
    result = await indexer.index_document("doc-ts")

    assert result.skipped is False
    assert result.node_count >= 4
    assert result.edge_count >= 5


@pytest.mark.asyncio
async def test_code_graph_indexer_resolves_cross_file_reference_hints():
    """Cross-file reference hints should become heuristic edges when the target exists."""
    from src.services.code_graph.models import CodeGraphNode, CodeGraphReferenceHint, ExtractedCodeGraph

    db = AsyncMock()
    indexer = CodeGraphIndexer(db)

    document = SimpleNamespace(
        id="doc-ts",
        projectId="proj-1",
        path="apps/web/src/components/renderer.ts",
        hash="ts123",
    )
    graph = ExtractedCodeGraph(
        nodes=[
            CodeGraphNode(
                symbol_key="typescript::apps.web.src.components.renderer::module::apps.web.src.components.renderer",
                kind="MODULE",
                language="typescript",
                module_path="apps.web.src.components.renderer",
                qualified_name="apps.web.src.components.renderer",
                local_name="renderer",
                start_line=1,
                end_line=10,
            ),
            CodeGraphNode(
                symbol_key=(
                    "typescript::apps.web.src.components.renderer::function::"
                    "apps.web.src.components.renderer.run"
                ),
                kind="FUNCTION",
                language="typescript",
                module_path="apps.web.src.components.renderer",
                qualified_name="apps.web.src.components.renderer.run",
                local_name="run",
                start_line=4,
                end_line=8,
                signature="() -> string",
            ),
        ],
        reference_hints=[
            CodeGraphReferenceHint(
                from_symbol_key=(
                    "typescript::apps.web.src.components.renderer::function::"
                    "apps.web.src.components.renderer.run"
                ),
                relationship="CALLS",
                callee="format",
                target_qualified_name="apps.web.src.components.helpers.formatResult",
                state="cross_file_candidate",
                reason="relative_import",
            )
        ],
        extractor_version=CODE_GRAPH_EXTRACTOR_VERSION,
    )
    db.query_raw = AsyncMock(
        return_value=[
            {
                "id": "target-node",
                "qualifiedName": "apps.web.src.components.helpers.formatResult",
            }
        ]
    )
    db.execute_raw = AsyncMock()

    await indexer._persist_graph(document, graph)

    heuristic_edge_calls = [
        call
        for call in db.execute_raw.await_args_list
        if "INSERT INTO code_edges" in call.args[0] and call.args[5] == "CALLS" and call.args[6] == "HEURISTIC"
    ]
    assert len(heuristic_edge_calls) == 1


@pytest.mark.asyncio
async def test_code_graph_query_service_returns_callers():
    """Reverse CALLS traversal should find direct callers of a method."""
    db = AsyncMock()
    db.query_raw = AsyncMock(
        side_effect=[
            [
                {
                    "id": "module",
                    "symbolKey": "python::src.rlm_engine::module::src.rlm_engine",
                    "qualifiedName": "src.rlm_engine",
                    "localName": "rlm_engine",
                    "kind": "MODULE",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 1,
                    "endLine": 20,
                    "signature": None,
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "run",
                    "symbolKey": "python::src.rlm_engine::method::src.rlm_engine.RLMEngine.run",
                    "qualifiedName": "src.rlm_engine.RLMEngine.run",
                    "localName": "run",
                    "kind": "METHOD",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 8,
                    "endLine": 9,
                    "signature": "(self) -> str",
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "handle",
                    "symbolKey": (
                        "python::src.rlm_engine::method::"
                        "src.rlm_engine.RLMEngine._handle_context_query"
                    ),
                    "qualifiedName": "src.rlm_engine.RLMEngine._handle_context_query",
                    "localName": "_handle_context_query",
                    "kind": "METHOD",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 11,
                    "endLine": 14,
                    "signature": "(self) -> str",
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "helper",
                    "symbolKey": "python::src.rlm_engine::function::src.rlm_engine.helper",
                    "qualifiedName": "src.rlm_engine.helper",
                    "localName": "helper",
                    "kind": "FUNCTION",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 4,
                    "endLine": 5,
                    "signature": "() -> str",
                    "file_path": "src/rlm_engine.py",
                },
            ],
            [
                {
                    "fromNodeId": "run",
                    "toNodeId": "handle",
                    "kind": "CALLS",
                    "source": "AST",
                    "confidence": 1.0,
                },
                {
                    "fromNodeId": "handle",
                    "toNodeId": "helper",
                    "kind": "CALLS",
                    "source": "AST",
                    "confidence": 1.0,
                },
            ],
        ]
    )

    service = CodeGraphQueryService(db, "proj-1")
    result = await service.get_callers(
        qualified_name="src.rlm_engine.RLMEngine._handle_context_query",
        depth=1,
        limit=20,
    )

    assert result["total_callers"] == 1
    assert result["callers"][0]["qualified_name"] == "src.rlm_engine.RLMEngine.run"
    assert result["callers"][0]["depth"] == 1


@pytest.mark.asyncio
async def test_code_graph_query_service_compacts_file_import_targets_by_default():
    """File-level import scans should return a compact module anchor by default."""
    db = AsyncMock()
    db.query_raw = AsyncMock(
        side_effect=[
            [
                {
                    "id": "module",
                    "symbolKey": "python::src.rlm_engine::module::src.rlm_engine",
                    "qualifiedName": "src.rlm_engine",
                    "localName": "rlm_engine",
                    "kind": "MODULE",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 1,
                    "endLine": 40,
                    "signature": None,
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "helper",
                    "symbolKey": "python::src.rlm_engine::function::src.rlm_engine.helper",
                    "qualifiedName": "src.rlm_engine.helper",
                    "localName": "helper",
                    "kind": "FUNCTION",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 4,
                    "endLine": 6,
                    "signature": "() -> str",
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "render",
                    "symbolKey": "python::src.rlm_engine::method::src.rlm_engine.RLMEngine._render",
                    "qualifiedName": "src.rlm_engine.RLMEngine._render",
                    "localName": "_render",
                    "kind": "METHOD",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 18,
                    "endLine": 20,
                    "signature": "(self) -> str",
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "os-import",
                    "symbolKey": "python::src.rlm_engine::import::src.rlm_engine::os::os",
                    "qualifiedName": "os",
                    "localName": "os",
                    "kind": "IMPORT",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 2,
                    "endLine": 2,
                    "signature": None,
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "json-import",
                    "symbolKey": "python::src.rlm_engine::import::src.rlm_engine::json::json",
                    "qualifiedName": "json",
                    "localName": "json",
                    "kind": "IMPORT",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 3,
                    "endLine": 3,
                    "signature": None,
                    "file_path": "src/rlm_engine.py",
                },
            ],
            [
                {
                    "fromNodeId": "module",
                    "toNodeId": "os-import",
                    "kind": "IMPORTS",
                    "source": "AST",
                    "confidence": 1.0,
                },
                {
                    "fromNodeId": "helper",
                    "toNodeId": "os-import",
                    "kind": "IMPORTS",
                    "source": "AST",
                    "confidence": 1.0,
                },
                {
                    "fromNodeId": "render",
                    "toNodeId": "json-import",
                    "kind": "IMPORTS",
                    "source": "AST",
                    "confidence": 1.0,
                },
            ],
        ]
    )

    service = CodeGraphQueryService(db, "proj-1")
    result = await service.get_imports(file_path="src/rlm_engine.py", direction="out", limit=20)

    assert result["compacted"] is True
    assert result["matched_target_count"] == 1
    assert result["scanned_target_count"] == 5
    assert [node["qualified_name"] for node in result["matched_targets"]] == ["src.rlm_engine"]
    assert [node["qualified_name"] for node in result["imports"]] == ["os", "json"]
    assert result["total_imports"] == 2


@pytest.mark.asyncio
async def test_code_graph_query_service_can_include_file_import_nodes():
    """File-level import scans should expose every scanned node when requested."""
    db = AsyncMock()
    db.query_raw = AsyncMock(
        side_effect=[
            [
                {
                    "id": "module",
                    "symbolKey": "python::src.rlm_engine::module::src.rlm_engine",
                    "qualifiedName": "src.rlm_engine",
                    "localName": "rlm_engine",
                    "kind": "MODULE",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 1,
                    "endLine": 40,
                    "signature": None,
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "helper",
                    "symbolKey": "python::src.rlm_engine::function::src.rlm_engine.helper",
                    "qualifiedName": "src.rlm_engine.helper",
                    "localName": "helper",
                    "kind": "FUNCTION",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 4,
                    "endLine": 6,
                    "signature": "() -> str",
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "render",
                    "symbolKey": "python::src.rlm_engine::method::src.rlm_engine.RLMEngine._render",
                    "qualifiedName": "src.rlm_engine.RLMEngine._render",
                    "localName": "_render",
                    "kind": "METHOD",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 18,
                    "endLine": 20,
                    "signature": "(self) -> str",
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "os-import",
                    "symbolKey": "python::src.rlm_engine::import::src.rlm_engine::os::os",
                    "qualifiedName": "os",
                    "localName": "os",
                    "kind": "IMPORT",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 2,
                    "endLine": 2,
                    "signature": None,
                    "file_path": "src/rlm_engine.py",
                },
            ],
            [
                {
                    "fromNodeId": "module",
                    "toNodeId": "os-import",
                    "kind": "IMPORTS",
                    "source": "AST",
                    "confidence": 1.0,
                },
                {
                    "fromNodeId": "helper",
                    "toNodeId": "os-import",
                    "kind": "IMPORTS",
                    "source": "AST",
                    "confidence": 1.0,
                },
            ],
        ]
    )

    service = CodeGraphQueryService(db, "proj-1")
    result = await service.get_imports(
        file_path="src/rlm_engine.py",
        direction="out",
        include_file_nodes=True,
        limit=20,
    )

    assert result["compacted"] is False
    assert result["matched_target_count"] == 4
    assert result["scanned_target_count"] == 4
    assert len(result["matched_targets"]) == 4
    assert result["total_imports"] == 1


@pytest.mark.asyncio
async def test_code_graph_query_service_finds_shortest_path():
    """Shortest path should return the structural chain between two symbols."""
    db = AsyncMock()
    db.query_raw = AsyncMock(
        side_effect=[
            [
                {
                    "id": "run",
                    "symbolKey": "python::src.rlm_engine::method::src.rlm_engine.RLMEngine.run",
                    "qualifiedName": "src.rlm_engine.RLMEngine.run",
                    "localName": "run",
                    "kind": "METHOD",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 8,
                    "endLine": 9,
                    "signature": "(self) -> str",
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "handle",
                    "symbolKey": (
                        "python::src.rlm_engine::method::"
                        "src.rlm_engine.RLMEngine._handle_context_query"
                    ),
                    "qualifiedName": "src.rlm_engine.RLMEngine._handle_context_query",
                    "localName": "_handle_context_query",
                    "kind": "METHOD",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 11,
                    "endLine": 14,
                    "signature": "(self) -> str",
                    "file_path": "src/rlm_engine.py",
                },
                {
                    "id": "helper",
                    "symbolKey": "python::src.rlm_engine::function::src.rlm_engine.helper",
                    "qualifiedName": "src.rlm_engine.helper",
                    "localName": "helper",
                    "kind": "FUNCTION",
                    "language": "python",
                    "modulePath": "src.rlm_engine",
                    "startLine": 4,
                    "endLine": 5,
                    "signature": "() -> str",
                    "file_path": "src/rlm_engine.py",
                },
            ],
            [
                {
                    "fromNodeId": "run",
                    "toNodeId": "handle",
                    "kind": "CALLS",
                    "source": "AST",
                    "confidence": 1.0,
                },
                {
                    "fromNodeId": "handle",
                    "toNodeId": "helper",
                    "kind": "CALLS",
                    "source": "AST",
                    "confidence": 1.0,
                },
            ],
        ]
    )

    service = CodeGraphQueryService(db, "proj-1")
    result = await service.get_shortest_path(
        from_qualified_name="src.rlm_engine.RLMEngine.run",
        to_qualified_name="src.rlm_engine.helper",
        max_hops=4,
    )

    assert result["found"] is True
    assert result["hops"] == 2
    assert [node["qualified_name"] for node in result["path"]] == [
        "src.rlm_engine.RLMEngine.run",
        "src.rlm_engine.RLMEngine._handle_context_query",
        "src.rlm_engine.helper",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "service_method", "params", "expected_key"),
    [
        (
            "_handle_code_callers",
            "get_callers",
            {"qualified_name": "src.rlm_engine.RLMEngine._handle_context_query"},
            "total_callers",
        ),
        (
            "_handle_code_imports",
            "get_imports",
            {"file_path": "src/rlm_engine.py", "direction": "out"},
            "total_imports",
        ),
        (
            "_handle_code_neighbors",
            "get_neighbors",
            {"qualified_name": "src.rlm_engine.RLMEngine"},
            "nodes",
        ),
        (
            "_handle_code_shortest_path",
            "get_shortest_path",
            {"from": "src.rlm_engine.RLMEngine.run", "to": "src.rlm_engine.helper"},
            "found",
        ),
    ],
)
async def test_code_graph_handlers_acquire_db_for_runtime_queries(
    monkeypatch,
    handler_name,
    service_method,
    params,
    expected_key,
):
    """Code graph handlers should fetch a live DB client instead of reading self.db."""
    db = object()

    async def fake_get_db():
        return db

    async def fake_service(self, **kwargs):
        assert self.db is db
        if service_method == "get_shortest_path":
            return {"found": False, "path": [], "edges": [], "hops": 0}
        if service_method == "get_neighbors":
            return {"matched_targets": [], "nodes": [], "edges": [], "depth": kwargs.get("depth", 2)}
        if service_method == "get_imports":
            return {
                "matched_targets": [],
                "direction": kwargs.get("direction", "out"),
                "imports": [],
                "total_imports": 0,
            }
        return {"matched_targets": [], "callers": [], "depth": kwargs.get("depth", 1), "total_callers": 0}

    monkeypatch.setattr(rlm_engine_module, "get_db", fake_get_db)
    monkeypatch.setattr(CodeGraphQueryService, service_method, fake_service)

    engine = RLMEngine("proj-1")
    result = await getattr(engine, handler_name)(params)

    assert expected_key in result.data
