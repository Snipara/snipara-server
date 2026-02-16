"""MCP Tool Definitions for Snipara.

This module contains all tool definitions returned by the tools/list method.
Each tool definition includes the schema for its input parameters.

Tool Categories:
    - Context Retrieval: rlm_context_query, rlm_ask, rlm_search, rlm_read
    - Query Optimization: rlm_decompose, rlm_multi_query, rlm_plan
    - Team Queries: rlm_multi_project_query (requires team API key)
    - Session Management: rlm_inject, rlm_context, rlm_clear_context
    - Metadata: rlm_stats, rlm_sections, rlm_settings
    - Summaries: rlm_store_summary, rlm_get_summaries, rlm_delete_summary
    - Shared Context: rlm_shared_context, rlm_list_templates, rlm_get_template
    - Agent Memory: rlm_remember, rlm_recall, rlm_memories, rlm_forget
    - Multi-Agent Swarm: rlm_swarm_*, rlm_claim, rlm_release, rlm_state_*, rlm_task_*
    - Document Sync: rlm_upload_document, rlm_sync_documents
    - RLM Orchestration: rlm_load_document, rlm_load_project, rlm_orchestrate, rlm_repl_context
    - Pass-by-Reference: rlm_get_chunk

Tool Tiers:
    - PRIMARY (🟢): Essential tools for all users - start here
    - POWER_USER (🔵): Advanced features for intermediate users
    - TEAM (🟡): Team collaboration and multi-project features
    - UTILITY (⚪): Session and project management utilities
    - ADVANCED (🔴): Multi-agent swarms and expert orchestration
"""

from enum import Enum


class ToolTier(str, Enum):
    """Tool tier classification for user guidance."""

    PRIMARY = "primary"  # Essential tools for all users
    POWER_USER = "power_user"  # Advanced features for intermediate users
    TEAM = "team"  # Team collaboration and multi-project
    UTILITY = "utility"  # Session management and utilities
    ADVANCED = "advanced"  # Multi-agent swarms and orchestration


# Mapping of tool name -> tier for discovery and filtering
TOOL_TIERS: dict[str, ToolTier] = {
    # PRIMARY (🟢) - Essential tools, start here
    "rlm_context_query": ToolTier.PRIMARY,
    "rlm_ask": ToolTier.PRIMARY,
    "rlm_search": ToolTier.PRIMARY,
    "rlm_read": ToolTier.PRIMARY,
    "rlm_recall": ToolTier.PRIMARY,
    "rlm_stats": ToolTier.PRIMARY,
    # POWER_USER (🔵) - Advanced features
    "rlm_multi_query": ToolTier.POWER_USER,
    "rlm_decompose": ToolTier.POWER_USER,
    "rlm_plan": ToolTier.POWER_USER,
    "rlm_remember": ToolTier.POWER_USER,
    "rlm_remember_bulk": ToolTier.POWER_USER,
    "rlm_store_summary": ToolTier.POWER_USER,
    "rlm_get_summaries": ToolTier.POWER_USER,
    "rlm_load_document": ToolTier.POWER_USER,
    "rlm_memories": ToolTier.POWER_USER,
    # TEAM (🟡) - Team collaboration
    "rlm_multi_project_query": ToolTier.TEAM,
    "rlm_shared_context": ToolTier.TEAM,
    "rlm_list_templates": ToolTier.TEAM,
    "rlm_get_template": ToolTier.TEAM,
    "rlm_upload_shared_document": ToolTier.TEAM,
    "rlm_list_collections": ToolTier.TEAM,
    "rlm_load_project": ToolTier.TEAM,
    # UTILITY (⚪) - Session management
    "rlm_inject": ToolTier.UTILITY,
    "rlm_context": ToolTier.UTILITY,
    "rlm_clear_context": ToolTier.UTILITY,
    "rlm_sections": ToolTier.UTILITY,
    "rlm_settings": ToolTier.UTILITY,
    "rlm_forget": ToolTier.UTILITY,
    "rlm_delete_summary": ToolTier.UTILITY,
    "rlm_get_chunk": ToolTier.UTILITY,
    # ADVANCED (🔴) - Multi-agent and orchestration
    "rlm_orchestrate": ToolTier.ADVANCED,
    "rlm_repl_context": ToolTier.ADVANCED,
    "rlm_upload_document": ToolTier.ADVANCED,
    "rlm_sync_documents": ToolTier.ADVANCED,
    "rlm_swarm_create": ToolTier.ADVANCED,
    "rlm_swarm_join": ToolTier.ADVANCED,
    "rlm_claim": ToolTier.ADVANCED,
    "rlm_release": ToolTier.ADVANCED,
    "rlm_state_get": ToolTier.ADVANCED,
    "rlm_state_set": ToolTier.ADVANCED,
    "rlm_broadcast": ToolTier.ADVANCED,
    "rlm_task_create": ToolTier.ADVANCED,
    "rlm_task_claim": ToolTier.ADVANCED,
    "rlm_task_complete": ToolTier.ADVANCED,
}


def get_tool_tier(tool_name: str) -> ToolTier:
    """Get tier for a tool (defaults to UTILITY if not mapped)."""
    return TOOL_TIERS.get(tool_name, ToolTier.UTILITY)


TOOL_DEFINITIONS: list[dict] = [
    # ============ Context Retrieval Tools ============
    {
        "name": "rlm_context_query",
        "description": "Query optimized context from documentation. Returns ranked sections within token budget.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Question or topic"},
                "max_tokens": {
                    "type": "integer",
                    "default": 4000,
                    "minimum": 100,
                    "maximum": 100000,
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "semantic", "hybrid"],
                    "default": "hybrid",
                },
                "include_metadata": {"type": "boolean", "default": True},
                "prefer_summaries": {"type": "boolean", "default": False},
                "return_references": {
                    "type": "boolean",
                    "default": False,
                    "description": "Return chunk references (IDs + previews) instead of full content. Use rlm_get_chunk to retrieve full content by ID. Reduces hallucination by maintaining clear source attribution.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "rlm_ask",
        "description": "Query documentation with a question (basic). Use rlm_context_query for better results.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "The question to ask"}},
            "required": ["query"],
        },
    },
    {
        "name": "rlm_search",
        "description": "Search documentation for a regex pattern.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "max_results": {"type": "integer", "default": 20},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "rlm_read",
        "description": "Read specific lines from documentation.",
        "inputSchema": {
            "type": "object",
            "properties": {"start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
            "required": ["start_line", "end_line"],
        },
    },
    # ============ Query Optimization Tools ============
    {
        "name": "rlm_decompose",
        "description": "Break complex query into sub-queries with execution order.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_depth": {"type": "integer", "default": 2, "minimum": 1, "maximum": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "rlm_multi_query",
        "description": "Execute multiple queries in one call with shared token budget.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "max_tokens": {"type": "integer"},
                        },
                        "required": ["query"],
                    },
                    "minItems": 1,
                    "maxItems": 10,
                },
                "max_tokens": {"type": "integer", "default": 8000},
            },
            "required": ["queries"],
        },
    },
    {
        "name": "rlm_plan",
        "description": "Generate full execution plan for complex questions. Returns steps for decomposition, context queries, and synthesis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The complex question to plan for"},
                "strategy": {
                    "type": "string",
                    "enum": ["breadth_first", "depth_first", "relevance_first"],
                    "default": "relevance_first",
                    "description": "Execution strategy",
                },
                "max_tokens": {
                    "type": "integer",
                    "default": 16000,
                    "minimum": 1000,
                    "maximum": 100000,
                },
            },
            "required": ["query"],
        },
    },
    # ============ Team Query Tools ============
    {
        "name": "rlm_multi_project_query",
        "description": "Query across all projects in a team. Requires team API key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Question or topic"},
                "max_tokens": {
                    "type": "integer",
                    "default": 4000,
                    "minimum": 100,
                    "maximum": 100000,
                },
                "per_project_limit": {"type": "integer", "default": 3, "minimum": 1, "maximum": 20},
                "project_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional project IDs/slugs to include",
                },
                "exclude_project_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional project IDs/slugs to exclude",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "semantic", "hybrid"],
                    "default": "keyword",
                },
                "include_metadata": {"type": "boolean", "default": True},
                "prefer_summaries": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
    },
    # ============ Session Management Tools ============
    {
        "name": "rlm_inject",
        "description": "Set session context for subsequent queries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {"type": "string"},
                "append": {"type": "boolean", "default": False},
            },
            "required": ["context"],
        },
    },
    {
        "name": "rlm_context",
        "description": "Show current session context.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "rlm_clear_context",
        "description": "Clear session context.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    # ============ Metadata Tools ============
    {
        "name": "rlm_stats",
        "description": "Show documentation statistics.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "rlm_sections",
        "description": "List indexed document sections with optional pagination and filtering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum sections to return (default: 50, max: 500)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of sections to skip for pagination (default: 0)",
                },
                "filter": {
                    "type": "string",
                    "description": "Filter sections by title prefix (case-insensitive)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_settings",
        "description": "Get current project settings from dashboard (max_tokens, search_mode, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "refresh": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force refresh from API",
                },
            },
            "required": [],
        },
    },
    # ============ Summary Tools ============
    {
        "name": "rlm_store_summary",
        "description": "Store an LLM-generated summary for a document.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_path": {"type": "string"},
                "summary": {"type": "string"},
                "summary_type": {
                    "type": "string",
                    "enum": ["concise", "detailed", "technical", "keywords", "custom"],
                    "default": "concise",
                },
                "generated_by": {"type": "string"},
            },
            "required": ["document_path", "summary"],
        },
    },
    {
        "name": "rlm_get_summaries",
        "description": "Retrieve stored summaries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_path": {"type": "string"},
                "summary_type": {
                    "type": "string",
                    "enum": ["concise", "detailed", "technical", "keywords", "custom"],
                },
                "include_content": {"type": "boolean", "default": True},
            },
            "required": [],
        },
    },
    {
        "name": "rlm_delete_summary",
        "description": "Delete stored summaries.",
        "inputSchema": {
            "type": "object",
            "properties": {"summary_id": {"type": "string"}, "document_path": {"type": "string"}},
            "required": [],
        },
    },
    # ============ Shared Context Tools ============
    {
        "name": "rlm_shared_context",
        "description": "Get merged context from linked shared collections. Returns categorized docs with budget allocation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_tokens": {
                    "type": "integer",
                    "default": 4000,
                    "minimum": 100,
                    "maximum": 100000,
                },
                "categories": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["MANDATORY", "BEST_PRACTICES", "GUIDELINES", "REFERENCE"],
                    },
                    "description": "Filter by categories (default: all)",
                },
                "include_content": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include merged content",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_list_templates",
        "description": "List available prompt templates from shared collections.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filter by category"},
            },
            "required": [],
        },
    },
    {
        "name": "rlm_get_template",
        "description": "Get a specific prompt template by ID or slug. Optionally render with variables.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_id": {"type": "string", "description": "Template ID"},
                "slug": {"type": "string", "description": "Template slug"},
                "variables": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Variables to substitute in template",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_list_collections",
        "description": "List all shared context collections accessible to you. Returns collections you own, team collections you're a member of, and public collections. Use this to find collection IDs for uploading documents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_public": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include public collections in the results",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_upload_shared_document",
        "description": "Upload or update a document in a shared context collection. Use for team best practices, coding standards, and guidelines. Requires Team plan or higher.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "description": "The shared collection ID"},
                "title": {"type": "string", "description": "Document title"},
                "content": {"type": "string", "description": "Document content (markdown)"},
                "category": {
                    "type": "string",
                    "enum": ["MANDATORY", "BEST_PRACTICES", "GUIDELINES", "REFERENCE"],
                    "default": "BEST_PRACTICES",
                    "description": "Document category for token budget allocation",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for filtering and organization",
                },
                "priority": {
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Priority within category (higher = more important)",
                },
            },
            "required": ["collection_id", "title", "content"],
        },
    },
    # ============ Agent Memory Tools ============
    {
        "name": "rlm_remember",
        "description": "Store a memory for later semantic recall. Supports types: fact, decision, learning, preference, todo, context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The memory text to store"},
                "content": {
                    "type": "string",
                    "description": "DEPRECATED: Use 'text' instead. The memory content to store.",
                },
                "type": {
                    "type": "string",
                    "enum": ["fact", "decision", "learning", "preference", "todo", "context"],
                    "default": "fact",
                },
                "scope": {
                    "type": "string",
                    "enum": ["agent", "project", "team", "user"],
                    "default": "project",
                },
                "category": {"type": "string", "description": "Optional category for grouping"},
                "ttl_days": {
                    "type": "integer",
                    "description": "Days until expiration (null = permanent)",
                },
                "related_to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of related memories",
                },
                "document_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Referenced document paths",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_remember_bulk",
        "description": "Store multiple memories in a single call. Batch embedding for efficiency. Max 50 memories per call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "Memory text to store"},
                            "type": {
                                "type": "string",
                                "enum": [
                                    "fact",
                                    "decision",
                                    "learning",
                                    "preference",
                                    "todo",
                                    "context",
                                ],
                                "default": "fact",
                            },
                            "scope": {
                                "type": "string",
                                "enum": ["agent", "project", "team", "user"],
                                "default": "project",
                            },
                            "category": {"type": "string"},
                            "ttl_days": {"type": "integer"},
                            "related_to": {"type": "array", "items": {"type": "string"}},
                            "document_refs": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["text"],
                    },
                    "minItems": 1,
                    "maxItems": 50,
                    "description": "Array of memories to store (max 50)",
                },
            },
            "required": ["memories"],
        },
    },
    {
        "name": "rlm_recall",
        "description": "Semantically recall relevant memories based on a query. Uses embeddings weighted by confidence decay.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "type": {
                    "type": "string",
                    "enum": ["fact", "decision", "learning", "preference", "todo", "context"],
                },
                "scope": {"type": "string", "enum": ["agent", "project", "team", "user"]},
                "category": {"type": "string", "description": "Filter by category"},
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "description": "Maximum memories to return",
                },
                "min_relevance": {
                    "type": "number",
                    "default": 0.5,
                    "description": "Minimum relevance score (0-1)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "rlm_memories",
        "description": "List memories with optional filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["fact", "decision", "learning", "preference", "todo", "context"],
                },
                "scope": {"type": "string", "enum": ["agent", "project", "team", "user"]},
                "category": {"type": "string"},
                "search": {"type": "string", "description": "Text search in content"},
                "limit": {"type": "integer", "default": 20},
                "offset": {"type": "integer", "default": 0},
            },
            "required": [],
        },
    },
    {
        "name": "rlm_forget",
        "description": "Delete memories by ID or filter criteria.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "Specific memory ID to delete"},
                "type": {
                    "type": "string",
                    "enum": ["fact", "decision", "learning", "preference", "todo", "context"],
                },
                "category": {"type": "string", "description": "Delete all in this category"},
                "older_than_days": {
                    "type": "integer",
                    "description": "Delete memories older than N days",
                },
            },
            "required": [],
        },
    },
    # ============ Multi-Agent Swarm Tools ============
    {
        "name": "rlm_swarm_create",
        "description": "Create a new agent swarm for multi-agent coordination.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Swarm name"},
                "description": {"type": "string"},
                "max_agents": {"type": "integer", "default": 10},
                "config": {"type": "object"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "rlm_swarm_join",
        "description": "Join an existing swarm as an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm to join"},
                "agent_id": {"type": "string", "description": "Your unique agent identifier"},
                "role": {
                    "type": "string",
                    "enum": ["coordinator", "worker", "observer"],
                    "default": "worker",
                },
                "capabilities": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["swarm_id", "agent_id"],
        },
    },
    {
        "name": "rlm_claim",
        "description": "Claim exclusive access to a resource (file, function, module). Claims auto-expire.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "resource_type": {
                    "type": "string",
                    "enum": ["file", "function", "module", "component", "other"],
                },
                "resource_id": {
                    "type": "string",
                    "description": "Resource identifier (e.g., file path)",
                },
                "timeout_seconds": {"type": "integer", "default": 300},
            },
            "required": ["swarm_id", "agent_id", "resource_type", "resource_id"],
        },
    },
    {
        "name": "rlm_release",
        "description": "Release a claimed resource.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "claim_id": {"type": "string"},
                "resource_type": {"type": "string"},
                "resource_id": {"type": "string"},
            },
            "required": ["swarm_id", "agent_id"],
        },
    },
    {
        "name": "rlm_state_get",
        "description": "Read shared swarm state by key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string"},
                "key": {"type": "string", "description": "State key to read"},
            },
            "required": ["swarm_id", "key"],
        },
    },
    {
        "name": "rlm_state_set",
        "description": "Write shared swarm state with optimistic locking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "key": {"type": "string"},
                "value": {"description": "Value to set (any JSON-serializable type)"},
                "expected_version": {
                    "type": "integer",
                    "description": "Expected version for optimistic locking",
                },
            },
            "required": ["swarm_id", "agent_id", "key", "value"],
        },
    },
    {
        "name": "rlm_broadcast",
        "description": "Send an event to all agents in the swarm.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "event_type": {"type": "string", "description": "Event type"},
                "payload": {"type": "object", "description": "Event data"},
            },
            "required": ["swarm_id", "agent_id", "event_type"],
        },
    },
    {
        "name": "rlm_task_create",
        "description": "Create a task in the swarm's distributed task queue.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "priority": {
                    "type": "integer",
                    "default": 0,
                    "description": "Higher = more urgent",
                },
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs this depends on",
                },
                "metadata": {"type": "object"},
            },
            "required": ["swarm_id", "agent_id", "title"],
        },
    },
    {
        "name": "rlm_task_claim",
        "description": "Claim a task from the queue. If task_id not specified, claims highest priority available task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "task_id": {"type": "string", "description": "Specific task to claim (optional)"},
                "timeout_seconds": {"type": "integer", "default": 600},
            },
            "required": ["swarm_id", "agent_id"],
        },
    },
    {
        "name": "rlm_task_complete",
        "description": "Mark a claimed task as completed or failed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "task_id": {"type": "string"},
                "success": {"type": "boolean", "default": True},
                "result": {"description": "Task result data"},
            },
            "required": ["swarm_id", "agent_id", "task_id"],
        },
    },
    # ============ Document Sync Tools ============
    {
        "name": "rlm_upload_document",
        "description": "Upload or update a document in the project. Supports .md, .txt, .mdx files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Document path (e.g., 'docs/api.md')"},
                "content": {"type": "string", "description": "Document content (markdown)"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "rlm_sync_documents",
        "description": "Bulk sync multiple documents. Use for batch uploads or CI/CD integration.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "documents": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                    "description": "Documents to sync",
                },
                "delete_missing": {
                    "type": "boolean",
                    "default": False,
                    "description": "Delete docs not in list",
                },
            },
            "required": ["documents"],
        },
    },
    # ============ RLM Orchestration Tools ============
    {
        "name": "rlm_load_document",
        "description": "Load raw document content by file path. Returns the full unprocessed content of a single document for RLM-style exploration where the model navigates raw content directly.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Document path (e.g., 'docs/api.md')"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "rlm_load_project",
        "description": "Load structured map of all project documents with content. Returns a token-budgeted dump of every file, with optional path filtering. Use for full-project exploration.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_tokens": {
                    "type": "integer",
                    "default": 16000,
                    "description": "Total token budget for returned content",
                },
                "paths_filter": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Only include files matching these path prefixes (e.g., ['docs/', 'src/'])",
                },
                "include_content": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include file content (false = metadata only)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_orchestrate",
        "description": "Multi-round context exploration in a single call. Performs: (1) section scan for project structure, (2) ranked search for top relevant sections, (3) raw file load for highest-scoring documents. Combines search intelligence with raw access.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The question or topic to explore"},
                "max_tokens": {
                    "type": "integer",
                    "default": 16000,
                    "description": "Token budget for raw file content",
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "Number of top sections to use for file selection",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "semantic", "hybrid"],
                    "default": "hybrid",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "rlm_repl_context",
        "description": "Package project context for REPL consumption. Returns a structured dict of files and sections plus Python helper code (peek, grep, sections, files, get_file, search, trim) ready for injection into an rlm-runtime REPL session via set_repl_context + execute_python. Optionally filter by a relevance query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional query to filter context by relevance. If empty, loads files in order within budget.",
                },
                "max_tokens": {
                    "type": "integer",
                    "default": 8000,
                    "description": "Token budget for file content",
                },
                "include_helpers": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include Python helper code (peek, grep, sections, files, get_file, search, trim) in setup_code",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "semantic", "hybrid"],
                    "default": "hybrid",
                    "description": "Search mode when query is provided",
                },
            },
            "required": [],
        },
    },
    # ============ Pass-by-Reference Tools ============
    {
        "name": "rlm_get_chunk",
        "description": "Retrieve full content by chunk ID. Use with rlm_context_query(return_references=True) to fetch full content of specific sections. This pass-by-reference pattern reduces hallucination by maintaining clear source attribution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chunk_id": {
                    "type": "string",
                    "description": "The chunk ID from rlm_context_query results (when return_references=True)",
                },
            },
            "required": ["chunk_id"],
        },
    },
]
