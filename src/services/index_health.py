# apps/mcp-server/src/services/index_health.py
"""Index health monitoring and metrics for Sprint 3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class TierDistribution:
    """Distribution of chunks across tiers."""

    hot: int = 0
    warm: int = 0
    cold: int = 0
    archive: int = 0

    @property
    def total(self) -> int:
        return self.hot + self.warm + self.cold + self.archive

    def to_dict(self) -> dict[str, Any]:
        total = self.total
        return {
            "hot": self.hot,
            "warm": self.warm,
            "cold": self.cold,
            "archive": self.archive,
            "total": total,
            "hot_percent": round(self.hot / total * 100, 1) if total > 0 else 0,
            "warm_percent": round(self.warm / total * 100, 1) if total > 0 else 0,
            "cold_percent": round(self.cold / total * 100, 1) if total > 0 else 0,
            "archive_percent": round(self.archive / total * 100, 1) if total > 0 else 0,
        }


@dataclass
class QualityDistribution:
    """Distribution of chunks by quality score."""

    high: int = 0  # >= 0.8
    medium: int = 0  # 0.5-0.8
    low: int = 0  # < 0.5

    @property
    def total(self) -> int:
        return self.high + self.medium + self.low

    def to_dict(self) -> dict[str, Any]:
        total = self.total
        return {
            "high": self.high,
            "medium": self.medium,
            "low": self.low,
            "total": total,
            "high_percent": round(self.high / total * 100, 1) if total > 0 else 0,
            "medium_percent": round(self.medium / total * 100, 1) if total > 0 else 0,
            "low_percent": round(self.low / total * 100, 1) if total > 0 else 0,
        }


@dataclass
class StaleDocument:
    """A document that may need reindexing."""

    id: str
    path: str
    reason: str  # "no_chunks", "outdated_chunks", "low_quality", "old_content"
    last_indexed: datetime | None
    days_stale: int
    chunk_count: int
    avg_quality: float


@dataclass
class IndexHealth:
    """Overall index health metrics for a project."""

    # Coverage
    total_documents: int
    indexed_documents: int
    unindexed_documents: int
    coverage_percent: float

    # Chunks
    total_chunks: int
    avg_chunks_per_doc: float
    avg_quality_score: float

    # Distributions
    tier_distribution: TierDistribution
    quality_distribution: QualityDistribution

    # Staleness
    stale_documents: list[StaleDocument]
    stale_count: int

    # Health score (0-100)
    health_score: int
    health_status: str  # "healthy", "warning", "critical"

    # Last index job
    last_index_at: datetime | None
    last_index_status: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage": {
                "total_documents": self.total_documents,
                "indexed_documents": self.indexed_documents,
                "unindexed_documents": self.unindexed_documents,
                "coverage_percent": self.coverage_percent,
            },
            "chunks": {
                "total_chunks": self.total_chunks,
                "avg_chunks_per_doc": round(self.avg_chunks_per_doc, 1),
                "avg_quality_score": round(self.avg_quality_score, 3),
            },
            "tier_distribution": self.tier_distribution.to_dict(),
            "quality_distribution": self.quality_distribution.to_dict(),
            "staleness": {
                "stale_count": self.stale_count,
                "stale_documents": [
                    {
                        "id": d.id,
                        "path": d.path,
                        "reason": d.reason,
                        "days_stale": d.days_stale,
                        "chunk_count": d.chunk_count,
                        "avg_quality": round(d.avg_quality, 3),
                    }
                    for d in self.stale_documents[:10]  # Limit to 10
                ],
            },
            "health": {
                "score": self.health_score,
                "status": self.health_status,
            },
            "last_index": {
                "at": self.last_index_at.isoformat() if self.last_index_at else None,
                "status": self.last_index_status,
            },
        }


async def compute_index_health(
    db: Any,
    project_id: str,
    stale_threshold_days: int = 30,
) -> IndexHealth:
    """
    Compute comprehensive index health metrics for a project.

    Args:
        db: Prisma database client
        project_id: Project to analyze
        stale_threshold_days: Days after which content is considered stale

    Returns:
        IndexHealth with all metrics computed
    """
    now = datetime.now(tz=UTC)
    stale_cutoff = now - timedelta(days=stale_threshold_days)

    # Get document counts
    total_docs = await db.document.count(
        where={"projectId": project_id, "deletedAt": None}
    )

    # Get documents with their chunk IDs (for counting)
    # Note: Prisma Python doesn't support nested select in include, just use True
    docs_with_chunks = await db.document.find_many(
        where={"projectId": project_id, "deletedAt": None},
        include={"chunks": True},
    )

    indexed_docs = sum(1 for d in docs_with_chunks if len(d.chunks) > 0)
    unindexed_docs = total_docs - indexed_docs

    # Get all chunks for this project
    # Note: Prisma Python doesn't support select like Prisma JS, just query all fields
    chunks = await db.documentchunk.find_many(
        where={"document": {"projectId": project_id, "deletedAt": None}},
    )

    total_chunks = len(chunks)

    # Tier distribution
    # Note: tier and qualityScore may not exist in schema yet, use getattr with defaults
    tier_dist = TierDistribution()
    for c in chunks:
        tier = getattr(c, "tier", None) or "WARM"
        if tier == "HOT":
            tier_dist.hot += 1
        elif tier == "WARM":
            tier_dist.warm += 1
        elif tier == "COLD":
            tier_dist.cold += 1
        else:
            tier_dist.archive += 1

    # Quality distribution
    quality_dist = QualityDistribution()
    total_quality = 0.0
    for c in chunks:
        score = getattr(c, "qualityScore", None) or 0.5
        total_quality += score
        if score >= 0.8:
            quality_dist.high += 1
        elif score >= 0.5:
            quality_dist.medium += 1
        else:
            quality_dist.low += 1

    avg_quality = total_quality / total_chunks if total_chunks > 0 else 0.0
    avg_chunks_per_doc = total_chunks / indexed_docs if indexed_docs > 0 else 0.0

    # Find stale documents
    stale_documents: list[StaleDocument] = []

    for doc in docs_with_chunks:
        chunk_count = len(doc.chunks)
        reason = None
        days_stale = 0
        latest_chunk = None

        # No chunks = definitely stale
        if chunk_count == 0:
            reason = "no_chunks"
            days_stale = (now - doc.createdAt.replace(tzinfo=UTC)).days

        # Check if document updated after last chunk
        elif doc.updatedAt:
            # Get latest chunk for this document
            latest_chunk = await db.documentchunk.find_first(
                where={"documentId": doc.id},
                order_by={"createdAt": "desc"},
            )
            if latest_chunk and doc.updatedAt > latest_chunk.createdAt:
                reason = "outdated_chunks"
                days_stale = (now - doc.updatedAt.replace(tzinfo=UTC)).days

        # Check for old content
        if not reason and doc.updatedAt:
            doc_updated = doc.updatedAt.replace(tzinfo=UTC)
            if doc_updated < stale_cutoff:
                reason = "old_content"
                days_stale = (now - doc_updated).days

        if reason:
            # Get average quality for this doc's chunks
            doc_chunks = [c for c in chunks if getattr(c, "documentId", None) == doc.id]
            avg_q = (
                sum(getattr(c, "qualityScore", 0.5) or 0.5 for c in doc_chunks) / len(doc_chunks)
                if doc_chunks
                else 0.0
            )

            stale_documents.append(
                StaleDocument(
                    id=doc.id,
                    path=doc.path,
                    reason=reason,
                    last_indexed=latest_chunk.createdAt if latest_chunk else None,
                    days_stale=days_stale,
                    chunk_count=chunk_count,
                    avg_quality=avg_q,
                )
            )

    # Sort stale docs by severity (no_chunks first, then by days_stale)
    stale_documents.sort(
        key=lambda d: (0 if d.reason == "no_chunks" else 1, -d.days_stale)
    )

    # Get last index job
    last_job = await db.indexjob.find_first(
        where={"projectId": project_id},
        order_by={"createdAt": "desc"},
    )

    # Compute health score (0-100)
    health_score = _compute_health_score(
        coverage_percent=indexed_docs / total_docs * 100 if total_docs > 0 else 100,
        avg_quality=avg_quality,
        stale_percent=len(stale_documents) / total_docs * 100 if total_docs > 0 else 0,
        archive_percent=tier_dist.archive / total_chunks * 100 if total_chunks > 0 else 0,
    )

    health_status = (
        "healthy" if health_score >= 80 else "warning" if health_score >= 50 else "critical"
    )

    return IndexHealth(
        total_documents=total_docs,
        indexed_documents=indexed_docs,
        unindexed_documents=unindexed_docs,
        coverage_percent=round(indexed_docs / total_docs * 100, 1) if total_docs > 0 else 100.0,
        total_chunks=total_chunks,
        avg_chunks_per_doc=avg_chunks_per_doc,
        avg_quality_score=avg_quality,
        tier_distribution=tier_dist,
        quality_distribution=quality_dist,
        stale_documents=stale_documents,
        stale_count=len(stale_documents),
        health_score=health_score,
        health_status=health_status,
        last_index_at=last_job.completedAt if last_job else None,
        last_index_status=last_job.status if last_job else None,
    )


def _compute_health_score(
    coverage_percent: float,
    avg_quality: float,
    stale_percent: float,
    archive_percent: float,
) -> int:
    """
    Compute overall health score from component metrics.

    Weights:
    - Coverage: 40%
    - Quality: 30%
    - Freshness (inverse of stale): 20%
    - Active content (inverse of archive): 10%
    """
    coverage_score = min(coverage_percent, 100)
    quality_score = avg_quality * 100
    freshness_score = max(0, 100 - stale_percent * 2)  # 50% stale = 0 score
    active_score = max(0, 100 - archive_percent)

    weighted = (
        coverage_score * 0.40
        + quality_score * 0.30
        + freshness_score * 0.20
        + active_score * 0.10
    )

    return int(round(weighted))


async def get_index_recommendations(
    db: Any,
    project_id: str,
    health: IndexHealth | None = None,
) -> list[dict[str, Any]]:
    """
    Get actionable recommendations based on index health.

    Returns list of recommendations with priority (high/medium/low).
    """
    if health is None:
        health = await compute_index_health(db, project_id)

    recommendations: list[dict[str, Any]] = []

    # Critical: Unindexed documents
    if health.unindexed_documents > 0:
        recommendations.append({
            "priority": "high",
            "type": "unindexed",
            "title": f"Index {health.unindexed_documents} unindexed documents",
            "description": "These documents have no searchable content. Run a full reindex to make them searchable.",
            "action": "reindex",
            "count": health.unindexed_documents,
        })

    # Warning: Low coverage
    if health.coverage_percent < 80:
        recommendations.append({
            "priority": "high" if health.coverage_percent < 50 else "medium",
            "type": "coverage",
            "title": f"Improve index coverage (currently {health.coverage_percent}%)",
            "description": "Low coverage means many documents won't appear in search results.",
            "action": "reindex",
        })

    # Warning: Stale content
    if health.stale_count > 0:
        no_chunks = sum(1 for d in health.stale_documents if d.reason == "no_chunks")
        outdated = sum(1 for d in health.stale_documents if d.reason == "outdated_chunks")

        if no_chunks > 0:
            recommendations.append({
                "priority": "high",
                "type": "no_chunks",
                "title": f"Reindex {no_chunks} documents with missing chunks",
                "description": "These documents exist but have no indexed content.",
                "action": "reindex",
                "count": no_chunks,
            })

        if outdated > 0:
            recommendations.append({
                "priority": "medium",
                "type": "outdated",
                "title": f"Update {outdated} documents with stale chunks",
                "description": "Document content has changed since last indexing.",
                "action": "reindex_incremental",
                "count": outdated,
            })

    # Warning: Low quality
    low_quality_percent = (
        health.quality_distribution.low / health.quality_distribution.total * 100
        if health.quality_distribution.total > 0
        else 0
    )
    if low_quality_percent > 20:
        recommendations.append({
            "priority": "medium",
            "type": "quality",
            "title": f"Improve chunk quality ({int(low_quality_percent)}% low quality)",
            "description": "Low-quality chunks may have incomplete content or missing headers.",
            "action": "review_content",
            "count": health.quality_distribution.low,
        })

    # Info: High archive rate
    archive_percent = (
        health.tier_distribution.archive / health.tier_distribution.total * 100
        if health.tier_distribution.total > 0
        else 0
    )
    if archive_percent > 50:
        recommendations.append({
            "priority": "low",
            "type": "archive",
            "title": f"Many chunks archived ({int(archive_percent)}%)",
            "description": "Archived chunks are rarely accessed. Consider if this content is still relevant.",
            "action": "review_content",
        })

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda r: priority_order.get(r["priority"], 99))

    return recommendations
