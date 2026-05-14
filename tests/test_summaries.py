"""Tests for summary storage tools (rlm_store_summary, rlm_get_summaries, rlm_delete_summary).

These tests focus on model validation. Database-dependent handler tests
are skipped when Prisma is not generated.
"""

import pytest
from datetime import datetime
from src.models import (
    Plan,
    SummaryType,
    StoreSummaryParams,
    StoreSummaryResult,
    GetSummariesParams,
    GetSummariesResult,
    SummaryInfo,
    DeleteSummaryParams,
    DeleteSummaryResult,
)

# Try to import RLMEngine, skip handler tests if Prisma not generated
try:
    from src.rlm_engine import RLMEngine
    PRISMA_AVAILABLE = True
except RuntimeError:
    PRISMA_AVAILABLE = False
    RLMEngine = None  # type: ignore


class TestSummaryTypeEnum:
    """Test SummaryType enum values."""

    def test_concise_type(self):
        """Test concise summary type."""
        assert SummaryType.CONCISE.value == "concise"

    def test_detailed_type(self):
        """Test detailed summary type."""
        assert SummaryType.DETAILED.value == "detailed"

    def test_technical_type(self):
        """Test technical summary type."""
        assert SummaryType.TECHNICAL.value == "technical"

    def test_keywords_type(self):
        """Test keywords summary type."""
        assert SummaryType.KEYWORDS.value == "keywords"

    def test_custom_type(self):
        """Test custom summary type."""
        assert SummaryType.CUSTOM.value == "custom"

    def test_enum_conversion_concise(self):
        """Test string to enum conversion for concise."""
        assert SummaryType("concise") == SummaryType.CONCISE

    def test_enum_conversion_detailed(self):
        """Test string to enum conversion for detailed."""
        assert SummaryType("detailed") == SummaryType.DETAILED

    def test_enum_conversion_technical(self):
        """Test string to enum conversion for technical."""
        assert SummaryType("technical") == SummaryType.TECHNICAL

    def test_invalid_type_raises(self):
        """Test invalid summary type raises error."""
        with pytest.raises(ValueError):
            SummaryType("invalid")


class TestStoreSummaryParams:
    """Test StoreSummaryParams validation."""

    def test_required_fields(self):
        """Test required fields validation."""
        params = StoreSummaryParams(
            document_path="docs/auth.md",
            summary="This document explains authentication.",
        )
        assert params.document_path == "docs/auth.md"
        assert params.summary == "This document explains authentication."
        assert params.summary_type == SummaryType.CONCISE  # default

    def test_default_summary_type(self):
        """Test default summary type is CONCISE."""
        params = StoreSummaryParams(
            document_path="docs/test.md",
            summary="Test summary",
        )
        assert params.summary_type == SummaryType.CONCISE

    def test_custom_summary_type(self):
        """Test custom summary type."""
        params = StoreSummaryParams(
            document_path="docs/test.md",
            summary="Technical summary",
            summary_type=SummaryType.TECHNICAL,
        )
        assert params.summary_type == SummaryType.TECHNICAL

    def test_section_id_field(self):
        """Test optional section_id field."""
        params = StoreSummaryParams(
            document_path="docs/auth.md",
            summary="Auth section summary",
            section_id="auth-flow",
        )
        assert params.section_id == "auth-flow"

    def test_line_range_fields(self):
        """Test optional line_start and line_end fields."""
        params = StoreSummaryParams(
            document_path="docs/auth.md",
            summary="Section summary",
            line_start=10,
            line_end=50,
        )
        assert params.line_start == 10
        assert params.line_end == 50

    def test_generated_by_field(self):
        """Test optional generated_by field."""
        params = StoreSummaryParams(
            document_path="docs/auth.md",
            summary="Summary text",
            generated_by="claude-3.5-sonnet",
        )
        assert params.generated_by == "claude-3.5-sonnet"

    def test_all_optional_fields(self):
        """Test all optional fields together."""
        params = StoreSummaryParams(
            document_path="docs/auth.md",
            summary="Auth section summary",
            summary_type=SummaryType.TECHNICAL,
            section_id="auth-flow",
            line_start=10,
            line_end=50,
            generated_by="claude-3.5-sonnet",
        )
        assert params.document_path == "docs/auth.md"
        assert params.summary == "Auth section summary"
        assert params.summary_type == SummaryType.TECHNICAL
        assert params.section_id == "auth-flow"
        assert params.line_start == 10
        assert params.line_end == 50
        assert params.generated_by == "claude-3.5-sonnet"

    def test_empty_summary_rejected(self):
        """Test empty summary is rejected."""
        with pytest.raises(ValueError):
            StoreSummaryParams(document_path="docs/test.md", summary="")


class TestGetSummariesParams:
    """Test GetSummariesParams validation."""

    def test_default_values(self):
        """Test default parameter values."""
        params = GetSummariesParams()
        assert params.document_path is None
        assert params.summary_type is None
        assert params.section_id is None
        assert params.include_content is True

    def test_filter_by_document_path(self):
        """Test filtering by document path."""
        params = GetSummariesParams(document_path="docs/auth.md")
        assert params.document_path == "docs/auth.md"

    def test_filter_by_summary_type(self):
        """Test filtering by summary type."""
        params = GetSummariesParams(summary_type=SummaryType.DETAILED)
        assert params.summary_type == SummaryType.DETAILED

    def test_filter_by_section_id(self):
        """Test filtering by section ID."""
        params = GetSummariesParams(section_id="auth-flow")
        assert params.section_id == "auth-flow"

    def test_include_content_false(self):
        """Test include_content set to False."""
        params = GetSummariesParams(include_content=False)
        assert params.include_content is False

    def test_all_filters(self):
        """Test all filter options together."""
        params = GetSummariesParams(
            document_path="docs/auth.md",
            summary_type=SummaryType.DETAILED,
            section_id="auth-flow",
            include_content=False,
        )
        assert params.document_path == "docs/auth.md"
        assert params.summary_type == SummaryType.DETAILED
        assert params.section_id == "auth-flow"
        assert params.include_content is False


class TestDeleteSummaryParams:
    """Test DeleteSummaryParams validation."""

    def test_delete_by_id(self):
        """Test delete by summary ID."""
        params = DeleteSummaryParams(summary_id="sum_123")
        assert params.summary_id == "sum_123"
        assert params.document_path is None
        assert params.summary_type is None

    def test_delete_by_path(self):
        """Test delete by document path."""
        params = DeleteSummaryParams(document_path="docs/auth.md")
        assert params.document_path == "docs/auth.md"
        assert params.summary_id is None

    def test_delete_by_type(self):
        """Test delete by summary type."""
        params = DeleteSummaryParams(summary_type=SummaryType.CONCISE)
        assert params.summary_type == SummaryType.CONCISE
        assert params.summary_id is None

    def test_delete_all_criteria(self):
        """Test multiple delete criteria."""
        params = DeleteSummaryParams(
            document_path="docs/auth.md",
            summary_type=SummaryType.TECHNICAL,
        )
        assert params.document_path == "docs/auth.md"
        assert params.summary_type == SummaryType.TECHNICAL


class TestStoreSummaryResult:
    """Test StoreSummaryResult model."""

    def test_created_result(self):
        """Test StoreSummaryResult for created summary."""
        result = StoreSummaryResult(
            summary_id="sum_123",
            document_path="docs/auth.md",
            summary_type=SummaryType.CONCISE,
            token_count=150,
            created=True,
            message="Summary created successfully (150 tokens)",
        )
        assert result.summary_id == "sum_123"
        assert result.document_path == "docs/auth.md"
        assert result.summary_type == SummaryType.CONCISE
        assert result.token_count == 150
        assert result.created is True
        assert "created" in result.message

    def test_updated_result(self):
        """Test StoreSummaryResult for updated summary."""
        result = StoreSummaryResult(
            summary_id="sum_123",
            document_path="docs/auth.md",
            summary_type=SummaryType.DETAILED,
            token_count=300,
            created=False,
            message="Summary updated successfully (300 tokens)",
        )
        assert result.created is False
        assert result.token_count == 300

    def test_model_dump(self):
        """Test StoreSummaryResult model_dump."""
        result = StoreSummaryResult(
            summary_id="sum_123",
            document_path="docs/test.md",
            summary_type=SummaryType.TECHNICAL,
            token_count=200,
            created=True,
            message="Test",
        )
        data = result.model_dump()
        assert data["summary_id"] == "sum_123"
        assert data["summary_type"] == "technical"


class TestSummaryInfo:
    """Test SummaryInfo model."""

    def test_basic_summary_info(self):
        """Test basic SummaryInfo creation."""
        now = datetime.now()
        info = SummaryInfo(
            summary_id="sum_123",
            document_path="docs/auth.md",
            summary_type=SummaryType.DETAILED,
            token_count=300,
            created_at=now,
            updated_at=now,
        )
        assert info.summary_id == "sum_123"
        assert info.document_path == "docs/auth.md"
        assert info.summary_type == SummaryType.DETAILED
        assert info.token_count == 300

    def test_summary_info_with_section(self):
        """Test SummaryInfo with section details."""
        now = datetime.now()
        info = SummaryInfo(
            summary_id="sum_123",
            document_path="docs/auth.md",
            summary_type=SummaryType.TECHNICAL,
            section_id="auth-flow",
            line_start=10,
            line_end=50,
            token_count=300,
            generated_by="claude-3.5-sonnet",
            created_at=now,
            updated_at=now,
        )
        assert info.section_id == "auth-flow"
        assert info.line_start == 10
        assert info.line_end == 50
        assert info.generated_by == "claude-3.5-sonnet"

    def test_summary_info_with_content(self):
        """Test SummaryInfo with content included."""
        now = datetime.now()
        info = SummaryInfo(
            summary_id="sum_123",
            document_path="docs/auth.md",
            summary_type=SummaryType.CONCISE,
            token_count=100,
            content="This is the summary content.",
            created_at=now,
            updated_at=now,
        )
        assert info.content == "This is the summary content."


class TestGetSummariesResult:
    """Test GetSummariesResult model."""

    def test_empty_result(self):
        """Test empty GetSummariesResult."""
        result = GetSummariesResult(
            summaries=[],
            total_count=0,
            total_tokens=0,
        )
        assert len(result.summaries) == 0
        assert result.total_count == 0
        assert result.total_tokens == 0

    def test_result_with_summaries(self):
        """Test GetSummariesResult with summaries."""
        now = datetime.now()
        info = SummaryInfo(
            summary_id="sum_123",
            document_path="docs/auth.md",
            summary_type=SummaryType.CONCISE,
            token_count=150,
            created_at=now,
            updated_at=now,
        )
        result = GetSummariesResult(
            summaries=[info],
            total_count=1,
            total_tokens=150,
        )
        assert len(result.summaries) == 1
        assert result.total_count == 1
        assert result.total_tokens == 150


class TestDeleteSummaryResult:
    """Test DeleteSummaryResult model."""

    def test_deleted_result(self):
        """Test DeleteSummaryResult with deletions."""
        result = DeleteSummaryResult(
            deleted_count=3,
            message="Deleted 3 summaries",
        )
        assert result.deleted_count == 3
        assert "3 summaries" in result.message

    def test_no_deletions(self):
        """Test DeleteSummaryResult with no deletions."""
        result = DeleteSummaryResult(
            deleted_count=0,
            message="No summaries matched criteria",
        )
        assert result.deleted_count == 0


@pytest.mark.skipif(not PRISMA_AVAILABLE, reason="Prisma client not generated")
class TestStoreSummaryPlanGating:
    """Test plan gating for rlm_store_summary."""

    @pytest.fixture
    def free_engine(self):
        """Create RLMEngine with FREE plan."""
        return RLMEngine("test-project", plan=Plan.FREE)

    @pytest.fixture
    def pro_engine(self):
        """Create RLMEngine with PRO plan."""
        return RLMEngine("test-project", plan=Plan.PRO)

    @pytest.mark.asyncio
    async def test_free_plan_rejected(self, free_engine):
        """Test FREE plan cannot store summaries."""
        result = await free_engine._handle_store_summary({
            "document_path": "docs/test.md",
            "summary": "Test summary",
        })
        assert "error" in result.data
        assert "Pro plan" in result.data["error"]

    @pytest.mark.asyncio
    async def test_missing_document_path(self, pro_engine):
        """Test missing document_path returns error."""
        result = await pro_engine._handle_store_summary({
            "summary": "Test summary",
        })
        assert "error" in result.data
        assert "document_path" in result.data["error"]

    @pytest.mark.asyncio
    async def test_missing_summary(self, pro_engine):
        """Test missing summary returns error."""
        result = await pro_engine._handle_store_summary({
            "document_path": "docs/test.md",
        })
        assert "error" in result.data
        assert "summary" in result.data["error"]


@pytest.mark.skipif(not PRISMA_AVAILABLE, reason="Prisma client not generated")
class TestGetSummariesPlanGating:
    """Test plan gating for rlm_get_summaries."""

    @pytest.fixture
    def free_engine(self):
        """Create RLMEngine with FREE plan."""
        return RLMEngine("test-project", plan=Plan.FREE)

    @pytest.mark.asyncio
    async def test_free_plan_rejected(self, free_engine):
        """Test FREE plan cannot get summaries."""
        result = await free_engine._handle_get_summaries({})
        assert "error" in result.data
        assert "Pro plan" in result.data["error"]
