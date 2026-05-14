"""Tests for rlm_context_query tool - Token budgeting and context optimization."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.engine.core import DocumentationIndex
from src.models import (
    ContextQueryParams,
    ContextQueryResult,
    ContextSection,
    GetChunkResult,
    Plan,
    SearchMode,
    ToolName,
)
from src.rlm_engine import (
    RLMEngine,
    Section,
    _is_simple_comparison_query,
    _should_auto_decompose,
    count_tokens,
    get_encoder,
)


class TestTokenCounting:
    """Tests for tiktoken integration."""

    def test_count_tokens_simple(self):
        """Test token counting for simple text."""
        text = "Hello, world!"
        tokens = count_tokens(text)
        assert tokens > 0
        assert tokens < 10  # Should be ~4 tokens

    def test_count_tokens_empty(self):
        """Test token counting for empty string."""
        assert count_tokens("") == 0

    def test_count_tokens_long_text(self):
        """Test token counting for longer text."""
        text = "This is a longer piece of text that should have more tokens. " * 10
        tokens = count_tokens(text)
        assert tokens > 50
        assert tokens < 200

    def test_encoder_singleton(self):
        """Test that encoder is lazily initialized and reused."""
        enc1 = get_encoder()
        enc2 = get_encoder()
        assert enc1 is enc2  # Same instance


class TestContextQueryParams:
    """Tests for ContextQueryParams validation."""

    def test_default_values(self):
        """Test default parameter values."""
        params = ContextQueryParams(query="test query")
        assert params.query == "test query"
        assert params.max_tokens == 4000
        assert params.search_mode == SearchMode.KEYWORD
        assert params.include_metadata is True

    def test_custom_values(self):
        """Test custom parameter values."""
        params = ContextQueryParams(
            query="How does auth work?",
            max_tokens=8000,
            search_mode=SearchMode.SEMANTIC,
            include_metadata=False,
        )
        assert params.query == "How does auth work?"
        assert params.max_tokens == 8000
        assert params.search_mode == SearchMode.SEMANTIC
        assert params.include_metadata is False

    def test_max_tokens_bounds(self):
        """Test max_tokens validation bounds."""
        # Valid minimum
        params = ContextQueryParams(query="test", max_tokens=100)
        assert params.max_tokens == 100

        # Valid maximum
        params = ContextQueryParams(query="test", max_tokens=100000)
        assert params.max_tokens == 100000

        # Below minimum should fail
        with pytest.raises(ValueError):
            ContextQueryParams(query="test", max_tokens=50)

        # Above maximum should fail
        with pytest.raises(ValueError):
            ContextQueryParams(query="test", max_tokens=200000)


class TestContextSection:
    """Tests for ContextSection model."""

    def test_section_creation(self):
        """Test creating a context section."""
        section = ContextSection(
            title="Authentication",
            content="This section covers authentication...",
            file="docs/auth.md",
            lines=(10, 50),
            relevance_score=0.85,
            token_count=150,
            truncated=False,
        )
        assert section.title == "Authentication"
        assert section.file == "docs/auth.md"
        assert section.lines == (10, 50)
        assert section.relevance_score == 0.85
        assert section.token_count == 150
        assert section.truncated is False

    def test_truncated_section(self):
        """Test creating a truncated section."""
        section = ContextSection(
            title="Long Section",
            content="Content that was truncated...",
            file="docs/long.md",
            lines=(1, 1000),
            relevance_score=0.92,
            token_count=500,
            truncated=True,
        )
        assert section.truncated is True

    def test_legacy_aliases_are_exposed(self):
        """Test that validated sections still expose legacy accessors."""
        section = ContextSection(
            title="Legacy-compatible section",
            content="Legacy consumers still read tokens and line attrs.",
            file="docs/legacy.md",
            lines=(12, 34),
            relevance_score=0.75,
            token_count=120,
            truncated=False,
        )

        assert section.start_line == 12
        assert section.end_line == 34
        assert section.tokens == 120

    def test_legacy_payload_is_normalized(self):
        """Test coercion from legacy payload fields."""
        section = ContextSection(
            title="Legacy payload",
            content="Normalizes fields from older callers.",
            file=None,
            start_line=7,
            end_line=9,
            relevance_score=100.0,
            tokens=24,
        )

        assert section.file == "(unknown)"
        assert section.lines == (7, 9)
        assert section.start_line == 7
        assert section.end_line == 9
        assert section.token_count == 24
        assert section.tokens == 24
        assert section.relevance_score == 1.0

    def test_relevance_score_bounds(self):
        """Test relevance score validation."""
        # Valid scores
        ContextSection(
            title="Test",
            content="content",
            file="test.md",
            lines=(1, 10),
            relevance_score=0.0,
            token_count=10,
        )
        ContextSection(
            title="Test",
            content="content",
            file="test.md",
            lines=(1, 10),
            relevance_score=1.0,
            token_count=10,
        )

        # Invalid scores
        with pytest.raises(ValueError):
            ContextSection(
                title="Test",
                content="content",
                file="test.md",
                lines=(1, 10),
                relevance_score=-0.1,
                token_count=10,
            )
        with pytest.raises(ValueError):
            ContextSection(
                title="Test",
                content="content",
                file="test.md",
                lines=(1, 10),
                relevance_score=1.5,
                token_count=10,
            )


class TestContextQueryResult:
    """Tests for ContextQueryResult model."""

    def test_empty_result(self):
        """Test creating an empty result."""
        result = ContextQueryResult(
            sections=[],
            total_tokens=0,
            max_tokens=4000,
            query="no matches",
            search_mode=SearchMode.KEYWORD,
        )
        assert len(result.sections) == 0
        assert result.total_tokens == 0
        assert result.session_context_included is False
        assert len(result.suggestions) == 0
        assert result.narrower_queries == []
        assert result.fast_context_parameters == {}
        assert result.recovery_guidance == []

    def test_result_with_sections(self):
        """Test creating a result with sections."""
        section = ContextSection(
            title="Test",
            content="content",
            file="test.md",
            lines=(1, 10),
            relevance_score=0.8,
            token_count=50,
        )
        result = ContextQueryResult(
            sections=[section],
            total_tokens=50,
            max_tokens=4000,
            query="test query",
            search_mode=SearchMode.KEYWORD,
            session_context_included=True,
            suggestions=["Other Section (score: 5.0)"],
        )
        assert len(result.sections) == 1
        assert result.total_tokens == 50
        assert result.session_context_included is True
        assert len(result.suggestions) == 1


class TestGetChunk:
    """Tests for pass-by-reference chunk retrieval."""

    def test_not_found_result_supports_message(self):
        """Missing chunks should return a structured result instead of a validation error."""
        result = GetChunkResult(
            chunk_id="chunk_missing",
            found=False,
            message="Chunk not found or expired.",
        )

        assert result.found is False
        assert result.title == ""
        assert result.content == ""
        assert result.message == "Chunk not found or expired."

    @pytest.mark.asyncio
    async def test_get_chunk_returns_structured_not_found(self):
        """The handler should not raise when a chunk ID cannot be resolved."""
        engine = RLMEngine("proj_test")
        engine.index = DocumentationIndex()

        result = await engine._handle_get_chunk({"chunk_id": "chunk_missing"})

        assert result.data["found"] is False
        assert "not found" in result.data["message"].lower()

    @pytest.mark.asyncio
    async def test_get_chunk_resolves_stateless_reference_from_index(self):
        """A new engine instance should resolve chunk refs without the original in-memory cache."""
        section = Section(
            id="[AUTH]",
            title="Authentication",
            content="# Authentication\n\nUse API keys for MCP calls.",
            start_line=1,
            end_line=3,
            level=1,
        )
        index = DocumentationIndex(
            files=["docs/auth.md"],
            sections=[section],
            file_boundaries={"docs/auth.md": (0, 3)},
        )

        first_engine = RLMEngine("proj_test")
        context_section = ContextSection(
            title="Authentication",
            content=section.content,
            file="docs/auth.md",
            lines=(1, 3),
            relevance_score=0.95,
            token_count=count_tokens(section.content),
        )
        chunk_id = first_engine._cache_context_section_ref(context_section)

        second_engine = RLMEngine("proj_test")
        second_engine.index = index
        result = await second_engine._handle_get_chunk({"chunk_id": chunk_id})

        assert result.data["found"] is True
        assert result.data["title"] == "Authentication"
        assert result.data["content"] == section.content
        assert result.data["file"] == "docs/auth.md"

    @pytest.mark.asyncio
    async def test_get_chunk_resolves_legacy_reference_from_index(self):
        """A new engine should still resolve pre-stateless 12-hex chunk refs."""
        section = Section(
            id="[AUTH]",
            title="Authentication",
            content="# Authentication\n\nUse API keys for MCP calls.",
            start_line=1,
            end_line=3,
            level=1,
        )
        index = DocumentationIndex(
            files=["docs/auth.md"],
            sections=[section],
            file_boundaries={"docs/auth.md": (0, 3)},
        )

        engine = RLMEngine("proj_test")
        engine.index = index
        legacy_chunk_id = engine._generate_legacy_chunk_ref_id_for_parts(
            file_path="docs/auth.md",
            title="Authentication",
        )

        assert legacy_chunk_id.startswith("chunk_")
        assert len(legacy_chunk_id) == len("chunk_") + 12

        result = await engine._handle_get_chunk({"chunk_id": legacy_chunk_id})

        assert result.data["found"] is True
        assert result.data["chunk_id"] == legacy_chunk_id
        assert result.data["title"] == "Authentication"
        assert result.data["content"] == section.content
        assert result.data["file"] == "docs/auth.md"


class TestAutoDecomposeHeuristics:
    """Tests for auto-decomposition gating."""

    def test_short_binary_comparison_stays_direct(self):
        """Short comparison queries should not auto-decompose."""
        query = "CE community edition vs EE enterprise edition licensing"
        assert _is_simple_comparison_query(query) is True
        assert _should_auto_decompose(query) is False

    def test_long_comparison_query_still_decomposes(self):
        """Longer comparison queries with multiple facets should still decompose."""
        query = (
            "Compare community edition and enterprise edition licensing, support obligations, "
            "deployment constraints, and redistribution rights"
        )
        assert _is_simple_comparison_query(query) is False
        assert _should_auto_decompose(query) is True

    def test_multi_question_query_still_decomposes(self):
        """Multiple questions should still trigger decomposition."""
        query = "How does auth work? What security measures are in place?"
        assert _should_auto_decompose(query) is True


class TestContextQueryCaching:
    """Tests for remote exact-query caching on rlm_context_query."""

    @staticmethod
    def _build_engine() -> RLMEngine:
        engine = RLMEngine("test-project", plan=Plan.TEAM)
        section = Section(
            id="[LICENSING]",
            title="Community Edition License",
            content=(
                "Community edition licensing terms and redistribution notes. "
                "This section documents what users can ship, modify, and host. "
                "It also explains support boundaries, redistribution limits, "
                "and validation behavior for community deployments."
            ),
            start_line=1,
            end_line=12,
            level=1,
        )
        engine.index = DocumentationIndex(
            files=["docs/licensing.md"],
            lines=section.content.splitlines(),
            sections=[section],
            total_chars=len(section.content),
            file_boundaries={"docs/licensing.md": (0, max(len(section.content.splitlines()), 1))},
        )
        return engine

    @pytest.mark.asyncio
    async def test_repeat_query_hits_cache(self, monkeypatch):
        """Second identical query should reuse the cached result."""
        engine_first = self._build_engine()
        engine_second = self._build_engine()
        cached_result: dict | None = None

        async def cache_get(_query: str, _max_tokens: int, variant: str | None = None):
            assert variant is not None
            return cached_result

        async def cache_set(
            _query: str,
            _max_tokens: int,
            result: dict,
            ttl: int | None = None,
            variant: str | None = None,
        ) -> bool:
            nonlocal cached_result
            assert ttl is None
            assert variant is not None
            cached_result = result
            return True

        fake_cache = SimpleNamespace(
            get=AsyncMock(side_effect=cache_get),
            set=AsyncMock(side_effect=cache_set),
            invalidate=AsyncMock(return_value=1),
        )
        monkeypatch.setattr("src.rlm_engine.get_cache", lambda *args, **kwargs: fake_cache)
        monkeypatch.setattr(
            "src.rlm_engine.get_db",
            AsyncMock(side_effect=RuntimeError("database not available in cache test")),
        )

        first_score = AsyncMock(return_value=[(engine_first.index.sections[0], 87.0)])
        second_score = AsyncMock(side_effect=AssertionError("cache miss recomputed scoring"))
        monkeypatch.setattr(engine_first, "_score_sections", first_score)
        monkeypatch.setattr(engine_second, "_score_sections", second_score)

        params = {
            "query": "community edition licensing",
            "max_tokens": 4000,
            "search_mode": "hybrid",
            "include_shared_context": False,
            "prefer_summaries": False,
        }

        first = await engine_first._handle_context_query(params)
        assert first_score.await_count == 1
        assert fake_cache.set.await_count == 1
        assert first.data["sections"][0]["title"] == "Community Edition License"

        second = await engine_second._handle_context_query(params)
        assert fake_cache.get.await_count == 2
        assert fake_cache.set.await_count == 1
        assert second.data["sections"][0]["title"] == "Community Edition License"
        assert second.data["timing"]["cache_lookup_ms"] >= 0

    @pytest.mark.asyncio
    async def test_reference_mode_skips_result_cache(self, monkeypatch):
        """Pass-by-reference mode should bypass result caching."""
        engine = self._build_engine()
        fake_cache = SimpleNamespace(
            get=AsyncMock(return_value=None),
            set=AsyncMock(return_value=True),
            invalidate=AsyncMock(return_value=1),
        )
        monkeypatch.setattr("src.rlm_engine.get_cache", lambda *args, **kwargs: fake_cache)
        monkeypatch.setattr(
            "src.rlm_engine.get_db",
            AsyncMock(side_effect=RuntimeError("database not available in reference cache test")),
        )
        monkeypatch.setattr(
            engine,
            "_score_sections",
            AsyncMock(return_value=[(engine.index.sections[0], 87.0)]),
        )

        result = await engine._handle_context_query(
            {
                "query": "community edition licensing",
                "max_tokens": 4000,
                "search_mode": "hybrid",
                "include_shared_context": False,
                "prefer_summaries": False,
                "return_references": True,
            }
        )

        assert result.data["references_mode"] is True
        fake_cache.get.assert_not_called()
        fake_cache.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_document_invalidates_query_cache(self, monkeypatch):
        """Document mutations should clear the remote context-query cache."""
        engine = RLMEngine("test-project", plan=Plan.TEAM)
        engine.index = DocumentationIndex()
        engine._chunks_available = True

        fake_cache = SimpleNamespace(
            get=AsyncMock(return_value=None),
            set=AsyncMock(return_value=True),
            invalidate=AsyncMock(return_value=3),
        )
        fake_db = SimpleNamespace(
            document=SimpleNamespace(
                find_first=AsyncMock(return_value=None),
                create=AsyncMock(return_value=None),
            ),
            documentchunk=SimpleNamespace(delete_many=AsyncMock(return_value=None)),
        )

        monkeypatch.setattr("src.rlm_engine.get_cache", lambda *args, **kwargs: fake_cache)
        monkeypatch.setattr("src.rlm_engine.get_db", AsyncMock(return_value=fake_db))

        result = await engine._handle_upload_document(
            {
                "path": "docs/new-license.md",
                "content": "# New License\nTerms and conditions.",
            }
        )

        assert result.data["action"] == "created"
        assert engine.index is None
        assert engine._chunks_available is None
        fake_cache.invalidate.assert_awaited_once()


class TestCodeGraphHybridContext:
    """Tests for v2 structural graph summaries inside rlm_context_query."""

    @pytest.mark.asyncio
    async def test_structural_query_inlines_code_graph_summary(self, monkeypatch):
        """Structural queries should inline a concise graph summary plus the tool hint."""
        engine = RLMEngine("test-project", plan=Plan.FREE)
        doc_section = Section(
            id="[CODE-GRAPH]",
            title="Code Graph Workflow",
            content=(
                "Use rlm_code_callers for reverse call lookups and rlm_code_neighbors "
                "for local structural traversal. This reference explains how the "
                "persisted graph complements document retrieval, when callers and "
                "neighbors are the right tool, and why direct symbol traversal is "
                "more precise than embeddings alone for repository structure questions."
            ),
            start_line=1,
            end_line=8,
            level=1,
        )
        engine.index = DocumentationIndex(
            files=["docs/reference/CODE_GRAPH.md"],
            lines=doc_section.content.splitlines(),
            sections=[doc_section],
            total_chars=len(doc_section.content),
            file_boundaries={"docs/reference/CODE_GRAPH.md": (0, 1)},
        )

        class FakeGraphService:
            async def get_callers(self, **kwargs):
                assert kwargs["qualified_name"] == "src.rlm_engine.RLMEngine._handle_context_query"
                return {
                    "matched_targets": [
                        {
                            "qualified_name": "src.rlm_engine.RLMEngine._handle_context_query",
                            "kind": "METHOD",
                            "file_path": "src/rlm_engine.py",
                            "start_line": 120,
                        }
                    ],
                    "callers": [
                        {
                            "qualified_name": "src.rlm_engine.RLMEngine.run",
                            "kind": "METHOD",
                            "file_path": "src/rlm_engine.py",
                            "start_line": 88,
                        }
                    ],
                    "depth": 1,
                    "total_callers": 1,
                }

        monkeypatch.setattr(
            engine,
            "_score_sections",
            AsyncMock(return_value=[(doc_section, 91.0)]),
        )
        monkeypatch.setattr(
            engine, "_get_code_graph_query_service", AsyncMock(return_value=FakeGraphService())
        )
        monkeypatch.setattr(
            "src.rlm_engine.get_db",
            AsyncMock(side_effect=RuntimeError("database not available in hybrid test")),
        )

        result = await engine._handle_context_query(
            {
                "query": "who calls src.rlm_engine.RLMEngine._handle_context_query?",
                "max_tokens": 4000,
                "search_mode": "hybrid",
                "include_shared_context": False,
                "prefer_summaries": False,
            }
        )

        assert result.data["graph_hybrid_used"] is True
        assert result.data["graph_context_tool"] == "rlm_code_callers"
        assert result.data["recommended_tool"] == "rlm_code_callers"
        assert result.data["sections"][0]["title"].startswith("Code Graph: Callers of")
        assert "Reverse callers found: 1" in result.data["sections"][0]["content"]
        assert "src.rlm_engine.RLMEngine.run" in result.data["sections"][0]["content"]
        assert result.data["sections"][1]["title"] == "Code Graph Workflow"

    @pytest.mark.asyncio
    async def test_narrative_query_keeps_graph_hybrid_disabled(self, monkeypatch):
        """Non-structural queries should remain document-only."""
        engine = RLMEngine("test-project", plan=Plan.FREE)
        section = Section(
            id="[LICENSING]",
            title="Community Edition License",
            content=(
                "Community edition licensing terms and redistribution notes. "
                "This section explains what users can ship, what support is "
                "included, and which redistribution scenarios are allowed "
                "for self-hosted and managed deployments."
            ),
            start_line=1,
            end_line=6,
            level=1,
        )
        engine.index = DocumentationIndex(
            files=["docs/licensing.md"],
            lines=section.content.splitlines(),
            sections=[section],
            total_chars=len(section.content),
            file_boundaries={"docs/licensing.md": (0, 1)},
        )

        monkeypatch.setattr(engine, "_score_sections", AsyncMock(return_value=[(section, 87.0)]))
        monkeypatch.setattr(
            "src.rlm_engine.get_db",
            AsyncMock(side_effect=RuntimeError("database not available in narrative test")),
        )

        result = await engine._handle_context_query(
            {
                "query": "community edition licensing",
                "max_tokens": 4000,
                "search_mode": "hybrid",
                "include_shared_context": False,
                "prefer_summaries": False,
            }
        )

        assert result.data["graph_hybrid_used"] is False
        assert result.data["graph_context_tool"] is None
        assert result.data["graph_context_summary"] is None
        assert result.data["sections"][0]["title"] == "Community Edition License"

    @pytest.mark.asyncio
    async def test_mixed_code_query_keeps_docs_first_and_appends_graph_context(self, monkeypatch):
        """Mixed implementation questions should stay doc-first while appending graph context."""
        engine = RLMEngine("test-project", plan=Plan.FREE)
        section = Section(
            id="[HANDLER]",
            title="Request Handler Flow",
            content=(
                "The handler prepares retrieval settings, loads shared context when allowed, "
                "and only then builds the final answer payload. This section explains the "
                "high-level flow around request handling and answer assembly."
            ),
            start_line=1,
            end_line=6,
            level=1,
        )
        engine.index = DocumentationIndex(
            files=["docs/reference/HANDLERS.md"],
            lines=section.content.splitlines(),
            sections=[section],
            total_chars=len(section.content),
            file_boundaries={"docs/reference/HANDLERS.md": (0, 1)},
        )

        class FakeGraphService:
            async def get_neighbors(self, **kwargs):
                assert kwargs["qualified_name"] == "src.rlm_engine.RLMEngine._handle_context_query"
                return {
                    "matched_targets": [
                        {
                            "qualified_name": "src.rlm_engine.RLMEngine._handle_context_query",
                            "kind": "METHOD",
                            "file_path": "src/rlm_engine.py",
                            "start_line": 120,
                        }
                    ],
                    "nodes": [
                        {
                            "qualified_name": "src.rlm_engine.RLMEngine.run",
                            "kind": "METHOD",
                            "file_path": "src/rlm_engine.py",
                            "start_line": 88,
                        }
                    ],
                    "edges": [
                        {
                            "from_qualified_name": "src.rlm_engine.RLMEngine.run",
                            "to_qualified_name": "src.rlm_engine.RLMEngine._handle_context_query",
                            "kind": "CALLS",
                        }
                    ],
                    "depth": 2,
                }

        monkeypatch.setattr(engine, "_score_sections", AsyncMock(return_value=[(section, 88.0)]))
        monkeypatch.setattr(
            engine, "_get_code_graph_query_service", AsyncMock(return_value=FakeGraphService())
        )
        monkeypatch.setattr(
            "src.rlm_engine.get_db",
            AsyncMock(side_effect=RuntimeError("database not available in mixed hybrid test")),
        )

        result = await engine._handle_context_query(
            {
                "query": (
                    "Explain how src.rlm_engine.RLMEngine._handle_context_query works during "
                    "request handling"
                ),
                "max_tokens": 4000,
                "search_mode": "hybrid",
                "include_shared_context": False,
                "prefer_summaries": False,
            }
        )

        assert result.data["graph_hybrid_used"] is True
        assert result.data["graph_context_tool"] == "rlm_code_neighbors"
        assert result.data["recommended_tool"] == "rlm_code_neighbors"
        assert result.data["sections"][0]["title"] == "Request Handler Flow"
        assert result.data["sections"][1]["title"].startswith("Code Graph: Neighborhood of")


class TestKeywordScoring:
    """Tests for keyword-based relevance scoring."""

    @pytest.fixture
    def engine(self):
        """Create an engine for testing."""
        return RLMEngine("test-project")

    def test_title_weight(self, engine):
        """Test that title matches are weighted higher."""
        section_title_match = Section(
            id="[AUTH]",
            title="Authentication Flow",
            content="Some content about login",
            start_line=1,
            end_line=10,
            level=1,
        )
        section_content_match = Section(
            id="[OTHER]",
            title="Other Section",
            content="Content about authentication and login flow",
            start_line=11,
            end_line=20,
            level=2,
        )

        keywords = ["authentication", "flow"]
        score_title = engine._calculate_keyword_score(section_title_match, keywords)
        score_content = engine._calculate_keyword_score(section_content_match, keywords)

        # Title match should score higher
        assert score_title > score_content

    def test_level_bonus(self, engine):
        """Test that higher-level sections get bonus points."""
        section_h1 = Section(
            id="[H1]",
            title="Main Topic",
            content="Content with keyword",
            start_line=1,
            end_line=10,
            level=1,
        )
        section_h3 = Section(
            id="[H3]",
            title="Main Topic",
            content="Content with keyword",
            start_line=1,
            end_line=10,
            level=3,
        )

        keywords = ["keyword"]
        score_h1 = engine._calculate_keyword_score(section_h1, keywords)
        score_h3 = engine._calculate_keyword_score(section_h3, keywords)

        # H1 should score higher than H3
        assert score_h1 > score_h3

    def test_no_match_zero_score(self, engine):
        """Test that non-matching sections get zero score."""
        section = Section(
            id="[TEST]",
            title="Unrelated Topic",
            content="Nothing relevant here",
            start_line=1,
            end_line=10,
            level=2,
        )

        keywords = ["authentication", "login"]
        score = engine._calculate_keyword_score(section, keywords)

        assert score == 0.0


class TestSmartTruncation:
    """Tests for smart content truncation."""

    @pytest.fixture
    def engine(self):
        """Create an engine for testing."""
        return RLMEngine("test-project")

    def test_no_truncation_needed(self, engine):
        """Test that short content is not truncated."""
        content = "Short content."
        result = engine._smart_truncate(content, 100)
        assert result == content
        assert "..." not in result

    def test_truncate_at_sentence(self, engine):
        """Test that truncation happens at sentence boundary."""
        content = "First sentence. Second sentence. Third sentence that is longer."
        # Set a token limit that will require truncation
        result = engine._smart_truncate(content, 10)

        # Should end with ... and at a sentence boundary
        assert result.endswith("...")
        # Should preserve at least some content
        assert len(result) > 10

    def test_truncate_preserves_meaning(self, engine):
        """Test that truncation preserves as much content as possible."""
        content = "Important information here. More details follow. Even more content."
        result = engine._smart_truncate(content, 8)

        # Should contain the beginning of the content
        assert result.startswith("Important")
        assert result.endswith("...")


class TestSearchModeEnum:
    """Tests for SearchMode enum."""

    def test_valid_modes(self):
        """Test valid search modes."""
        assert SearchMode.KEYWORD.value == "keyword"
        assert SearchMode.SEMANTIC.value == "semantic"
        assert SearchMode.HYBRID.value == "hybrid"

    def test_enum_conversion(self):
        """Test converting strings to SearchMode."""
        assert SearchMode("keyword") == SearchMode.KEYWORD
        assert SearchMode("semantic") == SearchMode.SEMANTIC
        assert SearchMode("hybrid") == SearchMode.HYBRID

    def test_invalid_mode(self):
        """Test that invalid mode raises error."""
        with pytest.raises(ValueError):
            SearchMode("invalid")


class TestToolNameEnum:
    """Tests for ToolName enum including new context_query."""

    def test_context_query_in_enum(self):
        """Test that rlm_context_query is in the ToolName enum."""
        assert ToolName.RLM_CONTEXT_QUERY.value == "rlm_context_query"

    def test_all_tools_present(self):
        """Test that all expected tools are present."""
        expected_tools = [
            "rlm_ask",
            "rlm_search",
            "rlm_inject",
            "rlm_context",
            "rlm_clear_context",
            "rlm_stats",
            "rlm_sections",
            "rlm_read",
            "rlm_context_query",
        ]
        tool_values = [t.value for t in ToolName]
        for tool in expected_tools:
            assert tool in tool_values, f"Missing tool: {tool}"
