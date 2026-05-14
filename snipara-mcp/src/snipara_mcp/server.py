#!/usr/bin/env python3
"""
Snipara MCP Server - stdio transport to Snipara REST API.

This MCP server connects your LLM client (MCP desktop client, Cursor, etc.)
to your Snipara project for context-optimized documentation queries.

Usage:
    snipara-mcp

Authentication (in priority order):
    1. OAuth token from ~/.snipara/tokens.json (run: snipara login)
    2. SNIPARA_API_KEY environment variable (legacy)

Environment variables:
    SNIPARA_PROJECT_ID: Your project ID (required if not using OAuth)
    SNIPARA_API_KEY: Your Snipara API key (legacy, optional if using OAuth)
    SNIPARA_API_URL: API URL (default: https://api.snipara.com)
    SNIPARA_IGNORE_OAUTH: Set to "true" to skip OAuth and use API key instead
"""

import asyncio
import json
import os
import re
import sys
import time
from functools import lru_cache
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, ResourceTemplate, TextContent, Tool

from .tool_contract import MCP_TOOL_DEFINITIONS, TOOL_NAMES

# Configuration
API_URL = os.environ.get("SNIPARA_API_URL", "https://api.snipara.com")

# Auth state (loaded on startup)
_auth_token: str | None = None
_auth_type: str = "none"  # "oauth", "api_key", or "none"
_project_id: str | None = None


def _requested_project() -> tuple[str | None, str | None, str | None]:
    """Return the explicitly requested project from environment."""
    env_project_id = os.environ.get("SNIPARA_PROJECT_ID") or None
    env_project_slug = os.environ.get("SNIPARA_PROJECT_SLUG") or None
    runtime_project = env_project_slug or env_project_id
    return env_project_id, env_project_slug, runtime_project


def _auth_from_token(project_id: str, token_data: dict[str, Any]) -> tuple[str, str, str] | None:
    """Build auth tuple from a stored token, preferring legacy-compatible API keys."""
    runtime_project = token_data.get("project_slug") or token_data.get("project_id") or project_id

    api_key = token_data.get("api_key")
    if api_key:
        return api_key, "api_key", runtime_project

    access_token = token_data.get("access_token")
    if access_token:
        return access_token, "oauth", runtime_project

    return None


def _load_auth() -> tuple[str | None, str, str | None]:
    """
    Load authentication credentials in priority order:
    1. OAuth token from ~/.snipara/tokens.json (unless SNIPARA_IGNORE_OAUTH=true)
    2. API key from environment

    Returns:
        Tuple of (token, auth_type, project_id)
    """
    # Check if OAuth should be skipped
    ignore_oauth = os.environ.get("SNIPARA_IGNORE_OAUTH", "").lower() in ("true", "1", "yes")
    env_project_id, env_project_slug, requested_project = _requested_project()

    # Try OAuth tokens first (unless ignored)
    if not ignore_oauth:
        try:
            from .auth import load_tokens

            tokens = load_tokens()
            if tokens:
                explicit_project_requested = bool(env_project_id or env_project_slug)

                if explicit_project_requested:
                    matching_tokens: list[tuple[str, dict[str, Any]]] = []
                    seen_projects: set[str] = set()

                    if env_project_id and env_project_id in tokens:
                        matching_tokens.append((env_project_id, tokens[env_project_id]))
                        seen_projects.add(env_project_id)

                    if env_project_slug:
                        for project_id, token_data in tokens.items():
                            if project_id in seen_projects:
                                continue
                            if token_data.get("project_slug") == env_project_slug:
                                matching_tokens.append((project_id, token_data))
                                seen_projects.add(project_id)

                    for project_id, token_data in matching_tokens:
                        auth = _auth_from_token(project_id, token_data)
                        if auth:
                            return auth
                else:
                    # Only fall back to the first available stored token when no
                    # project has been pinned explicitly by the workspace.
                    for project_id, token_data in tokens.items():
                        auth = _auth_from_token(project_id, token_data)
                        if auth:
                            return auth
        except ImportError:
            pass  # auth module not available
        except Exception:
            pass  # Token loading failed

    # Fall back to API key from environment
    api_key = os.environ.get("SNIPARA_API_KEY", "")
    project_id = requested_project or ""
    if api_key and project_id:
        return api_key, "api_key", project_id

    # Try .snipara.toml unified config (if snipara SDK installed)
    try:
        from snipara.config import load_config

        cfg = load_config()
        cfg_key = cfg.project.api_key or ""
        cfg_slug = cfg.project.slug or ""
        if cfg_key and cfg_slug:
            return cfg_key, "api_key", cfg_slug
    except ImportError:
        pass  # snipara SDK not installed
    except Exception:
        pass  # Config loading failed

    return None, "none", requested_project


# Load auth on module import
_auth_token, _auth_type, _project_id = _load_auth()

# Legacy compatibility
API_KEY = (
    _auth_token
    if _auth_type == "api_key" and _auth_token
    else os.environ.get("SNIPARA_API_KEY", "")
)
PROJECT_ID = _project_id or (_requested_project()[2] or "")

# Session context cache
_session_context: str = ""
_session_initialized: bool = False
_session_last_bootstrap_at: float = 0.0
_shared_context_bootstrapped: bool = False

# Settings cache (5 minute TTL)
_settings_cache: dict[str, Any] = {}
_settings_cache_time: float = 0
SETTINGS_CACHE_TTL = 300  # 5 minutes


async def get_project_settings() -> dict[str, Any]:
    """Fetch project automation settings from API with caching."""
    global _settings_cache, _settings_cache_time

    # Return cached settings if still valid
    if _settings_cache and (time.time() - _settings_cache_time) < SETTINGS_CACHE_TTL:
        return _settings_cache

    # Fetch fresh settings from API
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_URL}/v1/{PROJECT_ID}/automation",
                headers=get_headers(),
            )
            if response.status_code == 200:
                data = response.json()
                _settings_cache = data.get("settings", {})
                _settings_cache_time = time.time()
                return _settings_cache
    except Exception:
        pass  # Fall back to defaults on error

    # Return defaults if API fails
    return {
        "maxTokensPerQuery": 4000,
        "searchMode": "hybrid",
        "includeSummaries": True,
        "autoInjectContext": False,
        "enrichPrompts": False,
        "memoryAutoRecallOnSessionStart": True,
        "memoryAutoRecallOnResume": True,
        "memoryDeduplicateBeforeWrite": True,
        "memoryEndOfTaskCommitEnabled": True,
        "memoryWorkspaceProfileEnabled": True,
        "memoryNoveltyThreshold": 0.92,
        "memoryResumeWindowMinutes": 180,
    }


server = Server("snipara")


def get_headers() -> dict[str, str]:
    """Get request headers with appropriate auth."""
    headers = {"Content-Type": "application/json"}

    if _auth_type == "oauth" and _auth_token:
        headers["Authorization"] = f"Bearer {_auth_token}"
    elif _auth_type == "api_key" and _auth_token:
        headers["X-API-Key"] = _auth_token
    elif API_KEY:
        # Legacy fallback
        headers["X-API-Key"] = API_KEY

    return headers


async def call_api(
    tool: str,
    params: dict[str, Any],
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Call the Snipara MCP API."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{API_URL}/v1/{PROJECT_ID}/mcp",
            headers=get_headers(),
            json={"tool": tool, "params": params},
        )
        response.raise_for_status()
        return response.json()


def _json_text(value: Any) -> str:
    """Render JSON-safe text for generic MCP responses."""
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, ensure_ascii=True, sort_keys=False)


def _tool_result_payload(result: dict[str, Any]) -> Any:
    """Extract the most useful payload from a remote tool response."""
    return result.get("result", result.get("data"))


CONTEXT_QUERY_TIMEOUT_RECOVERY = (
    "The context query timed out. Retry Snipara with a narrower query before local file search, "
    'for example: rlm_context_query(query="<3-8 key terms>", max_tokens=1200, '
    'search_mode="keyword", return_references=true, prefer_summaries=true, '
    "auto_decompose=false, include_all_tiers=false). For exact terms use rlm_search; "
    "for structural code use rlm_code_neighbors, rlm_code_callers, or rlm_code_imports."
)
CONTEXT_QUERY_PRIMARY_TIMEOUT_SECONDS = 35.0
CONTEXT_QUERY_FAST_RETRY_TIMEOUT_SECONDS = 20.0
FAST_CONTEXT_RETRY_MAX_TOKENS = 1200
FAST_CONTEXT_STOP_WORDS = {
    "about",
    "after",
    "avec",
    "comment",
    "does",
    "dans",
    "from",
    "have",
    "how",
    "pour",
    "that",
    "the",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
}


def _suggest_fast_context_query(query: str) -> str:
    """Build a compact retry query from the user's question only."""
    stripped = " ".join(query.split())
    code_terms: list[str] = []
    code_terms.extend(re.findall(r"`([^`]{2,120})`", stripped))
    code_terms.extend(
        re.findall(r"\b[\w./-]+\.(?:py|pyi|ts|tsx|mts|cts|go|md|mdx|txt)\b", stripped)
    )
    code_terms.extend(re.findall(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){1,}\b", stripped))
    if code_terms:
        return " ".join(dict.fromkeys(term.strip("`") for term in code_terms if term))[:160]

    terms = [
        term
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", stripped)
        if term.lower() not in FAST_CONTEXT_STOP_WORDS
    ]
    if terms:
        return " ".join(dict.fromkeys(terms))[:160]
    return stripped[:160] or query


def _build_context_query_payload(
    arguments: dict[str, Any],
    settings: dict[str, Any],
    *,
    query: str,
) -> dict[str, Any]:
    """Build the remote API payload without polluting retrieval with session context."""
    max_tokens = arguments.get("max_tokens") or settings.get("maxTokensPerQuery", 4000)
    search_mode = arguments.get("search_mode") or settings.get("searchMode", "hybrid")
    include_summaries = arguments.get(
        "prefer_summaries",
        settings.get("includeSummaries", True),
    )
    return {
        "query": query,
        "max_tokens": max_tokens,
        "search_mode": search_mode,
        "include_metadata": arguments.get("include_metadata", True),
        "prefer_summaries": include_summaries,
        "return_references": arguments.get("return_references", False),
        "auto_decompose": arguments.get("auto_decompose", True),
        "include_all_tiers": arguments.get("include_all_tiers", False),
    }


def _build_fast_context_query_payload(
    arguments: dict[str, Any],
    settings: dict[str, Any],
    *,
    query: str,
) -> dict[str, Any]:
    payload = _build_context_query_payload(arguments, settings, query=_suggest_fast_context_query(query))
    requested_max_tokens = int(payload.get("max_tokens") or FAST_CONTEXT_RETRY_MAX_TOKENS)
    payload.update(
        {
            "max_tokens": min(requested_max_tokens, FAST_CONTEXT_RETRY_MAX_TOKENS),
            "search_mode": "keyword",
            "prefer_summaries": True,
            "return_references": True,
            "auto_decompose": False,
            "include_all_tiers": False,
        }
    )
    return payload


def _is_fast_context_query_payload(payload: dict[str, Any]) -> bool:
    return (
        payload.get("search_mode") == "keyword"
        and payload.get("return_references") is True
        and payload.get("auto_decompose") is False
        and payload.get("include_all_tiers") is False
        and int(payload.get("max_tokens") or 0) <= 1500
    )


def _mark_context_query_fallback(data: dict[str, Any], fast_payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(data)
    guidance = list(enriched.get("recovery_guidance") or [])
    guidance.insert(
        0,
        "The primary context query timed out; Snipara returned an automatic fast retry instead.",
    )
    enriched["recovery_guidance"] = guidance
    enriched["fast_context_parameters"] = fast_payload
    enriched["query_fallback_used"] = True
    enriched["query_fallback_reason"] = "primary_timeout"
    return enriched


async def _call_context_query_with_fast_retry(
    arguments: dict[str, Any],
    settings: dict[str, Any],
    *,
    query: str,
) -> dict[str, Any]:
    payload = _build_context_query_payload(arguments, settings, query=query)
    try:
        return await call_api(
            "rlm_context_query",
            payload,
            timeout=CONTEXT_QUERY_PRIMARY_TIMEOUT_SECONDS,
        )
    except httpx.ReadTimeout:
        if _is_fast_context_query_payload(payload):
            raise
        fast_payload = _build_fast_context_query_payload(arguments, settings, query=query)
        retry_result = await call_api(
            "rlm_context_query",
            fast_payload,
            timeout=CONTEXT_QUERY_FAST_RETRY_TIMEOUT_SECONDS,
        )
        if retry_result.get("success") and isinstance(retry_result.get("result"), dict):
            retry_result = dict(retry_result)
            retry_result["result"] = _mark_context_query_fallback(
                retry_result["result"],
                fast_payload,
            )
        return retry_result


def _append_context_recovery_guidance(parts: list[str], data: dict[str, Any]) -> None:
    guidance = data.get("recovery_guidance") or []
    fast_parameters = data.get("fast_context_parameters") or {}
    narrower_queries = data.get("narrower_queries") or []
    if not (guidance or fast_parameters or narrower_queries):
        return

    parts.append("## Recovery Hints")
    for item in guidance:
        parts.append(f"- {item}")
    if narrower_queries:
        parts.append(f"- Narrower queries: {', '.join(narrower_queries[:3])}")
    if fast_parameters:
        parts.append(f"- Fast retry arguments: {json.dumps(fast_parameters, ensure_ascii=True)}")
    parts.append("")


def _append_session_context(parts: list[str]) -> None:
    if not _session_context:
        return
    parts.append("## Session Context")
    parts.append(_session_context)
    parts.append("")


def _generic_success_response(name: str, payload: Any) -> list[TextContent]:
    """Render a generic tool payload when no curated formatter exists."""
    if payload in (None, "", [], {}):
        return [TextContent(type="text", text=f"**{name}** completed successfully.")]

    if isinstance(payload, str):
        return [TextContent(type="text", text=payload)]

    return [TextContent(type="text", text=f"**{name}**\n```json\n{_json_text(payload)}\n```")]


def _format_memory_error(error: str | None) -> str:
    """Add targeted guidance for common memory parameter mistakes."""
    message = error or "Unknown error"
    if "unsupported memory type 'workflow'" in message.lower():
        return (
            f"{message}\nHint: `workflow` is only supported in "
            "`rlm_end_of_task_commit.persist_types`."
        )
    return message


@lru_cache(maxsize=1)
def _get_shared_context_bootstrap_config() -> tuple[bool, int]:
    """Load local shared-context bootstrap settings from the SDK config."""
    try:
        from snipara.config import load_config
    except Exception:
        return True, 30

    try:
        cfg = load_config()
    except Exception:
        return True, 30

    context = getattr(cfg, "context", None)
    shared_context_enabled = bool(getattr(context, "shared_context", True)) if context else True
    budget_percent = getattr(context, "shared_context_budget_percent", 30) if context else 30
    try:
        budget_percent = int(budget_percent)
    except (TypeError, ValueError):
        budget_percent = 30

    return shared_context_enabled, max(1, min(100, budget_percent))


def _format_shared_context_bootstrap(shared_result: dict[str, Any] | None) -> str:
    """Render a compact shared-context primer for session bootstrap."""
    result = shared_result or {}

    merged_content = (result.get("merged_content") or "").strip()
    if merged_content:
        return merged_content[:1500]

    docs = result.get("documents") or []
    if not docs:
        return ""

    lines = ["Shared Context Documents:"]
    for doc in docs[:8]:
        lines.append(f"- [{doc.get('category', 'OTHER')}] {doc.get('title', 'Untitled')}")
    return "\n".join(lines)


def _format_session_bootstrap(
    session_memories: dict[str, Any] | None,
    tenant_profiles: dict[str, Any] | None,
    shared_context_text: str | None = None,
) -> str:
    sections: list[str] = []

    if shared_context_text:
        sections.append("Shared Context:")
        sections.append(shared_context_text)

    profiles = (tenant_profiles or {}).get("profiles") or []
    if profiles:
        latest = profiles[0]
        sections.append("Workspace Profile:")
        sections.append(latest.get("content", "")[:1500])

    critical = ((session_memories or {}).get("critical") or {}).get("memories") or []
    if critical:
        sections.append("Critical Memories:")
        for memory in critical[:8]:
            sections.append(f"- {memory.get('content', '')[:240]}")

    daily = ((session_memories or {}).get("daily") or {}).get("memories") or []
    if daily:
        sections.append("Recent Context:")
        for memory in daily[:6]:
            sections.append(f"- {memory.get('content', '')[:240]}")

    return "\n".join(section for section in sections if section).strip()


async def ensure_session_bootstrap(force: bool = False) -> None:
    """Initialize session context from memory automation settings."""
    global _session_initialized, _session_last_bootstrap_at, _session_context
    global _shared_context_bootstrapped

    settings = await get_project_settings()
    now = time.time()
    resume_window_minutes = settings.get("memoryResumeWindowMinutes", 180)
    should_refresh = (
        _session_initialized
        and settings.get("memoryAutoRecallOnResume", True)
        and (now - _session_last_bootstrap_at) > (resume_window_minutes * 60)
    )
    shared_context_enabled, shared_context_budget_percent = _get_shared_context_bootstrap_config()
    should_bootstrap_memory = (
        force
        or (not _session_initialized and settings.get("memoryAutoRecallOnSessionStart", True))
        or should_refresh
    )
    should_bootstrap_shared = shared_context_enabled and (force or not _shared_context_bootstrapped)

    if not force:
        if _session_initialized and not should_refresh and not should_bootstrap_shared:
            return
        if not _session_initialized and not should_bootstrap_memory and not should_bootstrap_shared:
            return

    session_memories: dict[str, Any] | None = None
    tenant_profiles: dict[str, Any] | None = None
    shared_context_text: str | None = None

    if should_bootstrap_memory:
        try:
            session_result = await call_api(
                "rlm_session_memories",
                {
                    "max_critical_tokens": 4000,
                    "max_daily_tokens": 2000,
                    "include_yesterday": True,
                },
            )
            if session_result.get("success"):
                session_memories = session_result.get("result", {})
        except Exception:
            session_memories = None

        if settings.get("memoryWorkspaceProfileEnabled", True):
            try:
                tenant_result = await call_api("rlm_tenant_profile_get", {})
                if tenant_result.get("success"):
                    tenant_profiles = tenant_result.get("result", {})
            except Exception:
                tenant_profiles = None

    if should_bootstrap_shared:
        try:
            shared_max_tokens = max(
                500,
                min(
                    2000,
                    int(settings.get("maxTokensPerQuery", 4000) * shared_context_budget_percent / 100),
                ),
            )
            shared_result = await call_api(
                "rlm_shared_context",
                {
                    "max_tokens": shared_max_tokens,
                    "include_content": True,
                },
            )
            _shared_context_bootstrapped = True
            if shared_result.get("success"):
                shared_context_text = _format_shared_context_bootstrap(shared_result.get("result", {}))
        except Exception:
            shared_context_text = None

    formatted = _format_session_bootstrap(session_memories, tenant_profiles, shared_context_text)
    if formatted:
        _session_context = formatted
    _session_initialized = True
    _session_last_bootstrap_at = now


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available Snipara tools."""
    return [
        Tool(
            name=tool["name"],
            description=tool["description"],
            inputSchema=tool["inputSchema"],
        )
        for tool in MCP_TOOL_DEFINITIONS
    ]


@server.list_resources()
async def list_resources() -> list[Resource]:
    """Snipara MCP is tool-only and does not expose resources."""
    return []


@server.list_resource_templates()
async def list_resource_templates() -> list[ResourceTemplate]:
    """Snipara MCP is tool-only and does not expose resource templates."""
    return []


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    global _session_context

    try:
        await ensure_session_bootstrap()

        if name == "rlm_context_query":
            settings = await get_project_settings()
            query = arguments["query"]

            result = await _call_context_query_with_fast_retry(
                arguments,
                settings,
                query=query,
            )

            if result.get("success"):
                data = result.get("result", {})
                sections = data.get("sections", [])
                section_refs = data.get("section_refs", [])
                if sections:
                    parts = []
                    # Prepend system instructions if provided
                    if data.get("system_instructions"):
                        parts.append(data["system_instructions"])
                    _append_session_context(parts)
                    parts.append("## Relevant Documentation\n")
                    for s in sections:
                        parts.append(f"### {s.get('title', 'Untitled')}")
                        parts.append(
                            f"*{s.get('file', '')} | Score: {s.get('relevance_score', 0):.2f}*\n"
                        )
                        parts.append(s.get("content", ""))
                        parts.append("")
                    parts.append(
                        f"---\n*{len(sections)} sections, {data.get('total_tokens', 0)} tokens*"
                    )
                    _append_context_recovery_guidance(parts, data)
                    return [TextContent(type="text", text="\n".join(parts))]
                if section_refs:
                    parts = ["## Relevant Documentation References\n"]
                    if data.get("system_instructions") or _session_context:
                        parts = []
                        if data.get("system_instructions"):
                            parts.append(data["system_instructions"])
                        _append_session_context(parts)
                        parts.append("## Relevant Documentation References\n")
                    for ref in section_refs:
                        parts.append(f"### {ref.get('title', 'Untitled')}")
                        parts.append(
                            f"*{ref.get('file', '')} | Lines: {ref.get('lines', '')} | "
                            f"Score: {ref.get('relevance_score', 0):.2f}*"
                        )
                        parts.append(f"Chunk: `{ref.get('chunk_id', '')}`")
                        if ref.get("preview"):
                            parts.append(ref["preview"])
                        parts.append("")
                    parts.append(
                        f"---\n*{len(section_refs)} references, {data.get('total_tokens', 0)} preview tokens*"
                    )
                    _append_context_recovery_guidance(parts, data)
                    return [TextContent(type="text", text="\n".join(parts))]
                return [TextContent(type="text", text="No relevant documentation found.")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_ask":
            question = arguments.get("query") or arguments.get("question")
            if not question:
                return [TextContent(type="text", text="**Error:** rlm_ask requires `query`.")]
            if _session_context:
                question = f"Context: {_session_context}\n\nQuestion: {question}"

            result = await call_api(
                "rlm_ask",
                {
                    "query": question,
                },
            )

            if result.get("success"):
                data = _tool_result_payload(result) or {}
                sections = data.get("sections", []) if isinstance(data, dict) else []
                if sections:
                    parts = ["## Relevant Documentation\n"]
                    for s in sections:
                        file_path = s.get("file", s.get("file_path", ""))
                        parts.append(f"### {s.get('title', 'Untitled')}")
                        parts.append(f"*{file_path}*\n")
                        parts.append(s.get("content", ""))
                        parts.append("")
                    return [TextContent(type="text", text="\n".join(parts))]
                return _generic_success_response(name, data)
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_search":
            result = await call_api(
                "rlm_search",
                {
                    "pattern": arguments["pattern"],
                    "max_results": arguments.get("max_results", 20),
                },
            )
            if result.get("success"):
                matches = result.get("result", {}).get("matches", [])
                max_results = arguments.get("max_results", 20)
                if matches:
                    lines = [f"Found {len(matches)} matches:\n"]
                    for m in matches[:max_results]:
                        lines.append(
                            f"  {m.get('file', '')}:{m.get('line_number', 0)}: {m.get('content', '')[:100]}"
                        )
                    if len(matches) > max_results:
                        lines.append(f"\n... and {len(matches) - max_results} more")
                    return [TextContent(type="text", text="\n".join(lines))]
                return [TextContent(type="text", text=f"No matches for '{arguments['pattern']}'")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_decompose":
            result = await call_api(
                "rlm_decompose",
                {"query": arguments["query"], "max_depth": arguments.get("max_depth", 2)},
            )
            if result.get("success"):
                data = result.get("result", {})
                sub = data.get("sub_queries", [])
                lines = [f"**Decomposed into {len(sub)} sub-queries:**\n"]
                for q in sub:
                    lines.append(
                        f"{q.get('id', 0)}. {q.get('query', '')} (priority: {q.get('priority', 1)})"
                    )
                lines.append(f"\n**Suggested order:** {data.get('suggested_sequence', [])}")
                return [TextContent(type="text", text="\n".join(lines))]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_multi_query":
            result = await call_api(
                "rlm_multi_query",
                {
                    "queries": arguments["queries"],
                    "max_tokens": arguments.get("max_tokens", 8000),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                parts = [f"**Executed {data.get('queries_executed', 0)} queries:**\n"]
                for r in data.get("results", []):
                    parts.append(f"### {r.get('query', '')}")
                    for s in r.get("sections", [])[:2]:
                        parts.append(f"- {s.get('title', '')} ({s.get('file', '')})")
                    parts.append("")
                parts.append(f"*Total: {data.get('total_tokens', 0)} tokens*")
                return [TextContent(type="text", text="\n".join(parts))]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_inject":
            ctx = arguments["context"]
            if arguments.get("append") and _session_context:
                _session_context = _session_context + "\n\n" + ctx
            else:
                _session_context = ctx
            try:
                await call_api("rlm_inject", {"context": _session_context})
            except Exception:
                pass
            return [
                TextContent(
                    type="text",
                    text=f"Session context {'appended' if arguments.get('append') else 'set'} ({len(_session_context)} chars)",
                )
            ]

        elif name == "rlm_context":
            if _session_context:
                return [
                    TextContent(type="text", text=f"**Session Context:**\n\n{_session_context}")
                ]
            return [TextContent(type="text", text="No session context. Use rlm_inject to set.")]

        elif name == "rlm_clear_context":
            if _session_context:
                _session_context = ""
                try:
                    await call_api("rlm_clear_context", {})
                except Exception:
                    pass
                return [TextContent(type="text", text="Session context cleared.")]
            return [TextContent(type="text", text="No context to clear.")]

        elif name == "rlm_stats":
            result = await call_api("rlm_stats", {})
            if result.get("success"):
                # Handle both "result" and "data" keys from different API responses
                d = result.get("result", result.get("data", {}))
                # Backend returns total_characters, not total_tokens
                files_loaded = d.get("files_loaded", d.get("document_count", 0))
                total_lines = d.get("total_lines", 0)
                total_chars = d.get("total_characters", 0)
                sections = d.get("sections", d.get("chunk_count", 0))

                # Safe formatting - convert to int if numeric string, else show as-is
                def fmt(v):
                    if isinstance(v, (int, float)):
                        return f"{int(v):,}"
                    if isinstance(v, str) and v.isdigit():
                        return f"{int(v):,}"
                    return str(v) if v else "0"

                return [
                    TextContent(
                        type="text",
                        text=f"**Stats:**\n- Files: {fmt(files_loaded)}\n- Lines: {fmt(total_lines)}\n- Characters: {fmt(total_chars)}\n- Sections: {fmt(sections)}",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_help":
            result = await call_api(
                "rlm_help",
                {
                    "query": arguments.get("query"),
                    "tool": arguments.get("tool"),
                    "tier": arguments.get("tier"),
                    "limit": arguments.get("limit", 5),
                },
            )
            if result.get("success"):
                data = result.get("result", {})

                if data.get("recommendations"):
                    lines = [f"**Tool recommendations** for: {data.get('query', 'your task')}\n"]
                    for item in data.get("recommendations", []):
                        lines.append(
                            f"- `{item.get('tool', '')}` ({item.get('tier', '')}): {item.get('description', '')}"
                        )
                    if data.get("tip"):
                        lines.append("")
                        lines.append(data["tip"])
                    return [TextContent(type="text", text="\n".join(lines))]

                if data.get("tools") and data.get("tier"):
                    lines = [f"**{data.get('tier', '').title()} tools**\n"]
                    for item in data.get("tools", []):
                        lines.append(f"- `{item.get('tool', '')}`: {item.get('description', '')}")
                    return [TextContent(type="text", text="\n".join(lines))]

                if data.get("tool"):
                    lines = [
                        f"**{data.get('tool', '')}**",
                        f"Tier: {data.get('tier', '')}",
                        data.get("description", ""),
                    ]
                    use_cases = data.get("use_cases") or []
                    if use_cases:
                        lines.append("")
                        lines.append("Use cases:")
                        for use_case in use_cases:
                            lines.append(f"- {use_case}")
                    if data.get("example"):
                        lines.append("")
                        lines.append(f"Example: `{data['example']}`")
                    return [TextContent(type="text", text="\n".join(lines))]

                return [TextContent(type="text", text="No tool guidance available.")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_sections":
            result = await call_api(
                "rlm_sections",
                {
                    "limit": arguments.get("limit"),
                    "offset": arguments.get("offset"),
                    "filter": arguments.get("filter"),
                },
            )
            if result.get("success"):
                sections = result.get("result", {}).get("sections", [])
                lines = ["**Documents:**\n"]
                for s in sections:
                    lines.append(f"- {s.get('path', '')} ({s.get('chunk_count', 0)} chunks)")
                return [TextContent(type="text", text="\n".join(lines))]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_read":
            result = await call_api(
                "rlm_read",
                {"start_line": arguments["start_line"], "end_line": arguments["end_line"]},
            )
            if result.get("success"):
                content = result.get("result", {}).get("content", "")
                return [
                    TextContent(
                        type="text",
                        text=f"**Lines {arguments['start_line']}-{arguments['end_line']}:**\n```\n{content}\n```",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_settings":
            global _settings_cache, _settings_cache_time
            # Force refresh if requested
            if arguments.get("refresh"):
                _settings_cache = {}
                _settings_cache_time = 0
            settings = await get_project_settings()
            cache_age = int(time.time() - _settings_cache_time) if _settings_cache_time else 0
            lines = [
                "**Project Settings** (from dashboard)\n",
                f"- Max Tokens: {settings.get('maxTokensPerQuery', 4000)}",
                f"- Search Mode: {settings.get('searchMode', 'hybrid')}",
                f"- Include Summaries: {settings.get('includeSummaries', True)}",
                f"- Auto-Inject Context: {settings.get('autoInjectContext', False)}",
                f"- Enrich Prompts: {settings.get('enrichPrompts', False)}",
                f"\n*Cache age: {cache_age}s (TTL: {SETTINGS_CACHE_TTL}s)*",
            ]
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "rlm_upload_document":
            payload = {
                "path": arguments["path"],
                "content": arguments["content"],
            }
            for optional_key in ("kind", "format", "language", "metadata"):
                if arguments.get(optional_key) is not None:
                    payload[optional_key] = arguments[optional_key]
            result = await call_api("rlm_upload_document", payload)
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=f"**Document {data.get('action', 'processed')}:** {data.get('path', '')} ({data.get('size', 0)} bytes)",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_sync_documents":
            result = await call_api(
                "rlm_sync_documents",
                {
                    "documents": arguments["documents"],
                    "delete_missing": arguments.get("delete_missing", False),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=f"**Sync complete:** {data.get('created', 0)} created, {data.get('updated', 0)} updated, {data.get('unchanged', 0)} unchanged, {data.get('deleted', 0)} deleted",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        # Phase 4.5: Planning
        elif name == "rlm_plan":
            result = await call_api(
                "rlm_plan",
                {
                    "query": arguments["query"],
                    "strategy": arguments.get("strategy", "relevance_first"),
                    "max_tokens": arguments.get("max_tokens", 16000),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                steps = data.get("steps", [])
                lines = [
                    f"**Execution Plan** ({data.get('plan_id', 'unknown')})\n",
                    f"Strategy: {data.get('strategy', 'relevance_first')}",
                    f"Estimated tokens: {data.get('estimated_total_tokens', 0)}\n",
                    "**Steps:**",
                ]
                for step in steps:
                    deps = (
                        f" (depends on: {step.get('depends_on', [])})"
                        if step.get("depends_on")
                        else ""
                    )
                    lines.append(
                        f"{step.get('step', 0)}. {step.get('action', '')} → {step.get('expected_output', '')}{deps}"
                    )
                return [TextContent(type="text", text="\n".join(lines))]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        # Phase 4.6: Summary Storage
        elif name == "rlm_store_summary":
            result = await call_api(
                "rlm_store_summary",
                {
                    "document_path": arguments["document_path"],
                    "summary": arguments["summary"],
                    "summary_type": arguments.get("summary_type", "concise"),
                    "generated_by": arguments.get("generated_by"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                action = "created" if data.get("created") else "updated"
                return [
                    TextContent(
                        type="text",
                        text=f"**Summary {action}:** {data.get('document_path', '')} ({data.get('summary_type', '')})\nTokens: {data.get('token_count', 0)} | ID: {data.get('summary_id', '')}",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_get_summaries":
            result = await call_api(
                "rlm_get_summaries",
                {
                    "document_path": arguments.get("document_path"),
                    "summary_type": arguments.get("summary_type"),
                    "include_content": arguments.get("include_content", True),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                summaries = data.get("summaries", [])
                if summaries:
                    lines = [
                        f"**Found {len(summaries)} summaries** ({data.get('total_tokens', 0)} tokens)\n"
                    ]
                    for s in summaries:
                        lines.append(
                            f"- **{s.get('document_path', '')}** ({s.get('summary_type', '')})"
                        )
                        if s.get("content"):
                            preview = (
                                s["content"][:200] + "..."
                                if len(s.get("content", "")) > 200
                                else s.get("content", "")
                            )
                            lines.append(f"  {preview}")
                    return [TextContent(type="text", text="\n".join(lines))]
                return [TextContent(type="text", text="No summaries found.")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_delete_summary":
            result = await call_api(
                "rlm_delete_summary",
                {
                    "summary_id": arguments.get("summary_id"),
                    "document_path": arguments.get("document_path"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=f"**Deleted:** {data.get('deleted_count', 0)} summary(ies)",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        # Phase 7: Shared Context
        elif name == "rlm_shared_context":
            result = await call_api(
                "rlm_shared_context",
                {
                    "max_tokens": arguments.get("max_tokens", 4000),
                    "categories": arguments.get("categories"),
                    "include_content": arguments.get("include_content", True),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                docs = data.get("documents", [])
                if docs:
                    lines = [
                        f"**Shared Context** ({data.get('collections_loaded', 0)} collections)\n",
                        f"Total tokens: {data.get('total_tokens', 0)} | Hash: {data.get('context_hash', '')[:8]}...\n",
                    ]
                    # Group by category
                    by_cat: dict[str, list] = {}
                    for d in docs:
                        cat = d.get("category", "OTHER")
                        if cat not in by_cat:
                            by_cat[cat] = []
                        by_cat[cat].append(d)
                    for cat in ["MANDATORY", "BEST_PRACTICES", "GUIDELINES", "REFERENCE"]:
                        if cat in by_cat:
                            lines.append(f"**{cat}:**")
                            for d in by_cat[cat]:
                                lines.append(
                                    f"  - {d.get('title', 'Untitled')} ({d.get('token_count', 0)} tokens)"
                                )
                    if data.get("merged_content"):
                        lines.append("\n---\n")
                        lines.append(data["merged_content"])
                    return [TextContent(type="text", text="\n".join(lines))]
                return [TextContent(type="text", text="No shared context linked to this project.")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_list_templates":
            result = await call_api(
                "rlm_list_templates",
                {
                    "category": arguments.get("category"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                templates = data.get("templates", [])
                if templates:
                    lines = [f"**Available Templates** ({len(templates)} total)\n"]
                    # Group by category
                    by_cat: dict[str, list] = {}
                    for t in templates:
                        cat = t.get("category", "general")
                        if cat not in by_cat:
                            by_cat[cat] = []
                        by_cat[cat].append(t)
                    for cat, temps in by_cat.items():
                        lines.append(f"**{cat}:**")
                        for t in temps:
                            desc = f" - {t['description']}" if t.get("description") else ""
                            vars_str = (
                                f" (vars: {', '.join(t.get('variables', []))})"
                                if t.get("variables")
                                else ""
                            )
                            lines.append(
                                f"  - `{t.get('slug', '')}`: {t.get('name', '')}{desc}{vars_str}"
                            )
                    return [TextContent(type="text", text="\n".join(lines))]
                return [TextContent(type="text", text="No templates found.")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_get_template":
            result = await call_api(
                "rlm_get_template",
                {
                    "template_id": arguments.get("template_id"),
                    "slug": arguments.get("slug"),
                    "variables": arguments.get("variables", {}),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                template = data.get("template")
                if template:
                    lines = [
                        f"**{template.get('name', 'Template')}** (`{template.get('slug', '')}`)\n",
                        f"Category: {template.get('category', '')} | Collection: {template.get('collection_name', '')}",
                    ]
                    if template.get("description"):
                        lines.append(f"Description: {template['description']}")
                    if template.get("variables"):
                        lines.append(f"Variables: {', '.join(template['variables'])}")
                    missing = data.get("missing_variables", [])
                    if missing:
                        lines.append(f"\n⚠️ Missing variables: {', '.join(missing)}")
                    lines.append("\n**Rendered Prompt:**\n```")
                    lines.append(data.get("rendered_prompt", template.get("prompt", "")))
                    lines.append("```")
                    return [TextContent(type="text", text="\n".join(lines))]
                return [TextContent(type="text", text="Template not found.")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        # Phase 8.2: Agent Memory Handlers
        elif name == "rlm_remember":
            content = arguments.get("text") or arguments.get("content")
            if not content:
                return [
                    TextContent(
                        type="text", text="**Error:** rlm_remember requires `text` or `content`."
                    )
                ]
            result = await call_api(
                "rlm_remember",
                {
                    "text": content,
                    "type": arguments.get("type", "fact"),
                    "scope": arguments.get("scope", "project"),
                    "category": arguments.get("category"),
                    "ttl_days": arguments.get("ttl_days"),
                    "related_to": arguments.get("related_to"),
                    "document_refs": arguments.get("document_refs"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=f"**Memory stored** (ID: {data.get('memory_id', '')})\nType: {data.get('type', '')} | Scope: {data.get('scope', '')}",
                    )
                ]
            return [
                TextContent(
                    type="text", text=f"**Error:** {_format_memory_error(result.get('error'))}"
                )
            ]

        elif name == "rlm_remember_if_novel":
            content = arguments.get("text") or arguments.get("content")
            if not content:
                return [
                    TextContent(
                        type="text",
                        text="**Error:** rlm_remember_if_novel requires `text` or legacy `content`.",
                    )
                ]
            result = await call_api(
                "rlm_remember_if_novel",
                {
                    "text": content,
                    "type": arguments.get("type", "fact"),
                    "scope": arguments.get("scope", "project"),
                    "category": arguments.get("category"),
                    "ttl_days": arguments.get("ttl_days"),
                    "related_to": arguments.get("related_to"),
                    "document_refs": arguments.get("document_refs"),
                    "novelty_threshold": arguments.get("novelty_threshold"),
                    "dedupe_limit": arguments.get("dedupe_limit", 5),
                    "allow_supersede": arguments.get("allow_supersede", True),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                status = "stored" if data.get("stored") else "skipped"
                lines = [
                    f"**Memory {status}**",
                    f"Reason: {data.get('reason', 'unknown')}",
                ]
                if data.get("memory_id"):
                    lines.append(f"ID: {data['memory_id']}")
                matches = data.get("matched_memories") or []
                if matches:
                    lines.append("")
                    lines.append("Similar memories:")
                    for match in matches[:3]:
                        preview = match.get("content", "")[:120]
                        score = match.get("relevance") or match.get("score") or 0
                        lines.append(f"- {preview} (score: {score:.2f})")
                return [TextContent(type="text", text="\n".join(lines))]
            return [
                TextContent(
                    type="text", text=f"**Error:** {_format_memory_error(result.get('error'))}"
                )
            ]

        elif name == "rlm_end_of_task_commit":
            result = await call_api(
                "rlm_end_of_task_commit",
                {
                    "summary": arguments["summary"],
                    "outcome": arguments.get("outcome", "completed"),
                    "files_touched": arguments.get("files_touched"),
                    "artifacts": arguments.get("artifacts"),
                    "persist_types": arguments.get("persist_types"),
                    "category": arguments.get("category"),
                    "dry_run": arguments.get("dry_run", False),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"**Task commit processed**\nStored: {data.get('stored_count', 0)} | "
                            f"Skipped: {data.get('skipped_count', 0)}"
                        ),
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_remember_bulk":
            result = await call_api(
                "rlm_remember_bulk",
                {
                    "memories": arguments["memories"],
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                stored = data.get("stored_count", 0)
                failed = data.get("failed_count", 0)
                lines = ["**Bulk memory storage complete**", f"Stored: {stored} | Failed: {failed}"]
                memory_ids = data.get("memory_ids", [])
                if memory_ids:
                    lines.append(
                        f"IDs: {', '.join(memory_ids[:5])}{'...' if len(memory_ids) > 5 else ''}"
                    )
                return [TextContent(type="text", text="\n".join(lines))]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_recall":
            result = await call_api(
                "rlm_recall",
                {
                    "query": arguments["query"],
                    "type": arguments.get("type"),
                    "scope": arguments.get("scope"),
                    "category": arguments.get("category"),
                    "limit": arguments.get("limit", 5),
                    "min_relevance": arguments.get("min_relevance", 0.5),
                    "include_inactive": arguments.get("include_inactive", False),
                    "warning_threshold": arguments.get("warning_threshold", 0.72),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                memories = data.get("memories", [])
                warnings = data.get("warnings", [])
                if memories:
                    lines = [
                        f"**Recalled {len(memories)} memories** (searched {data.get('total_searched', 0)})\n"
                    ]
                    for m in memories:
                        conf = m.get("confidence", 1.0)
                        rel = m.get("relevance", 0)
                        status = m.get("status", "ACTIVE")
                        lines.append(f"**[{m.get('type', '')}]** {m.get('content', '')[:200]}")
                        lines.append(
                            f"  *Relevance: {rel:.2f} | Confidence: {conf:.2f} | "
                            f"Status: {status} | Accessed: {m.get('access_count', 0)}x*\n"
                        )
                    if warnings:
                        lines.append("**Inactive memory warnings**")
                        for warning in warnings:
                            reason = warning.get("reason") or "No reason provided"
                            lines.append(
                                f"- **[{warning.get('status', 'INACTIVE')}]** "
                                f"{warning.get('content', '')[:160]}"
                            )
                            lines.append(
                                f"  *Relevance: {warning.get('relevance', 0):.2f} | "
                                f"Reason: {reason}*"
                            )
                    return [TextContent(type="text", text="\n".join(lines))]
                if warnings:
                    lines = ["No active memories found.", "", "**Inactive memory warnings**"]
                    for warning in warnings:
                        reason = warning.get("reason") or "No reason provided"
                        lines.append(
                            f"- **[{warning.get('status', 'INACTIVE')}]** "
                            f"{warning.get('content', '')[:160]}"
                        )
                        lines.append(
                            f"  *Relevance: {warning.get('relevance', 0):.2f} | Reason: {reason}*"
                        )
                    return [TextContent(type="text", text="\n".join(lines))]
                return [TextContent(type="text", text="No relevant memories found.")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_memories":
            result = await call_api(
                "rlm_memories",
                {
                    "type": arguments.get("type"),
                    "scope": arguments.get("scope"),
                    "category": arguments.get("category"),
                    "status": arguments.get("status"),
                    "search": arguments.get("search"),
                    "limit": arguments.get("limit", 20),
                    "offset": arguments.get("offset", 0),
                    "include_inactive": arguments.get("include_inactive", False),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                memories = data.get("memories", [])
                if memories:
                    lines = [
                        f"**{data.get('total_count', len(memories))} memories** (showing {len(memories)})\n"
                    ]
                    for m in memories:
                        lines.append(f"- **[{m.get('type', '')}]** {m.get('content', '')[:100]}...")
                        lines.append(
                            f"  *ID: {m.get('memory_id', '')} | Status: {m.get('status', 'ACTIVE')} | "
                            f"Category: {m.get('category', 'none')}*"
                        )
                    if data.get("has_more"):
                        lines.append(
                            f"\n*More results available (offset: {arguments.get('offset', 0) + len(memories)})*"
                        )
                    return [TextContent(type="text", text="\n".join(lines))]
                return [TextContent(type="text", text="No memories found.")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_memory_invalidate":
            params = {"memory_id": arguments["memory_id"]}
            if arguments.get("invalidated_at") is not None:
                params["invalidated_at"] = arguments["invalidated_at"]
            if arguments.get("reason") is not None:
                params["reason"] = arguments["reason"]
            result = await call_api("rlm_memory_invalidate", params)
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"**Memory invalidated**\n"
                            f"ID: {data.get('memory_id', '')} | "
                            f"Status: {data.get('status', 'INVALIDATED')}"
                        ),
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_memory_supersede":
            params = {
                "old_memory_id": arguments["old_memory_id"],
                "new_memory_id": arguments["new_memory_id"],
            }
            if arguments.get("reason") is not None:
                params["reason"] = arguments["reason"]
            result = await call_api("rlm_memory_supersede", params)
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"**Memory superseded**\n"
                            f"Old ID: {data.get('old_memory_id', '')} ({data.get('old_status', 'SUPERSEDED')})\n"
                            f"New ID: {data.get('new_memory_id', '')} ({data.get('new_status', 'ACTIVE')})"
                        ),
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_forget":
            result = await call_api(
                "rlm_forget",
                {
                    "memory_id": arguments.get("memory_id"),
                    "type": arguments.get("type"),
                    "category": arguments.get("category"),
                    "older_than_days": arguments.get("older_than_days"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=f"**{data.get('message', 'Deleted')}** ({data.get('deleted_count', 0)} memories)",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_session_memories":
            result = await call_api(
                "rlm_session_memories",
                {
                    "max_critical_tokens": arguments.get("max_critical_tokens", 8000),
                    "max_daily_tokens": arguments.get("max_daily_tokens", 4000),
                    "include_yesterday": arguments.get("include_yesterday", True),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                critical = (data.get("critical") or {}).get("memories", [])
                daily = (data.get("daily") or {}).get("memories", [])
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"**Session memories**\nCritical: {len(critical)} | Daily: {len(daily)}"
                        ),
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_memory_daily_brief":
            result = await call_api(
                "rlm_memory_daily_brief",
                {
                    "date": arguments.get("date"),
                    "max_items": arguments.get("max_items", 10),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                brief = data.get("brief")
                if brief:
                    return [TextContent(type="text", text=brief)]
                counts = data.get("counts", {})
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"**Daily brief**\nDecisions: {counts.get('decisions', 0)} | "
                            f"TODOs: {counts.get('todos', 0)} | Learnings: {counts.get('learnings', 0)}"
                        ),
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_tenant_profile_get":
            result = await call_api(
                "rlm_tenant_profile_get",
                {
                    "tenant_id": arguments.get("tenant_id"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                profiles = data.get("profiles", [])
                if profiles:
                    latest = profiles[0]
                    return [TextContent(type="text", text=latest.get("content", ""))]
                return [
                    TextContent(type="text", text=data.get("message", "No tenant profiles found."))
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        # Phase 9.1: Multi-Agent Swarm Handlers
        elif name == "rlm_swarm_create":
            result = await call_api(
                "rlm_swarm_create",
                {
                    "name": arguments["name"],
                    "description": arguments.get("description"),
                    "max_agents": arguments.get("max_agents", 10),
                    "config": arguments.get("config"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=f"**Swarm created:** {data.get('name', '')}\nID: {data.get('swarm_id', '')} | Max agents: {data.get('max_agents', 10)}",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_swarm_join":
            result = await call_api(
                "rlm_swarm_join",
                {
                    "swarm_id": arguments["swarm_id"],
                    "agent_id": arguments["agent_id"],
                    "role": arguments.get("role", "worker"),
                    "capabilities": arguments.get("capabilities"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=f"**Joined swarm** as {data.get('role', 'worker')}\nAgent ID: {data.get('agent_id', '')}",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_claim":
            result = await call_api(
                "rlm_claim",
                {
                    "swarm_id": arguments["swarm_id"],
                    "agent_id": arguments["agent_id"],
                    "resource_type": arguments["resource_type"],
                    "resource_id": arguments["resource_id"],
                    "timeout_seconds": arguments.get("timeout_seconds", 300),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                if data.get("extended"):
                    return [
                        TextContent(
                            type="text",
                            text=f"**Claim extended** until {data.get('expires_at', '')}",
                        )
                    ]
                return [
                    TextContent(
                        type="text",
                        text=f"**Resource claimed:** {data.get('resource_type', '')}:{data.get('resource_id', '')}\nExpires: {data.get('expires_at', '')}",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_release":
            result = await call_api(
                "rlm_release",
                {
                    "swarm_id": arguments["swarm_id"],
                    "agent_id": arguments["agent_id"],
                    "claim_id": arguments.get("claim_id"),
                    "resource_type": arguments.get("resource_type"),
                    "resource_id": arguments.get("resource_id"),
                },
            )
            if result.get("success"):
                return [TextContent(type="text", text="**Claim released**")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_state_get":
            result = await call_api(
                "rlm_state_get",
                {
                    "swarm_id": arguments["swarm_id"],
                    "key": arguments["key"],
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                if data.get("found"):
                    value_str = _json_text(data.get("value"))
                    return [
                        TextContent(
                            type="text",
                            text=f"**{arguments['key']}** (v{data.get('version', 0)})\n```json\n{value_str}\n```",
                        )
                    ]
                return [TextContent(type="text", text=f"Key '{arguments['key']}' not found")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_state_set":
            result = await call_api(
                "rlm_state_set",
                {
                    "swarm_id": arguments["swarm_id"],
                    "agent_id": arguments["agent_id"],
                    "key": arguments["key"],
                    "value": arguments["value"],
                    "expected_version": arguments.get("expected_version"),
                    "ttl_seconds": arguments.get("ttl_seconds"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=f"**State {data.get('message', 'updated')}:** {arguments['key']} → v{data.get('version', 0)}",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_broadcast":
            result = await call_api(
                "rlm_broadcast",
                {
                    "swarm_id": arguments["swarm_id"],
                    "agent_id": arguments["agent_id"],
                    "event_type": arguments["event_type"],
                    "payload": arguments.get("payload"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                redis_status = "✓ real-time" if data.get("redis_published") else "✗ persisted only"
                return [
                    TextContent(
                        type="text",
                        text=f"**Event broadcast:** {arguments['event_type']} ({redis_status})",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_task_create":
            result = await call_api(
                "rlm_task_create",
                {
                    "swarm_id": arguments["swarm_id"],
                    "agent_id": arguments["agent_id"],
                    "title": arguments["title"],
                    "description": arguments.get("description"),
                    "priority": arguments.get("priority", 0),
                    "deadline": arguments.get("deadline"),
                    "depends_on": arguments.get("depends_on"),
                    "metadata": arguments.get("metadata"),
                    "for_agent_id": arguments.get("for_agent_id"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                deps = (
                    f" (depends on: {data.get('depends_on', [])})" if data.get("depends_on") else ""
                )
                return [
                    TextContent(
                        type="text",
                        text=f"**Task created:** {arguments['title']}\nID: {data.get('task_id', '')} | Priority: {data.get('priority', 0)}{deps}",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_task_claim":
            result = await call_api(
                "rlm_task_claim",
                {
                    "swarm_id": arguments["swarm_id"],
                    "agent_id": arguments["agent_id"],
                    "task_id": arguments.get("task_id"),
                    "timeout_seconds": arguments.get("timeout_seconds", 600),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=f"**Task claimed:** {data.get('title', '')}\nID: {data.get('task_id', '')} | Deadline: {data.get('deadline', '')}",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_task_complete":
            result = await call_api(
                "rlm_task_complete",
                {
                    "swarm_id": arguments["swarm_id"],
                    "agent_id": arguments["agent_id"],
                    "task_id": arguments["task_id"],
                    "success": arguments.get("success", True),
                    "result": arguments.get("result"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                return [
                    TextContent(
                        type="text",
                        text=f"**Task {data.get('status', 'completed')}:** {arguments['task_id']}",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        # Sprint 3: Index Health & Analytics
        elif name == "rlm_index_health":
            result = await call_api(
                "rlm_index_health",
                {
                    "stale_threshold_days": arguments.get("stale_threshold_days", 30),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                lines = [
                    f"**Index Health Score: {data.get('health_score', 0):.0f}/100** ({data.get('health_status', 'unknown').upper()})\n",
                    f"**Coverage:** {data.get('coverage', {}).get('percentage', 0):.1f}% ({data.get('coverage', {}).get('indexed', 0)}/{data.get('coverage', {}).get('total', 0)} docs)",
                    f"**Quality:** {data.get('quality', {}).get('avg_score', 0):.2f} avg ({data.get('quality', {}).get('high', 0)} high, {data.get('quality', {}).get('medium', 0)} medium, {data.get('quality', {}).get('low', 0)} low)",
                    f"**Freshness:** {data.get('freshness', {}).get('percentage', 0):.1f}% fresh, {data.get('freshness', {}).get('stale_count', 0)} stale docs\n",
                    "**Tier Distribution:**",
                ]
                for tier, count in data.get("tier_distribution", {}).items():
                    lines.append(f"  - {tier}: {count}")
                if data.get("stale_documents"):
                    lines.append(f"\n**Stale Documents:** ({len(data['stale_documents'])})")
                    for doc in data["stale_documents"][:5]:
                        lines.append(
                            f"  - {doc.get('path', '')} ({doc.get('days_since_update', 0)} days)"
                        )
                if data.get("client_notice"):
                    lines.append(f"\n**Action needed:** {data['client_notice']}")
                if data.get("recommended_tool") == "rlm_reindex":
                    args = data.get("recommended_tool_arguments", {})
                    lines.append(
                        "Recommended: "
                        f'rlm_reindex(mode="{args.get("mode", "incremental")}", kind="{args.get("kind", "doc")}")'
                    )
                return [TextContent(type="text", text="\n".join(lines))]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_index_recommendations":
            result = await call_api("rlm_index_recommendations", {})
            if result.get("success"):
                data = result.get("result", {})
                recs = data.get("recommendations", [])
                if recs:
                    lines = [
                        f"**Index Health: {data.get('health_score', 0):.0f}/100** ({data.get('health_status', 'unknown').upper()})\n",
                        f"**{len(recs)} Recommendations:**\n",
                    ]
                    for i, rec in enumerate(recs, 1):
                        priority = rec.get("priority", "medium").upper()
                        lines.append(f"{i}. [{priority}] {rec.get('title', '')}")
                        lines.append(f"   {rec.get('description', '')}")
                        if rec.get("action"):
                            lines.append(f"   Action: {rec['action']}")
                        if rec.get("tool") == "rlm_reindex":
                            args = rec.get("arguments", {})
                            lines.append(
                                "   MCP: "
                                f'rlm_reindex(mode="{args.get("mode", "incremental")}", kind="{args.get("kind", "doc")}")'
                            )
                        lines.append("")
                    return [TextContent(type="text", text="\n".join(lines))]
                return [
                    TextContent(
                        type="text",
                        text=f"**Index Health: {data.get('health_score', 0):.0f}/100** - No recommendations needed!",
                    )
                ]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_reindex":
            payload: dict[str, Any] = {}
            if arguments.get("job_id"):
                payload["job_id"] = arguments["job_id"]
            else:
                payload["mode"] = arguments.get("mode", "incremental")
                payload["kind"] = arguments.get("kind", "doc")

            result = await call_api("rlm_reindex", payload)
            if result.get("success"):
                data = result.get("result", {})
                if data.get("action") == "status":
                    lines = [
                        f"**Reindex job {data.get('id', arguments.get('job_id', ''))}**",
                        f"Status: {str(data.get('status', 'unknown')).upper()} | Progress: {data.get('progress', 0)}%",
                        f"Kind: {str(data.get('index_kind', 'doc')).lower()} | Mode: {str(data.get('index_mode', 'incremental')).lower()}",
                        f"Documents: {data.get('documents_processed', 0)}/{data.get('documents_total', 0)} | Chunks: {data.get('chunks_created', 0)}",
                    ]
                    if data.get("error_message"):
                        lines.append(f"Error: {data['error_message']}")
                    return [TextContent(type="text", text="\n".join(lines))]

                lines = [
                    f"**Reindex job created:** {data.get('job_id', '')}",
                    f"Status: {str(data.get('status', 'pending')).upper()} | Progress: {data.get('progress', 0)}%",
                    f"Kind: {str(data.get('index_kind', 'doc')).lower()} | Mode: {str(data.get('index_mode', 'incremental')).lower()}",
                ]
                if data.get("already_exists"):
                    lines.append(
                        "A matching pending/running job already existed, so it was reused."
                    )
                lines.append(f'Poll via: rlm_reindex(job_id="{data.get("job_id", "")}")')
                return [TextContent(type="text", text="\n".join(lines))]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_search_analytics":
            result = await call_api(
                "rlm_search_analytics",
                {
                    "days": arguments.get("days", 30),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                latency = data.get("latency", {})
                lines = [
                    f"**Search Analytics** (Last {arguments.get('days', 30)} days)\n",
                    f"**Queries:** {data.get('total_queries', 0)} total, {data.get('successful_queries', 0)} successful ({data.get('success_rate', 0):.1f}%)",
                    f"**Tokens:** {data.get('total_input_tokens', 0):,} in / {data.get('total_output_tokens', 0):,} out\n",
                    f"**Latency (ms):** p50={latency.get('p50', 0):.0f}, p90={latency.get('p90', 0):.0f}, p99={latency.get('p99', 0):.0f}\n",
                    "**Top Tools:**",
                ]
                for tool in data.get("tool_usage", [])[:5]:
                    lines.append(
                        f"  - {tool.get('tool', '')}: {tool.get('count', 0)} calls ({tool.get('success_rate', 0):.1f}%)"
                    )
                if data.get("errors"):
                    lines.append("\n**Errors:**")
                    for err in data.get("errors", [])[:3]:
                        lines.append(f"  - {err.get('category', '')}: {err.get('count', 0)}")
                return [TextContent(type="text", text="\n".join(lines))]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        elif name == "rlm_query_trends":
            result = await call_api(
                "rlm_query_trends",
                {
                    "days": arguments.get("days", 7),
                    "granularity": arguments.get("granularity", "day"),
                },
            )
            if result.get("success"):
                data = result.get("result", {})
                trends = data.get("trends", [])
                if trends:
                    lines = [
                        f"**Query Trends** ({arguments.get('granularity', 'day')}ly, last {arguments.get('days', 7)} days)\n",
                    ]
                    for t in trends[-10:]:  # Show last 10 periods
                        bucket = (
                            t.get("bucket", "")[:10]
                            if arguments.get("granularity") == "day"
                            else t.get("bucket", "")[:16]
                        )
                        lines.append(
                            f"  {bucket}: {t.get('count', 0)} queries ({t.get('success_rate', 0):.0f}% success)"
                        )
                    return [TextContent(type="text", text="\n".join(lines))]
                return [TextContent(type="text", text="No query trends available for this period.")]
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

        else:
            if name not in TOOL_NAMES:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

            result = await call_api(name, arguments)
            if result.get("success"):
                return _generic_success_response(name, _tool_result_payload(result))
            return [
                TextContent(type="text", text=f"**Error:** {result.get('error', 'Unknown error')}")
            ]

    except httpx.HTTPStatusError as e:
        return [
            TextContent(
                type="text", text=f"**API Error:** {e.response.status_code} - {e.response.text}"
            )
        ]
    except httpx.ReadTimeout:
        if name == "rlm_context_query":
            return [TextContent(type="text", text=f"**Timeout:** {CONTEXT_QUERY_TIMEOUT_RECOVERY}")]
        return [
            TextContent(
                type="text", text=f"**Timeout:** {name} did not return before the client timeout."
            )
        ]
    except httpx.ConnectError:
        return [TextContent(type="text", text=f"**Connection Error:** Cannot reach {API_URL}")]
    except Exception as e:
        return [TextContent(type="text", text=f"**Error:** {type(e).__name__}: {str(e)}")]


async def run_server():
    """Run the MCP server."""
    global _auth_token, _auth_type, _project_id, API_KEY, PROJECT_ID

    # Reload auth in case it changed
    _auth_token, _auth_type, _project_id = _load_auth()
    API_KEY = (
        _auth_token
        if _auth_type == "api_key" and _auth_token
        else os.environ.get("SNIPARA_API_KEY", "")
    )
    PROJECT_ID = _project_id or (_requested_project()[2] or "")

    if not _auth_token and not API_KEY:
        print("Error: No authentication found.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Options:", file=sys.stderr)
        print("  1. Run 'snipara login' to authenticate via browser (recommended)", file=sys.stderr)
        print("  2. Set SNIPARA_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)

    if not PROJECT_ID:
        print("Error: No project ID found.", file=sys.stderr)
        if _auth_type == "oauth":
            print(
                "Your OAuth token should include a project ID. Try logging in again.",
                file=sys.stderr,
            )
        else:
            print("Set SNIPARA_PROJECT_ID environment variable.", file=sys.stderr)
        sys.exit(1)

    # Log auth method for debugging
    if _auth_type == "oauth":
        print(f"Authenticated via OAuth (project: {PROJECT_ID})", file=sys.stderr)
    else:
        print(f"Authenticated via API key (project: {PROJECT_ID})", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Entry point for snipara-mcp command."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
