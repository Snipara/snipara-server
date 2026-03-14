"""Tests for snipara.watcher — file sync and pattern matching.

Tests cover:
- Pattern matching with include/exclude globs
- File collection with deduplication
- One-shot sync_all with dry-run and real mode
- Error handling (binary files, upload failures)
- Sync report generation
- Edge cases: empty dirs, no matches, unicode errors
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from snipara.watcher import (
    SyncReport,
    collect_matching_files,
    matches_patterns,
    sync_all,
)

# ===================================================================
# SyncReport
# ===================================================================


class TestSyncReport:
    """Test SyncReport dataclass."""

    def test_empty_report(self) -> None:
        r = SyncReport()
        assert r.uploaded == []
        assert r.skipped == []
        assert r.errors == []
        assert r.total_files == 0
        assert r.uploaded_count == 0

    def test_uploaded_count(self) -> None:
        r = SyncReport(uploaded=["a.md", "b.md", "c.md"])
        assert r.uploaded_count == 3


# ===================================================================
# Pattern matching
# ===================================================================


class TestMatchesPatterns:
    """Test include/exclude glob pattern matching."""

    def test_include_match(self, tmp_path: Path) -> None:
        filepath = str(tmp_path / "docs" / "api.md")
        assert matches_patterns(
            filepath,
            include=["docs/**/*.md"],
            exclude=[],
            root=tmp_path,
        )

    def test_exclude_overrides_include(self, tmp_path: Path) -> None:
        filepath = str(tmp_path / "node_modules" / "readme.md")
        assert not matches_patterns(
            filepath,
            include=["**/*.md"],
            exclude=["node_modules/**"],
            root=tmp_path,
        )

    def test_no_include_match(self, tmp_path: Path) -> None:
        filepath = str(tmp_path / "src" / "main.py")
        assert not matches_patterns(
            filepath,
            include=["**/*.md"],
            exclude=[],
            root=tmp_path,
        )

    def test_root_level_file(self, tmp_path: Path) -> None:
        filepath = str(tmp_path / "README.md")
        assert matches_patterns(
            filepath,
            include=["*.md"],
            exclude=[],
            root=tmp_path,
        )

    def test_outside_root_returns_false(self, tmp_path: Path) -> None:
        filepath = "/completely/outside/path.md"
        assert not matches_patterns(
            filepath,
            include=["**/*.md"],
            exclude=[],
            root=tmp_path,
        )

    def test_git_excluded(self, tmp_path: Path) -> None:
        filepath = str(tmp_path / ".git" / "objects" / "abc.md")
        assert not matches_patterns(
            filepath,
            include=["**/*.md"],
            exclude=[".git/**"],
            root=tmp_path,
        )

    def test_multiple_include_patterns(self, tmp_path: Path) -> None:
        filepath_md = str(tmp_path / "file.md")
        filepath_txt = str(tmp_path / "file.txt")
        patterns = ["*.md", "*.txt"]
        assert matches_patterns(filepath_md, include=patterns, exclude=[], root=tmp_path)
        assert matches_patterns(filepath_txt, include=patterns, exclude=[], root=tmp_path)


# ===================================================================
# File collection
# ===================================================================


class TestCollectMatchingFiles:
    """Test file collection with glob patterns."""

    def test_collect_markdown_files(self, sync_project: Path) -> None:
        files = collect_matching_files(
            sync_project,
            include=["docs/**/*.md", "*.md"],
            exclude=["node_modules/**"],
        )
        relative_names = [str(f.relative_to(sync_project)) for f in files]
        assert "README.md" in relative_names
        assert "CHANGELOG.md" in relative_names
        assert "docs/getting-started.md" in relative_names
        assert "docs/api.md" in relative_names
        assert "docs/guides/auth.md" in relative_names
        # node_modules should be excluded
        assert not any("node_modules" in name for name in relative_names)

    def test_collect_no_matches(self, sync_project: Path) -> None:
        files = collect_matching_files(
            sync_project,
            include=["**/*.xyz"],
            exclude=[],
        )
        assert files == []

    def test_collect_deduplication(self, sync_project: Path) -> None:
        """Overlapping patterns should not produce duplicate entries."""
        files = collect_matching_files(
            sync_project,
            include=["**/*.md", "*.md"],  # Both match README.md
            exclude=[],
        )
        names = [str(f.relative_to(sync_project)) for f in files]
        assert names.count("README.md") == 1

    def test_collect_sorted_output(self, sync_project: Path) -> None:
        files = collect_matching_files(
            sync_project,
            include=["**/*.md"],
            exclude=[],
        )
        # Output should be sorted
        assert files == sorted(files)

    def test_collect_excludes_directories(self, sync_project: Path) -> None:
        """Only files should be collected, not directories."""
        files = collect_matching_files(
            sync_project,
            include=["docs/**"],
            exclude=[],
        )
        for f in files:
            assert f.is_file()


# ===================================================================
# sync_all
# ===================================================================


class TestSyncAll:
    """Test one-shot sync_all function."""

    @pytest.mark.asyncio
    async def test_dry_run(self, sync_project: Path) -> None:
        """Dry run should list files without uploading."""
        mock_client = MagicMock()
        mock_client.upload = AsyncMock()

        # Need to mock load_config since sync_all calls it
        mock_config = MagicMock()
        mock_config.sync.include = ["docs/**/*.md", "*.md"]
        mock_config.sync.exclude = ["node_modules/**", ".git/**"]

        with MagicMock() as _:
            report = await sync_all(
                mock_client,
                root=sync_project,
                include=["docs/**/*.md", "*.md"],
                exclude=["node_modules/**", ".git/**"],
                dry_run=True,
            )

        assert report.total_files > 0
        assert report.uploaded_count > 0
        # upload() should NOT have been called
        mock_client.upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_real_sync(self, sync_project: Path) -> None:
        """Real sync should upload files and report results."""
        mock_client = MagicMock()
        mock_client.upload = AsyncMock()

        report = await sync_all(
            mock_client,
            root=sync_project,
            include=["docs/**/*.md", "*.md"],
            exclude=["node_modules/**", ".git/**"],
            dry_run=False,
        )

        assert report.uploaded_count > 0
        assert mock_client.upload.call_count == report.uploaded_count
        # Verify relative paths were passed
        for call in mock_client.upload.call_args_list:
            path, content = call[0]
            assert not path.startswith("/")
            assert len(content) > 0

    @pytest.mark.asyncio
    async def test_binary_file_skipped(self, sync_project: Path) -> None:
        """Binary files (UnicodeDecodeError) should be skipped."""
        # Create a binary file
        binary_path = sync_project / "docs" / "image.md"
        binary_path.write_bytes(b"\x80\x81\x82\x83\xff\xfe")

        mock_client = MagicMock()
        mock_client.upload = AsyncMock()

        report = await sync_all(
            mock_client,
            root=sync_project,
            include=["docs/**/*.md"],
            exclude=[],
            dry_run=False,
        )

        # Binary file should be in skipped list
        assert any("image.md" in s for s in report.skipped)

    @pytest.mark.asyncio
    async def test_upload_error_captured(self, sync_project: Path) -> None:
        """Upload errors should be captured in report.errors."""
        mock_client = MagicMock()
        mock_client.upload = AsyncMock(side_effect=Exception("Network timeout"))

        report = await sync_all(
            mock_client,
            root=sync_project,
            include=["*.md"],
            exclude=[],
            dry_run=False,
        )

        assert len(report.errors) > 0
        # Each error is (path, error_message)
        for path, err in report.errors:
            assert "Network timeout" in err

    @pytest.mark.asyncio
    async def test_empty_directory(self, tmp_path: Path) -> None:
        """Sync on empty directory should produce empty report."""
        (tmp_path / ".git").mkdir()
        mock_client = MagicMock()

        report = await sync_all(
            mock_client,
            root=tmp_path,
            include=["**/*.md"],
            exclude=[],
        )

        assert report.total_files == 0
        assert report.uploaded_count == 0
