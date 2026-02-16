"""Enumeration types for RLM MCP Server."""

from enum import StrEnum


class ToolName(StrEnum):
    """Available RLM tools."""

    RLM_ASK = "rlm_ask"
    RLM_SEARCH = "rlm_search"
    RLM_INJECT = "rlm_inject"
    RLM_CONTEXT = "rlm_context"
    RLM_CLEAR_CONTEXT = "rlm_clear_context"
    RLM_STATS = "rlm_stats"
    RLM_HELP = "rlm_help"
    RLM_SECTIONS = "rlm_sections"
    RLM_READ = "rlm_read"
    RLM_CONTEXT_QUERY = "rlm_context_query"
    # Phase 4.5: Recursive Context Tools
    RLM_DECOMPOSE = "rlm_decompose"
    RLM_MULTI_QUERY = "rlm_multi_query"
    RLM_MULTI_PROJECT_QUERY = "rlm_multi_project_query"
    RLM_PLAN = "rlm_plan"
    # Phase 4.6: Summary Storage Tools
    RLM_STORE_SUMMARY = "rlm_store_summary"
    RLM_GET_SUMMARIES = "rlm_get_summaries"
    RLM_DELETE_SUMMARY = "rlm_delete_summary"
    # Phase 7: Shared Context Tools
    RLM_SHARED_CONTEXT = "rlm_shared_context"
    RLM_LIST_TEMPLATES = "rlm_list_templates"
    RLM_GET_TEMPLATE = "rlm_get_template"
    RLM_LIST_COLLECTIONS = "rlm_list_collections"
    RLM_UPLOAD_SHARED_DOCUMENT = "rlm_upload_shared_document"
    # Phase 8.2: Agent Memory Tools
    RLM_REMEMBER = "rlm_remember"
    RLM_REMEMBER_BULK = "rlm_remember_bulk"
    RLM_RECALL = "rlm_recall"
    RLM_MEMORIES = "rlm_memories"
    RLM_FORGET = "rlm_forget"
    # Phase 9.1: Multi-Agent Swarm Tools
    RLM_SWARM_CREATE = "rlm_swarm_create"
    RLM_SWARM_JOIN = "rlm_swarm_join"
    RLM_CLAIM = "rlm_claim"
    RLM_RELEASE = "rlm_release"
    RLM_STATE_GET = "rlm_state_get"
    RLM_STATE_SET = "rlm_state_set"
    RLM_STATE_POLL = "rlm_state_poll"
    RLM_BROADCAST = "rlm_broadcast"
    RLM_SWARM_EVENTS = "rlm_swarm_events"
    RLM_TASK_CREATE = "rlm_task_create"
    RLM_TASK_BULK_CREATE = "rlm_task_bulk_create"
    RLM_TASK_CLAIM = "rlm_task_claim"
    RLM_TASK_COMPLETE = "rlm_task_complete"
    # Phase 10: Document Sync Tools
    RLM_UPLOAD_DOCUMENT = "rlm_upload_document"
    RLM_SYNC_DOCUMENTS = "rlm_sync_documents"
    RLM_SETTINGS = "rlm_settings"
    # Phase 11: Access Control Tools
    RLM_REQUEST_ACCESS = "rlm_request_access"
    # Phase 12: RLM Orchestration Tools
    RLM_LOAD_DOCUMENT = "rlm_load_document"
    RLM_LOAD_PROJECT = "rlm_load_project"
    RLM_ORCHESTRATE = "rlm_orchestrate"
    # Phase 13: REPL Context Bridge
    RLM_REPL_CONTEXT = "rlm_repl_context"
    # Phase 14: Pass-by-Reference (reduce hallucination)
    RLM_GET_CHUNK = "rlm_get_chunk"


class SearchMode(StrEnum):
    """Search mode for context queries."""

    KEYWORD = "keyword"
    SEMANTIC = "semantic"  # Future: embedding-based
    HYBRID = "hybrid"  # Future: keyword + semantic


class Plan(StrEnum):
    """Subscription plans."""

    FREE = "FREE"
    PRO = "PRO"
    TEAM = "TEAM"
    ENTERPRISE = "ENTERPRISE"


class DecomposeStrategy(StrEnum):
    """Strategy for query decomposition."""

    AUTO = "auto"  # Let the engine decide
    TERM_BASED = "term_based"  # Extract key terms
    STRUCTURAL = "structural"  # Follow document structure


class PlanStrategy(StrEnum):
    """Strategy for execution planning."""

    BREADTH_FIRST = "breadth_first"
    DEPTH_FIRST = "depth_first"
    RELEVANCE_FIRST = "relevance_first"


class SummaryType(StrEnum):
    """Type of summary stored."""

    CONCISE = "concise"  # Brief 1-2 sentence summary
    DETAILED = "detailed"  # Full multi-paragraph summary
    TECHNICAL = "technical"  # Technical details focus
    KEYWORDS = "keywords"  # Key terms and concepts
    CUSTOM = "custom"  # User-defined summary type


class DocumentCategoryEnum(StrEnum):
    """Document category for token budget allocation."""

    MANDATORY = "MANDATORY"
    BEST_PRACTICES = "BEST_PRACTICES"
    GUIDELINES = "GUIDELINES"
    REFERENCE = "REFERENCE"


class AgentMemoryType(StrEnum):
    """Type of agent memory."""

    FACT = "fact"  # Objective information
    DECISION = "decision"  # Choice made with rationale
    LEARNING = "learning"  # Pattern or insight discovered
    PREFERENCE = "preference"  # User/team preference
    TODO = "todo"  # Deferred task or reminder
    CONTEXT = "context"  # General session context


class AgentMemoryScope(StrEnum):
    """Scope of agent memory visibility."""

    AGENT = "agent"  # Specific to one agent/session
    PROJECT = "project"  # Shared across project
    TEAM = "team"  # Shared across team
    USER = "user"  # Personal across all projects


class IndexJobStatus(StrEnum):
    """Status of an index job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
