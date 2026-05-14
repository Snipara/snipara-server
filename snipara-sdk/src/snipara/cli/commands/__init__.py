"""snipara.cli.commands — Individual CLI command implementations.

Each module in this package implements one ``snipara`` subcommand:

- ``init.py``       — ``snipara init [--migrate]``  Create or migrate config
- ``config_cmd.py`` — ``snipara config show|path``  View resolved configuration
- ``status.py``     — ``snipara status``            Auth, config, and runtime status
- ``login.py``      — ``snipara login``             OAuth device-flow authentication
- ``logout.py``     — ``snipara logout``            Clear stored tokens
- ``sync.py``       — ``snipara sync [--dry-run]``  One-shot file sync
- ``watch.py``      — ``snipara watch [--daemon]``  Continuous file watcher
"""
