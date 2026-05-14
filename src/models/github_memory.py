"""GitHub-native memory compiler contracts.

These models define the stable payloads for the GitHub ingestion, memory
candidate, and compiled context contracts before the public MCP/API surface is
added. They intentionally avoid persistence assumptions so the importer MVP can
use the same contract for fixtures, RLM Runtime evaluations, and service tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .enums import AgentMemoryScope, AgentMemoryType
from .memory_v2 import MemoryCreatePayload, MemoryEvidencePayload

SECRET_METADATA_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "client_secret",
    "github_token",
    "password",
    "private_key",
    "secret",
    "token",
}


class GitHubArtifactType(StrEnum):
    """GitHub artifact classes that can become evidence."""

    REPOSITORY = "repository"
    REPOSITORY_RULE = "repository_rule"
    TREE = "tree"
    FILE = "file"
    ISSUE = "issue"
    PULL_REQUEST = "pull_request"
    REVIEW_COMMENT = "review_comment"
    COMMIT = "commit"
    WORKFLOW_RUN = "workflow_run"
    WORKFLOW_JOB = "workflow_job"
    CHECK_RUN = "check_run"
    RELEASE = "release"


class MemoryCandidateRisk(StrEnum):
    """Risk flags that require review before memory persistence."""

    CONTRADICTION = "contradiction"
    EXTERNAL_POLICY = "external_policy"
    LOW_EVIDENCE = "low_evidence"
    PERSONAL_DATA = "personal_data"
    SECRET_LIKE = "secret_like"


class GitHubMemoryReviewAction(StrEnum):
    """Policy action for a GitHub-derived memory candidate."""

    QUEUE = "queue"
    AUTO_APPROVE = "auto_approve"
    REJECT = "reject"


class ContextSourceType(StrEnum):
    """Source classes that the context compiler can pack into a bundle."""

    MEMORY = "memory"
    GITHUB = "github"
    DOCUMENT = "document"
    CODE_GRAPH = "code_graph"
    PROJECT_RULE = "project_rule"
    SHARED_CONTEXT = "shared_context"


class GitHubSourceRef(BaseModel):
    """Stable reference to a GitHub artifact used as evidence."""

    owner: str = Field(..., min_length=1, description="GitHub owner or organization")
    repo: str = Field(..., min_length=1, description="GitHub repository name")
    artifact_type: GitHubArtifactType = Field(..., description="GitHub artifact class")
    external_id: str = Field(
        ...,
        min_length=1,
        description="Stable GitHub identifier, such as issue number, PR number, SHA, or path",
    )
    url: str = Field(..., min_length=1, description="Canonical GitHub URL")
    title: str | None = Field(default=None, description="Optional artifact title")
    branch: str | None = Field(default=None, description="Branch name when relevant")
    sha: str | None = Field(default=None, description="Commit SHA when relevant")
    path: str | None = Field(default=None, description="Repository file path when relevant")
    line_start: int | None = Field(default=None, ge=1, description="Start line")
    line_end: int | None = Field(default=None, ge=1, description="End line")
    state: str | None = Field(default=None, description="GitHub state, e.g. open or merged")
    updated_at: datetime | None = Field(default=None, description="GitHub updated timestamp")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-secret provider metadata needed for idempotent import",
    )

    @field_validator("owner", "repo")
    @classmethod
    def _reject_repo_path_segments(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or "/" in normalized:
            raise ValueError("owner and repo must be separate non-empty path segments")
        return normalized

    @field_validator("url")
    @classmethod
    def _validate_github_url(cls, value: str) -> str:
        normalized = value.strip()
        allowed_prefixes = (
            "https://github.com/",
            "https://api.github.com/",
            "https://raw.githubusercontent.com/",
        )
        if not normalized.startswith(allowed_prefixes):
            raise ValueError(
                "url must point to github.com, api.github.com, or raw.githubusercontent.com"
            )
        return normalized

    @field_validator("metadata")
    @classmethod
    def _reject_secret_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        secret_path = _find_secret_metadata_key(value)
        if secret_path:
            raise ValueError(f"metadata contains secret-like key: {secret_path}")
        return value

    @model_validator(mode="after")
    def _validate_line_range(self) -> GitHubSourceRef:
        if self.line_start is None and self.line_end is not None:
            raise ValueError("line_start is required when line_end is set")
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end must be greater than or equal to line_start")
        return self

    @property
    def repository(self) -> str:
        """Return owner/repo in the GitHub API format."""
        return f"{self.owner}/{self.repo}"

    @property
    def stable_key(self) -> str:
        """Deterministic evidence key for idempotent imports."""
        suffix = f":{self.path}:{self.line_start}-{self.line_end}" if self.path else ""
        return f"github:{self.repository}:{self.artifact_type.value}:{self.external_id}{suffix}"


class GitHubMemoryCandidate(BaseModel):
    """Reviewable memory candidate extracted from GitHub evidence."""

    content: str = Field(..., min_length=1, description="Proposed durable memory text")
    memory_type: AgentMemoryType = Field(..., description="Target memory semantic type")
    scope: AgentMemoryScope = Field(..., description="Target memory visibility scope")
    category: str | None = Field(default=None, description="Suggested memory category")
    evidence: list[GitHubSourceRef] = Field(
        default_factory=list,
        description="GitHub artifacts supporting this candidate",
    )
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Extraction confidence")
    suggested_ttl_days: int | None = Field(default=None, ge=1, description="Suggested TTL")
    risk_flags: list[MemoryCandidateRisk] = Field(
        default_factory=list,
        description="Review risks detected by extraction or policy",
    )
    auto_approve: bool = Field(
        default=False,
        description="Whether this candidate can bypass the review queue",
    )
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Extraction timestamp",
    )

    @model_validator(mode="after")
    def _enforce_review_policy(self) -> GitHubMemoryCandidate:
        if (
            self.risk_flags
            or not self.evidence
            or self.scope
            in {
                AgentMemoryScope.TEAM,
                AgentMemoryScope.USER,
            }
        ):
            self.auto_approve = False
        return self

    @property
    def evidence_keys(self) -> list[str]:
        """Return stable evidence keys for deduplication and traceability."""
        return [source.stable_key for source in self.evidence]


class GitHubMemoryPolicyResult(BaseModel):
    """Review policy outcome for a GitHub-derived memory candidate."""

    action: GitHubMemoryReviewAction = Field(..., description="Policy action")
    reasons: list[str] = Field(default_factory=list, description="Human-readable policy reasons")
    policy_version: str = Field(
        default="github-memory-policy/v1",
        description="Stable policy version for audit trails",
    )


class GitHubMemoryReviewItem(BaseModel):
    """Review-queue item wrapping one GitHub memory candidate."""

    review_id: str = Field(..., min_length=1, description="Deterministic review item ID")
    candidate: GitHubMemoryCandidate = Field(..., description="Candidate under review")
    policy: GitHubMemoryPolicyResult = Field(..., description="Applied review policy")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Queue item creation timestamp",
    )

    @property
    def evidence_keys(self) -> list[str]:
        """Expose source evidence keys without unpacking the candidate."""
        return self.candidate.evidence_keys


class GitHubMemoryPromotionPlan(BaseModel):
    """Memory V2 payloads produced after a GitHub candidate is approved."""

    review_id: str = Field(..., min_length=1, description="Source review item ID")
    memory: MemoryCreatePayload = Field(..., description="Memory V2 create payload")
    evidence: list[MemoryEvidencePayload] = Field(
        default_factory=list,
        description="Evidence rows to attach after memory creation",
    )
    policy: GitHubMemoryPolicyResult = Field(..., description="Policy result used for promotion")


class ContextCompileRequest(BaseModel):
    """Input contract for a future compiled context bundle."""

    task_intent: str = Field(..., min_length=1, description="Task the agent is trying to solve")
    token_budget: int = Field(..., ge=500, le=200000, description="Maximum bundle tokens")
    agent_id: str | None = Field(default=None, description="Optional requesting agent")
    project_id: str | None = Field(default=None, description="Snipara project scope")
    repository: str | None = Field(default=None, description="GitHub owner/repo scope")
    branch: str | None = Field(default=None, description="Branch-aware evidence preference")
    allowed_source_types: list[ContextSourceType] = Field(
        default_factory=lambda: [
            ContextSourceType.PROJECT_RULE,
            ContextSourceType.MEMORY,
            ContextSourceType.GITHUB,
            ContextSourceType.DOCUMENT,
            ContextSourceType.CODE_GRAPH,
        ],
        description="Sources that may be packed into the compiled context bundle",
    )
    freshness_days: int | None = Field(default=None, ge=1, description="Maximum evidence age")
    include_references: bool = Field(
        default=True,
        description="Prefer chunk IDs and source refs alongside content",
    )

    @field_validator("repository")
    @classmethod
    def _validate_repository(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if normalized.count("/") != 1 or not all(normalized.split("/", 1)):
            raise ValueError("repository must use owner/repo format")
        return normalized


class CompiledContextItem(BaseModel):
    """One packed item in a compiled context bundle."""

    source_type: ContextSourceType = Field(..., description="Origin source class")
    content: str | None = Field(default=None, description="Inline context content")
    chunk_id: str | None = Field(default=None, description="Pass-by-reference chunk ID")
    source_ref: str | None = Field(default=None, description="Stable source reference")
    evidence: list[GitHubSourceRef] = Field(default_factory=list, description="Citations")
    priority: int = Field(default=100, ge=0, description="Lower means packed earlier")
    token_count: int = Field(default=0, ge=0, description="Estimated token count")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Evidence confidence")
    stale: bool = Field(default=False, description="Whether this item may be stale")
    omitted_reason: str | None = Field(default=None, description="Why the item was omitted")

    @model_validator(mode="after")
    def _require_payload_or_reference(self) -> CompiledContextItem:
        if not self.content and not self.chunk_id and not self.source_ref:
            raise ValueError("compiled context item needs content, chunk_id, or source_ref")
        return self


class ContextCompileResponse(BaseModel):
    """Output contract for a compiled context bundle."""

    bundle_id: str = Field(..., min_length=1, description="Deterministic bundle identifier")
    request: ContextCompileRequest = Field(..., description="Original compile request")
    items: list[CompiledContextItem] = Field(
        default_factory=list,
        description="Packed context items in consumption order",
    )
    omitted_refs: list[CompiledContextItem] = Field(
        default_factory=list,
        description="Relevant items omitted because of budget or policy",
    )
    total_tokens: int = Field(default=0, ge=0, description="Packed item token count")
    max_tokens: int = Field(..., ge=0, description="Applied token budget")
    confidence_summary: dict[str, float] = Field(
        default_factory=dict,
        description="Aggregate confidence metrics",
    )
    staleness_warnings: list[str] = Field(
        default_factory=list,
        description="Staleness or branch mismatch warnings",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Compile timestamp",
    )

    @model_validator(mode="after")
    def _validate_budget(self) -> ContextCompileResponse:
        computed_tokens = sum(item.token_count for item in self.items)
        if self.total_tokens == 0:
            self.total_tokens = computed_tokens
        if self.total_tokens != computed_tokens:
            raise ValueError("total_tokens must match packed item token_count sum")
        if self.total_tokens > self.max_tokens:
            raise ValueError("compiled context exceeds max_tokens")
        return self


def _find_secret_metadata_key(value: Any, prefix: str = "") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).strip().lower()
            path = f"{prefix}.{key_text}" if prefix else key_text
            if key_text in SECRET_METADATA_KEYS or any(
                token in key_text for token in SECRET_METADATA_KEYS
            ):
                return path
            nested = _find_secret_metadata_key(child, path)
            if nested:
                return nested
    elif isinstance(value, list):
        for index, child in enumerate(value):
            nested = _find_secret_metadata_key(child, f"{prefix}[{index}]")
            if nested:
                return nested
    return None
