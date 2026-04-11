"""Agent Memory Service for Phase 8.2.

Provides semantic memory storage and recall for AI agents.
Memories can have types (FACT, DECISION, LEARNING, etc.), scopes,
and TTL with confidence decay over time.
"""

import asyncio
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from ..config import settings
from ..db import get_db
from ..models.enums import AgentMemoryType
from ..models.memory_v2 import (
    MemoryEvidencePayload,
    MemoryMigrationMapPayload,
    MemoryRelationPayload,
    MemoryUpdatePayload,
)
from .memory_mapper import map_agent_memory_to_memory_payload
from .memory_repository import MemoryRepository
from .cache import get_redis
from .embeddings import EMBEDDING_DIMENSION, get_embeddings_service

logger = logging.getLogger(__name__)

# Cache key prefixes
MEMORY_EMBEDDING_PREFIX = "rlm:mem_emb:"  # Memory embedding storage
MEMORY_EMBEDDING_TTL = 60 * 60 * 24 * 7  # 7 days default

# Confidence decay settings
CONFIDENCE_DECAY_RATE = 0.01  # 1% decay per day
MIN_CONFIDENCE = 0.1  # Minimum confidence after decay

# Auto-compaction settings
AUTO_COMPACT_THRESHOLD = 500  # Trigger compaction when memory count exceeds this
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

    Batches requests to avoid exceeding Upstash's 10MB response limit.
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
    BATCH_SIZE = 400
    result: dict[str, list[float]] = {}

    try:
        # Process in batches to avoid Upstash 10MB limit
        for i in range(0, len(memory_ids), BATCH_SIZE):
            batch_ids = memory_ids[i : i + BATCH_SIZE]
            keys = [f"{MEMORY_EMBEDDING_PREFIX}{mid}" for mid in batch_ids]

            try:
                values = await redis.mget(keys)
            except Exception as batch_error:
                # If batch still fails, try smaller batches
                if BATCH_SIZE > 100:
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
    db = await get_db()

    # Calculate expiration
    expires_at = None
    if ttl_days:
        expires_at = datetime.now(UTC) + timedelta(days=ttl_days)

    # Map string types to enum values (Prisma expects uppercase)
    memory_type_upper = memory_type.upper()
    scope_upper = scope.upper()

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
        }
    )

    # Generate and store embedding
    try:
        embeddings_service = get_embeddings_service()
        embedding = await embeddings_service.embed_text_async(content)

        # TTL for embedding based on memory TTL
        embedding_ttl = MEMORY_EMBEDDING_TTL
        if ttl_days:
            embedding_ttl = min(ttl_days * 24 * 60 * 60, MEMORY_EMBEDDING_TTL)

        await _store_memory_embedding(memory.id, embedding, embedding_ttl)
        logger.info(f"Stored memory {memory.id} with embedding")
    except Exception as e:
        logger.warning(f"Failed to generate embedding for memory {memory.id}: {e}")
        # Memory is still created, just without embedding

    # Trigger auto-compaction check (non-blocking)
    asyncio.create_task(_safe_auto_compact(project_id))

    if settings.memory_v2_dual_write:
        asyncio.create_task(
            _dual_write_memory_v2(
                legacy_memory=memory,
                memory_type=memory_type,
                scope=scope,
                ttl_days=ttl_days,
                source=source,
            )
        )

    return {
        "memory_id": memory.id,
        "content": memory.content,
        "type": memory_type,
        "scope": scope,
        "category": category,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "created": True,
        "message": f"Memory stored successfully (ID: {memory.id})",
    }


async def _dual_write_legacy_memory_object(legacy_memory: Any) -> str | None:
    """Persist a legacy AgentMemory ORM row into Memory V2."""

    mapped = map_agent_memory_to_memory_payload(legacy_memory)
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
) -> None:
    """Best-effort dual-write of legacy AgentMemory into Memory V2."""

    try:
        memory_v2_id = await _dual_write_legacy_memory_object(legacy_memory)
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

    if not settings.memory_v2_dual_write:
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

    db = await get_db()
    created_ids: list[str] = []
    failed: list[dict[str, Any]] = []
    texts: list[str] = []
    created_memories: list[Any] = []

    # Process each memory
    for i, mem in enumerate(memories):
        text = mem.get("text", "")
        if not text:
            failed.append({"index": i, "error": "text is required"})
            continue

        memory_type = mem.get("type", "fact").upper()
        scope = mem.get("scope", "project").upper()
        category = mem.get("category")
        ttl_days = mem.get("ttl_days")
        related_to = mem.get("related_to")
        document_refs = mem.get("document_refs")

        # Calculate expiration
        expires_at = None
        if ttl_days:
            expires_at = datetime.now(UTC) + timedelta(days=ttl_days)

        try:
            memory = await db.agentmemory.create(
                data={
                    "projectId": project_id,
                    "content": text,
                    "type": memory_type,
                    "scope": scope,
                    "category": category,
                    "expiresAt": expires_at,
                    "relatedMemoryIds": related_to or [],
                    "documentRefs": document_refs or [],
                    "source": source,
                    "confidence": 1.0,
                    "accessCount": 0,
                }
            )
            created_memories.append(memory)
            created_ids.append(memory.id)
            texts.append(text)
        except Exception as e:
            logger.warning(f"Failed to create memory at index {i}: {e}")
            failed.append({"index": i, "error": str(e)})

    # Batch generate embeddings for all created memories
    if texts:
        try:
            embeddings_service = get_embeddings_service()
            embeddings = await embeddings_service.embed_texts_async(texts)

            # Store embeddings in parallel
            embedding_ttl = MEMORY_EMBEDDING_TTL
            tasks = [
                _store_memory_embedding(mem.id, emb, embedding_ttl)
                for mem, emb in zip(created_memories, embeddings)
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            logger.info(f"Stored {len(created_ids)} memories with batch embeddings")
        except Exception as e:
            logger.warning(f"Failed to generate batch embeddings: {e}")
            # Memories still created, just without embeddings

    if settings.memory_v2_dual_write and created_memories:
        try:
            await asyncio.gather(
                *(_dual_write_legacy_memory_object(memory) for memory in created_memories),
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


async def semantic_recall(
    project_id: str,
    query: str,
    memory_type: str | None = None,
    scope: str | None = None,
    category: str | None = None,
    limit: int = 5,
    min_relevance: float = 0.5,
    include_expired: bool = False,
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

    Returns:
        Dict with recalled memories and metadata
    """
    import time

    start_time = time.time()

    db = await get_db()
    embeddings_service = get_embeddings_service()

    # Build filter
    where: dict[str, Any] = {"projectId": project_id}
    if memory_type:
        where["type"] = memory_type.upper()
    if scope:
        where["scope"] = scope.upper()
    if category:
        where["category"] = category
    if not include_expired:
        where["OR"] = [
            {"expiresAt": None},
            {"expiresAt": {"gt": datetime.now(UTC)}},
        ]

    # Get all matching memories
    memories = await db.agentmemory.find_many(
        where=where,
        order={"createdAt": "desc"},
        take=500,  # Limit to prevent huge queries
    )

    if not memories:
        return {
            "memories": [],
            "total_searched": 0,
            "query": query,
            "timing_ms": int((time.time() - start_time) * 1000),
        }

    # Generate query embedding
    try:
        query_embedding = await embeddings_service.embed_text_async(query)
    except Exception as e:
        logger.error(f"Failed to embed query: {e}")
        # Fallback to text search if embedding fails
        return await _text_search_fallback(memories, query, limit, min_relevance, start_time)

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
                embedding = await embeddings_service.embed_text_async(memory.content)
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
        return {
            "memories": [],
            "total_searched": len(memories),
            "query": query,
            "timing_ms": int((time.time() - start_time) * 1000),
        }

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
        return await _text_search_fallback(memories, query, limit, min_relevance, start_time)

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

        if relevance >= min_relevance:
            results.append(
                {
                    "memory_id": memory.id,
                    "content": memory.content,
                    "type": memory.type.lower(),
                    "scope": memory.scope.lower(),
                    "category": memory.category,
                    "relevance": round(relevance, 4),
                    "confidence": round(decayed_confidence, 4),
                    "created_at": memory.createdAt.isoformat(),
                    "last_accessed_at": memory.lastAccessedAt.isoformat()
                    if memory.lastAccessedAt
                    else None,
                    "access_count": memory.accessCount,
                }
            )

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

    query_terms = set(query.lower().split())
    results = []

    for memory in memories:
        content_terms = set(memory.content.lower().split())
        overlap = len(query_terms & content_terms)

        if overlap > 0:
            # Simple relevance based on term overlap
            relevance = overlap / max(len(query_terms), 1)

            if relevance >= min_relevance:
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
                        "relevance": round(relevance * decayed_confidence, 4),
                        "confidence": round(decayed_confidence, 4),
                        "created_at": memory.createdAt.isoformat(),
                        "last_accessed_at": memory.lastAccessedAt.isoformat()
                        if memory.lastAccessedAt
                        else None,
                        "access_count": memory.accessCount,
                    }
                )

    results.sort(key=lambda x: x["relevance"], reverse=True)
    results = results[:limit]

    return {
        "memories": results,
        "total_searched": len(memories),
        "query": query,
        "timing_ms": int((time.time() - start_time) * 1000),
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
    sort_by: str = "created_at",
    sort_order: str = "desc",
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
    db = await get_db()

    # Build filter
    where: dict[str, Any] = {"projectId": project_id}
    if memory_type:
        where["type"] = memory_type.upper()
    if scope:
        where["scope"] = scope.upper()
    if category:
        where["category"] = category
    if search:
        where["content"] = {"contains": search, "mode": "insensitive"}
    if not include_expired:
        where["OR"] = [
            {"expiresAt": None},
            {"expiresAt": {"gt": datetime.now(UTC)}},
        ]

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
        "has_more": (offset + limit) < total_count,
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
    db = await get_db()

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    category = f"journal:{today}"

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

    entries = await db.agentmemory.find_many(
        where={
            "projectId": project_id,
            "type": "CONTEXT",
            "category": {"in": categories},
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
        [
            f"**{e['created_at'][:19]}**\n{e['text']}"
            for e in journal["entries"]
        ]
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
        where["id"] = memory_id
    if memory_type:
        where["type"] = memory_type.upper()
    if category:
        where["category"] = category
    if older_than_days:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        where["createdAt"] = {"lt": cutoff}

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
        return {
            "error": f"Memory '{memory_id}' not found in Memory V2",
            "memory_id": memory_id,
        }

    await _memory_repository.invalidate_memory(resolved_id, target_time)
    return {
        "memory_id": resolved_id,
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

    if resolved_old_id is None:
        return {"error": f"Memory '{old_memory_id}' not found in Memory V2", "memory_id": old_memory_id}
    if resolved_new_id is None:
        return {"error": f"Memory '{new_memory_id}' not found in Memory V2", "memory_id": new_memory_id}

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
                        where={"projectId": memory.projectId, "path": external_ref, "deletedAt": None}
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
        indexed_docs = await db.document.find_many(
            where={"projectId": project_id},
        )
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
                    logger.warning(f"Failed to embed memory {memory.id} for conflict detection: {e}")

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
                    "tier": "ARCHIVE",
                    "category": f"{older.category or 'uncategorized'}:superseded",
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
        older_conf = calculate_confidence_decay(older.confidence, older.createdAt, older.lastAccessedAt)
        newer_conf = calculate_confidence_decay(newer.confidence, newer.createdAt, newer.lastAccessedAt)

        if older_conf > newer_conf:
            to_archive, to_keep = newer, older
        else:
            to_archive, to_keep = older, newer

        if not dry_run:
            await db.agentmemory.update(
                where={"id": to_archive.id},
                data={
                    "tier": "ARCHIVE",
                    "category": f"{to_archive.category or 'uncategorized'}:superseded",
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
                    "tier": "ARCHIVE",
                    "category": f"{older.category or 'uncategorized'}:merged",
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

    # Get CRITICAL tier memories
    critical = await db.agentmemory.find_many(
        where={
            "projectId": project_id,
            "tier": "CRITICAL",
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
    }

    daily = await db.agentmemory.find_many(
        where=daily_filter,
        order={"createdAt": "desc"},
    )

    # Budget tokens (approximate: 4 chars = 1 token)
    def budget_memories(memories: list, max_tokens: int) -> list[dict]:
        result = []
        total_tokens = 0
        for m in memories:
            # Estimate tokens
            mem_tokens = len(m.content) // 4
            if total_tokens + mem_tokens > max_tokens:
                break
            result.append(
                {
                    "id": m.id,
                    "content": m.content,
                    "type": m.type,
                    "category": m.category,
                    "confidence": calculate_confidence_decay(
                        m.confidence, m.createdAt, m.lastAccessedAt
                    ),
                    "created_at": m.createdAt.isoformat() if m.createdAt else None,
                }
            )
            total_tokens += mem_tokens
        return result

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
    conflict_strategy: str = "newer",
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
        where={"projectId": project_id},
        order={"createdAt": "asc"},
    )

    # ─────────────────────────────────────────────────────────
    # Phase 1: Date Normalization (NEW)
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
    # Phase 2: Dead Reference Cleanup (NEW)
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
    # Phase 3: Semantic Conflict Resolution (NEW)
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
                    archived_mem = next((m for m in all_memories if m.id == resolution["archived_id"]), None)
                    if archived_mem:
                        results["tokens_freed"] += len(archived_mem.content) // 4

            results["conflict_details"].append(resolution)

    # ─────────────────────────────────────────────────────────
    # Phase 4: Exact Duplicate Removal (existing logic)
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

        if not dry_run and duplicates_to_delete:
            await db.agentmemory.delete_many(
                where={"id": {"in": duplicates_to_delete}},
            )

    # ─────────────────────────────────────────────────────────
    # Phase 5: Promote Frequently Accessed Learnings (existing)
    # ─────────────────────────────────────────────────────────
    learnings = await db.agentmemory.find_many(
        where={
            "projectId": project_id,
            "type": "LEARNING",
            "accessCount": {"gte": promote_threshold},
            "tier": {"not": "CRITICAL"},
        },
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
    # Phase 6: Archive Old Memories (existing)
    # ─────────────────────────────────────────────────────────
    cutoff = now - timedelta(days=archive_older_than_days)
    old_memories = await db.agentmemory.find_many(
        where={
            "projectId": project_id,
            "tier": {"not": "CRITICAL"},
            "createdAt": {"lt": cutoff},
        },
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
        results["message"] = f"{action}: {', '.join(parts)} (~{results['tokens_freed']} tokens freed)"
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
            where={"projectId": project_id}
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

        # Run compaction with consolidation features enabled
        # Note: Auto-compact uses "newer" strategy to avoid flagging during automatic runs
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
            conflict_strategy="newer",  # Auto-resolve, don't flag
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
        },
        order={"confidence": "desc"},
        take=max_items // 2,
    )

    # Get active todos
    todos = await db.agentmemory.find_many(
        where={
            "projectId": project_id,
            "type": "TODO",
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
