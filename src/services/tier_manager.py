# apps/mcp-server/src/services/tier_manager.py
"""Tier management for document chunks based on access patterns."""

from datetime import UTC, datetime

from src.models.enums import ChunkTier

# Tier thresholds
TIER_CONFIG = {
    "hot": {
        "max_age_hours": 24,
        "min_relevance": 0.7,
        "min_access_count": 2,
    },
    "warm": {
        "max_age_days": 7,
        "min_relevance": 0.4,
        "min_access_count": 1,
    },
    "cold": {
        "max_age_days": 30,
        "min_relevance": 0.0,
    },
    "archive": {
        "min_age_days": 30,
    },
}


def compute_tier(
    last_accessed: datetime | None,
    avg_relevance: float,
    access_count: int,
    now: datetime | None = None,
) -> ChunkTier:
    """
    Compute the appropriate tier for a chunk based on access patterns.

    Rules:
    - HOT: accessed < 24h AND (relevance > 0.7 OR access_count >= 2)
    - WARM: accessed < 7d AND (relevance > 0.4 OR access_count >= 1)
    - COLD: accessed < 30d
    - ARCHIVE: accessed > 30d OR never accessed
    """
    now = now or datetime.now(tz=UTC)

    if last_accessed is None:
        return ChunkTier.COLD

    age = now - last_accessed
    hours_old = age.total_seconds() / 3600
    days_old = age.days

    # HOT tier
    if hours_old < 24:
        if avg_relevance >= 0.7 or access_count >= 2:
            return ChunkTier.HOT
        return ChunkTier.WARM

    # WARM tier
    if days_old < 7:
        if avg_relevance >= 0.4 or access_count >= 1:
            return ChunkTier.WARM
        return ChunkTier.COLD

    # COLD tier
    if days_old < 30:
        return ChunkTier.COLD

    # ARCHIVE tier
    return ChunkTier.ARCHIVE


def should_promote(
    current_tier: ChunkTier,
    avg_relevance: float,
    access_count: int,
    new_relevance: float,
) -> ChunkTier | None:
    """Check if a chunk should be promoted to a higher tier."""
    # Update running average
    new_avg = (avg_relevance * access_count + new_relevance) / (access_count + 1)

    new_tier = compute_tier(
        last_accessed=datetime.now(tz=UTC),
        avg_relevance=new_avg,
        access_count=access_count + 1,
    )

    # Tier hierarchy: HOT > WARM > COLD > ARCHIVE
    tier_order = [ChunkTier.ARCHIVE, ChunkTier.COLD, ChunkTier.WARM, ChunkTier.HOT]

    if tier_order.index(new_tier) > tier_order.index(current_tier):
        return new_tier

    return None


async def update_chunk_access(
    db,
    chunk_id: str,
    relevance_score: float,
) -> None:
    """Update chunk access statistics and potentially promote tier."""
    chunk = await db.documentchunk.find_unique(where={"id": chunk_id})
    if not chunk:
        return

    new_access_count = (chunk.accessCount or 0) + 1
    old_avg = chunk.avgRelevance or 0.0
    old_count = chunk.accessCount or 0

    new_avg_relevance = (old_avg * old_count + relevance_score) / new_access_count

    new_tier = compute_tier(
        last_accessed=datetime.now(tz=UTC),
        avg_relevance=new_avg_relevance,
        access_count=new_access_count,
    )

    await db.documentchunk.update(
        where={"id": chunk_id},
        data={
            "lastAccessed": datetime.now(tz=UTC),
            "accessCount": new_access_count,
            "avgRelevance": new_avg_relevance,
            "tier": new_tier.value,
        },
    )


async def batch_update_chunk_access(
    db,
    chunk_relevance_pairs: list[tuple[str, float]],
) -> None:
    """
    Batch update chunk access statistics.

    Args:
        db: Database client
        chunk_relevance_pairs: List of (chunk_id, relevance_score) tuples
    """
    for chunk_id, relevance_score in chunk_relevance_pairs:
        await update_chunk_access(db, chunk_id, relevance_score)
