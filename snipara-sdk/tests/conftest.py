"""Shared fixtures for Snipara SDK tests.

This module provides reusable pytest fixtures for:
- Temporary directories with .snipara.toml configs
- Mock SniparaClient objects
- Config factories for different test scenarios
- Async client fixtures with controlled lifecycle
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from snipara.config import CONFIG_FILENAME, LEGACY_FILENAME, SniparaConfig

# ---------------------------------------------------------------------------
# Environment isolation — clear SNIPARA_* env vars for all tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all SNIPARA_* env vars so tests don't pick up real config."""
    for key in list(os.environ):
        if key.startswith("SNIPARA_"):
            monkeypatch.delenv(key, raising=False)

# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with a .git marker."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    return tmp_path


@pytest.fixture()
def snipara_toml(tmp_project: Path) -> Path:
    """Create a .snipara.toml in the tmp project with realistic values."""
    content = textwrap.dedent("""\
        [project]
        slug = "test-project"
        api_key = "rlm_test1234567890abcdef"
        api_url = "https://api.snipara.com"

        [context]
        max_tokens = 6000
        search_mode = "semantic"
        shared_context = true
        shared_context_budget_percent = 25

        [runtime]
        backend = "anthropic"
        model = "claude-sonnet-4-20250514"
        environment = "docker"
        max_depth = 6
        verbose = true

        [runtime.docker]
        image = "python:3.12-slim"
        timeout = 600

        [sync]
        include = ["docs/**/*.md", "src/**/*.py"]
        exclude = ["node_modules/**", ".git/**", "__pycache__/**"]
        debounce_ms = 300
    """)
    config_path = tmp_project / CONFIG_FILENAME
    config_path.write_text(content)
    return config_path


@pytest.fixture()
def legacy_rlm_toml(tmp_project: Path) -> Path:
    """Create a legacy rlm.toml for migration tests."""
    content = textwrap.dedent("""\
        [rlm]
        backend = "openai"
        model = "gpt-4"
        environment = "local"
        max_depth = 3
        verbose = false
        snipara_api_key = "rlm_legacy_key_abcdef"
        snipara_project_slug = "legacy-project"
        snipara_include_shared_context = false
        snipara_shared_context_budget_percent = 20
    """)
    legacy_path = tmp_project / LEGACY_FILENAME
    legacy_path.write_text(content)
    return legacy_path


@pytest.fixture()
def global_config(tmp_path: Path) -> Path:
    """Create a global config at a simulated ~/.config/snipara/config.toml."""
    config_dir = tmp_path / ".config" / "snipara"
    config_dir.mkdir(parents=True)
    content = textwrap.dedent("""\
        [project]
        api_url = "https://custom.api.snipara.com"

        [context]
        max_tokens = 8000
        search_mode = "keyword"

        [runtime]
        backend = "litellm"
        model = "gpt-4-turbo"
    """)
    config_path = config_dir / "config.toml"
    config_path.write_text(content)
    return config_path


@pytest.fixture()
def default_config() -> SniparaConfig:
    """Return a config with all defaults (no file, no env)."""
    return SniparaConfig()


@pytest.fixture()
def populated_config() -> SniparaConfig:
    """Return a fully-populated config for testing serialization."""
    cfg = SniparaConfig()
    cfg.project.slug = "my-project"
    cfg.project.api_key = "rlm_abc123def456"
    cfg.context.max_tokens = 5000
    cfg.context.search_mode = "semantic"
    cfg.runtime.backend = "openai"
    cfg.runtime.model = "gpt-4"
    cfg.runtime.environment = "docker"
    cfg.runtime.verbose = True
    cfg.sync.include = ["**/*.md"]
    cfg.sync.exclude = [".git/**"]
    cfg.sync.debounce_ms = 250
    return cfg


# ---------------------------------------------------------------------------
# Mock client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_snipara_client() -> MagicMock:
    """Create a mock SniparaClient with async call_tool method.

    Returns a MagicMock that simulates SniparaClient behavior:
    - call_tool(tool_name, params) returns realistic response dicts
    - close() is an async no-op
    """
    client = MagicMock()
    client.call_tool = AsyncMock(
        return_value={
            "sections": [
                {
                    "title": "Authentication",
                    "content": "Auth uses JWT tokens...",
                    "relevance": 0.95,
                    "file": "docs/auth.md",
                    "line_start": 1,
                    "line_end": 50,
                }
            ],
            "total_tokens": 1234,
            "suggestions": [],
        }
    )
    client.close = AsyncMock()
    return client


@pytest.fixture()
def mock_snipara_client_factory() -> Any:
    """Factory for creating mock clients with custom call_tool responses."""

    def _factory(responses: dict[str, Any] | None = None) -> MagicMock:
        client = MagicMock()
        default_response = {
            "sections": [],
            "total_tokens": 0,
        }
        if responses:

            async def _call_tool(tool_name: str, params: dict) -> Any:
                return responses.get(tool_name, default_response)

            client.call_tool = AsyncMock(side_effect=_call_tool)
        else:
            client.call_tool = AsyncMock(return_value=default_response)
        client.close = AsyncMock()
        return client

    return _factory


# ---------------------------------------------------------------------------
# Token file fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def oauth_tokens(tmp_path: Path) -> Path:
    """Create a mock OAuth tokens file at a simulated ~/.snipara/tokens.json."""
    tokens_dir = tmp_path / ".snipara"
    tokens_dir.mkdir()
    tokens_path = tokens_dir / "tokens.json"
    tokens = {
        "test-project": {
            "access_token": "snipara_at_test123",
            "refresh_token": "snipara_rt_test456",
            "expires_at": 9999999999,
        }
    }
    tokens_path.write_text(json.dumps(tokens))
    return tokens_path


# ---------------------------------------------------------------------------
# File sync fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sync_project(tmp_project: Path) -> Path:
    """Create a project with files matching sync patterns."""
    # Create docs
    docs_dir = tmp_project / "docs"
    docs_dir.mkdir()
    (docs_dir / "getting-started.md").write_text("# Getting Started\n\nWelcome to the project.")
    (docs_dir / "api.md").write_text("# API Reference\n\nEndpoints...")

    # Nested docs
    nested = docs_dir / "guides"
    nested.mkdir()
    (nested / "auth.md").write_text("# Authentication Guide\n\nUse JWT tokens.")

    # Root markdown
    (tmp_project / "README.md").write_text("# Project\n\nDescription")
    (tmp_project / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0")

    # Non-matching files (should be excluded)
    src_dir = tmp_project / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hello')")

    # Excluded dirs
    node_modules = tmp_project / "node_modules"
    node_modules.mkdir()
    (node_modules / "package.md").write_text("should be excluded")

    return tmp_project
