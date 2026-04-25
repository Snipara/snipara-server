"""Tests for business-context freshness and provenance health."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.services.business_context_health import compute_business_context_health
from src.services.index_health import (
    IndexHealth,
    QualityDistribution,
    TierDistribution,
    get_index_recommendations,
)

NOW = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)


def make_doc(
    path: str,
    metadata: dict | None = None,
    *,
    id: str | None = None,
    kind: str = "DOC",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id or path,
        path=path,
        kind=kind,
        source="mcp",
        metadata=metadata,
        createdAt=NOW - timedelta(days=10),
        updatedAt=NOW - timedelta(days=5),
    )


def test_current_truth_expired_snapshot_requires_reupload():
    health = compute_business_context_health(
        [
            make_doc(
                "clients/xyz/requirements.md",
                {
                    "assetClass": "BUSINESS_DOCUMENT",
                    "usageMode": "current_truth",
                    "clientId": "xyz",
                    "sourceKind": "google_drive",
                    "sourceSnapshotAt": "2026-03-01T10:00:00Z",
                    "sourceModifiedAt": "2026-03-01T09:00:00Z",
                    "freshnessPolicy": {"maxAgeDays": 30},
                },
            )
        ],
        now=NOW,
    )

    assert health.tracked_documents == 1
    assert health.needs_reupload == 1
    assert health.signals[0].reason == "source_snapshot_expired"
    assert health.signals[0].action == "reupload"
    assert health.by_usage_mode == {"current_truth": 1}


def test_historical_reference_can_be_old_when_provenance_is_present():
    health = compute_business_context_health(
        [
            make_doc(
                "clients/acme/schema.context.md",
                {
                    "assetClass": "DIAGRAM",
                    "usageMode": "historical_reference",
                    "clientId": "acme",
                    "artifactType": "network_schema",
                    "artifactStatus": "approved",
                    "sourceSnapshotAt": "2024-01-01T10:00:00Z",
                },
            )
        ],
        now=NOW,
    )

    assert health.tracked_documents == 1
    assert health.needs_attention == 0
    assert health.by_asset_class == {"DIAGRAM": 1}
    assert health.by_usage_mode == {"historical_reference": 1}


def test_historical_reference_accepts_nested_reference_provenance():
    health = compute_business_context_health(
        [
            make_doc(
                "case-library/acme/schema.context.md",
                {
                    "assetClass": "DIAGRAM",
                    "usageMode": "historical_reference",
                    "referenceProvenance": {
                        "sourceClientId": "acme",
                        "sourceProjectId": "acme-network-redesign",
                        "approvalStatus": "approved_reference",
                    },
                },
            )
        ],
        now=NOW,
    )

    assert health.tracked_documents == 1
    assert health.needs_attention == 0


def test_historical_reference_without_client_or_origin_needs_metadata_review():
    health = compute_business_context_health(
        [
            make_doc(
                "case-library/schema.context.md",
                {
                    "assetClass": "DIAGRAM",
                    "usageMode": "historical_reference",
                    "artifactType": "network_schema",
                },
            )
        ],
        now=NOW,
    )

    assert health.needs_metadata_review == 1
    assert health.signals[0].reason == "missing_reference_provenance"
    assert health.signals[0].action == "review_source_metadata"


def test_low_quality_diagram_is_reviewed_not_reuploaded():
    health = compute_business_context_health(
        [
            make_doc(
                "clients/acme/schema.context.md",
                {
                    "assetClass": "DIAGRAM",
                    "usageMode": "historical_reference",
                    "clientId": "acme",
                    "quality": {"status": "poor"},
                },
            )
        ],
        now=NOW,
    )

    assert health.needs_quality_review == 1
    assert health.needs_reupload == 0
    assert health.signals[0].reason == "diagram_quality_low"
    assert health.signals[0].action == "review_content_quality"


def test_parser_version_mismatch_recommends_reindex():
    health = compute_business_context_health(
        [
            make_doc(
                "clients/acme/schema.context.md",
                {
                    "assetClass": "DIAGRAM",
                    "usageMode": "historical_reference",
                    "clientId": "acme",
                    "parser": {"name": "vsdx", "version": "1"},
                },
            )
        ],
        now=NOW,
        current_parser_versions={"vsdx": "2"},
    )

    assert health.needs_reindex == 1
    assert health.signals[0].reason == "parser_version_outdated"
    assert health.signals[0].action == "reindex"


def test_unclassified_non_code_docs_are_counted_and_code_docs_are_ignored():
    health = compute_business_context_health(
        [
            make_doc("docs/readme.md", None),
            make_doc("src/app.py", {"assetClass": "BUSINESS_DOCUMENT"}, kind="DocumentKind.CODE"),
        ],
        now=NOW,
    )

    assert health.tracked_documents == 0
    assert health.unclassified_documents == 1


def test_raw_vsdx_documents_are_tracked_as_diagrams():
    health = compute_business_context_health(
        [make_doc("diagrams/network.vsdx", None, kind="BINARY")],
        now=NOW,
    )

    assert health.tracked_documents == 1
    assert health.by_asset_class == {"DIAGRAM": 1}


@pytest.mark.asyncio
async def test_index_recommendations_include_business_reupload_action():
    business_health = compute_business_context_health(
        [
            make_doc(
                "clients/xyz/requirements.md",
                {
                    "assetClass": "BUSINESS_DOCUMENT",
                    "usageMode": "current_truth",
                    "clientId": "xyz",
                    "sourceSnapshotAt": "2026-03-01T10:00:00Z",
                    "freshnessPolicy": {"maxAgeDays": 30},
                },
            )
        ],
        now=NOW,
    )
    health = IndexHealth(
        total_documents=1,
        indexed_documents=1,
        unindexed_documents=0,
        coverage_percent=100,
        total_chunks=1,
        avg_chunks_per_doc=1,
        avg_quality_score=1,
        tier_distribution=TierDistribution(warm=1),
        quality_distribution=QualityDistribution(high=1),
        stale_documents=[],
        stale_count=0,
        health_score=100,
        health_status="healthy",
        last_index_at=NOW,
        last_index_status="completed",
        business_context=business_health,
    )

    recommendations = await get_index_recommendations(None, "project-1", health)

    assert recommendations[0]["type"] == "business_context_reupload"
    assert recommendations[0]["action"] == "reupload"
    assert recommendations[0]["count"] == 1
