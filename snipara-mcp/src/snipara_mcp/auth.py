#!/usr/bin/env python3
"""
OAuth Device Flow authentication for Snipara MCP.

This module implements the OAuth 2.0 Device Authorization Flow (RFC 8628)
to allow users to authenticate without manually copying API keys.

Usage:
    snipara-mcp-login          # Interactive login
    snipara-mcp-logout         # Clear stored tokens
    snipara-mcp-status         # Show current auth status
"""

import asyncio
import json
import os
import stat
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

# Token storage location
TOKEN_DIR = Path.home() / ".snipara"
TOKEN_FILE = TOKEN_DIR / "tokens.json"

# API configuration
DEFAULT_API_URL = "https://www.snipara.com"


def get_api_url() -> str:
    """Get the API URL from environment or default."""
    return os.environ.get("SNIPARA_API_URL", DEFAULT_API_URL)


def ensure_token_dir() -> None:
    """Ensure token directory exists with secure permissions."""
    if not TOKEN_DIR.exists():
        TOKEN_DIR.mkdir(parents=True, mode=0o700)


def load_tokens() -> dict[str, Any]:
    """Load stored tokens from file."""
    if not TOKEN_FILE.exists():
        return {}
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_tokens(tokens: dict[str, Any]) -> None:
    """Save tokens to file with secure permissions."""
    ensure_token_dir()
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    # Secure file permissions (owner read/write only)
    TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)


def get_stored_token(project_id: str) -> dict[str, Any] | None:
    """
    Get stored token for a project.

    Args:
        project_id: The project ID to get token for

    Returns:
        Token data if valid, None otherwise
    """
    tokens = load_tokens()
    token_data = tokens.get(project_id)

    if not token_data:
        return None

    # Check if access token is expired or about to expire (proactive refresh)
    expires_at = token_data.get("expires_at")
    if expires_at:
        try:
            exp_time = datetime.fromisoformat(expires_at)
            # Handle legacy tokens stored without timezone info
            if exp_time.tzinfo is None:
                exp_time = exp_time.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            # Proactive refresh: refresh if expired OR if less than 5 minutes remaining
            # This prevents mid-session failures
            time_remaining = (exp_time - now).total_seconds()
            if time_remaining < 300:  # 5 minutes
                # Token expired or about to expire, try to refresh
                refresh_token = token_data.get("refresh_token")
                if refresh_token:
                    try:
                        refreshed = asyncio.run(refresh_access_token(refresh_token))
                    except RuntimeError:
                        # Event loop already running (e.g., in async context)
                        # Fall back to returning current token if not expired yet
                        if time_remaining > 0:
                            return token_data
                        return None
                    if refreshed:
                        # Merge refreshed token with existing to preserve api_key/mcp_endpoint
                        # if not returned in refresh response
                        merged = {**token_data, **refreshed}
                        # Preserve api_key if not in refresh response
                        if not refreshed.get("api_key") and token_data.get("api_key"):
                            merged["api_key"] = token_data["api_key"]
                        if not refreshed.get("mcp_endpoint") and token_data.get("mcp_endpoint"):
                            merged["mcp_endpoint"] = token_data["mcp_endpoint"]
                        tokens[project_id] = merged
                        save_tokens(tokens)
                        return merged
                # Refresh failed - if token still has time, use it anyway
                if time_remaining > 0:
                    return token_data
                # Token expired and refresh failed
                return None
        except (ValueError, TypeError):
            pass

    return token_data


def store_token(project_id: str, token_data: dict[str, Any]) -> None:
    """
    Store token for a project.

    Args:
        project_id: The project ID
        token_data: Token response from OAuth server
    """
    tokens = load_tokens()

    # Calculate expiration time
    expires_in = token_data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    tokens[project_id] = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at.isoformat(),
        "scope": token_data.get("scope"),
        "project_slug": token_data.get("project_slug"),
        "project_id": project_id,
        "api_key": token_data.get("api_key"),  # Store API key for .mcp.json generation
        "mcp_endpoint": token_data.get("mcp_endpoint"),  # Store MCP endpoint URL
    }

    save_tokens(tokens)


def remove_token(project_id: str) -> bool:
    """
    Remove stored token for a project.

    Args:
        project_id: The project ID

    Returns:
        True if token was removed, False if not found
    """
    tokens = load_tokens()
    if project_id in tokens:
        del tokens[project_id]
        save_tokens(tokens)
        return True
    return False


def clear_all_tokens() -> int:
    """
    Clear all stored tokens.

    Returns:
        Number of tokens cleared
    """
    tokens = load_tokens()
    count = len(tokens)
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
    return count


def get_auth_header(project_id: str) -> str | None:
    """
    Get authorization header for a project.

    Checks for OAuth token first, falls back to API key from environment.

    Args:
        project_id: The project ID

    Returns:
        Authorization header value or None
    """
    # First check for stored OAuth token
    token_data = get_stored_token(project_id)
    if token_data and token_data.get("access_token"):
        return f"Bearer {token_data['access_token']}"

    # Fall back to API key from environment
    api_key = os.environ.get("SNIPARA_API_KEY")
    if api_key:
        return api_key  # Will be used as X-API-Key

    return None


async def refresh_access_token(refresh_token: str) -> dict[str, Any] | None:
    """
    Refresh an access token using a refresh token.

    Args:
        refresh_token: The refresh token

    Returns:
        New token data if successful, None otherwise
    """
    api_url = get_api_url()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_url}/api/oauth/token",
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )

            if response.status_code == 200:
                data = response.json()
                expires_in = data.get("expires_in", 3600)
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                return {
                    "access_token": data["access_token"],
                    "refresh_token": data.get("refresh_token"),
                    "expires_at": expires_at.isoformat(),
                    "scope": data.get("scope"),
                    "project_slug": data.get("project_slug"),
                    "project_id": data.get("project_id"),
                    "api_key": data.get("api_key"),  # May be returned on refresh
                    "mcp_endpoint": data.get("mcp_endpoint"),
                }
    except Exception:
        pass

    return None


async def device_flow_login() -> dict[str, Any]:
    """
    Perform OAuth 2.0 Device Authorization Flow.

    Returns:
        Token data from successful authentication

    Raises:
        Exception: If authentication fails
    """
    api_url = get_api_url()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Request device code
        print("\nRequesting device code...")
        response = await client.post(
            f"{api_url}/api/oauth/device/code",
            json={"client_id": "snipara-mcp", "auto_provision": True},
        )
        response.raise_for_status()
        device_data = response.json()

        user_code = device_data["user_code"]
        device_code = device_data["device_code"]
        verification_uri = device_data["verification_uri"]
        verification_uri_complete = device_data.get("verification_uri_complete")
        interval = device_data.get("interval", 5)
        expires_in = device_data.get("expires_in", 1800)

        # Step 2: Display instructions
        print("\n" + "=" * 50)
        print("  Snipara MCP Authentication")
        print("=" * 50)
        print()
        if verification_uri_complete:
            print("1. Open this URL in your browser:")
            print(f"   {verification_uri_complete}")
            print()
            print("2. Sign in, select a project, and click 'Authorize'")
            print("   (A free account will be created automatically)")
        else:
            print("1. Open this URL in your browser:")
            print(f"   {verification_uri}")
            print()
            print(f"2. Enter this code: {user_code}")
            print()
            print("3. Sign in, select a project, and click 'Authorize'")
            print("   (A free account will be created automatically)")
        print()
        print(f"Waiting for authorization... (expires in {expires_in // 60} minutes)")
        print("-" * 50)

        # Try to open browser automatically
        try:
            webbrowser.open(verification_uri_complete or verification_uri)
        except Exception:
            pass

        # Step 3: Poll for token
        start_time = datetime.now(timezone.utc)
        max_wait = timedelta(seconds=expires_in)

        while datetime.now(timezone.utc) - start_time < max_wait:
            await asyncio.sleep(interval)

            try:
                token_response = await client.post(
                    f"{api_url}/api/oauth/device/token",
                    json={
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "device_code": device_code,
                        "client_id": "snipara-mcp",
                    },
                )

                if token_response.status_code == 200:
                    token_data = token_response.json()
                    project_id = token_data.get("project_id")
                    project_slug = token_data.get("project_slug", project_id)
                    api_key = token_data.get("api_key")
                    project_name = token_data.get("project_name", project_slug)
                    server_url = token_data.get(
                        "server_url", "https://api.snipara.com"
                    )
                    mcp_endpoint = token_data.get(
                        "mcp_endpoint",
                        f"{server_url}/mcp/{project_slug}",
                    )

                    # Store token
                    store_token(project_id, token_data)

                    print()
                    print("=" * 50)
                    print("  Authentication Successful!")
                    print("=" * 50)
                    print()
                    print(f"  Project: {project_name} ({project_slug})")
                    print(f"  Token stored in: {TOKEN_FILE}")
                    if api_key:
                        print(f"  API Key: {api_key[:16]}...")
                    print()

                    # Print MCP configuration snippet
                    if api_key:
                        print(
                            "Add this to your .mcp.json to use"
                            " Snipara as an MCP server:"
                        )
                        print()
                        print("  {")
                        print('    "mcpServers": {')
                        print('      "snipara": {')
                        print('        "type": "http",')
                        print(f'        "url": "{mcp_endpoint}",')
                        print('        "headers": {')
                        print(f'          "X-API-Key": "{api_key}"')
                        print("        }")
                        print("      }")
                        print("    }")
                        print("  }")
                        print()

                    print("You can now use snipara-mcp with this project.")
                    print()

                    return token_data

                error_data = token_response.json()
                error = error_data.get("error")

                if error == "authorization_pending":
                    # Still waiting, continue polling
                    continue
                elif error == "slow_down":
                    # Increase interval
                    interval += 5
                    continue
                elif error == "access_denied":
                    raise Exception("Authorization denied by user")
                elif error == "expired_token":
                    raise Exception("Device code expired. Please try again.")
                else:
                    raise Exception(f"OAuth error: {error}")

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400:
                    # Might be authorization_pending, continue polling
                    continue
                raise

        raise Exception("Authorization timed out. Please try again.")


def login_cli() -> None:
    """CLI entry point for snipara-mcp-login."""
    print()
    print("Snipara MCP - Device Flow Login")
    print()

    try:
        asyncio.run(device_flow_login())
    except KeyboardInterrupt:
        print("\n\nLogin cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


def logout_cli() -> None:
    """CLI entry point for snipara-mcp-logout."""
    print()
    print("Snipara MCP - Logout")
    print()

    tokens = load_tokens()
    if not tokens:
        print("No stored tokens found.")
        return

    print(f"Found {len(tokens)} stored token(s):")
    for project_id, data in tokens.items():
        slug = data.get("project_slug", project_id)
        print(f"  - {slug}")

    print()
    confirm = input("Clear all tokens? [y/N] ").strip().lower()
    if confirm == "y":
        count = clear_all_tokens()
        print(f"\nCleared {count} token(s).")
    else:
        print("\nCancelled.")


def status_cli() -> None:
    """CLI entry point for snipara-mcp-status."""
    print()
    print("Snipara MCP - Authentication Status")
    print()

    # Check environment variables
    api_key = os.environ.get("SNIPARA_API_KEY")
    project_id = os.environ.get("SNIPARA_PROJECT_ID")

    if api_key:
        print("Environment:")
        print(f"  SNIPARA_API_KEY: {api_key[:12]}...")
        if project_id:
            print(f"  SNIPARA_PROJECT_ID: {project_id}")
        print()

    # Check stored tokens
    tokens = load_tokens()
    if tokens:
        print("Stored OAuth Tokens:")
        for pid, data in tokens.items():
            slug = data.get("project_slug", pid)
            expires_at = data.get("expires_at", "unknown")
            try:
                exp_time = datetime.fromisoformat(expires_at)
                # Handle legacy tokens stored without timezone info
                if exp_time.tzinfo is None:
                    exp_time = exp_time.replace(tzinfo=timezone.utc)
                if exp_time < datetime.now(timezone.utc):
                    status = "EXPIRED"
                else:
                    remaining = exp_time - datetime.now(timezone.utc)
                    status = f"valid for {remaining.total_seconds() / 60:.0f} min"
            except (ValueError, TypeError):
                status = "unknown"
            print(f"  - {slug}: {status}")
        print()
    else:
        print("No stored OAuth tokens.")
        print()

    if not api_key and not tokens:
        print("Not authenticated. Run 'snipara-mcp-login' to authenticate.")


if __name__ == "__main__":
    # Allow running as: python -m snipara_mcp.auth login|logout|status
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "login":
            login_cli()
        elif cmd == "logout":
            logout_cli()
        elif cmd == "status":
            status_cli()
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python -m snipara_mcp.auth [login|logout|status]")
    else:
        status_cli()
