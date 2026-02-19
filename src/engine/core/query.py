"""Query classification and expansion utilities.

This module provides utilities for classifying and expanding queries
to improve search relevance.
"""

import logging
import re

from ..scoring.constants import (
    CONCEPTUAL_PREFIXES,
    LIST_QUERY_PATTERNS,
    NUMBERED_SECTION_PATTERNS,
    PLANNED_CONTENT_MARKERS,
    QUERY_EXPANSIONS,
)

logger = logging.getLogger(__name__)

# Minimum sections to return for abstract/conceptual queries
# Abstract queries need more context to prevent hallucination
ABSTRACT_QUERY_MIN_SECTIONS = 5


def expand_query(query: str) -> str:
    """Expand abstract query terms with concrete keywords.

    For queries containing abstract terms like "architecture", appends
    concrete keywords that should match documentation sections.

    Args:
        query: Original query string

    Returns:
        Expanded query with additional keywords, or original if no expansion
    """
    query_lower = query.lower()
    expansions: list[str] = []

    for term, keywords in QUERY_EXPANSIONS.items():
        if term in query_lower:
            expansions.extend(keywords)

    if expansions:
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_expansions: list[str] = []
        for kw in expansions:
            kw_lower = kw.lower()
            if kw_lower not in seen and kw_lower not in query_lower:
                seen.add(kw_lower)
                unique_expansions.append(kw)

        if unique_expansions:
            # Append keywords to original query
            expanded = f"{query} {' '.join(unique_expansions)}"
            logger.info(f"Query expansion: '{query}' → '{expanded}'")
            return expanded

    return query


def is_abstract_query(query: str) -> bool:
    """Check if query is abstract and needs more context sections.

    Abstract queries use broad terms that may match few sections but require
    comprehensive answers. We boost minimum sections to reduce hallucination.

    Args:
        query: Query string to check

    Returns:
        True if query is abstract/conceptual
    """
    query_lower = query.lower()
    # Check if query contains any expansion terms
    for term in QUERY_EXPANSIONS.keys():
        if term in query_lower:
            return True
    # Also check for conceptual prefixes
    return any(query_lower.startswith(p) for p in CONCEPTUAL_PREFIXES)


def is_list_query(query: str) -> bool:
    """Check if query is asking for a list/enumeration of items.

    List queries like "what are the next articles to write" should boost
    sections with numbered patterns (Article #1, 1. First item, etc.)
    over prose/template sections that happen to contain matching keywords.

    Args:
        query: Query string to check

    Returns:
        True if query is asking for a list
    """
    query_lower = query.lower()
    return any(pattern in query_lower for pattern in LIST_QUERY_PATTERNS)


def is_numbered_section(title: str, content: str) -> bool:
    """Check if section title matches numbered/enumerated patterns.

    Args:
        title: Section title
        content: Section content (unused but kept for API consistency)

    Returns:
        True for sections like:
        - "### Article #1: Title"
        - "## 1. First Item"
        - "### Step 3: Implementation"
    """
    title_lower = title.lower()
    for pattern in NUMBERED_SECTION_PATTERNS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return True
    return False


def has_planned_content_markers(content: str) -> bool:
    """Check if content contains markers indicating planned/unpublished status.

    Args:
        content: Content to check

    Returns:
        True if content contains markers like 📝, "Status: Unpublished", "Draft", etc.
    """
    content_lower = content.lower()
    return any(marker in content_lower for marker in PLANNED_CONTENT_MARKERS)


# Internal path patterns for deprioritizing debug/internal files
INTERNAL_PATH_PATTERNS = (
    ".claude/",  # Claude config files
    ".cursorrules",  # Cursor config
    "/internal/",  # Internal documentation folders
    "/debug/",  # Debug folders
    "debug",  # Files containing "debug" in path
    "session",  # Session logs
)

# Score multiplier for sections from internal paths (0.1 = 90% penalty)
INTERNAL_PATH_PENALTY = 0.1


def is_internal_path(file_path: str) -> bool:
    """Check if a file path matches internal/debug patterns that should be deprioritized.

    Internal files like .claude/commands/debug.md contain session logs and debugging
    info that can pollute search results when they match common query terms.

    Args:
        file_path: File path to check

    Returns:
        True if path matches internal patterns
    """
    if not file_path:
        return False
    path_lower = file_path.lower()
    return any(pattern in path_lower for pattern in INTERNAL_PATH_PATTERNS)
