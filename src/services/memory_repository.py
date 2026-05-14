"""Repository layer for Memory V2.

Memory V2 is the canonical runtime persistence layer for agent memory. Legacy
AgentMemory compatibility is kept outside this repository for migration maps,
backfill, and hygiene of pre-V2 rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..db import get_db
from ..models.memory_v2 import (
    MemoryCreatePayload,
    MemoryEvidencePayload,
    MemoryMigrationMapPayload,
    MemoryRelationPayload,
    MemoryUpdatePayload,
)


def _enum_to_db(value: Any) -> Any:
    """Convert StrEnum values to Prisma enum strings."""

    if value is None:
        return None
    if hasattr(value, "name"):
        return value.name
    return value


class MemoryRepository:
    """Persistence abstraction for Memory V2 tables."""

    async def create_memory(self, payload: MemoryCreatePayload) -> Any:
        """Create a Memory row."""

        db = await get_db()
        data = {
            "projectId": payload.project_id,
            "teamId": payload.team_id,
            "userId": payload.user_id,
            "agentId": payload.agent_id,
            "type": _enum_to_db(payload.type),
            "scope": _enum_to_db(payload.scope),
            "status": _enum_to_db(payload.status),
            "title": payload.title,
            "content": payload.content,
            "summary": payload.summary,
            "category": payload.category,
            "confidence": payload.confidence,
            "freshnessScore": payload.freshness_score,
            "evidenceScore": payload.evidence_score,
            "validFrom": payload.valid_from,
            "validUntil": payload.valid_until,
            "staleAt": payload.stale_at,
            "source": _enum_to_db(payload.source),
            "sourceSessionId": payload.source_session_id,
            "createdBy": payload.created_by,
            "reviewedBy": payload.reviewed_by,
            "supersedesMemoryId": payload.supersedes_memory_id,
            "canonicalMemoryId": payload.canonical_memory_id,
            "lastAccessedAt": payload.last_accessed_at,
            "archivedAt": payload.archived_at,
        }
        return await db.memory.create(data=data)

    async def update_memory(self, memory_id: str, payload: MemoryUpdatePayload) -> Any:
        """Update a Memory row with a partial payload."""

        db = await get_db()
        raw = payload.model_dump(exclude_unset=True)
        field_map = {
            "status": "status",
            "title": "title",
            "content": "content",
            "summary": "summary",
            "category": "category",
            "confidence": "confidence",
            "freshness_score": "freshnessScore",
            "evidence_score": "evidenceScore",
            "valid_from": "validFrom",
            "valid_until": "validUntil",
            "stale_at": "staleAt",
            "reviewed_by": "reviewedBy",
            "last_accessed_at": "lastAccessedAt",
            "archived_at": "archivedAt",
            "supersedes_memory_id": "supersedesMemoryId",
            "canonical_memory_id": "canonicalMemoryId",
        }

        data: dict[str, Any] = {}
        for key, value in raw.items():
            db_key = field_map[key]
            data[db_key] = _enum_to_db(value)

        return await db.memory.update(where={"id": memory_id}, data=data)

    async def attach_evidence(
        self,
        memory_id: str,
        items: list[MemoryEvidencePayload],
    ) -> list[Any]:
        """Create evidence rows for a memory."""

        if not items:
            return []

        db = await get_db()
        created: list[Any] = []
        for item in items:
            created.append(
                await db.memoryevidence.create(
                    data={
                        "memoryId": memory_id,
                        "evidenceType": _enum_to_db(item.evidence_type),
                        "documentId": item.document_id,
                        "chunkId": item.chunk_id,
                        "externalRef": item.external_ref,
                        "snippet": item.snippet,
                        "lineStart": item.line_start,
                        "lineEnd": item.line_end,
                        "weight": item.weight,
                    }
                )
            )
        return created

    async def create_relations(
        self,
        from_memory_id: str,
        items: list[MemoryRelationPayload],
    ) -> list[Any]:
        """Create typed relations from one memory to others."""

        if not items:
            return []

        db = await get_db()
        created: list[Any] = []
        for item in items:
            created.append(
                await db.memoryrelation.create(
                    data={
                        "fromMemoryId": from_memory_id,
                        "toMemoryId": item.to_memory_id,
                        "relationType": _enum_to_db(item.relation_type),
                    }
                )
            )
        return created

    async def create_migration_map(self, payload: MemoryMigrationMapPayload) -> Any:
        """Persist the legacy-to-v2 migration ID map."""

        db = await get_db()
        return await db.memorymigrationmap.create(
            data={
                "legacyAgentMemoryId": payload.legacy_agent_memory_id,
                "newMemoryId": payload.new_memory_id,
                "checksum": payload.checksum,
            }
        )

    async def get_memory_id_for_legacy_id(self, legacy_agent_memory_id: str) -> str | None:
        """Resolve a V2 memory ID from a legacy AgentMemory ID."""

        db = await get_db()
        row = await db.memorymigrationmap.find_unique(
            where={"legacyAgentMemoryId": legacy_agent_memory_id}
        )
        return row.newMemoryId if row else None

    async def get_memory(self, memory_id: str) -> Any | None:
        """Fetch a Memory V2 row by ID."""

        db = await get_db()
        return await db.memory.find_unique(where={"id": memory_id})

    async def get_memory_with_evidence(self, memory_id: str) -> Any | None:
        """Fetch a Memory V2 row including evidence links."""

        db = await get_db()
        return await db.memory.find_unique(
            where={"id": memory_id},
            include={"evidenceLinks": True},
        )

    async def list_evidence(self, memory_id: str) -> list[Any]:
        """List evidence rows for a memory."""

        db = await get_db()
        return await db.memoryevidence.find_many(where={"memoryId": memory_id})

    async def invalidate_memory(
        self,
        memory_id: str,
        invalidated_at: datetime,
        reviewed_by: str | None = None,
    ) -> Any:
        """Mark a memory invalid without deleting it."""

        return await self.update_memory(
            memory_id,
            MemoryUpdatePayload(
                status="INVALIDATED",
                valid_until=invalidated_at,
                reviewed_by=reviewed_by,
            ),
        )

    async def supersede_memory(
        self,
        old_memory_id: str,
        new_memory_id: str,
        superseded_at: datetime,
    ) -> None:
        """Mark old memory as superseded and link it to the new memory."""

        await self.update_memory(
            old_memory_id,
            MemoryUpdatePayload(
                status="SUPERSEDED",
                valid_until=superseded_at,
            ),
        )
        await self.update_memory(
            new_memory_id,
            MemoryUpdatePayload(
                supersedes_memory_id=old_memory_id,
                canonical_memory_id=new_memory_id,
            ),
        )
        await self.create_relations(
            old_memory_id,
            [MemoryRelationPayload(to_memory_id=new_memory_id, relation_type="SUPERSEDES")],
        )
