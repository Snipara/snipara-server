"""Document data structures for the RLM engine.

This module contains the core data structures for representing
documentation sections and indices.
"""

from dataclasses import dataclass, field


@dataclass
class Section:
    """A documentation section.

    Represents a parsed section from a markdown document with metadata
    for search and display.

    Attributes:
        id: Unique identifier for this section
        title: Section heading text
        content: Full section content including the heading
        start_line: Starting line number (1-indexed)
        end_line: Ending line number (1-indexed, inclusive)
        level: Header level (1-6) from markdown heading
    """

    id: str
    title: str
    content: str
    start_line: int
    end_line: int
    level: int  # Header level (1-6)


@dataclass
class DocumentationIndex:
    """Index of loaded documentation.

    Contains all parsed documents and sections for a project,
    along with metadata for efficient search.

    Attributes:
        files: List of loaded file paths
        lines: All document lines concatenated
        sections: Parsed sections from all documents
        total_chars: Total character count across all documents
        file_boundaries: Maps file path to (start_line, end_line) in lines list
        ubiquitous_keywords: Keywords appearing in >70% of titles (excluded from
            distinctive keyword matching to avoid false relevance)
    """

    files: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    total_chars: int = 0
    # File boundary tracking: maps file path → (start_line_0indexed, end_line_0indexed_exclusive)
    file_boundaries: dict[str, tuple[int, int]] = field(default_factory=dict)
    # Auto-detected ubiquitous keywords (terms appearing in >70% of section titles)
    # These are excluded from distinctive keyword matching to avoid false relevance
    ubiquitous_keywords: set[str] = field(default_factory=set)
