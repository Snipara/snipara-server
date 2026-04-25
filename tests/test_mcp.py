"""Tests for the mcp module.

These tests verify the extracted MCP transport components work correctly.
Note: validation.py tests are skipped as they require full environment setup.
"""

import pytest

from src.mcp.jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    SERVER_ERROR,
    jsonrpc_error,
    jsonrpc_response,
)
from src.mcp.tool_defs import TOOL_DEFINITIONS


class TestJsonRpcHelpers:
    """Tests for JSON-RPC helper functions."""

    def test_jsonrpc_response_basic(self):
        """Test basic JSON-RPC response creation."""
        result = jsonrpc_response(1, {"data": "test"})
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["result"] == {"data": "test"}

    def test_jsonrpc_response_string_id(self):
        """Test JSON-RPC response with string ID."""
        result = jsonrpc_response("abc-123", "success")
        assert result["id"] == "abc-123"
        assert result["result"] == "success"

    def test_jsonrpc_response_null_result(self):
        """Test JSON-RPC response with null result."""
        result = jsonrpc_response(1, None)
        assert result["result"] is None

    def test_jsonrpc_error_basic(self):
        """Test basic JSON-RPC error creation."""
        result = jsonrpc_error(1, -32600, "Invalid request")
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["error"]["code"] == -32600
        assert result["error"]["message"] == "Invalid request"

    def test_jsonrpc_error_null_id(self):
        """Test JSON-RPC error with null ID (parse error case)."""
        result = jsonrpc_error(None, -32700, "Parse error")
        assert result["id"] is None
        assert result["error"]["code"] == -32700

    def test_jsonrpc_error_custom_code(self):
        """Test JSON-RPC error with custom error code."""
        result = jsonrpc_error(1, -32001, "Custom error")
        assert result["error"]["code"] == -32001


class TestErrorCodes:
    """Tests for JSON-RPC error code constants."""

    def test_parse_error(self):
        """Test PARSE_ERROR constant."""
        assert PARSE_ERROR == -32700

    def test_invalid_request(self):
        """Test INVALID_REQUEST constant."""
        assert INVALID_REQUEST == -32600

    def test_method_not_found(self):
        """Test METHOD_NOT_FOUND constant."""
        assert METHOD_NOT_FOUND == -32601

    def test_invalid_params(self):
        """Test INVALID_PARAMS constant."""
        assert INVALID_PARAMS == -32602

    def test_internal_error(self):
        """Test INTERNAL_ERROR constant."""
        assert INTERNAL_ERROR == -32603

    def test_server_error(self):
        """Test SERVER_ERROR constant."""
        assert SERVER_ERROR == -32000


class TestToolDefinitions:
    """Tests for TOOL_DEFINITIONS."""

    def test_tool_definitions_is_list(self):
        """Test TOOL_DEFINITIONS is a list."""
        assert isinstance(TOOL_DEFINITIONS, list)

    def test_tool_definitions_not_empty(self):
        """Test TOOL_DEFINITIONS has tools."""
        assert len(TOOL_DEFINITIONS) > 0

    def test_all_tools_have_name(self):
        """Test all tools have a name field."""
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert isinstance(tool["name"], str)
            assert tool["name"].startswith("rlm_")

    def test_all_tools_have_description(self):
        """Test all tools have a description field."""
        for tool in TOOL_DEFINITIONS:
            assert "description" in tool
            assert isinstance(tool["description"], str)
            assert len(tool["description"]) > 0

    def test_all_tools_have_input_schema(self):
        """Test all tools have an inputSchema field."""
        for tool in TOOL_DEFINITIONS:
            assert "inputSchema" in tool
            assert isinstance(tool["inputSchema"], dict)
            assert tool["inputSchema"].get("type") == "object"

    def test_context_query_tool_exists(self):
        """Test rlm_context_query tool is defined."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_context_query"), None)
        assert tool is not None
        assert "query" in tool["inputSchema"]["properties"]
        assert "max_tokens" in tool["inputSchema"]["properties"]
        assert "search_mode" in tool["inputSchema"]["properties"]

    def test_ask_tool_exists(self):
        """Test rlm_ask tool is defined."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_ask"), None)
        assert tool is not None
        assert "query" in tool["inputSchema"]["properties"]
        assert "query" in tool["inputSchema"]["required"]

    def test_search_tool_exists(self):
        """Test rlm_search tool is defined."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_search"), None)
        assert tool is not None
        assert "pattern" in tool["inputSchema"]["properties"]

    def test_memory_tools_exist(self):
        """Test agent memory tools are defined."""
        memory_tools = [
            "rlm_remember",
            "rlm_recall",
            "rlm_memories",
            "rlm_memory_invalidate",
            "rlm_memory_supersede",
            "rlm_forget",
        ]
        for name in memory_tools:
            tool = next((t for t in TOOL_DEFINITIONS if t["name"] == name), None)
            assert tool is not None, f"Tool {name} not found"

    def test_swarm_tools_exist(self):
        """Test multi-agent swarm tools are defined."""
        swarm_tools = [
            "rlm_swarm_create",
            "rlm_swarm_join",
            "rlm_claim",
            "rlm_release",
            "rlm_state_get",
            "rlm_state_set",
            "rlm_broadcast",
            "rlm_task_create",
            "rlm_task_claim",
            "rlm_task_complete",
        ]
        for name in swarm_tools:
            tool = next((t for t in TOOL_DEFINITIONS if t["name"] == name), None)
            assert tool is not None, f"Tool {name} not found"

    def test_orchestration_tools_exist(self):
        """Test RLM orchestration tools are defined."""
        orchestration_tools = [
            "rlm_load_document",
            "rlm_load_project",
            "rlm_orchestrate",
            "rlm_repl_context",
        ]
        for name in orchestration_tools:
            tool = next((t for t in TOOL_DEFINITIONS if t["name"] == name), None)
            assert tool is not None, f"Tool {name} not found"

    def test_get_chunk_tool_exists(self):
        """Test rlm_get_chunk tool is defined."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_get_chunk"), None)
        assert tool is not None
        assert "chunk_id" in tool["inputSchema"]["properties"]
        assert "chunk_id" in tool["inputSchema"]["required"]

    def test_reindex_tool_exists(self):
        """Test rlm_reindex tool is defined."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_reindex"), None)
        assert tool is not None
        properties = tool["inputSchema"]["properties"]
        assert "job_id" in properties
        assert properties["mode"]["enum"] == ["incremental", "full"]
        assert properties["kind"]["enum"] == ["doc", "code"]

    def test_document_sync_tools_expose_binary_contract(self):
        """Document sync tools should expose binary parser fields."""
        upload = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_upload_document"), None)
        sync = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_sync_documents"), None)

        assert upload is not None
        assert sync is not None
        upload_props = upload["inputSchema"]["properties"]
        assert upload_props["kind"]["enum"] == ["DOC", "BINARY"]
        assert "vsdx" in upload_props["format"]["enum"]

        item_props = sync["inputSchema"]["properties"]["documents"]["items"]["properties"]
        assert item_props["kind"]["enum"] == ["DOC", "BINARY"]
        assert "vsdx" in item_props["format"]["enum"]

    def test_tool_count(self):
        """Test expected number of tools."""
        # There should be 43 tools based on MCP_TOOLS_COMPLETE.md
        assert len(TOOL_DEFINITIONS) >= 40  # Allow some flexibility

    def test_unique_tool_names(self):
        """Test all tool names are unique."""
        names = [t["name"] for t in TOOL_DEFINITIONS]
        assert len(names) == len(set(names))


class TestToolSchemas:
    """Tests for individual tool schemas."""

    def test_context_query_search_modes(self):
        """Test rlm_context_query search mode enum values."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_context_query"), None)
        search_mode = tool["inputSchema"]["properties"]["search_mode"]
        assert search_mode["enum"] == ["keyword", "semantic", "hybrid"]
        assert search_mode["default"] == "hybrid"

    def test_context_query_max_tokens_limits(self):
        """Test rlm_context_query max_tokens limits."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_context_query"), None)
        max_tokens = tool["inputSchema"]["properties"]["max_tokens"]
        assert max_tokens["minimum"] == 100
        assert max_tokens["maximum"] == 100000
        assert max_tokens["default"] == 4000

    def test_decompose_max_depth_limits(self):
        """Test rlm_decompose max_depth limits."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_decompose"), None)
        max_depth = tool["inputSchema"]["properties"]["max_depth"]
        assert max_depth["minimum"] == 1
        assert max_depth["maximum"] == 5
        assert max_depth["default"] == 2

    def test_remember_type_enum(self):
        """Test rlm_remember type enum values."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_remember"), None)
        memory_type = tool["inputSchema"]["properties"]["type"]
        expected_types = ["fact", "decision", "learning", "preference", "todo", "context"]
        assert memory_type["enum"] == expected_types

    def test_remember_scope_enum(self):
        """Test rlm_remember scope enum values."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_remember"), None)
        scope = tool["inputSchema"]["properties"]["scope"]
        expected_scopes = ["agent", "project", "team", "user"]
        assert scope["enum"] == expected_scopes

    def test_recall_supports_inactive_controls(self):
        """Test rlm_recall exposes inactive-memory controls."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_recall"), None)
        props = tool["inputSchema"]["properties"]
        assert "include_inactive" in props
        assert props["include_inactive"]["default"] is False
        assert "warning_threshold" in props
        assert props["warning_threshold"]["default"] == 0.72

    def test_memories_supports_status_filter(self):
        """Test rlm_memories supports lifecycle filters."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_memories"), None)
        props = tool["inputSchema"]["properties"]
        assert props["status"]["enum"] == ["ACTIVE", "INVALIDATED", "SUPERSEDED"]
        assert props["include_inactive"]["default"] is False

    def test_memory_invalidate_requires_memory_id(self):
        """Test invalidate schema requires memory_id."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_memory_invalidate"), None)
        assert tool["inputSchema"]["required"] == ["memory_id"]

    def test_memory_supersede_requires_old_and_new_ids(self):
        """Test supersede schema links two memory IDs in the V2 contract."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_memory_supersede"), None)
        assert tool["inputSchema"]["required"] == ["old_memory_id", "new_memory_id"]

    def test_shared_context_categories(self):
        """Test rlm_shared_context category enum values."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_shared_context"), None)
        categories = tool["inputSchema"]["properties"]["categories"]["items"]
        expected = ["MANDATORY", "BEST_PRACTICES", "GUIDELINES", "REFERENCE"]
        assert categories["enum"] == expected

    def test_shared_context_management_tools_exist(self):
        """Shared context admin tools should be exposed in the contract."""
        expected_tools = {
            "rlm_create_collection",
            "rlm_get_collection_documents",
            "rlm_link_collection",
            "rlm_unlink_collection",
        }
        names = {tool["name"] for tool in TOOL_DEFINITIONS}
        assert expected_tools <= names

    def test_link_collection_categories(self):
        """rlm_link_collection should accept the standard shared-context categories."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_link_collection"), None)
        categories = tool["inputSchema"]["properties"]["enabled_categories"]["items"]
        expected = ["MANDATORY", "BEST_PRACTICES", "GUIDELINES", "REFERENCE"]
        assert categories["enum"] == expected

    def test_claim_resource_types(self):
        """Test rlm_claim resource_type enum values."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_claim"), None)
        resource_type = tool["inputSchema"]["properties"]["resource_type"]
        expected_types = ["file", "function", "module", "component", "other"]
        assert resource_type["enum"] == expected_types

    def test_swarm_join_roles(self):
        """Test rlm_swarm_join role enum values."""
        tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "rlm_swarm_join"), None)
        role = tool["inputSchema"]["properties"]["role"]
        expected_roles = ["coordinator", "worker", "observer"]
        assert role["enum"] == expected_roles
