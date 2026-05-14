"""Snipara SDK — Unified Python client for context optimization and agent infrastructure.

This is the top-level package providing all public exports for the ``snipara`` SDK.
It consolidates 5 separate config systems into a single ``.snipara.toml`` file,
provides async/sync Python clients wrapping the Snipara MCP server, event-driven
file synchronization, and an auto-feedback loop (query → execute → remember).

Quick Start::

    # Async usage
    from snipara import Snipara

    async with Snipara() as s:
        result = await s.query("how does auth work?")
        print(result["sections"])

    # Sync usage
    from snipara import SniparaSync

    with SniparaSync() as s:
        result = s.query("how does auth work?")

    # Config-only usage
    from snipara import load_config
    config = load_config()
    print(config.project.slug)

Exports:
    Snipara:        Async SDK client (primary interface)
    SniparaSync:    Synchronous wrapper for scripts and notebooks
    load_config:    Load and merge .snipara.toml configuration
    SniparaConfig:  Pydantic config model (type-safe)
    QueryResult:    Result from context queries
    SearchResult:   Result from regex searches
    PlanResult:     Result from execution planning
    MemoryResult:   Result from remember/recall operations
    UploadResult:   Result from document uploads
    SyncResult:     Result from bulk document sync
    ExecuteResult:  Result from rlm-runtime execution
    RunResult:      Result from full feedback loop

Installation::

    pip install snipara            # Core SDK
    pip install snipara[watch]     # + file watcher
    pip install snipara[runtime]   # + code execution
    pip install snipara[all]       # Everything
"""

from snipara._version import __version__
from snipara.client import (
    ExecuteResult,
    MemoryResult,
    PlanResult,
    QueryResult,
    RunResult,
    SearchResult,
    Snipara,
    SyncResult,
    UploadResult,
)
from snipara.config import SniparaConfig, load_config
from snipara.sync_client import SniparaSync

__all__ = [
    "__version__",
    # Clients
    "Snipara",
    "SniparaSync",
    # Config
    "SniparaConfig",
    "load_config",
    # Result types
    "QueryResult",
    "SearchResult",
    "PlanResult",
    "MemoryResult",
    "UploadResult",
    "SyncResult",
    "ExecuteResult",
    "RunResult",
]
