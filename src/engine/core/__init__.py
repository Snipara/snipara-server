"""Engine core module.

This module contains core utilities and data structures for the RLM engine:
- Query classification and expansion
- Token counting
- First-query tips
- Document data structures
"""

from .document import DocumentationIndex, Section
from .query import (
    ABSTRACT_QUERY_MIN_SECTIONS,
    INTERNAL_PATH_PATTERNS,
    INTERNAL_PATH_PENALTY,
    expand_query,
    has_planned_content_markers,
    is_abstract_query,
    is_internal_path,
    is_list_query,
    is_numbered_section,
)
from .tips import (
    PLAN_FEATURE_PLANS,
    SEMANTIC_SEARCH_PLANS,
    get_first_query_tips,
)
from .tokens import count_tokens, get_encoder

__all__ = [
    # Document structures
    "Section",
    "DocumentationIndex",
    # Query utilities
    "expand_query",
    "is_abstract_query",
    "is_list_query",
    "is_numbered_section",
    "has_planned_content_markers",
    "is_internal_path",
    "ABSTRACT_QUERY_MIN_SECTIONS",
    "INTERNAL_PATH_PATTERNS",
    "INTERNAL_PATH_PENALTY",
    # Token utilities
    "get_encoder",
    "count_tokens",
    # Tips
    "get_first_query_tips",
    "SEMANTIC_SEARCH_PLANS",
    "PLAN_FEATURE_PLANS",
]
