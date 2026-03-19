"""Agent Memory Service for Phase 8.2.

Provides semantic memory storage and recall for AI agents.
Memories can have types (FACT, DECISION, LEARNING, etc.), scopes,
and TTL with confidence decay over time.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from ..db import get_db
from .cache import get_redis
from .embeddings import EMBEDDING_DIMENSION, get_embeddings_service

logger = logging.getLogger(__name__)

# Cache key prefixes
MEMORY_EMBEDDING_PREFIX = "rlm:mem_emb:"  # Memory embedding storage
MEMORY_EMBEDDING_TTL = 60 * 60 * 24 * 7  # 7 days default

# Confidence decay settings
CONFIDENCE_DECAY_RATE = 0.01  # 1% decay per day
MIN_CONFIDENCE = 0.1  # Minimum confidence after decay


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

    try:
        keys = [f"{MEMORY_EMBEDDING_PREFIX}{mid}" for mid in memory_ids]
        values = await redis.mget(keys)

        result = {}
        for mid, value in zip(memory_ids, values):
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


# ============ PHASE 20: MEMORY TIERS & COMPACTION ============

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
) -> dict[str, Any]:
    """Compact and optimize memories.

    Args:
        project_id: The project ID
        scope: Memory scope to compact (agent, project, team)
        deduplicate: Merge similar memories
        promote_threshold: If learning accessed N times, promote to CRITICAL
        archive_older_than_days: Archive memories older than N days
        dry_run: Preview changes without applying

    Returns:
        Dict with compaction results
    """
    db = await get_db()
    now = datetime.now(UTC)

    results = {
        "duplicates_merged": 0,
        "promoted_to_critical": 0,
        "archived": 0,
        "tokens_freed": 0,
        "dry_run": dry_run,
    }

    # 1. Promote frequently accessed learnings
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

    # 2. Archive old memories (except CRITICAL)
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

    # 3. Deduplicate similar memories (simplified version)
    # Note: Full semantic deduplication would require embedding comparison
    if deduplicate:
        # Group by category and type, find exact content matches
        all_memories = await db.agentmemory.find_many(
            where={"projectId": project_id},
            order={"createdAt": "asc"},
        )

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

    action = "Would have" if dry_run else "Successfully"
    results["message"] = (
        f"{action} promoted {results['promoted_to_critical']} learnings, "
        f"archived {results['archived']} old memories, "
        f"merged {results['duplicates_merged']} duplicates "
        f"(~{results['tokens_freed']} tokens freed)"
    )

    return results


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
