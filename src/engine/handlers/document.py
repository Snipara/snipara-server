"""Document tool handlers for document management.

Handles:
- rlm_upload_document: Upload or update a document
- rlm_sync_documents: Bulk sync multiple documents
- rlm_settings: Get project settings
- rlm_request_access: Request access to a project
"""

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ...config import settings
from ...db import get_db
from ...models import (
    RequestAccessResult,
    SettingsResult,
    SyncDocumentsResult,
    ToolResult,
    UploadDocumentResult,
)
from ...services.binary_parsers import SUPPORTED_BINARY_FORMATS
from .base import HandlerContext, count_tokens

SUPPORTED_TEXT_DOCUMENT_FORMATS = ("adoc", "markdown", "md", "mdx", "rst", "txt")
SUPPORTED_SYNC_KINDS = {"DOC", "BINARY"}


def _document_format_from_path(path: str) -> str | None:
    file_name = path.rsplit("/", 1)[-1]
    if "." not in file_name:
        return None
    return file_name.rsplit(".", 1)[-1].lower()


def _resolve_document_storage(
    *, path: str, kind: Any = None, format_name: Any = None, language: Any = None
) -> tuple[dict[str, Any] | None, str | None]:
    inferred_format = _document_format_from_path(path)
    normalized_format = str(format_name or inferred_format or "").strip().lower()
    normalized_kind = str(kind or "").strip().upper()

    if not normalized_kind:
        if normalized_format in SUPPORTED_BINARY_FORMATS:
            normalized_kind = "BINARY"
        elif normalized_format in SUPPORTED_TEXT_DOCUMENT_FORMATS:
            normalized_kind = "DOC"

    if normalized_kind not in SUPPORTED_SYNC_KINDS:
        supported = ", ".join(
            f".{item}" for item in (*SUPPORTED_TEXT_DOCUMENT_FORMATS, *SUPPORTED_BINARY_FORMATS)
        )
        return None, f"Unsupported document type for '{path}'. Supported extensions: {supported}"

    if normalized_kind == "DOC" and normalized_format not in SUPPORTED_TEXT_DOCUMENT_FORMATS:
        supported = ", ".join(f".{item}" for item in SUPPORTED_TEXT_DOCUMENT_FORMATS)
        return None, f"DOC uploads support only: {supported}"

    if normalized_kind == "BINARY" and normalized_format not in SUPPORTED_BINARY_FORMATS:
        supported = ", ".join(f".{item}" for item in SUPPORTED_BINARY_FORMATS)
        return None, f"BINARY uploads support only: {supported}"

    normalized_language = str(language).strip().lower() if language else None
    return {
        "kind": normalized_kind,
        "format": normalized_format,
        "language": normalized_language or None,
    }, None


def _document_storage_matches(existing: Any, storage: dict[str, Any]) -> bool:
    existing_kind = str(getattr(existing, "kind", "DOC")).split(".")[-1].upper()
    return (
        existing_kind == storage["kind"]
        and getattr(existing, "format", None) == storage["format"]
        and getattr(existing, "language", None) == storage["language"]
    )


def _document_content_validation_error(content: str, storage: dict[str, Any]) -> str | None:
    if storage["kind"] != "BINARY" or storage["format"] == "svg":
        return None
    stripped = content.strip()
    if stripped.startswith("base64:") or (stripped.startswith("data:") and ";base64," in stripped):
        return None
    return "Binary document content must be base64-prefixed, e.g. base64:<payload>"


def _document_input_tokens(content: str, storage: dict[str, Any]) -> int:
    if storage["kind"] == "BINARY":
        return count_tokens(f"{storage['kind']} {storage['format']}")
    return count_tokens(content)


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
    storage, storage_error = _resolve_document_storage(
        path=path,
        kind=params.get("kind"),
        format_name=params.get("format"),
        language=params.get("language"),
    )

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

    if storage_error or storage is None:
        return ToolResult(
            data={"error": storage_error},
            input_tokens=0,
            output_tokens=0,
        )

    content_error = _document_content_validation_error(content, storage)
    if content_error:
        return ToolResult(
            data={"error": content_error},
            input_tokens=0,
            output_tokens=0,
        )

    db = await get_db()
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    size = len(content.encode())

    # Check if document exists (including soft-deleted)
    existing = await db.document.find_first(where={"projectId": ctx.project_id, "path": path})

    if existing:
        # Check if soft-deleted - if so, restore it
        if existing.deletedAt is not None:
            # Restore soft-deleted document with new content
            await db.document.update(
                where={"id": existing.id},
                data={
                    "content": content,
                    "hash": content_hash,
                    "size": size,
                    "deletedAt": None,
                    "deletedBy": None,
                    **storage,
                },
            )
            # Invalidate index cache
            invalidate_index()
            result = UploadDocumentResult(
                path=path,
                action="restored",
                size=size,
                hash=content_hash,
                message=f"Document '{path}' restored from trash ({size} bytes)",
            )
        # Check if content changed
        elif existing.hash == content_hash and _document_storage_matches(existing, storage):
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
                data={"content": content, "hash": content_hash, "size": size, **storage},
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
                **storage,
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
        input_tokens=_document_input_tokens(content, storage),
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

    # Get all existing documents (exclude soft-deleted)
    existing_docs = await db.document.find_many(where={"projectId": ctx.project_id, "deletedAt": None})
    existing_by_path = {doc.path: doc for doc in existing_docs}
    synced_paths = set()

    for doc_data in documents:
        path = doc_data.get("path", "")
        content = doc_data.get("content", "")
        storage, storage_error = _resolve_document_storage(
            path=path,
            kind=doc_data.get("kind"),
            format_name=doc_data.get("format"),
            language=doc_data.get("language"),
        )

        if not path or not content:
            continue

        if storage_error or storage is None:
            continue

        if _document_content_validation_error(content, storage):
            continue

        synced_paths.add(path)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        size = len(content.encode())
        input_tokens += _document_input_tokens(content, storage)

        if path in existing_by_path:
            existing = existing_by_path[path]
            if existing.hash == content_hash and _document_storage_matches(existing, storage):
                unchanged += 1
            else:
                await db.document.update(
                    where={"id": existing.id},
                    data={"content": content, "hash": content_hash, "size": size, **storage},
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
                    **storage,
                }
            )
            created += 1

    # Delete missing documents if requested
    if delete_missing:
        # Get trash retention days for this plan
        plan_name = ctx.plan.value if hasattr(ctx.plan, "value") else str(ctx.plan)
        trash_retention_days = settings.trash_retention_days.get(plan_name, 0)

        for path, doc in existing_by_path.items():
            if path not in synced_paths:
                if trash_retention_days > 0:
                    # Soft delete - move to trash (plan supports retention)
                    await db.document.update(
                        where={"id": doc.id},
                        data={
                            "deletedAt": datetime.now(timezone.utc),
                            "deletedBy": ctx.user_id,
                        },
                    )
                    # Delete chunks to free up space (can be regenerated on restore)
                    await db.documentchunk.delete_many(where={"documentId": doc.id})
                else:
                    # Hard delete - FREE plan has no trash retention
                    await db.documentchunk.delete_many(where={"documentId": doc.id})
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
