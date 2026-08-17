"""Regression tests for the public OSS boundary and compatibility contract."""

from fastapi.testclient import TestClient

from src.contract import OSS_CONTRACT, public_capabilities
from src.mcp.tool_defs import MCP_TOOL_DEFINITIONS, MCP_TOOL_NAMES, OSS_EXCLUDED_TOOL_NAMES
from src.server import app


def _route_paths() -> set[str]:
    return {route.path for route in app.routes if getattr(route, "path", None)}


def test_capabilities_document_is_public_and_non_secret():
    client = TestClient(app)
    response = client.get("/capabilities")

    assert response.status_code == 200
    assert response.json() == public_capabilities()
    assert response.json()["contract"] == OSS_CONTRACT
    assert "X-API-Key" in response.json()["authentication"]["schemes"]
    assert "X-Snipara-Contract" not in response.json()
    assert response.headers["x-snipara-contract"] == OSS_CONTRACT


def test_cloud_only_routes_are_not_registered():
    routes = _route_paths()

    assert "/capabilities" in routes
    assert not any(
        path.startswith(("/v1/admin", "/v1/team/", "/mcp/team/")) for path in routes
    )


def test_cloud_only_tools_and_identity_fields_are_not_public():
    assert not set(MCP_TOOL_NAMES) & set(OSS_EXCLUDED_TOOL_NAMES)

    def walk(value):
        if isinstance(value, dict):
            yield from value.keys()
            for item in value.values():
                yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)

    serialized_keys = {str(key) for key in walk(MCP_TOOL_DEFINITIONS)}
    assert "external_user_id" not in serialized_keys

    serialized = str(MCP_TOOL_DEFINITIONS).lower()
    assert "integrator" not in serialized
    assert "tenant_profile" not in serialized
