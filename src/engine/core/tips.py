"""First-query tool tips for user guidance.

This module generates plan-filtered tool tips that help users understand
all available tools without wasting tokens on every query.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...models import Plan

# Plans that have access to semantic search features
SEMANTIC_SEARCH_PLANS: set["Plan"] = set()

# Plans that have access to advanced planning features
PLAN_FEATURE_PLANS: set["Plan"] = set()


def _init_plan_sets() -> None:
    """Initialize plan sets after models are imported.

    This is called lazily to avoid circular imports.
    """
    global SEMANTIC_SEARCH_PLANS, PLAN_FEATURE_PLANS
    if not SEMANTIC_SEARCH_PLANS:
        from ...models import Plan
        SEMANTIC_SEARCH_PLANS = {Plan.PRO, Plan.TEAM, Plan.ENTERPRISE}
        PLAN_FEATURE_PLANS = {Plan.TEAM, Plan.ENTERPRISE}


def get_first_query_tips(plan: "Plan") -> str:
    """Generate plan-filtered tool tips for first query.

    Tips are injected only on the first query of a session to help users
    understand all available tools without wasting tokens on every query.

    Args:
        plan: User's current plan (FREE, PRO, TEAM, ENTERPRISE)

    Returns:
        Tool tips string with only tools available to this plan
    """
    _init_plan_sets()

    tips = ["## Snipara Tool Guide (First Query Tips)", ""]

    # Primary tools - available to all plans
    tips.append("**Primary Tools:**")
    tips.append("- `rlm_context_query` - Full documentation query with token budgeting")
    tips.append("- `rlm_ask` - Quick, simple query (~2500 tokens, no config needed)")
    tips.append("- `rlm_search` - Regex pattern search across documentation")
    tips.append("")

    # Pro+ tools - semantic search, decompose, multi-query
    if plan in SEMANTIC_SEARCH_PLANS:
        tips.append("**Power User Tools (Pro+):**")
        tips.append("- `rlm_multi_query` - Batch multiple queries in parallel")
        tips.append("- `rlm_decompose` - Break complex queries into sub-queries")
        tips.append("- `rlm_shared_context` - Get team coding standards/best practices")
        tips.append("- `rlm_load_document` - Load raw document content by file path")
        tips.append("")

    # Team+ tools - multi-project, plan, templates, orchestration
    if plan in PLAN_FEATURE_PLANS:
        tips.append("**Team Tools (Team+):**")
        tips.append("- `rlm_multi_project_query` - Search across ALL your projects")
        tips.append("- `rlm_plan` - Generate execution plan for complex questions")
        tips.append("- `rlm_list_templates` / `rlm_get_template` - Use prompt templates")
        tips.append("- `rlm_load_project` - Load full project structure with content")
        tips.append("- `rlm_orchestrate` - Multi-round context exploration (search + raw load)")
        tips.append("")

    # Utility tools - available to all
    tips.append("**Utility Tools:**")
    tips.append("- `rlm_inject` / `rlm_context` / `rlm_clear_context` - Session context")
    tips.append("- `rlm_stats` / `rlm_sections` - Browse documentation structure")
    tips.append("")

    tips.append("**Tip:** Use `rlm_ask` for quick answers, `rlm_context_query` for full control.")
    tips.append("")
    tips.append("---")

    return "\n".join(tips)
