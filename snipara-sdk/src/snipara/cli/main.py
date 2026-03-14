"""snipara CLI — unified command-line interface.

Entry point for the ``snipara`` command-line tool. Built with Click.

**Available commands:**

- ``snipara init [--migrate]`` — Create or migrate ``.snipara.toml``
- ``snipara config show|path`` — View resolved configuration
- ``snipara status`` — Show auth, config, and runtime status
- ``snipara login`` — OAuth device flow authentication
- ``snipara logout`` — Clear stored tokens
- ``snipara query "..."`` — Query Snipara for context
- ``snipara sync [--dry-run]`` — One-shot file sync
- ``snipara watch [--daemon]`` — Continuous file watcher

**Design notes:**

Commands that require optional dependencies (``watchfiles``, ``rlm-runtime``)
are lazy-loaded to avoid import overhead and provide helpful error messages
when the dependency is not installed.

**Entry point (pyproject.toml):**

    [project.scripts]
    snipara = "snipara.cli.main:cli"
"""

from __future__ import annotations

import click

from snipara._version import __version__


@click.group()
@click.version_option(version=__version__, prog_name="snipara")
def cli() -> None:
    """Snipara SDK — Context optimization and Agent infrastructure for LLMs."""


# --- Register subcommands ---

from snipara.cli.commands.config_cmd import config  # noqa: E402
from snipara.cli.commands.init import init  # noqa: E402

cli.add_command(init)
cli.add_command(config)


# Lazy-loaded commands to avoid import overhead for optional deps


@cli.command()
@click.argument("query_text")
@click.option("--max-tokens", "-t", type=int, default=None, help="Token budget")
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["keyword", "semantic", "hybrid"]),
    default=None,
    help="Search mode",
)
def query(query_text: str, max_tokens: int | None, mode: str | None) -> None:
    """Query Snipara for context."""
    import asyncio

    from snipara.client import Snipara

    async def _run() -> None:
        async with Snipara() as s:
            kwargs: dict = {}
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            if mode is not None:
                kwargs["search_mode"] = mode
            result = await s.query(query_text, **kwargs)
            click.echo(result.get("content", result))

    asyncio.run(_run())


@cli.command()
def login() -> None:
    """Authenticate with Snipara via browser."""
    from snipara.cli.commands.login import login as _login

    _login()


@cli.command()
def logout() -> None:
    """Clear stored authentication tokens."""
    from snipara.cli.commands.logout import logout as _logout

    _logout()


@cli.command()
def status() -> None:
    """Show authentication and configuration status."""
    from snipara.cli.commands.status import status as _status

    _status()


@cli.command()
@click.option("--daemon", is_flag=True, help="Run as background daemon")
def watch(daemon: bool) -> None:
    """Watch local files and sync changes to Snipara."""
    from snipara.cli.commands.watch import watch as _watch

    _watch(daemon)


@cli.command(name="sync")
@click.option("--dry-run", is_flag=True, help="Show what would be synced without uploading")
def sync_cmd(dry_run: bool) -> None:
    """One-shot sync of matching files to Snipara."""
    from snipara.cli.commands.sync import sync as _sync

    _sync(dry_run)
