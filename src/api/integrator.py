"""Integrator Admin API endpoints.

This module provides REST API endpoints for integrators to manage their
workspace, clients, and API keys. All endpoints require authentication
with an integrator's API key (rlm_*).

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


# ============ BUNDLE LIMITS ============

BUNDLE_LIMITS = {
    "LITE": {
        "queries_per_month": 200,
        "memories": 100,
        "swarms": 1,
        "agents_per_swarm": 5,
        "documents": 50,
        "storage_mb": 100,
    },
    "STANDARD": {
        "queries_per_month": 2000,
        "memories": 500,
        "swarms": 5,
        "agents_per_swarm": 10,
        "documents": 200,
        "storage_mb": 1024,
    },
    "UNLIMITED": {
        "queries_per_month": -1,  # Unlimited
        "memories": -1,
        "swarms": -1,
        "agents_per_swarm": 20,
        "documents": -1,
        "storage_mb": 10240,
    },
}


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
    Validate API key and return integrator info.

    The integrator must have an active subscription to use the Admin API.

    Args:
        api_key: The API key from the request header

    Returns:
        Dict with integrator info including workspace

    Raises:
        HTTPException if API key is invalid or user is not an integrator
    """
    db = await get_db()

    key_hash = hash_api_key(api_key)

    # Find the API key and get user
    api_key_record = await db.apikey.find_first(
        where={"keyHash": key_hash},
        include={
            "user": {
                "include": {
                    "integrator": {
                        "include": {
                            "workspace": True,
                        }
                    }
                }
            }
        },
    )

    # Also try team API keys
    if not api_key_record:
        api_key_record = await db.teamapikey.find_first(
            where={"keyHash": key_hash},
            include={
                "user": {
                    "include": {
                        "integrator": {
                            "include": {
                                "workspace": True,
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

    user = api_key_record.user
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    integrator = user.integrator
    if not integrator:
        raise HTTPException(
            status_code=403,
            detail="INTEGRATOR_NOT_FOUND: You must have an Integrator subscription to use this API. Visit https://snipara.com/integrator to sign up.",
        )

    return {
        "user_id": user.id,
        "integrator_id": integrator.id,
        "integrator": integrator,
        "workspace": integrator.workspace,
        "tier": integrator.tier,
        "client_limit": integrator.clientLimit,
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
    api_key: str = Depends(get_api_key_header),
):
    """
    Create a workspace for the integrator.

    Each integrator can only have one workspace. The workspace is the
    container for all clients managed by the integrator.

    Args:
        request: Workspace creation parameters
        api_key: Integrator's API key

    Returns:
        Created workspace details
    """
    integrator_info = await get_integrator_from_api_key(api_key)

    if integrator_info["workspace"]:
        raise HTTPException(
            status_code=400,
            detail="WORKSPACE_EXISTS: You already have a workspace. Use GET /v1/integrator/workspace to view it.",
        )

    db = await get_db()

    # Check if slug is already taken
    existing = await db.integratorworkspace.find_first(where={"slug": request.slug})
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Workspace slug '{request.slug}' is already taken. Choose a different slug.",
        )

    workspace = await db.integratorworkspace.create(
        data={
            "integratorId": integrator_info["integrator_id"],
            "name": request.name,
            "slug": request.slug,
        }
    )

    logger.info(
        f"Created workspace {workspace.id} for integrator {integrator_info['integrator_id']}"
    )

    return {
        "success": True,
        "data": {
            "workspace_id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "created_at": workspace.createdAt.isoformat(),
        },
    }


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
            detail="WORKSPACE_NOT_FOUND: You don't have a workspace yet. Create one with POST /v1/integrator/workspace.",
        )

    db = await get_db()

    # Get client count
    client_count = await db.integratorclient.count(
        where={"workspaceId": workspace.id}
    )

    return {
        "success": True,
        "data": {
            "workspace_id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "webhook_url": workspace.webhookUrl,
            "has_webhook_secret": bool(workspace.webhookSecret),
            "client_count": client_count,
            "client_limit": integrator_info["client_limit"],
            "tier": integrator_info["tier"],
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
    client_count = await db.integratorclient.count(
        where={"workspaceId": workspace.id}
    )
    if client_count >= integrator_info["client_limit"]:
        raise HTTPException(
            status_code=400,
            detail=f"CLIENT_LIMIT_REACHED: You have reached your tier limit of {integrator_info['client_limit']} clients. Upgrade your tier to add more.",
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
    team_membership = next(
        (tm for tm in user_teams if tm.role in ("OWNER", "ADMIN")), None
    )
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

    limits = BUNDLE_LIMITS.get(request.bundle, BUNDLE_LIMITS["LITE"])

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
                    "limits": BUNDLE_LIMITS.get(c.bundle, BUNDLE_LIMITS["LITE"]),
                    "created_at": c.createdAt.isoformat(),
                }
                for c in clients
            ],
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
            "limits": BUNDLE_LIMITS.get(client.bundle, BUNDLE_LIMITS["LITE"]),
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
            "limits": BUNDLE_LIMITS.get(client.bundle, BUNDLE_LIMITS["LITE"]),
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

    api_key_record = await db.clientapikey.find_first(
        where={"id": key_id, "clientId": client_id}
    )

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
