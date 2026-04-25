"""Tool Recommender Service.

Provides intelligent tool recommendations based on user queries.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class ToolTier(StrEnum):
    """Tool tier classification."""

    PRIMARY = "primary"
    POWER_USER = "power_user"
    TEAM = "team"
    UTILITY = "utility"
    ADVANCED = "advanced"


@dataclass
class ToolMetadata:
    """Metadata for a tool."""

    name: str
    tier: ToolTier
    keywords: list[str]
    use_cases: list[str]
    example: str
    related: list[str]
    description: str
    requires_team: bool = False
    requires_admin: bool = False


# Tool metadata for all 44+ tools
TOOL_METADATA: dict[str, ToolMetadata] = {
    # PRIMARY TIER - Core tools for everyday use
    "rlm_context_query": ToolMetadata(
        name="rlm_context_query",
        tier=ToolTier.PRIMARY,
        keywords=["search", "query", "find", "documentation", "context", "relevant", "semantic"],
        use_cases=[
            "Find relevant documentation sections",
            "Search for specific info with token budget",
            "Get context for a question",
        ],
        example='rlm_context_query(query="authentication", max_tokens=4000)',
        related=["rlm_ask", "rlm_search"],
        description="Query documentation with semantic search and token budgeting",
    ),
    "rlm_ask": ToolMetadata(
        name="rlm_ask",
        tier=ToolTier.PRIMARY,
        keywords=["ask", "question", "quick", "simple", "answer"],
        use_cases=[
            "Quick question with predictable tokens",
            "Simple documentation lookup",
        ],
        example='rlm_ask(question="How does auth work?")',
        related=["rlm_context_query"],
        description="Quick documentation query (~2500 tokens)",
    ),
    "rlm_search": ToolMetadata(
        name="rlm_search",
        tier=ToolTier.PRIMARY,
        keywords=["search", "regex", "pattern", "find", "grep"],
        use_cases=[
            "Find exact text patterns",
            "Regex search in docs",
        ],
        example='rlm_search(pattern="TODO.*fix")',
        related=["rlm_context_query"],
        description="Regex pattern search in documentation",
    ),
    "rlm_read": ToolMetadata(
        name="rlm_read",
        tier=ToolTier.PRIMARY,
        keywords=["read", "lines", "specific", "range", "section"],
        use_cases=[
            "Read specific line range",
            "Get exact section content",
        ],
        example="rlm_read(start_line=100, end_line=150)",
        related=["rlm_sections"],
        description="Read specific lines from indexed documentation",
    ),
    "rlm_recall": ToolMetadata(
        name="rlm_recall",
        tier=ToolTier.PRIMARY,
        keywords=["recall", "memory", "remember", "previous", "past", "history"],
        use_cases=[
            "Find previous decisions",
            "Recall learnings from past sessions",
            "Get user preferences",
        ],
        example='rlm_recall(query="auth decisions", limit=5)',
        related=["rlm_remember", "rlm_memories"],
        description="Semantically recall relevant memories",
    ),
    "rlm_stats": ToolMetadata(
        name="rlm_stats",
        tier=ToolTier.PRIMARY,
        keywords=["stats", "statistics", "info", "project", "overview"],
        use_cases=[
            "Get project statistics",
            "Check indexed document count",
        ],
        example="rlm_stats()",
        related=["rlm_sections", "rlm_settings"],
        description="Show documentation statistics",
    ),
    "rlm_help": ToolMetadata(
        name="rlm_help",
        tier=ToolTier.PRIMARY,
        keywords=["help", "recommend", "tools", "guide", "which", "how", "find"],
        use_cases=[
            "Find the right tool for a task",
            "Get detailed info about a specific tool",
            "List tools by tier",
        ],
        example='rlm_help(query="search across team projects")',
        related=["rlm_stats", "rlm_context_query"],
        description="Get tool recommendations based on query or tier",
    ),
    # POWER USER TIER - Advanced query and memory tools
    "rlm_multi_query": ToolMetadata(
        name="rlm_multi_query",
        tier=ToolTier.POWER_USER,
        keywords=["multi", "batch", "parallel", "multiple", "queries"],
        use_cases=[
            "Batch multiple questions",
            "Parallel queries with shared budget",
        ],
        example='rlm_multi_query(queries=[{"query": "auth"}, {"query": "db"}])',
        related=["rlm_context_query", "rlm_decompose"],
        description="Execute multiple queries in one call",
    ),
    "rlm_decompose": ToolMetadata(
        name="rlm_decompose",
        tier=ToolTier.POWER_USER,
        keywords=["decompose", "break", "complex", "sub-queries", "split"],
        use_cases=[
            "Break complex question into parts",
            "Plan multi-step query",
        ],
        example='rlm_decompose(query="How does the auth flow work end-to-end?")',
        related=["rlm_plan", "rlm_multi_query"],
        description="Break complex query into sub-queries",
    ),
    "rlm_plan": ToolMetadata(
        name="rlm_plan",
        tier=ToolTier.POWER_USER,
        keywords=["plan", "strategy", "execution", "complex", "steps"],
        use_cases=[
            "Generate execution plan for complex tasks",
            "Plan multi-step implementation",
        ],
        example='rlm_plan(query="Implement OAuth", strategy="relevance_first")',
        related=["rlm_decompose"],
        description="Generate execution plan for complex questions",
    ),
    "rlm_code_callers": ToolMetadata(
        name="rlm_code_callers",
        tier=ToolTier.POWER_USER,
        keywords=["code", "callers", "who calls", "references", "graph", "symbol"],
        use_cases=[
            "Find which methods call a target function",
            "Trace reverse call relationships in code",
            "Inspect structural callers without vector search",
        ],
        example='rlm_code_callers(qualified_name="src.rlm_engine.RLMEngine._handle_context_query")',
        related=["rlm_code_neighbors", "rlm_code_shortest_path"],
        description="Find callers of a code symbol from the code graph",
    ),
    "rlm_code_imports": ToolMetadata(
        name="rlm_code_imports",
        tier=ToolTier.POWER_USER,
        keywords=["code", "imports", "modules", "importers", "dependencies", "graph"],
        use_cases=[
            "List imports for a file or symbol",
            "Find which modules import a target module",
            "Inspect dependency edges in code",
        ],
        example='rlm_code_imports(file_path="src/rlm_engine.py", direction="out")',
        related=["rlm_code_neighbors", "rlm_code_callers"],
        description="Inspect import relationships in the code graph",
    ),
    "rlm_code_neighbors": ToolMetadata(
        name="rlm_code_neighbors",
        tier=ToolTier.POWER_USER,
        keywords=["code", "neighbors", "subgraph", "graph", "adjacent", "structure"],
        use_cases=[
            "Inspect the local graph around a symbol",
            "See nearby callers, imports, and containment edges",
            "Build a compact structural snapshot of code",
        ],
        example='rlm_code_neighbors(qualified_name="src.rlm_engine.RLMEngine", depth=2)',
        related=["rlm_code_callers", "rlm_code_shortest_path"],
        description="Return the local code subgraph around a symbol",
    ),
    "rlm_code_shortest_path": ToolMetadata(
        name="rlm_code_shortest_path",
        tier=ToolTier.POWER_USER,
        keywords=["code", "path", "shortest", "graph", "connect", "dependency"],
        use_cases=[
            "Find how two symbols are structurally connected",
            "Trace the shortest code path between nodes",
            "Explain graph connectivity in code",
        ],
        example='rlm_code_shortest_path(from="src.a.foo", to="src.b.bar")',
        related=["rlm_code_neighbors", "rlm_code_callers"],
        description="Find the shortest structural path between two code symbols",
    ),
    "rlm_remember": ToolMetadata(
        name="rlm_remember",
        tier=ToolTier.POWER_USER,
        keywords=["remember", "store", "save", "memory", "persist", "fact", "decision"],
        use_cases=[
            "Store a decision for later",
            "Save a learning or insight",
            "Record user preference",
        ],
        example='rlm_remember(text="Chose Redis for caching", type="decision")',
        related=["rlm_recall", "rlm_memories", "rlm_remember_bulk"],
        description="Store a memory for later recall",
    ),
    "rlm_remember_if_novel": ToolMetadata(
        name="rlm_remember_if_novel",
        tier=ToolTier.POWER_USER,
        keywords=["remember", "memory", "novel", "novelty", "dedupe", "duplicate", "persist"],
        use_cases=[
            "Store memory only when it is new",
            "Avoid duplicate durable memories",
            "Gate writes with novelty checks",
        ],
        example='rlm_remember_if_novel(text="Prefer project-scoped memory writes", type="decision")',
        related=["rlm_remember", "rlm_recall", "rlm_end_of_task_commit"],
        description="Store a memory only when it is sufficiently novel",
    ),
    "rlm_end_of_task_commit": ToolMetadata(
        name="rlm_end_of_task_commit",
        tier=ToolTier.POWER_USER,
        keywords=["end", "task", "commit", "summary", "durable", "persist", "decision"],
        use_cases=[
            "Persist durable knowledge from task summary",
            "Save decisions and learnings at task completion",
            "Turn task outcomes into reusable memory",
        ],
        example='rlm_end_of_task_commit(summary="Standardized memory writes on project scope")',
        related=["rlm_remember_if_novel", "rlm_remember", "rlm_journal_summarize"],
        description="Persist durable knowledge from a task summary",
    ),
    "rlm_remember_bulk": ToolMetadata(
        name="rlm_remember_bulk",
        tier=ToolTier.POWER_USER,
        keywords=["remember", "bulk", "batch", "multiple", "memories"],
        use_cases=[
            "Store multiple memories at once",
            "Batch import of facts or learnings",
        ],
        example='rlm_remember_bulk(memories=[{"text": "Fact 1"}, {"text": "Fact 2"}])',
        related=["rlm_remember", "rlm_recall"],
        description="Store multiple memories in bulk (max 50)",
    ),
    "rlm_memories": ToolMetadata(
        name="rlm_memories",
        tier=ToolTier.POWER_USER,
        keywords=["memories", "list", "browse", "filter", "all"],
        use_cases=[
            "List all memories",
            "Browse memories by type",
        ],
        example='rlm_memories(type="decision", limit=10)',
        related=["rlm_recall", "rlm_forget"],
        description="List memories with filters",
    ),
    "rlm_memory_invalidate": ToolMetadata(
        name="rlm_memory_invalidate",
        tier=ToolTier.POWER_USER,
        keywords=["invalidate", "obsolete", "wrong", "memory", "deprecated", "stale"],
        use_cases=[
            "Mark stale guidance as inactive",
            "Prevent a memory from resurfacing as active advice",
        ],
        example='rlm_memory_invalidate(memory_id="mem_abc123", reason="Old auth flow")',
        related=["rlm_memories", "rlm_memory_supersede"],
        description="Invalidate a memory without deleting it",
    ),
    "rlm_memory_supersede": ToolMetadata(
        name="rlm_memory_supersede",
        tier=ToolTier.POWER_USER,
        keywords=["supersede", "replace", "update", "memory", "new guidance"],
        use_cases=[
            "Replace obsolete memory with new guidance",
            "Preserve history while updating active memory",
        ],
        example='rlm_memory_supersede(old_memory_id="mem_abc123", text="Use bearer auth")',
        related=["rlm_memory_invalidate", "rlm_remember", "rlm_memories"],
        description="Replace one memory with a new active memory",
    ),
    "rlm_forget": ToolMetadata(
        name="rlm_forget",
        tier=ToolTier.POWER_USER,
        keywords=["forget", "delete", "remove", "clear", "memory"],
        use_cases=[
            "Delete specific memory",
            "Clear old memories",
        ],
        example='rlm_forget(memory_id="mem_abc123")',
        related=["rlm_memories"],
        description="Delete memories by ID or filter",
    ),
    "rlm_journal_append": ToolMetadata(
        name="rlm_journal_append",
        tier=ToolTier.POWER_USER,
        keywords=["journal", "append", "log", "daily", "note", "entry", "today"],
        use_cases=[
            "Add daily operational note",
            "Log today's progress",
            "Record session notes",
        ],
        example='rlm_journal_append(text="Completed auth refactor")',
        related=["rlm_journal_get", "rlm_journal_summarize", "rlm_remember"],
        description="Append an entry to today's daily journal",
    ),
    "rlm_journal_get": ToolMetadata(
        name="rlm_journal_get",
        tier=ToolTier.POWER_USER,
        keywords=["journal", "get", "read", "daily", "log", "today", "yesterday"],
        use_cases=[
            "Read today's journal entries",
            "Get yesterday's notes",
            "Review daily log",
        ],
        example='rlm_journal_get(date="2026-03-19", include_yesterday=True)',
        related=["rlm_journal_append", "rlm_journal_summarize"],
        description="Get journal entries for a specific date",
    ),
    "rlm_journal_summarize": ToolMetadata(
        name="rlm_journal_summarize",
        tier=ToolTier.POWER_USER,
        keywords=["journal", "summarize", "summary", "archive", "daily", "review"],
        use_cases=[
            "Generate daily summary for archiving",
            "Review and summarize a day's work",
            "Prepare journal for compaction",
        ],
        example='rlm_journal_summarize(date="2026-03-18")',
        related=["rlm_journal_get", "rlm_journal_append"],
        description="Get journal entries ready for summarization",
    ),
    "rlm_session_memories": ToolMetadata(
        name="rlm_session_memories",
        tier=ToolTier.POWER_USER,
        keywords=["session", "bootstrap", "resume", "autoload", "recall", "critical", "daily"],
        use_cases=[
            "Bootstrap a session from memory",
            "Reload critical decisions on resume",
            "Load daily and critical memory tiers",
        ],
        example="rlm_session_memories(max_critical_tokens=4000, max_daily_tokens=2000)",
        related=["rlm_recall", "rlm_memory_daily_brief", "rlm_tenant_profile_get"],
        description="Get tiered memories for session bootstrap and auto-load",
    ),
    "rlm_memory_compact": ToolMetadata(
        name="rlm_memory_compact",
        tier=ToolTier.POWER_USER,
        keywords=["compact", "deduplicate", "cleanup", "archive", "promote", "memory"],
        use_cases=[
            "Deduplicate and compact old memories",
            "Promote important learnings to critical tier",
            "Clean up noisy memory stores",
        ],
        example="rlm_memory_compact(scope=\"project\", deduplicate=True, dry_run=True)",
        related=["rlm_memories", "rlm_forget", "rlm_memory_daily_brief"],
        description="Compact, deduplicate, and promote memories",
    ),
    "rlm_memory_daily_brief": ToolMetadata(
        name="rlm_memory_daily_brief",
        tier=ToolTier.POWER_USER,
        keywords=["daily", "brief", "constraints", "active", "summary", "todo", "today"],
        use_cases=[
            "Generate a daily brief of active constraints",
            "Summarize decisions and todos for today",
            "Review the current operating context",
        ],
        example='rlm_memory_daily_brief(date="2026-04-15", max_items=10)',
        related=["rlm_session_memories", "rlm_journal_summarize"],
        description="Generate a daily brief of active constraints and pending work",
    ),
    "rlm_agent_profile_get": ToolMetadata(
        name="rlm_agent_profile_get",
        tier=ToolTier.ADVANCED,
        keywords=["agent", "profile", "identity", "soul", "personality", "swarm"],
        use_cases=[
            "Get agent's identity and personality",
            "Retrieve agent boundaries",
            "Check agent communication style",
        ],
        example='rlm_agent_profile_get(swarm_id="...", agent_id="jarvis")',
        related=["rlm_agent_profile_update", "rlm_swarm_join"],
        description="Get an agent's profile (identity, personality, boundaries)",
        requires_admin=True,
    ),
    "rlm_agent_profile_update": ToolMetadata(
        name="rlm_agent_profile_update",
        tier=ToolTier.ADVANCED,
        keywords=["agent", "profile", "update", "soul", "personality", "identity", "swarm"],
        use_cases=[
            "Set agent personality",
            "Define agent boundaries",
            "Configure communication style",
        ],
        example='rlm_agent_profile_update(swarm_id="...", agent_id="jarvis", profile={"personality": "INTJ"})',
        related=["rlm_agent_profile_get", "rlm_swarm_join"],
        description="Update an agent's profile (identity, personality, boundaries)",
        requires_admin=True,
    ),
    # TEAM TIER - Multi-project and shared context
    "rlm_multi_project_query": ToolMetadata(
        name="rlm_multi_project_query",
        tier=ToolTier.TEAM,
        keywords=["multi", "project", "team", "all", "cross", "search"],
        use_cases=[
            "Search across all team projects",
            "Find implementations in any project",
        ],
        example='rlm_multi_project_query(query="rate limiting")',
        related=["rlm_context_query"],
        description="Query across all projects in a team",
        requires_team=True,
    ),
    "rlm_shared_context": ToolMetadata(
        name="rlm_shared_context",
        tier=ToolTier.TEAM,
        keywords=["shared", "team", "standards", "guidelines", "best practices"],
        use_cases=[
            "Get team coding standards",
            "Load shared best practices",
        ],
        example='rlm_shared_context(categories=["MANDATORY", "BEST_PRACTICES"])',
        related=["rlm_list_templates"],
        description="Get merged context from shared collections",
        requires_team=True,
    ),
    "rlm_list_templates": ToolMetadata(
        name="rlm_list_templates",
        tier=ToolTier.TEAM,
        keywords=["templates", "list", "prompts", "shared"],
        use_cases=[
            "List available prompt templates",
            "Find team templates",
        ],
        example="rlm_list_templates(category='code-review')",
        related=["rlm_get_template"],
        description="List prompt templates from shared collections",
        requires_team=True,
    ),
    "rlm_get_template": ToolMetadata(
        name="rlm_get_template",
        tier=ToolTier.TEAM,
        keywords=["template", "get", "render", "prompt"],
        use_cases=[
            "Get specific prompt template",
            "Render template with variables",
        ],
        example='rlm_get_template(slug="pr-review", variables={"pr": "123"})',
        related=["rlm_list_templates"],
        description="Get a prompt template by ID or slug",
        requires_team=True,
    ),
    "rlm_list_collections": ToolMetadata(
        name="rlm_list_collections",
        tier=ToolTier.TEAM,
        keywords=["collections", "list", "shared", "available"],
        use_cases=[
            "List accessible shared collections",
            "Find team collections",
        ],
        example="rlm_list_collections(include_public=True)",
        related=["rlm_shared_context"],
        description="List shared context collections",
        requires_team=True,
    ),
    "rlm_create_collection": ToolMetadata(
        name="rlm_create_collection",
        tier=ToolTier.TEAM,
        keywords=["create", "collection", "shared", "team", "best practices"],
        use_cases=[
            "Create a project-specific shared collection",
            "Split mixed shared context into dedicated collections",
        ],
        example='rlm_create_collection(name="Vutler Best Practices")',
        related=["rlm_list_collections", "rlm_link_collection"],
        description="Create a new team shared context collection",
        requires_team=True,
    ),
    "rlm_get_collection_documents": ToolMetadata(
        name="rlm_get_collection_documents",
        tier=ToolTier.TEAM,
        keywords=["collection", "documents", "inspect", "shared", "content"],
        use_cases=[
            "Inspect documents in a shared collection",
            "Read collection content before splitting or moving docs",
        ],
        example='rlm_get_collection_documents(collection_id="...")',
        related=["rlm_list_collections", "rlm_upload_shared_document"],
        description="Inspect the documents inside a shared collection",
        requires_team=True,
    ),
    "rlm_link_collection": ToolMetadata(
        name="rlm_link_collection",
        tier=ToolTier.TEAM,
        keywords=["link", "project", "collection", "shared", "attach"],
        use_cases=[
            "Attach a shared collection to a project",
            "Apply project-specific best practices",
        ],
        example='rlm_link_collection(collection_id="...", project_id_or_slug="snipara")',
        related=["rlm_create_collection", "rlm_unlink_collection"],
        description="Link a shared collection to a project",
        requires_team=True,
    ),
    "rlm_unlink_collection": ToolMetadata(
        name="rlm_unlink_collection",
        tier=ToolTier.TEAM,
        keywords=["unlink", "detach", "project", "collection", "shared"],
        use_cases=[
            "Detach a shared collection from a project",
            "Remove mixed context from the wrong project",
        ],
        example='rlm_unlink_collection(collection_id="...", project_id_or_slug="snipara")',
        related=["rlm_link_collection", "rlm_list_collections"],
        description="Unlink a shared collection from a project",
        requires_team=True,
    ),
    "rlm_upload_shared_document": ToolMetadata(
        name="rlm_upload_shared_document",
        tier=ToolTier.TEAM,
        keywords=["upload", "shared", "document", "collection", "standard"],
        use_cases=[
            "Add document to shared collection",
            "Upload team coding standards",
        ],
        example='rlm_upload_shared_document(collection_id="...", title="Standards", content="...")',
        related=["rlm_shared_context"],
        description="Upload document to shared collection",
        requires_team=True,
    ),
    "rlm_tenant_profile_get": ToolMetadata(
        name="rlm_tenant_profile_get",
        tier=ToolTier.TEAM,
        keywords=["tenant", "workspace", "profile", "client", "preferences", "constraints"],
        use_cases=[
            "Load workspace profile at session start",
            "Retrieve client constraints and preferences",
            "Read project-level operating profile",
        ],
        example="rlm_tenant_profile_get()",
        related=["rlm_session_memories", "rlm_shared_context"],
        description="Get tenant or workspace profile for the current project",
        requires_team=True,
    ),
    # UTILITY TIER - Session and project management
    "rlm_inject": ToolMetadata(
        name="rlm_inject",
        tier=ToolTier.UTILITY,
        keywords=["inject", "context", "session", "set", "add"],
        use_cases=[
            "Set session context",
            "Add persistent context for queries",
        ],
        example='rlm_inject(context="Focus on security", append=False)',
        related=["rlm_context", "rlm_clear_context"],
        description="Set session context for subsequent queries",
    ),
    "rlm_context": ToolMetadata(
        name="rlm_context",
        tier=ToolTier.UTILITY,
        keywords=["context", "show", "current", "session"],
        use_cases=[
            "Show current session context",
            "Check injected context",
        ],
        example="rlm_context()",
        related=["rlm_inject", "rlm_clear_context"],
        description="Show current session context",
    ),
    "rlm_clear_context": ToolMetadata(
        name="rlm_clear_context",
        tier=ToolTier.UTILITY,
        keywords=["clear", "reset", "context", "session"],
        use_cases=[
            "Clear session context",
            "Reset to clean state",
        ],
        example="rlm_clear_context()",
        related=["rlm_inject", "rlm_context"],
        description="Clear session context",
    ),
    "rlm_sections": ToolMetadata(
        name="rlm_sections",
        tier=ToolTier.UTILITY,
        keywords=["sections", "list", "structure", "toc", "outline"],
        use_cases=[
            "List document sections",
            "Get documentation structure",
        ],
        example="rlm_sections(limit=50)",
        related=["rlm_stats", "rlm_read"],
        description="List indexed document sections",
    ),
    "rlm_settings": ToolMetadata(
        name="rlm_settings",
        tier=ToolTier.UTILITY,
        keywords=["settings", "config", "project", "configuration"],
        use_cases=[
            "View project settings",
            "Check configuration",
        ],
        example="rlm_settings(refresh=True)",
        related=["rlm_stats"],
        description="Get current project settings",
    ),
    "rlm_upload_document": ToolMetadata(
        name="rlm_upload_document",
        tier=ToolTier.UTILITY,
        keywords=["upload", "document", "add", "index", "binary", "pdf", "docx", "pptx", "svg", "vsdx"],
        use_cases=[
            "Upload a document for indexing",
            "Upload a binary parser document",
            "Add documentation file",
        ],
        example='rlm_upload_document(path="diagrams/network.vsdx", content="base64:...", kind="BINARY", format="vsdx")',
        related=["rlm_sync_documents"],
        description="Upload or update a project document, including supported binary parser files",
    ),
    "rlm_sync_documents": ToolMetadata(
        name="rlm_sync_documents",
        tier=ToolTier.UTILITY,
        keywords=["sync", "bulk", "documents", "batch", "upload", "binary", "business context"],
        use_cases=[
            "Batch upload documents",
            "Bulk upload business context files",
            "Sync documentation from CI/CD",
        ],
        example='rlm_sync_documents(documents=[{"path": "diagrams/network.vsdx", "content": "base64:...", "kind": "BINARY", "format": "vsdx"}])',
        related=["rlm_upload_document", "rlm_reindex"],
        description="Bulk sync multiple documents",
    ),
    "rlm_index_health": ToolMetadata(
        name="rlm_index_health",
        tier=ToolTier.POWER_USER,
        keywords=["index", "health", "coverage", "stale", "chunks", "quality", "analytics"],
        use_cases=[
            "Check index coverage before a demo",
            "See whether documents are missing searchable chunks",
            "Inspect index quality and freshness",
        ],
        example="rlm_index_health(stale_threshold_days=30)",
        related=["rlm_index_recommendations", "rlm_reindex"],
        description="Inspect documentation index coverage, freshness, and quality",
    ),
    "rlm_index_recommendations": ToolMetadata(
        name="rlm_index_recommendations",
        tier=ToolTier.POWER_USER,
        keywords=["index", "recommendations", "coverage", "reindex", "stale", "quality"],
        use_cases=[
            "Get the next maintenance step for a degraded index",
            "See whether full or incremental reindexing is recommended",
        ],
        example="rlm_index_recommendations()",
        related=["rlm_index_health", "rlm_reindex"],
        description="Return prioritized maintenance recommendations for the index",
    ),
    "rlm_reindex": ToolMetadata(
        name="rlm_reindex",
        tier=ToolTier.POWER_USER,
        keywords=["reindex", "index", "rebuild", "coverage", "chunks", "refresh", "maintenance"],
        use_cases=[
            "Trigger a full documentation reindex",
            "Run incremental catch-up after a sync",
            "Poll the status of an indexing job from MCP",
        ],
        example='rlm_reindex(mode="full", kind="doc")',
        related=["rlm_index_health", "rlm_index_recommendations", "rlm_sync_documents"],
        description="Trigger or poll a project reindex job through MCP",
    ),
    "rlm_store_summary": ToolMetadata(
        name="rlm_store_summary",
        tier=ToolTier.UTILITY,
        keywords=["summary", "store", "save", "cache"],
        use_cases=[
            "Store LLM-generated summary",
            "Cache document summary",
        ],
        example='rlm_store_summary(document_path="...", summary="...")',
        related=["rlm_get_summaries"],
        description="Store summary for a document",
    ),
    "rlm_get_summaries": ToolMetadata(
        name="rlm_get_summaries",
        tier=ToolTier.UTILITY,
        keywords=["summaries", "get", "retrieve", "cached"],
        use_cases=[
            "Get stored summaries",
            "Retrieve cached document summaries",
        ],
        example='rlm_get_summaries(document_path="docs/api.md")',
        related=["rlm_store_summary", "rlm_delete_summary"],
        description="Retrieve stored summaries",
    ),
    "rlm_delete_summary": ToolMetadata(
        name="rlm_delete_summary",
        tier=ToolTier.UTILITY,
        keywords=["summary", "delete", "remove", "clear"],
        use_cases=[
            "Delete stored summary",
            "Clear outdated summaries",
        ],
        example='rlm_delete_summary(summary_id="...")',
        related=["rlm_get_summaries"],
        description="Delete stored summaries",
    ),
    # ADVANCED TIER - Swarm, orchestration, and low-level tools
    "rlm_swarm_create": ToolMetadata(
        name="rlm_swarm_create",
        tier=ToolTier.ADVANCED,
        keywords=["swarm", "create", "multi-agent", "coordination"],
        use_cases=[
            "Create agent swarm for coordination",
            "Initialize multi-agent task",
        ],
        example='rlm_swarm_create(name="refactor-swarm")',
        related=["rlm_swarm_join", "rlm_task_create"],
        description="Create a new agent swarm",
        requires_admin=True,
    ),
    "rlm_swarm_join": ToolMetadata(
        name="rlm_swarm_join",
        tier=ToolTier.ADVANCED,
        keywords=["swarm", "join", "agent", "connect"],
        use_cases=[
            "Join existing swarm",
            "Connect as worker agent",
        ],
        example='rlm_swarm_join(swarm_id="...", agent_id="agent-1")',
        related=["rlm_swarm_create"],
        description="Join an existing swarm",
        requires_admin=True,
    ),
    "rlm_claim": ToolMetadata(
        name="rlm_claim",
        tier=ToolTier.ADVANCED,
        keywords=["claim", "lock", "resource", "file", "exclusive"],
        use_cases=[
            "Claim exclusive resource access",
            "Lock file for editing",
        ],
        example='rlm_claim(swarm_id="...", resource_type="file", resource_id="src/app.ts")',
        related=["rlm_release"],
        description="Claim exclusive resource access",
        requires_admin=True,
    ),
    "rlm_release": ToolMetadata(
        name="rlm_release",
        tier=ToolTier.ADVANCED,
        keywords=["release", "unlock", "resource", "free"],
        use_cases=[
            "Release claimed resource",
            "Unlock file",
        ],
        example='rlm_release(swarm_id="...", claim_id="...")',
        related=["rlm_claim"],
        description="Release a claimed resource",
        requires_admin=True,
    ),
    "rlm_state_get": ToolMetadata(
        name="rlm_state_get",
        tier=ToolTier.ADVANCED,
        keywords=["state", "get", "read", "shared", "swarm"],
        use_cases=[
            "Read shared swarm state",
            "Get coordination data",
        ],
        example='rlm_state_get(swarm_id="...", key="progress")',
        related=["rlm_state_set"],
        description="Read shared swarm state",
        requires_admin=True,
    ),
    "rlm_state_set": ToolMetadata(
        name="rlm_state_set",
        tier=ToolTier.ADVANCED,
        keywords=["state", "set", "write", "shared", "swarm"],
        use_cases=[
            "Write shared swarm state",
            "Update coordination data",
        ],
        example='rlm_state_set(swarm_id="...", key="progress", value=50)',
        related=["rlm_state_get"],
        description="Write shared swarm state",
        requires_admin=True,
    ),
    "rlm_broadcast": ToolMetadata(
        name="rlm_broadcast",
        tier=ToolTier.ADVANCED,
        keywords=["broadcast", "event", "notify", "swarm", "message"],
        use_cases=[
            "Broadcast event to all agents",
            "Notify swarm of completion",
        ],
        example='rlm_broadcast(swarm_id="...", event_type="task_done")',
        related=["rlm_swarm_create"],
        description="Send event to all agents in swarm",
        requires_admin=True,
    ),
    "rlm_task_create": ToolMetadata(
        name="rlm_task_create",
        tier=ToolTier.ADVANCED,
        keywords=["task", "create", "queue", "swarm", "work"],
        use_cases=[
            "Create task in swarm queue",
            "Add work item for agents",
        ],
        example='rlm_task_create(swarm_id="...", title="Refactor auth")',
        related=["rlm_task_claim", "rlm_task_complete"],
        description="Create a task in swarm queue",
        requires_admin=True,
    ),
    "rlm_task_claim": ToolMetadata(
        name="rlm_task_claim",
        tier=ToolTier.ADVANCED,
        keywords=["task", "claim", "take", "work", "queue"],
        use_cases=[
            "Claim task from queue",
            "Start working on task",
        ],
        example='rlm_task_claim(swarm_id="...", agent_id="...")',
        related=["rlm_task_create", "rlm_task_complete"],
        description="Claim a task from the queue",
        requires_admin=True,
    ),
    "rlm_task_complete": ToolMetadata(
        name="rlm_task_complete",
        tier=ToolTier.ADVANCED,
        keywords=["task", "complete", "done", "finish", "result"],
        use_cases=[
            "Mark task as completed",
            "Report task result",
        ],
        example='rlm_task_complete(swarm_id="...", task_id="...", success=True)',
        related=["rlm_task_claim"],
        description="Mark task as completed",
        requires_admin=True,
    ),
    "rlm_orchestrate": ToolMetadata(
        name="rlm_orchestrate",
        tier=ToolTier.ADVANCED,
        keywords=["orchestrate", "multi-round", "explore", "comprehensive"],
        use_cases=[
            "Multi-round context exploration",
            "Comprehensive query execution",
        ],
        example='rlm_orchestrate(query="auth flow", top_k=5)',
        related=["rlm_plan", "rlm_decompose"],
        description="Multi-round context exploration in single call",
    ),
    "rlm_load_document": ToolMetadata(
        name="rlm_load_document",
        tier=ToolTier.ADVANCED,
        keywords=["load", "document", "raw", "full"],
        use_cases=[
            "Load raw document content",
            "Get full unprocessed file",
        ],
        example='rlm_load_document(path="docs/api.md")',
        related=["rlm_load_project"],
        description="Load raw document by path",
    ),
    "rlm_load_project": ToolMetadata(
        name="rlm_load_project",
        tier=ToolTier.ADVANCED,
        keywords=["load", "project", "all", "dump", "full"],
        use_cases=[
            "Load all project documents",
            "Full project context dump",
        ],
        example="rlm_load_project(max_tokens=16000)",
        related=["rlm_load_document"],
        description="Load structured map of all project documents",
    ),
    "rlm_repl_context": ToolMetadata(
        name="rlm_repl_context",
        tier=ToolTier.ADVANCED,
        keywords=["repl", "context", "runtime", "code", "execute"],
        use_cases=[
            "Package context for REPL",
            "Prepare for code execution",
        ],
        example='rlm_repl_context(query="auth implementation")',
        related=["rlm_orchestrate"],
        description="Package context for REPL consumption",
    ),
    "rlm_get_chunk": ToolMetadata(
        name="rlm_get_chunk",
        tier=ToolTier.ADVANCED,
        keywords=["chunk", "get", "reference", "id", "retrieve"],
        use_cases=[
            "Get chunk by ID",
            "Retrieve referenced content",
        ],
        example='rlm_get_chunk(chunk_id="chunk_abc123")',
        related=["rlm_context_query"],
        description="Retrieve full content by chunk ID",
    ),
    "rlm_request_access": ToolMetadata(
        name="rlm_request_access",
        tier=ToolTier.ADVANCED,
        keywords=["access", "request", "permission", "team"],
        use_cases=[
            "Request project access",
            "Ask for permissions",
        ],
        example='rlm_request_access(project_id="...")',
        related=[],
        description="Request access to a project",
    ),
}


def _normalize_query(query: str) -> list[str]:
    """Normalize query into lowercase keywords."""
    # Simple tokenization - could be enhanced with stemming
    words = query.lower().split()
    # Remove common stop words
    stop_words = {
        "a",
        "an",
        "the",
        "is",
        "are",
        "to",
        "for",
        "in",
        "on",
        "how",
        "do",
        "i",
        "can",
        "what",
        "which",
        "should",
        "with",
        "without",
        "into",
        "from",
        "via",
        "agent",
        "automatically",
    }
    return [w.strip("?,.'\"") for w in words if w not in stop_words and len(w) > 1]


def _contains_phrase(query: str, phrases: list[str]) -> bool:
    """Return True when any phrase is present in the query."""
    return any(phrase in query for phrase in phrases)


def _compute_intent_boost(metadata: ToolMetadata, query_terms: list[str], query: str) -> float:
    """Boost or demote tools when the query reflects a higher-level workflow."""
    terms = set(query_terms)
    memory_terms = {
        "memory",
        "memories",
        "recall",
        "remember",
        "persist",
        "durable",
        "knowledge",
        "decision",
        "decisions",
        "learning",
        "preference",
        "workflow",
        "workflows",
        "session",
        "resume",
        "bootstrap",
        "profile",
        "workspace",
        "commit",
        "novel",
        "novelty",
        "duplicate",
        "duplicates",
        "dedupe",
    }
    swarm_terms = {
        "swarm",
        "queue",
        "claim",
        "worker",
        "workers",
        "broadcast",
        "coordination",
        "resource",
    }
    has_memory_intent = len(terms & memory_terms) >= 2 or _contains_phrase(
        query,
        [
            "end of task",
            "session start",
            "session bootstrap",
            "workspace profile",
            "without duplicates",
            "durable knowledge",
        ],
    )
    has_swarm_intent = bool(terms & swarm_terms) or _contains_phrase(
        query, ["multi-agent", "multi agent", "shared state", "task queue"]
    )

    session_bootstrap_intent = len(terms & {"session", "resume", "bootstrap", "recall"}) >= 2 or _contains_phrase(
        query,
        [
            "session bootstrap",
            "session start",
            "on resume",
            "resume session",
            "auto recall",
            "auto-load",
        ],
    )
    workspace_profile_intent = len(terms & {"workspace", "tenant", "profile", "constraints"}) >= 2 or _contains_phrase(
        query, ["workspace profile", "tenant profile", "client profile"]
    )
    durable_commit_intent = len(terms & {"persist", "durable", "knowledge", "commit", "summary"}) >= 2 or _contains_phrase(
        query,
        [
            "end of task",
            "task summary",
            "task completion",
            "end-of-task",
            "durable knowledge",
        ],
    )
    dedupe_intent = bool(terms & {"duplicate", "duplicates", "dedupe", "novel", "novelty"}) or _contains_phrase(
        query, ["without duplicates", "avoid duplicates", "if novel"]
    )
    daily_brief_intent = len(terms & {"daily", "brief", "active", "constraints", "todo"}) >= 2 or _contains_phrase(
        query, ["daily brief", "active constraints"]
    )
    index_health_intent = len(terms & {"index", "coverage", "chunks", "stale", "health", "quality"}) >= 2 or _contains_phrase(
        query,
        [
            "index health",
            "index coverage",
            "missing chunks",
            "search quality",
            "stale index",
        ],
    )
    reindex_intent = bool(terms & {"reindex", "rebuild", "refresh"}) or _contains_phrase(
        query,
        [
            "reindex the project",
            "reindex project",
            "trigger reindex",
            "run reindex",
            "full reindex",
            "rebuild the index",
        ],
    )
    direct_write_intent = bool(terms & {"store", "save", "write", "remember"}) and not (
        durable_commit_intent or dedupe_intent
    )

    boost = 0.0

    if session_bootstrap_intent:
        if metadata.name == "rlm_session_memories":
            boost += 70.0
        elif metadata.name == "rlm_tenant_profile_get":
            boost += 45.0
        elif metadata.name == "rlm_recall":
            boost += 20.0

    if workspace_profile_intent:
        if metadata.name == "rlm_tenant_profile_get":
            boost += 65.0
        elif metadata.name == "rlm_session_memories":
            boost += 15.0

    if durable_commit_intent:
        if metadata.name == "rlm_end_of_task_commit":
            boost += 80.0
        elif metadata.name == "rlm_remember_if_novel":
            boost += 35.0
        elif metadata.name == "rlm_journal_summarize":
            boost += 10.0
        elif metadata.name == "rlm_remember" and not direct_write_intent:
            boost -= 12.0

    if dedupe_intent:
        if metadata.name == "rlm_remember_if_novel":
            boost += 55.0
        elif metadata.name == "rlm_end_of_task_commit":
            boost += 20.0
        elif metadata.name == "rlm_memory_compact":
            boost += 12.0
        elif metadata.name == "rlm_remember":
            boost -= 10.0

    if daily_brief_intent:
        if metadata.name == "rlm_memory_daily_brief":
            boost += 75.0
        elif metadata.name == "rlm_session_memories":
            boost += 15.0

    if index_health_intent:
        if metadata.name == "rlm_index_health":
            boost += 55.0
        elif metadata.name == "rlm_index_recommendations":
            boost += 35.0

    if reindex_intent:
        if metadata.name == "rlm_reindex":
            boost += 90.0
        elif metadata.name == "rlm_index_recommendations":
            boost += 30.0
        elif metadata.name == "rlm_index_health":
            boost += 15.0

    if has_memory_intent and not has_swarm_intent and metadata.name in {
        "rlm_agent_profile_get",
        "rlm_agent_profile_update",
        "rlm_swarm_create",
        "rlm_swarm_join",
        "rlm_claim",
        "rlm_release",
        "rlm_broadcast",
        "rlm_task_create",
        "rlm_task_claim",
        "rlm_task_complete",
    }:
        boost -= 30.0

    return boost


def _compute_score(metadata: ToolMetadata, query_terms: list[str], query: str) -> float:
    """Compute relevance score for a tool based on query terms."""
    score = 0.0

    # Keyword matching (exact: +10, partial: +3)
    for term in query_terms:
        for kw in metadata.keywords:
            if term == kw:
                score += 10.0
            elif term in kw or kw in term:
                score += 3.0

    # Use case matching (+5 per match)
    for use_case in metadata.use_cases:
        use_case_lower = use_case.lower()
        matching_terms = sum(1 for t in query_terms if t in use_case_lower)
        if matching_terms > 0:
            score += 5.0 * matching_terms

    # Description matching (+2 per term)
    desc_lower = metadata.description.lower()
    for term in query_terms:
        if term in desc_lower:
            score += 2.0

    # Tier boost (PRIMARY tools get slight boost)
    if metadata.tier == ToolTier.PRIMARY:
        score += 1.0

    score += _compute_intent_boost(metadata, query_terms, query)

    return score


def recommend_tools(
    query: str,
    limit: int = 5,
    include_team: bool = False,
    include_admin: bool = False,
) -> list[dict]:
    """
    Recommend tools based on user query.

    Args:
        query: Natural language query describing what user wants to do
        limit: Maximum number of recommendations
        include_team: Include team-tier tools in results
        include_admin: Include admin-tier tools in results

    Returns:
        List of tool recommendations with scores
    """
    if not query or not query.strip():
        # Return primary tools by default
        return [
            {
                "tool": "rlm_context_query",
                "score": 100.0,
                "tier": ToolTier.PRIMARY,
                "description": TOOL_METADATA["rlm_context_query"].description,
                "example": TOOL_METADATA["rlm_context_query"].example,
                "use_cases": TOOL_METADATA["rlm_context_query"].use_cases,
            }
        ]

    query_terms = _normalize_query(query)
    if not query_terms:
        query_terms = query.lower().split()[:5]  # Fallback

    scored_tools: list[tuple[str, float, ToolMetadata]] = []

    for name, metadata in TOOL_METADATA.items():
        # Filter based on permissions
        if metadata.requires_team and not include_team:
            continue
        if metadata.requires_admin and not include_admin:
            continue

        score = _compute_score(metadata, query_terms, query.lower())
        if score > 0:
            scored_tools.append((name, score, metadata))

    # Sort by score descending
    scored_tools.sort(key=lambda x: x[1], reverse=True)

    # Take top N
    results = []
    for name, score, metadata in scored_tools[:limit]:
        results.append({
            "tool": name,
            "score": round(score, 1),
            "tier": metadata.tier,
            "description": metadata.description,
            "example": metadata.example,
            "use_cases": metadata.use_cases,
            "related": metadata.related,
        })

    # If no matches, suggest primary tools
    if not results:
        primary_tools = [m for m in TOOL_METADATA.values() if m.tier == ToolTier.PRIMARY][:limit]
        for metadata in primary_tools:
            results.append({
                "tool": metadata.name,
                "score": 0.0,
                "tier": metadata.tier,
                "description": metadata.description,
                "example": metadata.example,
                "use_cases": metadata.use_cases,
                "related": metadata.related,
                "note": "No exact matches - showing primary tools",
            })

    return results


def get_tool_info(tool_name: str) -> dict | None:
    """
    Get detailed information about a specific tool.

    Args:
        tool_name: Name of the tool (e.g., "rlm_context_query")

    Returns:
        Tool metadata dict or None if not found
    """
    metadata = TOOL_METADATA.get(tool_name)
    if not metadata:
        return None

    return {
        "tool": metadata.name,
        "tier": metadata.tier,
        "description": metadata.description,
        "keywords": metadata.keywords,
        "use_cases": metadata.use_cases,
        "example": metadata.example,
        "related": metadata.related,
        "requires_team": metadata.requires_team,
        "requires_admin": metadata.requires_admin,
    }


def list_tools_by_tier(tier: ToolTier | None = None) -> list[dict]:
    """
    List all tools, optionally filtered by tier.

    Args:
        tier: Optional tier to filter by

    Returns:
        List of tool summaries
    """
    results = []
    for name, metadata in TOOL_METADATA.items():
        if tier is not None and metadata.tier != tier:
            continue
        results.append({
            "tool": name,
            "tier": metadata.tier,
            "description": metadata.description,
        })

    # Sort by tier priority, then alphabetically
    tier_order = {
        ToolTier.PRIMARY: 0,
        ToolTier.POWER_USER: 1,
        ToolTier.TEAM: 2,
        ToolTier.UTILITY: 3,
        ToolTier.ADVANCED: 4,
    }
    results.sort(key=lambda x: (tier_order.get(x["tier"], 99), x["tool"]))

    return results
