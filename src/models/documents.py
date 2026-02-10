"""Document sync and index job models for RLM MCP Server (Phase 10+)."""

from datetime import datetime

from pydantic import BaseModel, Field

from .enums import IndexJobStatus

# ============ DOCUMENT SYNC MODELS (Phase 10) ============


class UploadDocumentResult(BaseModel):
    """Result of rlm_upload_document tool."""

    path: str = Field(..., description="Document path")
    action: str = Field(..., description="Action taken: 'created' or 'updated'")
    size: int = Field(..., ge=0, description="Document size in bytes")
    hash: str = Field(..., description="Content hash")
    message: str = Field(..., description="Human-readable status message")


class SyncDocumentsResult(BaseModel):
    """Result of rlm_sync_documents tool."""

    created: int = Field(default=0, ge=0, description="Documents created")
    updated: int = Field(default=0, ge=0, description="Documents updated")
    unchanged: int = Field(default=0, ge=0, description="Documents unchanged")
    deleted: int = Field(default=0, ge=0, description="Documents deleted")
    total: int = Field(default=0, ge=0, description="Total documents processed")
    message: str = Field(..., description="Human-readable status message")


class SettingsResult(BaseModel):
    """Result of rlm_settings tool."""

    project_id: str = Field(..., description="Project ID")
    max_tokens_per_query: int = Field(..., description="Max tokens per query")
    search_mode: str = Field(..., description="Default search mode")
    include_summaries: bool = Field(..., description="Include summaries in queries")
    auto_inject_context: bool = Field(..., description="Auto-inject context")
    message: str = Field(..., description="Human-readable status message")


# ============ ACCESS REQUEST MODELS ============


class RequestAccessResult(BaseModel):
    """Result of rlm_request_access tool."""

    request_id: str = Field(..., description="Access request ID")
    project_id: str = Field(..., description="Project ID")
    project_name: str = Field(..., description="Project name")
    requested_level: str = Field(..., description="Requested access level")
    status: str = Field(default="pending", description="Request status")
    message: str = Field(..., description="Human-readable status message")
    dashboard_url: str = Field(..., description="URL to view request status")


# ============ INDEX JOB MODELS (Async Indexing) ============


class IndexJobCreateResponse(BaseModel):
    """Response from creating an index job."""

    job_id: str = Field(..., description="Unique job identifier")
    project_id: str = Field(..., description="Project being indexed")
    status: IndexJobStatus = Field(..., description="Current job status")
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage (0-100)")
    created_at: datetime | None = Field(default=None, description="Job creation time")
    status_url: str = Field(..., description="URL to poll for job status")
    already_exists: bool = Field(
        default=False, description="Whether a job already existed for this project"
    )


class IndexJobStatusResponse(BaseModel):
    """Response from checking index job status."""

    id: str = Field(..., alias="job_id", description="Job ID")
    project_id: str = Field(..., description="Project being indexed")
    status: IndexJobStatus = Field(..., description="Current job status")
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage (0-100)")
    error_message: str | None = Field(default=None, description="Error message if failed")
    documents_total: int = Field(default=0, ge=0, description="Total documents to index")
    documents_processed: int = Field(default=0, ge=0, description="Documents processed so far")
    chunks_created: int = Field(default=0, ge=0, description="Total chunks created")
    retry_count: int = Field(default=0, ge=0, description="Number of retries")
    max_retries: int = Field(default=3, ge=0, description="Maximum retries allowed")
    worker_id: str | None = Field(default=None, description="Worker processing this job")
    created_at: datetime | None = Field(default=None, description="Job creation time")
    started_at: datetime | None = Field(default=None, description="When processing started")
    completed_at: datetime | None = Field(default=None, description="When job completed")
    updated_at: datetime | None = Field(default=None, description="Last update time")
    triggered_by: str | None = Field(default=None, description="User who triggered the job")
    triggered_via: str | None = Field(
        default=None, description="How the job was triggered (api_key, internal)"
    )
    results: dict[str, int] | None = Field(
        default=None, description="Results mapping document paths to chunk counts"
    )
