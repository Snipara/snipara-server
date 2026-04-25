"""Persistence and indexing for code graph extraction."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .models import ExtractedCodeGraph
from .registry import (
    CODE_GRAPH_EXTRACTOR_VERSION,
    FORMAT_TO_LANGUAGE,
    SUPPORTED_CODE_FORMATS,
    SUPPORTED_CODE_LANGUAGES,
    get_extractor_for_document,
    infer_document_language,
)

if TYPE_CHECKING:
    from prisma import Prisma

logger = logging.getLogger(__name__)


@dataclass
class CodeDocumentIndexResult:
    """Result of indexing a single code document."""

    document_id: str
    path: str
    node_count: int
    edge_count: int
    skipped: bool = False
    reason: str | None = None


class CodeGraphIndexer:
    """Index CODE documents into code graph tables."""

    def __init__(self, db: Prisma):
        self.db = db

    async def index_document(self, document_id: str) -> CodeDocumentIndexResult:
        """Extract and persist the code graph for one document."""
        document = await self.db.document.find_unique(where={"id": document_id})
        if not document:
            logger.warning("Code graph document not found: %s", document_id)
            return CodeDocumentIndexResult(
                document_id=document_id,
                path="",
                node_count=0,
                edge_count=0,
                skipped=True,
                reason="missing_document",
            )

        if not self._is_supported_document(document):
            logger.info(
                "Skipping unsupported CODE document for graph extraction: %s (%s/%s)",
                document.path,
                getattr(document, "language", None),
                getattr(document, "format", None),
            )
            return CodeDocumentIndexResult(
                document_id=document.id,
                path=document.path,
                node_count=0,
                edge_count=0,
                skipped=True,
                reason="unsupported_language",
            )

        existing_state = await self._load_index_state(document.id)
        if existing_state and (
            existing_state.get("documentHash") == document.hash
            and existing_state.get("extractorVersion") == CODE_GRAPH_EXTRACTOR_VERSION
        ):
            return CodeDocumentIndexResult(
                document_id=document.id,
                path=document.path,
                node_count=0,
                edge_count=0,
                skipped=True,
                reason="hash_match",
            )

        extracted = self._extract_document(document)
        await self._persist_graph(document, extracted)

        logger.info(
            "Indexed code graph for %s: %s nodes, %s edges",
            document.path,
            len(extracted.nodes),
            len(extracted.edges),
        )
        return CodeDocumentIndexResult(
            document_id=document.id,
            path=document.path,
            node_count=len(extracted.nodes),
            edge_count=len(extracted.edges),
        )

    async def list_project_documents(
        self, project_id: str, *, incremental: bool = False
    ) -> list[dict[str, Any]]:
        """Return CODE documents eligible for graph indexing."""
        if incremental:
            return await self.db.query_raw(
                """
                SELECT d.id, d.path
                FROM documents d
                LEFT JOIN code_index_state cis ON cis."documentId" = d.id
                WHERE d."projectId" = $1
                  AND d.kind = 'CODE'
                  AND d."deletedAt" IS NULL
                  AND (
                    COALESCE(d.language, '') IN ('python', 'typescript', 'go')
                    OR COALESCE(d.format, '') IN ('py', 'pyi', 'ts', 'tsx', 'mts', 'cts', 'go')
                  )
                  AND (
                    cis."documentId" IS NULL
                    OR cis."documentHash" <> d.hash
                    OR cis."extractorVersion" <> $2
                  )
                ORDER BY d.path
                """,
                project_id,
                CODE_GRAPH_EXTRACTOR_VERSION,
            )

        return await self.db.query_raw(
            """
            SELECT d.id, d.path
            FROM documents d
            WHERE d."projectId" = $1
              AND d.kind = 'CODE'
              AND d."deletedAt" IS NULL
              AND (
                COALESCE(d.language, '') IN ('python', 'typescript', 'go')
                OR COALESCE(d.format, '') IN ('py', 'pyi', 'ts', 'tsx', 'mts', 'cts', 'go')
              )
            ORDER BY d.path
            """,
            project_id,
        )

    def _extract_document(self, document: Any) -> ExtractedCodeGraph:
        extractor = get_extractor_for_document(document)
        if extractor is None:
            raise ValueError(f"Unsupported code graph document: {document.path}")
        return extractor.extract()

    @staticmethod
    def _is_supported_document(document: Any) -> bool:
        if getattr(document, "kind", None) != "CODE":
            return False
        return infer_document_language(document) is not None

    async def _load_index_state(self, document_id: str) -> dict[str, Any] | None:
        rows = await self.db.query_raw(
            """
            SELECT "documentHash", "extractorVersion"
            FROM code_index_state
            WHERE "documentId" = $1
            """,
            document_id,
        )
        return rows[0] if rows else None

    async def _persist_graph(self, document: Any, extracted: ExtractedCodeGraph) -> None:
        await self.db.execute_raw(
            'DELETE FROM code_nodes WHERE "documentId" = $1',
            document.id,
        )

        symbol_key_to_id: dict[str, str] = {}
        for node in extracted.nodes:
            node_id = uuid.uuid4().hex
            symbol_key_to_id[node.symbol_key] = node_id
            await self.db.execute_raw(
                """
                INSERT INTO code_nodes
                (id, "projectId", "documentId", kind, language, "modulePath", "symbolKey",
                 "qualifiedName", "localName", "startLine", "endLine", signature, docstring, "createdAt")
                VALUES
                ($1, $2, $3, $4::"CodeNodeKind", $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
                """,
                node_id,
                document.projectId,
                document.id,
                node.kind,
                node.language,
                node.module_path,
                node.symbol_key,
                node.qualified_name,
                node.local_name,
                node.start_line,
                node.end_line,
                node.signature,
                node.docstring,
            )

        for edge in extracted.edges:
            from_node_id = symbol_key_to_id.get(edge.from_symbol_key)
            to_node_id = symbol_key_to_id.get(edge.to_symbol_key)
            if from_node_id is None or to_node_id is None:
                continue

            await self.db.execute_raw(
                """
                INSERT INTO code_edges
                (id, "projectId", "fromNodeId", "toNodeId", kind, source, confidence, "createdAt")
                VALUES
                ($1, $2, $3, $4, $5::"CodeEdgeKind", $6::"EdgeSource", $7, NOW())
                """,
                uuid.uuid4().hex,
                document.projectId,
                from_node_id,
                to_node_id,
                edge.kind,
                edge.source,
                edge.confidence,
            )

        await self._persist_reference_hints(
            project_id=document.projectId,
            symbol_key_to_id=symbol_key_to_id,
            reference_hints=extracted.reference_hints,
        )

        await self.db.execute_raw(
            """
            INSERT INTO code_index_state
            ("documentId", "projectId", "documentHash", "extractorVersion", "indexedAt")
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT ("documentId")
            DO UPDATE SET
              "projectId" = EXCLUDED."projectId",
              "documentHash" = EXCLUDED."documentHash",
              "extractorVersion" = EXCLUDED."extractorVersion",
              "indexedAt" = NOW()
            """,
            document.id,
            document.projectId,
            document.hash,
            extracted.extractor_version,
        )

    async def _persist_reference_hints(
        self,
        *,
        project_id: str,
        symbol_key_to_id: dict[str, str],
        reference_hints: list[Any],
    ) -> None:
        inserted_edges: set[tuple[str, str, str]] = set()
        for hint in reference_hints:
            if hint.state != "cross_file_candidate" or not hint.target_qualified_name:
                continue

            from_node_id = symbol_key_to_id.get(hint.from_symbol_key)
            if from_node_id is None:
                continue

            rows = await self.db.query_raw(
                """
                SELECT id, "qualifiedName"
                FROM code_nodes
                WHERE "projectId" = $1
                  AND "qualifiedName" = $2
                ORDER BY "createdAt" DESC
                LIMIT 1
                """,
                project_id,
                hint.target_qualified_name,
            )
            if not rows:
                continue

            target_node_id = rows[0]["id"]
            edge_key = (from_node_id, target_node_id, hint.relationship)
            if edge_key in inserted_edges:
                continue

            await self.db.execute_raw(
                """
                INSERT INTO code_edges
                (id, "projectId", "fromNodeId", "toNodeId", kind, source, confidence, "createdAt")
                VALUES
                ($1, $2, $3, $4, $5::"CodeEdgeKind", $6::"EdgeSource", $7, NOW())
                """,
                uuid.uuid4().hex,
                project_id,
                from_node_id,
                target_node_id,
                hint.relationship,
                "HEURISTIC",
                hint.confidence,
            )
            inserted_edges.add(edge_key)
