"""Tests for snipara.config — layered config loading, TOML parsing, env overrides.

Tests cover:
- Default values when no config file exists
- Loading .snipara.toml with full and partial settings
- Legacy rlm.toml parsing and migration
- Global config at ~/.config/snipara/config.toml
- Layered resolution order (env > local > global > legacy > defaults)
- Environment variable overrides with type coercion
- Config file discovery walking up to git root
- TOML generation / serialization
- Edge cases: empty files, missing sections, nested directories
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from snipara.config import (
    CONFIG_FILENAME,
    SniparaConfig,
    _apply_env_overrides,
    _merge_toml_into_config,
    _parse_legacy_rlm_toml,
    _parse_toml,
    _walk_up_to_git_root,
    find_config_file,
    find_legacy_config,
    generate_toml,
    load_config,
)

# ===================================================================
# Default values
# ===================================================================


class TestDefaults:
    """Verify all default values match the documented specification."""

    def test_project_defaults(self) -> None:
        cfg = SniparaConfig()
        assert cfg.project.slug == ""
        assert cfg.project.api_key == ""
        assert cfg.project.api_url == "https://api.snipara.com"
        assert cfg.project.auth_url == "https://www.snipara.com"

    def test_context_defaults(self) -> None:
        cfg = SniparaConfig()
        assert cfg.context.max_tokens == 4000
        assert cfg.context.search_mode == "hybrid"
        assert cfg.context.include_summaries is True
        assert cfg.context.shared_context is True
        assert cfg.context.shared_context_budget_percent == 30

    def test_runtime_defaults(self) -> None:
        cfg = SniparaConfig()
        assert cfg.runtime.backend == "anthropic"
        assert cfg.runtime.model == "claude-sonnet-4-20250514"
        assert cfg.runtime.environment == "local"
        assert cfg.runtime.max_depth == 4
        assert cfg.runtime.max_subcalls == 10
        assert cfg.runtime.token_budget == 8000
        assert cfg.runtime.verbose is False

    def test_docker_defaults(self) -> None:
        cfg = SniparaConfig()
        assert cfg.docker.image == "python:3.11-slim"
        assert cfg.docker.cpus == 2.0
        assert cfg.docker.memory == "1g"
        assert cfg.docker.timeout == 300

    def test_sync_defaults(self) -> None:
        cfg = SniparaConfig()
        assert cfg.sync.include == ["docs/**/*.md", "*.md"]
        assert "node_modules/**" in cfg.sync.exclude
        assert ".git/**" in cfg.sync.exclude
        assert cfg.sync.debounce_ms == 500
        assert cfg.sync.delete_missing is False


# ===================================================================
# File discovery
# ===================================================================


class TestFileDiscovery:
    """Test config file discovery walking up directories."""

    def test_find_config_in_project_root(self, snipara_toml: Path, tmp_project: Path) -> None:
        found = find_config_file(tmp_project)
        assert found == snipara_toml

    def test_find_config_in_subdirectory(self, snipara_toml: Path, tmp_project: Path) -> None:
        """Config should be found even from a subdirectory."""
        subdir = tmp_project / "src" / "deep"
        subdir.mkdir(parents=True)
        found = find_config_file(subdir)
        assert found == snipara_toml

    def test_no_config_returns_none(self, tmp_project: Path) -> None:
        found = find_config_file(tmp_project)
        assert found is None

    def test_find_legacy_config(self, legacy_rlm_toml: Path, tmp_project: Path) -> None:
        with pytest.warns(DeprecationWarning, match="rlm.toml"):
            found = find_legacy_config(tmp_project)
        assert found == legacy_rlm_toml

    def test_walk_up_stops_at_git_root(self, tmp_project: Path) -> None:
        subdir = tmp_project / "a" / "b" / "c"
        subdir.mkdir(parents=True)
        dirs = _walk_up_to_git_root(subdir)
        # Should include subdir, a, b, c, and tmp_project (has .git)
        assert tmp_project in dirs
        assert dirs[-1] == tmp_project  # .git root is the last

    def test_walk_up_without_git(self, tmp_path: Path) -> None:
        """Without a .git dir, walk up to filesystem root."""
        dirs = _walk_up_to_git_root(tmp_path)
        assert tmp_path in dirs
        # Should eventually reach root
        assert dirs[-1].parent == dirs[-1]  # Filesystem root


# ===================================================================
# TOML loading
# ===================================================================


class TestTomlLoading:
    """Test loading .snipara.toml files."""

    def test_load_full_config(self, snipara_toml: Path, tmp_project: Path) -> None:
        cfg = load_config(tmp_project)
        assert cfg.project.slug == "test-project"
        assert cfg.project.api_key == "rlm_test1234567890abcdef"
        assert cfg.context.max_tokens == 6000
        assert cfg.context.search_mode == "semantic"
        assert cfg.runtime.environment == "docker"
        assert cfg.runtime.max_depth == 6
        assert cfg.runtime.verbose is True
        assert cfg.docker.image == "python:3.12-slim"
        assert cfg.docker.timeout == 600
        assert cfg.sync.debounce_ms == 300
        assert "docs/**/*.md" in cfg.sync.include

    def test_load_partial_config(self, tmp_project: Path) -> None:
        """Config with only [project] section — other sections keep defaults."""
        content = textwrap.dedent("""\
            [project]
            slug = "minimal"
            api_key = "rlm_mini"
        """)
        (tmp_project / CONFIG_FILENAME).write_text(content)
        cfg = load_config(tmp_project)
        assert cfg.project.slug == "minimal"
        assert cfg.project.api_key == "rlm_mini"
        # Defaults preserved
        assert cfg.context.max_tokens == 4000
        assert cfg.runtime.backend == "anthropic"
        assert cfg.sync.debounce_ms == 500

    def test_load_empty_config(self, tmp_project: Path) -> None:
        """Empty .snipara.toml gives all defaults."""
        (tmp_project / CONFIG_FILENAME).write_text("")
        cfg = load_config(tmp_project)
        assert cfg.project.slug == ""
        assert cfg.context.max_tokens == 4000

    def test_unknown_keys_ignored(self, tmp_project: Path) -> None:
        """Unknown TOML keys should not crash."""
        content = textwrap.dedent("""\
            [project]
            slug = "test"
            unknown_field = "should be ignored"

            [future_section]
            new_feature = true
        """)
        (tmp_project / CONFIG_FILENAME).write_text(content)
        cfg = load_config(tmp_project)
        assert cfg.project.slug == "test"


# ===================================================================
# Legacy rlm.toml
# ===================================================================


class TestLegacyConfig:
    """Test legacy rlm.toml parsing and field mapping."""

    def test_legacy_field_mapping(self, legacy_rlm_toml: Path, tmp_project: Path) -> None:
        data = _parse_toml(legacy_rlm_toml)
        cfg = SniparaConfig()
        cfg = _parse_legacy_rlm_toml(cfg, data)

        assert cfg.project.api_key == "rlm_legacy_key_abcdef"
        assert cfg.project.slug == "legacy-project"
        assert cfg.runtime.backend == "openai"
        assert cfg.runtime.model == "gpt-4"
        assert cfg.runtime.environment == "local"
        assert cfg.runtime.max_depth == 3
        assert cfg.context.shared_context is False
        assert cfg.context.shared_context_budget_percent == 20

    def test_legacy_empty_rlm_section(self) -> None:
        """Empty [rlm] section should not change defaults."""
        cfg = SniparaConfig()
        cfg = _parse_legacy_rlm_toml(cfg, {"rlm": {}})
        assert cfg.project.api_key == ""  # Still default

    def test_legacy_no_rlm_section(self) -> None:
        """TOML without [rlm] section should not crash."""
        cfg = SniparaConfig()
        cfg = _parse_legacy_rlm_toml(cfg, {"other": {"key": "val"}})
        assert cfg.project.api_key == ""

    def test_legacy_loaded_in_resolution(
        self, legacy_rlm_toml: Path, tmp_project: Path
    ) -> None:
        """load_config() should pick up legacy rlm.toml with deprecation warning."""
        with pytest.warns(DeprecationWarning, match="rlm.toml"):
            cfg = load_config(tmp_project)
        assert cfg.project.slug == "legacy-project"
        assert cfg.runtime.backend == "openai"


# ===================================================================
# Layered resolution
# ===================================================================


class TestLayeredResolution:
    """Test priority: env > local .snipara.toml > global > legacy > defaults."""

    def test_local_overrides_legacy(
        self, snipara_toml: Path, legacy_rlm_toml: Path, tmp_project: Path
    ) -> None:
        """Local .snipara.toml should override legacy rlm.toml."""
        with pytest.warns(DeprecationWarning):
            cfg = load_config(tmp_project)
        # .snipara.toml has "test-project", rlm.toml has "legacy-project"
        assert cfg.project.slug == "test-project"

    def test_env_overrides_local(self, snipara_toml: Path, tmp_project: Path) -> None:
        """Environment variables override .snipara.toml values."""
        env_patch = {
            "SNIPARA_API_KEY": "rlm_env_override_key",
            "SNIPARA_PROJECT_SLUG": "env-project",
            "SNIPARA_MAX_TOKENS": "12000",
        }
        with patch.dict(os.environ, env_patch, clear=False):
            cfg = load_config(tmp_project)
        assert cfg.project.api_key == "rlm_env_override_key"
        assert cfg.project.slug == "env-project"
        assert cfg.context.max_tokens == 12000

    def test_env_int_coercion(self) -> None:
        """SNIPARA_MAX_TOKENS should be coerced from string to int."""
        cfg = SniparaConfig()
        with patch.dict(os.environ, {"SNIPARA_MAX_TOKENS": "9999"}, clear=False):
            cfg = _apply_env_overrides(cfg)
        assert cfg.context.max_tokens == 9999
        assert isinstance(cfg.context.max_tokens, int)

    def test_env_project_id_alias(self) -> None:
        """SNIPARA_PROJECT_ID and SNIPARA_PROJECT_SLUG both map to slug."""
        cfg = SniparaConfig()
        with patch.dict(os.environ, {"SNIPARA_PROJECT_ID": "id-project"}, clear=False):
            cfg = _apply_env_overrides(cfg)
        assert cfg.project.slug == "id-project"


# ===================================================================
# TOML generation
# ===================================================================


class TestTomlGeneration:
    """Test config → TOML string serialization."""

    def test_generate_default_toml(self) -> None:
        cfg = SniparaConfig()
        toml_str = generate_toml(cfg)
        assert "[project]" in toml_str
        assert "[context]" in toml_str
        assert "[runtime]" in toml_str
        assert "[sync]" in toml_str
        assert "max_tokens = 4000" in toml_str

    def test_generate_with_api_key(self, populated_config: SniparaConfig) -> None:
        toml_str = generate_toml(populated_config)
        assert 'api_key = "rlm_abc123def456"' in toml_str
        assert 'slug = "my-project"' in toml_str

    def test_roundtrip_parse_generate(self, snipara_toml: Path, tmp_project: Path) -> None:
        """Load a config, generate TOML, re-parse, and verify key values match."""
        cfg1 = load_config(tmp_project)
        toml_str = generate_toml(cfg1)

        # Write and re-parse
        roundtrip_path = tmp_project / "roundtrip.toml"
        roundtrip_path.write_text(toml_str)
        data = _parse_toml(roundtrip_path)

        cfg2 = SniparaConfig()
        cfg2 = _merge_toml_into_config(cfg2, data)

        assert cfg2.project.slug == cfg1.project.slug
        assert cfg2.context.max_tokens == cfg1.context.max_tokens
        assert cfg2.runtime.backend == cfg1.runtime.backend
        assert cfg2.sync.debounce_ms == cfg1.sync.debounce_ms

    def test_default_api_url_omitted(self) -> None:
        """Default api_url should NOT appear in generated TOML (convention over config)."""
        cfg = SniparaConfig()
        toml_str = generate_toml(cfg)
        assert "api_url" not in toml_str

    def test_custom_api_url_included(self) -> None:
        cfg = SniparaConfig()
        cfg.project.api_url = "https://custom.example.com"
        toml_str = generate_toml(cfg)
        assert "api_url" in toml_str
        assert "custom.example.com" in toml_str


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_no_config_file_returns_defaults(self, tmp_project: Path) -> None:
        cfg = load_config(tmp_project)
        assert cfg.project.api_url == "https://api.snipara.com"
        assert cfg.context.max_tokens == 4000

    def test_config_source_path_tracked(self, snipara_toml: Path, tmp_project: Path) -> None:
        cfg = load_config(tmp_project)
        assert cfg._source_path == snipara_toml

    def test_config_source_path_none_without_file(self, tmp_project: Path) -> None:
        cfg = load_config(tmp_project)
        assert cfg._source_path is None

    def test_docker_section_nested_under_runtime(self, tmp_project: Path) -> None:
        """[runtime.docker] should be parsed correctly."""
        content = textwrap.dedent("""\
            [runtime]
            backend = "openai"

            [runtime.docker]
            image = "node:18-alpine"
            timeout = 120
        """)
        (tmp_project / CONFIG_FILENAME).write_text(content)
        cfg = load_config(tmp_project)
        assert cfg.runtime.backend == "openai"
        assert cfg.docker.image == "node:18-alpine"
        assert cfg.docker.timeout == 120
