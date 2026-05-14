"""Snipara MCP Server - Context optimization for LLMs."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .server import main


def _discover_version() -> str:
    """Resolve the package version from local checkout first, then installed metadata."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject.exists():
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return data["project"]["version"]

    try:
        return version("snipara-mcp")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _discover_version()
__all__ = ["main", "get_snipara_tools", "__version__"]


def get_snipara_tools(*args, **kwargs):
    """Get Snipara tools for rlm-runtime integration.

    This is a lazy import to avoid requiring rlm-runtime
    when using snipara-mcp as a standalone MCP server.

    See rlm_tools.get_snipara_tools for full documentation.
    """
    from .rlm_tools import get_snipara_tools as _get_snipara_tools
    return _get_snipara_tools(*args, **kwargs)
