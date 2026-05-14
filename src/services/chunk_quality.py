# apps/mcp-server/src/services/chunk_quality.py
"""Chunk quality scoring for improved ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class ChunkQuality:
    """Quality metrics for a document chunk."""

    completeness: float  # 0-1: section complete vs truncated
    code_integrity: float  # 0-1: code blocks complete
    header_clarity: float  # 0-1: has clear header
    link_density: float  # 0-1: internal references
    freshness: float  # 0-1: recency of last update

    @property
    def score(self) -> float:
        """Weighted quality score."""
        return (
            self.completeness * 0.30
            + self.code_integrity * 0.25
            + self.header_clarity * 0.20
            + self.link_density * 0.10
            + self.freshness * 0.15
        )

    def to_dict(self) -> dict:
        return {
            "completeness": round(self.completeness, 3),
            "code_integrity": round(self.code_integrity, 3),
            "header_clarity": round(self.header_clarity, 3),
            "link_density": round(self.link_density, 3),
            "freshness": round(self.freshness, 3),
            "score": round(self.score, 3),
        }


def compute_chunk_quality(
    content: str,
    updated_at: datetime | None = None,
    is_truncated: bool = False,
) -> ChunkQuality:
    """
    Compute quality metrics for a chunk.

    Args:
        content: The chunk text content
        updated_at: Last modification date of source document
        is_truncated: Whether this chunk was truncated to fit budget

    Returns:
        ChunkQuality with all metrics computed
    """

    # 1. Completeness: section ends cleanly
    content_stripped = content.rstrip()
    ends_cleanly = (
        content_stripped.endswith(("```", "\n---", "\n\n"))
        or content_stripped.endswith((".", "!", "?", ":"))
        or re.search(r"\n#{1,6}\s+\S", content_stripped[-50:]) is not None
    )
    completeness = 0.3 if is_truncated else (1.0 if ends_cleanly else 0.7)

    # 2. Code integrity: all code blocks are closed
    code_block_count = content.count("```")
    code_integrity = 1.0 if code_block_count % 2 == 0 else 0.3

    # Also check for incomplete inline code
    inline_code_count = content.count("`") - (code_block_count * 3)
    if inline_code_count % 2 != 0:
        code_integrity *= 0.8

    # 3. Header clarity: starts with a markdown header
    has_header = bool(re.match(r"^#{1,6}\s+\S", content.lstrip()))
    header_clarity = 1.0 if has_header else 0.5

    # 4. Link density: ratio of markdown links (capped at 1.0)
    links = len(re.findall(r"\[.*?\]\(.*?\)", content))
    # Normalize: 0 links = 0.3, 5+ links = 1.0
    link_density = min(0.3 + (links * 0.14), 1.0)

    # 5. Freshness: days since last update
    if updated_at:
        now = datetime.now(tz=UTC)
        # Handle naive datetime
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        days_old = (now - updated_at).days
        freshness = max(0.1, 1.0 - (days_old / 365))
    else:
        freshness = 0.5  # Unknown age

    return ChunkQuality(
        completeness=completeness,
        code_integrity=code_integrity,
        header_clarity=header_clarity,
        link_density=link_density,
        freshness=freshness,
    )


def is_high_quality(quality: ChunkQuality, threshold: float = 0.7) -> bool:
    """Check if a chunk meets quality threshold."""
    return quality.score >= threshold


def quality_penalty(quality: ChunkQuality) -> float:
    """
    Compute a penalty multiplier for low-quality chunks.

    Returns:
        Multiplier between 0.5 and 1.0
    """
    score = quality.score
    if score >= 0.8:
        return 1.0
    elif score >= 0.6:
        return 0.9
    elif score >= 0.4:
        return 0.75
    else:
        return 0.5
