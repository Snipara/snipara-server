"""Integrator Admin API endpoints.

This module provides REST API endpoints for integrators to manage their
workspace, clients, and API keys. All endpoints require authentication
with an integrator workspace API key (int_*). Regular project API keys
(rlm_*) and team API keys are NOT accepted here.

Base URL: /v1/integrator
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from ..db import get_db
from ..services.integrator_webhooks import (
    emit_api_key_created,
    emit_api_key_revoked,
    emit_client_created,
    emit_client_deleted,
    emit_client_updated,
)
from ..services.integrator_plans import (
    get_client_bundle_discount_percent,
    get_client_bundle_discount_range_percent,
    get_client_bundle_limits,
    get_client_bundle_pricing,
    get_integrator_client_limit,
    summarize_client_bundle_billing,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/integrator", tags=["Integrator"])


# ============ PYDANTIC MODELS ============


class CreateWorkspaceRequest(BaseModel):
    """Request body for creating a workspace."""

    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")


class UpdateWorkspaceRequest(BaseModel):
    """Request body for updating a workspace."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    webhook_url: str | None = None
    webhook_secret: str | None = None


class CreateClientRequest(BaseModel):
    """Request body for creating a client."""

    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    external_id: str | None = Field(default=None, max_length=100)
    bundle: str = Field(default="LITE", pattern=r"^(LITE|STANDARD|UNLIMITED)$")


class UpdateClientRequest(BaseModel):
    """Request body for updating a client."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    bundle: str | None = Field(default=None, pattern=r"^(LITE|STANDARD|UNLIMITED)$")
    is_active: bool | None = None


class CreateApiKeyRequest(BaseModel):
    """Request body for creating an API key."""

    name: str = Field(..., min_length=1, max_length=100)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


# ============ HELPER FUNCTIONS ============


def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_client_api_key() -> str:
    """Generate a new client API key with snipara_ic_ prefix."""
    random_part = secrets.token_hex(32)
    return f"snipara_ic_{random_part}"


async def get_integrator_from_api_key(api_key: str) -> dict:
    """
    Validate an integrator workspace API key (int_*) and return integrator info.

    Only keys stored in `IntegratorWorkspaceApiKey` are accepted. Regular
    project keys (rlm_*) and team API keys cannot be used to reach the
    integrator admin API, even if their owner happens to have an Integrator
    subscription.

    Args:
        api_key: The API key from the request header

    Returns:
        Dict with integrator info including workspace

    Raises:
        HTTPException if API key is invalid, not an integrator workspace key,
        or the integrator has no workspace.
    """
    # Defense-in-depth: reject anything that isn't an integrator workspace key
    # before touching the database.
    if not api_key.startswith("int_"):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key. The integrator API requires an int_* workspace key.",
        )

    db = await get_db()

    key_hash = hash_api_key(api_key)

    api_key_record = await db.integratorworkspaceapikey.find_first(
        where={"keyHash": key_hash},
        include={
            "workspace": {
                "include": {
                    "integrator": {
                        "include": {
                            "user": True,
                        }
                    }
                }
            }
        },
    )

    if not api_key_record:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Check if key is revoked
    if api_key_record.revokedAt:
        raise HTTPException(status_code=401, detail="API key has been revoked")

    # Check if key is expired
    if api_key_record.expiresAt and api_key_record.expiresAt < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="API key has expired")

    workspace = api_key_record.workspace
    if not workspace:
        raise HTTPException(status_code=401, detail="Invalid API key")

    integrator = workspace.integrator
    if not integrator:
        raise HTTPException(
            status_code=403,
            detail="INTEGRATOR_NOT_FOUND: You must have an Integrator subscription to use this API. Visit https://snipara.com/integrator to sign up.",
        )

    user = integrator.user
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Track last usage for auditing / dashboards
    try:
        await db.integratorworkspaceapikey.update(
            where={"id": api_key_record.id},
            data={"lastUsedAt": datetime.now(UTC)},
        )
    except Exception:
        # lastUsedAt update is best-effort; never block auth on it
        logger.debug("Failed to update lastUsedAt for integrator workspace API key")

    return {
        "user_id": user.id,
        "integrator_id": integrator.id,
        "integrator": integrator,
        "workspace": workspace,
        "tier": integrator.tier,
        "client_limit": get_integrator_client_limit(integrator.tier),
    }


async def get_api_key_header(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """Extract and validate API key from header."""
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header. Authenticate with your Snipara API key.",
        )
    return x_api_key


# ============ WORKSPACE ENDPOINTS ============


@router.post("/workspace")
async def create_workspace(
    request: CreateWorkspaceRequest,
):
    """
    DEPRECATED / DISABLED.

    Workspace creation is only allowed from the authenticated web dashboard
    (https://snipara.com/integrator) where the user is identified by a
    session, not by an API key. The API key flow is unsafe here because the
    only valid integrator key (`int_*`) is itself workspace-scoped — it can
    only exist after a workspace is created.

    Previously this endpoint accepted any `ApiKey` / `TeamApiKey` belonging
    to a user who had an Integrator record, which let non-integrator users
    create workspaces on the integrator side.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "WORKSPACE_CREATION_DISABLED: Workspaces can only be created from "
            "the Snipara dashboard at https://snipara.com/integrator. This API "
            "endpoint has been removed to prevent non-integrator accounts from "
            "provisioning workspaces."
        ),
    )


@router.get("/workspace")
async def get_workspace(
    api_key: str = Depends(get_api_key_header),
):
    """
    Get the integrator's workspace details.

    Returns:
        Workspace details including client count
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(
            status_code=404,
            detail="WORKSPACE_NOT_FOUND: You don't have a workspace yet. Create one from https://snipara.com/integrator.",
        )

    db = await get_db()

    clients = await db.integratorclient.find_many(where={"workspaceId": workspace.id})
    tier = integrator_info["tier"]

    return {
        "success": True,
        "data": {
            "workspace_id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "webhook_url": workspace.webhookUrl,
            "has_webhook_secret": bool(workspace.webhookSecret),
            "client_count": len(clients),
            "client_limit": integrator_info["client_limit"],
            "tier": tier,
            "pricing": {
                "client_bundle_discount_percent": get_client_bundle_discount_percent(tier),
                "client_bundle_discount_range_percent": get_client_bundle_discount_range_percent(
                    tier
                ),
                "discount_applies_to": "client_bundles",
                "billing_summary": summarize_client_bundle_billing(tier, clients),
            },
            "created_at": workspace.createdAt.isoformat(),
            "updated_at": workspace.updatedAt.isoformat(),
        },
    }


@router.patch("/workspace")
async def update_workspace(
    request: UpdateWorkspaceRequest,
    api_key: str = Depends(get_api_key_header),
):
    """
    Update workspace settings.

    Args:
        request: Fields to update
        api_key: Integrator's API key

    Returns:
        Updated workspace details
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(
            status_code=404,
            detail="WORKSPACE_NOT_FOUND: You don't have a workspace yet.",
        )

    db = await get_db()

    update_data = {}
    if request.name is not None:
        update_data["name"] = request.name
    if request.webhook_url is not None:
        update_data["webhookUrl"] = request.webhook_url
    if request.webhook_secret is not None:
        update_data["webhookSecret"] = request.webhook_secret

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    workspace = await db.integratorworkspace.update(
        where={"id": workspace.id},
        data=update_data,
    )

    logger.info(f"Updated workspace {workspace.id}")

    return {
        "success": True,
        "data": {
            "workspace_id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "webhook_url": workspace.webhookUrl,
            "has_webhook_secret": bool(workspace.webhookSecret),
            "updated_at": workspace.updatedAt.isoformat(),
        },
    }


# ============ CLIENT ENDPOINTS ============


@router.post("/clients")
async def create_client(
    request: CreateClientRequest,
    api_key: str = Depends(get_api_key_header),
):
    """
    Create a new client with an auto-generated project.

    This endpoint:
    1. Creates a new Client record
    2. Creates a dedicated Project for the client
    3. Links the client to the project

    Args:
        request: Client creation parameters
        api_key: Integrator's API key

    Returns:
        Created client details with project info
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(
            status_code=404,
            detail="WORKSPACE_NOT_FOUND: Create a workspace first with POST /v1/integrator/workspace.",
        )

    db = await get_db()

    # Check client limit
    client_count = await db.integratorclient.count(where={"workspaceId": workspace.id})
    client_limit = integrator_info["client_limit"]
    if client_limit != -1 and client_count >= client_limit:
        raise HTTPException(
            status_code=400,
            detail=f"CLIENT_LIMIT_REACHED: You have reached your tier limit of {client_limit} clients. Upgrade your tier to add more.",
        )

    # Check for duplicate email
    existing = await db.integratorclient.find_first(
        where={"workspaceId": workspace.id, "email": request.email}
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"A client with email '{request.email}' already exists in your workspace.",
        )

    # Check for duplicate external_id if provided
    if request.external_id:
        existing = await db.integratorclient.find_first(
            where={"workspaceId": workspace.id, "externalId": request.external_id}
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"A client with external_id '{request.external_id}' already exists.",
            )

    # Generate project slug from client name
    import re

    base_slug = re.sub(r"[^a-z0-9]+", "-", request.name.lower()).strip("-")
    project_slug = f"{workspace.slug}-{base_slug}"

    # Ensure slug is unique
    existing_project = await db.project.find_first(where={"slug": project_slug})
    if existing_project:
        project_slug = f"{project_slug}-{secrets.token_hex(4)}"

    # Get the integrator's team (for project ownership)
    integrator = await db.integrator.find_first(
        where={"id": integrator_info["integrator_id"]},
        include={"user": {"include": {"teamMembers": True}}},
    )

    # Use the first team the user owns, or create error
    user_teams = integrator.user.teamMembers if integrator and integrator.user else []
    team_membership = next((tm for tm in user_teams if tm.role in ("OWNER", "ADMIN")), None)
    if not team_membership:
        raise HTTPException(
            status_code=400,
            detail="You must be an owner or admin of a team to create clients. Create a team first.",
        )

    # Create project for the client
    project = await db.project.create(
        data={
            "name": f"{request.name} (via {workspace.name})",
            "slug": project_slug,
            "teamId": team_membership.teamId,
        }
    )

    # Create the client
    client = await db.integratorclient.create(
        data={
            "workspaceId": workspace.id,
            "name": request.name,
            "email": request.email,
            "externalId": request.external_id,
            "bundle": request.bundle,
            "projectId": project.id,
        }
    )

    logger.info(
        f"Created client {client.id} with project {project.id} for workspace {workspace.id}"
    )

    limits = get_client_bundle_limits(request.bundle)

    # Emit webhook event
    await emit_client_created(
        workspace.id,
        {
            "client_id": client.id,
            "project_id": project.id,
            "project_slug": project.slug,
            "name": client.name,
            "email": client.email,
            "external_id": client.externalId,
            "bundle": client.bundle,
        },
    )

    return {
        "success": True,
        "data": {
            "client_id": client.id,
            "project_id": project.id,
            "project_slug": project.slug,
            "name": client.name,
            "email": client.email,
            "external_id": client.externalId,
            "bundle": client.bundle,
            "is_active": client.isActive,
            "limits": limits,
            "pricing": get_client_bundle_pricing(client.bundle, integrator_info["tier"]),
            "created_at": client.createdAt.isoformat(),
        },
    }


@router.get("/clients")
async def list_clients(
    api_key: str = Depends(get_api_key_header),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    is_active: bool | None = Query(default=None),
    bundle: str | None = Query(default=None, pattern=r"^(LITE|STANDARD|UNLIMITED)$"),
):
    """
    List all clients in the workspace.

    Args:
        api_key: Integrator's API key
        limit: Maximum clients to return
        offset: Pagination offset
        is_active: Filter by active status
        bundle: Filter by bundle type

    Returns:
        List of clients with pagination
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(
            status_code=404,
            detail="WORKSPACE_NOT_FOUND: Create a workspace first.",
        )

    db = await get_db()

    where_clause: dict = {"workspaceId": workspace.id}
    if is_active is not None:
        where_clause["isActive"] = is_active
    if bundle:
        where_clause["bundle"] = bundle

    clients = await db.integratorclient.find_many(
        where=where_clause,
        include={"project": True},
        take=limit,
        skip=offset,
        order={"createdAt": "desc"},
    )

    total = await db.integratorclient.count(where=where_clause)
    billing_clients = await db.integratorclient.find_many(where={"workspaceId": workspace.id})
    tier = integrator_info["tier"]

    return {
        "success": True,
        "data": {
            "clients": [
                {
                    "client_id": c.id,
                    "project_id": c.projectId,
                    "project_slug": c.project.slug if c.project else None,
                    "name": c.name,
                    "email": c.email,
                    "external_id": c.externalId,
                    "bundle": c.bundle,
                    "is_active": c.isActive,
                    "limits": get_client_bundle_limits(c.bundle),
                    "pricing": get_client_bundle_pricing(c.bundle, tier),
                    "created_at": c.createdAt.isoformat(),
                }
                for c in clients
            ],
            "pricing": {
                "client_bundle_discount_percent": get_client_bundle_discount_percent(tier),
                "client_bundle_discount_range_percent": get_client_bundle_discount_range_percent(
                    tier
                ),
                "discount_applies_to": "client_bundles",
                "billing_summary": summarize_client_bundle_billing(tier, billing_clients),
            },
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + len(clients) < total,
            },
        },
    }


@router.get("/clients/{client_id}")
async def get_client(
    client_id: str,
    api_key: str = Depends(get_api_key_header),
):
    """
    Get a single client's details.

    Args:
        client_id: The client ID
        api_key: Integrator's API key

    Returns:
        Client details with project info
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    db = await get_db()

    client = await db.integratorclient.find_first(
        where={"id": client_id, "workspaceId": workspace.id},
        include={"project": True, "apiKeys": True},
    )

    if not client:
        raise HTTPException(status_code=404, detail="CLIENT_NOT_FOUND")
    tier = integrator_info["tier"]

    return {
        "success": True,
        "data": {
            "client_id": client.id,
            "project_id": client.projectId,
            "project_slug": client.project.slug if client.project else None,
            "name": client.name,
            "email": client.email,
            "external_id": client.externalId,
            "bundle": client.bundle,
            "is_active": client.isActive,
            "limits": get_client_bundle_limits(client.bundle),
            "pricing": get_client_bundle_pricing(client.bundle, tier),
            "api_key_count": len(client.apiKeys) if client.apiKeys else 0,
            "created_at": client.createdAt.isoformat(),
            "updated_at": client.updatedAt.isoformat(),
        },
    }


@router.patch("/clients/{client_id}")
async def update_client(
    client_id: str,
    request: UpdateClientRequest,
    api_key: str = Depends(get_api_key_header),
):
    """
    Update a client's settings.

    Args:
        client_id: The client ID
        request: Fields to update
        api_key: Integrator's API key

    Returns:
        Updated client details
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    db = await get_db()

    client = await db.integratorclient.find_first(
        where={"id": client_id, "workspaceId": workspace.id}
    )

    if not client:
        raise HTTPException(status_code=404, detail="CLIENT_NOT_FOUND")

    update_data = {}
    if request.name is not None:
        update_data["name"] = request.name
    if request.email is not None:
        # Check for duplicate email
        existing = await db.integratorclient.find_first(
            where={
                "workspaceId": workspace.id,
                "email": request.email,
                "NOT": {"id": client_id},
            }
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"A client with email '{request.email}' already exists.",
            )
        update_data["email"] = request.email
    if request.bundle is not None:
        update_data["bundle"] = request.bundle
    if request.is_active is not None:
        update_data["isActive"] = request.is_active

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    client = await db.integratorclient.update(
        where={"id": client_id},
        data=update_data,
        include={"project": True},
    )

    logger.info(f"Updated client {client_id}")
    tier = integrator_info["tier"]

    # Emit webhook event with changes
    await emit_client_updated(
        workspace.id,
        {
            "client_id": client.id,
            "project_id": client.projectId,
            "name": client.name,
            "email": client.email,
            "bundle": client.bundle,
            "is_active": client.isActive,
        },
        update_data,  # The fields that changed
    )

    return {
        "success": True,
        "data": {
            "client_id": client.id,
            "project_id": client.projectId,
            "project_slug": client.project.slug if client.project else None,
            "name": client.name,
            "email": client.email,
            "bundle": client.bundle,
            "is_active": client.isActive,
            "limits": get_client_bundle_limits(client.bundle),
            "pricing": get_client_bundle_pricing(client.bundle, tier),
            "updated_at": client.updatedAt.isoformat(),
        },
    }


@router.delete("/clients/{client_id}")
async def delete_client(
    client_id: str,
    api_key: str = Depends(get_api_key_header),
):
    """
    Delete a client and their associated project.

    This is a destructive operation that will:
    1. Delete all client API keys
    2. Delete the client's project (including all documents, memories, etc.)
    3. Delete the client record

    Args:
        client_id: The client ID
        api_key: Integrator's API key

    Returns:
        Deletion confirmation
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    db = await get_db()

    client = await db.integratorclient.find_first(
        where={"id": client_id, "workspaceId": workspace.id},
        include={"project": True},
    )

    if not client:
        raise HTTPException(status_code=404, detail="CLIENT_NOT_FOUND")

    project_id = client.projectId
    client_email = client.email

    # Delete client (cascades to API keys)
    await db.integratorclient.delete(where={"id": client_id})

    # Delete associated project if it exists
    if project_id:
        await db.project.delete(where={"id": project_id})

    logger.info(f"Deleted client {client_id} and project {project_id}")

    # Emit webhook event
    await emit_client_deleted(workspace.id, client_id, client_email)

    return {
        "success": True,
        "data": {
            "deleted_client_id": client_id,
            "deleted_project_id": project_id,
        },
    }


# ============ API KEY ENDPOINTS ============


@router.post("/clients/{client_id}/api-keys")
async def create_api_key(
    client_id: str,
    request: CreateApiKeyRequest,
    api_key: str = Depends(get_api_key_header),
):
    """
    Create a new API key for a client.

    The full API key is only returned once. Store it securely.

    Args:
        client_id: The client ID
        request: API key creation parameters
        api_key: Integrator's API key

    Returns:
        Created API key (shown only once)
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    db = await get_db()

    client = await db.integratorclient.find_first(
        where={"id": client_id, "workspaceId": workspace.id}
    )

    if not client:
        raise HTTPException(status_code=404, detail="CLIENT_NOT_FOUND")

    if not client.isActive:
        raise HTTPException(
            status_code=403,
            detail="CLIENT_INACTIVE: Cannot create API keys for inactive clients.",
        )

    # Generate API key
    raw_key = generate_client_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:16]  # snipara_ic_xxxx

    # Calculate expiration if specified
    expires_at = None
    if request.expires_in_days:
        from datetime import timedelta

        expires_at = datetime.now(UTC) + timedelta(days=request.expires_in_days)

    api_key_record = await db.clientapikey.create(
        data={
            "clientId": client_id,
            "name": request.name,
            "keyHash": key_hash,
            "keyPrefix": key_prefix,
            "expiresAt": expires_at,
        }
    )

    logger.info(f"Created API key {api_key_record.id} for client {client_id}")

    # Emit webhook event
    await emit_api_key_created(workspace.id, client_id, request.name, key_prefix)

    return {
        "success": True,
        "data": {
            "api_key": raw_key,  # Only shown once!
            "key_id": api_key_record.id,
            "key_prefix": key_prefix,
            "name": api_key_record.name,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "created_at": api_key_record.createdAt.isoformat(),
        },
        "warning": "Store this API key securely. It will not be shown again.",
    }


@router.get("/clients/{client_id}/api-keys")
async def list_api_keys(
    client_id: str,
    api_key: str = Depends(get_api_key_header),
):
    """
    List all API keys for a client.

    Note: The actual key values are not returned, only metadata.

    Args:
        client_id: The client ID
        api_key: Integrator's API key

    Returns:
        List of API key metadata
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    db = await get_db()

    client = await db.integratorclient.find_first(
        where={"id": client_id, "workspaceId": workspace.id}
    )

    if not client:
        raise HTTPException(status_code=404, detail="CLIENT_NOT_FOUND")

    api_keys = await db.clientapikey.find_many(
        where={"clientId": client_id},
        order={"createdAt": "desc"},
    )

    return {
        "success": True,
        "data": {
            "api_keys": [
                {
                    "key_id": k.id,
                    "key_prefix": k.keyPrefix,
                    "name": k.name,
                    "last_used_at": k.lastUsedAt.isoformat() if k.lastUsedAt else None,
                    "expires_at": k.expiresAt.isoformat() if k.expiresAt else None,
                    "revoked_at": k.revokedAt.isoformat() if k.revokedAt else None,
                    "is_active": not k.revokedAt
                    and (not k.expiresAt or k.expiresAt > datetime.now(UTC)),
                    "created_at": k.createdAt.isoformat(),
                }
                for k in api_keys
            ],
        },
    }


@router.delete("/clients/{client_id}/api-keys/{key_id}")
async def revoke_api_key(
    client_id: str,
    key_id: str,
    api_key: str = Depends(get_api_key_header),
):
    """
    Revoke an API key.

    Revoked keys cannot be un-revoked. Create a new key if needed.

    Args:
        client_id: The client ID
        key_id: The API key ID to revoke
        api_key: Integrator's API key

    Returns:
        Revocation confirmation
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    db = await get_db()

    client = await db.integratorclient.find_first(
        where={"id": client_id, "workspaceId": workspace.id}
    )

    if not client:
        raise HTTPException(status_code=404, detail="CLIENT_NOT_FOUND")

    api_key_record = await db.clientapikey.find_first(where={"id": key_id, "clientId": client_id})

    if not api_key_record:
        raise HTTPException(status_code=404, detail="API_KEY_NOT_FOUND")

    if api_key_record.revokedAt:
        raise HTTPException(status_code=400, detail="API key is already revoked")

    await db.clientapikey.update(
        where={"id": key_id},
        data={"revokedAt": datetime.now(UTC)},
    )

    logger.info(f"Revoked API key {key_id} for client {client_id}")

    # Emit webhook event
    await emit_api_key_revoked(workspace.id, client_id, key_id, api_key_record.name)

    return {
        "success": True,
        "data": {
            "revoked_key_id": key_id,
            "revoked_at": datetime.now(UTC).isoformat(),
        },
    }


# ============ SWARM ENDPOINTS ============


class CreateSwarmRequest(BaseModel):
    """Request body for creating a swarm."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    max_agents: int = Field(default=10, ge=1, le=100)


@router.post("/clients/{client_id}/swarms")
async def create_client_swarm(
    client_id: str,
    request: CreateSwarmRequest,
    api_key: str = Depends(get_api_key_header),
):
    """
    Create a swarm for a client's project.

    This pre-provisions a swarm so the client can immediately start
    using swarm features without needing ADMIN access.

    Args:
        client_id: The client ID
        request: Swarm creation parameters
        api_key: Integrator's API key

    Returns:
        Created swarm details
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    db = await get_db()

    # Get client with project
    client = await db.integratorclient.find_first(
        where={"id": client_id, "workspaceId": workspace.id},
        include={"project": True},
    )

    if not client:
        raise HTTPException(status_code=404, detail="CLIENT_NOT_FOUND")

    if not client.isActive:
        raise HTTPException(
            status_code=403,
            detail="CLIENT_INACTIVE: Cannot create swarms for inactive clients.",
        )

    if not client.project:
        raise HTTPException(
            status_code=400,
            detail="Client has no associated project.",
        )

    # Check bundle limits for swarms
    bundle_limits = get_client_bundle_limits(client.bundle)
    max_swarms = bundle_limits.get("swarms", 1)

    if max_swarms != -1:
        existing_swarms = await db.agentswarm.count(where={"projectId": client.projectId})
        if existing_swarms >= max_swarms:
            raise HTTPException(
                status_code=400,
                detail=f"SWARM_LIMIT_REACHED: {client.bundle} bundle allows {max_swarms} swarm(s). Upgrade bundle for more.",
            )

    # Create the swarm
    swarm = await db.agentswarm.create(
        data={
            "projectId": client.projectId,
            "name": request.name,
            "description": request.description,
            "maxAgents": request.max_agents,
            "isActive": True,
        }
    )

    logger.info(f"Created swarm {swarm.id} for client {client_id} project {client.projectId}")

    return {
        "success": True,
        "data": {
            "swarm_id": swarm.id,
            "project_id": client.projectId,
            "project_slug": client.project.slug,
            "name": swarm.name,
            "description": swarm.description,
            "max_agents": swarm.maxAgents,
            "is_active": swarm.isActive,
            "created_at": swarm.createdAt.isoformat(),
        },
    }


@router.get("/clients/{client_id}/swarms")
async def list_client_swarms(
    client_id: str,
    api_key: str = Depends(get_api_key_header),
):
    """
    List all swarms for a client's project.

    Args:
        client_id: The client ID
        api_key: Integrator's API key

    Returns:
        List of swarms
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    workspace = integrator_info["workspace"]
    if not workspace:
        raise HTTPException(status_code=404, detail="WORKSPACE_NOT_FOUND")

    db = await get_db()

    client = await db.integratorclient.find_first(
        where={"id": client_id, "workspaceId": workspace.id},
        include={"project": True},
    )

    if not client:
        raise HTTPException(status_code=404, detail="CLIENT_NOT_FOUND")

    if not client.project:
        return {"success": True, "data": {"swarms": []}}

    swarms = await db.agentswarm.find_many(
        where={"projectId": client.projectId},
        order={"createdAt": "desc"},
    )

    return {
        "success": True,
        "data": {
            "swarms": [
                {
                    "swarm_id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "max_agents": s.maxAgents,
                    "is_active": s.isActive,
                    "created_at": s.createdAt.isoformat(),
                }
                for s in swarms
            ],
        },
    }
