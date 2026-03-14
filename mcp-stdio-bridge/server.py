#!/usr/bin/env python3
"""
Snipara MCP Server - stdio bridge to Snipara REST API.

This MCP server bridges Claude Code to the Snipara context optimization API.
It exposes the same tools as the original rlm-repl but uses Snipara's
semantic search and context optimization engine.

Usage:
    python server.py

Environment variables:
    SNIPARA_API_URL: Base URL of Snipara API (default: http://localhost:3001)
    SNIPARA_API_KEY: API key for authentication
    SNIPARA_PROJECT_ID: Project ID to query
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# Configuration from environment
API_URL = os.environ.get("SNIPARA_API_URL", "http://localhost:3001")
API_KEY = os.environ.get("SNIPARA_API_KEY", "")
PROJECT_ID = os.environ.get("SNIPARA_PROJECT_ID", "")

# Session context (local cache)
_session_context: str = ""

# Create MCP server
server = Server("snipara")


def get_headers() -> dict[str, str]:
    """Get API request headers."""
    return {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }


async def call_snipara_api(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    """Call the Snipara MCP API."""
    url = f"{API_URL}/v1/{PROJECT_ID}/mcp"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            headers=get_headers(),
            json={"tool": tool, "params": params},
        )
        response.raise_for_status()
        return response.json()


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available Snipara tools."""
    return [
        Tool(
            name="rlm_ask",
            description="""Query project documentation with a question.

Uses Snipara's semantic search engine to find relevant documentation
and return optimized context. Supports hybrid search (keyword + semantic).

Examples:
- "How does authentication work?"
- "What are the API endpoints?"
- "Where is the database schema defined?"

Best for: Understanding features, finding code locations, getting answers.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask about the documentation"
                    }
                },
                "required": ["question"]
            }
        ),
        Tool(
            name="rlm_search",
            description="""Search documentation for a pattern (regex supported).

Returns matching lines with file paths and line numbers.
Useful for finding specific function names, configuration keys, or code patterns.

Examples:
- "requireAuth" - find auth helper usage
- "DATABASE_URL" - find environment variable usage
- "async def" - find async function definitions""",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return (default 20)",
                        "default": 20
                    }
                },
                "required": ["pattern"]
            }
        ),
        Tool(
            name="rlm_inject",
            description="""Inject session context for subsequent queries.

Sets task-specific context that will be included in all future queries.
Use this when starting a new task to focus the documentation search.

Examples:
- "Task: Fix authentication bug. Files: auth.ts, middleware.ts"
- "Focus: Database migrations and schema"
- "Working on: API endpoint implementation"

The context persists until cleared with rlm_clear_context.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "The context to inject (task description, files, focus areas)"
                    },
                    "append": {
                        "type": "boolean",
                        "description": "Append to existing context instead of replacing",
                        "default": False
                    }
                },
                "required": ["context"]
            }
        ),
        Tool(
            name="rlm_context",
            description="""Show the current session context.

Returns the currently injected session context, if any.
Useful for checking what context is active before querying.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="rlm_clear_context",
            description="""Clear the session context.

Removes any injected session context. Use when switching tasks
or when the context is no longer relevant.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="rlm_stats",
            description="""Show documentation statistics.

Returns information about loaded documentation files, total chunks,
and other metadata. Useful for understanding the scope of indexed docs.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="rlm_sections",
            description="""List all documentation sections.

Returns a list of all indexed documents and their sections.
Useful for understanding what topics are documented.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="rlm_read",
            description="""Read specific lines from documentation.

Returns the content of a specific line range from a document.
Useful after searching to read the full context around a match.

Example: Read lines 100-150 from docs/auth.md""",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_line": {
                        "type": "integer",
                        "description": "Starting line number"
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Ending line number"
                    }
                },
                "required": ["start_line", "end_line"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    global _session_context

    try:
        if name == "rlm_ask":
            question = arguments["question"]

            # Include session context in the query if set
            full_query = question
            if _session_context:
                full_query = f"Context: {_session_context}\n\nQuestion: {question}"

            # Call Snipara context_query API
            result = await call_snipara_api("rlm_context_query", {
                "query": full_query,
                "max_tokens": 4000,
                "search_mode": "hybrid",
                "include_metadata": True,
            })

            if result.get("success"):
                data = result.get("result", {})
                sections = data.get("sections", [])

                if sections:
                    response_parts = ["## Relevant Documentation\n"]
                    for section in sections:
                        title = section.get("title", "Untitled")
                        file_path = section.get("file", "unknown")
                        content = section.get("content", "")
                        score = section.get("relevance_score", 0)

                        response_parts.append(f"### {title}")
                        response_parts.append(f"*File: {file_path} | Relevance: {score:.2f}*\n")
                        response_parts.append(content)
                        response_parts.append("")

                    total_tokens = data.get("total_tokens", 0)
                    timing = result.get("usage", {})
                    latency = timing.get("latency_ms", 0)

                    response_parts.append("---")
                    response_parts.append(f"*{len(sections)} sections, {total_tokens} tokens, {latency}ms*")
                    response = "\n".join(response_parts)
                else:
                    response = "No relevant documentation found for your query."
            else:
                response = f"**Error:** {result.get('error', 'Unknown error')}"

            return [TextContent(type="text", text=response)]

        elif name == "rlm_search":
            pattern = arguments["pattern"]
            max_results = arguments.get("max_results", 20)

            # Call Snipara search API
            result = await call_snipara_api("rlm_search", {
                "pattern": pattern,
            })

            if result.get("success"):
                data = result.get("result", {})
                matches = data.get("matches", [])

                if matches:
                    lines = [f"Found {len(matches)} matches for '{pattern}':\n"]
                    for match in matches[:max_results]:
                        line_num = match.get("line_number", 0)
                        file_path = match.get("file", "")
                        content = match.get("content", "")[:120]
                        lines.append(f"  {file_path}:{line_num}: {content}")

                    if len(matches) > max_results:
                        lines.append(f"\n... and {len(matches) - max_results} more matches")
                    response = "\n".join(lines)
                else:
                    response = f"No matches found for '{pattern}'"
            else:
                response = f"**Error:** {result.get('error', 'Unknown error')}"

            return [TextContent(type="text", text=response)]

        elif name == "rlm_inject":
            context_text = arguments["context"]
            append = arguments.get("append", False)

            if append and _session_context:
                _session_context = _session_context + "\n\n" + context_text
            else:
                _session_context = context_text

            # Also save to Snipara session context
            try:
                await call_snipara_api("rlm_inject", {
                    "context": _session_context,
                })
            except Exception:
                pass  # Ignore if API doesn't support this yet

            response = f"""Session context {'appended' if append else 'set'} ({len(_session_context)} chars).

**Current context:**
{_session_context[:500]}{'...' if len(_session_context) > 500 else ''}"""

            return [TextContent(type="text", text=response)]

        elif name == "rlm_context":
            if _session_context:
                response = f"""**Session Context** ({len(_session_context)} chars):

{_session_context}"""
            else:
                response = "No session context set. Use `rlm_inject` to add context."

            return [TextContent(type="text", text=response)]

        elif name == "rlm_clear_context":
            if _session_context:
                _session_context = ""
                try:
                    await call_snipara_api("rlm_clear_context", {})
                except Exception:
                    pass
                response = "Session context cleared."
            else:
                response = "No session context to clear."

            return [TextContent(type="text", text=response)]

        elif name == "rlm_stats":
            result = await call_snipara_api("rlm_stats", {})

            if result.get("success"):
                data = result.get("result", {})
                response = f"""**Documentation Statistics**

- Documents indexed: {data.get('document_count', 'N/A')}
- Total chunks: {data.get('chunk_count', 'N/A')}
- Total tokens: {data.get('total_tokens', 'N/A'):,}

**Project:** {PROJECT_ID}
**API:** {API_URL}"""
            else:
                response = f"**Error:** {result.get('error', 'Unknown error')}"

            return [TextContent(type="text", text=response)]

        elif name == "rlm_sections":
            result = await call_snipara_api("rlm_sections", {})

            if result.get("success"):
                data = result.get("result", {})
                sections = data.get("sections", [])

                lines = ["**Indexed Documents:**\n"]
                for section in sections:
                    path = section.get("path", "")
                    chunk_count = section.get("chunk_count", 0)
                    lines.append(f"- {path} ({chunk_count} chunks)")

                response = "\n".join(lines)
            else:
                response = f"**Error:** {result.get('error', 'Unknown error')}"

            return [TextContent(type="text", text=response)]

        elif name == "rlm_read":
            start = arguments["start_line"]
            end = arguments["end_line"]

            result = await call_snipara_api("rlm_read", {
                "start_line": start,
                "end_line": end,
            })

            if result.get("success"):
                data = result.get("result", {})
                content = data.get("content", "")
                response = f"**Lines {start}-{end}:**\n\n```\n{content}\n```"
            else:
                response = f"**Error:** {result.get('error', 'Unknown error')}"

            return [TextContent(type="text", text=response)]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"**API Error:** {e.response.status_code} - {e.response.text}")]
    except httpx.ConnectError:
        return [TextContent(type="text", text=f"**Connection Error:** Cannot reach Snipara API at {API_URL}. Is the server running?")]
    except Exception as e:
        return [TextContent(type="text", text=f"**Error:** {type(e).__name__}: {str(e)}")]


async def main():
    """Run the MCP server."""
    if not API_KEY:
        print("Warning: SNIPARA_API_KEY not set", file=sys.stderr)
    if not PROJECT_ID:
        print("Warning: SNIPARA_PROJECT_ID not set", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
