"""Tests for rlm_settings tool and ProjectSettings.

These tests focus on model validation and engine settings initialization.
Database-dependent tests are skipped when Prisma is not generated.
"""

import pytest
from src.models import Plan, SettingsResult

# Try to import RLMEngine, skip engine tests if Prisma not generated
try:
    from src.rlm_engine import RLMEngine, ProjectSettings
    PRISMA_AVAILABLE = True
except RuntimeError:
    PRISMA_AVAILABLE = False
    # Mock ProjectSettings for model-only tests
    from dataclasses import dataclass

    @dataclass
    class ProjectSettings:
        max_tokens_per_query: int = 4000
        search_mode: str = "hybrid"
        include_summaries: bool = True
        enrich_prompts: bool = False
        auto_inject_context: bool = False
        system_instructions: str | None = None


class TestProjectSettings:
    """Test ProjectSettings dataclass."""

    def test_default_values(self):
        """Test default ProjectSettings values."""
        settings = ProjectSettings()
        assert settings.max_tokens_per_query == 4000
        assert settings.search_mode == "hybrid"
        assert settings.include_summaries is True
        assert settings.enrich_prompts is False
        assert settings.auto_inject_context is False

    def test_custom_values(self):
        """Test custom ProjectSettings values."""
        settings = ProjectSettings(
            max_tokens_per_query=8000,
            search_mode="semantic",
            include_summaries=False,
            enrich_prompts=True,
            auto_inject_context=True,
        )
        assert settings.max_tokens_per_query == 8000
        assert settings.search_mode == "semantic"
        assert settings.include_summaries is False
        assert settings.enrich_prompts is True
        assert settings.auto_inject_context is True


class TestSettingsResult:
    """Test SettingsResult Pydantic model."""

    def test_all_fields_present(self):
        """Test SettingsResult has all required fields."""
        result = SettingsResult(
            project_id="test-project",
            max_tokens_per_query=4000,
            search_mode="hybrid",
            include_summaries=True,
            auto_inject_context=False,
            message="Settings for project test-project",
        )
        assert result.project_id == "test-project"
        assert result.max_tokens_per_query == 4000
        assert result.search_mode == "hybrid"
        assert result.include_summaries is True
        assert result.auto_inject_context is False

    def test_model_dump(self):
        """Test SettingsResult model_dump for JSON serialization."""
        result = SettingsResult(
            project_id="proj_123",
            max_tokens_per_query=8000,
            search_mode="semantic",
            include_summaries=False,
            auto_inject_context=True,
            message="Test message",
        )
        data = result.model_dump()
        assert data["project_id"] == "proj_123"
        assert data["max_tokens_per_query"] == 8000
        assert data["search_mode"] == "semantic"
        assert data["include_summaries"] is False
        assert data["auto_inject_context"] is True
        assert data["message"] == "Test message"


@pytest.mark.skipif(not PRISMA_AVAILABLE, reason="Prisma client not generated")
class TestRLMEngineSettings:
    """Test RLMEngine settings initialization."""

    def test_default_settings_initialization(self):
        """Test RLMEngine initializes with default settings."""
        engine = RLMEngine("test-project")
        assert engine.settings.max_tokens_per_query == 4000
        assert engine.settings.search_mode == "hybrid"
        assert engine.settings.include_summaries is True
        assert engine.settings.enrich_prompts is False
        assert engine.settings.auto_inject_context is False

    def test_custom_settings_initialization(self):
        """Test RLMEngine initializes with custom settings dict."""
        engine = RLMEngine(
            "test-project",
            settings={
                "max_tokens_per_query": 16000,
                "search_mode": "keyword",
                "include_summaries": False,
                "enrich_prompts": True,
                "auto_inject_context": True,
            },
        )
        assert engine.settings.max_tokens_per_query == 16000
        assert engine.settings.search_mode == "keyword"
        assert engine.settings.include_summaries is False
        assert engine.settings.enrich_prompts is True
        assert engine.settings.auto_inject_context is True

    def test_partial_settings_uses_defaults(self):
        """Test partial settings dict uses defaults for missing keys."""
        engine = RLMEngine(
            "test-project",
            settings={
                "max_tokens_per_query": 8000,
                # Other settings should use defaults
            },
        )
        assert engine.settings.max_tokens_per_query == 8000
        assert engine.settings.search_mode == "hybrid"  # default
        assert engine.settings.include_summaries is True  # default
        assert engine.settings.enrich_prompts is False  # default

    def test_search_mode_keyword(self):
        """Test keyword search mode."""
        engine = RLMEngine("test-project", settings={"search_mode": "keyword"})
        assert engine.settings.search_mode == "keyword"

    def test_search_mode_semantic(self):
        """Test semantic search mode."""
        engine = RLMEngine("test-project", settings={"search_mode": "semantic"})
        assert engine.settings.search_mode == "semantic"

    def test_search_mode_hybrid(self):
        """Test hybrid search mode."""
        engine = RLMEngine("test-project", settings={"search_mode": "hybrid"})
        assert engine.settings.search_mode == "hybrid"


@pytest.mark.skipif(not PRISMA_AVAILABLE, reason="Prisma client not generated")
class TestRLMSettingsTool:
    """Test rlm_settings handler via RLMEngine."""

    @pytest.fixture
    def engine_with_defaults(self):
        """Create RLMEngine with default settings."""
        return RLMEngine("test-project")

    @pytest.fixture
    def engine_with_custom_settings(self):
        """Create RLMEngine with custom settings."""
        return RLMEngine(
            "test-project",
            settings={
                "max_tokens_per_query": 8000,
                "search_mode": "semantic",
                "include_summaries": False,
                "enrich_prompts": True,
                "auto_inject_context": True,
            },
        )

    @pytest.mark.asyncio
    async def test_returns_default_settings(self, engine_with_defaults):
        """Test _handle_settings returns default values."""
        result = await engine_with_defaults._handle_settings({})
        data = result.data

        assert data["project_id"] == "test-project"
        assert data["max_tokens_per_query"] == 4000
        assert data["search_mode"] == "hybrid"
        assert data["include_summaries"] is True
        assert data["auto_inject_context"] is False
        assert "message" in data

    @pytest.mark.asyncio
    async def test_returns_custom_settings(self, engine_with_custom_settings):
        """Test _handle_settings returns custom values."""
        result = await engine_with_custom_settings._handle_settings({})
        data = result.data

        assert data["max_tokens_per_query"] == 8000
        assert data["search_mode"] == "semantic"
        assert data["include_summaries"] is False
        assert data["auto_inject_context"] is True

    @pytest.mark.asyncio
    async def test_settings_output_tokens(self, engine_with_defaults):
        """Test _handle_settings calculates output tokens."""
        result = await engine_with_defaults._handle_settings({})
        # Output tokens should be calculated from the result
        assert result.output_tokens > 0
        # Input tokens should be 0 for settings (no input)
        assert result.input_tokens == 0


@pytest.mark.skipif(not PRISMA_AVAILABLE, reason="Prisma client not generated")
class TestPlanSettings:
    """Test plan affects settings access."""

    def test_free_plan_engine(self):
        """Test engine with FREE plan."""
        engine = RLMEngine("test-project", plan=Plan.FREE)
        assert engine.plan == Plan.FREE

    def test_pro_plan_engine(self):
        """Test engine with PRO plan."""
        engine = RLMEngine("test-project", plan=Plan.PRO)
        assert engine.plan == Plan.PRO

    def test_team_plan_engine(self):
        """Test engine with TEAM plan."""
        engine = RLMEngine("test-project", plan=Plan.TEAM)
        assert engine.plan == Plan.TEAM

    def test_enterprise_plan_engine(self):
        """Test engine with ENTERPRISE plan."""
        engine = RLMEngine("test-project", plan=Plan.ENTERPRISE)
        assert engine.plan == Plan.ENTERPRISE
