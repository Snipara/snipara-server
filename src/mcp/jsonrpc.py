"""JSON-RPC 2.0 helpers for MCP transport.

This module provides utility functions for creating JSON-RPC 2.0
responses and errors according to the specification.

See: https://www.jsonrpc.org/specification
"""

from typing import Any


def jsonrpc_response(id: Any, result: Any) -> dict:
    """Create a JSON-RPC 2.0 success response.

    Args:
        id: Request ID (must match the request)
        result: The result payload

    Returns:
        JSON-RPC 2.0 response dict
    """
    return {"jsonrpc": "2.0", "id": id, "result": result}


def jsonrpc_error(id: Any, code: int, message: str) -> dict:
    """Create a JSON-RPC 2.0 error response.

    Standard error codes:
        -32700: Parse error
        -32600: Invalid request
        -32601: Method not found
        -32602: Invalid params
        -32603: Internal error
        -32000 to -32099: Server errors (application-specific)

    Args:
        id: Request ID (can be None for parse errors)
        code: Error code (negative integer)
        message: Human-readable error message

    Returns:
        JSON-RPC 2.0 error response dict
    """
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
SERVER_ERROR = -32000  # Base for application-specific errors
