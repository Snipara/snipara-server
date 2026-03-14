"""snipara watch — file watcher CLI command."""

from __future__ import annotations

import asyncio

import click


def watch(daemon: bool) -> None:
    """Watch local files and sync changes to Snipara."""
    from snipara.client import Snipara
    from snipara.watcher import watch_and_sync

    if daemon:
        click.echo("Daemon mode is not yet implemented. Running in foreground.")

    async def _run() -> None:
        async with Snipara() as client:
            await watch_and_sync(client)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        click.echo("\nStopped watching.")
