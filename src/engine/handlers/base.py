"""Base infrastructure for tool handlers.

This module provides the common types and utilities used by all handler modules.
Each handler receives a HandlerContext with shared state and returns a ToolResult.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from ...models import Plan, ProjectSettings, ToolResult


@dataclass
class HandlerContext:
    """Context object passed to all handlers.

    Contains shared state and dependencies that handlers need to operate.
    This decouples handlers from the RLMEngine class.
    """

    # Core identifiers
    project_id: str
    user_id: str | None
    team_id: str | None

    # Plan and access
    plan: "Plan"
    access_level: str  # VIEWER, EDITOR, ADMIN

    # Project settings from dashboard
    settings: "ProjectSettings"

    # Session state
    session_context: str
    tips_shown: bool

    # Document index (may be None if not loaded)
    index: Any  # DocumentIndex | None

    # Database client (for handlers that need DB access)
    db: Any  # PrismaClient


# Type alias for handler functions
HandlerFunc = Callable[
    [dict[str, Any], HandlerContext],
    Coroutine[Any, Any, "ToolResult"],
]


def count_tokens(text: str) -> int:
    """Estimate token count for a string.

    Uses a simple heuristic of ~4 characters per token.
    This is a reasonable approximation for English text.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)
