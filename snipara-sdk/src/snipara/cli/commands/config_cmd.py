"""snipara config — view and manage configuration."""

from __future__ import annotations

import click

from snipara.config import find_config_file, find_global_config, find_legacy_config, load_config


@click.group()
def config() -> None:
    """View and manage Snipara configuration."""


@config.command()
def show() -> None:
    """Display resolved configuration from all layers."""
    cfg = load_config()

    click.echo("Snipara Configuration (resolved)")
    click.echo("=" * 50)
    click.echo()

    click.echo("[project]")
    click.echo(f"  slug      = {cfg.project.slug or '(not set)'}")
    click.echo(f"  api_key   = {_mask_key(cfg.project.api_key)}")
    click.echo(f"  api_url   = {cfg.project.api_url}")
    click.echo()

    click.echo("[context]")
    click.echo(f"  max_tokens    = {cfg.context.max_tokens}")
    click.echo(f"  search_mode   = {cfg.context.search_mode}")
    click.echo(f"  shared_context = {cfg.context.shared_context}")
    click.echo()

    click.echo("[runtime]")
    click.echo(f"  backend     = {cfg.runtime.backend}")
    click.echo(f"  model       = {cfg.runtime.model}")
    click.echo(f"  environment = {cfg.runtime.environment}")
    click.echo(f"  max_depth   = {cfg.runtime.max_depth}")
    click.echo(f"  verbose     = {cfg.runtime.verbose}")
    click.echo()

    click.echo("[sync]")
    click.echo(f"  include     = {cfg.sync.include}")
    click.echo(f"  exclude     = {cfg.sync.exclude}")
    click.echo(f"  debounce_ms = {cfg.sync.debounce_ms}")


@config.command()
def path() -> None:
    """Print path to active config file."""
    local = find_config_file()
    if local:
        click.echo(str(local))
        return

    global_path = find_global_config()
    if global_path:
        click.echo(str(global_path))
        return

    legacy = find_legacy_config()
    if legacy:
        click.echo(str(legacy))
        return

    click.echo("No config file found. Run 'snipara init' to create one.")
    raise SystemExit(1)


def _mask_key(key: str) -> str:
    """Mask an API key for safe display.

    Shows the first 7 and last 4 characters, replacing the middle with
    ``...``. Keys shorter than 12 characters show the first 4 and last 3.
    Returns ``"(not set)"`` for empty strings.

    Args:
        key: Raw API key string (e.g. ``"rlm_abc123def456"``).

    Returns:
        Masked string (e.g. ``"rlm_abc...f456"``) or ``"(not set)"``.
    """
    if not key:
        return "(not set)"
    if len(key) <= 12:
        return key[:4] + "..." + key[-3:]
    return key[:7] + "..." + key[-4:]
