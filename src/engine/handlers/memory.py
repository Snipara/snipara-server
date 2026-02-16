"""Memory tool handlers for agent memory persistence.

Handles:
- rlm_remember: Store a memory for later recall
- rlm_recall: Semantically recall relevant memories
- rlm_memories: List memories with filters
- rlm_forget: Delete memories by ID or filter criteria
"""

from typing import Any

from ...models import ToolResult
from ...services.agent_limits import check_memory_limits
from ...services.agent_memory import (
    delete_memories,
    list_memories,
    semantic_recall,
    store_memory,
)
from .base import HandlerContext, count_tokens


async def handle_remember(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Store a memory for later recall.

    Args:
        params: Dict containing:
            - text: Memory text to store (preferred)
            - content: DEPRECATED - use 'text' instead (backward compat)
            - type: Memory type (fact, decision, learning, preference, todo, context)
            - scope: Visibility scope (agent, project, team, user)
            - category: Optional grouping category
            - ttl_days: Days until expiration
            - related_to: IDs of related memories
            - document_refs: Referenced document paths

    Returns:
        ToolResult with memory ID and confirmation
    """
    # Accept both 'text' (new) and 'content' (legacy), text takes precedence
    content = params.get("text") or params.get("content", "")
    memory_type = params.get("type", "fact")
    scope = params.get("scope", "project")
    category = params.get("category")
    ttl_days = params.get("ttl_days")
    related_to = params.get("related_to")
    document_refs = params.get("document_refs")

    if not content:
        return ToolResult(
            data={"error": "rlm_remember: missing required parameter 'text' (or 'content')"},
            input_tokens=0,
            output_tokens=0,
        )

    # Check memory limits
    allowed, error = await check_memory_limits(ctx.project_id, ctx.user_id)
    if not allowed:
        return ToolResult(
            data={"error": error, "upgrade_url": "/billing/upgrade"},
            input_tokens=count_tokens(content),
            output_tokens=0,
        )

    result = await store_memory(
        project_id=ctx.project_id,
        content=content,
        memory_type=memory_type,
        scope=scope,
        category=category,
        ttl_days=ttl_days,
        related_to=related_to,
        document_refs=document_refs,
        source="mcp",
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(content),
        output_tokens=count_tokens(str(result)),
    )


async def handle_remember_bulk(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Store multiple memories in bulk.

    Args:
        params: Dict containing:
            - memories: Array of memory objects (max 50), each with:
                - text: Memory text to store
                - type: Memory type (default: fact)
                - scope: Visibility scope (default: project)
                - category: Optional grouping category
                - ttl_days: Days until expiration
                - related_to: IDs of related memories
                - document_refs: Referenced document paths

    Returns:
        ToolResult with created memory IDs and stats
    """
    from ...services.agent_memory import store_memories_bulk

    memories = params.get("memories", [])

    if not memories:
        return ToolResult(
            data={"error": "rlm_remember_bulk: 'memories' array is required"},
            input_tokens=0,
            output_tokens=0,
        )

    if len(memories) > 50:
        return ToolResult(
            data={"error": "rlm_remember_bulk: max 50 memories per call"},
            input_tokens=0,
            output_tokens=0,
        )

    # Check memory limits (aggregate count)
    allowed, error = await check_memory_limits(ctx.project_id, ctx.user_id, count=len(memories))
    if not allowed:
        total_tokens = sum(count_tokens(m.get("text", "")) for m in memories)
        return ToolResult(
            data={"error": error, "upgrade_url": "/billing/upgrade"},
            input_tokens=total_tokens,
            output_tokens=0,
        )

    # Store memories in bulk
    result = await store_memories_bulk(
        project_id=ctx.project_id,
        memories=memories,
        source="mcp",
    )

    input_tokens = sum(count_tokens(m.get("text", "")) for m in memories)
    output_tokens = count_tokens(str(result))

    return ToolResult(
        data=result,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


async def handle_recall(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Semantically recall relevant memories.

    Args:
        params: Dict containing:
            - query: Search query
            - type: Filter by memory type
            - scope: Filter by scope
            - category: Filter by category
            - limit: Maximum memories to return
            - min_relevance: Minimum relevance score (0-1)

    Returns:
        ToolResult with recalled memories and relevance scores
    """
    query = params.get("query", "")
    memory_type = params.get("type")
    scope = params.get("scope")
    category = params.get("category")
    limit = params.get("limit", 5)
    min_relevance = params.get("min_relevance", 0.5)

    if not query:
        return ToolResult(
            data={"error": "rlm_recall: missing required parameter 'query'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await semantic_recall(
        project_id=ctx.project_id,
        query=query,
        memory_type=memory_type,
        scope=scope,
        category=category,
        limit=limit,
        min_relevance=min_relevance,
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(query),
        output_tokens=count_tokens(str(result)),
    )


async def handle_memories(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """List memories with filters.

    Args:
        params: Dict containing:
            - type: Filter by memory type
            - scope: Filter by scope
            - category: Filter by category
            - search: Text search in content
            - limit: Maximum memories to return
            - offset: Pagination offset

    Returns:
        ToolResult with memories list and pagination info
    """
    memory_type = params.get("type")
    scope = params.get("scope")
    category = params.get("category")
    search = params.get("search")
    limit = params.get("limit", 20)
    offset = params.get("offset", 0)

    result = await list_memories(
        project_id=ctx.project_id,
        memory_type=memory_type,
        scope=scope,
        category=category,
        search=search,
        limit=limit,
        offset=offset,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_forget(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Delete memories by ID or filter criteria.

    Args:
        params: Dict containing (at least one):
            - memory_id: Specific memory ID to delete
            - type: Delete all of this type
            - category: Delete all in this category
            - older_than_days: Delete memories older than N days

    Returns:
        ToolResult with deletion count and confirmation
    """
    memory_id = params.get("memory_id")
    memory_type = params.get("type")
    category = params.get("category")
    older_than_days = params.get("older_than_days")

    # Require at least one filter
    if not any([memory_id, memory_type, category, older_than_days]):
        return ToolResult(
            data={
                "error": "rlm_forget: at least one filter is required (memory_id, type, category, or older_than_days)"
            },
            input_tokens=0,
            output_tokens=0,
        )

    result = await delete_memories(
        project_id=ctx.project_id,
        memory_id=memory_id,
        memory_type=memory_type,
        category=category,
        older_than_days=older_than_days,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )
