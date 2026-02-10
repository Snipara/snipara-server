"""MCP (Model Context Protocol) transport module.

This module contains components for the MCP Streamable HTTP transport:
- Tool definitions for tools/list
- JSON-RPC 2.0 helpers
- Request validation (requires config, import from .validation directly)

The main transport router and handlers remain in mcp_transport.py.
"""

from .jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    SERVER_ERROR,
    jsonrpc_error,
    jsonrpc_response,
)
from .tool_defs import TOOL_DEFINITIONS

# Note: validate_request requires config and is not imported at module level.
# Import directly when needed: from src.mcp.validation import validate_request

__all__ = [
    # Tool definitions
    "TOOL_DEFINITIONS",
    # JSON-RPC helpers
    "jsonrpc_response",
    "jsonrpc_error",
    "PARSE_ERROR",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "INVALID_PARAMS",
    "INTERNAL_ERROR",
    "SERVER_ERROR",
]
