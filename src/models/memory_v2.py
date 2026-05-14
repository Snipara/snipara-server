"""Memory V2 payload and repository models.

These models are internal building blocks for the migration from AgentMemory
to the richer Memory/MemoryEvidence/MemoryRelation schema. They are not yet
part of the public MCP request surface.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .enums import (
    AgentMemoryScope,
    AgentMemoryType,
    EvidenceType,
    MemoryRelationType,
    MemorySource,
    MemoryStatus,
)


class MemoryEvidencePayload(BaseModel):
    """Evidence row payload for Memory V2."""

    evidence_type: EvidenceType = Field(..., description="Evidence type")
    document_id: str | None = Field(default=None, description="Optional document ID")
    chunk_id: str | None = Field(default=None, description="Optional chunk ID")
    external_ref: str | None = Field(default=None, description="External ref or path")
    snippet: str | None = Field(default=None, description="Optional supporting excerpt")
    line_start: int | None = Field(default=None, description="Start line")
    line_end: int | None = Field(default=None, description="End line")
    weight: float = Field(default=1.0, ge=0.0, description="Evidence confidence weight")


class MemoryRelationPayload(BaseModel):
    """Relation payload between Memory V2 rows."""

    to_memory_id: str = Field(..., description="Target memory ID")
    relation_type: MemoryRelationType = Field(
        default=MemoryRelationType.RELATED_TO,
        description="Typed relation",
    )


class MemoryCreatePayload(BaseModel):
    """Create payload for the new Memory table."""

    project_id: str | None = Field(default=None, description="Owning project ID")
    team_id: str | None = Field(default=None, description="Owning team ID")
    user_id: str | None = Field(default=None, description="Owning user ID")
    agent_id: str | None = Field(default=None, description="Owning agent ID")

    type: AgentMemoryType = Field(..., description="Memory semantic type")
    scope: AgentMemoryScope = Field(..., description="Memory visibility scope")
    status: MemoryStatus = Field(default=MemoryStatus.ACTIVE, description="Lifecycle status")

    title: str | None = Field(default=None, description="Optional memory title")
    content: str = Field(..., description="Canonical memory content")
    summary: str | None = Field(default=None, description="Optional condensed summary")
    category: str | None = Field(default=None, description="Optional grouping category")

    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Memory confidence")
    freshness_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Freshness score for ranking",
    )
    evidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Evidence quality score for ranking",
    )

    valid_from: datetime | None = Field(default=None, description="Validity start time")
    valid_until: datetime | None = Field(default=None, description="Validity end time")
    stale_at: datetime | None = Field(default=None, description="When memory should become stale")

    source: MemorySource = Field(default=MemorySource.MCP, description="Creation source")
    source_session_id: str | None = Field(default=None, description="Source session ID")
    created_by: str | None = Field(default=None, description="Creator ID or system label")
    reviewed_by: str | None = Field(default=None, description="Reviewer ID")

    supersedes_memory_id: str | None = Field(
        default=None,
        description="Optional direct superseded memory ID",
    )
    canonical_memory_id: str | None = Field(
        default=None,
        description="Optional canonical group root memory ID",
    )

    last_accessed_at: datetime | None = Field(default=None, description="Last access time")
    archived_at: datetime | None = Field(default=None, description="Archive timestamp")


class MemoryUpdatePayload(BaseModel):
    """Partial update payload for Memory V2."""

    status: MemoryStatus | None = Field(default=None, description="Lifecycle status")
    title: str | None = Field(default=None, description="Optional memory title")
    content: str | None = Field(default=None, description="Canonical memory content")
    summary: str | None = Field(default=None, description="Optional condensed summary")
    category: str | None = Field(default=None, description="Optional grouping category")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Confidence")
    freshness_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Freshness score",
    )
    evidence_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Evidence score",
    )
    valid_from: datetime | None = Field(default=None, description="Validity start time")
    valid_until: datetime | None = Field(default=None, description="Validity end time")
    stale_at: datetime | None = Field(default=None, description="Stale timestamp")
    reviewed_by: str | None = Field(default=None, description="Reviewer ID")
    last_accessed_at: datetime | None = Field(default=None, description="Last access time")
    archived_at: datetime | None = Field(default=None, description="Archive time")
    supersedes_memory_id: str | None = Field(
        default=None,
        description="Optional superseded memory ID",
    )
    canonical_memory_id: str | None = Field(
        default=None,
        description="Optional canonical memory ID",
    )


class MemoryMigrationMapPayload(BaseModel):
    """Mapping payload between legacy AgentMemory and Memory V2 IDs."""

    legacy_agent_memory_id: str = Field(..., description="Legacy AgentMemory ID")
    new_memory_id: str = Field(..., description="Memory V2 ID")
    checksum: str | None = Field(default=None, description="Idempotence checksum")
