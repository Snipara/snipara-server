"""Document tool handlers for document management.

Handles:
- rlm_upload_document: Upload or update a document
- rlm_sync_documents: Bulk sync multiple documents
- rlm_settings: Get project settings
- rlm_request_access: Request access to a project
"""

import hashlib
from collections.abc import Callable
from typing import Any

from ...db import get_db
from ...models import (
    RequestAccessResult,
    SettingsResult,
    SyncDocumentsResult,
    ToolResult,
    UploadDocumentResult,
)
from .base import HandlerContext, count_tokens


async def handle_upload_document(
    params: dict[str, Any],
    ctx: HandlerContext,
    invalidate_index: Callable[[], None],  # Callback to invalidate engine's index
) -> ToolResult:
    """Upload or update a document.

    Args:
        params: Dict containing:
            - path: Document path (e.g., 'docs/api.md')
            - content: Document content (markdown)

    Returns:
        ToolResult with upload status
    """
    path = params.get("path", "")
    content = params.get("content", "")

    if not path or not content:
        missing = []
        if not path:
            missing.append("path")
        if not content:
            missing.append("content")
        return ToolResult(
            data={
                "error": f"rlm_upload_document: missing required parameter(s): {', '.join(missing)}"
            },
            input_tokens=0,
            output_tokens=0,
        )

    # Validate path
    if not path.endswith((".md", ".txt", ".mdx")):
        return ToolResult(
            data={"error": "Only .md, .txt, .mdx files are supported"},
            input_tokens=0,
            output_tokens=0,
        )

    db = await get_db()
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    size = len(content.encode())

    # Check if document exists
    existing = await db.document.find_first(where={"projectId": ctx.project_id, "path": path})

    if existing:
        # Check if content changed
        if existing.hash == content_hash:
            result = UploadDocumentResult(
                path=path,
                action="unchanged",
                size=size,
                hash=content_hash,
                message=f"Document '{path}' is unchanged",
            )
        else:
            # Update existing document
            await db.document.update(
                where={"id": existing.id},
                data={"content": content, "hash": content_hash, "size": size},
            )
            # Invalidate index cache
            invalidate_index()
            result = UploadDocumentResult(
                path=path,
                action="updated",
                size=size,
                hash=content_hash,
                message=f"Document '{path}' updated ({size} bytes)",
            )
    else:
        # Create new document
        await db.document.create(
            data={
                "projectId": ctx.project_id,
                "path": path,
                "content": content,
                "hash": content_hash,
                "size": size,
            }
        )
        # Invalidate index cache
        invalidate_index()
        result = UploadDocumentResult(
            path=path,
            action="created",
            size=size,
            hash=content_hash,
            message=f"Document '{path}' created ({size} bytes)",
        )

    return ToolResult(
        data=result.model_dump(),
        input_tokens=count_tokens(content),
        output_tokens=count_tokens(str(result.model_dump())),
    )


async def handle_sync_documents(
    params: dict[str, Any],
    ctx: HandlerContext,
    invalidate_index: Callable[[], None],  # Callback to invalidate engine's index
) -> ToolResult:
    """Bulk sync multiple documents.

    Args:
        params: Dict containing:
            - documents: List of {path, content} objects
            - delete_missing: Whether to delete docs not in list

    Returns:
        ToolResult with sync status
    """
    documents = params.get("documents", [])
    delete_missing = params.get("delete_missing", False)

    if not documents:
        return ToolResult(
            data={
                "error": "rlm_sync_documents: missing required parameter 'documents' (list of {path, content})"
            },
            input_tokens=0,
            output_tokens=0,
        )

    db = await get_db()
    created = 0
    updated = 0
    unchanged = 0
    deleted = 0
    input_tokens = 0

    # Get all existing documents
    existing_docs = await db.document.find_many(where={"projectId": ctx.project_id})
    existing_by_path = {doc.path: doc for doc in existing_docs}
    synced_paths = set()

    for doc_data in documents:
        path = doc_data.get("path", "")
        content = doc_data.get("content", "")

        if not path or not content:
            continue

        # Validate path
        if not path.endswith((".md", ".txt", ".mdx")):
            continue

        synced_paths.add(path)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        size = len(content.encode())
        input_tokens += count_tokens(content)

        if path in existing_by_path:
            existing = existing_by_path[path]
            if existing.hash == content_hash:
                unchanged += 1
            else:
                await db.document.update(
                    where={"id": existing.id},
                    data={"content": content, "hash": content_hash, "size": size},
                )
                updated += 1
        else:
            await db.document.create(
                data={
                    "projectId": ctx.project_id,
                    "path": path,
                    "content": content,
                    "hash": content_hash,
                    "size": size,
                }
            )
            created += 1

    # Delete missing documents if requested
    if delete_missing:
        for path, doc in existing_by_path.items():
            if path not in synced_paths:
                await db.document.delete(where={"id": doc.id})
                deleted += 1

    # Invalidate index cache if any changes
    if created > 0 or updated > 0 or deleted > 0:
        invalidate_index()

    total = created + updated + unchanged
    result = SyncDocumentsResult(
        created=created,
        updated=updated,
        unchanged=unchanged,
        deleted=deleted,
        total=total,
        message=f"Synced {total} documents: {created} created, {updated} updated, {unchanged} unchanged, {deleted} deleted",
    )

    return ToolResult(
        data=result.model_dump(),
        input_tokens=input_tokens,
        output_tokens=count_tokens(str(result.model_dump())),
    )


async def handle_settings(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Get project settings.

    Returns:
        ToolResult with project settings
    """
    result = SettingsResult(
        project_id=ctx.project_id,
        max_tokens_per_query=ctx.settings.max_tokens_per_query,
        search_mode=ctx.settings.search_mode,
        include_summaries=ctx.settings.include_summaries,
        auto_inject_context=ctx.settings.auto_inject_context,
        message=f"Settings for project {ctx.project_id}",
    )

    return ToolResult(
        data=result.model_dump(),
        input_tokens=0,
        output_tokens=count_tokens(str(result.model_dump())),
    )


async def handle_request_access(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Request access to a project.

    This tool allows team members with NONE access level to request
    higher access levels (VIEWER, EDITOR, ADMIN) from project admins.

    Args:
        params: Dict containing:
            - requested_level: The access level to request (VIEWER, EDITOR, ADMIN)
            - reason: Optional reason for requesting access

    Returns:
        ToolResult with RequestAccessResult containing request status
    """
    requested_level = params.get("requested_level", "VIEWER").upper()
    reason = params.get("reason", "")

    # Validate requested level
    valid_levels = {"VIEWER", "EDITOR", "ADMIN"}
    if requested_level not in valid_levels:
        return ToolResult(
            data={
                "error": f"Invalid level. Must be one of: {', '.join(valid_levels)}",
                "valid_levels": list(valid_levels),
            },
            input_tokens=0,
            output_tokens=0,
        )

    # Check if user_id is available (needed for access requests)
    if not ctx.user_id:
        return ToolResult(
            data={
                "error": "User context required for access requests. This typically means you're using a project API key which already has access.",
            },
            input_tokens=0,
            output_tokens=0,
        )

    db = await get_db()

    # Get project info
    project = await db.project.find_first(
        where={"id": ctx.project_id},
        select={"id": True, "name": True, "slug": True, "teamId": True},
    )

    if not project:
        return ToolResult(
            data={"error": "Project not found"},
            input_tokens=0,
            output_tokens=0,
        )

    # Get team member ID for the user
    team_member = await db.teammember.find_first(
        where={
            "userId": ctx.user_id,
            "teamId": project.teamId,
        },
        select={"id": True},
    )

    if not team_member:
        return ToolResult(
            data={"error": "You must be a team member to request project access"},
            input_tokens=0,
            output_tokens=0,
        )

    # Check for existing pending request
    existing = await db.accessrequest.find_first(
        where={
            "projectId": project.id,
            "teamMemberId": team_member.id,
            "status": "PENDING",
        },
    )

    if existing:
        return ToolResult(
            data={
                "error": "You already have a pending access request for this project",
                "request_id": existing.id,
                "status": "pending",
            },
            input_tokens=0,
            output_tokens=0,
        )

    # Create access request
    access_request = await db.accessrequest.create(
        data={
            "projectId": project.id,
            "teamMemberId": team_member.id,
            "requestedLevel": requested_level,
            "reason": reason[:500] if reason else None,
            "status": "PENDING",
        },
    )

    result = RequestAccessResult(
        request_id=access_request.id,
        project_id=project.id,
        project_name=project.name,
        requested_level=requested_level,
        status="pending",
        message="Access request submitted. A project admin will review your request.",
        dashboard_url=f"https://app.snipara.com/team/projects/{project.slug}/access-requests",
    )

    return ToolResult(
        data=result.model_dump(),
        input_tokens=0,
        output_tokens=count_tokens(str(result.model_dump())),
    )
