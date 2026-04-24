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
    append_journal,
    attach_memory_source_v2,
    delete_memories,
    get_journal,
    invalidate_memory_v2,
    list_memories,
    semantic_recall,
    store_memory,
    summarize_journal,
    supersede_memory_v2,
    verify_memory_v2,
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


async def handle_memory_invalidate(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Invalidate a V2 memory using a legacy or V2 memory ID."""

    memory_id = params.get("memory_id")
    invalidated_at = params.get("invalidated_at")
    reason = params.get("reason")

    if not memory_id:
        return ToolResult(
            data={"error": "rlm_memory_invalidate: missing required parameter 'memory_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    from datetime import datetime

    parsed_invalidated_at = None
    if invalidated_at:
        try:
            parsed_invalidated_at = datetime.fromisoformat(invalidated_at.replace("Z", "+00:00"))
        except ValueError:
            return ToolResult(
                data={"error": "rlm_memory_invalidate: invalid ISO timestamp for 'invalidated_at'"},
                input_tokens=0,
                output_tokens=0,
            )

    result = await invalidate_memory_v2(
        memory_id=memory_id,
        invalidated_at=parsed_invalidated_at,
        reason=reason,
    )
    return ToolResult(
        data=result,
        input_tokens=count_tokens(memory_id),
        output_tokens=count_tokens(str(result)),
    )


async def handle_memory_attach_source(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Attach evidence to a V2 memory using a legacy or V2 memory ID."""

    memory_id = params.get("memory_id")
    evidence_type = params.get("evidence_type")

    if not memory_id or not evidence_type:
        missing = []
        if not memory_id:
            missing.append("memory_id")
        if not evidence_type:
            missing.append("evidence_type")
        return ToolResult(
            data={"error": f"rlm_memory_attach_source: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await attach_memory_source_v2(
        memory_id=memory_id,
        evidence_type=evidence_type,
        document_id=params.get("document_id"),
        chunk_id=params.get("chunk_id"),
        external_ref=params.get("external_ref"),
        snippet=params.get("snippet"),
        line_start=params.get("line_start"),
        line_end=params.get("line_end"),
        weight=params.get("weight", 1.0),
    )
    return ToolResult(
        data=result,
        input_tokens=count_tokens(memory_id),
        output_tokens=count_tokens(str(result)),
    )


async def handle_memory_supersede(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Supersede one Memory V2 record with another."""

    old_memory_id = params.get("old_memory_id")
    new_memory_id = params.get("new_memory_id")
    reason = params.get("reason")

    if not old_memory_id or not new_memory_id:
        missing = []
        if not old_memory_id:
            missing.append("old_memory_id")
        if not new_memory_id:
            missing.append("new_memory_id")
        return ToolResult(
            data={"error": f"rlm_memory_supersede: missing required parameter(s): {', '.join(missing)}"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await supersede_memory_v2(
        old_memory_id=old_memory_id,
        new_memory_id=new_memory_id,
        reason=reason,
    )
    input_tokens = count_tokens(old_memory_id) + count_tokens(new_memory_id)
    return ToolResult(
        data=result,
        input_tokens=input_tokens,
        output_tokens=count_tokens(str(result)),
    )


async def handle_memory_verify(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Verify whether a Memory V2 record still has valid evidence."""

    memory_id = params.get("memory_id")
    mark_stale_if_missing = params.get("mark_stale_if_missing", True)

    if not memory_id:
        return ToolResult(
            data={"error": "rlm_memory_verify: missing required parameter 'memory_id'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await verify_memory_v2(
        memory_id=memory_id,
        mark_stale_if_missing=mark_stale_if_missing,
    )
    return ToolResult(
        data=result,
        input_tokens=count_tokens(memory_id),
        output_tokens=count_tokens(str(result)),
    )


# ============ DAILY JOURNAL HANDLERS ============


async def handle_journal_append(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Append an entry to today's journal.

    Args:
        params: Dict containing:
            - text: Journal entry text (markdown supported)
            - tags: Optional tags for categorization

    Returns:
        ToolResult with entry_id, date, and confirmation
    """
    text = params.get("text", "")
    tags = params.get("tags")

    if not text:
        return ToolResult(
            data={"error": "rlm_journal_append: missing required parameter 'text'"},
            input_tokens=0,
            output_tokens=0,
        )

    # Check memory limits (journal entries count against memory quota)
    allowed, error = await check_memory_limits(ctx.project_id, ctx.user_id)
    if not allowed:
        return ToolResult(
            data={"error": error, "upgrade_url": "/billing/upgrade"},
            input_tokens=count_tokens(text),
            output_tokens=0,
        )

    result = await append_journal(
        project_id=ctx.project_id,
        text=text,
        tags=tags,
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(text),
        output_tokens=count_tokens(str(result)),
    )


async def handle_journal_get(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get journal entries for a specific date.

    Args:
        params: Dict containing:
            - date: Date in YYYY-MM-DD format (default: today)
            - include_yesterday: Also include yesterday's entries

    Returns:
        ToolResult with date, entries list, and total count
    """
    date = params.get("date")
    include_yesterday = params.get("include_yesterday", False)

    result = await get_journal(
        project_id=ctx.project_id,
        date=date,
        include_yesterday=include_yesterday,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_journal_summarize(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get journal entries for a date, ready for summarization.

    Args:
        params: Dict containing:
            - date: Date to summarize (YYYY-MM-DD)

    Returns:
        ToolResult with combined content and suggested prompt
    """
    date = params.get("date")

    if not date:
        return ToolResult(
            data={"error": "rlm_journal_summarize: missing required parameter 'date'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await summarize_journal(
        project_id=ctx.project_id,
        date=date,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


# ============ PHASE 20: MEMORY TIERS & COMPACTION HANDLERS ============


async def handle_session_memories(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get tiered memories for session auto-load.

    Args:
        params: Dict containing:
            - max_critical_tokens: Token budget for CRITICAL tier (default: 8000)
            - max_daily_tokens: Token budget for DAILY tier (default: 4000)
            - include_yesterday: Include yesterday's daily memories (default: True)

    Returns:
        ToolResult with critical and daily memories organized by tier
    """
    from ...services.agent_memory import get_session_memories

    max_critical = params.get("max_critical_tokens", 8000)
    max_daily = params.get("max_daily_tokens", 4000)
    include_yesterday = params.get("include_yesterday", True)

    result = await get_session_memories(
        project_id=ctx.project_id,
        max_critical_tokens=max_critical,
        max_daily_tokens=max_daily,
        include_yesterday=include_yesterday,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_memory_compact(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Compact and optimize memories with intelligent consolidation.

    Args:
        params: Dict containing:
            # Existing parameters:
            - scope: Memory scope to compact (default: project)
            - deduplicate: Merge similar memories (default: True)
            - promote_threshold: Access count to promote to CRITICAL (default: 3)
            - archive_older_than_days: Archive memories older than N days (default: 30)
            - dry_run: Preview changes without applying (default: False)

            # NEW consolidation parameters:
            - normalize_dates: Convert relative dates to absolute (default: True)
                Example: "yesterday" -> "2026-03-24" (based on memory creation time)
            - validate_refs: Remove dead document_refs (default: True)
                Removes references to documents no longer in the index
            - conflict_strategy: How to resolve similar-but-different memories (default: "newer")
                - "newer": Keep most recent, archive older
                - "higher_confidence": Keep highest confidence score
                - "merge": Combine content into newer memory
                - "flag": Mark both for manual review (adds :needs_review to category)
            - similarity_threshold: Semantic similarity for conflict detection (default: 0.85)
                Range 0.0-1.0. Higher = stricter matching (fewer conflicts detected)

    Returns:
        ToolResult with compaction results including:
            - dates_normalized: Count of date conversions
            - dead_refs_removed: Count of invalid references removed
            - conflicts_resolved: Count of contradictions resolved
            - conflicts_flagged: Count flagged for review (if strategy="flag")
            - duplicates_merged: Count of exact duplicates removed
            - promoted_to_critical: Count of learnings promoted
            - archived: Count of old memories archived
            - tokens_freed: Estimated tokens saved
    """
    from ...services.agent_memory import compact_memories

    # Existing parameters
    scope = params.get("scope", "project")
    deduplicate = params.get("deduplicate", True)
    promote_threshold = params.get("promote_threshold", 3)
    archive_older_than_days = params.get("archive_older_than_days", 30)
    dry_run = params.get("dry_run", False)

    # NEW consolidation parameters
    normalize_dates = params.get("normalize_dates", True)
    validate_refs = params.get("validate_refs", True)
    conflict_strategy = params.get("conflict_strategy", "newer")
    similarity_threshold = params.get("similarity_threshold", 0.85)

    # Validate conflict_strategy
    valid_strategies = ["newer", "higher_confidence", "merge", "flag"]
    if conflict_strategy not in valid_strategies:
        return ToolResult(
            data={
                "error": f"Invalid conflict_strategy: {conflict_strategy}. "
                f"Must be one of: {', '.join(valid_strategies)}"
            },
            input_tokens=0,
            output_tokens=0,
        )

    # Validate similarity_threshold
    if not (0.0 <= similarity_threshold <= 1.0):
        return ToolResult(
            data={
                "error": f"Invalid similarity_threshold: {similarity_threshold}. "
                "Must be between 0.0 and 1.0"
            },
            input_tokens=0,
            output_tokens=0,
        )

    result = await compact_memories(
        project_id=ctx.project_id,
        scope=scope,
        deduplicate=deduplicate,
        promote_threshold=promote_threshold,
        archive_older_than_days=archive_older_than_days,
        dry_run=dry_run,
        # NEW parameters
        normalize_dates=normalize_dates,
        validate_refs=validate_refs,
        conflict_strategy=conflict_strategy,
        similarity_threshold=similarity_threshold,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


async def handle_memory_daily_brief(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Generate a daily memory brief.

    Args:
        params: Dict containing:
            - date: Date for brief (default: today)
            - max_items: Maximum items to include (default: 10)

    Returns:
        ToolResult with prioritized memory brief
    """
    from ...services.agent_memory import get_daily_brief

    date = params.get("date")
    max_items = params.get("max_items", 10)

    result = await get_daily_brief(
        project_id=ctx.project_id,
        date=date,
        max_items=max_items,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )


# ============ PHASE 20: TENANT PROFILE HANDLERS ============


async def handle_tenant_profile_create(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Create a structured tenant/client profile.

    Args:
        params: Dict containing:
            - client_name: Name of the client (required)
            - business_model: How the business works
            - industry: Industry vertical
            - tech_stack: Technology stack
            - legal_constraints: Legal requirements
            - security_requirements: Security constraints
            - ui_ux_prefs: UI/UX preferences
            - communication_style: How to communicate
            - risk_tolerance: low/medium/high
            - dos: List of things to do
            - donts: List of things to avoid
            - custom_fields: Additional custom fields

    Returns:
        ToolResult with profile ID and confirmation
    """
    from ...services.agent_memory import create_tenant_profile

    client_name = params.get("client_name")

    if not client_name:
        return ToolResult(
            data={"error": "rlm_tenant_profile_create: missing required parameter 'client_name'"},
            input_tokens=0,
            output_tokens=0,
        )

    result = await create_tenant_profile(
        project_id=ctx.project_id,
        client_name=client_name,
        business_model=params.get("business_model"),
        industry=params.get("industry"),
        tech_stack=params.get("tech_stack"),
        legal_constraints=params.get("legal_constraints"),
        security_requirements=params.get("security_requirements"),
        ui_ux_prefs=params.get("ui_ux_prefs"),
        communication_style=params.get("communication_style"),
        risk_tolerance=params.get("risk_tolerance"),
        dos=params.get("dos"),
        donts=params.get("donts"),
        custom_fields=params.get("custom_fields"),
    )

    return ToolResult(
        data=result,
        input_tokens=count_tokens(str(params)),
        output_tokens=count_tokens(str(result)),
    )


async def handle_tenant_profile_get(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get tenant profile(s) for a project.

    Args:
        params: Dict containing:
            - tenant_id: Specific profile ID (optional, returns all if not specified)

    Returns:
        ToolResult with tenant profile(s)
    """
    from ...services.agent_memory import get_tenant_profile

    tenant_id = params.get("tenant_id")

    result = await get_tenant_profile(
        project_id=ctx.project_id,
        tenant_id=tenant_id,
    )

    return ToolResult(
        data=result,
        input_tokens=0,
        output_tokens=count_tokens(str(result)),
    )
