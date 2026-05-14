"""snipara sync — one-shot file sync CLI command."""

from __future__ import annotations

import asyncio

import click


def sync(dry_run: bool) -> None:
    """One-shot sync of matching files to Snipara."""
    from snipara.client import Snipara
    from snipara.watcher import sync_all

    async def _run() -> None:
        async with Snipara() as client:
            report = await sync_all(client, dry_run=dry_run)

            if dry_run:
                click.echo(f"Would sync {report.total_files} file(s):")
                for f in report.uploaded:
                    click.echo(f"  {f}")
            else:
                click.echo(f"Synced {report.uploaded_count} file(s)")
                for f in report.uploaded:
                    click.echo(f"  ✓ {f}")
                for f in report.skipped:
                    click.echo(f"  - {f} (skipped)")
                for f, err in report.errors:
                    click.echo(f"  ✗ {f}: {err}")

    asyncio.run(_run())
