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
    - Agent Memory: rlm_remember, rlm_recall, rlm_memories, rlm_memory_invalidate, rlm_memory_supersede, rlm_forget
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
    "rlm_help": ToolTier.PRIMARY,
    # POWER_USER (🔵) - Advanced features
    "rlm_multi_query": ToolTier.POWER_USER,
    "rlm_decompose": ToolTier.POWER_USER,
    "rlm_plan": ToolTier.POWER_USER,
    "rlm_code_callers": ToolTier.POWER_USER,
    "rlm_code_imports": ToolTier.POWER_USER,
    "rlm_code_neighbors": ToolTier.POWER_USER,
    "rlm_code_shortest_path": ToolTier.POWER_USER,
    "rlm_remember": ToolTier.POWER_USER,
    "rlm_remember_if_novel": ToolTier.POWER_USER,
    "rlm_end_of_task_commit": ToolTier.POWER_USER,
    "rlm_remember_bulk": ToolTier.POWER_USER,
    "rlm_store_summary": ToolTier.POWER_USER,
    "rlm_get_summaries": ToolTier.POWER_USER,
    "rlm_load_document": ToolTier.POWER_USER,
    "rlm_memories": ToolTier.POWER_USER,
    "rlm_memory_invalidate": ToolTier.POWER_USER,
    "rlm_memory_supersede": ToolTier.POWER_USER,
    # TEAM (🟡) - Team collaboration
    "rlm_multi_project_query": ToolTier.TEAM,
    "rlm_shared_context": ToolTier.TEAM,
    "rlm_list_templates": ToolTier.TEAM,
    "rlm_get_template": ToolTier.TEAM,
    "rlm_create_collection": ToolTier.TEAM,
    "rlm_get_collection_documents": ToolTier.TEAM,
    "rlm_link_collection": ToolTier.TEAM,
    "rlm_unlink_collection": ToolTier.TEAM,
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
    "rlm_svg_bundle_ingest": ToolTier.ADVANCED,
    "rlm_request_access": ToolTier.UTILITY,  # Request access to a project
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
    "rlm_tasks": ToolTier.ADVANCED,
    "rlm_task_list": ToolTier.ADVANCED,  # Enhanced list with cursor pagination
    "rlm_task_stats": ToolTier.ADVANCED,  # Aggregated task counts by status
    "rlm_task_events": ToolTier.ADVANCED,  # Task status change events
    "rlm_agent_status": ToolTier.ADVANCED,  # Swarm agent discovery tool
    "rlm_swarm_leave": ToolTier.ADVANCED,  # Remove agent from swarm
    "rlm_swarm_members": ToolTier.ADVANCED,  # List agents in swarm
    "rlm_swarm_update": ToolTier.ADVANCED,  # Update swarm config (ADMIN)
    "rlm_task_reassign": ToolTier.ADVANCED,  # Reassign task
    "rlm_task_delete": ToolTier.ADVANCED,  # Delete task (admin only)
    "rlm_task_update": ToolTier.ADVANCED,  # Update task (admin only)
    "rlm_task_unclaim": ToolTier.ADVANCED,  # Unclaim a stuck task
    "rlm_task_recover": ToolTier.ADVANCED,  # Recover stuck tasks in batch
    # ADVANCED - Agent Profiles (Soul Layer)
    "rlm_agent_profile_get": ToolTier.ADVANCED,
    "rlm_agent_profile_update": ToolTier.ADVANCED,
    # POWER_USER - Decision Log
    "rlm_decision_create": ToolTier.POWER_USER,
    "rlm_decision_query": ToolTier.POWER_USER,
    "rlm_decision_supersede": ToolTier.POWER_USER,
    # POWER_USER - Index Health & Analytics (Sprint 3)
    "rlm_index_health": ToolTier.POWER_USER,
    "rlm_index_recommendations": ToolTier.POWER_USER,
    "rlm_reindex": ToolTier.POWER_USER,
    "rlm_search_analytics": ToolTier.POWER_USER,
    "rlm_query_trends": ToolTier.POWER_USER,
    # ADVANCED - Hierarchical Tasks
    "rlm_htask_create": ToolTier.ADVANCED,
    "rlm_htask_create_feature": ToolTier.ADVANCED,
    "rlm_htask_get": ToolTier.ADVANCED,
    "rlm_htask_tree": ToolTier.ADVANCED,
    "rlm_htask_update": ToolTier.ADVANCED,
    "rlm_htask_block": ToolTier.ADVANCED,
    "rlm_htask_unblock": ToolTier.ADVANCED,
    "rlm_htask_complete": ToolTier.ADVANCED,
    "rlm_htask_verify_closure": ToolTier.ADVANCED,
    "rlm_htask_close": ToolTier.ADVANCED,
    "rlm_htask_delete": ToolTier.ADVANCED,
    "rlm_htask_recommend_batch": ToolTier.ADVANCED,
    "rlm_htask_policy_get": ToolTier.ADVANCED,
    "rlm_htask_policy_update": ToolTier.ADVANCED,
    "rlm_htask_metrics": ToolTier.ADVANCED,
    "rlm_htask_audit_trail": ToolTier.ADVANCED,
    "rlm_htask_checkpoint_delta": ToolTier.ADVANCED,
    # POWER_USER - Daily Journal
    "rlm_journal_append": ToolTier.POWER_USER,
    "rlm_journal_get": ToolTier.POWER_USER,
    "rlm_journal_summarize": ToolTier.POWER_USER,
    # POWER_USER - Memory Tiers & Compaction (Phase 20)
    "rlm_session_memories": ToolTier.POWER_USER,
    "rlm_memory_compact": ToolTier.ADVANCED,
    "rlm_memory_daily_brief": ToolTier.POWER_USER,
    # TEAM - Tenant Profile (Phase 20)
    "rlm_tenant_profile_create": ToolTier.TEAM,
    "rlm_tenant_profile_get": ToolTier.TEAM,
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
                "auto_decompose": {
                    "type": "boolean",
                    "default": True,
                    "description": "Auto-decompose complex queries into sub-queries (Pro+ only). Complex queries (50+ words, multiple questions, comparisons) are automatically broken down and results merged. Set to False to disable.",
                },
                "include_all_tiers": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include all context tiers including COLD and ARCHIVE. By default, searches only HOT and WARM tiers for faster, more relevant results.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "rlm_ask",
        "description": "Query documentation with a question (basic). Use rlm_context_query for better results.",
        "alias_of": "rlm_context_query",
        "exposed": False,
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
    {
        "name": "rlm_code_callers",
        "description": "Find callers of a code symbol using the persisted code graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "qualified_name": {
                    "type": "string",
                    "description": "Repo-qualified symbol name",
                },
                "symbol_key": {
                    "type": "string",
                    "description": "Stable symbol key for an exact match",
                },
                "depth": {
                    "type": "integer",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 4,
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_code_imports",
        "description": "List imports for a code symbol or file, or find importers of a module.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "qualified_name": {
                    "type": "string",
                    "description": "Repo-qualified symbol name",
                },
                "symbol_key": {
                    "type": "string",
                    "description": "Stable symbol key for an exact match",
                },
                "file_path": {
                    "type": "string",
                    "description": "Resolve imports for a specific file path",
                },
                "direction": {
                    "type": "string",
                    "enum": ["out", "in"],
                    "default": "out",
                },
                "include_file_nodes": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "For file_path lookups, include every scanned symbol in matched_targets "
                        "instead of the compact module anchor"
                    ),
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_code_neighbors",
        "description": "Return the local code subgraph around a symbol.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "qualified_name": {
                    "type": "string",
                    "description": "Repo-qualified symbol name",
                },
                "symbol_key": {
                    "type": "string",
                    "description": "Stable symbol key for an exact match",
                },
                "depth": {
                    "type": "integer",
                    "default": 2,
                    "minimum": 1,
                    "maximum": 4,
                },
                "edge_kinds": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["CALLS", "CONTAINS", "IMPORTS", "REFERENCES"],
                    },
                    "description": "Optional edge kinds to include",
                },
                "limit": {
                    "type": "integer",
                    "default": 200,
                    "minimum": 1,
                    "maximum": 500,
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_code_shortest_path",
        "description": "Find the shortest structural path between two code symbols.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from": {
                    "type": "string",
                    "description": "Source repo-qualified symbol name",
                },
                "from_symbol_key": {
                    "type": "string",
                    "description": "Exact source symbol key",
                },
                "to": {
                    "type": "string",
                    "description": "Target repo-qualified symbol name",
                },
                "to_symbol_key": {
                    "type": "string",
                    "description": "Exact target symbol key",
                },
                "edge_kinds": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["CALLS", "CONTAINS", "IMPORTS", "REFERENCES"],
                    },
                    "description": "Optional edge kinds to traverse",
                },
                "max_hops": {
                    "type": "integer",
                    "default": 6,
                    "minimum": 1,
                    "maximum": 12,
                },
            },
            "required": [],
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
    {
        "name": "rlm_help",
        "description": "Get intelligent tool recommendations based on what you want to do. Helps discover the right tool for your task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Describe what you want to do (e.g., 'search across all team projects', 'remember a decision')",
                },
                "tool": {
                    "type": "string",
                    "description": "Get detailed info about a specific tool (e.g., 'rlm_context_query')",
                },
                "tier": {
                    "type": "string",
                    "enum": ["primary", "power_user", "team", "utility", "advanced"],
                    "description": "List all tools in a specific tier",
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                    "description": "Maximum recommendations to return",
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
        "name": "rlm_create_collection",
        "description": "Create a new TEAM shared context collection in the current project's team. Use this to separate project-specific best practices from broader team context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Collection display name"},
                "slug": {
                    "type": "string",
                    "description": "Optional collection slug. Defaults to a slugified version of name.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional collection description",
                },
                "is_public": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether the collection should be public",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "rlm_get_collection_documents",
        "description": "Inspect the documents stored in a shared context collection, including optional full content. Use this before copying or splitting mixed collections.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "description": "The shared collection ID"},
                "include_content": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include the full document content in the response",
                },
            },
            "required": ["collection_id"],
        },
    },
    {
        "name": "rlm_link_collection",
        "description": "Link an existing shared collection to a project you can access. Defaults to the current project when project_id_or_slug is omitted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "description": "The shared collection ID"},
                "project_id_or_slug": {
                    "type": "string",
                    "description": "Optional target project ID, slug, or github repo. Defaults to the current project.",
                },
                "priority": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Optional link priority (lower = higher priority)",
                },
                "token_budget_percent": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Optional token budget override for this collection",
                },
                "enabled_categories": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["MANDATORY", "BEST_PRACTICES", "GUIDELINES", "REFERENCE"],
                    },
                    "description": "Optional category allowlist for this project link",
                },
            },
            "required": ["collection_id"],
        },
    },
    {
        "name": "rlm_unlink_collection",
        "description": "Unlink a shared collection from a project you can access. Defaults to the current project when project_id_or_slug is omitted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "description": "The shared collection ID"},
                "project_id_or_slug": {
                    "type": "string",
                    "description": "Optional target project ID, slug, or github repo. Defaults to the current project.",
                },
            },
            "required": ["collection_id"],
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
        "description": "Store a memory for later semantic recall. Direct writes support fact, decision, learning, preference, todo, and context. Use rlm_end_of_task_commit for workflow capture.",
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
                "agent_id": {
                    "type": "string",
                    "description": "Required when scope=agent; identifies the agent-owned memory namespace",
                },
                "external_user_id": {
                    "type": "string",
                    "description": "Integrator client keys only: stable end-user ID for scope=user memory. Snipara hashes and namespaces it per integrator client.",
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
                "source": {
                    "type": "string",
                    "description": "Optional source label for the memory write",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_remember_if_novel",
        "description": "Store a memory only if it is sufficiently novel compared with existing memories. Direct writes support fact, decision, learning, preference, todo, and context. Use rlm_end_of_task_commit for workflow capture. Returns duplicate matches when skipped.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The memory text to store"},
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
                "agent_id": {
                    "type": "string",
                    "description": "Required when scope=agent; identifies the agent-owned memory namespace",
                },
                "external_user_id": {
                    "type": "string",
                    "description": "Integrator client keys only: stable end-user ID for scope=user memory. Snipara hashes and namespaces it per integrator client.",
                },
                "category": {"type": "string"},
                "ttl_days": {"type": "integer"},
                "related_to": {"type": "array", "items": {"type": "string"}},
                "document_refs": {"type": "array", "items": {"type": "string"}},
                "source": {
                    "type": "string",
                    "description": "Optional source label for the memory write",
                },
                "novelty_threshold": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Similarity threshold above which a memory is treated as duplicate",
                },
                "dedupe_limit": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "allow_supersede": {
                    "type": "boolean",
                    "default": True,
                    "description": "Reserved for future conflict handling",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "rlm_end_of_task_commit",
        "description": "Persist durable outcomes from a task summary. This is the workflow entry point via persist_types. Filters out operational noise and stores only novel durable knowledge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Task summary"},
                "outcome": {
                    "type": "string",
                    "enum": ["completed", "partial", "blocked", "abandoned"],
                    "default": "completed",
                },
                "files_touched": {"type": "array", "items": {"type": "string"}},
                "artifacts": {"type": "array", "items": {"type": "string"}},
                "persist_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["decision", "learning", "preference", "workflow"]},
                },
                "category": {"type": "string"},
                "external_user_id": {
                    "type": "string",
                    "description": "Integrator client keys only: stable end-user ID for user-owned memories created from task commits.",
                },
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["summary"],
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
                            "agent_id": {
                                "type": "string",
                                "description": "Required when scope=agent",
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
                "external_user_id": {
                    "type": "string",
                    "description": "Integrator client keys only: stable end-user ID for user-scoped bulk memories. Applies to all memories in the call.",
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
                "agent_id": {
                    "type": "string",
                    "description": "Required when scope=agent; limits recall to one agent namespace",
                },
                "external_user_id": {
                    "type": "string",
                    "description": "Integrator client keys only: stable end-user ID for scope=user recall. Snipara hashes and namespaces it per integrator client.",
                },
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
                "include_inactive": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include inactive memories in the main result set",
                },
                "warning_threshold": {
                    "type": "number",
                    "default": 0.72,
                    "description": "Minimum relevance score for inactive-memory warnings",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "rlm_memories",
        "description": "List memories with optional filters and sorting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["fact", "decision", "learning", "preference", "todo", "context"],
                },
                "scope": {"type": "string", "enum": ["agent", "project", "team", "user"]},
                "agent_id": {
                    "type": "string",
                    "description": "Required when scope=agent; limits listing to one agent namespace",
                },
                "external_user_id": {
                    "type": "string",
                    "description": "Integrator client keys only: stable end-user ID for scope=user memory listing. Snipara hashes and namespaces it per integrator client.",
                },
                "category": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["ACTIVE", "INVALIDATED", "SUPERSEDED"],
                    "description": "Filter by lifecycle status",
                },
                "search": {"type": "string", "description": "Text search in content"},
                "limit": {"type": "integer", "default": 20},
                "offset": {"type": "integer", "default": 0},
                "include_inactive": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include inactive memories in results",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["created_at", "confidence", "access_count", "last_accessed", "expires_at"],
                    "default": "created_at",
                    "description": "Field to sort by",
                },
                "sort_order": {
                    "type": "string",
                    "enum": ["asc", "desc"],
                    "default": "desc",
                    "description": "Sort direction",
                },
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
    {
        "name": "rlm_memory_invalidate",
        "description": "Invalidate a Memory V2 record without deleting it. Accepts a legacy memory ID if a migration map exists.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "Legacy or V2 memory ID"},
                "invalidated_at": {
                    "type": "string",
                    "description": "Optional ISO timestamp. Defaults to now.",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional human-readable invalidation reason",
                },
            },
            "required": ["memory_id"],
        },
    },
    {
        "name": "rlm_memory_attach_source",
        "description": "Attach structured evidence to a Memory V2 record. Accepts a legacy memory ID if a migration map exists.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "Legacy or V2 memory ID"},
                "evidence_type": {
                    "type": "string",
                    "enum": ["DOCUMENT", "CHUNK", "SESSION", "PR", "ISSUE", "COMMIT", "WEBHOOK", "EXTERNAL_URL"],
                    "description": "Evidence type",
                },
                "document_id": {"type": "string", "description": "Optional document ID"},
                "chunk_id": {"type": "string", "description": "Optional chunk ID"},
                "external_ref": {"type": "string", "description": "Optional path or URL"},
                "snippet": {"type": "string", "description": "Optional supporting excerpt"},
                "line_start": {"type": "integer", "description": "Optional start line"},
                "line_end": {"type": "integer", "description": "Optional end line"},
                "weight": {
                    "type": "number",
                    "default": 1.0,
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Evidence weight",
                },
            },
            "required": ["memory_id", "evidence_type"],
        },
    },
    {
        "name": "rlm_memory_supersede",
        "description": "Mark one Memory V2 record as superseded by another. Accepts legacy memory IDs if migration maps exist.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "old_memory_id": {"type": "string", "description": "Legacy or V2 memory ID being replaced"},
                "new_memory_id": {"type": "string", "description": "Legacy or V2 replacement memory ID"},
                "reason": {"type": "string", "description": "Optional supersession reason"},
            },
            "required": ["old_memory_id", "new_memory_id"],
        },
    },
    {
        "name": "rlm_memory_verify",
        "description": "Verify whether a Memory V2 record still has valid supporting evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "Legacy or V2 memory ID"},
                "mark_stale_if_missing": {
                    "type": "boolean",
                    "default": True,
                    "description": "Mark memory stale when all evidence is invalid",
                },
            },
            "required": ["memory_id"],
        },
    },
    # ============ Daily Journal Tools ============
    {
        "name": "rlm_journal_append",
        "description": "Append an entry to today's journal. Journals are daily logs of operational notes, decisions, and context. Auto-loads today + yesterday on session start.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Journal entry text (markdown supported)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for categorization",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "rlm_journal_get",
        "description": "Get journal entries for a specific date. Returns all entries from that day's operational log.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format (default: today)",
                },
                "include_yesterday": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also include yesterday's entries",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_journal_summarize",
        "description": "Get journal entries for a date, ready for summarization. Use before archiving old journals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date to summarize (YYYY-MM-DD)",
                },
            },
            "required": ["date"],
        },
    },
    # ============ Memory Tiers & Compaction Tools (Phase 20) ============
    {
        "name": "rlm_session_memories",
        "description": "Get tiered memories for session auto-load. Returns CRITICAL (decisions, facts) and DAILY (context, todos) memories organized by tier with token budgets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_critical_tokens": {
                    "type": "integer",
                    "default": 8000,
                    "description": "Token budget for CRITICAL tier",
                },
                "max_daily_tokens": {
                    "type": "integer",
                    "default": 4000,
                    "description": "Token budget for DAILY tier",
                },
                "include_yesterday": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include yesterday's daily memories",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Optional agent namespace to include in the session bundle",
                },
                "external_user_id": {
                    "type": "string",
                    "description": "Integrator client keys only: stable end-user ID whose personal memories should be included in the session bundle.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_memory_compact",
        "description": "Compact and optimize memories. Deduplicates similar memories, promotes frequent learnings to CRITICAL tier, and archives old entries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["agent", "project", "team"],
                    "default": "project",
                    "description": "Memory scope to compact",
                },
                "deduplicate": {
                    "type": "boolean",
                    "default": True,
                    "description": "Merge similar memories",
                },
                "promote_threshold": {
                    "type": "integer",
                    "default": 3,
                    "description": "If learning accessed N times, promote to CRITICAL",
                },
                "archive_older_than_days": {
                    "type": "integer",
                    "default": 30,
                    "description": "Archive memories older than N days",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "Preview changes without applying",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_memory_daily_brief",
        "description": "Generate a 'Top N active constraints' daily brief. Summarizes critical decisions, active rules, and pending todos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date for brief (default: today)",
                },
                "max_items": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum items to include",
                },
            },
            "required": [],
        },
    },
    # ============ Tenant Profile Tools (Phase 20) ============
    {
        "name": "rlm_tenant_profile_create",
        "description": "Create a structured tenant/client profile. Stored as CRITICAL memory for auto-loading. Use for client onboarding.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "client_name": {
                    "type": "string",
                    "description": "Name of the client/tenant (required)",
                },
                "business_model": {
                    "type": "string",
                    "description": "How the business works",
                },
                "industry": {
                    "type": "string",
                    "description": "Industry vertical",
                },
                "tech_stack": {
                    "type": "string",
                    "description": "Technology stack used",
                },
                "legal_constraints": {
                    "type": "string",
                    "description": "Legal requirements",
                },
                "security_requirements": {
                    "type": "string",
                    "description": "Security constraints",
                },
                "ui_ux_prefs": {
                    "type": "string",
                    "description": "UI/UX preferences",
                },
                "communication_style": {
                    "type": "string",
                    "description": "How to communicate",
                },
                "risk_tolerance": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Risk tolerance level",
                },
                "dos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of things to do",
                },
                "donts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of things to avoid",
                },
                "custom_fields": {
                    "type": "object",
                    "description": "Additional custom fields",
                },
            },
            "required": ["client_name"],
        },
    },
    {
        "name": "rlm_tenant_profile_get",
        "description": "Get tenant profile(s) for a project. Returns latest profile if tenant_id not specified.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tenant_id": {
                    "type": "string",
                    "description": "Specific profile ID (optional, returns all if not specified)",
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
        "name": "rlm_agent_profile_get",
        "description": "Get an agent's profile (identity, personality, boundaries). Auto-loaded on session start for swarm agents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "agent_id": {"type": "string", "description": "Agent identifier"},
            },
            "required": ["swarm_id", "agent_id"],
        },
    },
    {
        "name": "rlm_agent_profile_update",
        "description": "Update an agent's profile. Use to set personality, boundaries, communication style.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "agent_id": {"type": "string", "description": "Agent identifier"},
                "profile": {
                    "type": "object",
                    "description": "Profile data (merged with existing)",
                    "properties": {
                        "display_name": {"type": "string", "description": "Display name (e.g., 'Jarvis ⚡')"},
                        "personality": {"type": "string", "description": "Personality type (e.g., 'INTJ - Strategic')"},
                        "role_description": {"type": "string", "description": "Role description"},
                        "boundaries": {"type": "array", "items": {"type": "string"}, "description": "Boundaries and limits"},
                        "communication_style": {"type": "string", "description": "Preferred communication style"},
                        "decision_making": {"type": "string", "description": "Decision-making approach"},
                        "soul_document_path": {"type": "string", "description": "Path to SOUL.md document"},
                        "memory_scope": {"type": "string", "enum": ["agent", "project", "team"], "description": "Memory scope"},
                    },
                },
            },
            "required": ["swarm_id", "agent_id", "profile"],
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
        "description": "Write shared swarm state with optimistic locking and optional TTL.",
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
                "ttl_seconds": {
                    "type": "integer",
                    "description": "Time to live in seconds (optional, state expires after this)",
                },
            },
            "required": ["swarm_id", "agent_id", "key", "value"],
        },
    },
    {
        "name": "rlm_state_poll",
        "description": "Poll for state changes across multiple keys. Returns only keys that changed since last_versions. Use for efficient multi-key monitoring without individual get calls.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of state keys to monitor",
                },
                "last_versions": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                    "description": "Map of key -> last known version. Only keys with newer versions are returned.",
                    "default": {},
                },
            },
            "required": ["swarm_id", "keys"],
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
        "name": "rlm_swarm_events",
        "description": "Query and filter broadcast events in a swarm.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string"},
                "event_type": {
                    "type": "string",
                    "description": "Filter by event type",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Filter by sending agent",
                },
                "since": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Only events after this timestamp (ISO 8601)",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Maximum events to return",
                },
            },
            "required": ["swarm_id"],
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
                "deadline": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Optional deadline (ISO 8601 format)",
                },
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs this depends on",
                },
                "metadata": {"type": "object"},
                "for_agent_id": {
                    "type": "string",
                    "description": "Pre-assign task to specific agent (task affinity). If set, only this agent can claim the task. Use agent's agentId string, not the DB id.",
                },
            },
            "required": ["swarm_id", "agent_id", "title"],
        },
    },
    {
        "name": "rlm_task_bulk_create",
        "description": "Create multiple tasks in a single call. Max 50 tasks per call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "tasks": {
                    "type": "array",
                    "description": "Array of task objects (max 50)",
                    "maxItems": 50,
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "priority": {
                                "type": "integer",
                                "default": 0,
                                "description": "Higher = more urgent",
                            },
                            "deadline": {
                                "type": "string",
                                "format": "date-time",
                                "description": "Optional deadline (ISO 8601 format)",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Task IDs this depends on",
                            },
                            "metadata": {"type": "object"},
                            "for_agent_id": {
                                "type": "string",
                                "description": "Pre-assign task to specific agent (task affinity)",
                            },
                        },
                        "required": ["title"],
                    },
                },
            },
            "required": ["swarm_id", "agent_id", "tasks"],
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
    {
        "name": "rlm_tasks",
        "description": "List tasks in a swarm's task queue. Filter by status or assigned agent.",
        "alias_of": "rlm_task_list",
        "exposed": False,
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "claimed", "completed", "failed"],
                    "description": "Filter by task status",
                },
                "assigned_to": {
                    "type": "string",
                    "description": "Filter by assigned agent ID (for task affinity)",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Maximum tasks to return",
                },
            },
            "required": ["swarm_id"],
        },
    },
    {
        "name": "rlm_task_list",
        "description": """List tasks with cursor-based pagination for efficient iteration.

Enhanced version of rlm_tasks with:
- Cursor-based pagination for large task queues
- Returns owner (agent who claimed/completed)
- Updated_at timestamp for ordering

Use for building dashboards and progress reports.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "claimed", "completed", "failed", "cancelled"],
                    "description": "Filter by task status",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Maximum tasks to return",
                },
                "cursor": {
                    "type": "string",
                    "description": "Cursor for pagination (from previous response)",
                },
            },
            "required": ["swarm_id"],
        },
    },
    {
        "name": "rlm_task_stats",
        "description": """Get aggregated task statistics for a swarm.

Returns counts by status:
- done: Completed tasks
- in_progress: Currently claimed tasks
- blocked: Pending tasks with unmet dependencies
- pending: Ready tasks waiting to be claimed
- failed: Failed tasks
- cancelled: Cancelled tasks
- total: Total task count

This is the source of truth for swarm progress tracking.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
            },
            "required": ["swarm_id"],
        },
    },
    {
        "name": "rlm_task_events",
        "description": """Get task status change events for a swarm.

Filters to task-related events:
- task_created, task_claimed, task_completed, task_failed, task_cancelled

Use with 'since' parameter to get incremental updates for
calculating "tasks closed since last check".""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "since": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Only return events after this timestamp (ISO 8601)",
                },
                "limit": {
                    "type": "integer",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 500,
                    "description": "Maximum events to return",
                },
            },
            "required": ["swarm_id"],
        },
    },
    {
        "name": "rlm_agent_status",
        "description": """Get swarm agent status with pending tasks and clear instructions.

Call this at session start to discover tasks assigned to you. Returns:
- Pending tasks assigned to your agent (use rlm_task_claim to start)
- Active swarms you've joined
- Current task you're working on (if any)
- Clear instructions on what to do next

This is THE discovery tool for swarm agents - tells you what work is waiting.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {
                    "type": "string",
                    "description": "Swarm ID to check status for",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Your agent identifier in the swarm",
                },
            },
            "required": ["swarm_id", "agent_id"],
        },
    },
    {
        "name": "rlm_swarm_leave",
        "description": """Remove an agent from a swarm.

Use this to:
- Clean up inactive/crashed agents
- Remove yourself from a swarm when done
- Free up agent slots for others

What happens on removal:
1. All resource claims held by the agent are released
2. Pending/claimed tasks assigned to the agent are unassigned
3. The agent record is deleted from the swarm

The agent can rejoin later with rlm_swarm_join.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {
                    "type": "string",
                    "description": "Swarm ID",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent ID to remove (can be yourself or another agent)",
                },
            },
            "required": ["swarm_id", "agent_id"],
        },
    },
    {
        "name": "rlm_swarm_members",
        "description": """List all agents in a swarm with their status.

Returns each agent's:
- agent_id: The agent's identifier
- role: coordinator, worker, or observer
- status: active, idle, busy
- capabilities: What the agent can do
- current_task: What they're working on (if any)
- joined_at: When they joined

Use this to:
- See who's in the swarm
- Find available agents for task assignment
- Monitor agent activity""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {
                    "type": "string",
                    "description": "Swarm ID",
                },
            },
            "required": ["swarm_id"],
        },
    },
    {
        "name": "rlm_swarm_update",
        "description": """Update swarm configuration (requires ADMIN access).

Updatable settings:
- name: Swarm display name
- description: What the swarm is for
- max_agents: Maximum agents allowed (plan-limited)
- task_timeout: Seconds before unclaimed task expires (60-3600)
- claim_timeout: Seconds a resource claim lasts (60-7200)""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {
                    "type": "string",
                    "description": "Swarm ID to update",
                },
                "name": {
                    "type": "string",
                    "description": "New swarm name",
                },
                "description": {
                    "type": "string",
                    "description": "New description",
                },
                "max_agents": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Maximum agents allowed",
                },
                "task_timeout": {
                    "type": "integer",
                    "minimum": 60,
                    "maximum": 3600,
                    "description": "Task claim timeout in seconds",
                },
                "claim_timeout": {
                    "type": "integer",
                    "minimum": 60,
                    "maximum": 7200,
                    "description": "Resource claim timeout in seconds",
                },
            },
            "required": ["swarm_id"],
        },
    },
    {
        "name": "rlm_task_reassign",
        "description": """Reassign a task to a different agent.

Use this to:
- Move work from a busy/stuck agent to an available one
- Rebalance workload across agents
- Recover tasks from crashed agents

PENDING and CLAIMED tasks can always be reassigned.
IN_PROGRESS tasks require force=true (admin override).
COMPLETED/FAILED tasks cannot be reassigned.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {
                    "type": "string",
                    "description": "Swarm ID",
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID to reassign",
                },
                "new_agent_id": {
                    "type": "string",
                    "description": "Agent ID to assign the task to (or null to unassign)",
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force reassign even if task is IN_PROGRESS (admin only)",
                },
            },
            "required": ["swarm_id", "task_id"],
        },
    },
    {
        "name": "rlm_task_delete",
        "description": """Delete a task from a swarm (admin only).

Use this to:
- Remove cancelled or obsolete tasks
- Clean up test tasks
- Remove erroneously created tasks

Only PENDING, FAILED, or CANCELLED tasks can be deleted.
COMPLETED and IN_PROGRESS tasks cannot be deleted (use force=true to override).""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {
                    "type": "string",
                    "description": "Swarm ID",
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID to delete",
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force delete even if task is COMPLETED or IN_PROGRESS (admin only)",
                },
            },
            "required": ["swarm_id", "task_id"],
        },
    },
    {
        "name": "rlm_task_update",
        "description": """Update task properties (admin only).

Modifiable fields:
- title: Task title
- description: Task description
- priority: Task priority (higher = more urgent)
- status: Task status (PENDING, IN_PROGRESS, COMPLETED, FAILED, CANCELLED)

Note: Changing status to COMPLETED/FAILED sets completedAt automatically.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {
                    "type": "string",
                    "description": "Swarm ID",
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID to update",
                },
                "title": {
                    "type": "string",
                    "description": "New task title",
                },
                "description": {
                    "type": "string",
                    "description": "New task description",
                },
                "priority": {
                    "type": "integer",
                    "description": "New priority (higher = more urgent)",
                },
                "status": {
                    "type": "string",
                    "enum": ["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED"],
                    "description": "New task status",
                },
            },
            "required": ["swarm_id", "task_id"],
        },
    },
    {
        "name": "rlm_task_unclaim",
        "description": """Unclaim a task, returning it to PENDING status.

Use this to recover tasks that are stuck (claimed but not progressing).
The task will be available for any agent to claim again.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {
                    "type": "string",
                    "description": "Swarm ID",
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID to unclaim",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for unclaiming (optional)",
                },
            },
            "required": ["swarm_id", "task_id"],
        },
    },
    {
        "name": "rlm_task_recover",
        "description": """Find and recover stuck tasks in a swarm.

A task is considered stuck if it's CLAIMED or IN_PROGRESS but hasn't been
updated within the threshold. Use dry_run=true to preview before recovering.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {
                    "type": "string",
                    "description": "Swarm ID",
                },
                "stuck_threshold_minutes": {
                    "type": "integer",
                    "default": 30,
                    "description": "Minutes after which a task is considered stuck",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, only report stuck tasks without recovering",
                },
            },
            "required": ["swarm_id"],
        },
    },
    # ============ Document Sync Tools ============
    {
        "name": "rlm_upload_document",
        "description": (
            "Upload or update a document in the project. Supports text documents "
            "(.md, .markdown, .mdx, .txt, .rst, .adoc) and binary parser documents "
            "(.pdf, .docx, .pptx, .svg, .vsdx). Binary payloads should use "
            "base64:<payload> except SVG, which may use raw XML."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Document path (e.g., 'docs/api.md')"},
                "content": {
                    "type": "string",
                    "description": "Document content, or base64:<payload> for binary files",
                },
                "kind": {
                    "type": "string",
                    "enum": ["DOC", "BINARY"],
                    "description": "Document pipeline kind. Inferred from path when omitted.",
                },
                "format": {
                    "type": "string",
                    "enum": [
                        "adoc",
                        "docx",
                        "markdown",
                        "md",
                        "mdx",
                        "pdf",
                        "pptx",
                        "rst",
                        "svg",
                        "txt",
                        "vsdx",
                    ],
                    "description": "Document format. Inferred from file extension when omitted.",
                },
                "language": {
                    "type": "string",
                    "description": "Optional language hint. Usually omitted for DOC and BINARY uploads.",
                },
                "metadata": {
                    "type": "object",
                    "description": (
                        "Optional structured metadata such as assetClass, usageMode "
                        "(current_truth|historical_reference|template|global_knowledge), "
                        "clientId, sourceKind, sourceModifiedAt, sourceSnapshotAt, "
                        "sourceContentHash, freshnessPolicy, parser, and provenance fields"
                    ),
                    "additionalProperties": True,
                },
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
                            "content": {
                                "type": "string",
                                "description": "Plain text or base64:<payload> for binary files",
                            },
                            "kind": {
                                "type": "string",
                                "enum": ["DOC", "BINARY"],
                                "description": "Document pipeline kind. Inferred from path when omitted.",
                            },
                            "format": {
                                "type": "string",
                                "enum": [
                                    "adoc",
                                    "docx",
                                    "markdown",
                                    "md",
                                    "mdx",
                                    "pdf",
                                    "pptx",
                                    "rst",
                                    "svg",
                                    "txt",
                                    "vsdx",
                                ],
                                "description": "Document format. Inferred from file extension when omitted.",
                            },
                            "language": {
                                "type": "string",
                                "description": "Optional language hint. Usually omitted for DOC and BINARY uploads.",
                            },
                            "metadata": {
                                "type": "object",
                                "description": (
                                    "Optional structured metadata for business context, diagrams, "
                                    "source freshness, historical references, templates, and provenance"
                                ),
                                "additionalProperties": True,
                            },
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
    {
        "name": "rlm_svg_bundle_ingest",
        "description": (
            "Generate a native SVG companion context bundle and optionally upload the generated "
            "Markdown documents. Use dry_run=true to preview bundle IDs, paths, and payload size."
            " Uploaded bundle documents store bundleId/sourceHash/sourcePath/artifactRole metadata."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "svg_content": {"type": "string", "description": "Raw SVG XML content"},
                "source_path": {
                    "type": "string",
                    "description": "Original SVG path used for stable bundle identity",
                },
                "upload_prefix": {
                    "type": "string",
                    "default": "svg-context",
                    "description": "Destination path prefix for generated companion documents",
                },
                "include_enriched_svg": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include an enriched SVG XML markdown companion",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "Return the bundle summary without writing documents",
                },
                "reindex": {
                    "type": "boolean",
                    "default": False,
                    "description": "Trigger a document reindex job after a non-dry-run upload",
                },
                "reindex_mode": {
                    "type": "string",
                    "enum": ["incremental", "full"],
                    "default": "incremental",
                    "description": "Document reindex mode to use when reindex=true",
                },
            },
            "required": ["svg_content", "source_path"],
        },
    },
    {
        "name": "rlm_request_access",
        "description": """Request access to a project.

Allows team members with NONE access level to request higher access levels
(VIEWER, EDITOR, ADMIN) from project admins. Creates an access request that
admins can approve or deny via the dashboard.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "requested_level": {
                    "type": "string",
                    "enum": ["VIEWER", "EDITOR", "ADMIN"],
                    "default": "VIEWER",
                    "description": "The access level to request",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason for requesting access",
                },
            },
            "required": [],
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
        "description": """Bridge between Snipara's context optimization and RLM-Runtime's code execution.

PURPOSE: Package project documentation into a Python-ready format that can be injected into an rlm-runtime REPL session for context-aware code execution.

WORKFLOW:
1. Call rlm_repl_context to get context_data + setup_code
2. Use set_repl_context(key='context', value=context_data) to inject data
3. Use execute_python(setup_code) to load helper functions
4. Use helpers (peek, grep, find_function, etc.) to explore context
5. Execute code with full documentation context available

USE CASES:
- Implement features with documentation awareness
- Debug code with access to related docs
- Write tests referencing specifications
- Refactor with architecture docs available

Returns context_data (files + sections), setup_code (helper functions), and usage hints.""",
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
                    "description": "Include Python helper functions: peek(), grep(), sections(), files(), get_file(), search(), trim(), find_function(), list_imports(), context_summary()",
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
    # ============ Decision Log Tools ============
    {
        "name": "rlm_decision_create",
        "description": """Create a structured decision record (ADR-style) for architectural or technical decisions.

Records decisions with context, rationale, alternatives considered, and revert plans.
Auto-generates DEC-XXX IDs. Supports tags for categorization.

Use for:
- Architectural decisions (database choice, framework selection)
- Technical trade-offs (performance vs maintainability)
- Process decisions (deployment strategy, testing approach)""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short title for the decision (e.g., 'Use Redis for caching')",
                },
                "owner": {
                    "type": "string",
                    "description": "Who made or is responsible for this decision",
                },
                "scope": {
                    "type": "string",
                    "description": "Scope/area affected (e.g., 'backend', 'authentication', 'database')",
                },
                "impact": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                    "default": "MEDIUM",
                    "description": "Impact level of this decision",
                },
                "context": {
                    "type": "string",
                    "description": "Background and context for why this decision was needed",
                },
                "decision": {
                    "type": "string",
                    "description": "The actual decision made (what was chosen)",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this option was chosen over alternatives",
                },
                "alternatives": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of alternatives that were considered",
                },
                "revert_plan": {
                    "type": "string",
                    "description": "How to revert this decision if needed (optional)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization (e.g., ['architecture', 'caching', 'performance'])",
                },
            },
            "required": ["title", "owner", "scope", "context", "decision", "rationale"],
        },
    },
    {
        "name": "rlm_decision_query",
        "description": """Query project decisions with filters.

Search by status, impact, scope, tags, or text query.
Returns decisions sorted by recency with supersession chain info.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text search in title, context, decision, rationale",
                },
                "status": {
                    "type": "string",
                    "enum": ["ACTIVE", "SUPERSEDED", "REVERTED", "DRAFT"],
                    "description": "Filter by decision status",
                },
                "impact": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                    "description": "Filter by impact level",
                },
                "scope": {
                    "type": "string",
                    "description": "Filter by scope/area",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by tags (OR logic)",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum decisions to return",
                },
                "include_superseded": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include superseded decisions in results",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_decision_supersede",
        "description": """Supersede an existing decision with a new one.

Creates a new decision that replaces an old one, maintaining the chain of evolution.
The old decision is marked as SUPERSEDED with a link to the new decision.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "old_decision_id": {
                    "type": "string",
                    "description": "The DEC-XXX ID of the decision being superseded",
                },
                "title": {
                    "type": "string",
                    "description": "Title for the new decision",
                },
                "owner": {
                    "type": "string",
                    "description": "Who made this new decision",
                },
                "scope": {
                    "type": "string",
                    "description": "Scope/area affected",
                },
                "impact": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                    "description": "Impact level",
                },
                "context": {
                    "type": "string",
                    "description": "Why the original decision is being changed",
                },
                "decision": {
                    "type": "string",
                    "description": "The new decision",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this change is being made",
                },
                "alternatives": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Alternatives considered for the new decision",
                },
                "revert_plan": {
                    "type": "string",
                    "description": "How to revert this decision if needed",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for the new decision",
                },
            },
            "required": ["old_decision_id", "title", "owner", "context", "decision", "rationale"],
        },
    },
    # ============ Index Health & Analytics Tools (Sprint 3) ============
    {
        "name": "rlm_index_health",
        "description": """Get comprehensive index health metrics for your project.

Returns coverage, quality scores, tier distribution, stale document detection, and overall health score.
Use this to monitor the health of your documentation index and identify issues.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stale_threshold_days": {
                    "type": "integer",
                    "default": 30,
                    "minimum": 1,
                    "maximum": 365,
                    "description": "Days after which content is considered stale",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_index_recommendations",
        "description": """Get actionable recommendations to improve your index health.

Returns prioritized list of recommendations based on current index health metrics.
Recommendations include actions like reindexing, improving coverage, and reviewing quality.""",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "rlm_reindex",
        "description": """Trigger a project reindex job or poll an existing reindex job.

Use this when index coverage is low, documents are missing chunks, or you need to rebuild
documentation/code indexes after large sync operations. Call without job_id to create a job,
or pass job_id to check progress via MCP.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Existing reindex job ID to poll instead of creating a new one",
                },
                "mode": {
                    "type": "string",
                    "enum": ["incremental", "full"],
                    "default": "incremental",
                    "description": "Reindex mode when creating a new job",
                },
                "kind": {
                    "type": "string",
                    "enum": ["doc", "code"],
                    "default": "doc",
                    "description": "Which index to rebuild when creating a new job",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_search_analytics",
        "description": """Get comprehensive search analytics for your project.

Returns query counts, success rates, latency percentiles, tool usage breakdown,
daily trends, and error analysis for the specified time period.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "default": 30,
                    "minimum": 1,
                    "maximum": 90,
                    "description": "Number of days to analyze",
                },
            },
            "required": [],
        },
    },
    {
        "name": "rlm_query_trends",
        "description": """Get query trends over time with configurable granularity.

Returns time-bucketed query counts, success rates, and latency for trend analysis.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "default": 7,
                    "minimum": 1,
                    "maximum": 30,
                    "description": "Number of days to analyze",
                },
                "granularity": {
                    "type": "string",
                    "enum": ["hour", "day"],
                    "default": "hour",
                    "description": "Time bucket granularity",
                },
            },
            "required": [],
        },
    },
    # ============ Hierarchical Task Tools ============
    {
        "name": "rlm_htask_create",
        "description": """Create a hierarchical task at any level (N0-N3).

Supports 4-level hierarchy: N0_INITIATIVE > N1_FEATURE > N2_WORKSTREAM > N3_TASK.
Tasks have owners, priorities, acceptance criteria, and evidence requirements.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "level": {
                    "type": "string",
                    "enum": ["N0_INITIATIVE", "N1_FEATURE", "N2_WORKSTREAM", "N3_TASK"],
                    "default": "N3_TASK",
                    "description": "Task hierarchy level",
                },
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Task description"},
                "owner": {"type": "string", "description": "Task owner (required)"},
                "parent_id": {"type": "string", "description": "Parent task ID (required for N1-N3)"},
                "priority": {
                    "type": "string",
                    "enum": ["P0", "P1", "P2"],
                    "default": "P1",
                    "description": "Priority level",
                },
                "eta_target": {"type": "string", "description": "Target completion date (ISO format)"},
                "execution_target": {
                    "type": "string",
                    "enum": ["LOCAL", "CLOUD", "HYBRID", "EXTERNAL"],
                    "description": "Where the task executes",
                },
                "workstream_type": {
                    "type": "string",
                    "enum": ["API", "FRONTEND", "QA", "BUGFIX_HARDENING", "DEPLOY_PROD_VERIFY", "DATA", "SECURITY", "DOCUMENTATION", "CUSTOM", "OTHER"],
                    "description": "Workstream type for N2 tasks",
                },
                "acceptance_criteria": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of acceptance criteria [{id, text, checked}]",
                },
                "context_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Context references (URLs, file paths)",
                },
                "context_query": {
                    "type": "string",
                    "description": "Auto-fetch relevant docs via rlm_context_query and add to context_refs (e.g., 'JWT authentication patterns')",
                },
                "evidence_required": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Required evidence [{type, description}]",
                },
                "is_blocking": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether task blocks parent closure when failed/incomplete",
                },
            },
            "required": ["swarm_id", "title", "description", "owner"],
        },
    },
    {
        "name": "rlm_htask_create_feature",
        "description": """Create a N1 feature with standard workstreams.

Creates a feature (N1) with automatic N2 workstreams: API, FRONTEND, QA, BUGFIX_HARDENING, DEPLOY_PROD_VERIFY.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "title": {"type": "string", "description": "Feature title"},
                "description": {"type": "string", "description": "Feature description"},
                "owner": {"type": "string", "description": "Feature owner"},
                "parent_id": {"type": "string", "description": "Optional N0 parent"},
                "workstreams": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Workstream types to create (defaults to standard set)",
                },
                "workstream_owners": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Map of workstream type to owner (e.g., {'API': 'dev1', 'FRONTEND': 'dev2'})",
                },
            },
            "required": ["swarm_id", "title", "description", "owner"],
        },
    },
    {
        "name": "rlm_htask_get",
        "description": "Get a hierarchical task with its children.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "task_id": {"type": "string", "description": "Task ID"},
                "include_children": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include direct children",
                },
            },
            "required": ["swarm_id", "task_id"],
        },
    },
    {
        "name": "rlm_htask_tree",
        "description": """Get full hierarchical tree from a node.

Returns recursive tree structure with all descendants up to max_depth.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "task_id": {"type": "string", "description": "Root task ID (optional, defaults to all roots)"},
                "max_depth": {
                    "type": "integer",
                    "default": 4,
                    "description": "Maximum depth to traverse",
                },
                "include_archived": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include archived tasks",
                },
            },
            "required": ["swarm_id"],
        },
    },
    {
        "name": "rlm_htask_update",
        "description": """Update task fields (whitelist enforced by status).

Different fields are updatable based on task status. Structural fields require admin.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "task_id": {"type": "string", "description": "Task ID"},
                "updates": {
                    "type": "object",
                    "description": "Fields to update",
                },
                "is_admin": {
                    "type": "boolean",
                    "default": False,
                    "description": "Admin privileges for structural updates",
                },
            },
            "required": ["swarm_id", "task_id", "updates"],
        },
    },
    {
        "name": "rlm_htask_block",
        "description": """Block a task with detailed payload.

Requires blocker_type and blocker_reason. Automatically propagates to ancestors if is_blocking=true.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "task_id": {"type": "string", "description": "Task ID"},
                "blocker_type": {
                    "type": "string",
                    "enum": ["TECH", "DEPENDENCY", "ACCESS", "PRODUCT", "INFRA", "SECURITY", "OTHER"],
                    "description": "Type of blocker",
                },
                "blocker_reason": {"type": "string", "description": "Detailed explanation"},
                "blocked_by_task_id": {"type": "string", "description": "ID of blocking task"},
                "required_input": {"type": "string", "description": "What's needed to unblock"},
                "eta_recovery": {"type": "string", "description": "Expected unblock date (ISO)"},
                "escalation_to": {"type": "string", "description": "Who to escalate to"},
            },
            "required": ["swarm_id", "task_id", "blocker_type", "blocker_reason"],
        },
    },
    {
        "name": "rlm_htask_unblock",
        "description": "Unblock a task and re-evaluate ancestor status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "task_id": {"type": "string", "description": "Task ID"},
                "resolution": {"type": "string", "description": "How the blocker was resolved"},
            },
            "required": ["swarm_id", "task_id"],
        },
    },
    {
        "name": "rlm_htask_complete",
        "description": """Complete an N3 task with evidence and optional memory creation.

Evidence may be required based on policy. Use for leaf tasks (N3_TASK).
Automatically creates a linked memory with task outcome, learnings, and decision impact.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "task_id": {"type": "string", "description": "Task ID"},
                "evidence": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Evidence list [{type, description, ...}]",
                },
                "result": {
                    "type": "object",
                    "description": "Task result data",
                },
                "learnings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lessons learned from this task",
                },
                "decision_impact": {
                    "type": "string",
                    "description": "How this task affects future decisions",
                },
                "create_memory": {
                    "type": "boolean",
                    "default": True,
                    "description": "Auto-create a memory with task outcome (default: true)",
                },
            },
            "required": ["swarm_id", "task_id"],
        },
    },
    {
        "name": "rlm_htask_verify_closure",
        "description": """Verify if a parent task can be closed.

Checks all children status against closure policy. Returns blockers and waiver requirements.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "task_id": {"type": "string", "description": "Task ID"},
            },
            "required": ["swarm_id", "task_id"],
        },
    },
    {
        "name": "rlm_htask_close",
        "description": """Close a parent task (with optional waiver).

Use waiver_reason and waiver_approved_by when closing with exceptions (if policy allows).""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "task_id": {"type": "string", "description": "Task ID"},
                "waiver_reason": {"type": "string", "description": "Reason for waiver"},
                "waiver_approved_by": {"type": "string", "description": "Who approved the waiver"},
            },
            "required": ["swarm_id", "task_id"],
        },
    },
    {
        "name": "rlm_htask_delete",
        "description": """Delete a task (soft by default, hard with force flag).

Soft delete archives the task. Hard delete removes permanently (requires policy + admin).""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "task_id": {"type": "string", "description": "Task ID"},
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Hard delete (requires policy + admin)",
                },
                "cascade": {
                    "type": "boolean",
                    "default": False,
                    "description": "Delete all descendants",
                },
                "is_admin": {
                    "type": "boolean",
                    "default": False,
                    "description": "Admin privileges",
                },
            },
            "required": ["swarm_id", "task_id"],
        },
    },
    {
        "name": "rlm_htask_recommend_batch",
        "description": """Get recommended batch of N3 tasks ready to work on.

Returns prioritized list of unblocked, pending N3 tasks. Filter by feature_id or workstream_type for focused recommendations.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "feature_id": {"type": "string", "description": "Filter to tasks under this N1 feature"},
                "workstream_type": {
                    "type": "string",
                    "enum": ["API", "FRONTEND", "QA", "BUGFIX_HARDENING", "DEPLOY_PROD_VERIFY", "DATA", "SECURITY", "DOCUMENTATION", "CUSTOM", "OTHER"],
                    "description": "Filter to tasks in this workstream type",
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "description": "Maximum tasks to return",
                },
                "owner": {"type": "string", "description": "Filter by owner"},
                "exclude_blocked": {
                    "type": "boolean",
                    "default": True,
                    "description": "Exclude blocked tasks",
                },
            },
            "required": ["swarm_id"],
        },
    },
    {
        "name": "rlm_htask_policy_get",
        "description": "Get the htask policy configuration for a swarm.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
            },
            "required": ["swarm_id"],
        },
    },
    {
        "name": "rlm_htask_policy_update",
        "description": """Update the htask policy for a swarm.

Admin-only fields: allowStructuralUpdate, allowHardDelete, compatMode.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "updates": {
                    "type": "object",
                    "description": "Policy fields to update",
                },
                "is_admin": {
                    "type": "boolean",
                    "default": False,
                    "description": "Admin privileges",
                },
            },
            "required": ["swarm_id", "updates"],
        },
    },
    {
        "name": "rlm_htask_metrics",
        "description": """Get comprehensive metrics for htasks in a swarm.

Includes throughput, aging by level, blocked/recovered ratio, and top blockers.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "period_hours": {
                    "type": "integer",
                    "default": 24,
                    "description": "Period for time-based metrics",
                },
            },
            "required": ["swarm_id"],
        },
    },
    {
        "name": "rlm_htask_audit_trail",
        "description": "Get complete audit trail for a specific task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "task_id": {"type": "string", "description": "Task ID"},
            },
            "required": ["swarm_id", "task_id"],
        },
    },
    {
        "name": "rlm_htask_checkpoint_delta",
        "description": """Get delta report since last checkpoint.

Returns events, closures, blocks since the specified timestamp.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "swarm_id": {"type": "string", "description": "Swarm ID"},
                "since": {"type": "string", "description": "ISO timestamp of last checkpoint"},
            },
            "required": ["swarm_id", "since"],
        },
    },
]

# TOOL_DEFINITIONS is the authoritative list that both the hosted MCP surface and
# the packaged snipara-mcp contract sync from, so it must stay de-duplicated.
TOOL_DEFINITION_BY_NAME: dict[str, dict] = {tool["name"]: tool for tool in TOOL_DEFINITIONS}

EXPOSED_TOOL_DEFINITIONS: list[dict] = [
    tool
    for tool in TOOL_DEFINITION_BY_NAME.values()
    if tool.get("exposed", True)
]

EXPOSED_TOOL_NAMES: set[str] = {tool["name"] for tool in EXPOSED_TOOL_DEFINITIONS}

MCP_TOOL_DEFINITIONS: list[dict] = EXPOSED_TOOL_DEFINITIONS
MCP_TOOL_NAMES: list[str] = [tool["name"] for tool in MCP_TOOL_DEFINITIONS]
MCP_TOOL_NAME_SET: set[str] = set(MCP_TOOL_NAMES)
