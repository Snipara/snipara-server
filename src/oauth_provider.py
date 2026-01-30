"""
OAuth 2.0 provider metadata and ChatGPT App manifest endpoints.

This module provides:
- OAuth 2.0 Authorization Server Metadata (RFC 8414)
- OpenAI plugin / ChatGPT App manifest
- OAuth client registration helper endpoint (admin-only)

The actual Authorization Code flow endpoints (authorize, token, revoke) are
handled by the NextJS web app at /api/oauth/*, since they need user session
context. This module provides discovery metadata so clients can find them.
"""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["OAuth Provider"])


# ============ OAUTH METADATA ============


@router.get(
    "/.well-known/oauth-authorization-server",
    summary="OAuth 2.0 Authorization Server Metadata",
    description=(
        "Returns OAuth 2.0 Authorization Server Metadata per RFC 8414. "
        "Clients use this to discover authorization, token, and revocation endpoints."
    ),
)
async def oauth_metadata() -> dict:
    """OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
    base_url = "https://snipara.com"
    api_url = "https://api.snipara.com"

    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/api/oauth/authorize",
        "token_endpoint": f"{base_url}/api/oauth/token",
        "revocation_endpoint": f"{base_url}/api/oauth/revoke",
        "device_authorization_endpoint": f"{base_url}/api/oauth/device/code",
        "scopes_supported": ["mcp:read", "mcp:write"],
        "response_types_supported": ["code"],
        "grant_types_supported": [
            "authorization_code",
            "refresh_token",
            "urn:ietf:params:oauth:grant-type:device_code",
        ],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "service_documentation": f"{base_url}/docs/authentication",
        "ui_locales_supported": ["en"],
        # MCP-specific extensions
        "mcp_server_url": f"{api_url}/mcp",
        "gpt_actions_url": f"{api_url}/v1/gpt",
    }


# ============ CHATGPT APP MANIFEST ============


@router.get(
    "/.well-known/ai-plugin.json",
    summary="ChatGPT App / OpenAI Plugin manifest",
    description=(
        "Returns the OpenAI plugin manifest for ChatGPT App registration. "
        "This manifest describes the app, its authentication method, and API spec location."
    ),
)
async def chatgpt_app_manifest() -> dict:
    """OpenAI plugin manifest for ChatGPT App registration."""
    base_url = "https://snipara.com"
    api_url = "https://api.snipara.com"

    return {
        "schema_version": "v1",
        "name_for_human": "Snipara",
        "name_for_model": "snipara",
        "description_for_human": (
            "Query your project documentation with AI-optimized context. "
            "Upload docs, search with natural language, and get relevant answers."
        ),
        "description_for_model": (
            "Snipara provides optimized documentation context for any project. "
            "Use the query action to ask questions about the user's documentation. "
            "Use the search action to find specific patterns in the docs. "
            "Use the info action to understand the project's documentation scope. "
            "Use the remember action to store facts and decisions for later recall. "
            "Use the recall action to retrieve previously stored memories. "
            "Use the shared-context action to get team coding standards."
        ),
        "auth": {
            "type": "oauth",
            "client_url": f"{base_url}/api/oauth/authorize",
            "authorization_url": f"{base_url}/api/oauth/token",
            "scope": "mcp:read mcp:write",
            "authorization_content_type": "application/json",
            "verification_tokens": {
                "openai": "placeholder_verification_token",
            },
        },
        "api": {
            "type": "openapi",
            "url": f"{api_url}/v1/gpt/me/openapi",
            "is_user_authenticated": True,
        },
        "logo_url": f"{base_url}/logo.png",
        "contact_email": "support@snipara.com",
        "legal_info_url": f"{base_url}/legal/terms",
    }


# ============ OAUTH CLIENT MANAGEMENT ============


@router.get(
    "/v1/oauth/clients/chatgpt",
    summary="Get ChatGPT OAuth client configuration",
    description=(
        "Returns the pre-registered ChatGPT OAuth client details needed "
        "for configuring a ChatGPT App in the OpenAI developer portal."
    ),
)
async def get_chatgpt_client_config() -> dict:
    """Return ChatGPT-specific OAuth configuration instructions."""
    base_url = "https://snipara.com"

    return {
        "instructions": [
            "1. Go to https://platform.openai.com/apps to register your ChatGPT App",
            "2. Configure OAuth with these settings:",
        ],
        "oauth_config": {
            "authorization_url": f"{base_url}/api/oauth/authorize",
            "token_url": f"{base_url}/api/oauth/token",
            "revocation_url": f"{base_url}/api/oauth/revoke",
            "scope": "mcp:read mcp:write",
            "token_exchange_method": "default (POST with JSON body)",
        },
        "openapi_specs": {
            "gpt_store": "https://api.snipara.com/v1/gpt/me/openapi",
            "per_project": "https://api.snipara.com/v1/gpt/{project_slug}/openapi",
        },
        "notes": [
            "For the GPT Store (public): Use /v1/gpt/me/openapi — OAuth Bearer auth, project resolved from token.",
            "For private GPTs: Use /v1/gpt/{project_slug}/openapi — API Key auth per project.",
            "Client ID and secret are generated when you register the app in the Snipara dashboard.",
            "The authorization flow will ask the user to select a project and approve access.",
            "Tokens are scoped to a single project — if the user has multiple projects, they choose at auth time.",
        ],
    }
