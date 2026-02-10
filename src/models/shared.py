"""Shared context models for RLM MCP Server (Phase 7)."""

from pydantic import BaseModel, Field

from .enums import DocumentCategoryEnum


class SharedDocumentInfo(BaseModel):
    """Information about a shared document."""

    id: str = Field(..., description="Document ID")
    title: str = Field(..., description="Document title")
    category: DocumentCategoryEnum = Field(..., description="Document category")
    token_count: int = Field(..., ge=0, description="Token count")
    collection_name: str = Field(..., description="Source collection name")
    tags: list[str] = Field(default_factory=list, description="Document tags")


class SharedContextResult(BaseModel):
    """Result of rlm_shared_context tool."""

    documents: list[SharedDocumentInfo] = Field(
        default_factory=list,
        description="Shared documents matching criteria",
    )
    merged_content: str | None = Field(
        default=None,
        description="Merged content string (if include_content=True)",
    )
    total_tokens: int = Field(default=0, ge=0, description="Total tokens returned")
    collections_loaded: int = Field(default=0, ge=0, description="Number of collections loaded")
    context_hash: str = Field(
        default="",
        description="Hash for cache invalidation",
    )


class PromptTemplateInfo(BaseModel):
    """Information about a prompt template."""

    id: str = Field(..., description="Template ID")
    name: str = Field(..., description="Template name")
    slug: str = Field(..., description="Template slug")
    description: str | None = Field(default=None, description="Template description")
    prompt: str = Field(..., description="The prompt template text")
    variables: list[str] = Field(default_factory=list, description="Variables in the template")
    category: str = Field(..., description="Template category")
    collection_name: str = Field(..., description="Source collection name")


class ListTemplatesResult(BaseModel):
    """Result of rlm_list_templates tool."""

    templates: list[PromptTemplateInfo] = Field(
        default_factory=list, description="Available prompt templates"
    )
    total_count: int = Field(default=0, ge=0, description="Total templates found")
    categories: list[str] = Field(default_factory=list, description="Available categories")


class GetTemplateResult(BaseModel):
    """Result of rlm_get_template tool."""

    template: PromptTemplateInfo | None = Field(default=None, description="The template info")
    rendered_prompt: str | None = Field(
        default=None, description="Prompt with variables substituted"
    )
    missing_variables: list[str] = Field(
        default_factory=list, description="Variables that weren't provided"
    )
