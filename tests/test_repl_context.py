"""Tests for rlm_repl_context tool - REPL Context Bridge (Phase 13)."""

import pytest

from src.models import Plan, ToolName

# Try to import RLMEngine, skip handler tests if Prisma not generated
try:
    from src.rlm_engine import RLMEngine

    PRISMA_AVAILABLE = True
except Exception:
    PRISMA_AVAILABLE = False
    RLMEngine = None  # type: ignore


@pytest.mark.skipif(not PRISMA_AVAILABLE, reason="Prisma client not generated")
class TestReplContextPlanGating:
    """Test rlm_repl_context plan gating (PRO+)."""

    @pytest.mark.asyncio
    async def test_free_plan_rejected(self):
        """FREE plan should be rejected."""
        engine = RLMEngine("test-project", plan=Plan.FREE)
        result = await engine._handle_repl_context({})
        assert "error" in result.data
        assert "Pro plan" in result.data["error"]

    @pytest.mark.asyncio
    async def test_pro_plan_allowed(self):
        """PRO plan should be allowed (may fail on no docs, but no plan error)."""
        engine = RLMEngine("test-project", plan=Plan.PRO)
        result = await engine._handle_repl_context({})
        # Either returns context or "No documentation loaded" - not a plan error
        if "error" in result.data:
            assert "Pro plan" not in result.data["error"]

    @pytest.mark.asyncio
    async def test_team_plan_allowed(self):
        """TEAM plan should be allowed."""
        engine = RLMEngine("test-project", plan=Plan.TEAM)
        result = await engine._handle_repl_context({})
        if "error" in result.data:
            assert "Pro plan" not in result.data["error"]

    @pytest.mark.asyncio
    async def test_enterprise_plan_allowed(self):
        """ENTERPRISE plan should be allowed."""
        engine = RLMEngine("test-project", plan=Plan.ENTERPRISE)
        result = await engine._handle_repl_context({})
        if "error" in result.data:
            assert "Pro plan" not in result.data["error"]


@pytest.mark.skipif(not PRISMA_AVAILABLE, reason="Prisma client not generated")
class TestReplContextWithDocs:
    """Test rlm_repl_context with loaded documentation."""

    @pytest.fixture
    def engine(self):
        """Create engine with PRO plan."""
        return RLMEngine("test-project", plan=Plan.PRO)

    async def _load_test_docs(self, engine):
        """Load minimal test documentation into engine."""
        from src.rlm_engine import DocumentationIndex, Section

        engine.index = DocumentationIndex(
            lines=[
                "# Auth Guide",
                "",
                "Authentication uses JWT tokens for API sessions.",
                "Tokens expire after 24 hours and clients refresh them securely.",
                "Signature validation runs on every protected request.",
                "",
                "# API Reference",
                "",
                "The API supports REST and GraphQL for integration clients.",
                "Authentication headers are required on all protected endpoints.",
                "Rate limiting and error codes are documented per route.",
            ],
            sections=[
                Section(
                    id="s1",
                    title="Auth Guide",
                    content=(
                        "Authentication uses JWT tokens for API sessions.\n"
                        "Tokens expire after 24 hours and clients refresh them securely.\n"
                        "Signature validation runs on every protected request."
                    ),
                    start_line=1,
                    end_line=5,
                    level=1,
                ),
                Section(
                    id="s2",
                    title="API Reference",
                    content=(
                        "The API supports REST and GraphQL for integration clients.\n"
                        "Authentication headers are required on all protected endpoints.\n"
                        "Rate limiting and error codes are documented per route."
                    ),
                    start_line=7,
                    end_line=11,
                    level=1,
                ),
            ],
            files=["docs/auth.md", "docs/api.md"],
            file_boundaries={
                "docs/auth.md": (0, 6),
                "docs/api.md": (6, 11),
            },
        )

    @pytest.mark.asyncio
    async def test_no_query_loads_all_files(self, engine):
        """Without a query, should load all files within budget."""
        await self._load_test_docs(engine)
        result = await engine._handle_repl_context({"max_tokens": 50000})
        data = result.data

        assert "context_data" in data
        assert "setup_code" in data
        assert data["context_data"]["total_files_in_project"] == 2
        assert data["context_data"]["loaded_files"] == 2
        assert "docs/auth.md" in data["context_data"]["files"]
        assert "docs/api.md" in data["context_data"]["files"]

    @pytest.mark.asyncio
    async def test_query_filters_by_relevance(self, engine):
        """With a query, should prioritize relevant files."""
        await self._load_test_docs(engine)
        # Use keyword search mode to avoid DB calls for semantic search
        result = await engine._handle_repl_context(
            {"query": "authentication JWT", "max_tokens": 50000, "search_mode": "keyword"}
        )
        data = result.data

        assert "context_data" in data
        files = data["context_data"]["files"]
        # Should load files - auth.md should have higher relevance
        assert len(files) > 0
        if "docs/auth.md" in files:
            assert "relevance" in files["docs/auth.md"]

    @pytest.mark.asyncio
    async def test_includes_helpers_by_default(self, engine):
        """Should include helper code by default."""
        await self._load_test_docs(engine)
        result = await engine._handle_repl_context({})
        data = result.data

        assert "setup_code" in data
        assert "def peek(" in data["setup_code"]
        assert "def grep(" in data["setup_code"]
        assert "def sections(" in data["setup_code"]
        assert "def files(" in data["setup_code"]

    @pytest.mark.asyncio
    async def test_exclude_helpers(self, engine):
        """include_helpers=False should return empty setup_code."""
        await self._load_test_docs(engine)
        result = await engine._handle_repl_context({"include_helpers": False})
        data = result.data

        assert data["setup_code"] == ""

    @pytest.mark.asyncio
    async def test_token_budget_respected(self, engine):
        """Should not exceed token budget."""
        await self._load_test_docs(engine)
        # Very small budget
        result = await engine._handle_repl_context({"max_tokens": 5})
        data = result.data

        # Should load at most what fits
        assert data["total_tokens"] <= 10  # Small tolerance

    @pytest.mark.asyncio
    async def test_section_map_included(self, engine):
        """Should include section map for navigation."""
        await self._load_test_docs(engine)
        result = await engine._handle_repl_context({})
        data = result.data

        sections = data["context_data"]["sections"]
        assert len(sections) == 2
        assert sections[0]["title"] == "Auth Guide"
        assert sections[1]["title"] == "API Reference"

    @pytest.mark.asyncio
    async def test_file_content_structure(self, engine):
        """File entries should have content, tokens, truncated fields."""
        await self._load_test_docs(engine)
        result = await engine._handle_repl_context({"max_tokens": 50000})
        data = result.data

        for fp, fdata in data["context_data"]["files"].items():
            assert "content" in fdata
            assert "tokens" in fdata
            assert "truncated" in fdata

    @pytest.mark.asyncio
    async def test_usage_hint_present(self, engine):
        """Should include usage hint for LLM clients."""
        await self._load_test_docs(engine)
        result = await engine._handle_repl_context({})
        data = result.data

        assert "usage_hint" in data
        assert "set_repl_context" in data["usage_hint"]

    @pytest.mark.asyncio
    async def test_no_docs_returns_error(self):
        """Engine with no loaded docs should return error."""
        engine = RLMEngine("test-project", plan=Plan.PRO)
        result = await engine._handle_repl_context({})
        assert "error" in result.data
        assert "No documentation" in result.data["error"]


@pytest.mark.skipif(not PRISMA_AVAILABLE, reason="Prisma client not generated")
class TestReplContextToolRouting:
    """Test that rlm_repl_context is properly wired in the dispatch map."""

    def test_tool_name_exists(self):
        """ToolName enum should include RLM_REPL_CONTEXT."""
        assert hasattr(ToolName, "RLM_REPL_CONTEXT")
        assert ToolName.RLM_REPL_CONTEXT.value == "rlm_repl_context"

    def test_tool_in_read_tools(self):
        """rlm_repl_context should be in READ_TOOLS set."""
        from src.rlm_engine import READ_TOOLS

        assert ToolName.RLM_REPL_CONTEXT in READ_TOOLS

    def test_plan_gate_set_exists(self):
        """REPL_CONTEXT_PLANS should exist and include PRO+."""
        from src.rlm_engine import REPL_CONTEXT_PLANS

        assert Plan.PRO in REPL_CONTEXT_PLANS
        assert Plan.TEAM in REPL_CONTEXT_PLANS
        assert Plan.ENTERPRISE in REPL_CONTEXT_PLANS
        assert Plan.FREE not in REPL_CONTEXT_PLANS
