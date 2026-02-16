"""Summary tool handlers for summary storage.

Handles:
- rlm_store_summary: Store an LLM-generated summary for a document
- rlm_get_summaries: Retrieve stored summaries
- rlm_delete_summary: Delete stored summaries
"""

from typing import Any

from ...db import get_db
from ...models import (
    DeleteSummaryResult,
    GetSummariesResult,
    Plan,
    StoreSummaryResult,
    SummaryInfo,
    SummaryType,
    ToolResult,
)
from .base import HandlerContext, count_tokens

# Plans that support summary storage
SUMMARY_STORAGE_PLANS = {Plan.PRO, Plan.TEAM, Plan.ENTERPRISE}


async def handle_store_summary(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Store an LLM-generated summary for a document.

    This allows client LLMs to store summaries they generate, which can be
    retrieved later for faster context retrieval without re-processing.

    Args:
        params: Dict containing:
            - document_path: Path to the document
            - summary: The summary text to store
            - summary_type: Type of summary (concise, detailed, technical, keywords, custom)
            - section_id: Optional section identifier for partial summaries
            - line_start: Optional start line for section summary
            - line_end: Optional end line for section summary
            - generated_by: Optional model name that generated the summary

    Returns:
        ToolResult with StoreSummaryResult containing summary ID
    """
    document_path = params.get("document_path", "")
    summary = params.get("summary", "")
    summary_type_str = params.get("summary_type", "concise")
    section_id = params.get("section_id")
    line_start = params.get("line_start")
    line_end = params.get("line_end")
    generated_by = params.get("generated_by")

    # Plan gating
    if ctx.plan not in SUMMARY_STORAGE_PLANS:
        return ToolResult(
            data={
                "error": "rlm_store_summary requires Pro plan or higher",
                "upgrade_url": "/billing/upgrade",
            },
            input_tokens=count_tokens(summary),
            output_tokens=0,
        )

    # Validate inputs
    if not document_path or not summary:
        missing = []
        if not document_path:
            missing.append("document_path")
        if not summary:
            missing.append("summary")
        return ToolResult(
            data={
                "error": f"rlm_store_summary: missing required parameter(s): {', '.join(missing)}"
            },
            input_tokens=0,
            output_tokens=0,
        )

    # Parse summary type
    try:
        summary_type = SummaryType(summary_type_str)
    except ValueError:
        summary_type = SummaryType.CONCISE

    db = await get_db()

    # Find the document
    document = await db.document.find_first(
        where={
            "projectId": ctx.project_id,
            "path": document_path,
        }
    )

    if not document:
        return ToolResult(
            data={"error": f"Document not found: {document_path}"},
            input_tokens=count_tokens(summary),
            output_tokens=0,
        )

    # Calculate token count for the summary
    token_count = count_tokens(summary)

    # Check if summary already exists (upsert)
    existing = await db.documentsummary.find_first(
        where={
            "documentId": document.id,
            "summaryType": summary_type.value,
            "sectionId": section_id,
        }
    )

    if existing:
        # Update existing summary
        await db.documentsummary.update(
            where={"id": existing.id},
            data={
                "summary": summary,
                "tokenCount": token_count,
                "lineStart": line_start,
                "lineEnd": line_end,
                "generatedBy": generated_by,
            },
        )
        created = False
        summary_id = existing.id
    else:
        # Create new summary
        created_summary = await db.documentsummary.create(
            data={
                "documentId": document.id,
                "projectId": ctx.project_id,
                "summary": summary,
                "summaryType": summary_type.value,
                "sectionId": section_id,
                "lineStart": line_start,
                "lineEnd": line_end,
                "tokenCount": token_count,
                "generatedBy": generated_by,
            }
        )
        created = True
        summary_id = created_summary.id

    result = StoreSummaryResult(
        summary_id=summary_id,
        document_path=document_path,
        summary_type=summary_type,
        token_count=token_count,
        created=created,
        message=f"Summary {'created' if created else 'updated'} successfully ({token_count} tokens)",
    )

    return ToolResult(
        data=result.model_dump(),
        input_tokens=count_tokens(summary),
        output_tokens=count_tokens(str(result.model_dump())),
    )


async def handle_get_summaries(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Retrieve stored summaries.

    Args:
        params: Dict containing:
            - document_path: Filter by document path (optional)
            - summary_type: Filter by summary type (optional)
            - section_id: Filter by section ID (optional)
            - include_content: Include summary content in response (default True)

    Returns:
        ToolResult with GetSummariesResult containing matching summaries
    """
    document_path = params.get("document_path")
    summary_type_str = params.get("summary_type")
    section_id = params.get("section_id")
    include_content = params.get("include_content", True)

    # Plan gating
    if ctx.plan not in SUMMARY_STORAGE_PLANS:
        return ToolResult(
            data={
                "error": "rlm_get_summaries requires Pro plan or higher",
                "upgrade_url": "/billing/upgrade",
            },
            input_tokens=0,
            output_tokens=0,
        )

    db = await get_db()

    # Build query filters
    where_clause: dict[str, Any] = {"projectId": ctx.project_id}

    if document_path:
        # Find document ID first
        document = await db.document.find_first(
            where={
                "projectId": ctx.project_id,
                "path": document_path,
            }
        )
        if document:
            where_clause["documentId"] = document.id
        else:
            # No document found, return empty
            return ToolResult(
                data=GetSummariesResult(
                    summaries=[],
                    total_count=0,
                    total_tokens=0,
                ).model_dump(),
                input_tokens=0,
                output_tokens=0,
            )

    if summary_type_str:
        try:
            summary_type = SummaryType(summary_type_str)
            where_clause["summaryType"] = summary_type.value
        except ValueError:
            pass

    if section_id:
        where_clause["sectionId"] = section_id

    # Query summaries with document info
    summaries = await db.documentsummary.find_many(
        where=where_clause,
        include={"document": True},
        order={"createdAt": "desc"},
    )

    # Build response
    summary_infos: list[SummaryInfo] = []
    total_tokens = 0

    for s in summaries:
        try:
            summary_type_enum = SummaryType(s.summaryType)
        except ValueError:
            summary_type_enum = SummaryType.CUSTOM

        summary_info = SummaryInfo(
            summary_id=s.id,
            document_path=s.document.path if s.document else "unknown",
            summary_type=summary_type_enum,
            section_id=s.sectionId,
            line_start=s.lineStart,
            line_end=s.lineEnd,
            token_count=s.tokenCount,
            generated_by=s.generatedBy,
            content=s.summary if include_content else None,
            created_at=s.createdAt,
            updated_at=s.updatedAt,
        )
        summary_infos.append(summary_info)
        total_tokens += s.tokenCount

    result = GetSummariesResult(
        summaries=summary_infos,
        total_count=len(summary_infos),
        total_tokens=total_tokens,
    )

    output_tokens = total_tokens if include_content else len(summary_infos) * 50

    return ToolResult(
        data=result.model_dump(),
        input_tokens=0,
        output_tokens=output_tokens,
    )


async def handle_delete_summary(
    params: dict[str, Any],
    ctx: HandlerContext,
) -> ToolResult:
    """Delete stored summaries.

    Args:
        params: Dict containing (at least one required):
            - summary_id: Specific summary ID to delete
            - document_path: Delete all summaries for this document
            - summary_type: Delete summaries of this type

    Returns:
        ToolResult with DeleteSummaryResult containing deletion count
    """
    summary_id = params.get("summary_id")
    document_path = params.get("document_path")
    summary_type_str = params.get("summary_type")

    # Plan gating
    if ctx.plan not in SUMMARY_STORAGE_PLANS:
        return ToolResult(
            data={
                "error": "rlm_delete_summary requires Pro plan or higher",
                "upgrade_url": "/billing/upgrade",
            },
            input_tokens=0,
            output_tokens=0,
        )

    # Require at least one filter
    if not summary_id and not document_path and not summary_type_str:
        return ToolResult(
            data={
                "error": "rlm_delete_summary: at least one filter is required (summary_id, document_path, or summary_type)"
            },
            input_tokens=0,
            output_tokens=0,
        )

    db = await get_db()

    # Build delete filter
    where_clause: dict[str, Any] = {"projectId": ctx.project_id}

    if summary_id:
        # Delete specific summary
        where_clause["id"] = summary_id
    else:
        if document_path:
            document = await db.document.find_first(
                where={
                    "projectId": ctx.project_id,
                    "path": document_path,
                }
            )
            if document:
                where_clause["documentId"] = document.id
            else:
                return ToolResult(
                    data=DeleteSummaryResult(
                        deleted_count=0,
                        message="Document not found",
                    ).model_dump(),
                    input_tokens=0,
                    output_tokens=0,
                )

        if summary_type_str:
            try:
                summary_type = SummaryType(summary_type_str)
                where_clause["summaryType"] = summary_type.value
            except ValueError:
                pass

    # Execute delete
    deleted = await db.documentsummary.delete_many(where=where_clause)
    deleted_count = deleted if isinstance(deleted, int) else getattr(deleted, "count", 0)

    result = DeleteSummaryResult(
        deleted_count=deleted_count,
        message=f"Deleted {deleted_count} summary(ies)",
    )

    return ToolResult(
        data=result.model_dump(),
        input_tokens=0,
        output_tokens=count_tokens(str(result.model_dump())),
    )
