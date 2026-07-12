"""Agent Memory Service for Phase 8.2.

Provides semantic memory storage and recall for AI agents.
Memories can have types (FACT, DECISION, LEARNING, etc.), scopes,
and TTL with confidence decay over time.
"""

import asyncio
import json
import logging
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from ..config import settings
from ..db import get_db
from ..models.enums import (
    AgentMemoryScope,
    AgentMemoryType,
    EvidenceType,
    MemoryRelationType,
    MemoryStatus,
)
from ..models.memory_v2 import (
    MemoryCreatePayload,
    MemoryEvidencePayload,
    MemoryMigrationMapPayload,
    MemoryRelationPayload,
    MemoryUpdatePayload,
)
from ..models.responses import normalize_memory_novelty_threshold
from .agent_limits import get_memory_retention_limit
from .cache import get_redis
from .embeddings import EMBEDDING_DIMENSION, get_embeddings_service
from .memory_mapper import map_agent_memory_to_memory_payload, normalize_memory_source
from .memory_repository import MemoryRepository

logger = logging.getLogger(__name__)

# Cache key prefixes
MEMORY_EMBEDDING_PREFIX = "rlm:mem_emb:"  # Memory embedding storage
MEMORY_EMBEDDING_TTL = 60 * 60 * 24 * 7  # 7 days default

# Confidence decay settings
CONFIDENCE_DECAY_RATE = 0.01  # 1% decay per day
MIN_CONFIDENCE = 0.1  # Minimum confidence after decay

# Auto-compaction settings
AUTO_COMPACT_THRESHOLD = 250  # Trigger compaction before noisy projects reach recall scale
AUTO_COMPACT_COOLDOWN = 60 * 60 * 24  # Minimum seconds between auto-compactions (24 hours)
AUTO_COMPACT_CACHE_KEY_PREFIX = "rlm:auto_compact_last:"

# Conflict resolution strategies
CONFLICT_STRATEGY_NEWER = "newer"  # Keep most recent, archive older
CONFLICT_STRATEGY_HIGHER_CONFIDENCE = "higher_confidence"  # Keep highest confidence
CONFLICT_STRATEGY_MERGE = "merge"  # Combine into one
CONFLICT_STRATEGY_FLAG = "flag"  # Mark for manual review

# Date normalization patterns (regex pattern, replacement function)
# Note: replacement functions take (reference_time, *groups) as arguments
DATE_PATTERNS: list[tuple[str, Any]] = [
    # "yesterday" -> absolute date based on memory creation time
    (r"\byesterday\b", lambda ref: ref - timedelta(days=1)),
    # "today" -> absolute date
    (r"\btoday\b", lambda ref: ref),
    # "N days ago" -> absolute date
    (r"\b(\d+)\s+days?\s+ago\b", lambda ref, d: ref - timedelta(days=int(d))),
    # "last week" -> week of date
    (r"\blast\s+week\b", lambda ref: ref - timedelta(weeks=1)),
    # "last month" -> month
    (r"\blast\s+month\b", lambda ref: ref - timedelta(days=30)),
    # "this morning" -> date with morning
    (r"\bthis\s+morning\b", lambda ref: ref),
    # "recently" -> around date
    (r"\brecently\b", lambda ref: ref),
]

_memory_repository = MemoryRepository()

# Dual-write resolution settings
DUAL_WRITE_RESOLUTION_ATTEMPTS = 5
DUAL_WRITE_RESOLUTION_DELAY_SECONDS = 0.2
VALID_AGENT_MEMORY_TYPES = tuple(memory_type.value for memory_type in AgentMemoryType)
VALID_AGENT_MEMORY_SCOPES = tuple(scope.value for scope in AgentMemoryScope)
MEMORY_REVIEW_PENDING = "PENDING"
MEMORY_REVIEW_APPROVED = "APPROVED"
MEMORY_REVIEW_REJECTED = "REJECTED"
MEMORY_STATUS_ACTIVE = "ACTIVE"
MEMORY_STATUS_INVALIDATED = "INVALIDATED"
MEMORY_STATUS_SUPERSEDED = "SUPERSEDED"
VALID_MEMORY_REVIEW_STATUSES = (
    MEMORY_REVIEW_PENDING.lower(),
    MEMORY_REVIEW_APPROVED.lower(),
    MEMORY_REVIEW_REJECTED.lower(),
)
DEFAULT_TTL_BY_TYPE_DAYS = {
    "LEARNING": 30,
    "PREFERENCE": 90,
    "TODO": 7,
    "CONTEXT": 7,
}
RECALL_ACTIVE_TAKE = 350
RECALL_ARCHIVE_FALLBACK_TAKE = 150
RECALL_ON_THE_FLY_EMBEDDING_LIMIT = 10
RECALL_QUERY_EMBEDDING_TIMEOUT_SECONDS = 8.0
RECALL_MEMORY_EMBEDDING_TIMEOUT_SECONDS = 3.0
RECALL_ON_THE_FLY_EMBEDDING_BUDGET_SECONDS = 12.0
SUPERSEDE_RELEVANCE_THRESHOLD = 0.72
TRANSIENT_MEMORY_PREFIXES = (
    ("session", "session ended at "),
    ("file-access", "files accessed:"),
)
DELETED_MEMORY_TOMBSTONE_RE = re.compile(r"^\[DELETED memory [^\]]+\]$")

LOW_SIGNAL_REASON_SUPERSEDED_WORKSPACE_LEARNING = "superseded_workspace_learning"
LOW_SIGNAL_REASON_DELETED_TOMBSTONE = "deleted_tombstone"
LOW_SIGNAL_REASON_SYNC_TEST = "sync_test"
LOW_SIGNAL_REASON_TASK_JOURNAL = "task_journal"
LOW_SIGNAL_REASON_AUTO_DOCUMENT_UPLOAD = "auto_document_upload"
LOW_SIGNAL_REASON_TRIVIAL_DECOMPOSITION = "trivial_decomposition"
LOW_SIGNAL_REASON_EXECUTION_PLAN_RECEIPT = "execution_plan_receipt"
LOW_SIGNAL_REASON_SENSITIVE_MATERIAL = "sensitive_material"
MEMORY_DURABILITY_DURABLE = "durable"
MEMORY_DURABILITY_TRANSIENT = "transient"
MEMORY_DURABILITY_AMBIGUOUS = "ambiguous"
MEMORY_WRITE_RISK_LOW = "low"
MEMORY_WRITE_RISK_MEDIUM = "medium"
MEMORY_WRITE_RISK_HIGH = "high"
MEMORY_RANKING_MAX_BOOST = 0.18
SENSITIVE_MEMORY_REDACTION = "[REDACTED_SECRET]"

SENSITIVE_MEMORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "credential_assignment",
        re.compile(
            r"\b(?:password|passwd|pwd|api[_-]?key|secret|client[_-]?secret|"
            r"access[_-]?token|refresh[_-]?token|private[_-]?key|bearer[_-]?token)\b"
            r"\s*[:=]\s*[\"']?[^\s\"',;]{8,}",
            re.I,
        ),
    ),
    (
        "authorization_header",
        re.compile(
            r"\b(?:authorization|x-api-key)\s*:\s*(?:bearer\s+)?[A-Za-z0-9._~+/=-]{12,}",
            re.I,
        ),
    ),
    (
        "known_token_prefix",
        re.compile(
            r"\b(?:npm_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
            r"github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|"
            r"snipara_[A-Za-z0-9_]{12,}|AKIA[0-9A-Z]{16})\b"
        ),
    ),
    (
        "private_key_block",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.I),
    ),
    (
        "credentialed_connection_string",
        re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^:\s/@]+:[^@\s]+@"),
    ),
)

MEMORY_DURABLE_SIGNAL_RE = re.compile(
    r"\b("
    r"decided|decision|chose|adopted|prefer|preference|always|never|must|"
    r"learned|root cause|fixed by|resolved by|workaround|validated|"
    r"architecture|rationale|runbook|workflow"
    r")\b",
    re.I,
)
MEMORY_OPERATIONAL_RECEIPT_RE = re.compile(
    r"\b("
    r"files? (modified|touched|changed)|tests? (run|passed|failed)|"
    r"committed|pushed|deployed|opened pr|created branch|staged changes|"
    r"summary:|verification:|result:"
    r")\b",
    re.I,
)

LOW_SIGNAL_RESULT_KEYS = {
    LOW_SIGNAL_REASON_SUPERSEDED_WORKSPACE_LEARNING: "superseded_workspace_learning_removed",
    LOW_SIGNAL_REASON_DELETED_TOMBSTONE: "deleted_tombstones_removed",
    LOW_SIGNAL_REASON_SYNC_TEST: "sync_test_noise_removed",
    LOW_SIGNAL_REASON_TASK_JOURNAL: "task_journals_removed",
    LOW_SIGNAL_REASON_AUTO_DOCUMENT_UPLOAD: "auto_document_uploads_removed",
    LOW_SIGNAL_REASON_TRIVIAL_DECOMPOSITION: "trivial_decompositions_removed",
    LOW_SIGNAL_REASON_EXECUTION_PLAN_RECEIPT: "execution_plan_receipts_removed",
    LOW_SIGNAL_REASON_SENSITIVE_MATERIAL: "sensitive_memories_removed",
}


async def _embed_text_with_timeout(
    embeddings_service: Any,
    text: str,
    timeout_seconds: float,
    *,
    label: str,
) -> list[float]:
    """Bound recall embedding calls so memory retrieval degrades instead of hanging."""
    try:
        return await asyncio.wait_for(
            embeddings_service.embed_text_async(text),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        logger.warning("Timed out embedding %s after %.1fs", label, timeout_seconds)
        raise


def _normalize_memory_type(
    memory_type: str | AgentMemoryType | None,
    *,
    param_name: str = "type",
) -> AgentMemoryType | None:
    """Normalize and validate public memory type parameters."""
    if memory_type is None:
        return None

    raw_value = (
        memory_type.value if isinstance(memory_type, AgentMemoryType) else str(memory_type).strip()
    )
    if not raw_value:
        raise ValueError(f"Invalid parameter '{param_name}': value cannot be empty")

    try:
        return AgentMemoryType(raw_value.lower())
    except ValueError as exc:
        allowed = ", ".join(VALID_AGENT_MEMORY_TYPES)
        raise ValueError(
            f"Invalid parameter '{param_name}': unsupported memory type '{raw_value}'. "
            f"Expected one of: {allowed}"
        ) from exc


def _normalize_memory_scope(
    scope: str | AgentMemoryScope | None,
    *,
    param_name: str = "scope",
) -> AgentMemoryScope | None:
    """Normalize and validate public memory scope parameters."""
    if scope is None:
        return None

    raw_value = scope.value if isinstance(scope, AgentMemoryScope) else str(scope).strip()
    if not raw_value:
        raise ValueError(f"Invalid parameter '{param_name}': value cannot be empty")

    try:
        return AgentMemoryScope(raw_value.lower())
    except ValueError as exc:
        allowed = ", ".join(VALID_AGENT_MEMORY_SCOPES)
        raise ValueError(
            f"Invalid parameter '{param_name}': unsupported scope '{raw_value}'. "
            f"Expected one of: {allowed}"
        ) from exc


def _normalize_review_status(
    review_status: str | None,
    *,
    param_name: str = "review_status",
) -> str:
    """Normalize review queue status values for memory rows."""
    if review_status is None:
        return MEMORY_REVIEW_APPROVED

    raw_value = str(review_status).strip()
    if not raw_value:
        raise ValueError(f"Invalid parameter '{param_name}': value cannot be empty")

    normalized = raw_value.upper()
    if normalized not in {
        MEMORY_REVIEW_PENDING,
        MEMORY_REVIEW_APPROVED,
        MEMORY_REVIEW_REJECTED,
    }:
        allowed = ", ".join(VALID_MEMORY_REVIEW_STATUSES)
        raise ValueError(
            f"Invalid parameter '{param_name}': unsupported review status '{raw_value}'. "
            f"Expected one of: {allowed}"
        )

    return normalized


def _apply_review_status_filter(
    where: dict[str, Any],
    *,
    include_pending: bool = False,
    include_rejected: bool = False,
) -> dict[str, Any]:
    """Restrict queries to visible review states unless explicitly widened."""
    allowed_statuses = [MEMORY_REVIEW_APPROVED]
    if include_pending:
        allowed_statuses.append(MEMORY_REVIEW_PENDING)
    if include_rejected:
        allowed_statuses.append(MEMORY_REVIEW_REJECTED)

    where["reviewStatus"] = (
        allowed_statuses[0] if len(allowed_statuses) == 1 else {"in": allowed_statuses}
    )
    return where


def _memory_v2_status_for_review(review_status: str) -> MemoryStatus:
    """Map legacy review state onto Memory V2 lifecycle status."""
    if review_status == MEMORY_REVIEW_PENDING:
        return MemoryStatus.CANDIDATE
    if review_status == MEMORY_REVIEW_REJECTED:
        return MemoryStatus.INVALIDATED
    return MemoryStatus.ACTIVE


def _review_status_for_memory_v2_status(status: str) -> str:
    """Map Memory V2 lifecycle status back to the legacy review-state vocabulary."""
    normalized = str(status).upper()
    if normalized == MemoryStatus.CANDIDATE.value:
        return MEMORY_REVIEW_PENDING
    if normalized == MemoryStatus.ACTIVE.value:
        return MEMORY_REVIEW_APPROVED
    return MEMORY_REVIEW_REJECTED


def _normalize_review_queue_status(status: str | None) -> str:
    """Normalize public queue status aliases."""
    normalized = str(status or "candidate").strip().lower()
    if not normalized:
        normalized = "candidate"

    aliases = {
        "pending": "candidate",
        "approved": "active",
        "rejected": "invalidated",
    }
    normalized = aliases.get(normalized, normalized)
    allowed = {
        "candidate",
        "stale",
        "invalidated",
        "superseded",
        "archived",
        "active",
        "all",
    }
    if normalized not in allowed:
        allowed_text = ", ".join(sorted(allowed | set(aliases)))
        raise ValueError(
            f"Invalid parameter 'status': unsupported review queue status '{status}'. "
            f"Expected one of: {allowed_text}"
        )
    return normalized


def _queue_status_to_memory_v2_statuses(status: str) -> list[str] | None:
    """Return Memory V2 statuses for a normalized queue status."""
    if status == "all":
        return None
    return {
        "candidate": [MemoryStatus.CANDIDATE.value],
        "stale": [MemoryStatus.STALE.value],
        "invalidated": [MemoryStatus.INVALIDATED.value],
        "superseded": [MemoryStatus.SUPERSEDED.value],
        "archived": [MemoryStatus.ARCHIVED.value],
        "active": [MemoryStatus.ACTIVE.value],
    }[status]


def _queue_status_to_legacy_filter(status: str) -> dict[str, Any]:
    """Return AgentMemory filters for a normalized queue status."""
    if status == "all":
        return {}
    if status == "candidate":
        return {"reviewStatus": MEMORY_REVIEW_PENDING}
    if status == "active":
        return {"reviewStatus": MEMORY_REVIEW_APPROVED}
    if status == "invalidated":
        return {"reviewStatus": MEMORY_REVIEW_REJECTED}
    return {"status": status.upper()}


def _memory_queue_reason(status: str, review_status: str | None = None) -> str:
    """Classify why a row appears in the review queue."""
    normalized_status = str(status or "").lower()
    normalized_review = str(review_status or "").lower()
    if normalized_review == MEMORY_REVIEW_PENDING.lower() or normalized_status == "candidate":
        return "candidate_memory"
    if normalized_status == "stale":
        return "stale_memory"
    if normalized_status == "superseded":
        return "superseded_memory"
    if normalized_status == "archived":
        return "archived_memory"
    if normalized_review == MEMORY_REVIEW_REJECTED.lower() or normalized_status == "invalidated":
        return "rejected_memory"
    return "reviewed_memory"


def _enum_lower(value: Any) -> str:
    """Return a stable lowercase representation for Prisma enum/string values."""
    raw = getattr(value, "value", value)
    return str(raw).lower()


def _enum_upper(value: Any) -> str:
    """Return a stable uppercase representation for Prisma enum/string values."""
    raw = getattr(value, "value", value)
    return str(raw).upper()


def get_memory_scope_owner_error(
    scope: str | AgentMemoryScope | None,
    *,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> str | None:
    """Return a client-safe ownership error for scoped Memory V2 operations."""
    normalized_scope = _normalize_memory_scope(scope) or AgentMemoryScope.PROJECT
    if normalized_scope == AgentMemoryScope.USER and not user_id:
        return "scope=user requires an authenticated user_id"
    if normalized_scope == AgentMemoryScope.TEAM and not team_id:
        return "scope=team requires a team_id"
    if normalized_scope == AgentMemoryScope.AGENT and not agent_id:
        return "scope=agent requires an agent_id"
    return None


async def _resolve_project_team_id(
    project_id: str,
    team_id: str | None,
    db: Any | None = None,
) -> str | None:
    """Resolve a project's owning team id when the caller did not provide it."""
    if team_id:
        return team_id

    db = db or await get_db()
    project_repo = getattr(db, "project", None)
    if project_repo is None:
        return None

    project = await project_repo.find_unique(where={"id": project_id})
    return getattr(project, "teamId", None) if project else None


def _build_memory_v2_owner_conditions(
    *,
    project_id: str,
    scope: AgentMemoryScope | None,
    user_id: str | None,
    team_id: str | None,
    agent_id: str | None,
) -> list[dict[str, Any]]:
    """Build owner predicates for Memory V2 reads."""
    if scope == AgentMemoryScope.PROJECT:
        return [{"projectId": project_id, "scope": "PROJECT"}]
    if scope == AgentMemoryScope.USER:
        if not user_id:
            return []
        return [{"userId": user_id, "scope": "USER"}]
    if scope == AgentMemoryScope.TEAM:
        if not team_id:
            return []
        return [{"teamId": team_id, "scope": "TEAM"}]
    if scope == AgentMemoryScope.AGENT:
        if not agent_id:
            return []
        return [{"projectId": project_id, "agentId": agent_id, "scope": "AGENT"}]

    conditions = [{"projectId": project_id, "scope": "PROJECT"}]
    if user_id:
        conditions.append({"userId": user_id, "scope": "USER"})
    if team_id:
        conditions.append({"teamId": team_id, "scope": "TEAM"})
    if agent_id:
        conditions.append({"projectId": project_id, "agentId": agent_id, "scope": "AGENT"})
    return conditions


def _build_memory_v2_where(
    *,
    project_id: str,
    scope: AgentMemoryScope | None,
    user_id: str | None,
    team_id: str | None,
    agent_id: str | None,
    memory_type: AgentMemoryType | None = None,
    category: str | None = None,
    include_expired: bool = False,
    include_inactive: bool = False,
) -> dict[str, Any] | None:
    """Build a Memory V2 query with explicit owner boundaries."""
    owner_conditions = _build_memory_v2_owner_conditions(
        project_id=project_id,
        scope=scope,
        user_id=user_id,
        team_id=team_id,
        agent_id=agent_id,
    )
    if not owner_conditions:
        return None

    clauses: list[dict[str, Any]] = [{"OR": owner_conditions}]
    if memory_type:
        clauses.append({"type": memory_type.value.upper()})
    if category:
        clauses.append({"category": category})
    if not include_expired:
        clauses.append({"OR": [{"validUntil": None}, {"validUntil": {"gt": datetime.now(UTC)}}]})
    if not include_inactive:
        clauses.append({"status": "ACTIVE"})

    return {"AND": clauses} if len(clauses) > 1 else clauses[0]


def _memory_v2_owner_payload(
    *,
    project_id: str,
    scope: AgentMemoryScope,
    user_id: str | None,
    team_id: str | None,
    agent_id: str | None,
) -> dict[str, str | None]:
    """Return owner columns for a Memory V2 row."""
    return {
        "project_id": project_id,
        "team_id": team_id if scope == AgentMemoryScope.TEAM else None,
        "user_id": user_id if scope == AgentMemoryScope.USER else None,
        "agent_id": agent_id if scope == AgentMemoryScope.AGENT else None,
    }


def _normalize_ttl_days(ttl_days: int | None) -> int | None:
    """Validate ttl_days and normalize falsy values to None."""
    if ttl_days is None:
        return None

    normalized = int(ttl_days)
    if normalized <= 0:
        raise ValueError("Invalid parameter 'ttl_days': value must be greater than 0")

    return normalized


async def _resolve_effective_ttl_days(
    project_id: str,
    memory_type: AgentMemoryType,
    ttl_days: int | None,
) -> int | None:
    """Clamp explicit TTLs and apply conservative defaults for volatile memory types."""
    normalized_ttl = _normalize_ttl_days(ttl_days)
    retention_limit = await get_memory_retention_limit(project_id)
    default_ttl = DEFAULT_TTL_BY_TYPE_DAYS.get(memory_type.value.upper())
    effective_ttl = normalized_ttl if normalized_ttl is not None else default_ttl

    if retention_limit == -1 or effective_ttl is None:
        return effective_ttl

    return min(effective_ttl, retention_limit)


async def _fetch_recall_candidates(db: Any, where: dict[str, Any]) -> list[Any]:
    """Prioritize active/non-archived memories before falling back to archived ones."""
    primary_where = dict(where)
    primary_where["tier"] = {"not": "ARCHIVE"}
    primary_memories = await db.agentmemory.find_many(
        where=primary_where,
        order={"createdAt": "desc"},
        take=RECALL_ACTIVE_TAKE,
    )

    if len(primary_memories) >= RECALL_ACTIVE_TAKE:
        return primary_memories

    archive_where = dict(where)
    archive_where["tier"] = "ARCHIVE"
    archive_memories = await db.agentmemory.find_many(
        where=archive_where,
        order={"createdAt": "desc"},
        take=RECALL_ARCHIVE_FALLBACK_TAKE,
    )
    return primary_memories + archive_memories


def _is_automated_memory_source(source: str | None) -> bool:
    """Heuristic to distinguish automated captures from explicit user memory writes."""
    if not source:
        return False

    normalized = str(source).strip().lower()
    return normalized.startswith(("auto", "hook", "task_commit", "import"))


def detect_sensitive_memory_reasons(content: str | None) -> list[str]:
    """Return secret-pattern matches for memory content without exposing the secret value."""
    text = str(content or "")
    reasons: list[str] = []
    for reason, pattern in SENSITIVE_MEMORY_PATTERNS:
        if pattern.search(text):
            reasons.append(reason)
    return reasons


def memory_content_has_sensitive_material(content: str | None) -> bool:
    """Return True when content looks unsafe to persist or inject as durable memory."""
    return bool(detect_sensitive_memory_reasons(content))


def _assert_memory_content_is_safe(content: str | None) -> None:
    """Reject memory writes that appear to contain credentials or secret-bearing strings."""
    if memory_content_has_sensitive_material(content):
        raise ValueError(
            "Memory content appears to contain sensitive material and was not stored. "
            "Store operational access details in a secret manager instead."
        )


def _redact_sensitive_memory_content(content: str | None) -> str:
    """Redact recognizable secrets before including memory text in diagnostics."""
    redacted = str(content or "")
    for _, pattern in SENSITIVE_MEMORY_PATTERNS:
        redacted = pattern.sub(SENSITIVE_MEMORY_REDACTION, redacted)
    return redacted


def _memory_contains_sensitive_material(memory: Any) -> bool:
    """Return True when a memory row contains sensitive material."""
    return memory_content_has_sensitive_material(getattr(memory, "content", None))


def _filter_sensitive_memories(memories: list[Any]) -> tuple[list[Any], int]:
    """Drop sensitive memory rows before recall/session bootstrap injection."""
    safe_memories = [
        memory for memory in memories if not _memory_contains_sensitive_material(memory)
    ]
    return safe_memories, len(memories) - len(safe_memories)


def _is_transient_operational_memory(memory: Any) -> bool:
    """Filter low-signal operational markers from default semantic recall."""
    category = str(getattr(memory, "category", "") or "").strip().lower()
    content = str(getattr(memory, "content", "") or "").strip().lower()

    return any(
        category == expected_category and content.startswith(prefix)
        for expected_category, prefix in TRANSIENT_MEMORY_PREFIXES
    )


def _is_superseded_workspace_learning(memory: Any) -> bool:
    """Detect project-level workspace learning rows that were repeatedly superseded."""
    category = str(getattr(memory, "category", "") or "").strip().lower()
    memory_type = str(getattr(memory, "type", "") or "").strip().upper()
    return (
        memory_type == "LEARNING"
        and category.startswith("workspace-learning-")
        and ":superseded" in category
    )


def _is_deleted_memory_tombstone(memory: Any) -> bool:
    """Detect placeholder rows that only point at an already-deleted memory."""
    content = str(getattr(memory, "content", "") or "").strip()
    return bool(DELETED_MEMORY_TOMBSTONE_RE.fullmatch(content))


def _is_backend_sync_test_memory(memory: Any) -> bool:
    """Detect backend-only sync test artifacts that should not survive compaction."""
    content = str(getattr(memory, "content", "") or "")
    normalized = content.lower()
    if "SYNCTEST-" not in content.upper():
        return False

    return any(
        marker in normalized
        for marker in (
            "backend-only sync test",
            "simple task",
            "feature root",
            "acknowledged",
        )
    )


def _is_task_completion_journal(memory: Any) -> bool:
    """Detect operational task completion logs stored as learning memories."""
    category = str(getattr(memory, "category", "") or "").strip().lower()
    content = str(getattr(memory, "content", "") or "").strip().lower()
    return (
        category == "task-learning" and content.startswith('task "') and " completed by " in content
    )


def _is_auto_document_upload_marker(memory: Any) -> bool:
    """Detect upload receipts that document indexing already represents better."""
    category = str(getattr(memory, "category", "") or "").strip().lower()
    source = str(getattr(memory, "source", "") or "").strip().lower()
    content = str(getattr(memory, "content", "") or "").strip().lower()
    return (
        category == "auto-remember"
        and source in {"auto", ""}
        and content.startswith("uploaded document:")
    )


def _is_trivial_decomposition_marker(memory: Any) -> bool:
    """Detect one-way decomposition receipts that add no durable knowledge."""
    category = str(getattr(memory, "category", "") or "").strip().lower()
    content = str(getattr(memory, "content", "") or "").strip().lower()
    return (
        category == "auto-remember"
        and content.startswith("decomposed ")
        and content.endswith(" into 1 sub-queries")
    )


def _is_execution_plan_receipt(memory: Any) -> bool:
    """Detect generic plan receipts that describe tool usage, not durable decisions."""
    category = str(getattr(memory, "category", "") or "").strip().lower()
    source = str(getattr(memory, "source", "") or "").strip().lower()
    content = str(getattr(memory, "content", "") or "").strip().lower()
    return (
        category == "auto-remember"
        and source in {"auto", ""}
        and content.startswith("created execution plan for ")
        and " with " in content
        and content.endswith(" steps")
    )


def _classify_low_signal_memory(memory: Any) -> str | None:
    """Return the hygiene bucket for memories that are safe to prune."""
    if _memory_contains_sensitive_material(memory):
        return LOW_SIGNAL_REASON_SENSITIVE_MATERIAL
    if _is_superseded_workspace_learning(memory):
        return LOW_SIGNAL_REASON_SUPERSEDED_WORKSPACE_LEARNING
    if _is_deleted_memory_tombstone(memory):
        return LOW_SIGNAL_REASON_DELETED_TOMBSTONE
    if _is_backend_sync_test_memory(memory):
        return LOW_SIGNAL_REASON_SYNC_TEST
    if _is_task_completion_journal(memory):
        return LOW_SIGNAL_REASON_TASK_JOURNAL
    if _is_auto_document_upload_marker(memory):
        return LOW_SIGNAL_REASON_AUTO_DOCUMENT_UPLOAD
    if _is_trivial_decomposition_marker(memory):
        return LOW_SIGNAL_REASON_TRIVIAL_DECOMPOSITION
    if _is_execution_plan_receipt(memory):
        return LOW_SIGNAL_REASON_EXECUTION_PLAN_RECEIPT
    return None


def classify_memory_durability(
    content: str,
    memory_type: str | AgentMemoryType | None = None,
    *,
    category: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Classify whether a proposed memory is durable knowledge or operational noise."""
    normalized_type = _normalize_memory_type(memory_type) or AgentMemoryType.FACT
    normalized_content = " ".join(str(content or "").split())
    sensitive_reasons = detect_sensitive_memory_reasons(normalized_content)
    probe = type(
        "MemoryDurabilityProbe",
        (),
        {
            "content": normalized_content,
            "type": normalized_type.value.upper(),
            "category": category,
            "source": source,
            "status": MEMORY_STATUS_ACTIVE,
        },
    )()

    reasons: list[str] = []
    if sensitive_reasons:
        reasons.extend(f"sensitive:{reason}" for reason in sensitive_reasons)
    low_signal_reason = _classify_low_signal_memory(probe)
    if low_signal_reason:
        reasons.append(low_signal_reason)
    if len(normalized_content) < 24:
        reasons.append("too_short")
    if MEMORY_OPERATIONAL_RECEIPT_RE.search(normalized_content):
        reasons.append("operational_receipt")

    has_durable_signal = bool(MEMORY_DURABLE_SIGNAL_RE.search(normalized_content))
    if has_durable_signal:
        reasons.append("durable_signal")

    automated = _is_automated_memory_source(source)
    strong_type = normalized_type in {
        AgentMemoryType.DECISION,
        AgentMemoryType.PREFERENCE,
    }

    if sensitive_reasons:
        durability = MEMORY_DURABILITY_TRANSIENT
        risk = MEMORY_WRITE_RISK_HIGH
    elif low_signal_reason:
        durability = MEMORY_DURABILITY_TRANSIENT
        risk = MEMORY_WRITE_RISK_HIGH
    elif strong_type or has_durable_signal:
        durability = MEMORY_DURABILITY_DURABLE
        risk = MEMORY_WRITE_RISK_LOW
    elif automated:
        durability = MEMORY_DURABILITY_AMBIGUOUS
        risk = MEMORY_WRITE_RISK_MEDIUM
    else:
        durability = MEMORY_DURABILITY_DURABLE
        risk = MEMORY_WRITE_RISK_LOW

    should_review = automated and risk in {MEMORY_WRITE_RISK_MEDIUM, MEMORY_WRITE_RISK_HIGH}
    return {
        "durability": durability,
        "risk": risk,
        "reasons": reasons,
        "automated_source": automated,
        "durable_signal": has_durable_signal,
        "recommended_review_status": MEMORY_REVIEW_PENDING
        if should_review
        else MEMORY_REVIEW_APPROVED,
    }


def _memory_health_sample(memory: Any, reason: str) -> dict[str, Any]:
    """Return a compact, JSON-safe anomaly sample for memory health output."""
    created_at = getattr(memory, "createdAt", None)
    return {
        "memory_id": getattr(memory, "id", None),
        "reason": reason,
        "type": _enum_lower(getattr(memory, "type", "")),
        "scope": _enum_lower(getattr(memory, "scope", "")),
        "category": getattr(memory, "category", None),
        "status": _enum_lower(getattr(memory, "status", "")),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else None,
        "preview": _redact_sensitive_memory_content(getattr(memory, "content", ""))[:180],
    }


async def _delete_memories_with_embeddings(
    db: Any,
    memory_ids: list[str],
    *,
    dry_run: bool = False,
) -> int:
    """Delete memory rows and their cached embeddings together."""
    if not memory_ids:
        return 0

    if dry_run:
        return len(memory_ids)

    deleted_count = await db.agentmemory.delete_many(where={"id": {"in": memory_ids}})
    for memory_id in memory_ids:
        await _delete_memory_embedding(memory_id)
    return deleted_count


def resolve_review_status_for_source(
    settings_obj: Any | None,
    *,
    source: str | None = None,
    requested_review_status: str | None = None,
    content: str | None = None,
    memory_type: str | AgentMemoryType | None = None,
    category: str | None = None,
) -> str:
    """Resolve the effective review status for a memory write."""
    if requested_review_status is not None:
        return _normalize_review_status(requested_review_status)

    if content is not None:
        classification = classify_memory_durability(
            content,
            memory_type,
            category=category,
            source=source,
        )
        if classification["recommended_review_status"] == MEMORY_REVIEW_PENDING:
            return MEMORY_REVIEW_PENDING

    review_mode = str(getattr(settings_obj, "memory_review_mode", "AUTO") or "AUTO").upper()
    if review_mode == "INBOX" and _is_automated_memory_source(source):
        return MEMORY_REVIEW_PENDING

    return MEMORY_REVIEW_APPROVED


def calculate_confidence_decay(
    initial_confidence: float,
    created_at: datetime,
    last_accessed_at: datetime | None = None,
) -> float:
    """Calculate decayed confidence based on age and access patterns.

    Args:
        initial_confidence: Original confidence (0-1)
        created_at: When memory was created
        last_accessed_at: Last time memory was accessed (boosts confidence)

    Returns:
        Decayed confidence value (0-1)
    """
    now = datetime.now(UTC)

    # Use last access time if available, otherwise creation time
    reference_time = last_accessed_at or created_at

    # Ensure reference_time is timezone-aware (database may return naive datetimes)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)

    days_since_reference = (now - reference_time).days

    # Apply exponential decay
    decay_factor = (1 - CONFIDENCE_DECAY_RATE) ** days_since_reference
    decayed = initial_confidence * decay_factor

    return max(decayed, MIN_CONFIDENCE)


def _is_valid_embedding(embedding: Any) -> bool:
    """Validate that an embedding has the correct structure and dimensions.

    Args:
        embedding: The embedding to validate

    Returns:
        True if embedding is valid (list of EMBEDDING_DIMENSION floats)
    """
    if not isinstance(embedding, list):
        return False
    if len(embedding) != EMBEDDING_DIMENSION:
        return False
    # Check that all elements are numbers (int or float)
    return all(isinstance(x, (int, float)) for x in embedding)


async def _get_memory_embedding(memory_id: str) -> list[float] | None:
    """Get cached embedding for a memory from Redis.

    Args:
        memory_id: The memory ID

    Returns:
        Embedding vector or None if not cached
    """
    redis = await get_redis()
    if redis is None:
        return None

    try:
        key = f"{MEMORY_EMBEDDING_PREFIX}{memory_id}"
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)
        return None
    except Exception as e:
        logger.warning(f"Error getting memory embedding: {e}")
        return None


async def _get_memory_embeddings_batch(memory_ids: list[str]) -> dict[str, list[float]]:
    """Get cached embeddings for multiple memories from Redis using MGET.

    Batches requests to avoid exceeding Redis's 10MB response limit.
    Each embedding is ~8KB (1024 floats × 8 bytes JSON), so we batch
    in groups of 500 (~4MB per batch) to stay well under the limit.

    Args:
        memory_ids: List of memory IDs

    Returns:
        Dict mapping memory_id to embedding vector (only for cached entries)
    """
    if not memory_ids:
        return {}

    redis = await get_redis()
    if redis is None:
        return {}

    # Batch size: 400 embeddings × ~22KB = ~8.8MB per batch (under 10MB limit)
    # Actual embedding size: 1024 floats × ~21 bytes JSON encoding per float
    batch_size = 400
    result: dict[str, list[float]] = {}

    try:
        # Process in batches to avoid Redis 10MB limit
        for i in range(0, len(memory_ids), batch_size):
            batch_ids = memory_ids[i : i + batch_size]
            keys = [f"{MEMORY_EMBEDDING_PREFIX}{mid}" for mid in batch_ids]

            try:
                values = await redis.mget(keys)
            except Exception as batch_error:
                # If batch still fails, try smaller batches
                if batch_size > 100:
                    logger.warning(
                        f"MGET batch of {len(batch_ids)} failed, trying smaller batches: {batch_error}"
                    )
                    # Recursively process with smaller batch
                    for j in range(0, len(batch_ids), 100):
                        sub_batch = batch_ids[j : j + 100]
                        sub_keys = [f"{MEMORY_EMBEDDING_PREFIX}{mid}" for mid in sub_batch]
                        try:
                            sub_values = await redis.mget(sub_keys)
                            for mid, value in zip(sub_batch, sub_values):
                                if value:
                                    try:
                                        embedding = json.loads(value)
                                        if _is_valid_embedding(embedding):
                                            result[mid] = embedding
                                    except json.JSONDecodeError:
                                        pass
                        except Exception:
                            logger.warning(f"Sub-batch of {len(sub_batch)} also failed")
                    continue
                else:
                    raise

            for mid, value in zip(batch_ids, values):
                if value:
                    try:
                        embedding = json.loads(value)
                        # Validate embedding structure and dimensions
                        if _is_valid_embedding(embedding):
                            result[mid] = embedding
                        else:
                            logger.warning(
                                f"Invalid embedding for memory {mid}: "
                                f"expected {EMBEDDING_DIMENSION} dimensions, "
                                f"got {len(embedding) if isinstance(embedding, list) else 'non-list'}"
                            )
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse embedding JSON for memory {mid}")

        return result
    except Exception as e:
        logger.warning(f"Error getting memory embeddings batch: {e}")
        return {}


async def _store_memory_embedding(
    memory_id: str,
    embedding: list[float],
    ttl: int = MEMORY_EMBEDDING_TTL,
) -> bool:
    """Store embedding for a memory in Redis.

    Args:
        memory_id: The memory ID
        embedding: The embedding vector
        ttl: Time-to-live in seconds

    Returns:
        True if stored successfully
    """
    redis = await get_redis()
    if redis is None:
        return False

    try:
        key = f"{MEMORY_EMBEDDING_PREFIX}{memory_id}"
        await redis.setex(key, ttl, json.dumps(embedding))
        return True
    except Exception as e:
        logger.warning(f"Error storing memory embedding: {e}")
        return False


async def _delete_memory_embedding(memory_id: str) -> bool:
    """Delete embedding for a memory from Redis.

    Args:
        memory_id: The memory ID

    Returns:
        True if deleted
    """
    redis = await get_redis()
    if redis is None:
        return False

    try:
        key = f"{MEMORY_EMBEDDING_PREFIX}{memory_id}"
        await redis.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Error deleting memory embedding: {e}")
        return False


async def store_memory_v2(
    project_id: str,
    content: str,
    memory_type: str = "fact",
    scope: str = "project",
    category: str | None = None,
    ttl_days: int | None = None,
    related_to: list[str] | None = None,
    document_refs: list[str] | None = None,
    source: str | None = None,
    review_status: str | None = None,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
    title: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Store a Memory V2 row with explicit owner semantics."""
    _assert_memory_content_is_safe(content)
    normalized_memory_type = _normalize_memory_type(memory_type) or AgentMemoryType.FACT
    normalized_scope = _normalize_memory_scope(scope) or AgentMemoryScope.PROJECT
    normalized_review_status = resolve_review_status_for_source(
        settings,
        source=source,
        requested_review_status=review_status,
        content=content,
        memory_type=normalized_memory_type,
        category=category,
    )
    effective_ttl_days = await _resolve_effective_ttl_days(
        project_id,
        normalized_memory_type,
        ttl_days,
    )
    db = await get_db()
    resolved_team_id = await _resolve_project_team_id(project_id, team_id, db)
    owner_error = get_memory_scope_owner_error(
        normalized_scope,
        user_id=user_id,
        team_id=resolved_team_id,
        agent_id=agent_id,
    )
    if owner_error:
        raise ValueError(owner_error)

    now = datetime.now(UTC)
    valid_until = None
    stale_at = None
    if effective_ttl_days:
        expiry = now + timedelta(days=effective_ttl_days)
        if normalized_memory_type in {AgentMemoryType.TODO, AgentMemoryType.CONTEXT}:
            stale_at = expiry
        else:
            valid_until = expiry

    owner = _memory_v2_owner_payload(
        project_id=project_id,
        scope=normalized_scope,
        user_id=user_id,
        team_id=resolved_team_id,
        agent_id=agent_id,
    )
    payload = MemoryCreatePayload(
        project_id=owner["project_id"],
        team_id=owner["team_id"],
        user_id=owner["user_id"],
        agent_id=owner["agent_id"],
        type=normalized_memory_type,
        scope=normalized_scope,
        status=_memory_v2_status_for_review(normalized_review_status),
        title=title,
        content=content,
        summary=summary,
        category=category,
        confidence=1.0,
        freshness_score=1.0,
        evidence_score=0.0,
        valid_from=now,
        valid_until=valid_until,
        stale_at=stale_at,
        source=normalize_memory_source(source),
        created_by=user_id,
        reviewed_by=user_id if normalized_review_status != MEMORY_REVIEW_PENDING else None,
    )
    memory = await _memory_repository.create_memory(payload)
    if document_refs:
        await _memory_repository.attach_evidence(
            memory.id,
            [
                MemoryEvidencePayload(
                    evidence_type=EvidenceType.DOCUMENT,
                    external_ref=document_ref,
                )
                for document_ref in document_refs
            ],
        )
    if related_to:
        relations: list[MemoryRelationPayload] = []
        for related_memory_id in related_to:
            resolved_related_id = await _resolve_memory_v2_id(related_memory_id)
            if resolved_related_id:
                relations.append(
                    MemoryRelationPayload(
                        to_memory_id=resolved_related_id,
                        relation_type=MemoryRelationType.RELATED_TO,
                    )
                )
        await _memory_repository.create_relations(memory.id, relations)

    try:
        embeddings_service = get_embeddings_service()
        embedding = await embeddings_service.embed_text_async(content)
        embedding_ttl = MEMORY_EMBEDDING_TTL
        if effective_ttl_days:
            embedding_ttl = min(effective_ttl_days * 24 * 60 * 60, MEMORY_EMBEDDING_TTL)
        await _store_memory_embedding(memory.id, embedding, embedding_ttl)
    except Exception as e:
        logger.warning(f"Failed to generate embedding for Memory V2 {memory.id}: {e}")

    return {
        "memory_id": memory.id,
        "content": content,
        "type": normalized_memory_type.value,
        "scope": normalized_scope.value,
        "review_status": normalized_review_status.lower(),
        "status": _enum_lower(getattr(memory, "status", payload.status)),
        "category": category,
        "owner": {
            "project_id": owner["project_id"],
            "team_id": owner["team_id"],
            "user_id": owner["user_id"],
            "agent_id": owner["agent_id"],
        },
        "expires_at": valid_until.isoformat() if valid_until else None,
        "stale_at": stale_at.isoformat() if stale_at else None,
        "created": True,
        "message": f"Memory stored successfully (ID: {memory.id})",
    }


async def store_memory(
    project_id: str,
    content: str,
    memory_type: str = "fact",
    scope: str = "project",
    category: str | None = None,
    ttl_days: int | None = None,
    related_to: list[str] | None = None,
    document_refs: list[str] | None = None,
    source: str | None = None,
    review_status: str | None = None,
    review_notes: str | None = None,
    reviewed_at: datetime | None = None,
    reviewed_by: str | None = None,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Store a new memory with semantic embedding.

    Args:
        project_id: The project ID
        content: Memory content
        memory_type: Type of memory (fact, decision, learning, preference, todo, context)
        scope: Visibility scope (agent, project, team, user)
        category: Optional grouping category
        ttl_days: Days until expiration (null = permanent)
        related_to: IDs of related memories
        document_refs: Referenced document paths
        source: What created this memory

    Returns:
        Dict with memory_id, created status, and message
    """
    _assert_memory_content_is_safe(content)
    normalized_memory_type = _normalize_memory_type(memory_type) or AgentMemoryType.FACT
    normalized_scope = _normalize_memory_scope(scope) or AgentMemoryScope.PROJECT
    normalized_review_status = resolve_review_status_for_source(
        settings,
        source=source,
        requested_review_status=review_status,
        content=content,
        memory_type=normalized_memory_type,
        category=category,
    )
    if settings.memory_v2_primary_read is True:
        return await store_memory_v2(
            project_id=project_id,
            content=content,
            memory_type=normalized_memory_type.value,
            scope=normalized_scope.value,
            category=category,
            ttl_days=ttl_days,
            related_to=related_to,
            document_refs=document_refs,
            source=source,
            review_status=normalized_review_status,
            user_id=user_id,
            team_id=team_id,
            agent_id=agent_id,
        )

    effective_ttl_days = await _resolve_effective_ttl_days(
        project_id,
        normalized_memory_type,
        ttl_days,
    )
    now = datetime.now(UTC)
    db = await get_db()
    resolved_team_id = team_id
    if settings.memory_v2_dual_write is True:
        resolved_team_id = await _resolve_project_team_id(project_id, team_id, db)
        owner_error = get_memory_scope_owner_error(
            normalized_scope,
            user_id=user_id,
            team_id=resolved_team_id,
            agent_id=agent_id,
        )
        if owner_error:
            raise ValueError(owner_error)

    # Calculate expiration
    expires_at = None
    if effective_ttl_days:
        expires_at = now + timedelta(days=effective_ttl_days)

    # Map string types to enum values (Prisma expects uppercase)
    memory_type_upper = normalized_memory_type.value.upper()
    scope_upper = normalized_scope.value.upper()
    tier = classify_memory_tier(
        memory_type_upper,
        access_count=0,
        confidence=0.0,
        created_at=now,
    )

    # Create memory in database
    memory = await db.agentmemory.create(
        data={
            "projectId": project_id,
            "content": content,
            "type": memory_type_upper,
            "scope": scope_upper,
            "category": category,
            "expiresAt": expires_at,
            "relatedMemoryIds": related_to or [],
            "documentRefs": document_refs or [],
            "source": source,
            "confidence": 1.0,
            "accessCount": 0,
            "tier": tier,
            "reviewStatus": normalized_review_status,
            "reviewNotes": review_notes,
            "reviewedAt": None
            if normalized_review_status == MEMORY_REVIEW_PENDING
            else reviewed_at,
            "reviewedBy": None
            if normalized_review_status == MEMORY_REVIEW_PENDING
            else reviewed_by,
        }
    )

    # Generate and store embedding
    try:
        embeddings_service = get_embeddings_service()
        embedding = await embeddings_service.embed_text_async(content)

        # TTL for embedding based on memory TTL
        embedding_ttl = MEMORY_EMBEDDING_TTL
        if effective_ttl_days:
            embedding_ttl = min(effective_ttl_days * 24 * 60 * 60, MEMORY_EMBEDDING_TTL)

        await _store_memory_embedding(memory.id, embedding, embedding_ttl)
        logger.info(f"Stored memory {memory.id} with embedding")
    except Exception as e:
        logger.warning(f"Failed to generate embedding for memory {memory.id}: {e}")
        # Memory is still created, just without embedding

    # Trigger auto-compaction check (non-blocking)
    asyncio.create_task(_safe_auto_compact(project_id))

    if settings.memory_v2_dual_write is True:
        asyncio.create_task(
            _dual_write_memory_v2(
                legacy_memory=memory,
                memory_type=memory_type,
                scope=scope,
                ttl_days=effective_ttl_days,
                source=source,
                user_id=user_id,
                team_id=resolved_team_id,
                agent_id=agent_id,
            )
        )

    return {
        "memory_id": memory.id,
        "content": memory.content,
        "type": normalized_memory_type.value,
        "scope": normalized_scope.value,
        "review_status": normalized_review_status.lower(),
        "category": category,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "created": True,
        "message": f"Memory stored successfully (ID: {memory.id})",
    }


async def remember_if_novel(
    project_id: str,
    content: str,
    memory_type: str = "fact",
    scope: str = "project",
    category: str | None = None,
    ttl_days: int | None = None,
    related_to: list[str] | None = None,
    document_refs: list[str] | None = None,
    novelty_threshold: float = 0.92,
    dedupe_limit: int = 5,
    allow_supersede: bool = True,
    source: str | None = None,
    review_status: str | None = None,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Store a memory only when it is novel enough versus recent similar memories."""
    _assert_memory_content_is_safe(content)
    novelty_threshold = normalize_memory_novelty_threshold(novelty_threshold)
    normalized_memory_type = _normalize_memory_type(memory_type) or AgentMemoryType.FACT
    normalized_scope = _normalize_memory_scope(scope) or AgentMemoryScope.PROJECT

    recall_result = await semantic_recall(
        project_id=project_id,
        query=content,
        memory_type=normalized_memory_type.value,
        scope=normalized_scope.value,
        category=category,
        limit=dedupe_limit,
        min_relevance=0.0,
        include_pending=True,
        user_id=user_id,
        team_id=team_id,
        agent_id=agent_id,
    )

    matched_memories = recall_result.get("memories", []) or []
    best_match = matched_memories[0] if matched_memories else None
    best_score = 0.0
    if best_match:
        best_score = float(best_match.get("relevance") or best_match.get("score") or 0.0)

    supersede_candidate = None
    if best_match and allow_supersede and best_score >= SUPERSEDE_RELEVANCE_THRESHOLD:
        supersede_candidate = best_match

    if best_match and best_score >= novelty_threshold:
        return {
            "stored": False,
            "reason": "duplicate",
            "memory_id": None,
            "novelty_threshold": novelty_threshold,
            "matched_memories": matched_memories,
            "message": "Skipped duplicate memory",
        }

    effective_related_to = list(related_to or [])
    if supersede_candidate:
        superseded_id = supersede_candidate.get("memory_id")
        if superseded_id and superseded_id not in effective_related_to:
            effective_related_to.append(superseded_id)

    store_result = await store_memory(
        project_id=project_id,
        content=content,
        memory_type=normalized_memory_type.value,
        scope=normalized_scope.value,
        category=category,
        ttl_days=ttl_days,
        related_to=effective_related_to,
        document_refs=document_refs,
        source=source,
        review_status=review_status,
        user_id=user_id,
        team_id=team_id,
        agent_id=agent_id,
    )

    supersede_result = None
    new_memory_id = store_result.get("memory_id")
    if supersede_candidate and new_memory_id:
        old_memory_id = supersede_candidate.get("memory_id")
        if old_memory_id:
            if settings.memory_v2_primary_read is True:
                supersede_result = await supersede_memory_v2(
                    old_memory_id,
                    new_memory_id,
                    reason="Superseded by newer remember_if_novel write",
                )
            else:
                db = await get_db()
                supersede_result = await _mark_legacy_memory_superseded(
                    db,
                    old_memory_id=old_memory_id,
                    new_memory_id=new_memory_id,
                    reason="Superseded by newer remember_if_novel write",
                )
                if settings.memory_v2_dual_write is True:
                    asyncio.create_task(_safe_supersede_memory_v2(old_memory_id, new_memory_id))

    return {
        "stored": True,
        "reason": "superseded" if supersede_result else "novel",
        "memory_id": new_memory_id,
        "novelty_threshold": novelty_threshold,
        "supersede_threshold": SUPERSEDE_RELEVANCE_THRESHOLD,
        "matched_memories": matched_memories,
        "superseded_memory": supersede_result,
        "store_result": store_result,
        "message": "Stored novel memory and superseded older match"
        if supersede_result
        else "Stored novel memory",
    }


TASK_COMMIT_PERSIST_TYPES = ("decision", "learning", "preference", "todo", "context")
TASK_COMMIT_DEFAULT_PERSIST_TYPES = ("decision", "learning", "preference", "todo", "context")

TASK_COMMIT_RECEIPT_PATTERNS = (
    re.compile(
        r"\b(files? modified|files? touched|tests? (run|passed|failed)|lint passed)\b", re.I
    ),
    re.compile(r"\b(committed|pushed|opened pr|created branch|staged changes)\b", re.I),
    re.compile(r"\b(done|completed):?\s*(edited|updated|changed|ran|tested)\b", re.I),
    re.compile(r"\b(summary|result|verification|modified files?)\s*:", re.I),
)


def _split_task_commit_summary(summary: str) -> list[str]:
    """Split a task summary into durable-knowledge-sized statements."""
    statements: list[str] = []
    for raw_line in re.split(r"[\n\r]+", summary):
        line = re.sub(r"^\s*[-*•]\s*", "", raw_line).strip()
        if not line:
            continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", line)
        statements.extend(part.strip(" ;") for part in parts if part.strip(" ;"))
    return statements


def _is_task_commit_receipt(text: str) -> bool:
    """Return True for operational receipts that should not become durable memory."""
    normalized = " ".join(text.split())
    lowered = normalized.lower()
    if len(normalized) < 24:
        return True
    if any(pattern.search(normalized) for pattern in TASK_COMMIT_RECEIPT_PATTERNS):
        return True
    if lowered.startswith(("i ", "we ")) and any(
        verb in lowered for verb in ("edited", "updated", "changed", "ran", "tested", "added tests")
    ):
        return True
    return False


def _classify_task_commit_statement(text: str) -> tuple[str, str, str] | None:
    """Classify a single task summary statement into a durable memory candidate."""
    lowered = text.lower()
    if re.search(r"\b(decided|decision|chose|choose|standardized|adopted|migrated to)\b", lowered):
        return ("decision", "decision", "decision_signal")
    if re.search(r"\b(prefer|preference|user wants|team wants|should default to)\b", lowered):
        return ("preference", "preference", "preference_signal")
    if re.search(r"\b(todo|follow[- ]?up|next step|still need|needs to|blocked by)\b", lowered):
        return ("todo", "todo", "todo_signal")
    if re.search(
        r"\b(learned|found|discovered|root cause|fixed by|resolved by|workaround|validated|troubleshooting)\b",
        lowered,
    ):
        return ("learning", "learning", "learning_signal")
    if re.search(r"\b(workflow|runbook|from now on|always use|do not|never|must use)\b", lowered):
        return ("context", "context", "workflow_signal")
    return None


def _extract_task_commit_candidates(
    summary: str,
    outcome: str,
    persist_types: list[str] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Build and explain durable memory candidates from a task summary."""
    allowed = set(persist_types or TASK_COMMIT_DEFAULT_PERSIST_TYPES)
    allowed.discard("workflow")
    if "workflow" in (persist_types or []):
        allowed.add("context")

    candidates: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for statement in _split_task_commit_summary(summary):
        normalized = " ".join(statement.split())
        if memory_content_has_sensitive_material(normalized):
            skipped.append(
                {"text": SENSITIVE_MEMORY_REDACTION, "reason": LOW_SIGNAL_REASON_SENSITIVE_MATERIAL}
            )
            continue
        if _is_task_commit_receipt(normalized):
            skipped.append({"text": normalized, "reason": "operational_receipt"})
            continue

        classified = _classify_task_commit_statement(normalized)
        if classified is None:
            skipped.append({"text": normalized, "reason": "no_durable_signal"})
            continue

        candidate_type, memory_type, reason = classified
        if candidate_type not in allowed:
            skipped.append(
                {
                    "text": normalized,
                    "candidate_type": candidate_type,
                    "reason": "type_not_requested",
                }
            )
            continue

        dedupe_key = (memory_type, normalized.lower())
        if dedupe_key in seen:
            skipped.append(
                {
                    "text": normalized,
                    "candidate_type": candidate_type,
                    "reason": "duplicate_candidate",
                }
            )
            continue
        seen.add(dedupe_key)
        candidates.append(
            {
                "candidate_type": candidate_type,
                "memory_type": memory_type,
                "text": normalized,
                "reason": reason,
            }
        )

    if not candidates and outcome in {"blocked", "partial"}:
        for statement in _split_task_commit_summary(summary):
            normalized = " ".join(statement.split())
            if (
                not _is_task_commit_receipt(normalized)
                and len(normalized) >= 40
                and "context" in allowed
            ):
                candidates.append(
                    {
                        "candidate_type": "context",
                        "memory_type": "context",
                        "text": normalized,
                        "reason": f"{outcome}_context",
                    }
                )
                break

    return {"candidates": candidates, "skipped": skipped}


async def end_of_task_commit(
    project_id: str,
    summary: str,
    outcome: str = "completed",
    files_touched: list[str] | None = None,
    artifacts: list[str] | None = None,
    persist_types: list[str] | None = None,
    category: str | None = None,
    dry_run: bool = False,
    novelty_threshold: float = 0.92,
    review_status: str | None = None,
    deduplicate_before_write: bool = True,
    source: str = "task_commit",
    user_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    """Persist durable outcomes from a task summary."""
    del files_touched, artifacts

    normalized = " ".join(summary.split())
    if len(normalized) < 20:
        return {
            "stored_count": 0,
            "skipped_count": 0,
            "candidates": [],
            "message": "Summary too short for durable commit",
        }

    extraction = _extract_task_commit_candidates(
        summary=normalized,
        outcome=outcome,
        persist_types=persist_types,
    )
    candidates = extraction["candidates"]
    skipped_candidates = extraction["skipped"]

    if not candidates:
        return {
            "stored_count": 0,
            "skipped_count": len(skipped_candidates),
            "candidates": [],
            "stored_candidates": [],
            "skipped_candidates": skipped_candidates,
            "message": "No durable knowledge detected",
        }

    if dry_run:
        return {
            "stored_count": 0,
            "skipped_count": len(skipped_candidates),
            "candidates": [{**candidate, "durable": True} for candidate in candidates],
            "stored_candidates": [],
            "skipped_candidates": skipped_candidates,
            "message": "Dry run only",
        }

    results = []
    stored_candidates = []
    stored_count = 0
    skipped_count = len(skipped_candidates)

    for candidate in candidates:
        if deduplicate_before_write:
            result = await remember_if_novel(
                project_id=project_id,
                content=candidate["text"],
                memory_type=candidate["memory_type"],
                scope="project",
                category=category or f"task-{candidate['candidate_type']}",
                novelty_threshold=novelty_threshold,
                source=source,
                review_status=review_status,
                user_id=user_id,
                team_id=team_id,
                allow_supersede=False,
            )
            stored = bool(result.get("stored"))
            reason = result.get("reason")
            memory_id = result.get("memory_id")
        else:
            stored_result = await store_memory(
                project_id=project_id,
                content=candidate["text"],
                memory_type=candidate["memory_type"],
                scope="project",
                category=category or f"task-{candidate['candidate_type']}",
                source=source,
                review_status=review_status,
                user_id=user_id,
                team_id=team_id,
            )
            stored = True
            reason = "stored"
            memory_id = stored_result.get("memory_id")

        stored_count += 1 if stored else 0
        skipped_count += 0 if stored else 1
        result_item = {
            **candidate,
            "stored": stored,
            "memory_id": memory_id,
            "reason": reason,
        }
        results.append(result_item)
        if stored:
            stored_candidates.append(result_item)
        else:
            skipped_candidates.append({**candidate, "reason": reason or "not_stored"})

    return {
        "stored_count": stored_count,
        "skipped_count": skipped_count,
        "candidates": results,
        "stored_candidates": stored_candidates,
        "skipped_candidates": skipped_candidates,
        "message": "Task commit processed",
    }


async def _dual_write_legacy_memory_object(
    legacy_memory: Any,
    *,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> str | None:
    """Persist a legacy AgentMemory ORM row into Memory V2."""

    mapped = map_agent_memory_to_memory_payload(legacy_memory)
    scope = (
        _normalize_memory_scope(getattr(legacy_memory, "scope", None)) or AgentMemoryScope.PROJECT
    )
    db = await get_db()
    resolved_team_id = await _resolve_project_team_id(
        getattr(legacy_memory, "projectId", None),
        team_id,
        db,
    )
    owner_error = get_memory_scope_owner_error(
        scope,
        user_id=user_id,
        team_id=resolved_team_id,
        agent_id=agent_id,
    )
    if owner_error:
        logger.warning(
            "Skipping Memory V2 dual-write for legacy memory %s: %s",
            getattr(legacy_memory, "id", "unknown"),
            owner_error,
        )
        return None
    if scope == AgentMemoryScope.USER:
        mapped.memory.user_id = user_id
    elif scope == AgentMemoryScope.TEAM:
        mapped.memory.team_id = resolved_team_id
    elif scope == AgentMemoryScope.AGENT:
        mapped.memory.agent_id = agent_id
    mapped.memory.created_by = user_id
    memory_v2 = await _memory_repository.create_memory(mapped.memory)

    if mapped.evidence:
        await _memory_repository.attach_evidence(memory_v2.id, mapped.evidence)

    await _memory_repository.create_migration_map(
        MemoryMigrationMapPayload(
            legacy_agent_memory_id=legacy_memory.id,
            new_memory_id=memory_v2.id,
            checksum=mapped.checksum,
        )
    )

    for related_legacy_id in mapped.related_legacy_ids:
        related_v2_id = await _memory_repository.get_memory_id_for_legacy_id(related_legacy_id)
        if related_v2_id:
            await _memory_repository.create_relations(
                memory_v2.id,
                [MemoryRelationPayload(to_memory_id=related_v2_id, relation_type="RELATED_TO")],
            )

    return memory_v2.id


async def _dual_write_memory_v2(
    legacy_memory: Any,
    memory_type: str,
    scope: str,
    ttl_days: int | None,
    source: str | None,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> None:
    """Best-effort dual-write of legacy AgentMemory into Memory V2."""

    try:
        memory_v2_id = await _dual_write_legacy_memory_object(
            legacy_memory,
            user_id=user_id,
            team_id=team_id,
            agent_id=agent_id,
        )
        logger.info(f"Dual-wrote legacy memory {legacy_memory.id} to Memory V2 {memory_v2_id}")
    except Exception as e:
        logger.warning(
            f"Memory V2 dual-write failed for legacy memory {getattr(legacy_memory, 'id', 'unknown')}: {e}"
        )


async def _resolve_memory_v2_id(memory_id: str) -> str | None:
    """Resolve a Memory V2 ID from either a V2 or legacy memory ID.

    When dual-write is enabled, a freshly-created legacy memory may not yet have
    its migration map row because the V2 write runs in the background. In that
    case, briefly poll for the map before returning not found.
    """

    memory = await _memory_repository.get_memory(memory_id)
    if memory is not None:
        return memory_id

    resolved_id = await _memory_repository.get_memory_id_for_legacy_id(memory_id)
    if resolved_id is not None:
        return resolved_id

    if settings.memory_v2_dual_write is not True:
        return None

    db = await get_db()
    legacy_memory = await db.agentmemory.find_unique(where={"id": memory_id})
    if legacy_memory is None:
        return None

    for _ in range(DUAL_WRITE_RESOLUTION_ATTEMPTS):
        await asyncio.sleep(DUAL_WRITE_RESOLUTION_DELAY_SECONDS)
        resolved_id = await _memory_repository.get_memory_id_for_legacy_id(memory_id)
        if resolved_id is not None:
            return resolved_id

    return None


async def _mark_legacy_memory_superseded(
    db: Any,
    old_memory_id: str,
    new_memory_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Mark an old AgentMemory row as superseded by a new active row."""

    superseded_at = datetime.now(UTC)
    await db.agentmemory.update(
        where={"id": old_memory_id},
        data={
            "status": MEMORY_STATUS_SUPERSEDED,
            "invalidatedAt": superseded_at,
            "invalidatedReason": reason,
            "supersededByMemoryId": new_memory_id,
        },
    )
    return {
        "old_memory_id": old_memory_id,
        "new_memory_id": new_memory_id,
        "status": MEMORY_STATUS_SUPERSEDED.lower(),
        "superseded_at": superseded_at.isoformat(),
        "reason": reason,
    }


async def _invalidate_legacy_memory(
    db: Any,
    memory_id: str,
    invalidated_at: datetime,
    reason: str | None = None,
) -> dict[str, Any] | None:
    """Mark a legacy AgentMemory row inactive when no Memory V2 row exists."""
    legacy_memory = await db.agentmemory.find_unique(where={"id": memory_id})
    if legacy_memory is None:
        return None

    await db.agentmemory.update(
        where={"id": memory_id},
        data={
            "status": MEMORY_STATUS_INVALIDATED,
            "invalidatedAt": invalidated_at,
            "invalidatedReason": reason,
        },
    )
    return {
        "memory_id": memory_id,
        "invalidated": True,
        "status": MEMORY_STATUS_INVALIDATED.lower(),
        "invalidated_at": invalidated_at.isoformat(),
        "reason": reason,
        "message": f"Legacy memory '{memory_id}' invalidated",
    }


async def _safe_supersede_memory_v2(
    old_memory_id: str,
    new_memory_id: str,
) -> None:
    """Best-effort propagation of legacy supersession into Memory V2."""

    try:
        old_v2_id = await _resolve_memory_v2_id(old_memory_id)
        new_v2_id = await _resolve_memory_v2_id(new_memory_id)
        if not old_v2_id or not new_v2_id:
            return
        await _memory_repository.supersede_memory(old_v2_id, new_v2_id, datetime.now(UTC))
    except Exception as e:
        logger.debug(
            "Memory V2 supersede propagation failed for %s -> %s: %s",
            old_memory_id,
            new_memory_id,
            e,
        )


async def _safe_auto_compact(project_id: str) -> None:
    """Safely run auto-compaction without blocking or raising."""
    try:
        await maybe_auto_compact(project_id)
    except Exception as e:
        logger.debug(f"Auto-compact background task failed: {e}")


async def store_memories_bulk(
    project_id: str,
    memories: list[dict[str, Any]],
    source: str | None = None,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Store multiple memories with batch embedding.

    Args:
        project_id: The project ID
        memories: Array of memory objects, each with:
            - text: Memory text to store
            - type: Memory type (default: fact)
            - scope: Visibility scope (default: project)
            - category: Optional grouping category
            - ttl_days: Days until expiration
            - related_to: IDs of related memories
            - document_refs: Referenced document paths
        source: What created these memories

    Returns:
        Dict with created memory IDs and stats
    """
    import asyncio

    if settings.memory_v2_primary_read is True:
        created_ids: list[str] = []
        failed: list[dict[str, Any]] = []
        for i, mem in enumerate(memories):
            try:
                result = await store_memory_v2(
                    project_id=project_id,
                    content=mem.get("text", ""),
                    memory_type=mem.get("type", "fact"),
                    scope=mem.get("scope", "project"),
                    category=mem.get("category"),
                    ttl_days=mem.get("ttl_days"),
                    related_to=mem.get("related_to"),
                    document_refs=mem.get("document_refs"),
                    source=source,
                    review_status=mem.get("review_status"),
                    user_id=user_id,
                    team_id=team_id,
                    agent_id=mem.get("agent_id") or agent_id,
                )
                created_ids.append(result["memory_id"])
            except Exception as e:
                failed.append({"index": i, "error": str(e)})
        return {
            "created": len(created_ids),
            "failed": len(failed),
            "memory_ids": created_ids,
            "failures": failed if failed else None,
            "message": f"Stored {len(created_ids)} memories successfully",
        }

    db = await get_db()
    created_ids: list[str] = []
    failed: list[dict[str, Any]] = []
    texts: list[str] = []
    created_memories: list[Any] = []
    created_memory_owners: list[dict[str, str | None]] = []
    embedding_ttls: list[int] = []
    resolved_team_id = team_id
    if settings.memory_v2_dual_write is True:
        resolved_team_id = await _resolve_project_team_id(project_id, team_id, db)

    # Process each memory
    for i, mem in enumerate(memories):
        text = mem.get("text", "")
        if not text:
            failed.append({"index": i, "error": "text is required"})
            continue

        category = mem.get("category")
        ttl_days = mem.get("ttl_days")
        related_to = mem.get("related_to")
        document_refs = mem.get("document_refs")
        review_status = resolve_review_status_for_source(
            settings,
            source=source,
            requested_review_status=mem.get("review_status"),
            content=text,
            memory_type=mem.get("type", "fact"),
            category=category,
        )
        review_notes = mem.get("review_notes")
        reviewed_at = mem.get("reviewed_at")
        reviewed_by = mem.get("reviewed_by")

        try:
            _assert_memory_content_is_safe(text)
            memory_type = _normalize_memory_type(mem.get("type", "fact")) or AgentMemoryType.FACT
            scope = _normalize_memory_scope(mem.get("scope", "project")) or AgentMemoryScope.PROJECT
            item_agent_id = mem.get("agent_id") or agent_id
            if settings.memory_v2_dual_write is True:
                owner_error = get_memory_scope_owner_error(
                    scope,
                    user_id=user_id,
                    team_id=resolved_team_id,
                    agent_id=item_agent_id,
                )
                if owner_error:
                    raise ValueError(owner_error)

            effective_ttl_days = await _resolve_effective_ttl_days(
                project_id,
                memory_type,
                ttl_days,
            )
            now = datetime.now(UTC)

            # Calculate expiration
            expires_at = None
            if effective_ttl_days:
                expires_at = now + timedelta(days=effective_ttl_days)

            tier = classify_memory_tier(
                memory_type.value.upper(),
                access_count=0,
                confidence=0.0,
                created_at=now,
            )
            memory = await db.agentmemory.create(
                data={
                    "projectId": project_id,
                    "content": text,
                    "type": memory_type.value.upper(),
                    "scope": scope.value.upper(),
                    "category": category,
                    "expiresAt": expires_at,
                    "relatedMemoryIds": related_to or [],
                    "documentRefs": document_refs or [],
                    "source": source,
                    "confidence": 1.0,
                    "accessCount": 0,
                    "tier": tier,
                    "reviewStatus": review_status,
                    "reviewNotes": review_notes,
                    "reviewedAt": None if review_status == MEMORY_REVIEW_PENDING else reviewed_at,
                    "reviewedBy": None if review_status == MEMORY_REVIEW_PENDING else reviewed_by,
                }
            )
            created_memories.append(memory)
            created_memory_owners.append(
                {
                    "user_id": user_id,
                    "team_id": resolved_team_id,
                    "agent_id": item_agent_id,
                }
            )
            created_ids.append(memory.id)
            texts.append(text)
            embedding_ttls.append(
                min(effective_ttl_days * 24 * 60 * 60, MEMORY_EMBEDDING_TTL)
                if effective_ttl_days
                else MEMORY_EMBEDDING_TTL
            )
        except Exception as e:
            logger.warning(f"Failed to create memory at index {i}: {e}")
            failed.append({"index": i, "error": str(e)})

    # Batch generate embeddings for all created memories
    if texts:
        try:
            embeddings_service = get_embeddings_service()
            embeddings = await embeddings_service.embed_texts_async(texts)

            # Store embeddings in parallel
            tasks = [
                _store_memory_embedding(mem.id, emb, ttl)
                for mem, emb, ttl in zip(created_memories, embeddings, embedding_ttls)
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            logger.info(f"Stored {len(created_ids)} memories with batch embeddings")
        except Exception as e:
            logger.warning(f"Failed to generate batch embeddings: {e}")
            # Memories still created, just without embeddings

    if settings.memory_v2_dual_write is True and created_memories:
        try:
            await asyncio.gather(
                *(
                    _dual_write_legacy_memory_object(
                        memory,
                        user_id=owner["user_id"],
                        team_id=owner["team_id"],
                        agent_id=owner["agent_id"],
                    )
                    for memory, owner in zip(created_memories, created_memory_owners)
                ),
                return_exceptions=True,
            )
        except Exception as e:
            logger.warning(f"Bulk Memory V2 dual-write failed: {e}")

    return {
        "created": len(created_ids),
        "failed": len(failed),
        "memory_ids": created_ids,
        "failures": failed if failed else None,
        "message": f"Stored {len(created_ids)} memories successfully",
    }


def _recall_ranking_boost(query: str, memory: Any) -> tuple[float, list[str]]:
    """Return a small bounded ranking boost for intent-critical memory classes."""
    terms = set(re.findall(r"[a-z0-9_:-]+", query.lower()))
    memory_type = _enum_lower(getattr(memory, "type", ""))
    scope = _enum_lower(getattr(memory, "scope", ""))
    category = str(getattr(memory, "category", "") or "").lower()
    content = str(getattr(memory, "content", "") or "").lower()

    boost = 0.0
    reasons: list[str] = []

    if terms & {"prefer", "preference", "preferences", "user", "profile", "personal"}:
        if memory_type == "preference" or scope == "user" or "preference" in category:
            boost += 0.08
            reasons.append("preference_intent")

    if terms & {"decision", "decisions", "adr", "architecture", "rationale", "chosen", "chose"}:
        if memory_type == "decision" or "architecture" in category or "decided" in content:
            boost += 0.07
            reasons.append("decision_intent")

    if terms & {
        "bug",
        "bugs",
        "fix",
        "fixed",
        "root",
        "cause",
        "troubleshoot",
        "troubleshooting",
        "workaround",
    }:
        if memory_type == "learning" or any(
            marker in content for marker in ("root cause", "fixed", "workaround", "resolved")
        ):
            boost += 0.07
            reasons.append("troubleshooting_intent")

    if terms & {"bootstrap", "session", "carryover", "resume", "handoff", "context"}:
        if memory_type in {"context", "todo"} or category in {"session", "handoff", "context"}:
            boost += 0.06
            reasons.append("session_carryover_intent")

    return min(boost, MEMORY_RANKING_MAX_BOOST), reasons


def _apply_recall_ranking_boost(
    relevance: float,
    query: str,
    memory: Any,
) -> tuple[float, list[str]]:
    boost, reasons = _recall_ranking_boost(query, memory)
    if boost <= 0:
        return relevance, []
    return min(relevance * (1.0 + boost), 1.0), reasons


async def _semantic_recall_v2(
    project_id: str,
    query: str,
    memory_type: str | None = None,
    scope: str | None = None,
    category: str | None = None,
    limit: int = 5,
    min_relevance: float = 0.6,
    include_expired: bool = False,
    include_inactive: bool = False,
    warning_threshold: float = 0.72,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Semantically recall Memory V2 rows with explicit owner boundaries."""
    import time

    start_time = time.time()
    warnings: list[str] = []
    db = await get_db()
    resolved_team_id = await _resolve_project_team_id(project_id, team_id, db)
    normalized_scope = _normalize_memory_scope(scope) if scope else None
    owner_error = (
        get_memory_scope_owner_error(
            normalized_scope,
            user_id=user_id,
            team_id=resolved_team_id,
            agent_id=agent_id,
        )
        if normalized_scope
        else None
    )
    if owner_error:
        return {
            "memories": [],
            "warnings": [],
            "total_searched": 0,
            "query": query,
            "error": owner_error,
            "timing_ms": int((time.time() - start_time) * 1000),
        }

    normalized_memory_type = _normalize_memory_type(memory_type) if memory_type else None
    where = _build_memory_v2_where(
        project_id=project_id,
        scope=normalized_scope,
        user_id=user_id,
        team_id=resolved_team_id,
        agent_id=agent_id,
        memory_type=normalized_memory_type,
        category=category,
        include_expired=include_expired,
        include_inactive=include_inactive,
    )
    if where is None:
        return {
            "memories": [],
            "warnings": [],
            "total_searched": 0,
            "query": query,
            "timing_ms": int((time.time() - start_time) * 1000),
        }

    memories = await db.memory.find_many(where=where, order={"createdAt": "desc"}, take=500)
    if not category:
        memories = [memory for memory in memories if not _is_transient_operational_memory(memory)]
    memories, filtered_sensitive_count = _filter_sensitive_memories(memories)
    if filtered_sensitive_count:
        warnings.append("sensitive_memory_filtered")
    if not memories:
        return {
            "memories": [],
            "warnings": warnings,
            "total_searched": 0,
            "query": query,
            "timing_ms": int((time.time() - start_time) * 1000),
        }

    embeddings_service = get_embeddings_service()
    try:
        query_embedding = await _embed_text_with_timeout(
            embeddings_service,
            query,
            RECALL_QUERY_EMBEDDING_TIMEOUT_SECONDS,
            label="Memory V2 recall query",
        )
    except Exception as e:
        logger.error(f"Failed to embed query for Memory V2 recall: {e}")
        fallback = await _text_search_fallback(memories, query, limit, min_relevance, start_time)
        fallback["warnings"] = warnings + fallback.get("warnings", [])
        return fallback

    cached_embeddings = await _get_memory_embeddings_batch([m.id for m in memories])
    memory_embeddings: list[tuple[Any, list[float]]] = []
    memories_to_embed: list[Any] = []
    for memory in memories:
        if memory.id in cached_embeddings:
            memory_embeddings.append((memory, cached_embeddings[memory.id]))
            continue
        memories_to_embed.append(memory)

    embedded_on_the_fly = 0
    skipped_missing_embeddings = 0
    embedding_deadline = time.time() + RECALL_ON_THE_FLY_EMBEDDING_BUDGET_SECONDS
    for memory in memories_to_embed[:RECALL_ON_THE_FLY_EMBEDDING_LIMIT]:
        if time.time() >= embedding_deadline:
            skipped_missing_embeddings = len(memories_to_embed) - embedded_on_the_fly
            logger.warning(
                "Memory V2 recall embedding budget exhausted after %s generated embeddings",
                embedded_on_the_fly,
            )
            break
        try:
            embedding = await _embed_text_with_timeout(
                embeddings_service,
                memory.content,
                RECALL_MEMORY_EMBEDDING_TIMEOUT_SECONDS,
                label=f"Memory V2 row {memory.id}",
            )
            await _store_memory_embedding(memory.id, embedding)
            memory_embeddings.append((memory, embedding))
            embedded_on_the_fly += 1
        except Exception as e:
            logger.warning(f"Failed to embed Memory V2 {memory.id}: {e}")

    if len(memories_to_embed) > embedded_on_the_fly and skipped_missing_embeddings == 0:
        skipped_missing_embeddings = len(memories_to_embed) - embedded_on_the_fly
    if skipped_missing_embeddings:
        logger.info(
            "Memory V2 recall used %s cached embeddings, generated %s, skipped %s uncached rows",
            len(cached_embeddings),
            embedded_on_the_fly,
            skipped_missing_embeddings,
        )

    if not memory_embeddings:
        logger.warning("Memory V2 recall had no usable embeddings; using text fallback")
        fallback = await _text_search_fallback(memories, query, limit, min_relevance, start_time)
        fallback["warnings"] = warnings + fallback.get("warnings", [])
        return fallback

    similarities = embeddings_service.cosine_similarity(
        query_embedding,
        [emb for _, emb in memory_embeddings],
    )
    results = []
    for (memory, _), similarity in zip(memory_embeddings, similarities):
        decayed_confidence = calculate_confidence_decay(
            memory.confidence,
            memory.createdAt,
            memory.lastAccessedAt,
        )
        relevance = (similarity * 0.7) + (similarity * decayed_confidence * 0.3)
        relevance, ranking_boosts = _apply_recall_ranking_boost(relevance, query, memory)
        if relevance < min_relevance:
            continue
        item = {
            "memory_id": memory.id,
            "content": memory.content,
            "type": _enum_lower(memory.type),
            "scope": _enum_lower(memory.scope),
            "category": memory.category,
            "status": _enum_lower(memory.status),
            "review_status": "approved"
            if _enum_upper(memory.status) == "ACTIVE"
            else "pending"
            if _enum_upper(memory.status) == "CANDIDATE"
            else "rejected",
            "owner": {
                "project_id": getattr(memory, "projectId", None),
                "team_id": getattr(memory, "teamId", None),
                "user_id": getattr(memory, "userId", None),
                "agent_id": getattr(memory, "agentId", None),
            },
            "relevance": round(relevance, 4),
            "confidence": round(decayed_confidence, 4),
            "created_at": memory.createdAt.isoformat(),
            "last_accessed_at": memory.lastAccessedAt.isoformat()
            if memory.lastAccessedAt
            else None,
            "access_count": 0,
        }
        if ranking_boosts:
            item["ranking_boosts"] = ranking_boosts
        results.append(item)

    results.sort(key=lambda x: x["relevance"], reverse=True)
    results = results[:limit]
    if results:
        try:
            await db.memory.update_many(
                where={"id": {"in": [r["memory_id"] for r in results]}},
                data={"lastAccessedAt": datetime.now(UTC)},
            )
        except Exception as e:
            logger.warning(f"Failed to update Memory V2 access timestamps: {e}")

    _ = warning_threshold
    return {
        "memories": results,
        "warnings": warnings,
        "total_searched": len(memories),
        "query": query,
        "timing_ms": int((time.time() - start_time) * 1000),
    }


async def semantic_recall(
    project_id: str,
    query: str,
    memory_type: str | None = None,
    scope: str | None = None,
    category: str | None = None,
    limit: int = 5,
    min_relevance: float = 0.6,
    include_expired: bool = False,
    include_inactive: bool = False,
    warning_threshold: float = 0.72,
    include_pending: bool = False,
    include_rejected: bool = False,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Semantically recall relevant memories based on a query.

    Args:
        project_id: The project ID
        query: Search query
        memory_type: Filter by type
        scope: Filter by scope
        category: Filter by category
        limit: Maximum memories to return
        min_relevance: Minimum relevance score (0-1)
        include_expired: Include expired memories
        include_inactive: Reserved for inactive-memory surfacing in recall results
        warning_threshold: Reserved threshold for inactive-memory warnings

    Returns:
        Dict with recalled memories and metadata
    """
    import time

    start_time = time.time()
    warnings: list[str] = []
    if settings.memory_v2_primary_read is True or settings.memory_v2_dual_read is True:
        v2_result = await _semantic_recall_v2(
            project_id=project_id,
            query=query,
            memory_type=memory_type,
            scope=scope,
            category=category,
            limit=limit,
            min_relevance=min_relevance,
            include_expired=include_expired,
            include_inactive=include_inactive or include_pending or include_rejected,
            warning_threshold=warning_threshold,
            user_id=user_id,
            team_id=team_id,
            agent_id=agent_id,
        )
        if settings.memory_v2_primary_read is True or v2_result.get("memories"):
            return v2_result

    # Build filter
    where: dict[str, Any] = {"projectId": project_id}
    _apply_review_status_filter(
        where,
        include_pending=include_pending,
        include_rejected=include_rejected,
    )
    if memory_type:
        normalized_memory_type = _normalize_memory_type(memory_type)
        where["type"] = normalized_memory_type.value.upper()
    if scope:
        normalized_scope = _normalize_memory_scope(scope)
        where["scope"] = normalized_scope.value.upper()
    if category:
        where["category"] = category
    if not include_expired:
        where["OR"] = [
            {"expiresAt": None},
            {"expiresAt": {"gt": datetime.now(UTC)}},
        ]
    if not include_inactive:
        where["status"] = MEMORY_STATUS_ACTIVE

    _ = warning_threshold

    db = await get_db()
    embeddings_service = get_embeddings_service()

    # Prioritize active/non-archived memories before considering ARCHIVE rows.
    memories = await _fetch_recall_candidates(db, where)

    if not category:
        memories = [memory for memory in memories if not _is_transient_operational_memory(memory)]
    memories, filtered_sensitive_count = _filter_sensitive_memories(memories)
    if filtered_sensitive_count:
        warnings.append("sensitive_memory_filtered")

    if not memories:
        return {
            "memories": [],
            "warnings": warnings,
            "total_searched": 0,
            "query": query,
            "timing_ms": int((time.time() - start_time) * 1000),
        }

    # Generate query embedding
    try:
        query_embedding = await _embed_text_with_timeout(
            embeddings_service,
            query,
            RECALL_QUERY_EMBEDDING_TIMEOUT_SECONDS,
            label="legacy memory recall query",
        )
    except Exception as e:
        logger.error(f"Failed to embed query: {e}")
        # Fallback to text search if embedding fails
        fallback = await _text_search_fallback(memories, query, limit, min_relevance, start_time)
        fallback["warnings"] = warnings + fallback.get("warnings", [])
        return fallback

    # Batch fetch all cached embeddings
    memory_ids = [m.id for m in memories]
    cached_embeddings = await _get_memory_embeddings_batch(memory_ids)
    logger.debug(f"Cache hit: {len(cached_embeddings)}/{len(memories)} embeddings")

    # Identify memories needing embedding generation
    memory_embeddings: list[tuple[Any, list[float]]] = []
    memories_to_embed: list[Any] = []

    for memory in memories:
        if memory.id in cached_embeddings:
            memory_embeddings.append((memory, cached_embeddings[memory.id]))
        else:
            memories_to_embed.append(memory)

    # Batch generate embeddings for cache misses (limit to prevent timeout)
    if memories_to_embed:
        # Limit on-the-fly generation to prevent long delays
        max_to_embed = min(len(memories_to_embed), 10)
        for memory in memories_to_embed[:max_to_embed]:
            try:
                embedding = await _embed_text_with_timeout(
                    embeddings_service,
                    memory.content,
                    RECALL_MEMORY_EMBEDDING_TIMEOUT_SECONDS,
                    label=f"legacy memory row {memory.id}",
                )
                await _store_memory_embedding(memory.id, embedding)
                memory_embeddings.append((memory, embedding))
            except Exception as e:
                logger.warning(f"Failed to embed memory {memory.id}: {e}")
                continue
        if len(memories_to_embed) > max_to_embed:
            logger.info(
                f"Skipped embedding {len(memories_to_embed) - max_to_embed} memories to prevent timeout"
            )

    if not memory_embeddings:
        logger.warning("Legacy memory recall had no usable embeddings; using text fallback")
        fallback = await _text_search_fallback(memories, query, limit, min_relevance, start_time)
        fallback["warnings"] = warnings + fallback.get("warnings", [])
        return fallback

    # Calculate similarities
    doc_embeddings = [emb for _, emb in memory_embeddings]
    try:
        similarities = embeddings_service.cosine_similarity(query_embedding, doc_embeddings)
    except ValueError as e:
        logger.error(
            f"Failed to calculate similarities due to dimension mismatch: {e}. "
            "This indicates corrupted embeddings in cache. Falling back to text search."
        )
        # Fallback to text search if embeddings are corrupted
        fallback = await _text_search_fallback(memories, query, limit, min_relevance, start_time)
        fallback["warnings"] = warnings + fallback.get("warnings", [])
        return fallback

    # Score and rank
    results = []
    for (memory, _), similarity in zip(memory_embeddings, similarities):
        # Apply confidence decay
        decayed_confidence = calculate_confidence_decay(
            memory.confidence,
            memory.createdAt,
            memory.lastAccessedAt,
        )

        # Improved relevance scoring:
        # - Semantic similarity is the PRIMARY signal (weight: 70%)
        # - Confidence acts as a MINOR adjustment (weight: 30%)
        # This prevents old but highly relevant memories from being penalized too much
        relevance = (similarity * 0.7) + (similarity * decayed_confidence * 0.3)

        # Boost for high term overlap (near-exact matches)
        # This fixes low scores for quasi-exact query matches
        query_terms = set(query.lower().split())
        content_terms = set(memory.content.lower().split())
        if query_terms:
            term_overlap = len(query_terms & content_terms) / len(query_terms)
            if term_overlap > 0.5:  # 50%+ terms match (lowered from 70%)
                # Boost factor: 1.0 at 50% overlap, up to 1.25 at 100% overlap
                boost = 1.0 + (term_overlap - 0.5) * 0.5
                relevance = min(relevance * boost, 1.0)

        relevance, ranking_boosts = _apply_recall_ranking_boost(relevance, query, memory)

        if relevance >= min_relevance:
            item = {
                "memory_id": memory.id,
                "content": memory.content,
                "type": memory.type.lower(),
                "scope": memory.scope.lower(),
                "category": memory.category,
                "status": getattr(memory, "status", MEMORY_STATUS_ACTIVE).lower(),
                "review_status": getattr(memory, "reviewStatus", MEMORY_REVIEW_APPROVED).lower(),
                "relevance": round(relevance, 4),
                "confidence": round(decayed_confidence, 4),
                "created_at": memory.createdAt.isoformat(),
                "last_accessed_at": memory.lastAccessedAt.isoformat()
                if memory.lastAccessedAt
                else None,
                "access_count": memory.accessCount,
            }
            if ranking_boosts:
                item["ranking_boosts"] = ranking_boosts
            results.append(item)

    # Sort by relevance
    results.sort(key=lambda x: x["relevance"], reverse=True)
    results = results[:limit]

    # Batch update access counts for returned memories
    if results:
        result_ids = [r["memory_id"] for r in results]
        try:
            await db.agentmemory.update_many(
                where={"id": {"in": result_ids}},
                data={"lastAccessedAt": datetime.now(UTC)},
            )
            # Note: update_many doesn't support increment, so we do a raw query
            # For now, skip accessCount increment to optimize latency
            # TODO: Use raw SQL for atomic increment if needed
        except Exception as e:
            logger.warning(f"Failed to batch update access counts: {e}")

    return {
        "memories": results,
        "warnings": warnings,
        "total_searched": len(memories),
        "query": query,
        "timing_ms": int((time.time() - start_time) * 1000),
    }


async def _text_search_fallback(
    memories: list,
    query: str,
    limit: int,
    min_relevance: float,
    start_time: float,
) -> dict[str, Any]:
    """Fallback to text search if embedding fails.

    Uses simple keyword matching as a degraded mode.
    """
    import time

    memories, filtered_sensitive_count = _filter_sensitive_memories(memories)
    warnings = ["sensitive_memory_filtered"] if filtered_sensitive_count else []
    query_terms = set(query.lower().split())
    results = []

    for memory in memories:
        content_terms = set(memory.content.lower().split())
        overlap = len(query_terms & content_terms)

        if overlap > 0:
            # Simple relevance based on term overlap
            relevance = overlap / max(len(query_terms), 1)

            decayed_confidence = calculate_confidence_decay(
                memory.confidence,
                memory.createdAt,
                memory.lastAccessedAt,
            )
            final_relevance = relevance * decayed_confidence
            final_relevance, ranking_boosts = _apply_recall_ranking_boost(
                final_relevance,
                query,
                memory,
            )

            if final_relevance >= min_relevance:
                item = {
                    "memory_id": memory.id,
                    "content": memory.content,
                    "type": _enum_lower(memory.type),
                    "scope": _enum_lower(memory.scope),
                    "category": memory.category,
                    "status": _enum_lower(getattr(memory, "status", MEMORY_STATUS_ACTIVE)),
                    "review_status": getattr(
                        memory, "reviewStatus", MEMORY_REVIEW_APPROVED
                    ).lower(),
                    "relevance": round(final_relevance, 4),
                    "confidence": round(decayed_confidence, 4),
                    "created_at": memory.createdAt.isoformat(),
                    "last_accessed_at": memory.lastAccessedAt.isoformat()
                    if memory.lastAccessedAt
                    else None,
                    "access_count": getattr(memory, "accessCount", 0),
                }
                if ranking_boosts:
                    item["ranking_boosts"] = ranking_boosts
                results.append(item)

    results.sort(key=lambda x: x["relevance"], reverse=True)
    results = results[:limit]

    return {
        "memories": results,
        "warnings": warnings,
        "total_searched": len(memories),
        "query": query,
        "timing_ms": int((time.time() - start_time) * 1000),
    }


async def _list_memories_v2(
    project_id: str,
    memory_type: str | None = None,
    scope: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
    include_expired: bool = False,
    include_inactive: bool = False,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """List Memory V2 rows with explicit owner boundaries."""
    db = await get_db()
    resolved_team_id = await _resolve_project_team_id(project_id, team_id, db)
    normalized_scope = _normalize_memory_scope(scope) if scope else None
    owner_error = (
        get_memory_scope_owner_error(
            normalized_scope,
            user_id=user_id,
            team_id=resolved_team_id,
            agent_id=agent_id,
        )
        if normalized_scope
        else None
    )
    if owner_error:
        return {"memories": [], "total_count": 0, "has_more": False, "error": owner_error}

    where = _build_memory_v2_where(
        project_id=project_id,
        scope=normalized_scope,
        user_id=user_id,
        team_id=resolved_team_id,
        agent_id=agent_id,
        memory_type=_normalize_memory_type(memory_type) if memory_type else None,
        category=category,
        include_expired=include_expired,
        include_inactive=include_inactive,
    )
    if where is None:
        return {"memories": [], "total_count": 0, "has_more": False}

    if search:
        where = {"AND": [where, {"content": {"contains": search, "mode": "insensitive"}}]}

    sort_field_map = {
        "created_at": "createdAt",
        "confidence": "confidence",
        "last_accessed": "lastAccessedAt",
        "expires_at": "validUntil",
    }
    sort_field = sort_field_map.get(sort_by, "createdAt")
    order_direction = "asc" if sort_order == "asc" else "desc"

    total_count = await db.memory.count(where=where)
    memories = await db.memory.find_many(
        where=where,
        order={sort_field: order_direction},
        skip=offset,
        take=limit,
    )
    memories, filtered_sensitive_count = _filter_sensitive_memories(memories)

    return {
        "memories": [
            {
                "memory_id": memory.id,
                "content": memory.content,
                "type": _enum_lower(memory.type),
                "scope": _enum_lower(memory.scope),
                "category": memory.category,
                "status": _enum_lower(memory.status),
                "confidence": round(
                    calculate_confidence_decay(
                        memory.confidence,
                        memory.createdAt,
                        memory.lastAccessedAt,
                    ),
                    4,
                ),
                "source": _enum_lower(memory.source),
                "owner": {
                    "project_id": getattr(memory, "projectId", None),
                    "team_id": getattr(memory, "teamId", None),
                    "user_id": getattr(memory, "userId", None),
                    "agent_id": getattr(memory, "agentId", None),
                },
                "created_at": memory.createdAt.isoformat(),
                "expires_at": memory.validUntil.isoformat() if memory.validUntil else None,
                "access_count": 0,
            }
            for memory in memories
        ],
        "total_count": total_count,
        "warnings": ["sensitive_memory_filtered"] if filtered_sensitive_count else [],
        "filtered_sensitive_count": filtered_sensitive_count,
        "has_more": (offset + limit) < total_count,
    }


async def list_memories(
    project_id: str,
    memory_type: str | None = None,
    scope: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
    include_expired: bool = False,
    include_pending: bool = False,
    include_rejected: bool = False,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    status: str | None = None,
    include_inactive: bool = False,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """List memories with optional filters and sorting.

    Args:
        project_id: The project ID
        memory_type: Filter by type
        scope: Filter by scope
        category: Filter by category
        search: Text search in content
        limit: Maximum memories to return
        offset: Pagination offset
        include_expired: Include expired memories
        sort_by: Field to sort by (created_at, confidence, access_count, last_accessed, expires_at)
        sort_order: Sort direction (asc, desc)

    Returns:
        Dict with memories list and pagination info
    """
    if settings.memory_v2_primary_read is True or settings.memory_v2_dual_read is True:
        v2_result = await _list_memories_v2(
            project_id=project_id,
            memory_type=memory_type,
            scope=scope,
            category=category,
            search=search,
            limit=limit,
            offset=offset,
            include_expired=include_expired,
            include_inactive=include_inactive or bool(status),
            sort_by=sort_by,
            sort_order=sort_order,
            user_id=user_id,
            team_id=team_id,
            agent_id=agent_id,
        )
        if settings.memory_v2_primary_read is True or v2_result.get("memories"):
            return v2_result

    # Build filter
    where: dict[str, Any] = {"projectId": project_id}
    _apply_review_status_filter(
        where,
        include_pending=include_pending,
        include_rejected=include_rejected,
    )
    if memory_type:
        normalized_memory_type = _normalize_memory_type(memory_type)
        where["type"] = normalized_memory_type.value.upper()
    if scope:
        normalized_scope = _normalize_memory_scope(scope)
        where["scope"] = normalized_scope.value.upper()
    if category:
        where["category"] = category
    if search:
        where["content"] = {"contains": search, "mode": "insensitive"}
    if status:
        where["status"] = status
    elif not include_inactive:
        where["status"] = MEMORY_STATUS_ACTIVE
    if not include_expired:
        where["OR"] = [
            {"expiresAt": None},
            {"expiresAt": {"gt": datetime.now(UTC)}},
        ]

    db = await get_db()

    # Map sort_by to Prisma field names
    sort_field_map = {
        "created_at": "createdAt",
        "confidence": "confidence",
        "access_count": "accessCount",
        "last_accessed": "lastAccessedAt",
        "expires_at": "expiresAt",
    }
    sort_field = sort_field_map.get(sort_by, "createdAt")
    order_direction = "asc" if sort_order == "asc" else "desc"

    # Count total
    total_count = await db.agentmemory.count(where=where)

    # Get memories
    memories = await db.agentmemory.find_many(
        where=where,
        order={sort_field: order_direction},
        skip=offset,
        take=limit,
    )
    memories, filtered_sensitive_count = _filter_sensitive_memories(memories)

    results = []
    for memory in memories:
        decayed_confidence = calculate_confidence_decay(
            memory.confidence,
            memory.createdAt,
            memory.lastAccessedAt,
        )

        results.append(
            {
                "memory_id": memory.id,
                "content": memory.content,
                "type": memory.type.lower(),
                "scope": memory.scope.lower(),
                "category": memory.category,
                "review_status": getattr(memory, "reviewStatus", MEMORY_REVIEW_APPROVED).lower(),
                "confidence": round(decayed_confidence, 4),
                "source": memory.source,
                "created_at": memory.createdAt.isoformat(),
                "expires_at": memory.expiresAt.isoformat() if memory.expiresAt else None,
                "access_count": memory.accessCount,
            }
        )

    return {
        "memories": results,
        "total_count": total_count,
        "warnings": ["sensitive_memory_filtered"] if filtered_sensitive_count else [],
        "filtered_sensitive_count": filtered_sensitive_count,
        "has_more": (offset + limit) < total_count,
    }


def _isoformat_or_none(value: Any) -> str | None:
    """Return an ISO timestamp for datetime-like values."""
    return value.isoformat() if value else None


def _format_memory_v2_evidence(memory: Any) -> list[dict[str, Any]]:
    """Format Memory V2 evidence links for review queue output."""
    evidence_links = getattr(memory, "evidenceLinks", None) or []
    return [
        {
            "evidence_type": _enum_lower(getattr(link, "evidenceType", "")),
            "document_id": getattr(link, "documentId", None),
            "chunk_id": getattr(link, "chunkId", None),
            "external_ref": getattr(link, "externalRef", None),
            "snippet": getattr(link, "snippet", None),
            "line_start": getattr(link, "lineStart", None),
            "line_end": getattr(link, "lineEnd", None),
            "weight": getattr(link, "weight", None),
        }
        for link in evidence_links
    ]


def _format_legacy_evidence(memory: Any) -> list[dict[str, Any]]:
    """Format legacy document refs as evidence-like links."""
    document_refs = getattr(memory, "documentRefs", None) or []
    return [
        {
            "evidence_type": "document",
            "document_id": None,
            "chunk_id": None,
            "external_ref": document_ref,
            "snippet": None,
            "line_start": None,
            "line_end": None,
            "weight": 1.0,
        }
        for document_ref in document_refs
    ]


def _format_memory_v2_queue_item(memory: Any, include_evidence: bool) -> dict[str, Any]:
    """Format a Memory V2 row as a review queue item."""
    status = _enum_lower(getattr(memory, "status", MemoryStatus.CANDIDATE.value))
    review_status = _review_status_for_memory_v2_status(status)
    created_at = getattr(memory, "createdAt", None)
    last_accessed_at = getattr(memory, "lastAccessedAt", None)
    confidence = calculate_confidence_decay(
        getattr(memory, "confidence", 1.0),
        created_at,
        last_accessed_at,
    )
    item = {
        "memory_id": memory.id,
        "backend": "memory_v2",
        "content": memory.content,
        "type": _enum_lower(getattr(memory, "type", "fact")),
        "scope": _enum_lower(getattr(memory, "scope", "project")),
        "category": getattr(memory, "category", None),
        "source": _enum_lower(getattr(memory, "source", "")),
        "status": status,
        "review_status": review_status.lower(),
        "needs_review_reason": _memory_queue_reason(status, review_status),
        "confidence": round(confidence, 4),
        "created_at": _isoformat_or_none(created_at),
        "updated_at": _isoformat_or_none(getattr(memory, "updatedAt", None)),
        "valid_until": _isoformat_or_none(getattr(memory, "validUntil", None)),
        "stale_at": _isoformat_or_none(getattr(memory, "staleAt", None)),
        "archived_at": _isoformat_or_none(getattr(memory, "archivedAt", None)),
        "owner": {
            "project_id": getattr(memory, "projectId", None),
            "team_id": getattr(memory, "teamId", None),
            "user_id": getattr(memory, "userId", None),
            "agent_id": getattr(memory, "agentId", None),
        },
    }
    if include_evidence:
        item["evidence"] = _format_memory_v2_evidence(memory)
    return item


def _format_legacy_queue_item(memory: Any, include_evidence: bool) -> dict[str, Any]:
    """Format a legacy AgentMemory row as a review queue item."""
    review_status = str(
        getattr(memory, "reviewStatus", MEMORY_REVIEW_APPROVED) or MEMORY_REVIEW_APPROVED
    )
    status = _enum_lower(getattr(memory, "status", MEMORY_STATUS_ACTIVE))
    created_at = getattr(memory, "createdAt", None)
    last_accessed_at = getattr(memory, "lastAccessedAt", None)
    confidence = calculate_confidence_decay(
        getattr(memory, "confidence", 1.0),
        created_at,
        last_accessed_at,
    )
    item = {
        "memory_id": memory.id,
        "backend": "agent_memory",
        "content": memory.content,
        "type": _enum_lower(getattr(memory, "type", "fact")),
        "scope": _enum_lower(getattr(memory, "scope", "project")),
        "category": getattr(memory, "category", None),
        "source": getattr(memory, "source", None),
        "status": status,
        "review_status": review_status.lower(),
        "review_notes": getattr(memory, "reviewNotes", None),
        "needs_review_reason": _memory_queue_reason(status, review_status),
        "confidence": round(confidence, 4),
        "created_at": _isoformat_or_none(created_at),
        "updated_at": _isoformat_or_none(getattr(memory, "updatedAt", None)),
        "reviewed_at": _isoformat_or_none(getattr(memory, "reviewedAt", None)),
        "expires_at": _isoformat_or_none(getattr(memory, "expiresAt", None)),
        "access_count": getattr(memory, "accessCount", 0),
        "owner": {
            "project_id": getattr(memory, "projectId", None),
            "team_id": None,
            "user_id": None,
            "agent_id": None,
        },
    }
    if include_evidence:
        item["evidence"] = _format_legacy_evidence(memory)
    return item


async def list_memory_review_queue(
    project_id: str,
    status: str = "candidate",
    memory_type: str | None = None,
    scope: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    include_evidence: bool = True,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """List reviewable Memory V2 and legacy AgentMemory rows without mutating them."""
    normalized_status = _normalize_review_queue_status(status)
    normalized_memory_type = _normalize_memory_type(memory_type) if memory_type else None
    normalized_scope = _normalize_memory_scope(scope) if scope else None
    limit = max(1, min(int(limit or 50), 100))
    offset = max(0, int(offset or 0))
    db = await get_db()
    resolved_team_id = await _resolve_project_team_id(project_id, team_id, db)
    owner_error = (
        get_memory_scope_owner_error(
            normalized_scope,
            user_id=user_id,
            team_id=resolved_team_id,
            agent_id=agent_id,
        )
        if normalized_scope
        else None
    )
    if owner_error:
        return {
            "project_id": project_id,
            "status": normalized_status,
            "items": [],
            "total_count": 0,
            "has_more": False,
            "mutated": False,
            "error": owner_error,
        }

    items: list[dict[str, Any]] = []
    total_count = 0
    warnings: list[str] = []

    v2_statuses = _queue_status_to_memory_v2_statuses(normalized_status)
    v2_where = _build_memory_v2_where(
        project_id=project_id,
        scope=normalized_scope,
        user_id=user_id,
        team_id=resolved_team_id,
        agent_id=agent_id,
        memory_type=normalized_memory_type,
        category=category,
        include_expired=True,
        include_inactive=True,
    )
    if v2_where is not None:
        v2_clauses: list[dict[str, Any]] = [v2_where]
        if v2_statuses is not None:
            v2_clauses.append(
                {"status": v2_statuses[0] if len(v2_statuses) == 1 else {"in": v2_statuses}}
            )
        if search:
            v2_clauses.append({"content": {"contains": search, "mode": "insensitive"}})
        v2_where = {"AND": v2_clauses} if len(v2_clauses) > 1 else v2_clauses[0]
        try:
            total_count += await db.memory.count(where=v2_where)
            find_many_kwargs: dict[str, Any] = {
                "where": v2_where,
                "order": {"createdAt": "desc"},
                "skip": offset,
                "take": limit,
            }
            if include_evidence:
                find_many_kwargs["include"] = {"evidenceLinks": True}
            v2_rows = await db.memory.find_many(**find_many_kwargs)
            v2_rows, filtered_sensitive_count = _filter_sensitive_memories(v2_rows)
            if filtered_sensitive_count:
                warnings.append("sensitive_memory_filtered")
            items.extend(_format_memory_v2_queue_item(row, include_evidence) for row in v2_rows)
        except Exception as exc:
            logger.warning("Failed to read Memory V2 review queue: %s", exc)
            warnings.append("memory_v2_review_queue_unavailable")

    legacy_where: dict[str, Any] = {"projectId": project_id}
    legacy_where.update(_queue_status_to_legacy_filter(normalized_status))
    if normalized_memory_type:
        legacy_where["type"] = normalized_memory_type.value.upper()
    if normalized_scope:
        legacy_where["scope"] = normalized_scope.value.upper()
    if category:
        legacy_where["category"] = category
    if search:
        legacy_where["content"] = {"contains": search, "mode": "insensitive"}
    try:
        legacy_total = await db.agentmemory.count(where=legacy_where)
        total_count += legacy_total
        legacy_limit = max(limit - len(items), 0)
        if legacy_limit:
            legacy_rows = await db.agentmemory.find_many(
                where=legacy_where,
                order={"createdAt": "desc"},
                skip=offset if not items else 0,
                take=legacy_limit,
            )
            legacy_rows, filtered_sensitive_count = _filter_sensitive_memories(legacy_rows)
            if filtered_sensitive_count:
                warnings.append("sensitive_memory_filtered")
            items.extend(_format_legacy_queue_item(row, include_evidence) for row in legacy_rows)
    except Exception as exc:
        logger.warning("Failed to read legacy memory review queue: %s", exc)
        warnings.append("legacy_review_queue_unavailable")

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    items = items[:limit]
    return {
        "project_id": project_id,
        "status": normalized_status,
        "generated_at": datetime.now(UTC).isoformat(),
        "items": items,
        "total_count": total_count,
        "has_more": (offset + limit) < total_count,
        "warnings": sorted(set(warnings)),
        "mutated": False,
    }


def _normalize_review_queue_action(action: str | None) -> str:
    """Normalize queue resolution action aliases."""
    normalized = str(action or "").strip().lower()
    aliases = {"approve": "accept"}
    normalized = aliases.get(normalized, normalized)
    allowed = {"accept", "reject", "archive", "invalidate", "merge", "supersede"}
    if normalized not in allowed:
        allowed_text = ", ".join(sorted(allowed | set(aliases)))
        raise ValueError(
            f"Invalid parameter 'action': unsupported queue action '{action}'. "
            f"Expected one of: {allowed_text}"
        )
    return normalized


async def _update_legacy_review_queue_item(
    db: Any,
    *,
    project_id: str | None,
    memory_id: str,
    action: str,
    reviewed_by: str | None,
    reviewed_at: datetime,
    notes: str | None,
    target_memory_id: str | None = None,
) -> dict[str, Any]:
    """Apply a review queue action to a legacy AgentMemory row if it exists."""
    where: dict[str, Any] = {"id": memory_id}
    if project_id:
        where["projectId"] = project_id
    legacy = await db.agentmemory.find_first(where=where)
    if legacy is None:
        return {"updated": False, "count": 0}

    data: dict[str, Any] = {
        "reviewedAt": reviewed_at,
        "reviewedBy": reviewed_by,
    }
    if notes is not None:
        data["reviewNotes"] = notes
    if action == "accept":
        data["reviewStatus"] = MEMORY_REVIEW_APPROVED
        data["status"] = MEMORY_STATUS_ACTIVE
    elif action == "archive":
        data["reviewStatus"] = MEMORY_REVIEW_REJECTED
        data["status"] = MemoryStatus.ARCHIVED.value
    elif action in {"reject", "invalidate"}:
        data["reviewStatus"] = MEMORY_REVIEW_REJECTED
        data["status"] = MEMORY_STATUS_INVALIDATED
        data["invalidatedAt"] = reviewed_at
        if notes is not None:
            data["invalidatedReason"] = notes
    elif action in {"merge", "supersede"}:
        data["reviewStatus"] = MEMORY_REVIEW_REJECTED
        data["status"] = MEMORY_STATUS_SUPERSEDED
        data["supersededByMemoryId"] = target_memory_id
        if notes is not None:
            data["invalidatedReason"] = notes

    result = await db.agentmemory.update_many(where=where, data=data)
    return {"updated": getattr(result, "count", 0) > 0, "count": getattr(result, "count", 0)}


async def resolve_memory_review_queue_item(
    project_id: str,
    memory_id: str,
    action: str,
    target_memory_id: str | None = None,
    notes: str | None = None,
    reviewed_by: str | None = None,
) -> dict[str, Any]:
    """Resolve one Memory V2 or legacy AgentMemory review queue item."""
    if not memory_id:
        raise ValueError("memory_id is required")

    normalized_action = _normalize_review_queue_action(action)
    if normalized_action in {"merge", "supersede"} and not target_memory_id:
        return {
            "error": f"target_memory_id is required for action '{normalized_action}'",
            "memory_id": memory_id,
            "action": normalized_action,
            "mutated": False,
        }

    if normalized_action in {"merge", "supersede"}:
        supersede_result = await supersede_memory_v2(
            memory_id,
            target_memory_id or "",
            reason=notes,
        )
        if supersede_result.get("error"):
            supersede_result["mutated"] = False
            return supersede_result
        db = await get_db()
        legacy_result = await _update_legacy_review_queue_item(
            db,
            project_id=project_id,
            memory_id=memory_id,
            action=normalized_action,
            reviewed_by=reviewed_by,
            reviewed_at=datetime.now(UTC),
            notes=notes,
            target_memory_id=target_memory_id,
        )
        return {
            **supersede_result,
            "action": normalized_action,
            "target_memory_id": target_memory_id,
            "legacy_updated": legacy_result["updated"],
            "mutated": True,
        }

    reviewed_at = datetime.now(UTC)
    resolved_v2_id = await _resolve_memory_v2_id(memory_id)
    db = await get_db()
    v2_updated = False
    if resolved_v2_id is not None:
        memory = await db.memory.find_unique(where={"id": resolved_v2_id})
        if memory is None:
            resolved_v2_id = None
        elif project_id and getattr(memory, "projectId", project_id) != project_id:
            return {
                "error": f"Memory '{memory_id}' not found in project '{project_id}'",
                "memory_id": memory_id,
                "action": normalized_action,
                "mutated": False,
            }
        else:
            if normalized_action == "accept":
                payload = MemoryUpdatePayload(
                    status=MemoryStatus.ACTIVE,
                    reviewed_by=reviewed_by,
                )
            elif normalized_action == "archive":
                payload = MemoryUpdatePayload(
                    status=MemoryStatus.ARCHIVED,
                    reviewed_by=reviewed_by,
                    archived_at=reviewed_at,
                )
            else:
                payload = MemoryUpdatePayload(
                    status=MemoryStatus.INVALIDATED,
                    reviewed_by=reviewed_by,
                    valid_until=reviewed_at,
                )
            await _memory_repository.update_memory(resolved_v2_id, payload)
            v2_updated = True

    legacy_result = await _update_legacy_review_queue_item(
        db,
        project_id=project_id,
        memory_id=memory_id,
        action=normalized_action,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        notes=notes,
    )

    if not v2_updated and not legacy_result["updated"]:
        return {
            "error": f"Memory '{memory_id}' not found",
            "memory_id": memory_id,
            "action": normalized_action,
            "mutated": False,
        }

    lifecycle_status = {
        "accept": MemoryStatus.ACTIVE.value,
        "archive": MemoryStatus.ARCHIVED.value,
        "reject": MemoryStatus.INVALIDATED.value,
        "invalidate": MemoryStatus.INVALIDATED.value,
    }[normalized_action]
    review_status = _review_status_for_memory_v2_status(lifecycle_status)
    return {
        "memory_id": memory_id,
        "resolved_memory_id": resolved_v2_id,
        "action": normalized_action,
        "status": lifecycle_status.lower(),
        "review_status": review_status.lower(),
        "reviewed_at": reviewed_at.isoformat(),
        "reviewed_by": reviewed_by,
        "notes": notes,
        "memory_v2_updated": v2_updated,
        "legacy_updated": legacy_result["updated"],
        "mutated": True,
    }


async def get_memory_health(
    project_id: str,
    scope: str | None = None,
    include_inactive: bool = False,
    sample_limit: int = 5,
) -> dict[str, Any]:
    """Return read-only memory hygiene counters and anomaly samples for a project."""
    db = await get_db()
    normalized_scope = _normalize_memory_scope(scope) if scope else None
    sample_limit = max(0, min(int(sample_limit or 0), 20))
    now = datetime.now(UTC)

    where: dict[str, Any] = {
        "projectId": project_id,
        "reviewStatus": MEMORY_REVIEW_APPROVED,
    }
    if normalized_scope:
        where["scope"] = normalized_scope.value.upper()
    if not include_inactive:
        where["status"] = MEMORY_STATUS_ACTIVE
        where["OR"] = [
            {"expiresAt": None},
            {"expiresAt": {"gt": now}},
        ]

    memories = await db.agentmemory.find_many(
        where=where,
        order={"createdAt": "desc"},
        take=5000,
    )

    by_status: Counter[str] = Counter()
    by_scope: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    by_tier: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    hygiene_by_reason: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []

    for memory in memories:
        status = _enum_lower(getattr(memory, "status", "") or MEMORY_STATUS_ACTIVE)
        scope_name = _enum_lower(getattr(memory, "scope", "") or "project")
        type_name = _enum_lower(getattr(memory, "type", "") or "fact")
        tier = _enum_lower(getattr(memory, "tier", "") or "daily")
        category = str(getattr(memory, "category", "") or "uncategorized")

        by_status[status] += 1
        by_scope[scope_name] += 1
        by_type[type_name] += 1
        by_tier[tier] += 1
        by_category[category] += 1

        reason = _classify_low_signal_memory(memory)
        if reason is None and ":superseded" in category.lower() and status == "active":
            reason = "active_superseded_category"

        if reason:
            hygiene_by_reason[reason] += 1
            if len(samples) < sample_limit:
                samples.append(_memory_health_sample(memory, reason))

    top_categories = [
        {"category": category, "count": count} for category, count in by_category.most_common(10)
    ]
    hygiene_counts = dict(sorted(hygiene_by_reason.items()))
    warnings = []
    if hygiene_counts:
        warnings.append("active_hygiene_anomalies_detected")
    if len(memories) >= 5000:
        warnings.append("health_scan_capped_at_5000_rows")

    return {
        "project_id": project_id,
        "scope": normalized_scope.value if normalized_scope else "all",
        "include_inactive": include_inactive,
        "generated_at": now.isoformat(),
        "row_limit": 5000,
        "total_scanned": len(memories),
        "auto_compact": {
            "threshold": AUTO_COMPACT_THRESHOLD,
            "cooldown_seconds": AUTO_COMPACT_COOLDOWN,
            "would_trigger_by_count": len(memories) >= AUTO_COMPACT_THRESHOLD,
        },
        "counts": {
            "by_status": dict(sorted(by_status.items())),
            "by_scope": dict(sorted(by_scope.items())),
            "by_type": dict(sorted(by_type.items())),
            "by_tier": dict(sorted(by_tier.items())),
            "top_categories": top_categories,
        },
        "hygiene": {
            "anomaly_count": sum(hygiene_by_reason.values()),
            "by_reason": hygiene_counts,
            "samples": samples,
        },
        "warnings": warnings,
    }


def _memory_candidate_sample(memory: Any, reason: str | None = None) -> dict[str, Any]:
    """Return a compact read-only memory candidate for hygiene tools."""
    sample = _memory_health_sample(memory, reason or "candidate")
    sample["review_status"] = str(
        getattr(memory, "reviewStatus", MEMORY_REVIEW_APPROVED) or MEMORY_REVIEW_APPROVED
    ).lower()
    sample["confidence"] = round(float(getattr(memory, "confidence", 0.0) or 0.0), 4)
    return sample


def _normalized_memory_signature(content: str) -> str:
    """Normalize content for deterministic duplicate grouping."""
    lowered = str(content or "").lower()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9 ]+", "", lowered)
    return lowered.strip()


def _lexical_similarity(left: str, right: str) -> float:
    left_terms = set(re.findall(r"[a-z0-9]+", left.lower()))
    right_terms = set(re.findall(r"[a-z0-9]+", right.lower()))
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / len(left_terms | right_terms)


def _build_duplicate_candidate_groups(
    memories: list[Any],
    *,
    min_similarity: float = 0.9,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Build read-only duplicate groups with a suggested newest-memory winner."""
    groups: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    signature_groups: dict[tuple[str, str, str], list[Any]] = {}

    for memory in memories:
        signature = _normalized_memory_signature(getattr(memory, "content", ""))
        if len(signature) < 24:
            continue
        key = (
            _enum_upper(getattr(memory, "type", "")),
            str(getattr(memory, "category", "") or ""),
            signature,
        )
        signature_groups.setdefault(key, []).append(memory)

    for group_memories in signature_groups.values():
        if len(group_memories) < 2:
            continue
        for memory in group_memories:
            seen_ids.add(memory.id)
        newest = max(group_memories, key=lambda item: getattr(item, "createdAt", datetime.min))
        groups.append(
            {
                "reason": "exact_normalized_duplicate",
                "suggested_keep_memory_id": newest.id,
                "suggested_supersede_memory_ids": [
                    memory.id for memory in group_memories if memory.id != newest.id
                ],
                "similarity": 1.0,
                "memories": [
                    _memory_candidate_sample(memory, "duplicate") for memory in group_memories
                ],
            }
        )
        if len(groups) >= limit:
            return groups

    candidates = [memory for memory in memories if memory.id not in seen_ids]
    for index, left in enumerate(candidates):
        if len(groups) >= limit:
            break
        left_signature = _normalized_memory_signature(getattr(left, "content", ""))
        if len(left_signature) < 32:
            continue
        near_group = [left]
        for right in candidates[index + 1 :]:
            if right.id in seen_ids:
                continue
            if _enum_upper(getattr(left, "type", "")) != _enum_upper(getattr(right, "type", "")):
                continue
            if str(getattr(left, "category", "") or "") != str(
                getattr(right, "category", "") or ""
            ):
                continue
            similarity = _lexical_similarity(left_signature, getattr(right, "content", ""))
            if similarity >= min_similarity:
                near_group.append(right)
        if len(near_group) < 2:
            continue
        for memory in near_group:
            seen_ids.add(memory.id)
        newest = max(near_group, key=lambda item: getattr(item, "createdAt", datetime.min))
        groups.append(
            {
                "reason": "near_lexical_duplicate",
                "suggested_keep_memory_id": newest.id,
                "suggested_supersede_memory_ids": [
                    memory.id for memory in near_group if memory.id != newest.id
                ],
                "similarity": min_similarity,
                "memories": [
                    _memory_candidate_sample(memory, "duplicate") for memory in near_group
                ],
            }
        )

    return groups[:limit]


async def get_memory_duplicate_candidates(
    project_id: str,
    scope: str | None = None,
    include_inactive: bool = False,
    limit: int = 20,
    min_similarity: float = 0.9,
) -> dict[str, Any]:
    """Return read-only duplicate/supersession groups without mutating memory."""
    db = await get_db()
    normalized_scope = _normalize_memory_scope(scope) if scope else None
    now = datetime.now(UTC)
    where: dict[str, Any] = {
        "projectId": project_id,
        "reviewStatus": MEMORY_REVIEW_APPROVED,
    }
    if normalized_scope:
        where["scope"] = normalized_scope.value.upper()
    if not include_inactive:
        where["status"] = MEMORY_STATUS_ACTIVE
        where["OR"] = [{"expiresAt": None}, {"expiresAt": {"gt": now}}]

    memories = await db.agentmemory.find_many(where=where, order={"createdAt": "desc"}, take=5000)
    groups = _build_duplicate_candidate_groups(
        memories,
        min_similarity=max(0.0, min(float(min_similarity), 1.0)),
        limit=max(1, min(int(limit or 20), 100)),
    )
    return {
        "project_id": project_id,
        "scope": normalized_scope.value if normalized_scope else "all",
        "include_inactive": include_inactive,
        "generated_at": now.isoformat(),
        "total_scanned": len(memories),
        "group_count": len(groups),
        "groups": groups,
        "mutated": False,
    }


async def get_memory_clean_candidates(
    project_id: str,
    scope: str | None = None,
    include_inactive: bool = False,
    limit_per_bucket: int = 10,
) -> dict[str, Any]:
    """Return grouped read-only memory cleanup candidates."""
    db = await get_db()
    normalized_scope = _normalize_memory_scope(scope) if scope else None
    now = datetime.now(UTC)
    limit_per_bucket = max(1, min(int(limit_per_bucket or 10), 50))

    where: dict[str, Any] = {"projectId": project_id}
    if normalized_scope:
        where["scope"] = normalized_scope.value.upper()
    if not include_inactive:
        where["status"] = MEMORY_STATUS_ACTIVE

    memories = await db.agentmemory.find_many(where=where, order={"createdAt": "desc"}, take=5000)
    buckets: dict[str, list[Any]] = {
        "noise": [],
        "possibly_stale": [],
        "category_anomalies": [],
        "needs_human_review": [],
    }

    for memory in memories:
        status = _enum_lower(getattr(memory, "status", "") or MEMORY_STATUS_ACTIVE)
        category = str(getattr(memory, "category", "") or "")
        memory_type = _enum_upper(getattr(memory, "type", ""))
        review_status = str(
            getattr(memory, "reviewStatus", MEMORY_REVIEW_APPROVED) or MEMORY_REVIEW_APPROVED
        ).upper()
        expires_at = getattr(memory, "expiresAt", None)
        created_at = getattr(memory, "createdAt", None)
        low_signal_reason = _classify_low_signal_memory(memory)

        if low_signal_reason and len(buckets["noise"]) < limit_per_bucket:
            buckets["noise"].append(_memory_candidate_sample(memory, low_signal_reason))
        if (
            review_status == MEMORY_REVIEW_PENDING
            and len(buckets["needs_human_review"]) < limit_per_bucket
        ):
            buckets["needs_human_review"].append(_memory_candidate_sample(memory, "pending_review"))
        if (
            status == "active"
            and ":superseded" in category.lower()
            and len(buckets["category_anomalies"]) < limit_per_bucket
        ):
            buckets["category_anomalies"].append(
                _memory_candidate_sample(memory, "active_superseded_category")
            )
        if expires_at is not None and getattr(expires_at, "tzinfo", None) is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if created_at is not None and getattr(created_at, "tzinfo", None) is None:
            created_at = created_at.replace(tzinfo=UTC)
        is_expired = expires_at is not None and expires_at <= now
        is_stale_context = (
            memory_type in {"CONTEXT", "TODO"}
            and created_at is not None
            and created_at < now - timedelta(days=30)
        )
        if (is_expired or is_stale_context) and len(buckets["possibly_stale"]) < limit_per_bucket:
            buckets["possibly_stale"].append(
                _memory_candidate_sample(
                    memory,
                    "expired" if is_expired else "old_context_or_todo",
                )
            )

    duplicate_groups = _build_duplicate_candidate_groups(
        [
            memory
            for memory in memories
            if _enum_upper(getattr(memory, "reviewStatus", "")) != MEMORY_REVIEW_PENDING
        ],
        limit=limit_per_bucket,
    )
    result_buckets = {
        **buckets,
        "duplicates": duplicate_groups,
    }
    return {
        "project_id": project_id,
        "scope": normalized_scope.value if normalized_scope else "all",
        "include_inactive": include_inactive,
        "generated_at": now.isoformat(),
        "total_scanned": len(memories),
        "counts": {bucket: len(values) for bucket, values in result_buckets.items()},
        "candidates": result_buckets,
        "mutated": False,
    }


# ============ DAILY JOURNAL FUNCTIONS ============


async def append_journal(
    project_id: str,
    text: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Append an entry to today's journal.

    Journals are daily logs stored as CONTEXT memories with category="journal:YYYY-MM-DD".

    Args:
        project_id: The project ID
        text: Journal entry text (markdown supported)
        tags: Optional tags for categorization

    Returns:
        Dict with entry_id, date, and confirmation message
    """
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    category = f"journal:{today}"
    if settings.memory_v2_primary_read is True:
        result = await store_memory_v2(
            project_id=project_id,
            content=text,
            memory_type=AgentMemoryType.CONTEXT.value,
            scope=AgentMemoryScope.PROJECT.value,
            category=category,
            document_refs=tags,
            source="journal",
            review_status=MEMORY_REVIEW_APPROVED,
        )
        return {
            "entry_id": result["memory_id"],
            "date": today,
            "tags": tags,
            "message": f"Added journal entry for {today}",
        }

    db = await get_db()

    # Store as CONTEXT memory with journal category
    memory = await db.agentmemory.create(
        data={
            "projectId": project_id,
            "content": text,
            "type": "CONTEXT",
            "scope": "PROJECT",
            "category": category,
            "source": "journal",
            "confidence": 1.0,
            "accessCount": 0,
            "documentRefs": tags or [],  # Store tags in documentRefs field
            "reviewStatus": MEMORY_REVIEW_APPROVED,
        }
    )

    # Generate embedding for the entry
    try:
        embeddings_service = get_embeddings_service()
        embedding = await embeddings_service.embed_text_async(text)
        await _store_memory_embedding(memory.id, embedding)
    except Exception as e:
        logger.warning(f"Failed to generate embedding for journal entry {memory.id}: {e}")

    return {
        "entry_id": memory.id,
        "date": today,
        "tags": tags,
        "message": f"Added journal entry for {today}",
    }


async def get_journal(
    project_id: str,
    date: str | None = None,
    include_yesterday: bool = False,
) -> dict[str, Any]:
    """Get journal entries for a specific date.

    Args:
        project_id: The project ID
        date: Date in YYYY-MM-DD format (default: today)
        include_yesterday: Also include yesterday's entries

    Returns:
        Dict with date, entries list, and total count
    """
    db = await get_db()

    # Build list of categories to fetch
    categories = []
    target_date = date or datetime.now(UTC).strftime("%Y-%m-%d")
    categories.append(f"journal:{target_date}")

    if include_yesterday:
        # Parse target date and get yesterday
        try:
            target_dt = datetime.strptime(target_date, "%Y-%m-%d")
            yesterday = (target_dt - timedelta(days=1)).strftime("%Y-%m-%d")
            categories.append(f"journal:{yesterday}")
        except ValueError:
            pass  # Invalid date format, ignore yesterday

    if settings.memory_v2_primary_read is True:
        entries = await db.memory.find_many(
            where={
                "projectId": project_id,
                "type": "CONTEXT",
                "category": {"in": categories},
                "status": "ACTIVE",
            },
            order={"createdAt": "asc"},
            include={"evidenceLinks": True},
        )

        return {
            "date": target_date,
            "include_yesterday": include_yesterday,
            "entries": [
                {
                    "id": e.id,
                    "text": e.content,
                    "tags": [
                        link.externalRef
                        for link in getattr(e, "evidenceLinks", []) or []
                        if getattr(link, "externalRef", None)
                    ],
                    "created_at": e.createdAt.isoformat(),
                }
                for e in entries
            ],
            "total_entries": len(entries),
        }

    entries = await db.agentmemory.find_many(
        where={
            "projectId": project_id,
            "type": "CONTEXT",
            "category": {"in": categories},
            "reviewStatus": MEMORY_REVIEW_APPROVED,
        },
        order={"createdAt": "asc"},
    )

    return {
        "date": target_date,
        "include_yesterday": include_yesterday,
        "entries": [
            {
                "id": e.id,
                "text": e.content,
                "tags": e.documentRefs or [],
                "created_at": e.createdAt.isoformat(),
            }
            for e in entries
        ],
        "total_entries": len(entries),
    }


async def summarize_journal(
    project_id: str,
    date: str,
) -> dict[str, Any]:
    """Get journal entries for a date, ready for summarization.

    This returns all entries for a date so they can be summarized
    by an LLM before archival. The actual summarization should be
    done by the calling agent.

    Args:
        project_id: The project ID
        date: Date to summarize (YYYY-MM-DD)

    Returns:
        Dict with date, entries, combined content, and suggested prompt
    """
    # Get entries for the date
    journal = await get_journal(project_id, date, include_yesterday=False)

    if not journal["entries"]:
        return {
            "date": date,
            "entries": [],
            "combined_content": "",
            "entry_count": 0,
            "message": f"No journal entries found for {date}",
        }

    # Combine all entries into a single text
    combined = "\n\n---\n\n".join(
        [f"**{e['created_at'][:19]}**\n{e['text']}" for e in journal["entries"]]
    )

    return {
        "date": date,
        "entries": journal["entries"],
        "combined_content": combined,
        "entry_count": len(journal["entries"]),
        "suggested_prompt": f"Summarize the following {len(journal['entries'])} journal entries from {date} into a concise daily brief highlighting key decisions, learnings, and action items:",
    }


async def delete_memories(
    project_id: str,
    memory_id: str | None = None,
    memory_type: str | None = None,
    category: str | None = None,
    older_than_days: int | None = None,
) -> dict[str, Any]:
    """Delete memories matching criteria.

    Args:
        project_id: The project ID
        memory_id: Specific memory to delete
        memory_type: Delete all of this type
        category: Delete all in this category
        older_than_days: Delete memories older than N days

    Returns:
        Dict with deleted count and message
    """
    db = await get_db()
    # Build filter
    where: dict[str, Any] = {"projectId": project_id}

    if memory_id:
        if settings.memory_v2_primary_read is True:
            resolved_id = await _resolve_memory_v2_id(memory_id)
            if resolved_id is None:
                return {
                    "deleted_count": 0,
                    "message": f"Memory {memory_id} not found",
                }
            where["id"] = resolved_id
        else:
            where["id"] = memory_id
    if memory_type:
        normalized_memory_type = _normalize_memory_type(memory_type)
        where["type"] = normalized_memory_type.value.upper()
    if category:
        where["category"] = category
    if older_than_days:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        where["createdAt"] = {"lt": cutoff}

    if settings.memory_v2_primary_read is True:
        to_delete = await db.memory.find_many(where=where)
        memory_ids = [m.id for m in to_delete]
        result = await db.memory.delete_many(where=where)
        deleted_count = result

        for mid in memory_ids:
            await _delete_memory_embedding(mid)

        message = f"Deleted {deleted_count} memories"
        if memory_id:
            message = (
                f"Memory {memory_id} deleted"
                if deleted_count > 0
                else f"Memory {memory_id} not found"
            )

        return {
            "deleted_count": deleted_count,
            "message": message,
        }

    # Get IDs to delete embeddings
    to_delete = await db.agentmemory.find_many(where=where)
    memory_ids = [m.id for m in to_delete]

    # Delete memories
    result = await db.agentmemory.delete_many(where=where)
    deleted_count = result

    # Delete embeddings from Redis
    for mid in memory_ids:
        await _delete_memory_embedding(mid)

    message = f"Deleted {deleted_count} memories"
    if memory_id:
        message = (
            f"Memory {memory_id} deleted" if deleted_count > 0 else f"Memory {memory_id} not found"
        )

    return {
        "deleted_count": deleted_count,
        "message": message,
    }


async def invalidate_memory_v2(
    memory_id: str,
    invalidated_at: datetime | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Invalidate a Memory V2 record using a legacy or V2 memory ID."""

    target_time = invalidated_at or datetime.now(UTC)
    resolved_id = await _resolve_memory_v2_id(memory_id)
    if resolved_id is None:
        db = await get_db()
        legacy_result = await _invalidate_legacy_memory(
            db,
            memory_id=memory_id,
            invalidated_at=target_time,
            reason=reason,
        )
        if legacy_result is not None:
            return legacy_result

        return {
            "error": f"Memory '{memory_id}' not found in Memory V2",
            "memory_id": memory_id,
        }

    await _memory_repository.invalidate_memory(resolved_id, target_time)
    db = await get_db()
    legacy_result = await _invalidate_legacy_memory(
        db,
        memory_id=memory_id,
        invalidated_at=target_time,
        reason=reason,
    )

    return {
        "memory_id": resolved_id,
        "legacy_memory_id": memory_id if legacy_result is not None else None,
        "legacy_invalidated": legacy_result is not None,
        "invalidated": True,
        "invalidated_at": target_time.isoformat(),
        "reason": reason,
        "message": f"Memory '{resolved_id}' invalidated",
    }


async def attach_memory_source_v2(
    memory_id: str,
    evidence_type: str,
    document_id: str | None = None,
    chunk_id: str | None = None,
    external_ref: str | None = None,
    snippet: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    weight: float = 1.0,
) -> dict[str, Any]:
    """Attach evidence to a Memory V2 record using a legacy or V2 memory ID."""

    resolved_id = await _resolve_memory_v2_id(memory_id)
    if resolved_id is None:
        return {
            "error": f"Memory '{memory_id}' not found in Memory V2",
            "memory_id": memory_id,
        }

    await _memory_repository.attach_evidence(
        resolved_id,
        [
            MemoryEvidencePayload(
                evidence_type=evidence_type,
                document_id=document_id,
                chunk_id=chunk_id,
                external_ref=external_ref,
                snippet=snippet,
                line_start=line_start,
                line_end=line_end,
                weight=weight,
            )
        ],
    )
    return {
        "memory_id": resolved_id,
        "evidence_type": evidence_type,
        "created": True,
        "message": f"Attached {evidence_type} evidence to memory '{resolved_id}'",
    }


async def supersede_memory_v2(
    old_memory_id: str,
    new_memory_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Mark one V2 memory as superseded by another."""

    resolved_old_id = await _resolve_memory_v2_id(old_memory_id)
    resolved_new_id = await _resolve_memory_v2_id(new_memory_id)

    if resolved_old_id is None or resolved_new_id is None:
        db = await get_db()
        old_legacy = await db.agentmemory.find_unique(where={"id": old_memory_id})
        new_legacy = await db.agentmemory.find_unique(where={"id": new_memory_id})
        if old_legacy is not None and (new_legacy is not None or resolved_new_id is not None):
            supersede_result = await _mark_legacy_memory_superseded(
                db,
                old_memory_id=old_memory_id,
                new_memory_id=new_memory_id,
                reason=reason,
            )
            supersede_result["superseded"] = True
            supersede_result["message"] = (
                f"Legacy memory '{old_memory_id}' superseded by '{new_memory_id}'"
            )
            return supersede_result

    if resolved_old_id is None:
        return {
            "error": f"Memory '{old_memory_id}' not found in Memory V2",
            "memory_id": old_memory_id,
        }
    if resolved_new_id is None:
        return {
            "error": f"Memory '{new_memory_id}' not found in Memory V2",
            "memory_id": new_memory_id,
        }

    superseded_at = datetime.now(UTC)
    await _memory_repository.supersede_memory(resolved_old_id, resolved_new_id, superseded_at)
    return {
        "old_memory_id": resolved_old_id,
        "new_memory_id": resolved_new_id,
        "superseded": True,
        "superseded_at": superseded_at.isoformat(),
        "reason": reason,
        "message": f"Memory '{resolved_old_id}' superseded by '{resolved_new_id}'",
    }


async def verify_memory_v2(
    memory_id: str,
    mark_stale_if_missing: bool = True,
) -> dict[str, Any]:
    """Verify that a V2 memory still has valid supporting evidence."""

    resolved_id = await _resolve_memory_v2_id(memory_id)
    if resolved_id is None:
        return {"error": f"Memory '{memory_id}' not found in Memory V2", "memory_id": memory_id}
    memory = await _memory_repository.get_memory_with_evidence(resolved_id)
    if memory is None:
        return {"error": f"Memory '{memory_id}' not found in Memory V2", "memory_id": memory_id}

    db = await get_db()
    evidence_rows = list(getattr(memory, "evidenceLinks", []) or [])
    total = len(evidence_rows)
    valid = 0
    invalid = 0

    for evidence in evidence_rows:
        evidence_type = str(getattr(evidence, "evidenceType", ""))
        document_id = getattr(evidence, "documentId", None)
        chunk_id = getattr(evidence, "chunkId", None)
        external_ref = getattr(evidence, "externalRef", None)

        is_valid = False
        if evidence_type == "DOCUMENT":
            if document_id:
                is_valid = await db.document.find_unique(where={"id": document_id}) is not None
            elif external_ref and getattr(memory, "projectId", None):
                is_valid = (
                    await db.document.find_first(
                        where={
                            "projectId": memory.projectId,
                            "path": external_ref,
                            "deletedAt": None,
                        }
                    )
                ) is not None
        elif evidence_type == "CHUNK":
            if chunk_id:
                is_valid = await db.documentchunk.find_unique(where={"id": chunk_id}) is not None
        else:
            is_valid = bool(external_ref or getattr(evidence, "snippet", None))

        if is_valid:
            valid += 1
        else:
            invalid += 1

    evidence_score = (valid / total) if total > 0 else 0.0
    status = str(getattr(memory, "status", "ACTIVE"))

    update = MemoryUpdatePayload(evidence_score=evidence_score)
    if total > 0 and valid == 0 and mark_stale_if_missing and status == "ACTIVE":
        update.status = "STALE"
        update.stale_at = datetime.now(UTC)
        status = "STALE"

    await _memory_repository.update_memory(resolved_id, update)

    return {
        "memory_id": resolved_id,
        "verified": True,
        "total_evidence": total,
        "valid_evidence": valid,
        "invalid_evidence": invalid,
        "evidence_score": round(evidence_score, 4),
        "status": status,
        "message": f"Verified memory '{resolved_id}'",
    }


# ============ PHASE 20: MEMORY TIERS & COMPACTION ============


def normalize_memory_dates(content: str, reference_time: datetime) -> tuple[str, int]:
    """Convert relative dates in memory content to absolute dates.

    Uses the memory's creation time as reference (not current time) to accurately
    convert "yesterday" etc. to what was meant when the memory was stored.

    Args:
        content: Memory content string
        reference_time: The memory's creation time (used as reference for relative dates)

    Returns:
        Tuple of (normalized_content, count_of_replacements)
    """
    normalized = content
    replacement_count = 0

    # Ensure reference_time is timezone-aware
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)

    for pattern, replacer in DATE_PATTERNS:
        matches = list(re.finditer(pattern, normalized, re.IGNORECASE))
        for match in reversed(matches):  # Reverse to preserve indices
            try:
                groups = match.groups()
                if groups:
                    result_date = replacer(reference_time, *groups)
                else:
                    result_date = replacer(reference_time)

                # Format the replacement based on pattern type
                if "week" in pattern:
                    replacement = f"week of {result_date.strftime('%Y-%m-%d')}"
                elif "month" in pattern:
                    replacement = result_date.strftime("%Y-%m")
                elif "morning" in pattern:
                    replacement = f"{result_date.strftime('%Y-%m-%d')} morning"
                elif "recently" in pattern:
                    replacement = f"around {result_date.strftime('%Y-%m-%d')}"
                else:
                    replacement = result_date.strftime("%Y-%m-%d")

                normalized = normalized[: match.start()] + replacement + normalized[match.end() :]
                replacement_count += 1
            except Exception as e:
                logger.warning(f"Failed to normalize date pattern '{match.group()}': {e}")
                continue

    return normalized, replacement_count


async def validate_document_refs(
    document_refs: list[str],
    project_id: str,
) -> tuple[list[str], int]:
    """Validate document_refs against indexed documents.

    Args:
        document_refs: List of document paths to validate
        project_id: The project ID

    Returns:
        Tuple of (valid_refs, removed_count)
    """
    if not document_refs:
        return [], 0

    db = await get_db()

    # Get all indexed document paths for this project
    try:
        indexed_docs = await db.document.find_many(where={"projectId": project_id})
        indexed_paths = {doc.path for doc in indexed_docs}

        # Filter to only valid refs
        valid_refs = [ref for ref in document_refs if ref in indexed_paths]
        removed_count = len(document_refs) - len(valid_refs)

        return valid_refs, removed_count
    except Exception as e:
        logger.warning(f"Failed to validate document refs: {e}")
        return document_refs, 0  # Return original on error


async def find_semantic_conflicts(
    memories: list[Any],
    similarity_threshold: float = 0.85,
) -> list[tuple[Any, Any, float]]:
    """Find memory pairs that are semantically similar but not identical.

    These are potential conflicts (e.g., "user prefers React" vs "user prefers Vue").

    Args:
        memories: List of memory objects
        similarity_threshold: Minimum similarity to consider as conflict (0.85 = 85%)

    Returns:
        List of tuples: (older_memory, newer_memory, similarity_score)
    """
    if len(memories) < 2:
        return []

    embeddings_service = get_embeddings_service()
    conflicts: list[tuple[Any, Any, float]] = []

    # Get all memory IDs
    memory_ids = [m.id for m in memories]

    # Batch fetch cached embeddings
    cached_embeddings = await _get_memory_embeddings_batch(memory_ids)

    # Build list of memories with embeddings
    memories_with_embeddings: list[tuple[Any, list[float]]] = []

    for memory in memories:
        if memory.id in cached_embeddings:
            memories_with_embeddings.append((memory, cached_embeddings[memory.id]))
        else:
            # Generate embedding on the fly (limited to prevent timeout)
            if len(memories_with_embeddings) < 100:  # Limit on-the-fly generation
                try:
                    embedding = await embeddings_service.embed_text_async(memory.content)
                    await _store_memory_embedding(memory.id, embedding)
                    memories_with_embeddings.append((memory, embedding))
                except Exception as e:
                    logger.warning(
                        f"Failed to embed memory {memory.id} for conflict detection: {e}"
                    )

    if len(memories_with_embeddings) < 2:
        return []

    # Compare pairs of same-type memories
    for i, (m1, emb1) in enumerate(memories_with_embeddings):
        for j, (m2, emb2) in enumerate(memories_with_embeddings):
            if i >= j:
                continue  # Skip self and already-compared pairs

            # Only compare same-type memories (e.g., PREFERENCE vs PREFERENCE)
            if m1.type != m2.type:
                continue

            # Calculate similarity
            try:
                similarities = embeddings_service.cosine_similarity(emb1, [emb2])
                similarity = similarities[0] if similarities else 0
            except Exception as e:
                logger.warning(f"Failed to calculate similarity: {e}")
                continue

            # Check if similar but not identical (conflict zone: 0.85-0.98)
            if similarity_threshold <= similarity < 0.98:
                # Determine which is older
                m1_time = m1.createdAt or datetime.min.replace(tzinfo=UTC)
                m2_time = m2.createdAt or datetime.min.replace(tzinfo=UTC)

                if m1_time.tzinfo is None:
                    m1_time = m1_time.replace(tzinfo=UTC)
                if m2_time.tzinfo is None:
                    m2_time = m2_time.replace(tzinfo=UTC)

                if m1_time < m2_time:
                    conflicts.append((m1, m2, similarity))  # m1 is older
                else:
                    conflicts.append((m2, m1, similarity))  # m2 is older

    return conflicts


async def resolve_conflict(
    older: Any,
    newer: Any,
    similarity: float,
    strategy: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Resolve a conflict between two similar memories.

    Args:
        older: The older memory
        newer: The newer memory
        similarity: Similarity score between them
        strategy: Resolution strategy (newer, higher_confidence, merge, flag)
        dry_run: If True, don't apply changes

    Returns:
        Dict with resolution details
    """
    db = await get_db()

    if strategy == CONFLICT_STRATEGY_NEWER:
        # Archive the older one (newer wins by recency)
        if not dry_run:
            await db.agentmemory.update(
                where={"id": older.id},
                data={
                    "status": MEMORY_STATUS_SUPERSEDED,
                    "tier": "ARCHIVE",
                    "category": f"{older.category or 'uncategorized'}:superseded",
                    "invalidatedAt": datetime.now(UTC),
                    "invalidatedReason": "Superseded by memory compaction",
                    "supersededByMemoryId": newer.id,
                },
            )
        return {
            "action": "archived_older",
            "archived_id": older.id,
            "kept_id": newer.id,
            "similarity": round(similarity, 4),
            "reason": "Newer memory supersedes older similar memory",
        }

    elif strategy == CONFLICT_STRATEGY_HIGHER_CONFIDENCE:
        # Archive the lower confidence one
        older_conf = calculate_confidence_decay(
            older.confidence, older.createdAt, older.lastAccessedAt
        )
        newer_conf = calculate_confidence_decay(
            newer.confidence, newer.createdAt, newer.lastAccessedAt
        )

        if older_conf > newer_conf:
            to_archive, to_keep = newer, older
        else:
            to_archive, to_keep = older, newer

        if not dry_run:
            await db.agentmemory.update(
                where={"id": to_archive.id},
                data={
                    "status": MEMORY_STATUS_SUPERSEDED,
                    "tier": "ARCHIVE",
                    "category": f"{to_archive.category or 'uncategorized'}:superseded",
                    "invalidatedAt": datetime.now(UTC),
                    "invalidatedReason": "Superseded by memory compaction",
                    "supersededByMemoryId": to_keep.id,
                },
            )
        return {
            "action": "archived_lower_confidence",
            "archived_id": to_archive.id,
            "kept_id": to_keep.id,
            "similarity": round(similarity, 4),
            "reason": f"Kept memory with higher confidence ({to_keep.confidence:.2f} vs {to_archive.confidence:.2f})",
        }

    elif strategy == CONFLICT_STRATEGY_MERGE:
        # Merge content into newer, archive older
        merged_content = f"{newer.content}\n\n[Supersedes ({older.createdAt.strftime('%Y-%m-%d') if older.createdAt else 'unknown'}): {older.content[:100]}...]"

        if not dry_run:
            # Update newer with merged content
            await db.agentmemory.update(
                where={"id": newer.id},
                data={
                    "content": merged_content,
                    "relatedMemoryIds": [*newer.relatedMemoryIds, older.id],
                },
            )
            # Archive older
            await db.agentmemory.update(
                where={"id": older.id},
                data={
                    "status": MEMORY_STATUS_SUPERSEDED,
                    "tier": "ARCHIVE",
                    "category": f"{older.category or 'uncategorized'}:merged",
                    "invalidatedAt": datetime.now(UTC),
                    "invalidatedReason": "Merged by memory compaction",
                    "supersededByMemoryId": newer.id,
                },
            )
        return {
            "action": "merged",
            "kept_id": newer.id,
            "archived_id": older.id,
            "similarity": round(similarity, 4),
            "reason": "Merged older memory content into newer",
        }

    elif strategy == CONFLICT_STRATEGY_FLAG:
        # Mark both for manual review
        if not dry_run:
            for m in [older, newer]:
                current_category = m.category or "uncategorized"
                if ":needs_review" not in current_category:
                    await db.agentmemory.update(
                        where={"id": m.id},
                        data={"category": f"{current_category}:needs_review"},
                    )
        return {
            "action": "flagged",
            "flagged_ids": [older.id, newer.id],
            "similarity": round(similarity, 4),
            "reason": "Flagged both memories for manual review",
        }

    else:
        return {
            "action": "skipped",
            "reason": f"Unknown strategy: {strategy}",
        }


# Tier classification rules
TIER_TYPE_DEFAULTS = {
    "DECISION": "CRITICAL",
    "FACT": "CRITICAL",
    "LEARNING": "ARCHIVE",
    "PREFERENCE": "ARCHIVE",
    "TODO": "DAILY",
    "CONTEXT": "DAILY",
}

# Promotion thresholds
ACCESS_COUNT_THRESHOLD = 3  # Promote if accessed 3+ times
CONFIDENCE_THRESHOLD = 0.8  # Promote if confidence > 0.8
DAILY_RECENCY_DAYS = 7  # Daily tier keeps last 7 days


def classify_memory_tier(
    memory_type: str,
    access_count: int = 0,
    confidence: float = 1.0,
    created_at: datetime | None = None,
) -> str:
    """Determine the appropriate tier for a memory.

    Args:
        memory_type: Type of memory (FACT, DECISION, LEARNING, etc.)
        access_count: How many times memory has been accessed
        confidence: Current confidence score
        created_at: When memory was created

    Returns:
        Tier string: CRITICAL, DAILY, or ARCHIVE
    """
    # Default by type
    tier = TIER_TYPE_DEFAULTS.get(memory_type.upper(), "ARCHIVE")

    # Promote based on access patterns
    if access_count >= ACCESS_COUNT_THRESHOLD:
        tier = "CRITICAL"
    elif confidence >= CONFIDENCE_THRESHOLD:
        tier = "CRITICAL"

    # Daily tier for recent context
    if memory_type.upper() == "CONTEXT" and created_at:
        now = datetime.now(UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        days_old = (now - created_at).days
        if days_old <= DAILY_RECENCY_DAYS:
            tier = "DAILY"

    return tier


async def get_session_memories(
    project_id: str,
    max_critical_tokens: int = 8000,
    max_daily_tokens: int = 4000,
    include_yesterday: bool = True,
    user_id: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Get memories to inject on session start, organized by tier.

    Args:
        project_id: The project ID
        max_critical_tokens: Token budget for CRITICAL tier
        max_daily_tokens: Token budget for DAILY tier
        include_yesterday: Include yesterday's daily memories

    Returns:
        Dict with critical and daily memories, token counts
    """
    db = await get_db()
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    warnings: list[str] = []
    filtered_sensitive_total = 0

    def budget_memories(memories: list, max_tokens: int) -> list[dict]:
        result = []
        total_tokens = 0
        for m in memories:
            mem_tokens = len(m.content) // 4
            if total_tokens + mem_tokens > max_tokens:
                break
            result.append(
                {
                    "id": m.id,
                    "content": m.content,
                    "type": _enum_upper(m.type),
                    "scope": _enum_lower(getattr(m, "scope", "project")),
                    "category": m.category,
                    "review_status": getattr(m, "reviewStatus", MEMORY_REVIEW_APPROVED).lower(),
                    "owner": {
                        "project_id": getattr(m, "projectId", None),
                        "team_id": getattr(m, "teamId", None),
                        "user_id": getattr(m, "userId", None),
                        "agent_id": getattr(m, "agentId", None),
                    },
                    "confidence": calculate_confidence_decay(
                        m.confidence, m.createdAt, m.lastAccessedAt
                    ),
                    "created_at": m.createdAt.isoformat() if m.createdAt else None,
                }
            )
            total_tokens += mem_tokens
        return result

    def bootstrap_status(
        critical_content: list[dict[str, Any]],
        daily_content: list[dict[str, Any]],
        token_count: int,
    ) -> dict[str, Any]:
        injected = critical_content + daily_content
        scope_counts = Counter(str(memory.get("scope") or "unknown") for memory in injected)
        type_counts = Counter(str(memory.get("type") or "UNKNOWN").lower() for memory in injected)
        ages: list[int] = []
        for memory in injected:
            created_at = memory.get("created_at")
            if not created_at:
                continue
            try:
                created_dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=UTC)
                ages.append(max((now - created_dt).days, 0))
            except ValueError:
                continue
        return {
            "ran": True,
            "timestamp": now.isoformat(),
            "injected_memory_count": len(injected),
            "injected_profile_count": sum(
                1 for memory in injected if memory.get("category") == TENANT_PROFILE_CATEGORY
            ),
            "total_tokens": token_count,
            "scope_counts": dict(sorted(scope_counts.items())),
            "type_counts": dict(sorted(type_counts.items())),
            "freshness": {
                "newest_age_days": min(ages) if ages else None,
                "oldest_age_days": max(ages) if ages else None,
                "average_age_days": round(sum(ages) / len(ages), 2) if ages else None,
            },
            "injected": [
                {
                    "memory_id": memory.get("id"),
                    "type": str(memory.get("type") or "").lower(),
                    "scope": memory.get("scope"),
                    "category": memory.get("category"),
                    "created_at": memory.get("created_at"),
                }
                for memory in injected[:25]
            ],
        }

    if settings.memory_v2_primary_read is True or settings.memory_v2_dual_read is True:
        resolved_team_id = await _resolve_project_team_id(project_id, team_id, db)
        owner_conditions = _build_memory_v2_owner_conditions(
            project_id=project_id,
            scope=None,
            user_id=user_id,
            team_id=resolved_team_id,
            agent_id=agent_id,
        )
        valid_filter = {"OR": [{"validUntil": None}, {"validUntil": {"gt": now}}]}
        critical = await db.memory.find_many(
            where={
                "AND": [
                    {"OR": owner_conditions},
                    {"status": "ACTIVE"},
                    valid_filter,
                    {"type": {"in": ["FACT", "DECISION", "LEARNING", "PREFERENCE"]}},
                ]
            },
            order={"confidence": "desc"},
            take=200,
        )
        daily = await db.memory.find_many(
            where={
                "AND": [
                    {"OR": owner_conditions},
                    {"status": "ACTIVE"},
                    valid_filter,
                    {"createdAt": {"gte": yesterday if include_yesterday else today}},
                    {"type": {"in": ["TODO", "CONTEXT"]}},
                ]
            },
            order={"createdAt": "desc"},
            take=200,
        )
        critical, filtered_critical = _filter_sensitive_memories(critical)
        daily, filtered_daily = _filter_sensitive_memories(daily)
        filtered_sensitive_total += filtered_critical + filtered_daily
        if filtered_critical or filtered_daily:
            warnings.append("sensitive_memory_filtered")
        critical_content = budget_memories(critical, max_critical_tokens)
        daily_content = budget_memories(daily, max_daily_tokens)
        if settings.memory_v2_primary_read is True or critical_content or daily_content:
            critical_tokens = sum(len(m["content"]) // 4 for m in critical_content)
            daily_tokens = sum(len(m["content"]) // 4 for m in daily_content)
            return {
                "critical": {
                    "memories": critical_content,
                    "count": len(critical_content),
                    "tokens": critical_tokens,
                },
                "daily": {
                    "memories": daily_content,
                    "count": len(daily_content),
                    "tokens": daily_tokens,
                },
                "sources": {
                    "project": any(
                        m["scope"] == "project" for m in critical_content + daily_content
                    ),
                    "team": any(m["scope"] == "team" for m in critical_content + daily_content),
                    "user": any(m["scope"] == "user" for m in critical_content + daily_content),
                    "agent": any(m["scope"] == "agent" for m in critical_content + daily_content),
                },
                "total_tokens": critical_tokens + daily_tokens,
                "warnings": warnings,
                "filtered_sensitive_count": filtered_sensitive_total,
                "bootstrap": bootstrap_status(
                    critical_content,
                    daily_content,
                    critical_tokens + daily_tokens,
                ),
                "message": f"Loaded {len(critical_content)} critical + {len(daily_content)} daily memories ({critical_tokens + daily_tokens} tokens)",
            }

    # Get CRITICAL tier memories
    critical = await db.agentmemory.find_many(
        where={
            "projectId": project_id,
            "tier": "CRITICAL",
            "reviewStatus": MEMORY_REVIEW_APPROVED,
            "OR": [
                {"expiresAt": None},
                {"expiresAt": {"gt": now}},
            ],
        },
        order={"confidence": "desc"},
    )

    # Get DAILY tier memories (today + optionally yesterday)
    daily_filter: dict[str, Any] = {
        "projectId": project_id,
        "tier": "DAILY",
        "createdAt": {"gte": yesterday if include_yesterday else today},
        "reviewStatus": MEMORY_REVIEW_APPROVED,
    }

    daily = await db.agentmemory.find_many(
        where=daily_filter,
        order={"createdAt": "desc"},
    )

    critical, filtered_critical = _filter_sensitive_memories(critical)
    daily, filtered_daily = _filter_sensitive_memories(daily)
    filtered_sensitive_total += filtered_critical + filtered_daily
    if filtered_critical or filtered_daily:
        warnings.append("sensitive_memory_filtered")

    critical_content = budget_memories(critical, max_critical_tokens)
    daily_content = budget_memories(daily, max_daily_tokens)

    critical_tokens = sum(len(m["content"]) // 4 for m in critical_content)
    daily_tokens = sum(len(m["content"]) // 4 for m in daily_content)

    return {
        "critical": {
            "memories": critical_content,
            "count": len(critical_content),
            "tokens": critical_tokens,
        },
        "daily": {
            "memories": daily_content,
            "count": len(daily_content),
            "tokens": daily_tokens,
        },
        "total_tokens": critical_tokens + daily_tokens,
        "warnings": warnings,
        "filtered_sensitive_count": filtered_sensitive_total,
        "bootstrap": bootstrap_status(
            critical_content,
            daily_content,
            critical_tokens + daily_tokens,
        ),
        "message": f"Loaded {len(critical_content)} critical + {len(daily_content)} daily memories ({critical_tokens + daily_tokens} tokens)",
    }


async def compact_memories(
    project_id: str,
    scope: str = "project",
    deduplicate: bool = True,
    promote_threshold: int = 3,
    archive_older_than_days: int = 30,
    dry_run: bool = False,
    # New consolidation parameters
    normalize_dates: bool = True,
    validate_refs: bool = True,
    conflict_strategy: str = "",
    similarity_threshold: float = 0.85,
) -> dict[str, Any]:
    """Compact and optimize memories with intelligent consolidation.

    Args:
        project_id: The project ID
        scope: Memory scope to compact (agent, project, team)
        deduplicate: Merge similar memories
        promote_threshold: If learning accessed N times, promote to CRITICAL
        archive_older_than_days: Archive memories older than N days
        dry_run: Preview changes without applying

        # New consolidation parameters (inspired by dream-skill):
        normalize_dates: Convert relative dates ("yesterday") to absolute ("2026-03-24")
        validate_refs: Remove dead document_refs that no longer exist in index
        conflict_strategy: How to resolve contradictions:
            - "newer": Keep most recent, archive older (default)
            - "higher_confidence": Keep highest confidence score
            - "merge": Combine content into newer memory
            - "flag": Mark both for manual review
        similarity_threshold: Semantic similarity threshold for conflict detection (0.0-1.0)

    Returns:
        Dict with compaction results including new consolidation metrics
    """
    db = await get_db()
    now = datetime.now(UTC)

    results: dict[str, Any] = {
        "noise_pruned": 0,
        "superseded_workspace_learning_removed": 0,
        "deleted_tombstones_removed": 0,
        "sync_test_noise_removed": 0,
        "task_journals_removed": 0,
        "auto_document_uploads_removed": 0,
        "trivial_decompositions_removed": 0,
        "execution_plan_receipts_removed": 0,
        # Existing metrics
        "duplicates_merged": 0,
        "promoted_to_critical": 0,
        "archived": 0,
        "tokens_freed": 0,
        # New consolidation metrics
        "dates_normalized": 0,
        "dead_refs_removed": 0,
        "conflicts_resolved": 0,
        "conflicts_flagged": 0,
        "conflict_details": [],
        "dry_run": dry_run,
    }

    # Get all memories for this project (used across multiple phases)
    all_memories = await db.agentmemory.find_many(
        where={"projectId": project_id, "reviewStatus": MEMORY_REVIEW_APPROVED},
        order={"createdAt": "asc"},
    )

    # ─────────────────────────────────────────────────────────
    # Phase 1: Low-Signal Hygiene Cleanup (NEW)
    # Prune obviously non-durable memory rows before expensive work
    # ─────────────────────────────────────────────────────────
    low_signal_ids: list[str] = []
    low_signal_id_set: set[str] = set()
    already_archived_ids: set[str] = set()

    for memory in all_memories:
        reason = _classify_low_signal_memory(memory)
        if reason is None:
            continue

        low_signal_ids.append(memory.id)
        low_signal_id_set.add(memory.id)
        results["noise_pruned"] += 1
        results[LOW_SIGNAL_RESULT_KEYS[reason]] += 1
        results["tokens_freed"] += len(memory.content) // 4

    if low_signal_ids:
        await _delete_memories_with_embeddings(db, low_signal_ids, dry_run=dry_run)
        all_memories = [memory for memory in all_memories if memory.id not in low_signal_id_set]

    # ─────────────────────────────────────────────────────────
    # Phase 2: Date Normalization (NEW)
    # Convert relative dates to absolute using memory's creation time
    # ─────────────────────────────────────────────────────────
    if normalize_dates:
        for memory in all_memories:
            if not memory.content or not memory.createdAt:
                continue

            normalized_content, replacement_count = normalize_memory_dates(
                memory.content,
                memory.createdAt,
            )

            if replacement_count > 0:
                if not dry_run:
                    await db.agentmemory.update(
                        where={"id": memory.id},
                        data={"content": normalized_content},
                    )
                    # Update in-memory object for subsequent phases
                    memory.content = normalized_content
                results["dates_normalized"] += replacement_count

    # ─────────────────────────────────────────────────────────
    # Phase 3: Dead Reference Cleanup (NEW)
    # Remove document_refs that no longer exist in the index
    # ─────────────────────────────────────────────────────────
    if validate_refs:
        for memory in all_memories:
            if not memory.documentRefs:
                continue

            valid_refs, removed_count = await validate_document_refs(
                memory.documentRefs,
                project_id,
            )

            if removed_count > 0:
                if not dry_run:
                    await db.agentmemory.update(
                        where={"id": memory.id},
                        data={"documentRefs": valid_refs},
                    )
                results["dead_refs_removed"] += removed_count

    # ─────────────────────────────────────────────────────────
    # Phase 4: Semantic Conflict Resolution (NEW)
    # Find similar-but-different memories and resolve contradictions
    # ─────────────────────────────────────────────────────────
    if deduplicate and conflict_strategy:
        # Find semantic conflicts using embeddings
        conflicts = await find_semantic_conflicts(all_memories, similarity_threshold)

        for older, newer, similarity in conflicts:
            resolution = await resolve_conflict(
                older=older,
                newer=newer,
                similarity=similarity,
                strategy=conflict_strategy,
                dry_run=dry_run,
            )

            if resolution.get("action") == "flagged":
                results["conflicts_flagged"] += 1
            elif resolution.get("action") != "skipped":
                results["conflicts_resolved"] += 1
                # Estimate tokens freed from archived memory
                if "archived_id" in resolution:
                    archived_mem = next(
                        (m for m in all_memories if m.id == resolution["archived_id"]), None
                    )
                    if archived_mem:
                        results["tokens_freed"] += len(archived_mem.content) // 4
                    already_archived_ids.add(resolution["archived_id"])

            results["conflict_details"].append(resolution)

    # ─────────────────────────────────────────────────────────
    # Phase 5: Exact Duplicate Removal (existing logic)
    # Remove memories with identical content prefix + type
    # ─────────────────────────────────────────────────────────
    if deduplicate:
        seen_content: dict[str, str] = {}  # content hash -> id
        duplicates_to_delete: list[str] = []

        for m in all_memories:
            # Simple hash: first 100 chars + type
            content_key = f"{m.type}:{m.content[:100]}"
            if content_key in seen_content:
                duplicates_to_delete.append(m.id)
                results["duplicates_merged"] += 1
                results["tokens_freed"] += len(m.content) // 4
            else:
                seen_content[content_key] = m.id

        if duplicates_to_delete:
            duplicate_id_set = set(duplicates_to_delete)
            await _delete_memories_with_embeddings(db, duplicates_to_delete, dry_run=dry_run)
            all_memories = [memory for memory in all_memories if memory.id not in duplicate_id_set]
            low_signal_id_set.update(duplicate_id_set)

    # ─────────────────────────────────────────────────────────
    # Phase 6: Promote Frequently Accessed Learnings (existing)
    # ─────────────────────────────────────────────────────────
    learning_where: dict[str, Any] = {
        "projectId": project_id,
        "type": "LEARNING",
        "accessCount": {"gte": promote_threshold},
        "tier": {"not": "CRITICAL"},
        "reviewStatus": MEMORY_REVIEW_APPROVED,
    }
    if low_signal_id_set:
        learning_where["id"] = {"notIn": sorted(low_signal_id_set)}

    learnings = await db.agentmemory.find_many(
        where=learning_where,
    )

    for learning in learnings:
        if not dry_run:
            await db.agentmemory.update(
                where={"id": learning.id},
                data={
                    "tier": "CRITICAL",
                    "promotedAt": now,
                    "promotedBy": "compaction",
                },
            )
        results["promoted_to_critical"] += 1

    # ─────────────────────────────────────────────────────────
    # Phase 7: Archive Old Memories (existing)
    # ─────────────────────────────────────────────────────────
    cutoff = now - timedelta(days=archive_older_than_days)
    old_memory_where: dict[str, Any] = {
        "projectId": project_id,
        "tier": {"notIn": ["CRITICAL", "ARCHIVE"]},
        "createdAt": {"lt": cutoff},
        "reviewStatus": MEMORY_REVIEW_APPROVED,
    }
    excluded_archive_ids = low_signal_id_set | already_archived_ids
    if excluded_archive_ids:
        old_memory_where["id"] = {"notIn": sorted(excluded_archive_ids)}

    old_memories = await db.agentmemory.find_many(
        where=old_memory_where,
    )

    for memory in old_memories:
        if not dry_run:
            await db.agentmemory.update(
                where={"id": memory.id},
                data={"tier": "ARCHIVE"},
            )
        results["archived"] += 1

    # Build summary message
    action = "Would have" if dry_run else "Successfully"
    parts = []

    if results["noise_pruned"] > 0:
        parts.append(f"pruned {results['noise_pruned']} low-signal memories")
    if results["dates_normalized"] > 0:
        parts.append(f"normalized {results['dates_normalized']} dates")
    if results["dead_refs_removed"] > 0:
        parts.append(f"removed {results['dead_refs_removed']} dead refs")
    if results["conflicts_resolved"] > 0:
        parts.append(f"resolved {results['conflicts_resolved']} conflicts")
    if results["conflicts_flagged"] > 0:
        parts.append(f"flagged {results['conflicts_flagged']} for review")
    if results["duplicates_merged"] > 0:
        parts.append(f"merged {results['duplicates_merged']} duplicates")
    if results["promoted_to_critical"] > 0:
        parts.append(f"promoted {results['promoted_to_critical']} learnings")
    if results["archived"] > 0:
        parts.append(f"archived {results['archived']} old memories")

    if parts:
        results["message"] = (
            f"{action}: {', '.join(parts)} (~{results['tokens_freed']} tokens freed)"
        )
    else:
        results["message"] = f"{action}: No changes needed"

    # Remove conflict_details if empty (to reduce response size)
    if not results["conflict_details"]:
        del results["conflict_details"]

    return results


async def maybe_auto_compact(project_id: str) -> dict[str, Any] | None:
    """Check if auto-compaction should run and trigger it if needed.

    Auto-compaction runs when:
    1. Memory count exceeds AUTO_COMPACT_THRESHOLD
    2. At least AUTO_COMPACT_COOLDOWN seconds since last compaction

    Args:
        project_id: The project ID

    Returns:
        Compaction results if ran, None otherwise
    """
    db = await get_db()
    redis = await get_redis()

    # Check memory count
    try:
        memory_count = await db.agentmemory.count(
            where={"projectId": project_id, "reviewStatus": MEMORY_REVIEW_APPROVED}
        )

        if memory_count < AUTO_COMPACT_THRESHOLD:
            return None  # Not enough memories to compact

        # Check cooldown
        if redis:
            cache_key = f"{AUTO_COMPACT_CACHE_KEY_PREFIX}{project_id}"
            last_compact = await redis.get(cache_key)
            if last_compact:
                # Still in cooldown
                logger.debug(f"Auto-compact skipped for {project_id}: cooldown active")
                return None

        logger.info(f"Auto-compacting memories for project {project_id} ({memory_count} memories)")

        # Auto-compaction should be safe and deterministic: prune low-signal
        # receipts, exact duplicates, stale refs, and old daily memories. Broad
        # semantic conflict resolution can archive valid nuance, so keep it
        # manual unless a caller explicitly opts in.
        results = await compact_memories(
            project_id=project_id,
            scope="project",
            deduplicate=True,
            promote_threshold=3,
            archive_older_than_days=30,
            dry_run=False,
            # Consolidation features (enabled by default for auto-compact)
            normalize_dates=True,
            validate_refs=True,
            conflict_strategy="",
            similarity_threshold=0.85,
        )

        # Set cooldown in Redis
        if redis:
            await redis.setex(cache_key, AUTO_COMPACT_COOLDOWN, "1")

        results["auto_triggered"] = True
        results["memory_count_before"] = memory_count

        logger.info(
            f"Auto-compaction completed for {project_id}: "
            f"{results['duplicates_merged']} duplicates, "
            f"{results['archived']} archived"
        )

        return results

    except Exception as e:
        logger.warning(f"Auto-compaction failed for {project_id}: {e}")
        return None


async def get_daily_brief(
    project_id: str,
    date: str | None = None,
    max_items: int = 10,
) -> dict[str, Any]:
    """Generate a 'Top N active constraints' brief for the day.

    Args:
        project_id: The project ID
        date: Date for brief (default: today)
        max_items: Maximum items to include

    Returns:
        Dict with prioritized memory brief
    """
    db = await get_db()

    # Parse date
    if date:
        try:
            target_date = datetime.fromisoformat(date)
        except ValueError:
            return {"error": f"Invalid date format: {date}. Use YYYY-MM-DD"}
    else:
        target_date = datetime.now(UTC)

    target_date = target_date.replace(tzinfo=UTC)

    # Get critical decisions (highest priority)
    decisions = await db.agentmemory.find_many(
        where={
            "projectId": project_id,
            "type": "DECISION",
            "tier": "CRITICAL",
            "reviewStatus": MEMORY_REVIEW_APPROVED,
        },
        order={"confidence": "desc"},
        take=max_items // 2,
    )

    # Get active todos
    todos = await db.agentmemory.find_many(
        where={
            "projectId": project_id,
            "type": "TODO",
            "reviewStatus": MEMORY_REVIEW_APPROVED,
            "OR": [
                {"expiresAt": None},
                {"expiresAt": {"gt": target_date}},
            ],
        },
        order={"createdAt": "desc"},
        take=max_items // 4,
    )

    # Get recent learnings
    recent_cutoff = target_date - timedelta(days=7)
    learnings = await db.agentmemory.find_many(
        where={
            "projectId": project_id,
            "type": "LEARNING",
            "createdAt": {"gte": recent_cutoff},
            "reviewStatus": MEMORY_REVIEW_APPROVED,
        },
        order={"accessCount": "desc"},
        take=max_items // 4,
    )

    # Build brief
    items = []

    for d in decisions:
        items.append(
            {
                "priority": 1,
                "type": "DECISION",
                "content": d.content,
                "category": d.category,
            }
        )

    for t in todos:
        items.append(
            {
                "priority": 2,
                "type": "TODO",
                "content": t.content,
                "category": t.category,
            }
        )

    for l in learnings:  # noqa: E741
        items.append(
            {
                "priority": 3,
                "type": "LEARNING",
                "content": l.content,
                "category": l.category,
            }
        )

    # Sort by priority and limit
    items = sorted(items, key=lambda x: x["priority"])[:max_items]

    # Build formatted brief
    brief_lines = ["# Daily Brief", ""]
    if decisions:
        brief_lines.append("## Active Decisions")
        for d in decisions:
            brief_lines.append(f"- {d.content[:200]}")
        brief_lines.append("")

    if todos:
        brief_lines.append("## Pending TODOs")
        for t in todos:
            brief_lines.append(f"- [ ] {t.content[:200]}")
        brief_lines.append("")

    if learnings:
        brief_lines.append("## Recent Learnings")
        for l in learnings:  # noqa: E741
            brief_lines.append(f"- {l.content[:200]}")

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "items": items,
        "brief": "\n".join(brief_lines),
        "counts": {
            "decisions": len(decisions),
            "todos": len(todos),
            "learnings": len(learnings),
        },
    }


# ============ PHASE 20: TENANT PROFILE ============

TENANT_PROFILE_CATEGORY = "tenant_profile"


async def create_tenant_profile(
    project_id: str,
    client_name: str,
    business_model: str | None = None,
    industry: str | None = None,
    tech_stack: str | None = None,
    legal_constraints: str | None = None,
    security_requirements: str | None = None,
    ui_ux_prefs: str | None = None,
    communication_style: str | None = None,
    risk_tolerance: str | None = None,
    dos: list[str] | None = None,
    donts: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a structured tenant/client profile stored as CRITICAL memory.

    Args:
        project_id: The project ID
        client_name: Name of the client/tenant
        business_model: How the business works
        industry: Industry vertical
        tech_stack: Technology stack used
        legal_constraints: Legal requirements
        security_requirements: Security constraints
        ui_ux_prefs: UI/UX preferences
        communication_style: How to communicate
        risk_tolerance: low/medium/high
        dos: List of things to do
        donts: List of things to avoid
        custom_fields: Additional custom fields

    Returns:
        Dict with profile ID and confirmation
    """
    # Build profile content
    profile_parts = [f"# Tenant Profile: {client_name}", ""]

    if business_model or industry or tech_stack:
        profile_parts.append("## Business Context")
        if business_model:
            profile_parts.append(f"- **Business Model:** {business_model}")
        if industry:
            profile_parts.append(f"- **Industry:** {industry}")
        if tech_stack:
            profile_parts.append(f"- **Stack:** {tech_stack}")
        profile_parts.append("")

    if legal_constraints or security_requirements:
        profile_parts.append("## Constraints")
        if legal_constraints:
            profile_parts.append(f"- **Legal:** {legal_constraints}")
        if security_requirements:
            profile_parts.append(f"- **Security:** {security_requirements}")
        profile_parts.append("")

    if ui_ux_prefs or communication_style or risk_tolerance:
        profile_parts.append("## Preferences")
        if ui_ux_prefs:
            profile_parts.append(f"- **UI/UX:** {ui_ux_prefs}")
        if communication_style:
            profile_parts.append(f"- **Communication:** {communication_style}")
        if risk_tolerance:
            profile_parts.append(f"- **Risk Tolerance:** {risk_tolerance}")
        profile_parts.append("")

    if dos or donts:
        profile_parts.append("## Do/Don't")
        if dos:
            profile_parts.append("### DO")
            for do in dos:
                profile_parts.append(f"- {do}")
        if donts:
            profile_parts.append("### DON'T")
            for dont in donts:
                profile_parts.append(f"- {dont}")
        profile_parts.append("")

    if custom_fields:
        profile_parts.append("## Additional Info")
        for key, value in custom_fields.items():
            profile_parts.append(f"- **{key}:** {value}")

    content = "\n".join(profile_parts)

    # Store as CRITICAL memory
    result = await store_memory(
        project_id=project_id,
        content=content,
        memory_type="FACT",
        scope="PROJECT",
        category=TENANT_PROFILE_CATEGORY,
        source="tenant_profile",
    )

    # Manually promote to CRITICAL tier
    db = await get_db()
    await db.agentmemory.update(
        where={"id": result["memory_id"]},
        data={
            "tier": "CRITICAL",
            "promotedAt": datetime.now(UTC),
            "promotedBy": "tenant_profile_create",
        },
    )

    return {
        "profile_id": result["memory_id"],
        "client_name": client_name,
        "message": f"Created tenant profile for {client_name} (stored as CRITICAL memory)",
        "content_preview": content[:500] + "..." if len(content) > 500 else content,
    }


async def get_tenant_profile(
    project_id: str,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Get tenant profile(s) for a project.

    Args:
        project_id: The project ID
        tenant_id: Specific profile ID (optional, returns latest if not specified)

    Returns:
        Dict with tenant profile(s)
    """
    db = await get_db()

    if tenant_id:
        # Get specific profile
        profile = await db.agentmemory.find_unique(where={"id": tenant_id})
        if not profile:
            return {"error": f"Profile {tenant_id} not found"}
        return {
            "profile_id": profile.id,
            "content": profile.content,
            "created_at": profile.createdAt.isoformat() if profile.createdAt else None,
            "tier": profile.tier,
        }
    else:
        # Get all tenant profiles for project
        profiles = await db.agentmemory.find_many(
            where={
                "projectId": project_id,
                "category": TENANT_PROFILE_CATEGORY,
                "reviewStatus": MEMORY_REVIEW_APPROVED,
            },
            order={"createdAt": "desc"},
        )

        if not profiles:
            return {"profiles": [], "message": "No tenant profiles found"}

        return {
            "profiles": [
                {
                    "profile_id": p.id,
                    "content": p.content,
                    "created_at": p.createdAt.isoformat() if p.createdAt else None,
                    "tier": p.tier,
                }
                for p in profiles
            ],
            "count": len(profiles),
        }
