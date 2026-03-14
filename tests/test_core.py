"""Tests for the engine.core module.

These tests verify the extracted core utilities work correctly.
"""

import pytest

from src.engine.core import (
    ABSTRACT_QUERY_MIN_SECTIONS,
    INTERNAL_PATH_PATTERNS,
    INTERNAL_PATH_PENALTY,
    DocumentationIndex,
    Section,
    count_tokens,
    expand_query,
    get_encoder,
    has_planned_content_markers,
    is_abstract_query,
    is_internal_path,
    is_list_query,
    is_numbered_section,
)


class TestQueryExpansion:
    """Tests for query expansion."""

    def test_expand_architecture_query(self):
        """Test that architecture queries are expanded."""
        result = expand_query("what is the architecture")
        assert "architecture" in result.lower()
        # Should contain expansion keywords
        assert len(result) > len("what is the architecture")

    def test_no_expansion_for_simple_query(self):
        """Test that simple queries are not expanded."""
        query = "how to use the API"
        result = expand_query(query)
        # No expansion terms, should return original
        assert result == query

    def test_deduplicate_expansions(self):
        """Test that duplicate expansion keywords are removed."""
        result = expand_query("architecture design")
        # Should not have duplicates
        words = result.lower().split()
        assert len(words) == len(set(words))


class TestQueryClassification:
    """Tests for query classification."""

    def test_is_abstract_query_true(self):
        """Test abstract query detection."""
        assert is_abstract_query("what is the architecture") is True
        assert is_abstract_query("explain the design") is True

    def test_is_abstract_query_false(self):
        """Test non-abstract query detection."""
        assert is_abstract_query("how to install") is False
        assert is_abstract_query("fix the bug") is False

    def test_is_list_query_true(self):
        """Test list query detection."""
        assert is_list_query("what are the steps") is True
        assert is_list_query("list all features") is True
        assert is_list_query("what are the next articles") is True

    def test_is_list_query_false(self):
        """Test non-list query detection."""
        assert is_list_query("explain the API") is False
        assert is_list_query("how to configure") is False


class TestSectionClassification:
    """Tests for section classification."""

    def test_numbered_section_detected(self):
        """Test numbered section detection."""
        assert is_numbered_section("### Article #1: Introduction", "") is True
        assert is_numbered_section("1. First Item", "") is True
        assert is_numbered_section("Issue #123: Bug fix", "") is True

    def test_non_numbered_section(self):
        """Test non-numbered sections."""
        assert is_numbered_section("Introduction", "") is False
        assert is_numbered_section("Getting Started", "") is False

    def test_planned_content_markers(self):
        """Test planned content marker detection."""
        assert has_planned_content_markers("📝 Draft article") is True
        assert has_planned_content_markers("Status: Unpublished") is True
        assert has_planned_content_markers("Published article") is False


class TestInternalPath:
    """Tests for internal path detection."""

    def test_internal_paths_detected(self):
        """Test internal path patterns."""
        assert is_internal_path(".claude/commands/debug.md") is True
        assert is_internal_path("docs/internal/notes.md") is True
        assert is_internal_path("logs/debug/session.log") is True

    def test_normal_paths_not_internal(self):
        """Test normal paths are not flagged as internal."""
        assert is_internal_path("docs/api.md") is False
        assert is_internal_path("src/main.py") is False
        assert is_internal_path("README.md") is False

    def test_empty_path(self):
        """Test empty path handling."""
        assert is_internal_path("") is False
        assert is_internal_path(None) is False  # type: ignore


class TestTokenCounting:
    """Tests for token counting."""

    def test_count_tokens_empty(self):
        """Test empty string returns 0."""
        assert count_tokens("") == 0

    def test_count_tokens_short(self):
        """Test short text returns at least 1."""
        assert count_tokens("hi") >= 1

    def test_count_tokens_longer(self):
        """Test longer text returns reasonable count."""
        text = "This is a test sentence with about forty characters."
        tokens = count_tokens(text)
        # Should be roughly 10-15 tokens for this text
        assert 5 < tokens < 20

    def test_get_encoder(self):
        """Test encoder is returned."""
        encoder = get_encoder()
        assert encoder is not None
        # Should be reusable
        encoder2 = get_encoder()
        assert encoder is encoder2


class TestDocumentStructures:
    """Tests for document data structures."""

    def test_section_creation(self):
        """Test Section dataclass creation."""
        section = Section(
            id="sec_123",
            title="Introduction",
            content="# Introduction\nHello world",
            start_line=1,
            end_line=2,
            level=1,
        )
        assert section.id == "sec_123"
        assert section.title == "Introduction"
        assert section.level == 1

    def test_documentation_index_creation(self):
        """Test DocumentationIndex dataclass creation."""
        index = DocumentationIndex()
        assert index.files == []
        assert index.sections == []
        assert index.total_chars == 0
        assert index.ubiquitous_keywords == set()

    def test_documentation_index_with_data(self):
        """Test DocumentationIndex with populated data."""
        section = Section(
            id="sec_1",
            title="Test",
            content="# Test\nContent",
            start_line=1,
            end_line=2,
            level=1,
        )
        index = DocumentationIndex(
            files=["doc.md"],
            lines=["# Test", "Content"],
            sections=[section],
            total_chars=20,
            file_boundaries={"doc.md": (0, 2)},
            ubiquitous_keywords={"test"},
        )
        assert len(index.files) == 1
        assert len(index.sections) == 1
        assert index.total_chars == 20
        assert "test" in index.ubiquitous_keywords


class TestConstants:
    """Tests for exported constants."""

    def test_abstract_query_min_sections(self):
        """Test constant value."""
        assert ABSTRACT_QUERY_MIN_SECTIONS == 5

    def test_internal_path_patterns(self):
        """Test patterns are defined."""
        assert len(INTERNAL_PATH_PATTERNS) > 0
        assert ".claude/" in INTERNAL_PATH_PATTERNS

    def test_internal_path_penalty(self):
        """Test penalty value."""
        assert 0 < INTERNAL_PATH_PENALTY < 1
