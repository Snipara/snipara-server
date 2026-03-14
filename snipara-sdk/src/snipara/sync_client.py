"""SniparaSync — synchronous wrapper around the async Snipara client.

Provides the same API as :class:`~snipara.client.Snipara` but with blocking
(synchronous) method calls. Suitable for scripts, notebooks, and non-async code.

**Event loop handling:**

- If no event loop is running, uses ``asyncio.run()`` directly.
- If an event loop IS running (e.g., Jupyter notebooks), falls back to
  running the coroutine in a ``ThreadPoolExecutor`` to avoid
  ``RuntimeError: This event loop is already running``.

**Usage::

    from snipara import SniparaSync

    with SniparaSync() as s:
        result = s.query("how does auth work?")
        print(result)

    # Or without context manager
    s = SniparaSync()
    result = s.query("...")
    s.close()

**All methods mirror the async ``Snipara`` client:**
``query()``, ``search()``, ``plan()``, ``multi_query()``, ``shared_context()``,
``upload()``, ``sync_documents()``, ``remember()``, ``recall()``,
``execute()``, ``run()``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from snipara.client import (
    ExecuteResult,
    RunResult,
    Snipara,
)
from snipara.config import SniparaConfig


class SniparaSync:
    """Synchronous Snipara SDK client.

    Wraps the async Snipara class using asyncio.run() for each call.
    Suitable for scripts, notebooks, and non-async code.

    Usage::

        s = SniparaSync()
        result = s.query("how does auth work?")
        print(result)
        s.close()
    """

    def __init__(
        self,
        api_key: str | None = None,
        project_slug: str | None = None,
        api_url: str | None = None,
        config: SniparaConfig | None = None,
    ):
        """Initialise the synchronous Snipara client.

        All parameters mirror :meth:`Snipara.__init__`. Internally creates
        an async :class:`Snipara` instance and wraps every call with
        ``asyncio.run()`` (or a thread-pool fallback in Jupyter).

        Args:
            api_key: Snipara API key (``rlm_...``). If *None*, resolved from
                config or ``SNIPARA_API_KEY`` env var.
            project_slug: Project identifier. If *None*, resolved from config
                or ``SNIPARA_PROJECT_ID`` env var.
            api_url: Base API URL. Defaults to ``https://api.snipara.com``.
            config: Pre-loaded :class:`SniparaConfig`. If *None*, auto-
                discovered via :func:`load_config`.
        """
        self._async_client = Snipara(
            api_key=api_key,
            project_slug=project_slug,
            api_url=api_url,
            config=config,
        )

    def _run(self, coro: Any) -> Any:
        """Run an async coroutine synchronously."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an existing event loop (e.g., Jupyter)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return asyncio.run(coro)

    # --- Context ---

    def query(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Query Snipara for optimized context."""
        return self._run(self._async_client.query(query, **kwargs))

    def search(self, pattern: str, **kwargs: Any) -> dict[str, Any]:
        """Search documentation with regex pattern."""
        return self._run(self._async_client.search(pattern, **kwargs))

    def plan(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Generate an execution plan."""
        return self._run(self._async_client.plan(query, **kwargs))

    def multi_query(self, queries: list[str], **kwargs: Any) -> dict[str, Any]:
        """Execute multiple queries with shared budget."""
        return self._run(self._async_client.multi_query(queries, **kwargs))

    def shared_context(self, **kwargs: Any) -> dict[str, Any]:
        """Get merged team shared context."""
        return self._run(self._async_client.shared_context(**kwargs))

    # --- Documents ---

    def upload(self, path: str, content: str) -> dict[str, Any]:
        """Upload or update a document."""
        return self._run(self._async_client.upload(path, content))

    def sync_documents(self, documents: list[dict[str, str]], **kwargs: Any) -> dict[str, Any]:
        """Bulk sync documents."""
        return self._run(self._async_client.sync_documents(documents, **kwargs))

    # --- Memory ---

    def remember(self, content: str, **kwargs: Any) -> dict[str, Any]:
        """Store a memory."""
        return self._run(self._async_client.remember(content, **kwargs))

    def recall(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Recall relevant memories."""
        return self._run(self._async_client.recall(query, **kwargs))

    # --- Execution ---

    def execute(self, task: str, **kwargs: Any) -> ExecuteResult:
        """Execute via rlm-runtime. Requires: pip install snipara[runtime]"""
        return self._run(self._async_client.execute(task, **kwargs))

    def run(self, task: str, **kwargs: Any) -> RunResult:
        """Full feedback loop: query → execute → remember."""
        return self._run(self._async_client.run(task, **kwargs))

    # --- Lifecycle ---

    @property
    def config(self) -> SniparaConfig:
        return self._async_client.config

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._run(self._async_client.close())

    def __enter__(self) -> SniparaSync:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
