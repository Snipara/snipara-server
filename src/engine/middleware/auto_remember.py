"""Auto-remember middleware for automatic memory storage after tool calls.

When a project has `memory_save_on_commit` enabled, this middleware automatically
extracts and stores learnings/decisions from meaningful tool results.
"""

import logging
from typing import Any

from ...services.agent_memory import store_memory

logger = logging.getLogger(__name__)

# Tools that should trigger auto-remember
# Format: tool_name -> (memory_type, content_extractor_key)
AUTO_REMEMBER_TOOLS: dict[str, tuple[str, str]] = {
    "rlm_context_query": ("LEARNING", "query_result"),
    "rlm_decompose": ("DECISION", "decomposition"),
    "rlm_plan": ("DECISION", "plan"),
    "rlm_upload_document": ("DECISION", "upload"),
    "rlm_store_summary": ("LEARNING", "summary"),
    "rlm_task_complete": ("LEARNING", "task_completion"),
    "rlm_swarm_create": ("DECISION", "swarm"),
}

# Tools to NEVER auto-remember (avoid recursion, noise)
EXCLUDED_TOOLS: set[str] = {
    # Memory tools - avoid recursion
    "rlm_remember",
    "rlm_recall",
    "rlm_memories",
    "rlm_forget",
    # Meta/utility tools
    "rlm_stats",
    "rlm_settings",
    "rlm_context",
    "rlm_sections",
    "rlm_clear_context",
    "rlm_inject",
    # Read-only tools
    "rlm_search",
    "rlm_ask",
    "rlm_read",
    "rlm_get_chunk",
    "rlm_get_summaries",
    "rlm_list_templates",
    "rlm_get_template",
    "rlm_shared_context",
    "rlm_multi_query",
    "rlm_multi_project_query",
    "rlm_orchestrate",
    "rlm_repl_context",
    "rlm_load_document",
    "rlm_load_project",
}


def extract_memory_content(
    tool: str, params: dict[str, Any], result: dict[str, Any]
) -> tuple[str, str] | None:
    """Extract memory content from tool result.

    Args:
        tool: The tool name that was executed.
        params: The parameters passed to the tool.
        result: The result data from the tool.

    Returns:
        Tuple of (memory_type, content) or None if no memory should be stored.
    """
    if tool not in AUTO_REMEMBER_TOOLS:
        return None

    memory_type, extractor = AUTO_REMEMBER_TOOLS[tool]
    content: str = ""

    # Extract content based on tool type
    if extractor == "query_result":
        query = params.get("query", "")
        sections = result.get("sections", [])
        if sections:
            titles = [s.get("title", "")[:50] for s in sections[:2]]
            content = f"Queried: '{query}' → Found: {', '.join(titles)}"
        else:
            content = f"Queried: '{query}' (no results)"

    elif extractor == "decomposition":
        query = params.get("query", "")
        sub_queries = result.get("sub_queries", [])
        count = len(sub_queries) if sub_queries else 0
        truncated = query[:50] + "..." if len(query) > 50 else query
        content = f"Decomposed '{truncated}' into {count} sub-queries"

    elif extractor == "plan":
        query = params.get("query", "")
        steps = result.get("steps", [])
        count = len(steps) if steps else 0
        truncated = query[:50] + "..." if len(query) > 50 else query
        content = f"Created execution plan for '{truncated}' with {count} steps"

    elif extractor == "upload":
        path = params.get("path", "unknown")
        content = f"Uploaded document: {path}"

    elif extractor == "summary":
        doc_path = params.get("document_path", "unknown")
        content = f"Stored summary for: {doc_path}"

    elif extractor == "task_completion":
        task_id = params.get("task_id", "unknown")
        success = result.get("success", True)
        status = "completed" if success else "failed"
        content = f"Task {task_id} {status}"

    elif extractor == "swarm":
        name = params.get("name", "unnamed")
        content = f"Created swarm: {name}"

    else:
        return None

    # Length limits
    if len(content) < 20:
        return None
    if len(content) > 500:
        content = content[:497] + "..."

    return (memory_type, content)


async def maybe_auto_remember(
    tool: str,
    params: dict[str, Any],
    result: dict[str, Any],
    project_id: str,
    settings: Any,
) -> None:
    """Optionally store a memory based on tool result.

    Called after every tool execution. Checks settings and extracts memory
    if applicable. Failures are logged but don't affect the original tool call.

    Args:
        tool: The tool name that was executed.
        params: The parameters passed to the tool.
        result: The result data from the tool (ToolResult.data).
        project_id: The project ID for storing the memory.
        settings: ProjectSettings object with memory_save_on_commit and
            memory_inject_types fields.
    """
    # Check if feature is enabled
    if not getattr(settings, "memory_save_on_commit", False):
        return

    # Skip excluded tools
    if tool in EXCLUDED_TOOLS:
        return

    # Skip if result indicates failure
    if isinstance(result, dict) and result.get("error"):
        return

    try:
        # Extract memory content
        extracted = extract_memory_content(tool, params, result if result else {})
        if not extracted:
            return

        memory_type, content = extracted

        # Check if this type is in the allowed types
        allowed_types = getattr(settings, "memory_inject_types", ["DECISION", "LEARNING"])
        if memory_type not in allowed_types:
            return

        # Store the memory
        await store_memory(
            project_id=project_id,
            content=content,
            memory_type=memory_type.lower(),  # DB uses lowercase
            scope="project",
            category="auto-remember",
            ttl_days=30,  # Auto-memories expire after 30 days
            source="auto",
        )

        logger.debug(f"Auto-remembered {memory_type} from {tool}: {content[:50]}...")

    except Exception as e:
        # Never fail the original tool call due to auto-remember errors
        logger.warning(f"Auto-remember failed for {tool}: {e}")
