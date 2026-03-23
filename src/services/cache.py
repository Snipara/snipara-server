"""Query result caching service.

Caches context query results for Team+ plans to improve response times
for similar queries.

Architecture:
- L1 Cache: Redis (in-memory, sub-millisecond lookups)
- L2 Cache: PostgreSQL QueryCache table (persistent, 10-50ms lookups)

Cache hit flow:
1. Check L1 (Redis) → if hit, record L1 hit stats, return
2. Check L2 (PostgreSQL) → if hit, record L2 hit stats, populate L1, return
3. Miss → execute query, record L1+L2 miss stats, populate both caches
"""

import hashlib
import json
import logging
import time
from typing import Any

from ..config import settings
from .cache_stats import (
    generate_query_hash,
    get_l2_cached_result,
    record_cache_hit,
    record_cache_miss,
    set_l2_cached_result,
)

logger = logging.getLogger(__name__)

# Redis client - lazy initialized
_redis: Any | None = None


async def get_redis():
    """Get or create Redis connection."""
    global _redis
    if _redis is None:
        try:
            import redis.asyncio as redis

            _redis = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            return None
    return _redis


def _generate_cache_key(project_id: str, query: str, max_tokens: int, search_mode: str = "keyword") -> str:
    """Generate a cache key for a query."""
    query_hash = generate_query_hash(query, max_tokens, search_mode)
    return f"rlm:context:{project_id}:{query_hash}"


class QueryCache:
    """Cache for context query results."""

    # Cache TTL in seconds (1 hour)
    DEFAULT_TTL = 3600

    def __init__(self, project_id: str):
        """Initialize cache for a project.

        Args:
            project_id: The project ID
        """
        self.project_id = project_id

    async def get(self, query: str, max_tokens: int) -> dict[str, Any] | None:
        """Get cached result for a query.

        Args:
            query: The query string
            max_tokens: Token budget

        Returns:
            Cached result dict or None if not found
        """
        redis = await get_redis()
        if redis is None:
            return None

        try:
            cache_key = _generate_cache_key(self.project_id, query, max_tokens)
            cached = await redis.get(cache_key)

            if cached:
                logger.debug(f"Cache hit for query: {query[:50]}...")
                return json.loads(cached)

            logger.debug(f"Cache miss for query: {query[:50]}...")
            return None

        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    async def set(
        self,
        query: str,
        max_tokens: int,
        result: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """Cache a query result.

        Args:
            query: The query string
            max_tokens: Token budget
            result: The result to cache
            ttl: Time-to-live in seconds (default: 1 hour)

        Returns:
            True if cached successfully
        """
        redis = await get_redis()
        if redis is None:
            return False

        try:
            cache_key = _generate_cache_key(self.project_id, query, max_tokens)
            ttl = ttl or self.DEFAULT_TTL

            await redis.setex(
                cache_key,
                ttl,
                json.dumps(result),
            )

            logger.debug(f"Cached result for query: {query[:50]}... (TTL: {ttl}s)")
            return True

        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    async def invalidate(self, pattern: str | None = None) -> int:
        """Invalidate cache entries.

        Args:
            pattern: Optional pattern to match (e.g., for specific queries).
                    If None, invalidates all cache for this project.

        Returns:
            Number of keys deleted
        """
        redis = await get_redis()
        if redis is None:
            return 0

        try:
            if pattern:
                cache_pattern = f"rlm:context:{self.project_id}:{pattern}*"
            else:
                cache_pattern = f"rlm:context:{self.project_id}:*"

            # Find all matching keys
            keys = []
            async for key in redis.scan_iter(match=cache_pattern):
                keys.append(key)

            if keys:
                deleted = await redis.delete(*keys)
                logger.info(f"Invalidated {deleted} cache entries for project {self.project_id}")
                return deleted

            return 0

        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")
            return 0

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics for this project.

        Returns:
            Dict with cache statistics
        """
        redis = await get_redis()
        if redis is None:
            return {"available": False}

        try:
            cache_pattern = f"rlm:context:{self.project_id}:*"

            # Count keys
            count = 0
            total_size = 0
            async for key in redis.scan_iter(match=cache_pattern):
                count += 1
                # Get size of each key's value
                value = await redis.get(key)
                if value:
                    total_size += len(value)

            return {
                "available": True,
                "project_id": self.project_id,
                "cached_queries": count,
                "total_size_bytes": total_size,
                "ttl_seconds": self.DEFAULT_TTL,
            }

        except Exception as e:
            logger.warning(f"Cache stats error: {e}")
            return {"available": False, "error": str(e)}


class SimilarQueryCache:
    """Cache that also matches semantically similar queries.

    For Team+ plans, this provides fuzzy matching for similar queries
    to maximize cache hits.
    """

    # Similarity threshold (0-1, higher = more similar required)
    SIMILARITY_THRESHOLD = 0.85

    def __init__(self, project_id: str):
        """Initialize similar query cache.

        Args:
            project_id: The project ID
        """
        self.project_id = project_id
        self.base_cache = QueryCache(project_id)

    async def get(self, query: str, max_tokens: int) -> tuple[dict[str, Any] | None, bool]:
        """Get cached result, including similar query matches.

        Args:
            query: The query string
            max_tokens: Token budget

        Returns:
            Tuple of (cached result, is_exact_match)
        """
        # First try exact match
        exact_result = await self.base_cache.get(query, max_tokens)
        if exact_result:
            return exact_result, True

        # For similar query matching, we'd need embeddings
        # This is a placeholder for future semantic matching
        # TODO: Implement semantic similarity matching using embeddings

        return None, False

    async def set(
        self,
        query: str,
        max_tokens: int,
        result: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """Cache a query result.

        Args:
            query: The query string
            max_tokens: Token budget
            result: The result to cache
            ttl: Time-to-live in seconds

        Returns:
            True if cached successfully
        """
        return await self.base_cache.set(query, max_tokens, result, ttl)


class TieredCache:
    """Two-tier cache with L1 (Redis) and L2 (PostgreSQL) layers.

    Automatically records cache hits/misses to CacheStats for dashboard visualization.

    Cache flow:
    1. Check L1 (Redis) → fast, sub-millisecond
    2. If L1 miss, check L2 (PostgreSQL) → slower, but persistent
    3. If L2 hit, populate L1 for future requests
    4. If both miss, return None and let caller populate caches
    """

    # Cache TTL in seconds
    DEFAULT_L1_TTL = 3600  # 1 hour
    DEFAULT_L2_TTL = 3600  # 1 hour

    def __init__(self, project_id: str, search_mode: str = "keyword"):
        """Initialize tiered cache for a project.

        Args:
            project_id: The project ID
            search_mode: Search mode for cache key generation
        """
        self.project_id = project_id
        self.search_mode = search_mode
        self._l1_cache = QueryCache(project_id)

    async def get(
        self,
        query: str,
        max_tokens: int,
        estimate_compute_ms: int = 100,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Get cached result from L1 or L2.

        Args:
            query: The query string
            max_tokens: Token budget
            estimate_compute_ms: Estimated compute time in ms (for stats)

        Returns:
            Tuple of (cached result, cache_level) where cache_level is "l1", "l2", or None
        """
        start_time = time.perf_counter()
        query_hash = generate_query_hash(query, max_tokens, self.search_mode)

        # Try L1 (Redis) first
        l1_result = await self._l1_cache.get(query, max_tokens)
        if l1_result:
            # L1 hit - record stats
            tokens_saved = l1_result.get("totalTokens", l1_result.get("total_tokens", 0))
            compute_ms = int((time.perf_counter() - start_time) * 1000)
            await record_cache_hit(
                self.project_id,
                "l1",
                tokens_saved,
                max(estimate_compute_ms - compute_ms, 0),
            )
            logger.info(f"L1 cache hit for {query[:50]}... ({tokens_saved} tokens)")
            return l1_result, "l1"

        # L1 miss - try L2 (PostgreSQL)
        await record_cache_miss(self.project_id, "l1")

        l2_result = await get_l2_cached_result(self.project_id, query_hash)
        if l2_result:
            # L2 hit - record stats and populate L1
            tokens_saved = l2_result.get("totalTokens", l2_result.get("total_tokens", 0))
            compute_ms = int((time.perf_counter() - start_time) * 1000)
            await record_cache_hit(
                self.project_id,
                "l2",
                tokens_saved,
                max(estimate_compute_ms - compute_ms, 0),
            )

            # Populate L1 for future requests
            await self._l1_cache.set(query, max_tokens, l2_result, self.DEFAULT_L1_TTL)

            logger.info(f"L2 cache hit for {query[:50]}... ({tokens_saved} tokens)")
            return l2_result, "l2"

        # Both L1 and L2 miss
        await record_cache_miss(self.project_id, "l2")
        logger.debug(f"Cache miss (L1+L2) for {query[:50]}...")
        return None, None

    async def set(
        self,
        query: str,
        max_tokens: int,
        result: dict[str, Any],
        l1_ttl: int | None = None,
        l2_ttl: int | None = None,
    ) -> bool:
        """Store result in both L1 and L2 caches.

        Args:
            query: The query string
            max_tokens: Token budget
            result: The result to cache
            l1_ttl: L1 cache TTL (default: 1 hour)
            l2_ttl: L2 cache TTL (default: 1 hour)

        Returns:
            True if cached successfully in at least one tier
        """
        l1_ttl = l1_ttl or self.DEFAULT_L1_TTL
        l2_ttl = l2_ttl or self.DEFAULT_L2_TTL
        query_hash = generate_query_hash(query, max_tokens, self.search_mode)

        # Store in L1
        l1_success = await self._l1_cache.set(query, max_tokens, result, l1_ttl)

        # Store in L2
        sections = result.get("sections", [])
        total_tokens = result.get("totalTokens", result.get("total_tokens", 0))
        suggestions = result.get("suggestions", [])

        l2_success = await set_l2_cached_result(
            self.project_id,
            query_hash,
            sections,
            total_tokens,
            suggestions,
            l2_ttl,
        )

        logger.debug(f"Cached in L1={l1_success}, L2={l2_success} for {query[:50]}...")
        return l1_success or l2_success

    async def invalidate(self) -> tuple[int, int]:
        """Invalidate all cache entries for this project.

        Returns:
            Tuple of (l1_deleted, l2_deleted)
        """
        from .cache_stats import invalidate_l2_cache

        l1_deleted = await self._l1_cache.invalidate()
        l2_deleted = await invalidate_l2_cache(self.project_id)
        return l1_deleted, l2_deleted


# Factory function
def get_cache(project_id: str, use_similarity: bool = False) -> QueryCache:
    """Get a cache instance for a project.

    Args:
        project_id: The project ID
        use_similarity: Whether to use similar query matching (Team+ only)

    Returns:
        QueryCache or SimilarQueryCache instance
    """
    if use_similarity:
        return SimilarQueryCache(project_id)
    return QueryCache(project_id)


def get_tiered_cache(project_id: str, search_mode: str = "keyword") -> TieredCache:
    """Get a tiered cache instance for a project.

    This is the recommended cache for context queries as it uses both
    L1 (Redis) and L2 (PostgreSQL) layers and records statistics.

    Args:
        project_id: The project ID
        search_mode: Search mode for cache key generation

    Returns:
        TieredCache instance
    """
    return TieredCache(project_id, search_mode)
