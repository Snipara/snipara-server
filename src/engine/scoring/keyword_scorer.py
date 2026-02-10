"""Keyword scoring for RLM search engine.

This module provides keyword-based relevance scoring using:
- BM25-style length normalization
- Title vs content weighting
- Section level bonuses
- Phrase matching
"""

import logging
import re
from typing import TYPE_CHECKING, Protocol

from .constants import (
    GENERIC_TITLE_TERMS,
    LIST_QUERY_PATTERNS,
    NUMBERED_SECTION_PATTERNS,
    PLANNED_CONTENT_MARKERS,
    QUERY_EXPANSIONS,
    STOP_WORDS,
)
from .stemmer import stem_keyword

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SectionProtocol(Protocol):
    """Protocol for Section-like objects."""

    id: str
    title: str
    content: str
    start_line: int
    end_line: int
    level: int


def extract_keywords(query: str) -> list[str]:
    """Extract meaningful keywords from a query, filtering stop words.

    Args:
        query: The search query string.

    Returns:
        List of lowercase keywords, stop words removed.
    """
    # Split on non-alphanumeric characters
    words = re.split(r"[^\w]+", query.lower())
    # Filter stop words and very short words
    return [w for w in words if w and len(w) >= 2 and w not in STOP_WORDS]


def expand_keywords(keywords: list[str]) -> list[str]:
    """Expand abstract keywords with concrete terms for better recall.

    Args:
        keywords: Original keywords from the query.

    Returns:
        Expanded keyword list with additional terms.
    """
    expanded = list(keywords)

    for keyword in keywords:
        if keyword in QUERY_EXPANSIONS:
            for expansion in QUERY_EXPANSIONS[keyword]:
                expansion_lower = expansion.lower()
                if expansion_lower not in expanded:
                    expanded.append(expansion_lower)

        # Also check 2-word phrases
        for i in range(len(keywords) - 1):
            phrase = f"{keywords[i]} {keywords[i + 1]}"
            if phrase in QUERY_EXPANSIONS:
                for expansion in QUERY_EXPANSIONS[phrase]:
                    expansion_lower = expansion.lower()
                    if expansion_lower not in expanded:
                        expanded.append(expansion_lower)

    return expanded


def is_list_query(query: str) -> bool:
    """Detect if query is asking for a list/enumeration of items.

    Args:
        query: The search query string.

    Returns:
        True if query matches list/enumeration patterns.
    """
    query_lower = query.lower()
    return any(pattern in query_lower for pattern in LIST_QUERY_PATTERNS)


def calculate_keyword_score(
    section: SectionProtocol,
    keywords: list[str],
    is_list_query_flag: bool = False,
) -> float:
    """Calculate keyword relevance score for a section.

    Scoring factors:
    - Title matches weighted 5x (not length-normalized)
    - Content matches weighted 1x (BM25-style length normalization)
    - Section level bonus (higher level = more important)
    - Title keyword coverage boost (multi-keyword title match)
    - Exact phrase match bonus
    - List/enumeration pattern bonus (when query asks for lists)

    Args:
        section: The section to score.
        keywords: List of keywords to match.
        is_list_query_flag: Whether the query is asking for a list.

    Returns:
        Keyword relevance score (higher is better).
    """
    score = 0.0
    title_lower = section.title.lower()
    content_lower = section.content.lower()

    # BM25-style length normalization for content scoring.
    # Prevents long sections from dominating via raw keyword counts.
    # avgdl ~2000 chars is a reasonable average section length.
    content_length = len(content_lower)
    length_norm = 1.0 / (1.0 + 0.75 * (content_length / 2000.0 - 1.0))
    length_norm = max(length_norm, 0.15)  # Floor to avoid near-zero

    title_keyword_hits = 0

    for keyword in keywords:
        if len(keyword) < 2:  # Skip very short words
            continue

        stem = stem_keyword(keyword)

        # Title matches — reduced weight for generic terms
        title_count = title_lower.count(keyword)
        # Fall back to stem match for morphological variants
        # e.g. "prices" (stem "pric") matches title containing "pricing"
        if title_count == 0 and stem != keyword:
            title_count = title_lower.count(stem)
        if title_count > 0:
            title_keyword_hits += 1
            # Generic terms get 1.5x weight, specific terms get 5x
            # This prevents "Snipara tools not available" ranking above
            # actual tool documentation for "What tools does Snipara expose?"
            if keyword in GENERIC_TITLE_TERMS or stem in GENERIC_TITLE_TERMS:
                score += title_count * 1.5
            else:
                score += title_count * 5.0

        # Content matches (length-normalized)
        content_count = content_lower.count(keyword)
        if content_count == 0 and stem != keyword:
            content_count = content_lower.count(stem)
        score += content_count * length_norm

    # Bonus for higher-level sections (h1, h2 more important)
    level_bonus = max(0, 4 - section.level) * 0.5
    score += level_bonus if score > 0 else 0

    # Title keyword coverage boost: when multiple query keywords appear
    # in the section title, this section is likely a direct topical match.
    # Apply multiplicative boost proportional to the number of title hits.
    if title_keyword_hits >= 2:
        coverage_boost = 1.0 + title_keyword_hits * 2.0
        score *= coverage_boost

    # Exact phrase match bonus: if the entire query (or a significant portion)
    # appears verbatim in the title, this is very likely the right section.
    query_words = [w for w in keywords if len(w) >= 3]
    if len(query_words) >= 2:
        query_phrase = " ".join(query_words[:4])  # First 4 significant words
        if query_phrase.lower() in title_lower:
            score *= 3.0  # 3x bonus for exact phrase in title
            logger.debug(f"Exact phrase match in title: '{query_phrase}' → '{section.title}'")

    # List/enumeration boost
    if is_list_query_flag and score > 0:
        score = _apply_list_pattern_boost(section, score)

    return score


def _apply_list_pattern_boost(section: SectionProtocol, base_score: float) -> float:
    """Apply bonus for sections that contain list/enumeration patterns.

    Args:
        section: The section to check.
        base_score: The base keyword score.

    Returns:
        Boosted score if list patterns found.
    """
    combined = f"{section.title}\n{section.content}".lower()

    # Check for numbered patterns
    for pattern in NUMBERED_SECTION_PATTERNS:
        if re.search(pattern, combined, re.MULTILINE | re.IGNORECASE):
            return base_score * 1.5

    # Check for planned content markers
    for marker in PLANNED_CONTENT_MARKERS:
        if marker.lower() in combined:
            return base_score * 1.3

    return base_score


def filter_ubiquitous_keywords(
    keywords: list[str],
    ubiquitous: set[str],
) -> tuple[list[str], list[str]]:
    """Separate keywords into distinctive and ubiquitous sets.

    Ubiquitous keywords (like project names) appear in many sections
    and should not trigger "distinctive match" requirements.

    Args:
        keywords: All extracted keywords.
        ubiquitous: Set of ubiquitous keywords to filter out.

    Returns:
        Tuple of (distinctive_keywords, ubiquitous_keywords).
    """
    distinctive = []
    ubiq = []

    for kw in keywords:
        if kw in ubiquitous or stem_keyword(kw) in ubiquitous:
            ubiq.append(kw)
        else:
            distinctive.append(kw)

    return distinctive, ubiq
