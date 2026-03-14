"""Snipara SDK test suite.

Tests cover:
- Configuration loading, layered resolution, and TOML generation (test_config.py)
- Async SDK client methods and result types (test_client.py)
- Synchronous wrapper delegation (test_sync_client.py)
- File watcher pattern matching, collection, and sync (test_watcher.py)
- CLI commands: init, migrate, config, status, version (test_cli_init.py)

Run with::

    pytest tests/ -v
"""
