"""Cache statistics tracking service.

Records L1 (Redis) and L2 (database) cache hits/misses to PostgreSQL
for dashboard visualization and analytics.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..db import get_db

logger = logging.getLogger(__name__)

# Default cache TTL for L2 (database) cache
DEFAULT_L2_TTL_SECONDS = 3600  # 1 hour


def generate_query_hash(query: str, max_tokens: int, search_mode: str = "keyword") -> str:
    """Generate a deterministic hash for a query.

    Args:
        query: The query string
        max_tokens: Token budget
        search_mode: Search mode (keyword, semantic, hybrid)

    Returns:
        SHA-256 hash of normalized query parameters
    """
    normalized_query = query.lower().strip()
    params = f"{normalized_query}|{max_tokens}|{search_mode}"
    return hashlib.sha256(params.encode()).hexdigest()


async def record_cache_hit(
    project_id: str,
    level: str,
    tokens_saved: int,
    compute_ms_saved: int,
) -> None:
    """Record a cache hit and update statistics.

    Args:
        project_id: The project ID
        level: Cache level ("l1" or "l2")
        tokens_saved: Number of tokens saved by cache hit
        compute_ms_saved: Milliseconds of compute time saved
    """
    try:
        db = await get_db()

        # Build the increment fields based on cache level
        if level == "l1":
            increment_field = "l1Hits"
        else:
            increment_field = "l2Hits"

        # Upsert the cache stats record
        await db.cachestats.upsert(
            where={"projectId": project_id},
            data={
                "create": {
                    "projectId": project_id,
                    "l1Hits": 1 if level == "l1" else 0,
                    "l2Hits": 1 if level == "l2" else 0,
                    "l1Misses": 0,
                    "l2Misses": 0,
                    "tokensSaved": tokens_saved,
                    "computeMsSaved": compute_ms_saved,
                    "periodStart": datetime.now(timezone.utc),
                },
                "update": {
                    increment_field: {"increment": 1},
                    "tokensSaved": {"increment": tokens_saved},
                    "computeMsSaved": {"increment": compute_ms_saved},
                },
            },
        )
        logger.debug(f"Recorded {level} cache hit for project {project_id}")
    except Exception as e:
        logger.warning(f"Failed to record cache hit: {e}")


async def record_cache_miss(project_id: str, level: str) -> None:
    """Record a cache miss.

    Args:
        project_id: The project ID
        level: Cache level ("l1" or "l2")
    """
    try:
        db = await get_db()

        if level == "l1":
            increment_field = "l1Misses"
        else:
            increment_field = "l2Misses"

        await db.cachestats.upsert(
            where={"projectId": project_id},
            data={
                "create": {
                    "projectId": project_id,
                    "l1Hits": 0,
                    "l2Hits": 0,
                    "l1Misses": 1 if level == "l1" else 0,
                    "l2Misses": 1 if level == "l2" else 0,
                    "tokensSaved": 0,
                    "computeMsSaved": 0,
                    "periodStart": datetime.now(timezone.utc),
                },
                "update": {
                    increment_field: {"increment": 1},
                },
            },
        )
        logger.debug(f"Recorded {level} cache miss for project {project_id}")
    except Exception as e:
        logger.warning(f"Failed to record cache miss: {e}")


async def get_l2_cached_result(
    project_id: str,
    query_hash: str,
) -> dict[str, Any] | None:
    """Get a cached result from L2 (database) cache.

    Args:
        project_id: The project ID
        query_hash: The query hash

    Returns:
        Cached result dict or None if not found/expired
    """
    try:
        db = await get_db()

        entry = await db.querycache.find_first(
            where={
                "projectId": project_id,
                "queryHash": query_hash,
                "expiresAt": {"gt": datetime.now(timezone.utc)},
            },
        )

        if entry:
            # Update hit count and last hit time
            await db.querycache.update(
                where={"id": entry.id},
                data={
                    "hitCount": {"increment": 1},
                    "lastHitAt": datetime.now(timezone.utc),
                },
            )

            logger.debug(f"L2 cache hit for query {query_hash[:16]}...")
            return {
                "sections": entry.sections,
                "totalTokens": entry.totalTokens,
                "suggestions": entry.suggestions,
            }

        return None
    except Exception as e:
        logger.warning(f"Failed to get L2 cache: {e}")
        return None


async def set_l2_cached_result(
    project_id: str,
    query_hash: str,
    sections: list[dict[str, Any]],
    total_tokens: int,
    suggestions: list[str] | None = None,
    ttl_seconds: int = DEFAULT_L2_TTL_SECONDS,
    document_versions: dict[str, str] | None = None,
) -> bool:
    """Store a result in L2 (database) cache.

    Args:
        project_id: The project ID
        query_hash: The query hash
        sections: List of section dicts to cache
        total_tokens: Total tokens in the result
        suggestions: Optional list of suggestions
        ttl_seconds: Cache TTL in seconds
        document_versions: Optional dict of document IDs to version hashes

    Returns:
        True if cached successfully
    """
    try:
        db = await get_db()

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

        # Ensure sections is JSON serializable
        sections_json = json.dumps(sections) if isinstance(sections, list) else sections
        # Prisma Json fields need proper JSON - use Json.null for empty
        doc_versions_json = json.dumps(document_versions) if document_versions else "{}"

        await db.querycache.upsert(
            where={
                "projectId_queryHash": {
                    "projectId": project_id,
                    "queryHash": query_hash,
                }
            },
            data={
                "create": {
                    "project": {"connect": {"id": project_id}},
                    "queryHash": query_hash,
                    "sections": sections_json,
                    "totalTokens": total_tokens,
                    "suggestions": suggestions or [],
                    "expiresAt": expires_at,
                    "documentVersions": doc_versions_json,
                    "hitCount": 0,
                },
                "update": {
                    "sections": sections_json,
                    "totalTokens": total_tokens,
                    "suggestions": suggestions or [],
                    "expiresAt": expires_at,
                    "documentVersions": doc_versions_json,
                },
            },
        )

        logger.debug(f"Cached result in L2 for query {query_hash[:16]}... (TTL: {ttl_seconds}s)")
        return True
    except Exception as e:
        logger.warning(f"Failed to set L2 cache: {e}")
        return False


async def invalidate_l2_cache(project_id: str, pattern: str | None = None) -> int:
    """Invalidate L2 cache entries for a project.

    Args:
        project_id: The project ID
        pattern: Optional query hash prefix to match

    Returns:
        Number of entries deleted
    """
    try:
        db = await get_db()

        if pattern:
            # Delete entries matching the pattern
            result = await db.querycache.delete_many(
                where={
                    "projectId": project_id,
                    "queryHash": {"startswith": pattern},
                },
            )
        else:
            # Delete all entries for the project
            result = await db.querycache.delete_many(
                where={"projectId": project_id},
            )

        logger.info(f"Invalidated {result} L2 cache entries for project {project_id}")
        return result
    except Exception as e:
        logger.warning(f"Failed to invalidate L2 cache: {e}")
        return 0


async def cleanup_expired_l2_cache(project_id: str | None = None) -> int:
    """Clean up expired L2 cache entries.

    Args:
        project_id: Optional project ID to limit cleanup

    Returns:
        Number of entries deleted
    """
    try:
        db = await get_db()

        where: dict[str, Any] = {
            "expiresAt": {"lte": datetime.now(timezone.utc)},
        }
        if project_id:
            where["projectId"] = project_id

        result = await db.querycache.delete_many(where=where)
        logger.info(f"Cleaned up {result} expired L2 cache entries")
        return result
    except Exception as e:
        logger.warning(f"Failed to cleanup expired L2 cache: {e}")
        return 0
