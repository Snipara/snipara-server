"""Subject identity helpers for integrator client API keys."""

import hashlib
from typing import Any


MEMORY_TOOL_NAMES = {
    "rlm_remember",
    "rlm_remember_if_novel",
    "rlm_end_of_task_commit",
    "rlm_remember_bulk",
    "rlm_recall",
    "rlm_memories",
    "rlm_session_memories",
}


def build_integrator_subject_user_id(client_id: str, external_user_id: str) -> str:
    """Create a stable, non-reversible user owner ID for an integrator end user."""
    value = external_user_id.strip()
    if not value:
        raise ValueError("external_user_id cannot be empty")
    if len(value) > 256:
        raise ValueError("external_user_id must be 256 characters or less")

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"integrator:{client_id}:user:{digest}"


def get_external_user_id(arguments: dict[str, Any] | None) -> str | None:
    """Read the integrator end-user identifier from tool arguments."""
    if not arguments:
        return None
    value = arguments.get("external_user_id")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("external_user_id must be a string")
    return value


def memory_call_uses_user_scope(tool_name: str, arguments: dict[str, Any] | None) -> bool:
    """Return True when a memory call explicitly targets scope=user."""
    if tool_name not in MEMORY_TOOL_NAMES or not arguments:
        return False
    if arguments.get("scope") == "user":
        return True
    if tool_name == "rlm_remember_bulk":
        memories = arguments.get("memories")
        if isinstance(memories, list):
            return any(
                isinstance(memory, dict) and memory.get("scope") == "user" for memory in memories
            )
    return False


def resolve_integrator_memory_user_id(
    *,
    auth_info: dict[str, Any] | None,
    default_user_id: str | None,
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> str | None:
    """
    Resolve the effective user owner for memory tools.

    Integrator client keys (`snipara_ic_*`) represent a client project, not the
    integrator owner's personal memory namespace. For memory tools we only
    expose user-scoped memories when the integrator forwards a stable
    `external_user_id` for the end user.
    """
    if auth_info is None or auth_info.get("auth_type") != "integrator_client":
        return default_user_id
    if tool_name not in MEMORY_TOOL_NAMES:
        return default_user_id

    external_user_id = get_external_user_id(arguments)
    if not external_user_id:
        return None

    client_id = auth_info.get("client_id")
    if not client_id:
        raise ValueError("Integrator client auth is missing client_id")
    return build_integrator_subject_user_id(client_id, external_user_id)
