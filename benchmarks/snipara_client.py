"""Snipara API client for benchmarking.

Calls the real Snipara MCP API to get optimized context,
enabling accurate benchmarking of context optimization quality.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx


def load_oauth_token(project_slug: str = "snipara") -> Optional[dict]:
    """Load OAuth token from ~/.snipara/tokens.json.

    Args:
        project_slug: Project slug to find token for

    Returns:
        Token dict with access_token, or None if not found
    """
    tokens_file = Path.home() / ".snipara" / "tokens.json"
    if not tokens_file.exists():
        return None

    try:
        tokens = json.loads(tokens_file.read_text())

        # Find token by project_slug
        for project_id, token_data in tokens.items():
            if token_data.get("project_slug") == project_slug:
                # Check if expired
                expires_at = token_data.get("expires_at")
                if expires_at:
                    exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    if exp_dt < datetime.now(exp_dt.tzinfo) if exp_dt.tzinfo else datetime.now():
                        # Token expired, but still return it for refresh attempt
                        pass
                return token_data

        # If no match by slug, return first token
        if tokens:
            return list(tokens.values())[0]
    except (json.JSONDecodeError, KeyError):
        pass

    return None


@dataclass
class ContextSection:
    """A section returned by Snipara context query."""

    title: str
    content: str
    file: str
    lines: tuple[int, int]
    relevance_score: float
    token_count: int
    truncated: bool = False


@dataclass
class ContextQueryResult:
    """Result from Snipara rlm_context_query."""

    sections: list[ContextSection]
    total_tokens: int
    max_tokens: int
    query: str
    search_mode: str
    suggestions: list[str]
    summaries_used: int = 0
    shared_context_included: bool = False
    shared_context_tokens: int = 0
    timing: Optional[dict] = None
    system_instructions: str = ""  # Grounding instructions from API

    def to_context_string(self) -> str:
        """Convert sections to a single context string.

        Includes system_instructions (grounding rules) at the top
        to help prevent LLM hallucination.
        """
        parts = []

        # Prepend grounding instructions if available
        if self.system_instructions:
            parts.append(self.system_instructions)

        for section in self.sections:
            parts.append(f"## {section.title}\n\n{section.content}")
        return "\n\n---\n\n".join(parts)


class SniparaClient:
    """Client for Snipara MCP API."""

    # Refresh token 5 minutes before expiry
    _REFRESH_GRACE_SECONDS = 300

    def __init__(
        self,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        project_slug: str = "snipara",
        base_url: Optional[str] = None,
    ):
        """Initialize Snipara client.

        Args:
            api_key: Snipara API key (rlm_...). Defaults to SNIPARA_API_KEY env var.
            access_token: OAuth access token (snipara_at_...). Auto-loaded from ~/.snipara/tokens.json.
            project_slug: Project slug for API endpoint.
            base_url: Base URL for Snipara API.
        """
        self.api_key = api_key or os.getenv("SNIPARA_API_KEY")
        self.access_token = access_token
        self.project_slug = project_slug
        self.base_url = base_url or os.getenv("SNIPARA_BASE_URL", "https://api.snipara.com/mcp")
        self._client: Optional[httpx.AsyncClient] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        self._project_id: Optional[str] = None

        # When using API key with a non-production server (e.g. localhost),
        # skip OAuth entirely — the local server only validates API keys.
        if self.api_key and "api.snipara.com" not in self.base_url:
            self.access_token = None
            return

        # Always load token data from tokens.json for refresh_token/expires_at
        # Even when access_token is passed explicitly, we need the refresh_token
        # to auto-refresh when the token expires during long benchmark runs
        token_data = load_oauth_token(project_slug)
        if token_data:
            if not self.access_token:
                self.access_token = token_data.get("access_token")
            self._refresh_token = token_data.get("refresh_token")
            self._project_id = token_data.get("project_id")
            expires_at = token_data.get("expires_at")
            if expires_at:
                try:
                    self._expires_at = datetime.fromisoformat(
                        expires_at.replace("Z", "+00:00")
                    )
                    if self._expires_at.tzinfo is None:
                        self._expires_at = self._expires_at.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

    async def _ensure_token_valid(self) -> None:
        """Check token expiry and refresh if needed.

        Refreshes the access token using the refresh_token if the current
        token is expired or within the grace window (5 minutes).
        Updates tokens.json on disk after a successful refresh.
        """
        if not self.access_token or not self._refresh_token or not self._expires_at:
            return

        now = datetime.now(timezone.utc)
        grace = timedelta(seconds=self._REFRESH_GRACE_SECONDS)

        if self._expires_at - grace > now:
            return  # Token still valid

        # Token expired or about to expire — refresh it
        import sys
        remaining = (self._expires_at - now).total_seconds()
        print(f"\n    [oauth] Token expires in {remaining:.0f}s, refreshing...", file=sys.stderr, end="")
        try:
            async with httpx.AsyncClient(timeout=30.0) as refresh_client:
                resp = await refresh_client.post(
                    "https://www.snipara.com/api/oauth/token",
                    json={
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                    },
                )
                if resp.status_code != 200:
                    print(f" FAILED (HTTP {resp.status_code}: {resp.text[:100]})", file=sys.stderr)
                    return  # Refresh failed, keep using existing token

                data = resp.json()
                self.access_token = data["access_token"]
                if data.get("refresh_token"):
                    self._refresh_token = data["refresh_token"]

                expires_in = data.get("expires_in", 3600)
                self._expires_at = now + timedelta(seconds=expires_in)

                print(f" OK (new token valid for {expires_in}s)", file=sys.stderr)

                # Invalidate existing client so it gets recreated with new token
                if self._client:
                    await self._client.aclose()
                    self._client = None

                # Update tokens.json on disk
                tokens_file = Path.home() / ".snipara" / "tokens.json"
                if tokens_file.exists() and self._project_id:
                    try:
                        tokens = json.loads(tokens_file.read_text())
                        if self._project_id in tokens:
                            tokens[self._project_id]["access_token"] = self.access_token
                            tokens[self._project_id]["expires_at"] = self._expires_at.isoformat()
                            if data.get("refresh_token"):
                                tokens[self._project_id]["refresh_token"] = self._refresh_token
                            tokens_file.write_text(json.dumps(tokens, indent=2))
                    except (json.JSONDecodeError, KeyError):
                        pass
        except Exception as exc:
            print(f" ERROR ({exc})", file=sys.stderr)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client. Refreshes token if needed."""
        await self._ensure_token_valid()

        if self._client is None:
            # Determine auth header - api.snipara.com supports both X-API-Key and Authorization
            if self.access_token:
                headers = {"Authorization": f"Bearer {self.access_token}"}
            elif self.api_key:
                # Use X-API-Key header (preferred for API keys)
                headers = {"X-API-Key": self.api_key}
            else:
                raise ValueError("No authentication configured. Run 'snipara-mcp-login' or set SNIPARA_API_KEY")

            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=60.0,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def context_query(
        self,
        query: str,
        max_tokens: int = 4000,
        search_mode: str = "keyword",
        include_metadata: bool = True,
        prefer_summaries: bool = False,
    ) -> ContextQueryResult:
        """Call rlm_context_query to get optimized context.

        Args:
            query: The question/query to get context for
            max_tokens: Maximum tokens to return
            search_mode: Search strategy (keyword, semantic, hybrid)
            include_metadata: Include file paths, line numbers, scores
            prefer_summaries: Prefer stored summaries over full content

        Returns:
            ContextQueryResult with optimized context
        """
        client = await self._get_client()

        url = f"{self.base_url}/{self.project_slug}"
        # Use MCP JSON-RPC format
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "rlm_context_query",
                "arguments": {
                    "query": query,
                    "max_tokens": max_tokens,
                    "search_mode": search_mode,
                    "include_metadata": include_metadata,
                    "prefer_summaries": prefer_summaries,
                },
            },
        }

        response = await client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        # Parse MCP JSON-RPC response
        if "error" in data:
            raise ValueError(f"API error: {data['error'].get('message', 'Unknown error')}")

        # Extract result from JSON-RPC response
        rpc_result = data.get("result", {})
        content = rpc_result.get("content", [])
        if content and content[0].get("type") == "text":
            result = json.loads(content[0].get("text", "{}"))
        else:
            result = {}

        return self._parse_context_result(result, query, max_tokens, search_mode)

    def _parse_context_result(
        self, result: dict, query: str, max_tokens: int, search_mode: str
    ) -> ContextQueryResult:
        """Parse API response into ContextQueryResult."""
        sections = []
        for s in result.get("sections", []):
            sections.append(ContextSection(
                title=s.get("title", ""),
                content=s.get("content", ""),
                file=s.get("file", ""),
                lines=tuple(s.get("lines", [0, 0])),
                relevance_score=s.get("relevance_score", 0.0),
                token_count=s.get("token_count", 0),
                truncated=s.get("truncated", False),
            ))

        return ContextQueryResult(
            sections=sections,
            total_tokens=result.get("total_tokens", 0),
            max_tokens=result.get("max_tokens", max_tokens),
            query=result.get("query", query),
            search_mode=result.get("search_mode", search_mode),
            suggestions=result.get("suggestions", []),
            summaries_used=result.get("summaries_used", 0),
            shared_context_included=result.get("shared_context_included", False),
            shared_context_tokens=result.get("shared_context_tokens", 0),
            timing=result.get("timing"),
            system_instructions=result.get("system_instructions", ""),
        )

    def _parse_jsonrpc_response(self, data: dict) -> dict:
        """Parse MCP JSON-RPC response and extract result dict."""
        if "error" in data:
            raise ValueError(f"API error: {data['error'].get('message', 'Unknown error')}")
        rpc_result = data.get("result", {})
        content = rpc_result.get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0].get("text", "{}"))
        return {}

    async def decompose(
        self,
        query: str,
        max_depth: int = 2,
    ) -> dict:
        """Call rlm_decompose to break query into sub-queries.

        Args:
            query: Complex question to decompose
            max_depth: Maximum recursion depth

        Returns:
            Decomposition result with sub-queries
        """
        client = await self._get_client()

        url = f"{self.base_url}/{self.project_slug}"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "rlm_decompose",
                "arguments": {
                    "query": query,
                    "max_depth": max_depth,
                },
            },
        }

        response = await client.post(url, json=payload)
        response.raise_for_status()

        return self._parse_jsonrpc_response(response.json())

    async def multi_query(
        self,
        queries: list[str],
        max_tokens: int = 8000,
    ) -> dict:
        """Call rlm_multi_query to execute multiple queries.

        Args:
            queries: List of queries to execute
            max_tokens: Total token budget

        Returns:
            Multi-query result with sections for each query
        """
        client = await self._get_client()

        url = f"{self.base_url}/{self.project_slug}"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "rlm_multi_query",
                "arguments": {
                    "queries": [{"query": q} for q in queries],
                    "max_tokens": max_tokens,
                },
            },
        }

        response = await client.post(url, json=payload)
        response.raise_for_status()

        return self._parse_jsonrpc_response(response.json())

    async def execute_python(
        self,
        code: str,
        session_id: str = "benchmark",
        profile: str = "default",
        timeout: Optional[int] = None,
    ) -> dict:
        """Execute Python code in RLM-Runtime sandboxed REPL.

        Args:
            code: Python code to execute
            session_id: Session ID for isolated context (variables persist across calls)
            profile: Execution profile (quick=5s, default=30s, analysis=120s, extended=300s)
            timeout: Optional timeout override in seconds (max 300)

        Returns:
            Execution result with output, result, and any errors
        """
        client = await self._get_client()

        url = f"{self.base_url}/{self.project_slug}"
        arguments = {
            "code": code,
            "session_id": session_id,
            "profile": profile,
        }
        if timeout:
            arguments["timeout"] = timeout

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "execute_python",
                "arguments": arguments,
            },
        }

        response = await client.post(url, json=payload)
        response.raise_for_status()

        return self._parse_jsonrpc_response(response.json())

    async def set_repl_context(
        self,
        key: str,
        value: str,
        session_id: str = "benchmark",
    ) -> dict:
        """Set a variable in REPL context for later use.

        Args:
            key: Variable name
            value: JSON-encoded value to store
            session_id: Session ID (default: 'benchmark')

        Returns:
            Result confirming the variable was set
        """
        client = await self._get_client()

        url = f"{self.base_url}/{self.project_slug}"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "set_repl_context",
                "arguments": {
                    "key": key,
                    "value": value,
                    "session_id": session_id,
                },
            },
        }

        response = await client.post(url, json=payload)
        response.raise_for_status()

        return self._parse_jsonrpc_response(response.json())

    async def clear_repl_context(self, session_id: str = "benchmark") -> dict:
        """Clear all variables from REPL context.

        Args:
            session_id: Session ID to clear (default: 'benchmark')

        Returns:
            Result confirming context was cleared
        """
        client = await self._get_client()

        url = f"{self.base_url}/{self.project_slug}"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "clear_repl_context",
                "arguments": {
                    "session_id": session_id,
                },
            },
        }

        response = await client.post(url, json=payload)
        response.raise_for_status()

        return self._parse_jsonrpc_response(response.json())


class MockSniparaClient(SniparaClient):
    """Mock client for testing without API calls.

    Uses local documentation instead of API calls.
    """

    def __init__(self, docs_content: str, **kwargs):
        """Initialize mock client.

        Args:
            docs_content: Full documentation content to use
        """
        super().__init__(**kwargs)
        self.docs_content = docs_content
        self._sections = self._parse_sections(docs_content)

    def _parse_sections(self, content: str) -> list[dict]:
        """Parse documentation into sections."""
        sections = []
        lines = content.split("\n")
        current_section = None
        current_content = []
        start_line = 1

        for i, line in enumerate(lines, 1):
            if line.startswith("#"):
                # Save previous section
                if current_section:
                    sections.append({
                        "title": current_section,
                        "content": "\n".join(current_content).strip(),
                        "start_line": start_line,
                        "end_line": i - 1,
                    })
                # Start new section
                current_section = line.lstrip("#").strip()
                current_content = []
                start_line = i
            else:
                current_content.append(line)

        # Save last section
        if current_section:
            sections.append({
                "title": current_section,
                "content": "\n".join(current_content).strip(),
                "start_line": start_line,
                "end_line": len(lines),
            })

        return sections

    async def context_query(
        self,
        query: str,
        max_tokens: int = 4000,
        search_mode: str = "keyword",
        include_metadata: bool = True,
        prefer_summaries: bool = False,
    ) -> ContextQueryResult:
        """Mock context query using keyword matching."""
        query_terms = set(query.lower().split())

        # Score sections by keyword overlap
        scored_sections = []
        for section in self._sections:
            title_terms = set(section["title"].lower().split())
            content_terms = set(section["content"].lower().split())

            title_score = len(query_terms & title_terms) * 3
            content_score = len(query_terms & content_terms)
            total_score = title_score + content_score

            if total_score > 0:
                scored_sections.append((total_score, section))

        # Sort by score and select top sections within budget
        scored_sections.sort(key=lambda x: x[0], reverse=True)

        result_sections = []
        total_tokens = 0

        for score, section in scored_sections:
            # Estimate tokens (4 chars per token)
            section_tokens = len(section["content"]) // 4

            if total_tokens + section_tokens > max_tokens:
                break

            result_sections.append(ContextSection(
                title=section["title"],
                content=section["content"],
                file="CLAUDE.md",
                lines=(section["start_line"], section["end_line"]),
                relevance_score=min(1.0, score / 10),
                token_count=section_tokens,
            ))
            total_tokens += section_tokens

        return ContextQueryResult(
            sections=result_sections,
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            query=query,
            search_mode=search_mode,
            suggestions=[],
        )


async def create_client(
    use_real_api: bool = True,
    api_key: Optional[str] = None,
    access_token: Optional[str] = None,
    project_slug: str = "snipara",
    docs_content: Optional[str] = None,
) -> SniparaClient:
    """Factory function to create appropriate client.

    Authentication priority (OAuth preferred):
        1. access_token parameter (OAuth)
        2. OAuth token from ~/.snipara/tokens.json (auto-loaded by SniparaClient)
        3. api_key parameter (deprecated)

    Args:
        use_real_api: Whether to use real Snipara API
        api_key: API key - DEPRECATED, use OAuth instead
        access_token: OAuth access token (preferred)
        project_slug: Project slug for API
        docs_content: Documentation content for mock client

    Returns:
        SniparaClient or MockSniparaClient instance
    """
    if use_real_api:
        # OAuth token takes priority over API key
        return SniparaClient(
            api_key=api_key,
            access_token=access_token,
            project_slug=project_slug,
        )
    elif docs_content:
        return MockSniparaClient(docs_content=docs_content)
    else:
        raise ValueError("docs_content required for mock client")
