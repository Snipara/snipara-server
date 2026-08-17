"""MCP Streamable HTTP Transport for Snipara.

This module implements the MCP (Model Context Protocol) Streamable HTTP transport
specification, enabling direct connections from MCP-compatible AI clients.

Supported Clients:
    - MCP client (Anthropic)
    - Cursor IDE
    - ChatGPT (with MCP support)
    - Windsurf
    - Any MCP-compatible client

Protocol:
    Uses JSON-RPC 2.0 over HTTP with the following methods:
    - initialize: Establish connection and exchange capabilities
    - tools/list: List available tools
    - tools/call: Execute a tool with arguments
    - ping: Keep-alive check

Endpoints:
    POST /mcp/{project_id}  - Main JSON-RPC endpoint for tool execution
    GET  /mcp/{project_id}  - SSE endpoint for server-initiated messages

Authentication:
    Accepts either:
    - X-API-Key header: the local API key configured for this server
    - Authorization: Bearer header: the same local API key

Example Configuration (MCP client .mcp.json):
    {
        "mcpServers": {
            "snipara": {
                "type": "http",
                "url": "http://localhost:8000/mcp/{project_slug}",
                "headers": {"X-API-Key": "rlm_..."}
            }
        }
    }

Note:
    The OSS transport exposes project-scoped MCP only. Team and multi-client
    routes belong to the private Cloud and are intentionally absent.
"""

import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from . import __version__
from .auth import enforce_tool_scope
from .mcp import MCP_TOOL_DEFINITIONS, MCP_TOOL_NAME_SET, jsonrpc_error, jsonrpc_response
from .mcp.validation import validate_request
from .models import Plan, ToolName
from .rlm_engine import RLMEngine
from .usage import track_usage

# ============ HELPERS ============


def _get_client_ip(request: Request) -> str | None:
    """Extract client IP from X-Forwarded-For header or direct connection."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


# ============ ROUTER CONFIGURATION ============

router = APIRouter(prefix="/mcp", tags=["MCP Transport"])

#: MCP protocol version (spec: 2024-11-05)
MCP_VERSION = "2024-11-05"


# ============ REQUEST HANDLERS ============


async def handle_call_tool(
    id: Any,
    params: dict,
    project_id: str,
    plan: Plan,
    access_level: str = "EDITOR",
    user_id: str | None = None,
    team_id: str | None = None,
    auth_info: dict | None = None,
) -> dict:
    """Handle MCP tools/call request.

    Executes a tool through the RLMEngine and tracks usage.

    Args:
        id: JSON-RPC request ID
        params: Tool call parameters containing:
            - name: Tool name (e.g., "rlm_context_query")
            - arguments: Tool-specific arguments
        project_id: Database project ID
        plan: Subscription plan for rate limiting
        access_level: API key access level (VIEWER, EDITOR, ADMIN)
        user_id: User ID from authentication (for shared context, memory)

    Returns:
        JSON-RPC response with tool result or error
    """
    tool_name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return jsonrpc_error(id, -32602, "Tool arguments must be an object")

    if tool_name not in MCP_TOOL_NAME_SET:
        return jsonrpc_error(id, -32602, f"Tool not available in OSS mode: {tool_name}")

    try:
        tool_enum = ToolName(tool_name)
    except ValueError:
        return jsonrpc_error(id, -32602, f"Unknown tool: {tool_name}")

    try:
        enforce_tool_scope(tool_name, auth_info)
        engine = RLMEngine(
            project_id,
            plan=plan,
            access_level=access_level,
            user_id=user_id,
            team_id=team_id,
        )
        result = await engine.execute(tool_enum, arguments)

        await track_usage(
            project_id=project_id,
            tool=tool_name,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=0,
            success=True,
        )

        return jsonrpc_response(
            id,
            {
                "content": [
                    {"type": "text", "text": json.dumps(result.data, indent=2, default=str)}
                ],
            },
        )
    except Exception as e:
        await track_usage(
            project_id=project_id,
            tool=tool_name,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            success=False,
            error=str(e),
        )
        return jsonrpc_error(id, -32000, str(e))


async def handle_request(
    body: dict,
    project_id: str,
    plan: Plan,
    access_level: str = "EDITOR",
    user_id: str | None = None,
    team_id: str | None = None,
    auth_info: dict | None = None,
) -> dict | None:
    """Handle a single JSON-RPC request.

    Routes requests to appropriate handlers based on method.

    Supported Methods:
        - initialize: Returns server info and capabilities
        - tools/list: Returns available tool definitions
        - tools/call: Executes a tool
        - ping: Returns empty response (keep-alive)

    Args:
        body: JSON-RPC request body
        project_id: Database project ID
        plan: Subscription plan
        access_level: API key access level (VIEWER, EDITOR, ADMIN)
        user_id: User ID from authentication (for shared context, memory)

    Returns:
        JSON-RPC response dict, or None for notifications (requests without id)
    """
    method, id, params = body.get("method"), body.get("id"), body.get("params", {})

    if id is None:  # Notification
        return None

    if method == "initialize":
        return jsonrpc_response(
            id,
            {
                "protocolVersion": MCP_VERSION,
                "serverInfo": {"name": "snipara", "version": __version__},
                "capabilities": {"tools": {}},
            },
        )
    elif method == "tools/list":
        return jsonrpc_response(id, {"tools": MCP_TOOL_DEFINITIONS})
    elif method == "tools/call":
        return await handle_call_tool(
            id, params, project_id, plan, access_level, user_id, team_id, auth_info
        )
    elif method == "ping":
        return jsonrpc_response(id, {})
    else:
        return jsonrpc_error(id, -32601, f"Method not found: {method}")


# ============ HTTP ENDPOINTS ============


@router.post("/{owner}/{repo}")
async def mcp_endpoint_repo(
    owner: str,
    repo: str,
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
):
    """Same as /mcp/{project_id}, but accepts a GitHub-style `owner/repo`
    identifier so the CLI can send its auto-resolved owner/repo directly
    (FastAPI doesn't decode %2F on single-segment path params).
    """
    return await mcp_endpoint(f"{owner}/{repo}", request, x_api_key, authorization)


@router.post("/{project_id}")
async def mcp_endpoint(
    project_id: str,
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
):
    """MCP Streamable HTTP endpoint.

    Accepts authentication via either X-API-Key or Authorization: Bearer header.

    Config example (MCP client):
    ```json
    {"mcpServers": {"snipara": {"type": "http", "url": "http://localhost:8000/mcp/{project_id}", "headers": {"X-API-Key": "<SNIPARA_LOCAL_API_KEY>"}}}}
    ```

    Alternative (Authorization Bearer):
    ```json
    {"mcpServers": {"snipara": {"type": "http", "url": "http://localhost:8000/mcp/{project_id}", "headers": {"Authorization": "Bearer <SNIPARA_LOCAL_API_KEY>"}}}}
    ```
    """
    # Accept X-API-Key header (preferred) or Authorization: Bearer
    if x_api_key:
        api_key = x_api_key
    elif authorization:
        api_key = authorization[7:] if authorization.startswith("Bearer ") else authorization
    else:
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing authentication. Set X-API-Key to SNIPARA_LOCAL_API_KEY."
            ),
        )

    client_ip = _get_client_ip(request)
    api_key_info, plan, error, actual_project_id = await validate_request(
        project_id, api_key, client_ip=client_ip
    )
    if error:
        raise HTTPException(status_code=401 if "Invalid" in error else 429, detail=error)

    # Extract access level from validated API key (defaults to EDITOR if not set)
    access_level = api_key_info.get("access_level", "EDITOR") if api_key_info else "EDITOR"
    # Extract user_id for shared context and memory operations
    user_id = api_key_info.get("user_id") if api_key_info else None

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(jsonrpc_error(None, -32700, "Parse error"), status_code=400)

    # Use actual database ID for all operations (not URL slug)
    if isinstance(body, list):
        responses = [
            r
            for req in body
            if (
                r := await handle_request(
                    req,
                    actual_project_id,
                    plan,
                    access_level,
                    user_id,
                    api_key_info.get("team_id") if api_key_info else None,
                    api_key_info,
                )
            )
        ]
        return JSONResponse(responses)

    response = await handle_request(
        body,
        actual_project_id,
        plan,
        access_level,
        user_id,
        api_key_info.get("team_id") if api_key_info else None,
        api_key_info,
    )
    return JSONResponse(response) if response else Response(status_code=204)


@router.get("/{project_id}")
async def mcp_sse(
    project_id: str,
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
):
    """MCP Server-Sent Events (SSE) endpoint.

    Provides a persistent connection for server-initiated messages.
    Currently used for keep-alive pings every 30 seconds.

    Args:
        project_id: Project ID or slug
        x_api_key: API key via X-API-Key header
        authorization: API key via Authorization: Bearer header

    Returns:
        SSE stream with JSON messages:
        - {"type": "connected"} on connection
        - {"type": "ping"} every 30 seconds
    """
    # Accept X-API-Key header (preferred) or Authorization: Bearer
    if x_api_key:
        api_key = x_api_key
    elif authorization:
        api_key = authorization[7:] if authorization.startswith("Bearer ") else authorization
    else:
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing authentication. Set X-API-Key to SNIPARA_LOCAL_API_KEY."
            ),
        )

    client_ip = _get_client_ip(request)
    _, _, error, _ = await validate_request(project_id, api_key, client_ip=client_ip)
    if error:
        raise HTTPException(status_code=401, detail=error)

    async def stream():
        import asyncio

        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        try:
            while True:
                await asyncio.sleep(30)
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
