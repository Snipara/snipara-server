"""Context query models for RLM MCP Server."""

from typing import Any

from pydantic import BaseModel, Field

from .enums import DecomposeStrategy, PlanStrategy, SearchMode

# ============ CONTEXT QUERY RESPONSE MODELS ============


class ContextSection(BaseModel):
    """A section of relevant context returned by rlm_context_query."""

    title: str = Field(..., description="Section title/heading")
    content: str = Field(..., description="Section content (may be truncated)")
    file: str = Field(..., description="Source file path")
    lines: tuple[int, int] = Field(..., description="Start and end line numbers")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance score (0-1)")
    token_count: int = Field(..., ge=0, description="Token count for this section")
    truncated: bool = Field(
        default=False, description="Whether content was truncated to fit budget"
    )


class ContextSectionRef(BaseModel):
    """A chunk reference returned when return_references=True.

    Pass-by-reference architecture: returns chunk IDs + previews instead of full content.
    Use rlm_get_chunk(chunk_id) to retrieve full content when needed.
    This reduces hallucination by maintaining clear source attribution.
    """

    chunk_id: str = Field(
        ..., description="Unique chunk identifier for retrieval via rlm_get_chunk"
    )
    title: str = Field(..., description="Section title/heading")
    preview: str = Field(..., description="First ~100 characters of content for context")
    file: str = Field(..., description="Source file path")
    lines: tuple[int, int] = Field(..., description="Start and end line numbers")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance score (0-1)")
    token_count: int = Field(
        ..., ge=0, description="Full content token count (for budget planning)"
    )
    keyword_score: float = Field(default=0.0, description="Keyword match score (for debugging)")
    semantic_score: float = Field(
        default=0.0, description="Semantic similarity score (for debugging)"
    )


class GetChunkResult(BaseModel):
    """Result of rlm_get_chunk tool - retrieves full content by chunk ID."""

    chunk_id: str = Field(..., description="The chunk ID that was requested")
    title: str = Field(..., description="Section title/heading")
    content: str = Field(..., description="Full section content")
    file: str = Field(..., description="Source file path")
    lines: tuple[int, int] = Field(..., description="Start and end line numbers")
    token_count: int = Field(..., ge=0, description="Token count for this section")
    found: bool = Field(default=True, description="Whether the chunk was found")


class ContextQueryResult(BaseModel):
    """Result of rlm_context_query tool - optimized context for the client's LLM."""

    sections: list[ContextSection] = Field(
        default_factory=list,
        description="Ranked list of relevant sections (when return_references=False)",
    )
    section_refs: list[ContextSectionRef] = Field(
        default_factory=list,
        description="Chunk references with IDs + previews (when return_references=True). "
        "Use rlm_get_chunk(chunk_id) to retrieve full content.",
    )
    references_mode: bool = Field(
        default=False,
        description="True if returning references instead of full content",
    )
    total_tokens: int = Field(
        ..., ge=0, description="Total tokens returned (preview tokens if references_mode)"
    )
    max_tokens: int = Field(..., description="Token budget that was requested")
    query: str = Field(..., description="Original query")
    search_mode: SearchMode = Field(..., description="Search mode used")
    search_mode_downgraded: bool = Field(
        default=False,
        description="Whether search mode was downgraded due to plan restrictions",
    )
    session_context_included: bool = Field(
        default=False, description="Whether session context was prepended"
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Additional sections that may be relevant but didn't fit",
    )
    summaries_used: int = Field(
        default=0,
        ge=0,
        description="Number of stored summaries used instead of full content",
    )
    timing: dict[str, int] | None = Field(
        default=None,
        description="Timing breakdown in milliseconds (embed_ms, search_ms, score_ms, total_ms)",
    )
    system_instructions: str | None = Field(
        default=None,
        description="System instructions to guide LLM behavior when using Snipara tools",
    )
    shared_context_included: bool = Field(
        default=False,
        description="Whether shared best practices were included (from linked collections)",
    )
    shared_context_tokens: int = Field(
        default=0,
        ge=0,
        description="Number of tokens from shared context collections",
    )
    first_query_tips_included: bool = Field(
        default=False,
        description="Whether first-query tool tips were included (shown only on first query)",
    )
    # Smart Routing Hints (helps clients decide when to use RLM-Runtime)
    routing_recommendation: str | None = Field(
        default=None,
        description="Recommended execution mode: 'direct' (use context as-is) or 'rlm_runtime' (use RLM for complex reasoning)",
    )
    routing_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score (0-1) for the routing recommendation",
    )
    routing_reason: str | None = Field(
        default=None,
        description="Human-readable explanation for routing recommendation",
    )
    query_complexity: str | None = Field(
        default=None,
        description="Assessed query complexity: 'simple', 'moderate', or 'complex'",
    )


# ============ RECURSIVE CONTEXT MODELS (Phase 4.5) ============


class SubQuery(BaseModel):
    """A sub-query generated by decomposition."""

    id: int = Field(..., description="Sub-query ID (1-indexed)")
    query: str = Field(..., description="The sub-query text")
    priority: int = Field(default=1, ge=1, le=10, description="Priority (1=highest)")
    estimated_tokens: int = Field(default=1000, ge=0, description="Estimated tokens for this query")
    key_terms: list[str] = Field(default_factory=list, description="Key terms identified")


class DecomposeResult(BaseModel):
    """Result of rlm_decompose tool."""

    original_query: str = Field(..., description="The original query")
    sub_queries: list[SubQuery] = Field(default_factory=list, description="Generated sub-queries")
    dependencies: list[tuple[int, int]] = Field(
        default_factory=list,
        description="Dependencies between sub-queries [(a, b) means a should be read before b]",
    )
    suggested_sequence: list[int] = Field(
        default_factory=list, description="Suggested execution order (query IDs)"
    )
    total_estimated_tokens: int = Field(
        default=0, ge=0, description="Total estimated tokens for all sub-queries"
    )
    strategy_used: DecomposeStrategy = Field(..., description="Strategy that was used")


class MultiQueryResultItem(BaseModel):
    """Result for a single query in a multi-query batch."""

    query: str = Field(..., description="The original query")
    sections: list[ContextSection] = Field(default_factory=list, description="Relevant sections")
    tokens_used: int = Field(default=0, ge=0, description="Tokens used for this query")
    success: bool = Field(default=True, description="Whether query succeeded")
    error: str | None = Field(default=None, description="Error message if failed")


class MultiQueryResult(BaseModel):
    """Result of rlm_multi_query tool."""

    results: list[MultiQueryResultItem] = Field(
        default_factory=list, description="Results for each query"
    )
    total_tokens: int = Field(default=0, ge=0, description="Total tokens used")
    queries_executed: int = Field(default=0, ge=0, description="Number of queries executed")
    queries_skipped: int = Field(default=0, ge=0, description="Queries skipped due to budget")
    search_mode: SearchMode = Field(..., description="Search mode used")


class PlanStep(BaseModel):
    """A step in an execution plan."""

    step: int = Field(..., ge=1, description="Step number")
    action: str = Field(..., description="Action to perform: decompose, context_query, multi_query")
    params: dict[str, Any] = Field(default_factory=dict, description="Parameters for the action")
    depends_on: list[int] = Field(default_factory=list, description="Steps this step depends on")
    expected_output: str = Field(default="sections", description="Expected output type")


class PlanResult(BaseModel):
    """Result of rlm_plan tool."""

    plan_id: str = Field(..., description="Unique plan identifier")
    query: str = Field(..., description="The original query")
    steps: list[PlanStep] = Field(default_factory=list, description="Execution steps")
    estimated_total_tokens: int = Field(default=0, ge=0, description="Estimated total tokens")
    strategy: PlanStrategy = Field(..., description="Strategy used")
    estimated_queries: int = Field(default=0, ge=0, description="Estimated number of queries")
