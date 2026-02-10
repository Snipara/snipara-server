"""Summary storage models for RLM MCP Server (Phase 4.6)."""

from datetime import datetime

from pydantic import BaseModel, Field

from .enums import SummaryType


class StoreSummaryResult(BaseModel):
    """Result of rlm_store_summary tool."""

    summary_id: str = Field(..., description="Unique identifier for the stored summary")
    document_path: str = Field(..., description="Document path")
    summary_type: SummaryType = Field(..., description="Type of summary stored")
    token_count: int = Field(..., ge=0, description="Token count of the summary")
    created: bool = Field(default=True, description="True if new, False if updated existing")
    message: str = Field(..., description="Human-readable status message")


class SummaryInfo(BaseModel):
    """Information about a stored summary."""

    summary_id: str = Field(..., description="Unique identifier")
    document_path: str = Field(..., description="Document path")
    summary_type: SummaryType = Field(..., description="Type of summary")
    section_id: str | None = Field(default=None, description="Section identifier")
    line_start: int | None = Field(default=None, description="Start line")
    line_end: int | None = Field(default=None, description="End line")
    token_count: int = Field(..., ge=0, description="Token count")
    generated_by: str | None = Field(default=None, description="Generator model")
    content: str | None = Field(
        default=None, description="Summary content (if include_content=True)"
    )
    created_at: datetime = Field(..., description="When summary was created")
    updated_at: datetime = Field(..., description="When summary was last updated")


class GetSummariesResult(BaseModel):
    """Result of rlm_get_summaries tool."""

    summaries: list[SummaryInfo] = Field(
        default_factory=list, description="List of summaries matching filters"
    )
    total_count: int = Field(default=0, ge=0, description="Total number of summaries")
    total_tokens: int = Field(default=0, ge=0, description="Total tokens across all summaries")


class DeleteSummaryResult(BaseModel):
    """Result of rlm_delete_summary tool."""

    deleted_count: int = Field(default=0, ge=0, description="Number of summaries deleted")
    message: str = Field(..., description="Human-readable status message")
