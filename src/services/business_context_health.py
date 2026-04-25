"""Business-context freshness and provenance analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

BUSINESS_ASSET_CLASSES = {"BUSINESS_DOCUMENT", "PRESENTATION", "DIAGRAM"}
BUSINESS_USAGE_MODES = {
    "current_truth",
    "historical_reference",
    "template",
    "global_knowledge",
    "unspecified",
}


@dataclass(frozen=True)
class BusinessContextSignal:
    """Actionable signal for one business-context document."""

    id: str
    path: str
    reason: str
    action: str
    priority: str
    asset_class: str
    usage_mode: str
    client_id: str | None = None
    source_kind: str | None = None
    artifact_type: str | None = None
    artifact_status: str | None = None
    days_since_snapshot: int | None = None
    source_modified_at: str | None = None
    source_snapshot_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "reason": self.reason,
            "action": self.action,
            "priority": self.priority,
            "asset_class": self.asset_class,
            "usage_mode": self.usage_mode,
            "client_id": self.client_id,
            "source_kind": self.source_kind,
            "artifact_type": self.artifact_type,
            "artifact_status": self.artifact_status,
            "days_since_snapshot": self.days_since_snapshot,
            "source_modified_at": self.source_modified_at,
            "source_snapshot_at": self.source_snapshot_at,
        }


@dataclass
class BusinessContextHealth:
    """Aggregated health for business-context documents."""

    tracked_documents: int = 0
    unclassified_documents: int = 0
    by_asset_class: dict[str, int] = field(default_factory=dict)
    by_usage_mode: dict[str, int] = field(default_factory=dict)
    by_source_kind: dict[str, int] = field(default_factory=dict)
    signals: list[BusinessContextSignal] = field(default_factory=list)

    @property
    def needs_reupload(self) -> int:
        return sum(1 for signal in self.signals if signal.action == "reupload")

    @property
    def needs_reindex(self) -> int:
        return sum(1 for signal in self.signals if signal.action == "reindex")

    @property
    def needs_metadata_review(self) -> int:
        return sum(1 for signal in self.signals if signal.action == "review_source_metadata")

    @property
    def needs_quality_review(self) -> int:
        return sum(1 for signal in self.signals if signal.action == "review_content_quality")

    @property
    def needs_attention(self) -> int:
        return len(self.signals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracked_documents": self.tracked_documents,
            "unclassified_documents": self.unclassified_documents,
            "by_asset_class": self.by_asset_class,
            "by_usage_mode": self.by_usage_mode,
            "by_source_kind": self.by_source_kind,
            "needs_attention": self.needs_attention,
            "needs_reupload": self.needs_reupload,
            "needs_reindex": self.needs_reindex,
            "needs_metadata_review": self.needs_metadata_review,
            "needs_quality_review": self.needs_quality_review,
            "signals": [signal.to_dict() for signal in self.signals[:20]],
        }


def compute_business_context_health(
    documents: list[Any],
    *,
    now: datetime | None = None,
    current_parser_versions: dict[str, str] | None = None,
) -> BusinessContextHealth:
    """Compute business-context freshness/provenance signals from document metadata."""

    current_time = now or datetime.now(tz=UTC)
    parser_versions = current_parser_versions or {}
    health = BusinessContextHealth()

    for document in documents:
        if _document_kind(document) == "CODE":
            continue

        metadata = _metadata_dict(getattr(document, "metadata", None))
        asset_class = _asset_class(document, metadata)
        if not asset_class:
            health.unclassified_documents += 1
            continue

        usage_mode = _usage_mode(metadata)
        source_kind = _string(metadata.get("sourceKind") or metadata.get("source_kind"))
        client_id = _string(metadata.get("clientId") or metadata.get("client_id"))
        artifact_type = _string(metadata.get("artifactType") or metadata.get("artifact_type"))
        artifact_status = _string(metadata.get("artifactStatus") or metadata.get("artifact_status"))

        health.tracked_documents += 1
        _increment(health.by_asset_class, asset_class)
        _increment(health.by_usage_mode, usage_mode)
        if source_kind:
            _increment(health.by_source_kind, source_kind)

        base = {
            "id": str(getattr(document, "id", "")),
            "path": str(getattr(document, "path", "")),
            "asset_class": asset_class,
            "usage_mode": usage_mode,
            "client_id": client_id,
            "source_kind": source_kind,
            "artifact_type": artifact_type,
            "artifact_status": artifact_status,
        }

        health.signals.extend(
            _freshness_signals(
                metadata,
                base=base,
                now=current_time,
            )
        )
        health.signals.extend(
            _provenance_signals(
                metadata,
                base=base,
            )
        )
        health.signals.extend(
            _parser_signals(
                metadata,
                base=base,
                current_parser_versions=parser_versions,
            )
        )
        health.signals.extend(
            _quality_signals(
                metadata,
                base=base,
            )
        )

    health.signals.sort(key=lambda signal: (_priority_rank(signal.priority), signal.path))
    return health


def _freshness_signals(
    metadata: dict[str, Any],
    *,
    base: dict[str, Any],
    now: datetime,
) -> list[BusinessContextSignal]:
    usage_mode = str(base["usage_mode"])
    policy = metadata.get("freshnessPolicy") if isinstance(metadata.get("freshnessPolicy"), dict) else {}
    source_modified_at = _parse_datetime(metadata.get("sourceModifiedAt") or metadata.get("source_modified_at"))
    source_snapshot_at = _parse_datetime(metadata.get("sourceSnapshotAt") or metadata.get("source_snapshot_at"))
    source_hash = _string(metadata.get("sourceContentHash") or metadata.get("source_content_hash"))
    latest_hash = _string(
        metadata.get("latestSourceContentHash")
        or metadata.get("currentSourceContentHash")
        or metadata.get("manifestSourceContentHash")
    )

    require_modified_at = bool(policy.get("requireSourceModifiedAt", usage_mode == "current_truth"))
    require_hash = bool(policy.get("requireContentHash", False))
    max_age_days = _int_or_none(policy.get("maxAgeDays"))
    if max_age_days is None and usage_mode == "current_truth":
        max_age_days = 30

    signals: list[BusinessContextSignal] = []

    missing_required_metadata = (
        (require_modified_at and source_modified_at is None)
        or (require_hash and not source_hash)
        or (usage_mode == "current_truth" and not any((source_modified_at, source_snapshot_at, source_hash)))
    )
    if missing_required_metadata:
        signals.append(
            BusinessContextSignal(
                **base,
                reason="missing_source_metadata",
                action="review_source_metadata",
                priority="high" if usage_mode == "current_truth" else "medium",
            )
        )

    if source_snapshot_at and max_age_days is not None:
        days_since_snapshot = max(0, (now - source_snapshot_at).days)
        if days_since_snapshot > max_age_days:
            signals.append(
                BusinessContextSignal(
                    **base,
                    reason="source_snapshot_expired",
                    action="reupload",
                    priority="high" if usage_mode == "current_truth" else "medium",
                    days_since_snapshot=days_since_snapshot,
                    source_snapshot_at=source_snapshot_at.isoformat(),
                    source_modified_at=source_modified_at.isoformat() if source_modified_at else None,
                )
            )

    if source_modified_at and source_snapshot_at and source_modified_at > source_snapshot_at:
        signals.append(
            BusinessContextSignal(
                **base,
                reason="source_modified_after_upload",
                action="reupload",
                priority="high",
                source_modified_at=source_modified_at.isoformat(),
                source_snapshot_at=source_snapshot_at.isoformat(),
            )
        )

    if source_hash and latest_hash and source_hash != latest_hash:
        signals.append(
            BusinessContextSignal(
                **base,
                reason="source_hash_changed",
                action="reupload",
                priority="high",
                source_modified_at=source_modified_at.isoformat() if source_modified_at else None,
                source_snapshot_at=source_snapshot_at.isoformat() if source_snapshot_at else None,
            )
        )

    return signals


def _provenance_signals(
    metadata: dict[str, Any],
    *,
    base: dict[str, Any],
) -> list[BusinessContextSignal]:
    usage_mode = str(base["usage_mode"])
    if usage_mode != "historical_reference":
        return []

    reference_provenance = metadata.get("referenceProvenance") or metadata.get("reference_provenance")
    has_nested_provenance = isinstance(reference_provenance, dict) and any(
        _string(value) for value in reference_provenance.values()
    )

    has_provenance = has_nested_provenance or any(
        metadata.get(key)
        for key in (
            "clientId",
            "client_id",
            "sourceClientId",
            "source_client_id",
            "derivedFrom",
            "derived_from",
        )
    )
    if has_provenance:
        return []

    return [
        BusinessContextSignal(
            **base,
            reason="missing_reference_provenance",
            action="review_source_metadata",
            priority="medium",
        )
    ]


def _parser_signals(
    metadata: dict[str, Any],
    *,
    base: dict[str, Any],
    current_parser_versions: dict[str, str],
) -> list[BusinessContextSignal]:
    parser = metadata.get("parser") if isinstance(metadata.get("parser"), dict) else {}
    parser_name = _string(parser.get("name") or metadata.get("parserName"))
    parser_version = _string(parser.get("version") or metadata.get("parserVersion"))

    if not parser_name or not parser_version:
        return []

    current_version = current_parser_versions.get(parser_name)
    if not current_version or current_version == parser_version:
        return []

    return [
        BusinessContextSignal(
            **base,
            reason="parser_version_outdated",
            action="reindex",
            priority="medium",
        )
    ]


def _quality_signals(
    metadata: dict[str, Any],
    *,
    base: dict[str, Any],
) -> list[BusinessContextSignal]:
    if base["asset_class"] != "DIAGRAM":
        return []

    quality = metadata.get("quality") if isinstance(metadata.get("quality"), dict) else {}
    quality_status = _string(
        metadata.get("qualityStatus")
        or metadata.get("quality_status")
        or quality.get("status")
    )
    if not quality_status or quality_status.lower() not in {"poor", "low"}:
        return []

    return [
        BusinessContextSignal(
            **base,
            reason="diagram_quality_low",
            action="review_content_quality",
            priority="medium",
        )
    ]


def _asset_class(document: Any, metadata: dict[str, Any]) -> str | None:
    raw_asset_class = _string(metadata.get("assetClass") or metadata.get("asset_class"))
    normalized = _normalize_enum(raw_asset_class)
    if normalized in BUSINESS_ASSET_CLASSES:
        return normalized

    parser = metadata.get("parser") if isinstance(metadata.get("parser"), dict) else {}
    parser_name = _normalize_enum(_string(parser.get("name") or metadata.get("parserName")))
    path = str(getattr(document, "path", "")).lower()

    if (
        metadata.get("bundleId")
        or metadata.get("artifactRole")
        or parser_name in {"SVG", "VSDX"}
        or path.endswith((".svg", ".vsdx"))
    ):
        return "DIAGRAM"
    if parser_name == "PPTX" or path.endswith((".pptx.context.md", ".deck.md")):
        return "PRESENTATION"
    if any(
        key in metadata
        for key in (
            "clientId",
            "client_id",
            "usageMode",
            "usage_mode",
            "artifactType",
            "artifact_type",
            "sourceKind",
            "source_kind",
        )
    ):
        return "BUSINESS_DOCUMENT"
    return None


def _usage_mode(metadata: dict[str, Any]) -> str:
    raw = _string(
        metadata.get("usageMode")
        or metadata.get("usage_mode")
        or metadata.get("contextRole")
        or metadata.get("context_role")
    )
    normalized = _normalize_enum(raw)
    aliases = {
        "ACTIVE": "current_truth",
        "CURRENT": "current_truth",
        "CURRENT_TRUTH": "current_truth",
        "CURRENT_CLIENT": "current_truth",
        "HISTORICAL": "historical_reference",
        "HISTORICAL_REFERENCE": "historical_reference",
        "REFERENCE": "historical_reference",
        "CASE_LIBRARY": "historical_reference",
        "PAST_DELIVERABLE": "historical_reference",
        "TEMPLATE": "template",
        "GLOBAL_TEMPLATE": "template",
        "GLOBAL": "global_knowledge",
        "GLOBAL_KNOWLEDGE": "global_knowledge",
        "BUSINESS_KNOWLEDGE": "global_knowledge",
    }
    return aliases.get(normalized, "unspecified")


def _metadata_dict(metadata: Any) -> dict[str, Any]:
    return metadata if isinstance(metadata, dict) else {}


def _document_kind(document: Any) -> str:
    kind = getattr(document, "kind", None)
    if hasattr(kind, "value"):
        kind = kind.value
    kind_text = str(kind or "DOC")
    if "." in kind_text:
        kind_text = kind_text.rsplit(".", 1)[-1]
    return _normalize_enum(kind_text)


def _normalize_enum(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("-", "_").replace(" ", "_").upper()


def _string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _increment(mapping: dict[str, int], key: str) -> None:
    mapping[key] = mapping.get(key, 0) + 1


def _priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(priority, 99)
