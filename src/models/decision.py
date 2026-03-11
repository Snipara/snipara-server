# apps/mcp-server/src/models/decision.py
"""Decision log models for structured architectural and technical decisions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DecisionStatus(StrEnum):
    """Status of a decision."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REVERTED = "REVERTED"
    DRAFT = "DRAFT"


class DecisionImpact(StrEnum):
    """Impact level of a decision."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Decision(BaseModel):
    """A structured architectural or technical decision."""

    id: str = Field(..., description="Unique decision ID (e.g., DEC-001)")
    title: str = Field(..., description="Short descriptive title")

    # Ownership
    owner: str = Field(..., description="Who made/owns this decision")
    date: datetime = Field(default_factory=datetime.utcnow)

    # Classification
    scope: str = Field(..., description="Area affected (e.g., search, auth, api)")
    impact: DecisionImpact = Field(default=DecisionImpact.MEDIUM)
    status: DecisionStatus = Field(default=DecisionStatus.ACTIVE)

    # Content
    context: str = Field(..., description="Background and problem statement")
    decision: str = Field(..., description="What was decided")
    rationale: str = Field(..., description="Why this decision was made")
    alternatives: list[str] = Field(
        default_factory=list, description="Alternatives considered"
    )

    # Lifecycle
    revert_plan: str | None = Field(None, description="How to revert if needed")
    supersedes: str | None = Field(None, description="Decision ID this supersedes")
    superseded_by: str | None = Field(
        None, description="Decision ID that supersedes this"
    )

    # Tags for searchability
    tags: list[str] = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "DEC-001",
                "title": "Use RRF for Hybrid Search",
                "owner": "architect",
                "scope": "search",
                "impact": "HIGH",
                "status": "ACTIVE",
                "context": "Need to combine keyword and semantic search results",
                "decision": "Use Reciprocal Rank Fusion (RRF) algorithm",
                "rationale": "RRF is robust to score scale differences between search types",
                "alternatives": ["Weighted average", "Linear combination", "Max score"],
                "revert_plan": "Fall back to weighted average if latency > 100ms",
                "tags": ["search", "algorithm", "performance"],
            }
        }
    }


class DecisionCreateParams(BaseModel):
    """Parameters for creating a new decision."""

    title: str
    owner: str
    scope: str
    impact: DecisionImpact = DecisionImpact.MEDIUM
    context: str
    decision: str
    rationale: str
    alternatives: list[str] = Field(default_factory=list)
    revert_plan: str | None = None
    tags: list[str] = Field(default_factory=list)


class DecisionQueryParams(BaseModel):
    """Parameters for querying decisions."""

    query: str | None = None
    scope: str | None = None
    status: str | None = None
    impact: str | None = None
    owner: str | None = None
    since: datetime | None = None
    tags: list[str] | None = None
    limit: int = 20
    include_superseded: bool = False


class DecisionQueryResult(BaseModel):
    """Result of a decision query."""

    decisions: list[Decision]
    total: int
    has_more: bool
