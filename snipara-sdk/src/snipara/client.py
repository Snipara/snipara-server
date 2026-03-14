"""Snipara async SDK client — unified interface for context, execution, and memory.

This module provides the primary ``Snipara`` async client class and all result
dataclasses. The client wraps ``snipara_mcp.rlm_tools.SniparaClient`` internally,
so there is no HTTP logic duplication.

**Client capabilities:**

- **Context Optimization**: ``query()``, ``search()``, ``plan()``, ``multi_query()``,
  ``shared_context()`` — fetch ranked, optimized documentation context
- **Document Management**: ``upload()``, ``sync_documents()`` — manage indexed documents
- **Agent Memory**: ``remember()``, ``recall()`` — semantic memory storage and retrieval
- **Code Execution**: ``execute()`` — run tasks via rlm-runtime (optional dependency)
- **Auto-Feedback Loop**: ``run()`` — chain query → execute → remember in one call

**Usage (async context manager, recommended)::

    async with Snipara() as s:
        result = await s.query("how does auth work?")
        print(result["sections"])

**Usage (manual lifecycle)::

    s = Snipara(api_key="rlm_...", project_slug="my-project")
    result = await s.query("auth")
    await s.close()

**Result types:**

All methods return either raw ``dict[str, Any]`` (for API responses) or typed
dataclasses (``ExecuteResult``, ``RunResult``) for execution results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from snipara.config import SniparaConfig, load_config

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    """Result from a context query.

    Attributes:
        sections: Ranked documentation sections returned by the API.
        total_tokens: Total token count consumed by the returned context.
        suggestions: Optional follow-up query suggestions.
        raw: Full unprocessed API response dict.
    """

    sections: list[dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    suggestions: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Result from a regex search.

    Attributes:
        matches: List of matching documentation sections.
        total_matches: Total number of matches found.
        raw: Full unprocessed API response dict.
    """

    matches: list[dict[str, Any]] = field(default_factory=list)
    total_matches: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanResult:
    """Result from a plan generation.

    Attributes:
        steps: Ordered execution steps with dependencies.
        total_tokens: Total token count consumed by the plan context.
        raw: Full unprocessed API response dict.
    """

    steps: list[dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryResult:
    """Result from a remember/recall operation.

    Attributes:
        memory_id: Unique identifier assigned to the stored memory (remember).
        memories: List of recalled memories with relevance scores (recall).
        raw: Full unprocessed API response dict.
    """

    memory_id: str = ""
    memories: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class UploadResult:
    """Result from a document upload.

    Attributes:
        path: Document path that was uploaded (e.g. ``"docs/api.md"``).
        status: Upload status string (e.g. ``"created"``, ``"updated"``).
        raw: Full unprocessed API response dict.
    """

    path: str = ""
    status: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncResult:
    """Result from a bulk document sync.

    Attributes:
        created: Number of newly created documents.
        updated: Number of documents that were updated.
        unchanged: Number of documents that were already up to date.
        deleted: Number of documents deleted (when ``delete_missing=True``).
        raw: Full unprocessed API response dict.
    """

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecuteResult:
    """Result from rlm-runtime execution.

    Attributes:
        response: Final text response from the execution agent.
        trajectory: List of intermediate steps taken during execution.
        total_tokens: Total tokens consumed across all LLM calls.
        total_cost: Total cost in USD for the execution.
        duration_ms: Wall-clock duration of execution in milliseconds.
        raw: Full unprocessed result object from rlm-runtime.
    """

    response: str = ""
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    total_cost: float = 0.0
    duration_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        """Auto-generated one-line summary."""
        if self.response:
            first_line = self.response.strip().split("\n")[0]
            return first_line[:200]
        return ""


@dataclass
class RunResult:
    """Result from a full run() loop (query -> execute -> remember).

    Attributes:
        context: Context query result (Step 1), or *None* if skipped.
        execution: Execution result (Step 2), or *None* if execution failed.
        memories_stored: List of memory IDs created during the remember step.
    """

    context: QueryResult | None = None
    execution: ExecuteResult | None = None
    memories_stored: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class Snipara:
    """Async Snipara SDK client.

    Wraps snipara_mcp.rlm_tools.SniparaClient internally.
    Auto-discovers .snipara.toml configuration.

    Usage::

        async with Snipara() as s:
            result = await s.query("how does auth work?")
            print(result.sections)
    """

    def __init__(
        self,
        api_key: str | None = None,
        project_slug: str | None = None,
        api_url: str | None = None,
        config: SniparaConfig | None = None,
    ):
        """Initialise the async Snipara client.

        Args:
            api_key: Snipara API key (``rlm_...``). If *None*, resolved from
                config or ``SNIPARA_API_KEY`` env var.
            project_slug: Project identifier. If *None*, resolved from config
                or ``SNIPARA_PROJECT_ID`` env var.
            api_url: Base API URL. Defaults to ``https://api.snipara.com``.
            config: Pre-loaded :class:`SniparaConfig`. If *None*, auto-
                discovered via :func:`load_config`.
        """
        self._config = config or load_config()
        self._api_key = api_key or self._config.project.api_key
        self._project_slug = project_slug or self._config.project.slug
        self._api_url = api_url or self._config.project.api_url
        self._client: Any = None  # Lazy-initialized SniparaClient

    def _ensure_client(self) -> Any:
        """Lazy-initialize the underlying SniparaClient."""
        if self._client is None:
            from snipara_mcp.rlm_tools import SniparaClient

            if not self._api_key:
                raise ValueError(
                    "No API key configured. Set SNIPARA_API_KEY env var, "
                    "add api_key to .snipara.toml, or pass api_key= to Snipara()."
                )
            if not self._project_slug:
                raise ValueError(
                    "No project slug configured. Set SNIPARA_PROJECT_ID env var, "
                    "add slug to .snipara.toml, or pass project_slug= to Snipara()."
                )
            self._client = SniparaClient(
                api_key=self._api_key,
                project_slug=self._project_slug,
                api_url=self._api_url,
            )
        return self._client

    # --- Context Optimization ---

    async def query(
        self,
        query: str,
        *,
        max_tokens: int | None = None,
        search_mode: str | None = None,
    ) -> dict[str, Any]:
        """Query Snipara for optimized context.

        Returns the raw API response dict. Use result["sections"] for ranked sections.
        """
        client = self._ensure_client()
        params: dict[str, Any] = {"query": query}
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        elif self._config.context.max_tokens != 4000:
            params["max_tokens"] = self._config.context.max_tokens
        if search_mode is not None:
            params["search_mode"] = search_mode
        elif self._config.context.search_mode != "hybrid":
            params["search_mode"] = self._config.context.search_mode
        return await client.call_tool("rlm_context_query", params)

    async def search(self, pattern: str, *, max_results: int = 20) -> dict[str, Any]:
        """Search documentation with regex pattern."""
        client = self._ensure_client()
        return await client.call_tool(
            "rlm_search", {"pattern": pattern, "max_results": max_results}
        )

    async def plan(
        self,
        query: str,
        *,
        strategy: str = "relevance_first",
        max_tokens: int = 16000,
    ) -> dict[str, Any]:
        """Generate an execution plan for a complex query."""
        client = self._ensure_client()
        return await client.call_tool(
            "rlm_plan",
            {"query": query, "strategy": strategy, "max_tokens": max_tokens},
        )

    async def multi_query(
        self, queries: list[str], *, max_tokens: int = 8000
    ) -> dict[str, Any]:
        """Execute multiple queries with a shared token budget."""
        client = self._ensure_client()
        query_objects = [{"query": q} for q in queries]
        return await client.call_tool(
            "rlm_multi_query", {"queries": query_objects, "max_tokens": max_tokens}
        )

    async def shared_context(
        self,
        *,
        categories: list[str] | None = None,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """Get merged context from team shared collections."""
        client = self._ensure_client()
        params: dict[str, Any] = {"max_tokens": max_tokens}
        if categories:
            params["categories"] = categories
        return await client.call_tool("rlm_shared_context", params)

    # --- Document Management ---

    async def upload(self, path: str, content: str) -> dict[str, Any]:
        """Upload or update a document in the project."""
        client = self._ensure_client()
        return await client.call_tool(
            "rlm_upload_document", {"path": path, "content": content}
        )

    async def sync_documents(
        self,
        documents: list[dict[str, str]],
        *,
        delete_missing: bool = False,
    ) -> dict[str, Any]:
        """Bulk sync multiple documents."""
        client = self._ensure_client()
        params: dict[str, Any] = {"documents": documents}
        if delete_missing:
            params["delete_missing"] = True
        return await client.call_tool("rlm_sync_documents", params)

    # --- Agent Memory ---

    async def remember(
        self,
        content: str,
        *,
        type: str = "fact",
        scope: str = "project",
        category: str | None = None,
        ttl_days: int | None = None,
    ) -> dict[str, Any]:
        """Store a memory for later semantic recall."""
        client = self._ensure_client()
        params: dict[str, Any] = {"content": content, "type": type, "scope": scope}
        if category:
            params["category"] = category
        if ttl_days is not None:
            params["ttl_days"] = ttl_days
        return await client.call_tool("rlm_remember", params)

    async def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        min_relevance: float = 0.5,
        type: str | None = None,
    ) -> dict[str, Any]:
        """Semantically recall relevant memories."""
        client = self._ensure_client()
        params: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "min_relevance": min_relevance,
        }
        if type:
            params["type"] = type
        return await client.call_tool("rlm_recall", params)

    # --- Code Execution (requires rlm-runtime) ---

    async def execute(
        self,
        task: str,
        *,
        context: dict[str, Any] | None = None,
        environment: str | None = None,
        max_depth: int | None = None,
    ) -> ExecuteResult:
        """Execute a task via rlm-runtime.

        Requires: pip install snipara[runtime]
        """
        try:
            from rlm import RLM
        except ImportError:
            raise ImportError(
                "rlm-runtime is required for execute(). "
                "Install with: pip install snipara[runtime]"
            )

        env = environment or self._config.runtime.environment
        depth = max_depth or self._config.runtime.max_depth

        rlm = RLM(
            backend=self._config.runtime.backend,
            model=self._config.runtime.model,
            environment=env,
            max_depth=depth,
            verbose=self._config.runtime.verbose,
        )

        prompt = task
        if context:
            sections = context.get("sections", [])
            if sections:
                context_text = "\n\n".join(
                    s.get("content", str(s)) for s in sections if isinstance(s, dict)
                )
                prompt = f"Context:\n{context_text}\n\nTask:\n{task}"

        result = await rlm.completion(prompt)

        return ExecuteResult(
            response=getattr(result, "response", str(result)),
            trajectory=getattr(result, "trajectory", []),
            total_tokens=getattr(result, "total_tokens", 0),
            total_cost=getattr(result, "total_cost", 0.0),
            duration_ms=getattr(result, "duration_ms", 0),
            raw={"result": result},
        )

    # --- Auto-Feedback Loop ---

    async def run(
        self,
        task: str,
        *,
        context_query: str | None = None,
        remember_learnings: bool = True,
        memory_types: list[str] | None = None,
    ) -> RunResult:
        """Complete feedback loop: query → execute → remember.

        Args:
            task: The task to execute.
            context_query: Query to fetch context before execution.
                          Defaults to the task itself.
            remember_learnings: Whether to store learnings after execution.
            memory_types: Memory types to store (default: ["learning"]).
        """
        mem_types = memory_types or ["learning"]
        run_result = RunResult()

        # Step 1: Query context
        query_text = context_query or task
        context = await self.query(query_text)
        run_result.context = QueryResult(
            sections=context.get("sections", []),
            total_tokens=context.get("total_tokens", 0),
            raw=context,
        )

        # Step 2: Execute
        execution = await self.execute(task, context=context)
        run_result.execution = execution

        # Step 3: Remember
        if remember_learnings and execution.response:
            for mem_type in mem_types:
                result = await self.remember(
                    content=f"Task: {task}\nResult: {execution.summary}",
                    type=mem_type,
                    category="auto-feedback",
                )
                mem_id = result.get("memory_id", "")
                if mem_id:
                    run_result.memories_stored.append(mem_id)

        return run_result

    # --- Lifecycle ---

    @property
    def config(self) -> SniparaConfig:
        """Return the resolved configuration."""
        return self._config

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def __aenter__(self) -> Snipara:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
