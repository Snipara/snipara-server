"""Tests for documentation consistency and validation.

This module provides automated validation for:
- Version synchronization between pyproject.toml and __init__.py
- GitHub URL correctness in documentation files
- Documentation status accuracy (e.g., rlm-runtime deployment state)
"""

import re
import sys
import tomllib
from pathlib import Path

import pytest

def _find_project_root() -> Path:
    """Locate either the monorepo root or the standalone FastAPI mirror root."""
    test_file = Path(__file__).resolve()
    for candidate in test_file.parents:
        if (candidate / "apps/mcp-server").exists():
            return candidate
        if (candidate / "snipara-mcp/pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    return test_file.parent.parent


PROJECT_ROOT = _find_project_root()
MCP_SERVER_ROOT = (
    PROJECT_ROOT / "apps/mcp-server"
    if (PROJECT_ROOT / "apps/mcp-server").exists()
    else PROJECT_ROOT
)


class TestVersionConsistency:
    """Ensure version numbers are synchronized across files."""

    def test_pyproject_init_version_match(self):
        """Version in pyproject.toml should match __init__.py."""
        pyproject_path = MCP_SERVER_ROOT / "snipara-mcp/pyproject.toml"
        init_path = MCP_SERVER_ROOT / "snipara-mcp/src/snipara_mcp/__init__.py"
        if not pyproject_path.exists() or not init_path.exists():
            pytest.skip("snipara-mcp package not available in this checkout")

        # Read pyproject.toml version
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)
        pyproject_version = pyproject["project"]["version"]

        package_src = init_path.parents[1]
        sys.path.insert(0, str(package_src))
        try:
            from snipara_mcp import __version__ as init_version
        finally:
            sys.path.remove(str(package_src))

        assert pyproject_version == init_version, (
            f"Version mismatch: pyproject.toml={pyproject_version}, "
            f"__init__.py={init_version}. "
            "Update __init__.py to match pyproject.toml."
        )


class TestGitHubLinks:
    """Validate GitHub links are correct in documentation."""

    CORRECT_RLM_RUNTIME_URL = "github.com/Snipara/rlm-runtime"
    WRONG_RLM_RUNTIME_URL = "github.com/alopez3006/rlm-runtime"

    def test_rlm_runtime_github_links_in_docs(self):
        """All rlm-runtime GitHub links in docs/ should point to correct repo."""
        docs_path = PROJECT_ROOT / "docs"
        if not docs_path.exists():
            pytest.skip("docs/ not available in standalone FastAPI mirror")

        errors = []
        for md_file in docs_path.rglob("*.md"):
            content = md_file.read_text()
            if self.WRONG_RLM_RUNTIME_URL in content:
                relative_path = md_file.relative_to(PROJECT_ROOT)
                errors.append(str(relative_path))

        assert not errors, (
            f"Wrong GitHub URL '{self.WRONG_RLM_RUNTIME_URL}' found in: {errors}. "
            f"Should be '{self.CORRECT_RLM_RUNTIME_URL}'."
        )

    def test_rlm_runtime_github_links_in_components(self):
        """Check web components for correct rlm-runtime GitHub links."""
        web_path = PROJECT_ROOT / "apps/web/src"
        if not web_path.exists():
            pytest.skip("apps/web/src not available in standalone FastAPI mirror")

        errors = []
        for tsx_file in web_path.rglob("*.tsx"):
            content = tsx_file.read_text()
            if self.WRONG_RLM_RUNTIME_URL in content:
                relative_path = tsx_file.relative_to(PROJECT_ROOT)
                errors.append(str(relative_path))

        assert not errors, (
            f"Wrong GitHub URL '{self.WRONG_RLM_RUNTIME_URL}' found in: {errors}. "
            f"Should be '{self.CORRECT_RLM_RUNTIME_URL}'."
        )


class TestDocumentationStatus:
    """Ensure documentation reflects actual deployment status."""

    def test_rlm_runtime_not_marked_as_planned(self):
        """rlm-runtime.md should not say 'Planned (not yet deployed)'."""
        rlm_docs = PROJECT_ROOT / "docs/rlm-runtime.md"

        if not rlm_docs.exists():
            pytest.skip("docs/rlm-runtime.md not found")

        content = rlm_docs.read_text()
        assert "Planned (not yet deployed)" not in content, (
            "docs/rlm-runtime.md still marked as 'Planned (not yet deployed)' "
            "but rlm-runtime is active and available on PyPI."
        )

    def test_rlm_runtime_has_installation_instructions(self):
        """rlm-runtime.md should contain installation instructions."""
        rlm_docs = PROJECT_ROOT / "docs/rlm-runtime.md"

        if not rlm_docs.exists():
            pytest.skip("docs/rlm-runtime.md not found")

        content = rlm_docs.read_text()
        assert "pip install rlm-runtime" in content, (
            "docs/rlm-runtime.md should contain installation instructions "
            "with 'pip install rlm-runtime'."
        )


class TestAPIConsistency:
    """Validate API endpoint consistency across codebase."""

    def test_rlm_tools_uses_correct_api_pattern(self):
        """rlm_tools.py should use the standard API URL pattern."""
        rlm_tools_path = (
            PROJECT_ROOT
            / "apps/mcp-server/snipara-mcp/src/snipara_mcp/rlm_tools.py"
        )

        if not rlm_tools_path.exists():
            pytest.skip("rlm_tools.py not found")

        content = rlm_tools_path.read_text()

        # Check that it uses the correct base URL pattern
        assert "snipara.com" in content, (
            "rlm_tools.py should use snipara.com as the API base URL."
        )

        # Check that it uses the /api/mcp/ endpoint pattern
        assert "/api/mcp/" in content, (
            "rlm_tools.py should use /api/mcp/{project_slug} endpoint pattern."
        )
