"""Regression test for the checked-in snipara-fastapi MCP mirror."""

import sys
from pathlib import Path

import pytest

TEST_FILE = Path(__file__).resolve()
PROJECT_ROOT = next(
    (
        candidate
        for candidate in (TEST_FILE.parents[2], TEST_FILE.parents[3])
        if (candidate / "apps/mcp-server/scripts").exists()
    ),
    None,
)
if PROJECT_ROOT is None:
    pytest.skip("mirror sync check requires the Snipara monorepo", allow_module_level=True)
SCRIPTS_DIR = PROJECT_ROOT / "apps/mcp-server/scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sync_snipara_fastapi_mirror as mirror_sync


def test_snipara_fastapi_mcp_mirror_is_in_sync() -> None:
    """The checked-in snipara-fastapi mirror should match canonical MCP sources."""
    assert mirror_sync.sync(check_only=True) == 0
