"""snipara status — show auth and configuration status."""

from __future__ import annotations

from pathlib import Path

import click

from snipara.config import find_config_file, find_legacy_config, load_config


def status() -> None:
    """Show authentication and configuration status."""
    config = load_config()

    click.echo("Snipara Status")
    click.echo("=" * 40)
    click.echo()

    # Config file location
    local = find_config_file()
    if local:
        click.echo(f"Config:  {local}")
    else:
        legacy = find_legacy_config()
        if legacy:
            click.echo(f"Config:  {legacy} (legacy — run 'snipara init --migrate')")
        else:
            click.echo("Config:  (none — run 'snipara init')")
    click.echo()

    # Project info
    click.echo(f"Project: {config.project.slug or '(not set)'}")
    click.echo(f"API URL: {config.project.api_url}")
    click.echo()

    # Auth status
    api_key = config.project.api_key
    if api_key:
        masked = api_key[:7] + "..." + api_key[-4:] if len(api_key) > 12 else api_key
        click.echo(f"API Key: {masked}")
    else:
        click.echo("API Key: (not set)")

    # Check OAuth tokens
    tokens_path = Path.home() / ".snipara" / "tokens.json"
    if tokens_path.exists():
        import json

        try:
            tokens = json.loads(tokens_path.read_text())
            count = len(tokens)
            click.echo(f"OAuth:   {count} stored token(s) at {tokens_path}")
        except (json.JSONDecodeError, OSError):
            click.echo(f"OAuth:   Token file exists but is unreadable: {tokens_path}")
    else:
        click.echo("OAuth:   No stored tokens")

    click.echo()

    # Runtime info
    click.echo(f"Runtime: {config.runtime.backend} / {config.runtime.model}")
    click.echo(f"Env:     {config.runtime.environment}")

    # Check if rlm-runtime is available
    try:
        import rlm  # noqa: F401

        click.echo("rlm-runtime: installed")
    except ImportError:
        click.echo("rlm-runtime: not installed (pip install snipara[runtime])")

    # Check if watchfiles is available
    try:
        import watchfiles  # noqa: F401

        click.echo("watchfiles:  installed")
    except ImportError:
        click.echo("watchfiles:  not installed (pip install snipara[watch])")
