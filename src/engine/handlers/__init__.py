"""Tool handlers for the RLM engine.

This package contains extracted tool handlers organized by domain:
- memory: Agent memory persistence (remember, recall, memories, forget)
- swarm: Multi-agent coordination (swarm_create, swarm_join, claim, release, etc.)
- session: Session context management (inject, context, clear_context)
- summary: Summary storage (store_summary, get_summaries, delete_summary)
- document: Document management (upload_document, sync_documents, settings, request_access)

Each handler is a standalone async function that takes:
- params: dict[str, Any] - Tool parameters from MCP call
- ctx: HandlerContext - Shared engine context (project_id, plan, settings, etc.)

And returns:
- ToolResult with data, input_tokens, output_tokens
"""

from .base import HandlerContext, HandlerFunc, count_tokens
from .document import (
    handle_request_access,
    handle_settings,
    handle_sync_documents,
    handle_upload_document,
)
from .memory import (
    handle_forget,
    handle_memories,
    handle_recall,
    handle_remember,
)
from .session import (
    handle_clear_context,
    handle_context,
    handle_inject,
)
from .summary import (
    handle_delete_summary,
    handle_get_summaries,
    handle_store_summary,
)
from .swarm import (
    handle_broadcast,
    handle_claim,
    handle_release,
    handle_state_get,
    handle_state_set,
    handle_swarm_create,
    handle_swarm_join,
    handle_task_claim,
    handle_task_complete,
    handle_task_create,
)

__all__ = [
    # Base
    "HandlerContext",
    "HandlerFunc",
    "count_tokens",
    # Memory handlers
    "handle_remember",
    "handle_recall",
    "handle_memories",
    "handle_forget",
    # Swarm handlers
    "handle_swarm_create",
    "handle_swarm_join",
    "handle_claim",
    "handle_release",
    "handle_state_get",
    "handle_state_set",
    "handle_broadcast",
    "handle_task_create",
    "handle_task_claim",
    "handle_task_complete",
    # Session handlers
    "handle_inject",
    "handle_context",
    "handle_clear_context",
    # Summary handlers
    "handle_store_summary",
    "handle_get_summaries",
    "handle_delete_summary",
    # Document handlers
    "handle_upload_document",
    "handle_sync_documents",
    "handle_settings",
    "handle_request_access",
]
