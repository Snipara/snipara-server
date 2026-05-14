"""snipara logout — clear stored authentication tokens."""

from __future__ import annotations

import click


def logout() -> None:
    """Clear all stored Snipara authentication tokens."""
    from pathlib import Path

    tokens_path = Path.home() / ".snipara" / "tokens.json"

    if not tokens_path.exists():
        click.echo("No stored tokens found.")
        return

    if click.confirm("Remove all stored authentication tokens?"):
        tokens_path.unlink()
        click.echo("Tokens removed.")
    else:
        click.echo("Cancelled.")
