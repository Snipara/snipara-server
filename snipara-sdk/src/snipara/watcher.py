"""File watcher — event-driven sync of local files to Snipara.

This module provides file synchronization between a local project and Snipara.
It supports two modes:

1. **One-shot sync** via :func:`sync_all` — scans all matching files and uploads them
2. **Continuous watch** via :func:`watch_and_sync` — monitors filesystem events and
   uploads on create/modify (uses ``watchfiles``, a Rust-based async watcher)

**Pattern matching:**

Files are matched against include/exclude glob patterns from the ``[sync]`` section
of ``.snipara.toml``. Exclude patterns take priority over include patterns. Patterns
use :mod:`fnmatch` semantics (``**`` for recursive, ``*`` for single segment).

**Key functions:**

- :func:`sync_all` — One-shot sync of all matching files (with dry-run support)
- :func:`watch_and_sync` — Blocking async watcher for continuous sync
- :func:`collect_matching_files` — Collect files matching include/exclude patterns
- :func:`matches_patterns` — Check if a single path matches patterns

**Key types:**

- :class:`SyncReport` — Report from a sync operation (uploaded, skipped, errors)

**Usage::

    from snipara import Snipara
    from snipara.watcher import sync_all

    async with Snipara() as client:
        report = await sync_all(client, dry_run=True)
        print(f"Would sync {report.total_files} file(s)")
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SyncReport:
    """Report from a sync operation.

    Attributes:
        uploaded: Relative paths of files successfully uploaded (or that
            would be uploaded in dry-run mode).
        skipped: Relative paths of files skipped (e.g. binary files).
        errors: List of ``(relative_path, error_message)`` tuples for files
            that failed to upload.
        total_files: Total number of files that matched the include/exclude
            patterns before any upload attempt.
    """

    uploaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    total_files: int = 0

    @property
    def uploaded_count(self) -> int:
        return len(self.uploaded)


def _glob_match(path_str: str, pattern: str) -> bool:
    """Match a path string against a glob pattern with ``**`` support.

    Standard :func:`fnmatch.fnmatch` does not handle ``**`` (any number of
    directory levels). This function converts ``**`` patterns to regex for
    correct multi-level directory matching.

    ``**`` matches zero or more path segments. So ``docs/**/*.md`` matches
    both ``docs/api.md`` (zero intermediate dirs) and ``docs/guides/auth.md``
    (one intermediate dir).

    Args:
        path_str: Relative file path (e.g. ``"docs/guides/auth.md"``).
        pattern: Glob pattern (e.g. ``"docs/**/*.md"``).

    Returns:
        True if path matches the pattern.
    """
    if "**" not in pattern:
        return fnmatch.fnmatch(path_str, pattern)
    # Convert glob pattern to regex:
    #   /**/  → zero or more path segments (including separators)
    #   **    → match any path (standalone)
    #   *     → match anything within a single path segment
    #   ?     → match one non-separator character
    #
    # Handle /**/  as (/.+)?/  so it matches zero intermediate dirs.
    # e.g. docs/**/*.md  → docs(/.+)?/[^/]*\.md
    # This matches: docs/api.md, docs/sub/api.md, docs/a/b/c.md
    regex = re.escape(pattern)
    # First: replace /**/ with a placeholder that captures zero-or-more segments
    regex = regex.replace(r"/\*\*/" , "/GLOBSTAR_SEP/")
    # Handle leading **/ (e.g. **/*.md matches any depth from root)
    regex = regex.replace(r"\*\*/", "GLOBSTAR_PREFIX/")
    # Handle trailing /** (e.g. docs/** matches everything under docs)
    regex = regex.replace(r"/\*\*", "/GLOBSTAR_SUFFIX")
    # Handle bare ** (e.g. ** matches everything)
    regex = regex.replace(r"\*\*", "GLOBSTAR_BARE")
    # Replace single * and ?
    regex = regex.replace(r"\*", "[^/]*")
    regex = regex.replace(r"\?", "[^/]")
    # Expand globstar placeholders
    regex = regex.replace("/GLOBSTAR_SEP/", "(/.*)?/")
    regex = regex.replace("GLOBSTAR_PREFIX/", "(.*/)?")
    regex = regex.replace("/GLOBSTAR_SUFFIX", "(/.*)?")
    regex = regex.replace("GLOBSTAR_BARE", ".*")
    return bool(re.fullmatch(regex, path_str))


def matches_patterns(
    path: str, include: list[str], exclude: list[str], root: Path
) -> bool:
    """Check if a file path matches include patterns and not exclude patterns.

    Exclude patterns are checked first (deny takes priority). Then include
    patterns are checked. If neither matches, returns False.

    Supports ``**`` for recursive directory matching.

    Args:
        path: Absolute file path.
        include: List of glob include patterns.
        exclude: List of glob exclude patterns.
        root: Project root for computing relative paths.

    Returns:
        True if the file should be included in sync operations.
    """
    try:
        relative = str(Path(path).relative_to(root))
    except ValueError:
        return False

    # Check exclude first
    for pattern in exclude:
        if _glob_match(relative, pattern):
            return False

    # Check include
    for pattern in include:
        if _glob_match(relative, pattern):
            return True

    return False


def collect_matching_files(root: Path, include: list[str], exclude: list[str]) -> list[Path]:
    """Collect all files under root matching include/exclude patterns."""
    matches = []
    for pattern in include:
        for path in root.glob(pattern):
            if path.is_file():
                relative = str(path.relative_to(root))
                excluded = False
                for ex in exclude:
                    if _glob_match(relative, ex):
                        excluded = True
                        break
                if not excluded:
                    matches.append(path)
    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in matches:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return sorted(unique)


async def sync_all(
    client: Any,
    root: Path | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    dry_run: bool = False,
) -> SyncReport:
    """One-shot sync of all matching files.

    Args:
        client: Snipara client instance (must have .upload() method)
        root: Project root directory (default: cwd)
        include: Glob patterns to include
        exclude: Glob patterns to exclude
        dry_run: If True, report what would be synced without uploading
    """
    from snipara.config import load_config

    config = load_config()
    root = root or Path.cwd()
    include = include or config.sync.include
    exclude = exclude or config.sync.exclude

    files = collect_matching_files(root, include, exclude)
    report = SyncReport(total_files=len(files))

    for filepath in files:
        relative = str(filepath.relative_to(root))
        if dry_run:
            report.uploaded.append(relative)
            continue
        try:
            content = filepath.read_text(encoding="utf-8")
            await client.upload(relative, content)
            report.uploaded.append(relative)
        except UnicodeDecodeError:
            report.skipped.append(relative)
        except Exception as e:
            report.errors.append((relative, str(e)))

    return report


async def watch_and_sync(
    client: Any,
    root: Path | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    debounce_ms: int = 500,
) -> None:
    """Watch for file changes and sync to Snipara. Blocking.

    Args:
        client: Snipara client instance
        root: Project root to watch
        include: Glob patterns to include
        exclude: Glob patterns to exclude
        debounce_ms: Debounce interval in milliseconds
    """
    try:
        from watchfiles import Change, awatch
    except ImportError:
        raise ImportError(
            "watchfiles is required for file watching. "
            "Install with: pip install snipara[watch]"
        )

    from snipara.config import load_config

    config = load_config()
    root = (root or Path.cwd()).resolve()
    include = include or config.sync.include
    exclude = exclude or config.sync.exclude

    print(f"Watching {root} for changes...")
    print(f"  Include: {include}")
    print(f"  Exclude: {exclude}")
    print(f"  Debounce: {debounce_ms}ms")
    print()

    async for changes in awatch(root, debounce=debounce_ms):
        for change_type, path_str in changes:
            path = Path(path_str)

            if not matches_patterns(path_str, include, exclude, root):
                continue

            if change_type in (Change.added, Change.modified):
                relative = str(path.relative_to(root))
                try:
                    content = path.read_text(encoding="utf-8")
                    await client.upload(relative, content)
                    print(f"  Synced: {relative}")
                except UnicodeDecodeError:
                    print(f"  Skip (binary): {relative}")
                except Exception as e:
                    print(f"  Error: {relative} — {e}")

            elif change_type == Change.deleted:
                relative = str(path.relative_to(root))
                print(f"  Deleted: {relative} (not synced — use snipara sync --delete-missing)")
