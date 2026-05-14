"""Query helpers for traversing persisted code graphs."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from prisma import Prisma


DEFAULT_NEIGHBOR_EDGE_KINDS = ("CALLS", "CONTAINS", "IMPORTS", "REFERENCES")


@dataclass
class _GraphSnapshot:
    nodes: dict[str, dict[str, Any]]
    outgoing: dict[str, list[dict[str, Any]]]
    incoming: dict[str, list[dict[str, Any]]]


class CodeGraphQueryService:
    """Traverse the code graph for a single project."""

    def __init__(self, db: Prisma, project_id: str):
        self.db = db
        self.project_id = project_id

    async def get_callers(
        self,
        *,
        qualified_name: str | None = None,
        symbol_key: str | None = None,
        depth: int = 1,
        limit: int = 50,
    ) -> dict[str, Any]:
        snapshot = await self._load_snapshot()
        matched_targets = self._resolve_nodes(
            snapshot,
            qualified_name=qualified_name,
            symbol_key=symbol_key,
        )

        caller_depth: dict[str, int] = {}
        frontier = {node["id"] for node in matched_targets}
        visited = set(frontier)

        for current_depth in range(1, max(1, depth) + 1):
            next_frontier: set[str] = set()
            for node_id in frontier:
                for edge in snapshot.incoming.get(node_id, []):
                    if edge["kind"] != "CALLS":
                        continue

                    caller_id = edge["fromNodeId"]
                    if caller_id in visited:
                        continue

                    visited.add(caller_id)
                    caller_depth[caller_id] = current_depth
                    next_frontier.add(caller_id)

            if not next_frontier:
                break
            frontier = next_frontier

        callers = [
            self._node_payload(snapshot.nodes[node_id], depth=caller_depth[node_id])
            for node_id in caller_depth
            if node_id in snapshot.nodes
        ]
        callers.sort(key=lambda node: (node.get("depth", 0), node["file_path"], node["start_line"]))

        return {
            "matched_targets": [self._node_payload(node) for node in matched_targets],
            "callers": callers[:limit],
            "depth": max(1, depth),
            "total_callers": len(callers),
        }

    async def get_imports(
        self,
        *,
        qualified_name: str | None = None,
        symbol_key: str | None = None,
        file_path: str | None = None,
        direction: str = "out",
        limit: int = 50,
        include_file_nodes: bool = False,
    ) -> dict[str, Any]:
        snapshot = await self._load_snapshot()
        direction = "in" if direction == "in" else "out"

        matched_targets = self._resolve_nodes(
            snapshot,
            qualified_name=qualified_name,
            symbol_key=symbol_key,
            file_path=file_path,
        )
        traversal_targets = matched_targets

        if file_path and direction == "out":
            traversal_targets = self._resolve_nodes(
                snapshot,
                file_path=file_path,
                include_all_file_nodes=True,
            )
            if include_file_nodes:
                matched_targets = traversal_targets
            elif not matched_targets:
                matched_targets = traversal_targets[:1]

        scanned_target_count = len(traversal_targets)
        matched_target_count = len(matched_targets)
        compacted = matched_target_count < scanned_target_count

        if direction == "out":
            imports: dict[str, dict[str, Any]] = {}
            for node in traversal_targets:
                for edge in snapshot.outgoing.get(node["id"], []):
                    if edge["kind"] != "IMPORTS":
                        continue
                    imported = snapshot.nodes.get(edge["toNodeId"])
                    if imported is None:
                        continue
                    imports[imported["id"]] = self._node_payload(imported)

            results = list(imports.values())
            results.sort(key=lambda node: (node["file_path"], node["start_line"], node["qualified_name"]))
            return {
                "matched_targets": [self._node_payload(node) for node in matched_targets],
                "direction": direction,
                "compacted": compacted,
                "matched_target_count": matched_target_count,
                "scanned_target_count": scanned_target_count,
                "imports": results[:limit],
                "total_imports": len(results),
            }

        importers: dict[str, dict[str, Any]] = {}
        target_names = {node["qualifiedName"] for node in matched_targets}
        matching_import_nodes = [
            node
            for node in snapshot.nodes.values()
            if node["kind"] == "IMPORT"
            and any(
                node["qualifiedName"] == target_name
                or node["qualifiedName"].startswith(f"{target_name}.")
                for target_name in target_names
            )
        ]

        for import_node in matching_import_nodes:
            for edge in snapshot.incoming.get(import_node["id"], []):
                if edge["kind"] != "IMPORTS":
                    continue
                importer = snapshot.nodes.get(edge["fromNodeId"])
                if importer is None:
                    continue
                importers[importer["id"]] = self._node_payload(importer)

        results = list(importers.values())
        results.sort(key=lambda node: (node["file_path"], node["start_line"], node["qualified_name"]))
        return {
            "matched_targets": [self._node_payload(node) for node in matched_targets],
            "direction": direction,
            "compacted": compacted,
            "matched_target_count": matched_target_count,
            "scanned_target_count": scanned_target_count,
            "imports": results[:limit],
            "total_imports": len(results),
        }

    async def get_neighbors(
        self,
        *,
        qualified_name: str | None = None,
        symbol_key: str | None = None,
        depth: int = 2,
        edge_kinds: list[str] | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        snapshot = await self._load_snapshot()
        matched_targets = self._resolve_nodes(
            snapshot,
            qualified_name=qualified_name,
            symbol_key=symbol_key,
        )
        allowed = {kind.upper() for kind in (edge_kinds or DEFAULT_NEIGHBOR_EDGE_KINDS)}
        queue = deque((node["id"], 0) for node in matched_targets)
        node_depths = {node["id"]: 0 for node in matched_targets}
        edge_map: dict[tuple[str, str, str], dict[str, Any]] = {}

        while queue:
            node_id, current_depth = queue.popleft()
            if current_depth >= max(1, depth):
                continue

            adjacent_edges = snapshot.outgoing.get(node_id, []) + snapshot.incoming.get(node_id, [])
            for edge in adjacent_edges:
                if edge["kind"] not in allowed:
                    continue

                neighbor_id = (
                    edge["toNodeId"] if edge["fromNodeId"] == node_id else edge["fromNodeId"]
                )
                edge_map[(edge["fromNodeId"], edge["toNodeId"], edge["kind"])] = edge

                if neighbor_id in node_depths:
                    continue

                node_depths[neighbor_id] = current_depth + 1
                queue.append((neighbor_id, current_depth + 1))

        nodes = [
            self._node_payload(snapshot.nodes[node_id], depth=node_depths[node_id])
            for node_id in node_depths
            if node_id in snapshot.nodes
        ]
        nodes.sort(key=lambda node: (node.get("depth", 0), node["file_path"], node["start_line"]))
        edges = [
            self._edge_payload(snapshot, edge)
            for edge in edge_map.values()
            if edge["fromNodeId"] in node_depths and edge["toNodeId"] in node_depths
        ]
        edges.sort(key=lambda edge: (edge["kind"], edge["from_symbol_key"], edge["to_symbol_key"]))

        return {
            "matched_targets": [self._node_payload(node) for node in matched_targets],
            "nodes": nodes[:limit],
            "edges": edges[:limit],
            "depth": max(1, depth),
        }

    async def get_shortest_path(
        self,
        *,
        from_qualified_name: str | None = None,
        from_symbol_key: str | None = None,
        to_qualified_name: str | None = None,
        to_symbol_key: str | None = None,
        edge_kinds: list[str] | None = None,
        max_hops: int = 6,
    ) -> dict[str, Any]:
        snapshot = await self._load_snapshot()
        starts = self._resolve_nodes(
            snapshot,
            qualified_name=from_qualified_name,
            symbol_key=from_symbol_key,
        )
        targets = self._resolve_nodes(
            snapshot,
            qualified_name=to_qualified_name,
            symbol_key=to_symbol_key,
        )
        allowed = {kind.upper() for kind in (edge_kinds or DEFAULT_NEIGHBOR_EDGE_KINDS)}
        target_ids = {node["id"] for node in targets}

        previous: dict[str, tuple[str | None, dict[str, Any] | None]] = {
            node["id"]: (None, None) for node in starts
        }
        depths = {node["id"]: 0 for node in starts}
        queue = deque(node["id"] for node in starts)
        found_id: str | None = None

        while queue:
            node_id = queue.popleft()
            current_depth = depths[node_id]

            if node_id in target_ids:
                found_id = node_id
                break

            if current_depth >= max(1, max_hops):
                continue

            for edge in snapshot.outgoing.get(node_id, []) + snapshot.incoming.get(node_id, []):
                if edge["kind"] not in allowed:
                    continue

                neighbor_id = (
                    edge["toNodeId"] if edge["fromNodeId"] == node_id else edge["fromNodeId"]
                )
                if neighbor_id in previous:
                    continue

                previous[neighbor_id] = (node_id, edge)
                depths[neighbor_id] = current_depth + 1
                queue.append(neighbor_id)

        if found_id is None:
            return {
                "matched_sources": [self._node_payload(node) for node in starts],
                "matched_targets": [self._node_payload(node) for node in targets],
                "found": False,
                "path": [],
                "edges": [],
                "hops": 0,
            }

        node_ids: list[str] = []
        edges: list[dict[str, Any]] = []
        current_id: str | None = found_id
        while current_id is not None:
            node_ids.append(current_id)
            previous_id, edge = previous[current_id]
            if edge is not None:
                edges.append(self._edge_payload(snapshot, edge))
            current_id = previous_id

        node_ids.reverse()
        edges.reverse()

        return {
            "matched_sources": [self._node_payload(node) for node in starts],
            "matched_targets": [self._node_payload(node) for node in targets],
            "found": True,
            "path": [self._node_payload(snapshot.nodes[node_id]) for node_id in node_ids],
            "edges": edges,
            "hops": max(0, len(node_ids) - 1),
        }

    async def _load_snapshot(self) -> _GraphSnapshot:
        node_rows = await self.db.query_raw(
            """
            SELECT
              n.id,
              n."symbolKey",
              n."qualifiedName",
              n."localName",
              n.kind,
              n.language,
              n."modulePath",
              n."startLine",
              n."endLine",
              n.signature,
              d.path AS file_path
            FROM code_nodes n
            JOIN documents d ON n."documentId" = d.id
            WHERE n."projectId" = $1
            """,
            self.project_id,
        )
        edge_rows = await self.db.query_raw(
            """
            SELECT "fromNodeId", "toNodeId", kind, source, confidence
            FROM code_edges
            WHERE "projectId" = $1
            """,
            self.project_id,
        )

        nodes = {row["id"]: row for row in node_rows}
        outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for edge in edge_rows:
            outgoing[edge["fromNodeId"]].append(edge)
            incoming[edge["toNodeId"]].append(edge)

        return _GraphSnapshot(nodes=nodes, outgoing=outgoing, incoming=incoming)

    def _resolve_nodes(
        self,
        snapshot: _GraphSnapshot,
        *,
        qualified_name: str | None = None,
        symbol_key: str | None = None,
        file_path: str | None = None,
        include_all_file_nodes: bool = False,
    ) -> list[dict[str, Any]]:
        nodes = list(snapshot.nodes.values())
        if symbol_key:
            matched = [node for node in nodes if node["symbolKey"] == symbol_key]
        elif qualified_name:
            matched = [node for node in nodes if node["qualifiedName"] == qualified_name]
        elif file_path:
            matched = [node for node in nodes if node["file_path"] == file_path]
            if not include_all_file_nodes:
                matched = [node for node in matched if node["kind"] == "MODULE"]
        else:
            matched = []

        matched.sort(key=lambda node: (node["file_path"], node["startLine"], node["qualifiedName"]))
        return matched

    @staticmethod
    def _node_payload(node: dict[str, Any], *, depth: int | None = None) -> dict[str, Any]:
        payload = {
            "symbol_key": node["symbolKey"],
            "qualified_name": node["qualifiedName"],
            "local_name": node["localName"],
            "kind": node["kind"],
            "language": node["language"],
            "module_path": node["modulePath"],
            "file_path": node["file_path"],
            "start_line": node["startLine"],
            "end_line": node["endLine"],
            "signature": node.get("signature"),
        }
        if depth is not None:
            payload["depth"] = depth
        return payload

    @staticmethod
    def _edge_payload(snapshot: _GraphSnapshot, edge: dict[str, Any]) -> dict[str, Any]:
        from_node = snapshot.nodes.get(edge["fromNodeId"])
        to_node = snapshot.nodes.get(edge["toNodeId"])
        return {
            "from_symbol_key": from_node["symbolKey"] if from_node else edge["fromNodeId"],
            "to_symbol_key": to_node["symbolKey"] if to_node else edge["toNodeId"],
            "from_qualified_name": from_node["qualifiedName"] if from_node else None,
            "to_qualified_name": to_node["qualifiedName"] if to_node else None,
            "kind": edge["kind"],
            "source": edge["source"],
            "confidence": edge["confidence"],
        }
