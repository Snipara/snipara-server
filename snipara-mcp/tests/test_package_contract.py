"""Package-local regression tests for snipara-mcp."""

from pathlib import Path
import sys
import types

from typer.testing import CliRunner

import snipara_mcp
import snipara_mcp.auth as mcp_auth
import snipara_mcp.server as mcp_server
from snipara_mcp.cli import app
from snipara_mcp.tool_contract import MCP_TOOL_DEFINITIONS


def _package_version_from_pyproject() -> str:
    import tomllib

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_package_version_matches_pyproject() -> None:
    """The installed package should report the same version as pyproject.toml."""
    assert snipara_mcp.__version__ == _package_version_from_pyproject()


def test_cli_version_reports_package_version() -> None:
    """The CLI version command should reuse the package version."""
    runner = CliRunner()

    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert f"Snipara CLI v{snipara_mcp.__version__}" in result.stdout
    assert f"snipara-mcp: {snipara_mcp.__version__}" in result.stdout


def test_cli_tools_list_renders_tool_names(monkeypatch) -> None:
    """The generic tools list command should surface the remote tool inventory."""
    runner = CliRunner()

    async def fake_call_mcp_jsonrpc(api_url, project_slug, auth_header, method, params):
        assert method == "tools/list"
        assert project_slug == "snipara"
        return {
            "result": {
                "tools": [
                    {"name": "rlm_help", "description": "Recommend the right tool for a task."},
                    {"name": "rlm_session_memories", "description": "Load tiered session memories."},
                ]
            }
        }

    monkeypatch.setattr("snipara_mcp.cli.load_auth_header", lambda: "rlm_test")
    monkeypatch.setattr("snipara_mcp.cli.call_mcp_jsonrpc", fake_call_mcp_jsonrpc)

    result = runner.invoke(app, ["tools", "list", "--slug", "snipara"])

    assert result.exit_code == 0
    assert "Available MCP tools: 2" in result.stdout
    assert "rlm_help" in result.stdout
    assert "rlm_session_memories" in result.stdout


def test_cli_tools_call_decodes_json_text_payload(monkeypatch) -> None:
    """The generic tools call command should pretty-print decoded JSON text payloads."""
    runner = CliRunner()

    async def fake_call_mcp_tool(api_url, project_slug, auth_header, tool_name, arguments):
        assert tool_name == "rlm_help"
        assert arguments == {"query": "session automation"}
        return {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '{"recommended_tools":["rlm_session_memories","rlm_remember_if_novel"]}',
                    }
                ]
            }
        }

    monkeypatch.setattr("snipara_mcp.cli.load_auth_header", lambda: "rlm_test")
    monkeypatch.setattr("snipara_mcp.cli.call_mcp_tool", fake_call_mcp_tool)

    result = runner.invoke(
        app,
        [
            "tools",
            "call",
            "rlm_help",
            "--slug",
            "snipara",
            "--args",
            '{"query":"session automation"}',
        ],
    )

    assert result.exit_code == 0
    assert '"recommended_tools"' in result.stdout
    assert "rlm_session_memories" in result.stdout


async def test_list_tools_matches_generated_contract() -> None:
    """The packaged MCP server should expose the generated tool contract verbatim."""
    listed_tools = {tool.name: tool.inputSchema for tool in await mcp_server.list_tools()}
    contract_tools = {tool["name"]: tool["inputSchema"] for tool in MCP_TOOL_DEFINITIONS}

    assert listed_tools == contract_tools


async def test_upload_document_forwards_metadata(monkeypatch) -> None:
    """Single-file stdio uploads should preserve document metadata fields."""
    calls = []

    async def fake_call_api(tool, params):
        calls.append((tool, params))
        return {
            "success": True,
            "result": {
                "action": "metadata_updated",
                "path": params["path"],
                "size": len(params["content"]),
            },
        }

    monkeypatch.setattr(mcp_server, "call_api", fake_call_api)

    await mcp_server.call_tool(
        "rlm_upload_document",
        {
            "path": "clients/acme/current.md",
            "content": "# Current",
            "kind": "DOC",
            "format": "md",
            "language": "markdown",
            "metadata": {"assetClass": "BUSINESS_DOCUMENT", "usageMode": "current_truth"},
        },
    )

    assert calls[-1] == (
        "rlm_upload_document",
        {
            "path": "clients/acme/current.md",
            "content": "# Current",
            "kind": "DOC",
            "format": "md",
            "language": "markdown",
            "metadata": {"assetClass": "BUSINESS_DOCUMENT", "usageMode": "current_truth"},
        },
    )


def _clear_auth_env(monkeypatch) -> None:
    for key in (
        "SNIPARA_IGNORE_OAUTH",
        "SNIPARA_PROJECT_ID",
        "SNIPARA_PROJECT_SLUG",
        "SNIPARA_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def _stub_empty_sdk_config(monkeypatch) -> None:
    package = types.ModuleType("snipara")
    package.__path__ = []  # type: ignore[attr-defined]
    config_module = types.ModuleType("snipara.config")
    config_module.load_config = lambda: types.SimpleNamespace(
        project=types.SimpleNamespace(api_key="", slug="")
    )
    monkeypatch.setitem(sys.modules, "snipara", package)
    monkeypatch.setitem(sys.modules, "snipara.config", config_module)


def test_load_auth_uses_matching_workspace_oauth_token(monkeypatch) -> None:
    """An explicit workspace slug should select the matching OAuth token only."""
    _clear_auth_env(monkeypatch)
    _stub_empty_sdk_config(monkeypatch)
    monkeypatch.setenv("SNIPARA_PROJECT_SLUG", "snipara")
    monkeypatch.setattr(
        mcp_auth,
        "load_tokens",
        lambda: {
            "proj-vutler": {
                "access_token": "snipara_at_vutler",
                "project_slug": "vutler",
            },
            "proj-snipara": {
                "access_token": "snipara_at_snipara",
                "project_slug": "snipara",
            },
        },
    )

    token, auth_type, project_id = mcp_server._load_auth()

    assert token == "snipara_at_snipara"
    assert auth_type == "oauth"
    assert project_id == "snipara"


def test_load_auth_does_not_fallback_to_other_project_when_workspace_is_explicit(monkeypatch) -> None:
    """An explicit workspace should never silently borrow another project's token."""
    _clear_auth_env(monkeypatch)
    _stub_empty_sdk_config(monkeypatch)
    monkeypatch.setenv("SNIPARA_PROJECT_SLUG", "snipara")
    monkeypatch.setattr(
        mcp_auth,
        "load_tokens",
        lambda: {
            "proj-vutler": {
                "access_token": "snipara_at_vutler",
                "project_slug": "vutler",
            }
        },
    )

    token, auth_type, project_id = mcp_server._load_auth()

    assert token is None
    assert auth_type == "none"
    assert project_id == "snipara"


def test_load_auth_uses_env_api_key_after_explicit_project_miss(monkeypatch) -> None:
    """Explicit workspaces should fall back to env auth, not another token."""
    _clear_auth_env(monkeypatch)
    _stub_empty_sdk_config(monkeypatch)
    monkeypatch.setenv("SNIPARA_PROJECT_SLUG", "snipara")
    monkeypatch.setenv("SNIPARA_API_KEY", "rlm_pk_env")
    monkeypatch.setattr(
        mcp_auth,
        "load_tokens",
        lambda: {
            "proj-vutler": {
                "access_token": "snipara_at_vutler",
                "project_slug": "vutler",
            }
        },
    )

    token, auth_type, project_id = mcp_server._load_auth()

    assert token == "rlm_pk_env"
    assert auth_type == "api_key"
    assert project_id == "snipara"


def test_load_auth_prefers_project_api_key_for_legacy_v1_routes(monkeypatch) -> None:
    """Stored API keys should win over bearer tokens for legacy /v1 project calls."""
    _clear_auth_env(monkeypatch)
    _stub_empty_sdk_config(monkeypatch)
    monkeypatch.setenv("SNIPARA_PROJECT_SLUG", "snipara")
    monkeypatch.setattr(
        mcp_auth,
        "load_tokens",
        lambda: {
            "proj-snipara": {
                "access_token": "snipara_at_snipara",
                "api_key": "rlm_pk_snipara",
                "project_slug": "snipara",
            }
        },
    )

    token, auth_type, project_id = mcp_server._load_auth()

    assert token == "rlm_pk_snipara"
    assert auth_type == "api_key"
    assert project_id == "snipara"


def test_get_headers_uses_auth_type_specific_header(monkeypatch) -> None:
    """Legacy project calls should emit the header that matches the selected auth type."""
    monkeypatch.setattr(mcp_server, "_auth_token", "snipara_at_snipara")
    monkeypatch.setattr(mcp_server, "_auth_type", "oauth")
    monkeypatch.setattr(mcp_server, "API_KEY", "")

    oauth_headers = mcp_server.get_headers()

    assert oauth_headers["Authorization"] == "Bearer snipara_at_snipara"
    assert "X-API-Key" not in oauth_headers

    monkeypatch.setattr(mcp_server, "_auth_token", "rlm_pk_snipara")
    monkeypatch.setattr(mcp_server, "_auth_type", "api_key")

    api_key_headers = mcp_server.get_headers()

    assert api_key_headers["X-API-Key"] == "rlm_pk_snipara"
    assert "Authorization" not in api_key_headers
