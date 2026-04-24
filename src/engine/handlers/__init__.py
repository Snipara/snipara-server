"""Tool handlers for the RLM engine.

This package contains extracted tool handlers organized by domain:
- memory: Agent memory persistence (remember, recall, memories, forget)
- swarm: Multi-agent coordination (swarm_create, swarm_join, claim, release, etc.)
- session: Session context management (inject, context, clear_context)
- summary: Summary storage (store_summary, get_summaries, delete_summary)
- document: Document management (upload_document, sync_documents, settings, request_access)
- decisions: Decision log (decision_create, decision_query, decision_supersede)

Each handler is a standalone async function that takes:
- params: dict[str, Any] - Tool parameters from MCP call
- ctx: HandlerContext - Shared engine context (project_id, plan, settings, etc.)

And returns:
- ToolResult with data, input_tokens, output_tokens
"""

from .base import HandlerContext, HandlerFunc, count_tokens
from .decisions import (
    handle_decision_create,
    handle_decision_query,
    handle_decision_supersede,
)
from .document import (
    handle_request_access,
    handle_settings,
    handle_sync_documents,
    handle_upload_document,
)
from .htask import (
    handle_htask_audit_trail,
    handle_htask_block,
    handle_htask_checkpoint_delta,
    handle_htask_close,
    handle_htask_complete,
    handle_htask_create,
    handle_htask_create_feature,
    handle_htask_delete,
    handle_htask_get,
    handle_htask_metrics,
    handle_htask_policy_get,
    handle_htask_policy_update,
    handle_htask_recommend_batch,
    handle_htask_tree,
    handle_htask_unblock,
    handle_htask_update,
    handle_htask_verify_closure,
)
from .memory import (
    handle_forget,
    handle_journal_append,
    handle_journal_get,
    handle_journal_summarize,
    handle_memories,
    handle_memory_attach_source,
    handle_memory_compact,
    handle_memory_daily_brief,
    handle_memory_invalidate,
    handle_memory_supersede,
    handle_memory_verify,
    handle_recall,
    handle_remember,
    handle_remember_bulk,
    handle_session_memories,
    handle_tenant_profile_create,
    handle_tenant_profile_get,
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
    handle_agent_profile_get,
    handle_agent_profile_update,
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
    handle_task_events,
    handle_task_list,
    handle_task_recover,
    handle_task_stats,
    handle_task_unclaim,
    handle_tasks,
)

__all__ = [
    # Base
    "HandlerContext",
    "HandlerFunc",
    "count_tokens",
    # Memory handlers
    "handle_remember",
    "handle_remember_bulk",
    "handle_recall",
    "handle_memories",
    "handle_forget",
    "handle_memory_invalidate",
    "handle_memory_attach_source",
    "handle_memory_supersede",
    "handle_memory_verify",
    # Journal handlers
    "handle_journal_append",
    "handle_journal_get",
    "handle_journal_summarize",
    # Memory Tier & Compaction handlers (Phase 20)
    "handle_session_memories",
    "handle_memory_compact",
    "handle_memory_daily_brief",
    # Tenant Profile handlers (Phase 20)
    "handle_tenant_profile_create",
    "handle_tenant_profile_get",
    # Swarm handlers
    "handle_swarm_create",
    "handle_swarm_join",
    "handle_agent_profile_get",
    "handle_agent_profile_update",
    "handle_claim",
    "handle_release",
    "handle_state_get",
    "handle_state_set",
    "handle_broadcast",
    "handle_task_create",
    "handle_task_claim",
    "handle_task_complete",
    "handle_tasks",
    "handle_task_list",
    "handle_task_stats",
    "handle_task_events",
    "handle_task_unclaim",
    "handle_task_recover",
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
    # Decision handlers
    "handle_decision_create",
    "handle_decision_query",
    "handle_decision_supersede",
    # Hierarchical Task handlers
    "handle_htask_create",
    "handle_htask_create_feature",
    "handle_htask_get",
    "handle_htask_tree",
    "handle_htask_update",
    "handle_htask_block",
    "handle_htask_unblock",
    "handle_htask_complete",
    "handle_htask_verify_closure",
    "handle_htask_close",
    "handle_htask_delete",
    "handle_htask_recommend_batch",
    "handle_htask_policy_get",
    "handle_htask_policy_update",
    "handle_htask_metrics",
    "handle_htask_audit_trail",
    "handle_htask_checkpoint_delta",
]
