"""Session tool handlers for context management.

Handles:
- rlm_inject: Inject context into session
- rlm_context: Get current session context
- rlm_clear_context: Clear session context
"""

from typing import Any

from ...models import ToolResult
from .base import HandlerContext, count_tokens


async def handle_inject(
    params: dict[str, Any],
    ctx: HandlerContext,
    set_context_callback: Any,  # Callable to update engine's session_context
) -> ToolResult:
    """Inject context into the session.

    Args:
        params: Dict containing:
            - context: Context string to inject
            - append: Whether to append or replace existing context

    Returns:
        ToolResult with confirmation
    """
    context = params.get("context", "")
    append = params.get("append", False)

    if not context:
        return ToolResult(
            data={"error": "rlm_inject: missing required parameter 'context'"},
            input_tokens=0,
            output_tokens=0,
        )

    if append and ctx.session_context:
        new_context = f"{ctx.session_context}\n\n{context}"
    else:
        new_context = context

    # Update context via callback
    set_context_callback(new_context)

    return ToolResult(
        data={
            "success": True,
            "context_length": len(new_context),
            "token_count": count_tokens(new_context),
        },
        input_tokens=count_tokens(context),
        output_tokens=0,
    )


async def handle_context(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get current session context.

    Returns:
        ToolResult with current context and token count
    """
    return ToolResult(
        data={
            "context": ctx.session_context,
            "token_count": count_tokens(ctx.session_context),
        },
        input_tokens=0,
        output_tokens=count_tokens(ctx.session_context),
    )


async def handle_clear_context(
    params: dict[str, Any],
    ctx: HandlerContext,
    set_context_callback: Any,  # Callable to update engine's session_context
) -> ToolResult:
    """Clear session context.

    Returns:
        ToolResult with confirmation
    """
    # Clear context via callback
    set_context_callback("")

    return ToolResult(
        data={"success": True, "message": "Session context cleared"},
        input_tokens=0,
        output_tokens=0,
    )
