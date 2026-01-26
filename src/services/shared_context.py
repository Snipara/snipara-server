"""Shared Context Service - loads and merges shared context collections for projects.

This service fetches shared context collections linked to a project and merges
their documents with the project's own documentation, respecting:
- Collection priority ordering
- Category-based token budgeting
- Conflict detection
"""

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum

from ..db import get_db

logger = logging.getLogger(__name__)


class DocumentCategory(str, Enum):
    """Document category for token budget allocation."""

    MANDATORY = "MANDATORY"
    BEST_PRACTICES = "BEST_PRACTICES"
    GUIDELINES = "GUIDELINES"
    REFERENCE = "REFERENCE"


# Default token budget percentages by category
DEFAULT_CATEGORY_BUDGETS = {
    DocumentCategory.MANDATORY: 40,
    DocumentCategory.BEST_PRACTICES: 30,
    DocumentCategory.GUIDELINES: 20,
    DocumentCategory.REFERENCE: 10,
}

# Priority order (higher = more important)
CATEGORY_PRIORITY = {
    DocumentCategory.MANDATORY: 100,
    DocumentCategory.BEST_PRACTICES: 75,
    DocumentCategory.GUIDELINES: 50,
    DocumentCategory.REFERENCE: 25,
}


@dataclass
class SharedDocument:
    """A shared document from a collection."""

    id: str
    title: str
    slug: str
    content: str
    category: DocumentCategory
    tags: list[str]
    priority: int  # Within-category priority
    token_count: int
    content_hash: str
    collection_id: str
    collection_name: str
    collection_priority: int  # Collection priority in project


@dataclass
class SharedContext:
    """Merged shared context for a project."""

    documents: list[SharedDocument] = field(default_factory=list)
    total_tokens: int = 0
    collection_versions: dict[str, int] = field(default_factory=dict)


async def load_team_context_for_project(project_id: str) -> list[SharedDocument]:
    """
    Load team-level context that applies to all projects in the team.

    Team contexts are simpler than SharedContextCollections - they're just
    key-value pairs with content that gets auto-included for all team projects.

    Args:
        project_id: The project ID

    Returns:
        List of SharedDocument from team contexts
    """
    db = await get_db()

    # Get project's team
    project = await db.project.find_unique(
        where={"id": project_id},
    )

    if not project or not project.teamId:
        return []

    # Get active team contexts
    team_contexts = await db.teamcontext.find_many(
        where={
            "teamId": project.teamId,
            "isActive": True,
        },
        order={"priority": "desc"},
    )

    documents: list[SharedDocument] = []

    for ctx in team_contexts:
        # Estimate token count (rough: 4 chars per token)
        token_count = len(ctx.value) // 4

        # Create a content hash
        content_hash = hashlib.sha256(ctx.value.encode()).hexdigest()[:16]

        doc = SharedDocument(
            id=f"team_ctx_{ctx.id}",
            title=ctx.name,
            slug=ctx.key,
            content=ctx.value,
            category=DocumentCategory.BEST_PRACTICES,
            tags=[],
            priority=ctx.priority,
            token_count=token_count,
            content_hash=content_hash,
            collection_id=f"team_{project.teamId}",
            collection_name="Team Context",
            collection_priority=-1,  # Higher priority than project collections
        )
        documents.append(doc)

    return documents


async def load_project_shared_context(project_id: str) -> SharedContext:
    """
    Load all shared context linked to a project.

    Returns documents from linked collections, ordered by:
    1. Collection priority (lower = higher priority)
    2. Category priority (MANDATORY > BEST_PRACTICES > GUIDELINES > REFERENCE)
    3. Document priority within category

    Args:
        project_id: The project ID

    Returns:
        SharedContext with all linked documents
    """
    db = await get_db()

    # Get all linked collections with their documents
    project_contexts = await db.projectsharedcontext.find_many(
        where={
            "projectId": project_id,
            "isEnabled": True,
        },
        include={
            "collection": {
                "include": {
                    "documents": True,
                }
            }
        },
        order={"priority": "asc"},
    )

    documents: list[SharedDocument] = []
    collection_versions: dict[str, int] = {}
    total_tokens = 0

    # Load team-level context first (highest priority, auto-applies to all projects)
    team_documents = await load_team_context_for_project(project_id)
    documents.extend(team_documents)
    total_tokens += sum(d.token_count for d in team_documents)

    for ctx in project_contexts:
        collection = ctx.collection
        if not collection:
            continue

        collection_versions[collection.id] = collection.version

        # Get enabled categories for this link (empty = all enabled)
        enabled_categories = ctx.enabledCategories or []

        for doc in collection.documents:
            # Filter by enabled categories if specified
            if enabled_categories and doc.category not in enabled_categories:
                continue

            try:
                category = DocumentCategory(doc.category)
            except ValueError:
                category = DocumentCategory.BEST_PRACTICES

            shared_doc = SharedDocument(
                id=doc.id,
                title=doc.title,
                slug=doc.slug,
                content=doc.content,
                category=category,
                tags=doc.tags or [],
                priority=doc.priority,
                token_count=doc.tokenCount,
                content_hash=doc.contentHash,
                collection_id=collection.id,
                collection_name=collection.name,
                collection_priority=ctx.priority,
            )
            documents.append(shared_doc)
            total_tokens += doc.tokenCount

    # Sort documents by priority
    documents.sort(key=lambda d: (
        d.collection_priority,  # Collection priority first
        -CATEGORY_PRIORITY.get(d.category, 0),  # Then category priority (descending)
        -d.priority,  # Then document priority (descending)
    ))

    return SharedContext(
        documents=documents,
        total_tokens=total_tokens,
        collection_versions=collection_versions,
    )


def allocate_shared_context_budget(
    context: SharedContext,
    max_tokens: int,
    category_budgets: dict[DocumentCategory, int] | None = None,
) -> list[SharedDocument]:
    """
    Allocate shared context documents to fit within token budget.

    MANDATORY documents are always included first (up to their budget).
    Other categories are filled according to their budget percentages.

    Args:
        context: The SharedContext with all available documents
        max_tokens: Total token budget
        category_budgets: Optional custom budget percentages per category

    Returns:
        List of documents that fit within the budget
    """
    budgets = category_budgets or DEFAULT_CATEGORY_BUDGETS

    # Calculate token budgets per category
    category_token_budgets = {
        cat: int(max_tokens * percent / 100)
        for cat, percent in budgets.items()
    }

    # Track usage per category
    category_used: dict[DocumentCategory, int] = {cat: 0 for cat in DocumentCategory}
    selected: list[SharedDocument] = []
    total_used = 0

    # First pass: Include MANDATORY documents
    for doc in context.documents:
        if doc.category != DocumentCategory.MANDATORY:
            continue

        budget = category_token_budgets[DocumentCategory.MANDATORY]
        if category_used[DocumentCategory.MANDATORY] + doc.token_count <= budget:
            if total_used + doc.token_count <= max_tokens:
                selected.append(doc)
                category_used[DocumentCategory.MANDATORY] += doc.token_count
                total_used += doc.token_count

    # Second pass: Include other categories
    for doc in context.documents:
        if doc.category == DocumentCategory.MANDATORY:
            continue  # Already processed

        budget = category_token_budgets.get(doc.category, 0)
        if category_used[doc.category] + doc.token_count <= budget:
            if total_used + doc.token_count <= max_tokens:
                selected.append(doc)
                category_used[doc.category] += doc.token_count
                total_used += doc.token_count

    # Third pass: Fill remaining budget with any category
    remaining = max_tokens - total_used
    for doc in context.documents:
        if doc in selected:
            continue

        if doc.token_count <= remaining:
            selected.append(doc)
            total_used += doc.token_count
            remaining -= doc.token_count

    return selected


def merge_shared_context_with_project_docs(
    shared_docs: list[SharedDocument],
    project_content: str,
) -> str:
    """
    Merge shared context documents with project-specific content.

    Shared context is prepended with clear section markers.
    Project content is marked as having higher priority (overrides shared).

    Args:
        shared_docs: Allocated shared documents
        project_content: Project-specific documentation content

    Returns:
        Merged content string
    """
    if not shared_docs:
        return project_content

    parts: list[str] = []

    # Group by category for organization
    by_category: dict[DocumentCategory, list[SharedDocument]] = {
        cat: [] for cat in DocumentCategory
    }
    for doc in shared_docs:
        by_category[doc.category].append(doc)

    # Add shared context header
    parts.append("<!-- BEGIN SHARED CONTEXT -->")
    parts.append("<!-- These are shared guidelines and best practices. -->")
    parts.append("<!-- Project-specific instructions below take precedence. -->")
    parts.append("")

    category_labels = {
        DocumentCategory.MANDATORY: "## MANDATORY RULES",
        DocumentCategory.BEST_PRACTICES: "## BEST PRACTICES",
        DocumentCategory.GUIDELINES: "## GUIDELINES",
        DocumentCategory.REFERENCE: "## REFERENCE",
    }

    for category in [
        DocumentCategory.MANDATORY,
        DocumentCategory.BEST_PRACTICES,
        DocumentCategory.GUIDELINES,
        DocumentCategory.REFERENCE,
    ]:
        docs = by_category[category]
        if not docs:
            continue

        parts.append(category_labels[category])
        parts.append("")

        for doc in docs:
            parts.append(f"### {doc.title}")
            parts.append(f"<!-- From: {doc.collection_name} -->")
            parts.append(doc.content)
            parts.append("")

    parts.append("<!-- END SHARED CONTEXT -->")
    parts.append("")

    # Add project content with override marker
    if project_content:
        parts.append("<!-- BEGIN PROJECT-SPECIFIC CONTENT -->")
        parts.append("<!-- These instructions override shared context above. -->")
        parts.append("")
        parts.append(project_content)
        parts.append("")
        parts.append("<!-- END PROJECT-SPECIFIC CONTENT -->")

    return "\n".join(parts)


def compute_context_hash(context: SharedContext) -> str:
    """
    Compute a hash of the shared context for cache invalidation.

    The hash changes when:
    - Collection versions change
    - Documents are added/removed
    - Document content changes

    Args:
        context: The SharedContext to hash

    Returns:
        SHA256 hash string
    """
    # Combine collection versions and document hashes
    parts = []

    # Add collection versions sorted by ID
    for col_id in sorted(context.collection_versions.keys()):
        version = context.collection_versions[col_id]
        parts.append(f"{col_id}:{version}")

    # Add document content hashes
    for doc in context.documents:
        parts.append(doc.content_hash)

    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


async def get_shared_mcp_config(project_id: str) -> dict | None:
    """
    Get merged MCP configuration from linked collections.

    Returns the combined MCP tool configurations from all linked collections.
    Later collections in priority order can override earlier ones.

    Args:
        project_id: The project ID

    Returns:
        Merged MCP configuration dict or None if no config found
    """
    db = await get_db()

    # Get linked collections with MCP config
    project_contexts = await db.projectsharedcontext.find_many(
        where={
            "projectId": project_id,
            "isEnabled": True,
        },
        include={
            "collection": {
                "include": {
                    "mcpConfig": True,
                }
            }
        },
        order={"priority": "asc"},
    )

    merged_config: dict = {
        "tools": {},
        "enabled": [],
        "disabled": [],
    }

    for ctx in project_contexts:
        collection = ctx.collection
        if not collection or not collection.mcpConfig:
            continue

        mcp_config = collection.mcpConfig

        # Merge tool configurations
        if mcp_config.toolConfig:
            tool_config = mcp_config.toolConfig
            if isinstance(tool_config, dict):
                for tool_name, config in tool_config.items():
                    merged_config["tools"][tool_name] = config

        # Merge enabled tools (union)
        if mcp_config.enabledTools:
            for tool in mcp_config.enabledTools:
                if tool not in merged_config["enabled"]:
                    merged_config["enabled"].append(tool)

        # Merge disabled tools (union)
        if mcp_config.disabledTools:
            for tool in mcp_config.disabledTools:
                if tool not in merged_config["disabled"]:
                    merged_config["disabled"].append(tool)

    if not merged_config["tools"] and not merged_config["enabled"]:
        return None

    return merged_config


async def get_shared_prompt_templates(
    project_id: str,
    category: str | None = None,
) -> list[dict]:
    """
    Get prompt templates from linked collections.

    Args:
        project_id: The project ID
        category: Optional category filter

    Returns:
        List of prompt template dicts
    """
    db = await get_db()

    # Get linked collections with templates
    project_contexts = await db.projectsharedcontext.find_many(
        where={
            "projectId": project_id,
            "isEnabled": True,
        },
        include={
            "collection": {
                "include": {
                    "promptTemplates": True,
                }
            }
        },
        order={"priority": "asc"},
    )

    templates: list[dict] = []

    for ctx in project_contexts:
        collection = ctx.collection
        if not collection:
            continue

        for template in collection.promptTemplates:
            # Filter by category if specified
            if category and template.category != category:
                continue

            templates.append({
                "id": template.id,
                "name": template.name,
                "slug": template.slug,
                "description": template.description,
                "prompt": template.prompt,
                "variables": template.variables or [],
                "category": template.category,
                "collection_name": collection.name,
                "collection_id": collection.id,
            })

    return templates
