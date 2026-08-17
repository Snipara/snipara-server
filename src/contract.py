"""Public compatibility contract for the self-hosted Snipara server."""

from . import __version__

OSS_CONTRACT = "snipara-server-oss-v2"

PUBLIC_FEATURES = (
    "project_context",
    "semantic_search",
    "persistent_memory",
    "document_indexing",
    "code_graph",
    "local_usage_tracking",
)

EXCLUDED_CLOUD_FEATURES = (
    "multi_project_queries",
    "team_scopes",
    "integrator_identity",
    "oauth_device_flow",
    "billing_and_plans",
    "admin_routes",
)


def public_capabilities() -> dict[str, object]:
    """Return the stable, non-secret capability document for adapters."""
    return {
        "contract": OSS_CONTRACT,
        "server": {
            "name": "snipara-server",
            "version": __version__,
            "distribution": "self-hosted",
        },
        "scope": "project",
        "authentication": {
            "schemes": ["X-API-Key", "Authorization: Bearer"],
            "mode": "static_operator_key",
        },
        "transports": {
            "mcp_streamable_http": "/mcp/{project_id}",
            "legacy_json": "/v1/{project_id}/mcp",
        },
        "features": list(PUBLIC_FEATURES),
        "excluded_cloud_features": list(EXCLUDED_CLOUD_FEATURES),
    }
