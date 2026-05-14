"""Graphify-compatible export helpers for persisted Snipara code graphs."""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from prisma import Prisma


def _normalize_label(label: str) -> str:
    """Normalize labels for diacritic-insensitive matching."""
    normalized = unicodedata.normalize("NFKD", label)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _graphify_confidence(source: str, confidence: float) -> str:
    """Map Snipara edge provenance onto Graphify's confidence labels."""
    if source == "AST" and confidence >= 1.0:
        return "EXTRACTED"
    if confidence < 0.5:
        return "AMBIGUOUS"
    return "INFERRED"


def _source_location(start_line: int, end_line: int) -> str:
    """Render a Graphify-style source location string."""
    if start_line == end_line:
        return f"L{start_line}"
    return f"L{start_line}-L{end_line}"


def _serialize_timestamp(value: datetime | str | None) -> str | None:
    """Serialize timestamps returned by Prisma raw queries."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def build_graphify_payload(
    *,
    project_id: str,
    project_slug: str,
    project_name: str,
    node_rows: list[dict[str, Any]],
    edge_rows: list[dict[str, Any]],
    indexed_document_count: int,
    last_indexed_at: datetime | None,
    directed: bool,
) -> dict[str, Any]:
    """Build a Graphify-compatible node-link graph payload."""
    nodes = []
    languages: set[str] = set()

    for row in node_rows:
        label = row["qualifiedName"]
        languages.add(row["language"])
        nodes.append(
            {
                "id": row["symbolKey"],
                "label": label,
                "norm_label": _normalize_label(label),
                "file_type": row["language"],
                "kind": row["kind"].lower(),
                "language": row["language"],
                "source_file": row["file_path"],
                "source_location": _source_location(row["startLine"], row["endLine"]),
                "qualified_name": row["qualifiedName"],
                "local_name": row["localName"],
                "module_path": row["modulePath"],
                "signature": row.get("signature"),
            }
        )

    links = []
    for row in edge_rows:
        links.append(
            {
                "source": row["fromSymbolKey"],
                "target": row["toSymbolKey"],
                "relation": row["kind"].lower(),
                "confidence": _graphify_confidence(row["source"], float(row["confidence"])),
                "confidence_score": round(float(row["confidence"]), 3),
                "source_kind": row["source"],
                "from_qualified_name": row["fromQualifiedName"],
                "to_qualified_name": row["toQualifiedName"],
            }
        )

    return {
        "directed": directed,
        "multigraph": False,
        "graph": {
            "adapter": "snipara-graphify",
            "schema": "graphify-node-link-v1-subset",
            "generated_at": datetime.now(UTC).isoformat(),
            "project_id": project_id,
            "project_slug": project_slug,
            "project_name": project_name,
            "export_mode": "directed" if directed else "undirected",
            "node_count": len(nodes),
            "edge_count": len(links),
            "indexed_document_count": indexed_document_count,
            "languages": sorted(languages),
            "last_indexed_at": _serialize_timestamp(last_indexed_at),
            "compatibility_notes": [
                "Graphify-compatible node-link JSON for MCP/serve workflows",
                "Communities and multimodal semantic passes are not included in this export",
            ],
        },
        "nodes": nodes,
        "links": links,
    }


class GraphifyExportService:
    """Export persisted Snipara code graphs as Graphify-compatible node-link JSON."""

    def __init__(self, db: Prisma):
        self.db = db

    async def export_project_graph(
        self,
        *,
        project_id: str,
        project_slug: str,
        project_name: str,
        directed: bool = False,
    ) -> dict[str, Any]:
        """Export one project's code graph as a Graphify-compatible payload."""
        node_rows = await self.db.query_raw(
            """
            SELECT
              n."symbolKey",
              n.kind,
              n.language,
              n."modulePath",
              n."qualifiedName",
              n."localName",
              n."startLine",
              n."endLine",
              n.signature,
              d.path AS file_path
            FROM code_nodes n
            JOIN documents d ON n."documentId" = d.id
            WHERE n."projectId" = $1
            ORDER BY d.path, n."startLine", n."qualifiedName"
            """,
            project_id,
        )
        edge_rows = await self.db.query_raw(
            """
            SELECT
              e.kind,
              e.source,
              e.confidence,
              fn."symbolKey" AS "fromSymbolKey",
              fn."qualifiedName" AS "fromQualifiedName",
              tn."symbolKey" AS "toSymbolKey",
              tn."qualifiedName" AS "toQualifiedName"
            FROM code_edges e
            JOIN code_nodes fn ON e."fromNodeId" = fn.id
            JOIN code_nodes tn ON e."toNodeId" = tn.id
            WHERE e."projectId" = $1
            ORDER BY fn."symbolKey", tn."symbolKey", e.kind
            """,
            project_id,
        )
        index_stats = await self.db.query_raw(
            """
            SELECT
              COUNT(*)::int AS indexed_document_count,
              MAX("indexedAt") AS last_indexed_at
            FROM code_index_state
            WHERE "projectId" = $1
            """,
            project_id,
        )
        stats = index_stats[0] if index_stats else {}

        return build_graphify_payload(
            project_id=project_id,
            project_slug=project_slug,
            project_name=project_name,
            node_rows=node_rows,
            edge_rows=edge_rows,
            indexed_document_count=int(stats.get("indexed_document_count", 0) or 0),
            last_indexed_at=stats.get("last_indexed_at"),
            directed=directed,
        )
