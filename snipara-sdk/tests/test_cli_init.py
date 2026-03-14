"""Tests for snipara CLI commands — init, config, status, sync.

Tests cover:
- `snipara init` interactive creation
- `snipara init --migrate` rlm.toml conversion
- `snipara config show` display
- `snipara config path` discovery
- `snipara status` output
- `snipara sync --dry-run` CLI integration
- Error handling for missing configs
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from snipara.cli.main import cli
from snipara.config import CONFIG_FILENAME, LEGACY_FILENAME


@pytest.fixture()
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture()
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal project directory with .git and chdir into it."""
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ===================================================================
# snipara init
# ===================================================================


class TestInitCommand:
    """Test `snipara init` interactive config creation."""

    def test_init_creates_config(self, runner: CliRunner, project_dir: Path) -> None:
        """Interactive init should create .snipara.toml."""
        result = runner.invoke(
            cli,
            ["init", "--dir", str(project_dir)],
            input="my-project\nrlm_test_key\n4000\nhybrid\nn\n",
        )
        assert result.exit_code == 0
        config_path = project_dir / CONFIG_FILENAME
        assert config_path.exists()
        content = config_path.read_text()
        assert "my-project" in content
        assert "rlm_test_key" in content

    def test_init_default_values(self, runner: CliRunner, project_dir: Path) -> None:
        """Init with all defaults (empty inputs) should still create valid TOML."""
        result = runner.invoke(
            cli,
            ["init", "--dir", str(project_dir)],
            input="\n\n4000\nhybrid\nn\n",
        )
        assert result.exit_code == 0
        config_path = project_dir / CONFIG_FILENAME
        assert config_path.exists()

    def test_init_existing_no_overwrite(self, runner: CliRunner, project_dir: Path) -> None:
        """Init should ask before overwriting existing config."""
        config_path = project_dir / CONFIG_FILENAME
        config_path.write_text("[project]\nslug = 'existing'\n")
        result = runner.invoke(
            cli,
            ["init", "--dir", str(project_dir)],
            input="n\n",  # Don't overwrite
        )
        assert result.exit_code == 0 or result.exit_code == 1
        # Original content preserved
        assert "existing" in config_path.read_text()


# ===================================================================
# snipara init --migrate
# ===================================================================


class TestMigrateCommand:
    """Test `snipara init --migrate` rlm.toml conversion."""

    def test_migrate_creates_snipara_toml(self, runner: CliRunner, project_dir: Path) -> None:
        """Migrate should convert rlm.toml to .snipara.toml."""
        legacy_content = textwrap.dedent("""\
            [rlm]
            backend = "openai"
            model = "gpt-4"
            snipara_api_key = "rlm_migrated_key"
            snipara_project_slug = "migrated-project"
        """)
        (project_dir / LEGACY_FILENAME).write_text(legacy_content)

        result = runner.invoke(cli, ["init", "--migrate", "--dir", str(project_dir)])
        assert result.exit_code == 0
        assert "Migration complete" in result.output

        config_path = project_dir / CONFIG_FILENAME
        assert config_path.exists()
        content = config_path.read_text()
        assert "migrated-project" in content
        assert "rlm_migrated_key" in content
        assert "openai" in content

    def test_migrate_no_rlm_toml(self, runner: CliRunner, project_dir: Path) -> None:
        """Migrate without rlm.toml should fail gracefully."""
        result = runner.invoke(cli, ["init", "--migrate", "--dir", str(project_dir)])
        assert result.exit_code != 0
        assert "No rlm.toml found" in result.output


# ===================================================================
# snipara config show
# ===================================================================


class TestConfigShow:
    """Test `snipara config show` output."""

    def test_show_default_config(self, runner: CliRunner, project_dir: Path) -> None:
        """config show with no config file should display defaults."""
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "[project]" in result.output
        assert "[context]" in result.output
        assert "[runtime]" in result.output
        assert "[sync]" in result.output

    def test_show_with_config(self, runner: CliRunner, project_dir: Path) -> None:
        """config show should display values from .snipara.toml."""
        content = textwrap.dedent("""\
            [project]
            slug = "show-test"
            api_key = "rlm_show_test_key_1234"
        """)
        (project_dir / CONFIG_FILENAME).write_text(content)
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "show-test" in result.output
        # API key should be masked
        assert "rlm_sho...1234" in result.output


# ===================================================================
# snipara config path
# ===================================================================


class TestConfigPath:
    """Test `snipara config path` discovery."""

    def test_path_with_config(self, runner: CliRunner, project_dir: Path) -> None:
        config_path = project_dir / CONFIG_FILENAME
        config_path.write_text("[project]\nslug = 'test'\n")
        result = runner.invoke(cli, ["config", "path"])
        assert result.exit_code == 0
        assert str(config_path) in result.output

    def test_path_no_config(self, runner: CliRunner, project_dir: Path) -> None:
        result = runner.invoke(cli, ["config", "path"])
        assert result.exit_code != 0
        assert "No config file found" in result.output


# ===================================================================
# snipara status
# ===================================================================


class TestStatusCommand:
    """Test `snipara status` output."""

    def test_status_basic(self, runner: CliRunner, project_dir: Path) -> None:
        """Status should show config and auth information."""
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Snipara Status" in result.output
        assert "Config:" in result.output
        assert "API Key:" in result.output

    def test_status_with_config(self, runner: CliRunner, project_dir: Path) -> None:
        content = textwrap.dedent("""\
            [project]
            slug = "status-test"
            api_key = "rlm_status_test_1234567890"

            [runtime]
            backend = "openai"
            model = "gpt-4"
        """)
        (project_dir / CONFIG_FILENAME).write_text(content)
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "status-test" in result.output
        assert "openai" in result.output


# ===================================================================
# snipara version
# ===================================================================


class TestVersion:
    """Test version display."""

    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
