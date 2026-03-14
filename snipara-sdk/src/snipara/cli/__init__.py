"""snipara.cli — Command-line interface for the Snipara SDK.

Built with `Click <https://click.palletsprojects.com/>`_.

**Entry point:** ``snipara`` (registered in pyproject.toml ``[project.scripts]``).

**Subpackages:**

- ``commands/`` — Individual CLI command implementations (init, config, status, etc.)

**Design notes:**

Commands that require optional dependencies (``watchfiles``, ``rlm-runtime``)
are lazy-loaded in ``main.py`` to keep startup fast and provide helpful error
messages when the dependency is not installed.
"""
