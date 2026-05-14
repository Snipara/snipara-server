"""First-query tool tips for user guidance.

This module generates plan-filtered tool tips that help users understand
all available tools without wasting tokens on every query.

Tool Tiers:
    - PRIMARY (🟢): Essential tools for all users - start here
    - POWER_USER (🔵): Advanced features for intermediate users
    - TEAM (🟡): Team collaboration and multi-project features
    - UTILITY (⚪): Session and project management utilities
    - ADVANCED (🔴): Multi-agent swarms and expert orchestration
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
    Tools are organized by tier with emoji badges.

    Args:
        plan: User's current plan (FREE, PRO, TEAM, ENTERPRISE)

    Returns:
        Tool tips string with only tools available to this plan
    """
    _init_plan_sets()

    tips = ["## Snipara Tool Guide", ""]

    # Tier legend
    tips.append("**Tiers:** 🟢 Primary | 🔵 Power User | 🟡 Team | ⚪ Utility | 🔴 Advanced")
    tips.append("")

    # PRIMARY (🟢) - available to all plans
    tips.append("**🟢 Primary Tools (Start Here):**")
    tips.append("- `rlm_context_query` - Full documentation query with token budgeting")
    tips.append("- `rlm_ask` - Quick, simple query (~2500 tokens)")
    tips.append("- `rlm_search` - Regex pattern search")
    tips.append("- `rlm_recall` - Retrieve saved memories")
    tips.append(
        '- Fast retry after timeout: `rlm_context_query(max_tokens=1200, search_mode="keyword", return_references=true, auto_decompose=false)`'
    )
    tips.append("")

    # POWER_USER (🔵) - Pro+ tools
    if plan in SEMANTIC_SEARCH_PLANS:
        tips.append("**🔵 Power User Tools (Pro+):**")
        tips.append("- `rlm_multi_query` - Batch multiple queries")
        tips.append("- `rlm_decompose` - Break complex queries into sub-queries")
        tips.append("- `rlm_code_callers` / `rlm_code_neighbors` - Fast structural code context")
        tips.append("- `rlm_remember` / `rlm_remember_bulk` - Store memories")
        tips.append("- `rlm_load_document` - Load raw document content")
        tips.append("")

    # TEAM (🟡) - Team+ tools
    if plan in PLAN_FEATURE_PLANS:
        tips.append("**🟡 Team Tools (Team+):**")
        tips.append("- `rlm_multi_project_query` - Search across ALL projects")
        tips.append("- `rlm_plan` - Generate execution plan")
        tips.append("- `rlm_shared_context` - Team coding standards")
        tips.append("- `rlm_list_templates` / `rlm_get_template` - Prompt templates")
        tips.append("")

    # UTILITY (⚪) - available to all
    tips.append("**⚪ Utility Tools:**")
    tips.append("- `rlm_inject` / `rlm_context` / `rlm_clear_context` - Session context")
    tips.append("- `rlm_stats` / `rlm_sections` - Documentation structure")
    tips.append("")

    # ADVANCED (🔴) - Team+ for swarms
    if plan in PLAN_FEATURE_PLANS:
        tips.append("**🔴 Advanced Tools (Expert):**")
        tips.append("- `rlm_orchestrate` - Multi-round context exploration")
        tips.append("- `rlm_swarm_*` - Multi-agent coordination")
        tips.append("")

    tips.append("**Tip:** Start with `rlm_ask` for quick answers, `rlm_context_query` for control.")
    tips.append(
        "**Recovery:** If `rlm_context_query` times out, retry with the fast parameters above before local file search."
    )
    tips.append("**Help:** Use `rlm_help` to find the right tool for your task.")
    tips.append("")
    tips.append("---")

    return "\n".join(tips)
