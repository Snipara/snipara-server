"""Hierarchical Task Policy Service.

Manages configurable policies per swarm for hierarchical tasks:
- Closure rules (strict vs. allow exceptions)
- Evidence requirements
- Blocking defaults
- Structural update permissions
- Compatibility mode
"""

import logging
from typing import Any

from ..db import get_db

logger = logging.getLogger(__name__)


# =============================================================================
# POLICY RETRIEVAL & UPDATE
# =============================================================================


async def get_policy(swarm_id: str) -> dict[str, Any]:
    """Get or create the policy for a swarm.

    Args:
        swarm_id: The swarm ID

    Returns:
        Policy dict with all configuration values
    """
    db = await get_db()

    policy = await db.htaskpolicy.find_unique(where={"swarmId": swarm_id})

    if not policy:
        # Create default policy
        policy = await db.htaskpolicy.create(
            data={"swarmId": swarm_id}
        )
        logger.info(f"Created default policy for swarm {swarm_id}")

    return {
        "id": policy.id,
        "swarm_id": policy.swarmId,
        "max_depth": policy.maxDepth,
        "closure_policy": policy.closurePolicy,
        "require_evidence_on_complete": policy.requireEvidenceOnComplete,
        "allow_parent_close_with_waiver": policy.allowParentCloseWithWaiver,
        "failed_is_blocking_default": policy.failedIsBlockingDefault,
        "allow_structural_update": policy.allowStructuralUpdate,
        "allow_hard_delete": policy.allowHardDelete,
        "compat_mode": policy.compatMode,
        "created_at": policy.createdAt.isoformat() if policy.createdAt else None,
        "updated_at": policy.updatedAt.isoformat() if policy.updatedAt else None,
    }


async def get_policy_raw(swarm_id: str):
    """Get raw policy object (for internal use).

    Args:
        swarm_id: The swarm ID

    Returns:
        Raw Prisma policy object or None
    """
    db = await get_db()
    return await db.htaskpolicy.find_unique(where={"swarmId": swarm_id})


async def update_policy(
    swarm_id: str,
    updates: dict[str, Any],
    is_admin: bool = False,
) -> dict[str, Any]:
    """Update policy for a swarm.

    Args:
        swarm_id: The swarm ID
        updates: Dict of fields to update
        is_admin: Whether the caller has admin privileges

    Returns:
        Updated policy dict or error
    """
    # Validate fields
    allowed_fields = {
        "maxDepth",
        "closurePolicy",
        "requireEvidenceOnComplete",
        "allowParentCloseWithWaiver",
        "failedIsBlockingDefault",
    }

    # Admin-only fields
    admin_fields = {
        "allowStructuralUpdate",
        "allowHardDelete",
        "compatMode",
    }

    # Convert snake_case to camelCase for Prisma
    field_map = {
        "max_depth": "maxDepth",
        "closure_policy": "closurePolicy",
        "require_evidence_on_complete": "requireEvidenceOnComplete",
        "allow_parent_close_with_waiver": "allowParentCloseWithWaiver",
        "failed_is_blocking_default": "failedIsBlockingDefault",
        "allow_structural_update": "allowStructuralUpdate",
        "allow_hard_delete": "allowHardDelete",
        "compat_mode": "compatMode",
    }

    # Process updates
    prisma_updates = {}
    for key, value in updates.items():
        prisma_key = field_map.get(key, key)

        if prisma_key in admin_fields and not is_admin:
            return {
                "success": False,
                "error": f"Field '{key}' requires admin privileges",
            }

        if prisma_key not in allowed_fields and prisma_key not in admin_fields:
            return {
                "success": False,
                "error": f"Unknown field '{key}'",
            }

        prisma_updates[prisma_key] = value

    if not prisma_updates:
        return {"success": False, "error": "No valid fields to update"}

    db = await get_db()

    await db.htaskpolicy.upsert(
        where={"swarmId": swarm_id},
        create={"swarmId": swarm_id, **prisma_updates},
        update=prisma_updates,
    )

    logger.info(f"Updated policy for swarm {swarm_id}: {list(prisma_updates.keys())}")

    return {
        "success": True,
        "policy": await get_policy(swarm_id),
    }


# =============================================================================
# POLICY HELPERS
# =============================================================================


def can_close_with_exceptions(policy: dict[str, Any]) -> bool:
    """Check if parent can close with exceptions (waiver required).

    Args:
        policy: Policy dict

    Returns:
        True if waiver-based closure is allowed
    """
    return (
        policy.get("closure_policy") == "ALLOW_EXCEPTIONS"
        and policy.get("allow_parent_close_with_waiver", False)
    )


def is_blocking_default(policy: dict[str, Any]) -> bool:
    """Check if failed tasks should block by default.

    Args:
        policy: Policy dict

    Returns:
        True if failed tasks should be blocking by default
    """
    return policy.get("failed_is_blocking_default", True)


def get_max_depth(policy: dict[str, Any]) -> int:
    """Get maximum hierarchy depth from policy.

    Args:
        policy: Policy dict

    Returns:
        Maximum depth (default 4)
    """
    return policy.get("max_depth", 4)


def requires_evidence_on_complete(policy: dict[str, Any]) -> bool:
    """Check if evidence is required for task completion.

    Args:
        policy: Policy dict

    Returns:
        True if evidence is required
    """
    return policy.get("require_evidence_on_complete", True)


def allows_structural_update(policy: dict[str, Any]) -> bool:
    """Check if structural updates (level, parentId) are allowed.

    Args:
        policy: Policy dict

    Returns:
        True if structural updates are allowed
    """
    return policy.get("allow_structural_update", False)


def allows_hard_delete(policy: dict[str, Any]) -> bool:
    """Check if hard delete is allowed.

    Args:
        policy: Policy dict

    Returns:
        True if hard delete is allowed
    """
    return policy.get("allow_hard_delete", False)


def get_compat_mode(policy: dict[str, Any]) -> str:
    """Get compatibility mode for rlm_task_* migration.

    Args:
        policy: Policy dict

    Returns:
        Compat mode: LEGACY, DUAL, SHADOW, or HTASK
    """
    return policy.get("compat_mode", "LEGACY")
