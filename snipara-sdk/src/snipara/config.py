"""Snipara unified config: .snipara.toml loader with layered resolution.

This module provides the configuration system for the Snipara SDK. It supports
a layered resolution chain that merges settings from multiple sources:

**Resolution order (highest priority wins):**

1. Environment variables (``SNIPARA_API_KEY``, ``SNIPARA_PROJECT_ID``, etc.)
2. ``.snipara.toml`` in the project directory (walks up to git root)
3. ``~/.config/snipara/config.toml`` (global user defaults)
4. ``rlm.toml`` (legacy format, emits deprecation warning)
5. Built-in defaults (Pydantic model defaults)

**Key functions:**

- :func:`load_config` — Main entry point. Loads and merges all config layers.
- :func:`find_config_file` — Find ``.snipara.toml`` walking up from CWD.
- :func:`find_legacy_config` — Find legacy ``rlm.toml`` with deprecation warning.
- :func:`generate_toml` — Serialize a ``SniparaConfig`` back to TOML string.

**Config models (Pydantic):**

- :class:`SniparaConfig` — Root config, mirrors ``.snipara.toml`` structure
- :class:`ProjectConfig` — ``[project]`` section (auth, API)
- :class:`ContextConfig` — ``[context]`` section (query defaults)
- :class:`RuntimeConfig` — ``[runtime]`` section (rlm-runtime settings)
- :class:`DockerConfig` — ``[runtime.docker]`` section
- :class:`SyncConfig` — ``[sync]`` section (file watcher patterns)

**Usage:**

    >>> from snipara.config import load_config
    >>> config = load_config()
    >>> config.project.slug
    'my-project'
    >>> config.context.max_tokens
    4000

**Environment variable mapping:**

    SNIPARA_API_KEY        → project.api_key
    SNIPARA_PROJECT_ID     → project.slug
    SNIPARA_PROJECT_SLUG   → project.slug (alias)
    SNIPARA_API_URL        → project.api_url
    SNIPARA_SEARCH_MODE    → context.search_mode
    SNIPARA_MAX_TOKENS     → context.max_tokens
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

# Python 3.11+ has tomllib in stdlib; 3.10 needs tomli backport
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        raise ImportError(
            "Python 3.10 requires the 'tomli' package for TOML support. "
            "Install with: pip install snipara"
        )

# ---------------------------------------------------------------------------
# Pydantic config models
# ---------------------------------------------------------------------------


class ProjectConfig(BaseModel):
    """[project] section — auth and API settings."""

    slug: str = ""
    api_key: str = ""
    api_url: str = "https://api.snipara.com"
    auth_url: str = "https://www.snipara.com"


class ContextConfig(BaseModel):
    """[context] section — query defaults."""

    max_tokens: int = 4000
    search_mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    include_summaries: bool = True
    shared_context: bool = True
    shared_context_budget_percent: int = 30


class RuntimeConfig(BaseModel):
    """[runtime] section — rlm-runtime execution settings."""

    backend: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    environment: Literal["local", "docker"] = "local"
    max_depth: int = 4
    max_subcalls: int = 10
    token_budget: int = 8000
    verbose: bool = False


class DockerConfig(BaseModel):
    """[runtime.docker] section."""

    image: str = "python:3.11-slim"
    cpus: float = 2.0
    memory: str = "1g"
    timeout: int = 300


class SyncConfig(BaseModel):
    """[sync] section — file watcher and sync settings."""

    include: list[str] = Field(default_factory=lambda: ["docs/**/*.md", "*.md"])
    exclude: list[str] = Field(
        default_factory=lambda: ["node_modules/**", ".git/**", "dist/**", "__pycache__/**"]
    )
    debounce_ms: int = 500
    delete_missing: bool = False


class SniparaConfig(BaseModel):
    """Root config — mirrors .snipara.toml structure."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)

    # Track where config was loaded from (not serialized to TOML)
    _source_path: Path | None = None


# ---------------------------------------------------------------------------
# Config file discovery
# ---------------------------------------------------------------------------

CONFIG_FILENAME = ".snipara.toml"
LEGACY_FILENAME = "rlm.toml"
GLOBAL_CONFIG_DIR = Path.home() / ".config" / "snipara"
GLOBAL_CONFIG_PATH = GLOBAL_CONFIG_DIR / "config.toml"


def _walk_up_to_git_root(start: Path) -> list[Path]:
    """Return directories from start up to (and including) git root."""
    dirs = []
    current = start.resolve()
    while True:
        dirs.append(current)
        if (current / ".git").exists():
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return dirs


def find_config_file(start_dir: Path | None = None) -> Path | None:
    """Walk up from start_dir to git root looking for .snipara.toml."""
    for d in _walk_up_to_git_root(start_dir or Path.cwd()):
        candidate = d / CONFIG_FILENAME
        if candidate.exists():
            return candidate
    return None


def find_legacy_config(start_dir: Path | None = None) -> Path | None:
    """Check for legacy rlm.toml and emit deprecation warning."""
    for d in _walk_up_to_git_root(start_dir or Path.cwd()):
        candidate = d / LEGACY_FILENAME
        if candidate.exists():
            warnings.warn(
                f"Found legacy {LEGACY_FILENAME} at {candidate}. "
                "Migrate to .snipara.toml with: snipara init --migrate. "
                "rlm.toml support will be removed in v1.0.",
                DeprecationWarning,
                stacklevel=3,
            )
            return candidate
    return None


def find_global_config() -> Path | None:
    """Check ~/.config/snipara/config.toml."""
    if GLOBAL_CONFIG_PATH.exists():
        return GLOBAL_CONFIG_PATH
    return None


# ---------------------------------------------------------------------------
# TOML parsing helpers
# ---------------------------------------------------------------------------


def _parse_toml(path: Path) -> dict[str, Any]:
    """Read and parse a TOML file."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def _merge_toml_into_config(config: SniparaConfig, data: dict[str, Any]) -> SniparaConfig:
    """Merge parsed TOML dict into SniparaConfig, section by section."""
    if "project" in data:
        for k, v in data["project"].items():
            if hasattr(config.project, k):
                setattr(config.project, k, v)

    if "context" in data:
        for k, v in data["context"].items():
            if hasattr(config.context, k):
                setattr(config.context, k, v)

    if "runtime" in data:
        rt = dict(data["runtime"])
        docker_data = rt.pop("docker", None)
        for k, v in rt.items():
            if hasattr(config.runtime, k):
                setattr(config.runtime, k, v)
        if docker_data:
            for k, v in docker_data.items():
                if hasattr(config.docker, k):
                    setattr(config.docker, k, v)

    if "sync" in data:
        for k, v in data["sync"].items():
            if hasattr(config.sync, k):
                setattr(config.sync, k, v)

    return config


def _parse_legacy_rlm_toml(config: SniparaConfig, data: dict[str, Any]) -> SniparaConfig:
    """Map legacy rlm.toml [rlm] section into SniparaConfig."""
    rlm = data.get("rlm", {})
    if not rlm:
        return config

    # Project settings
    if rlm.get("snipara_api_key"):
        config.project.api_key = rlm["snipara_api_key"]
    if rlm.get("snipara_project_slug"):
        config.project.slug = rlm["snipara_project_slug"]

    # Runtime settings
    field_map = {
        "backend": "backend",
        "model": "model",
        "environment": "environment",
        "max_depth": "max_depth",
        "max_subcalls": "max_subcalls",
        "token_budget": "token_budget",
        "verbose": "verbose",
    }
    for toml_key, config_key in field_map.items():
        if toml_key in rlm:
            setattr(config.runtime, config_key, rlm[toml_key])

    # Shared context settings
    if rlm.get("snipara_include_shared_context") is not None:
        config.context.shared_context = rlm["snipara_include_shared_context"]
    if rlm.get("snipara_shared_context_budget_percent") is not None:
        config.context.shared_context_budget_percent = rlm[
            "snipara_shared_context_budget_percent"
        ]

    return config


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------

_ENV_MAP: dict[str, tuple[str, str]] = {
    "SNIPARA_API_KEY": ("project", "api_key"),
    "SNIPARA_PROJECT_ID": ("project", "slug"),
    "SNIPARA_PROJECT_SLUG": ("project", "slug"),
    "SNIPARA_API_URL": ("project", "api_url"),
    "SNIPARA_SEARCH_MODE": ("context", "search_mode"),
    "SNIPARA_MAX_TOKENS": ("context", "max_tokens"),
}


def _apply_env_overrides(config: SniparaConfig) -> SniparaConfig:
    """Apply environment variable overrides (highest priority)."""
    for env_var, (section_name, field_name) in _ENV_MAP.items():
        val = os.environ.get(env_var)
        if val is None:
            continue
        section = getattr(config, section_name)
        field_type = type(getattr(section, field_name))
        if field_type is int:
            val = int(val)
        elif field_type is bool:
            val = val.lower() in ("true", "1", "yes")
        setattr(section, field_name, val)
    return config


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(start_dir: Path | None = None) -> SniparaConfig:
    """
    Load Snipara config with layered resolution.

    Priority (highest wins):
        1. Environment variables (SNIPARA_API_KEY, SNIPARA_PROJECT_ID, etc.)
        2. .snipara.toml in project directory (walk up to git root)
        3. ~/.config/snipara/config.toml (global defaults)
        4. rlm.toml (legacy, with deprecation warning)
        5. Built-in defaults

    Returns:
        SniparaConfig with all layers merged.
    """
    config = SniparaConfig()

    # Layer 4: Legacy rlm.toml (lowest file priority)
    legacy_path = find_legacy_config(start_dir)
    if legacy_path:
        legacy_data = _parse_toml(legacy_path)
        config = _parse_legacy_rlm_toml(config, legacy_data)

    # Layer 3: Global config
    global_path = find_global_config()
    if global_path:
        global_data = _parse_toml(global_path)
        config = _merge_toml_into_config(config, global_data)

    # Layer 2: Project-local .snipara.toml (highest file priority)
    local_path = find_config_file(start_dir)
    if local_path:
        local_data = _parse_toml(local_path)
        config = _merge_toml_into_config(config, local_data)
        config._source_path = local_path

    # Layer 1: Environment variables (highest overall priority)
    config = _apply_env_overrides(config)

    return config


def generate_toml(config: SniparaConfig) -> str:
    """Generate a .snipara.toml string from a SniparaConfig object."""
    lines = []

    lines.append("[project]")
    if config.project.slug:
        lines.append(f'slug = "{config.project.slug}"')
    if config.project.api_key:
        lines.append(f'api_key = "{config.project.api_key}"')
    if config.project.api_url != "https://api.snipara.com":
        lines.append(f'api_url = "{config.project.api_url}"')
    lines.append("")

    lines.append("[context]")
    lines.append(f"max_tokens = {config.context.max_tokens}")
    lines.append(f'search_mode = "{config.context.search_mode}"')
    lines.append(f"shared_context = {'true' if config.context.shared_context else 'false'}")
    lines.append(
        f"shared_context_budget_percent = {config.context.shared_context_budget_percent}"
    )
    lines.append("")

    lines.append("[runtime]")
    lines.append(f'backend = "{config.runtime.backend}"')
    lines.append(f'model = "{config.runtime.model}"')
    lines.append(f'environment = "{config.runtime.environment}"')
    lines.append(f"max_depth = {config.runtime.max_depth}")
    lines.append(f"verbose = {'true' if config.runtime.verbose else 'false'}")
    lines.append("")

    lines.append("[runtime.docker]")
    lines.append(f'image = "{config.docker.image}"')
    lines.append(f"timeout = {config.docker.timeout}")
    lines.append("")

    lines.append("[sync]")
    include_str = ", ".join(f'"{p}"' for p in config.sync.include)
    lines.append(f"include = [{include_str}]")
    exclude_str = ", ".join(f'"{p}"' for p in config.sync.exclude)
    lines.append(f"exclude = [{exclude_str}]")
    lines.append(f"debounce_ms = {config.sync.debounce_ms}")
    lines.append("")

    return "\n".join(lines) + "\n"
