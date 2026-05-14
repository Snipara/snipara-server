"""snipara init — create .snipara.toml interactively or migrate from rlm.toml."""

from __future__ import annotations

from pathlib import Path

import click

from snipara.config import (
    CONFIG_FILENAME,
    LEGACY_FILENAME,
    SniparaConfig,
    _parse_legacy_rlm_toml,
    _parse_toml,
    _walk_up_to_git_root,
    generate_toml,
)


@click.command()
@click.option("--migrate", is_flag=True, help="Convert existing rlm.toml to .snipara.toml")
@click.option(
    "--dir",
    "target_dir",
    type=click.Path(exists=True, file_okay=False),
    default=".",
    help="Directory to create .snipara.toml in",
)
def init(migrate: bool, target_dir: str) -> None:
    """Create a .snipara.toml configuration file."""
    target = Path(target_dir).resolve()
    output_path = target / CONFIG_FILENAME

    if output_path.exists() and not migrate:
        click.echo(f"Config already exists: {output_path}")
        if not click.confirm("Overwrite?"):
            raise SystemExit(0)

    if migrate:
        _do_migrate(target, output_path)
    else:
        _do_interactive(output_path)


def _do_migrate(target: Path, output_path: Path) -> None:
    """Migrate an existing ``rlm.toml`` to ``.snipara.toml``.

    Walks up from *target* to the git root looking for ``rlm.toml``, parses
    it with :func:`_parse_legacy_rlm_toml`, converts to the new config
    format, and writes the result to *output_path*.

    Args:
        target: Starting directory for the upward search.
        output_path: Destination path for the new ``.snipara.toml`` file.
    """
    # Find rlm.toml walking up
    legacy_path = None
    for d in _walk_up_to_git_root(target):
        candidate = d / LEGACY_FILENAME
        if candidate.exists():
            legacy_path = candidate
            break

    if not legacy_path:
        click.echo("No rlm.toml found. Run 'snipara init' instead.")
        raise SystemExit(1)

    click.echo(f"Found {legacy_path}")
    legacy_data = _parse_toml(legacy_path)
    config = SniparaConfig()
    config = _parse_legacy_rlm_toml(config, legacy_data)

    toml_str = generate_toml(config)
    output_path.write_text(toml_str)
    click.echo(f"Created {output_path}")
    click.echo()
    click.echo("Migration complete. You can now delete rlm.toml.")
    click.echo("Add .snipara.toml to .gitignore if it contains API keys.")


def _do_interactive(output_path: Path) -> None:
    """Interactively create a ``.snipara.toml`` configuration file.

    Prompts the user for project slug, API key, context settings, and
    optional rlm-runtime settings, then writes the resulting configuration
    to *output_path*. Warns if the file contains an API key that should
    be git-ignored.

    Args:
        output_path: Destination path for the new ``.snipara.toml`` file.
    """
    config = SniparaConfig()

    click.echo("Snipara SDK Configuration")
    click.echo("=" * 40)
    click.echo()

    # Project settings
    slug = click.prompt("Project slug", default="", show_default=False)
    if slug:
        config.project.slug = slug

    api_key = click.prompt("API key (rlm_...)", default="", show_default=False)
    if api_key:
        config.project.api_key = api_key

    # Context settings
    max_tokens = click.prompt("Default max tokens", default=config.context.max_tokens)
    config.context.max_tokens = max_tokens

    search_mode = click.prompt(
        "Search mode",
        type=click.Choice(["keyword", "semantic", "hybrid"]),
        default=config.context.search_mode,
    )
    config.context.search_mode = search_mode

    # Runtime settings (optional)
    if click.confirm("Configure rlm-runtime settings?", default=False):
        model = click.prompt("LLM model", default=config.runtime.model)
        config.runtime.model = model

        env = click.prompt(
            "Execution environment",
            type=click.Choice(["local", "docker"]),
            default=config.runtime.environment,
        )
        config.runtime.environment = env

    toml_str = generate_toml(config)
    output_path.write_text(toml_str)
    click.echo()
    click.echo(f"Created {output_path}")

    if config.project.api_key:
        click.echo()
        click.echo("WARNING: .snipara.toml contains your API key.")
        click.echo("Add it to .gitignore to avoid committing secrets:")
        click.echo("  echo '.snipara.toml' >> .gitignore")
