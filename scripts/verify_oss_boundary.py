"""Fail if the published runtime accidentally exposes Cloud-only surfaces."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.contract import OSS_CONTRACT  # noqa: E402
from src.mcp.tool_defs import (
    MCP_TOOL_DEFINITIONS,
    MCP_TOOL_NAMES,
    OSS_EXCLUDED_TOOL_NAMES,
)  # noqa: E402

FORBIDDEN_ROUTE_MARKERS = (
    "/v1/admin",
    "/v1/team/",
    "/mcp/team/",
)


def _route_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    routes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"get", "post", "put", "patch", "delete"}:
            continue
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            routes.add(node.args[0].value)
    return routes


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def main() -> int:
    server_routes = _route_literals(ROOT / "src/server.py")
    transport_routes = _route_literals(ROOT / "src/mcp_transport.py")
    all_routes = server_routes | transport_routes
    forbidden_routes = sorted(
        route for route in all_routes if any(marker in route for marker in FORBIDDEN_ROUTE_MARKERS)
    )
    if forbidden_routes:
        raise SystemExit(f"OSS boundary violation: forbidden routes exposed: {forbidden_routes}")

    leaked_tools = sorted(set(MCP_TOOL_NAMES) & set(OSS_EXCLUDED_TOOL_NAMES))
    if leaked_tools:
        raise SystemExit(f"OSS boundary violation: excluded tools exposed: {leaked_tools}")

    if _contains_key(MCP_TOOL_DEFINITIONS, "external_user_id"):
        raise SystemExit("OSS boundary violation: external_user_id remains in public tool metadata")

    capabilities = json.dumps(MCP_TOOL_DEFINITIONS).lower()
    if "integrator" in capabilities or "tenant_profile" in capabilities:
        raise SystemExit("OSS boundary violation: hosted identity wording remains in public tool metadata")

    expected_routes = {"/health", "/ready", "/capabilities"}
    missing_routes = sorted(expected_routes - server_routes)
    if missing_routes:
        raise SystemExit(f"OSS contract violation: required routes missing: {missing_routes}")

    print(f"OSS boundary verified: {OSS_CONTRACT}; {len(MCP_TOOL_NAMES)} public tools; no Cloud-only routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
