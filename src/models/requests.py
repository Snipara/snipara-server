"""Request models (Pydantic *Params classes) for RLM MCP Server."""

from typing import Any

from pydantic import BaseModel, Field

from .enums import (
    AgentMemoryScope,
    AgentMemoryType,
    DecomposeStrategy,
    DocumentCategoryEnum,
    PlanStrategy,
    SearchMode,
    SummaryType,
    ToolName,
)

# ============ CORE REQUEST MODELS ============


class MCPRequest(BaseModel):
    """MCP tool execution request."""

    tool: ToolName = Field(..., description="The RLM tool to execute")
    params: dict[str, Any] = Field(default_factory=dict, description="Tool parameters")


class AskParams(BaseModel):
    """Parameters for rlm_ask tool."""

    question: str = Field(..., description="The question to ask about the documentation")


class SearchParams(BaseModel):
    """Parameters for rlm_search tool."""

    pattern: str = Field(..., description="Regex pattern to search for")
    max_results: int = Field(default=20, description="Maximum results to return")


class InjectParams(BaseModel):
    """Parameters for rlm_inject tool."""

    context: str = Field(..., description="The context to inject")
    append: bool = Field(default=False, description="Append to existing context")


class ReadParams(BaseModel):
    """Parameters for rlm_read tool."""

    start_line: int = Field(..., description="Starting line number")
    end_line: int = Field(..., description="Ending line number")


# ============ CONTEXT QUERY PARAMS ============


class ContextQueryParams(BaseModel):
    """Parameters for rlm_context_query tool - the main context optimization tool."""

    query: str = Field(..., description="The query/question to get context for")
    max_tokens: int = Field(
        default=4000,
        ge=100,
        le=100000,
        description="Maximum tokens to return (respects client's token budget)",
    )
    search_mode: SearchMode = Field(
        default=SearchMode.KEYWORD,
        description="Search strategy: keyword, semantic (future), or hybrid (future)",
    )
    include_metadata: bool = Field(
        default=True,
        description="Include file paths, line numbers, and relevance scores",
    )
    prefer_summaries: bool = Field(
        default=False,
        description="Prefer stored summaries over full document content when available",
    )
    return_references: bool = Field(
        default=False,
        description="Return chunk references (IDs + previews) instead of full content. "
        "Use rlm_get_chunk to retrieve full content by ID. Reduces hallucination by "
        "maintaining clear source attribution.",
    )


class MultiProjectQueryParams(BaseModel):
    """Parameters for rlm_multi_project_query tool."""

    query: str = Field(..., description="The query/question to get context for")
    max_tokens: int = Field(
        default=4000,
        ge=100,
        le=100000,
        description="Maximum tokens to return across all projects",
    )
    per_project_limit: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Maximum sections to return per project",
    )
    project_ids: list[str] = Field(
        default_factory=list,
        description="Optional list of project IDs or slugs to include",
    )
    exclude_project_ids: list[str] = Field(
        default_factory=list,
        description="Optional list of project IDs or slugs to exclude",
    )
    search_mode: SearchMode = Field(
        default=SearchMode.KEYWORD,
        description="Search strategy: keyword, semantic, or hybrid",
    )
    include_metadata: bool = Field(
        default=True,
        description="Include file paths, line numbers, and relevance scores",
    )
    prefer_summaries: bool = Field(
        default=False,
        description="Prefer stored summaries when available",
    )


# ============ RECURSIVE CONTEXT PARAMS (Phase 4.5) ============


class DecomposeParams(BaseModel):
    """Parameters for rlm_decompose tool."""

    query: str = Field(..., description="The complex question to decompose")
    max_depth: int = Field(default=2, ge=1, le=5, description="Maximum recursion depth")
    strategy: DecomposeStrategy = Field(
        default=DecomposeStrategy.AUTO, description="Decomposition strategy"
    )
    hints: list[str] = Field(
        default_factory=list,
        description="Optional hints to guide decomposition",
    )


class MultiQueryItem(BaseModel):
    """A single query in a multi-query batch."""

    query: str = Field(..., description="The query text")
    max_tokens: int | None = Field(default=None, description="Optional per-query token budget")


class MultiQueryParams(BaseModel):
    """Parameters for rlm_multi_query tool."""

    queries: list[MultiQueryItem] = Field(
        ..., min_length=1, max_length=10, description="List of queries to execute"
    )
    max_tokens: int = Field(default=8000, ge=500, le=50000, description="Total token budget")
    search_mode: SearchMode = Field(
        default=SearchMode.HYBRID, description="Search mode for all queries"
    )


class PlanParams(BaseModel):
    """Parameters for rlm_plan tool."""

    query: str = Field(..., description="The complex question to plan for")
    strategy: PlanStrategy = Field(
        default=PlanStrategy.RELEVANCE_FIRST, description="Execution strategy"
    )
    max_tokens: int = Field(default=16000, ge=1000, le=100000, description="Total token budget")


# ============ SUMMARY STORAGE PARAMS (Phase 4.6) ============


class StoreSummaryParams(BaseModel):
    """Parameters for rlm_store_summary tool."""

    document_path: str = Field(..., description="Path to the document (relative to project root)")
    summary: str = Field(..., min_length=1, description="The summary text to store")
    summary_type: SummaryType = Field(default=SummaryType.CONCISE, description="Type of summary")
    section_id: str | None = Field(
        default=None, description="Optional section identifier for partial summaries"
    )
    line_start: int | None = Field(default=None, ge=1, description="Start line for section summary")
    line_end: int | None = Field(default=None, ge=1, description="End line for section summary")
    generated_by: str | None = Field(
        default=None,
        description="Model that generated the summary (e.g., 'claude-3.5-sonnet')",
    )


class GetSummariesParams(BaseModel):
    """Parameters for rlm_get_summaries tool."""

    document_path: str | None = Field(default=None, description="Filter by document path")
    summary_type: SummaryType | None = Field(default=None, description="Filter by summary type")
    section_id: str | None = Field(default=None, description="Filter by section ID")
    include_content: bool = Field(default=True, description="Include summary content in response")


class DeleteSummaryParams(BaseModel):
    """Parameters for rlm_delete_summary tool."""

    summary_id: str | None = Field(default=None, description="Specific summary ID")
    document_path: str | None = Field(default=None, description="Delete all summaries for document")
    summary_type: SummaryType | None = Field(
        default=None, description="Delete summaries of this type"
    )


# ============ SHARED CONTEXT PARAMS (Phase 7) ============


class SharedContextParams(BaseModel):
    """Parameters for rlm_shared_context tool."""

    max_tokens: int = Field(
        default=4000,
        ge=100,
        le=100000,
        description="Maximum tokens for shared context",
    )
    categories: list[DocumentCategoryEnum] | None = Field(
        default=None,
        description="Filter by categories (null = all categories)",
    )
    include_content: bool = Field(
        default=True,
        description="Include document content in response",
    )


class ListTemplatesParams(BaseModel):
    """Parameters for rlm_list_templates tool."""

    category: str | None = Field(default=None, description="Filter by category")


class GetTemplateParams(BaseModel):
    """Parameters for rlm_get_template tool."""

    template_id: str | None = Field(default=None, description="Template ID")
    slug: str | None = Field(default=None, description="Template slug")
    variables: dict[str, str] = Field(
        default_factory=dict,
        description="Variable values to substitute in the template",
    )


# ============ AGENT MEMORY PARAMS (Phase 8.2) ============


class RememberParams(BaseModel):
    """Parameters for rlm_remember tool."""

    content: str = Field(..., min_length=1, description="The memory content to store")
    type: AgentMemoryType = Field(default=AgentMemoryType.FACT, description="Type of memory")
    scope: AgentMemoryScope = Field(
        default=AgentMemoryScope.PROJECT, description="Visibility scope"
    )
    category: str | None = Field(default=None, description="Optional grouping category")
    ttl_days: int | None = Field(
        default=None, ge=1, le=365, description="Days until memory expires (null = permanent)"
    )
    related_to: list[str] = Field(default_factory=list, description="IDs of related memories")
    document_refs: list[str] = Field(default_factory=list, description="Referenced document paths")
    source: str | None = Field(
        default=None, description="What created this memory (e.g., 'user', 'agent', 'import')"
    )


class RecallParams(BaseModel):
    """Parameters for rlm_recall tool - semantic memory retrieval."""

    query: str = Field(..., min_length=1, description="Search query for semantic recall")
    type: AgentMemoryType | None = Field(default=None, description="Filter by memory type")
    scope: AgentMemoryScope | None = Field(default=None, description="Filter by scope")
    category: str | None = Field(default=None, description="Filter by category")
    limit: int = Field(default=5, ge=1, le=50, description="Maximum memories to return")
    min_relevance: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Minimum relevance score (0-1)"
    )
    include_expired: bool = Field(default=False, description="Include expired memories in recall")


class MemoriesParams(BaseModel):
    """Parameters for rlm_memories tool - list memories with filters."""

    type: AgentMemoryType | None = Field(default=None, description="Filter by type")
    scope: AgentMemoryScope | None = Field(default=None, description="Filter by scope")
    category: str | None = Field(default=None, description="Filter by category")
    search: str | None = Field(default=None, description="Text search in content")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum memories to return")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
    include_expired: bool = Field(default=False, description="Include expired memories")


class ForgetParams(BaseModel):
    """Parameters for rlm_forget tool."""

    memory_id: str | None = Field(default=None, description="Specific memory ID to delete")
    type: AgentMemoryType | None = Field(
        default=None, description="Delete all memories of this type"
    )
    category: str | None = Field(default=None, description="Delete all memories in this category")
    older_than_days: int | None = Field(
        default=None, ge=1, description="Delete memories older than N days"
    )


# ============ MULTI-AGENT SWARM PARAMS (Phase 9.1) ============


class SwarmCreateParams(BaseModel):
    """Parameters for rlm_swarm_create tool."""

    name: str = Field(..., min_length=1, max_length=100, description="Swarm name")
    description: str | None = Field(default=None, description="Swarm description")
    max_agents: int = Field(default=10, ge=2, le=50, description="Maximum agents allowed")
    task_timeout: int = Field(default=300, ge=60, le=3600, description="Task timeout in seconds")
    claim_timeout: int = Field(
        default=600, ge=60, le=7200, description="Resource claim timeout in seconds"
    )


class SwarmJoinParams(BaseModel):
    """Parameters for rlm_swarm_join tool."""

    swarm_id: str = Field(..., description="ID of swarm to join")
    agent_id: str = Field(..., description="Unique identifier for this agent")
    name: str | None = Field(default=None, description="Human-readable agent name")


class ClaimParams(BaseModel):
    """Parameters for rlm_claim tool - claim exclusive resource access."""

    swarm_id: str = Field(..., description="Swarm ID")
    agent_id: str = Field(..., description="Agent ID making the claim")
    resource_type: str = Field(
        ..., description="Resource type: 'file', 'function', 'module', 'custom'"
    )
    resource_id: str = Field(..., description="Resource identifier (e.g., 'src/auth.ts')")
    ttl_seconds: int | None = Field(
        default=None, ge=60, le=7200, description="Custom TTL (uses swarm default if null)"
    )


class ReleaseParams(BaseModel):
    """Parameters for rlm_release tool."""

    swarm_id: str = Field(..., description="Swarm ID")
    agent_id: str = Field(..., description="Agent ID releasing the claim")
    resource_type: str = Field(..., description="Resource type")
    resource_id: str = Field(..., description="Resource identifier")


class StateGetParams(BaseModel):
    """Parameters for rlm_state_get tool."""

    swarm_id: str = Field(..., description="Swarm ID")
    key: str = Field(..., description="State key to retrieve")


class StateSetParams(BaseModel):
    """Parameters for rlm_state_set tool."""

    swarm_id: str = Field(..., description="Swarm ID")
    agent_id: str = Field(..., description="Agent ID setting the state")
    key: str = Field(..., description="State key")
    value: Any = Field(..., description="State value (JSON-serializable)")
    expected_version: int | None = Field(
        default=None, ge=0, description="Expected version for optimistic locking (null = overwrite)"
    )


class BroadcastParams(BaseModel):
    """Parameters for rlm_broadcast tool."""

    swarm_id: str = Field(..., description="Swarm ID")
    agent_id: str = Field(..., description="Agent ID broadcasting")
    event_type: str = Field(..., description="Event type (e.g., 'file_changed', 'task_done')")
    payload: dict[str, Any] = Field(default_factory=dict, description="Event payload")


class TaskCreateParams(BaseModel):
    """Parameters for rlm_task_create tool."""

    swarm_id: str = Field(..., description="Swarm ID")
    title: str = Field(..., min_length=1, description="Task title")
    description: str | None = Field(default=None, description="Task description")
    priority: int = Field(default=0, ge=0, le=100, description="Priority (higher = more urgent)")
    depends_on: list[str] = Field(
        default_factory=list, description="Task IDs that must complete first"
    )


class TaskClaimParams(BaseModel):
    """Parameters for rlm_task_claim tool."""

    swarm_id: str = Field(..., description="Swarm ID")
    agent_id: str = Field(..., description="Agent ID claiming")
    task_id: str | None = Field(
        default=None, description="Specific task ID (null = get next available)"
    )


class TaskCompleteParams(BaseModel):
    """Parameters for rlm_task_complete tool."""

    swarm_id: str = Field(..., description="Swarm ID")
    agent_id: str = Field(..., description="Agent ID completing")
    task_id: str = Field(..., description="Task ID to complete")
    result: dict[str, Any] | None = Field(default=None, description="Task result data")
    error: str | None = Field(default=None, description="Error message if task failed")


# ============ DOCUMENT SYNC PARAMS (Phase 10) ============


class SyncDocumentItem(BaseModel):
    """A document to sync."""

    path: str = Field(..., description="Document path")
    content: str = Field(..., description="Document content")


class SyncDocumentsParams(BaseModel):
    """Parameters for rlm_sync_documents tool."""

    documents: list[SyncDocumentItem] = Field(
        ..., description="Documents to sync", min_length=1, max_length=100
    )
    delete_missing: bool = Field(default=False, description="Delete documents not in list")


# ============ ACCESS REQUEST PARAMS ============


class RequestAccessParams(BaseModel):
    """Parameters for rlm_request_access tool."""

    requested_level: str = Field(
        default="VIEWER",
        description="Requested access level: VIEWER, EDITOR, or ADMIN",
    )
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for requesting access",
    )
