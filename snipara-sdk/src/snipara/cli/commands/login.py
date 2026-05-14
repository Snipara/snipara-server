"""snipara login — OAuth device flow authentication."""

from __future__ import annotations

import click


def login() -> None:
    """Authenticate with Snipara via browser (OAuth device flow)."""
    try:
        from snipara_mcp.auth import device_flow_login
    except ImportError:
        click.echo("Error: snipara-mcp package required. Install with: pip install snipara")
        raise SystemExit(1)

    import asyncio

    from snipara.config import load_config

    config = load_config()
    api_url = config.project.auth_url

    click.echo("Starting Snipara authentication...")
    click.echo()

    result = asyncio.run(device_flow_login(api_url=api_url))

    if result:
        click.echo()
        click.echo("Authentication successful!")
        project_id = result.get("project_id", "")
        if project_id:
            click.echo(f"Project: {project_id}")
        click.echo("Token stored at ~/.snipara/tokens.json")
    else:
        click.echo("Authentication failed.")
        raise SystemExit(1)
