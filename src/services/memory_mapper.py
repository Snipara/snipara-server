"""Mapping helpers for the Memory V2 migration layer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ..models.enums import AgentMemoryType, EvidenceType, MemorySource, MemoryStatus
from ..models.memory_v2 import MemoryCreatePayload, MemoryEvidencePayload


@dataclass
class MappedLegacyMemory:
    """Structured output for backfilling a legacy AgentMemory row."""

    memory: MemoryCreatePayload
    evidence: list[MemoryEvidencePayload] = field(default_factory=list)
    related_legacy_ids: list[str] = field(default_factory=list)
    checksum: str | None = None


def normalize_memory_source(source: str | None) -> MemorySource:
    """Map loose legacy source strings to MemorySource."""

    if not source:
        return MemorySource.MCP

    normalized = source.strip().upper().replace("-", "_").replace(" ", "_")

    if normalized in MemorySource.__members__:
        return MemorySource[normalized]

    if "SESSION" in normalized:
        return MemorySource.SESSION_CAPTURE
    if "DOC" in normalized:
        return MemorySource.DOC_DERIVED
    if "WEBHOOK" in normalized:
        return MemorySource.WEBHOOK
    if "IMPORT" in normalized:
        return MemorySource.IMPORT
    if "MANUAL" in normalized:
        return MemorySource.MANUAL
    return MemorySource.MCP


def _infer_memory_status(
    memory_type: AgentMemoryType,
    expires_at: datetime | None,
    now: datetime | None = None,
) -> MemoryStatus:
    """Infer initial lifecycle state from legacy memory attributes."""

    if expires_at is None:
        return MemoryStatus.ACTIVE

    reference = now or datetime.now(UTC)
    if expires_at > reference:
        return MemoryStatus.ACTIVE

    if memory_type in {AgentMemoryType.TODO, AgentMemoryType.CONTEXT}:
        return MemoryStatus.STALE
    return MemoryStatus.ACTIVE


def _derive_validity_windows(
    memory_type: AgentMemoryType,
    created_at: datetime,
    expires_at: datetime | None,
) -> tuple[datetime, datetime | None, datetime | None]:
    """Map legacy expiry semantics to Memory V2 validity windows."""

    valid_from = created_at
    valid_until: datetime | None = None
    stale_at: datetime | None = None

    if memory_type in {AgentMemoryType.TODO, AgentMemoryType.CONTEXT}:
        stale_at = expires_at or (created_at + timedelta(days=30))
    else:
        valid_until = expires_at

    return valid_from, valid_until, stale_at


def _evidence_score_from_refs(document_refs: list[str]) -> float:
    """Derive a simple initial evidence score from attached refs."""

    if not document_refs:
        return 0.0
    return min(1.0, 0.35 + (len(document_refs) * 0.15))


def _build_checksum(legacy_memory: Any) -> str:
    """Build a stable checksum for idempotent backfill."""

    digest = hashlib.sha256()
    digest.update(str(getattr(legacy_memory, "id", "")).encode())
    digest.update(str(getattr(legacy_memory, "content", "")).encode())
    digest.update(str(getattr(legacy_memory, "updatedAt", "")).encode())
    return digest.hexdigest()


def map_agent_memory_to_memory_payload(legacy_memory: Any) -> MappedLegacyMemory:
    """Convert a legacy AgentMemory ORM row into Memory V2 payloads."""

    memory_type = AgentMemoryType(getattr(legacy_memory, "type").lower())
    created_at = getattr(legacy_memory, "createdAt")
    expires_at = getattr(legacy_memory, "expiresAt", None)
    document_refs = list(getattr(legacy_memory, "documentRefs", []) or [])
    related_memory_ids = list(getattr(legacy_memory, "relatedMemoryIds", []) or [])

    valid_from, valid_until, stale_at = _derive_validity_windows(
        memory_type=memory_type,
        created_at=created_at,
        expires_at=expires_at,
    )

    memory = MemoryCreatePayload(
        project_id=getattr(legacy_memory, "projectId", None),
        type=memory_type,
        scope=getattr(legacy_memory, "scope").lower(),
        status=_infer_memory_status(memory_type, expires_at),
        content=getattr(legacy_memory, "content"),
        category=getattr(legacy_memory, "category", None),
        confidence=getattr(legacy_memory, "confidence", 1.0),
        freshness_score=1.0,
        evidence_score=_evidence_score_from_refs(document_refs),
        valid_from=valid_from,
        valid_until=valid_until,
        stale_at=stale_at,
        source=normalize_memory_source(getattr(legacy_memory, "source", None)),
        last_accessed_at=getattr(legacy_memory, "lastAccessedAt", None),
    )

    evidence = [
        MemoryEvidencePayload(
            evidence_type=EvidenceType.DOCUMENT,
            external_ref=ref,
            weight=1.0,
        )
        for ref in document_refs
    ]

    return MappedLegacyMemory(
        memory=memory,
        evidence=evidence,
        related_legacy_ids=related_memory_ids,
        checksum=_build_checksum(legacy_memory),
    )

