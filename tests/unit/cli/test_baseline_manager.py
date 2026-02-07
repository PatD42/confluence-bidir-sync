"""Unit tests for cli.baseline_manager module."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from src.cli.baseline_manager import BaselineManager
from src.cli.errors import CLIError
from src.cli.models import MergeResult


class TestBaselineManager:
    """Test cases for BaselineManager."""

    @pytest.fixture
    def temp_baseline_dir(self):
        """Create a temporary directory for baseline testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manager(self, temp_baseline_dir):
        """Create BaselineManager instance with temp directory."""
        return BaselineManager(baseline_dir=temp_baseline_dir)

    @pytest.fixture
    def initialized_manager(self, manager):
        """Create an initialized BaselineManager instance."""
        manager.initialize()
        return manager


class TestInitialization(TestBaselineManager):
    """Test BaselineManager initialization."""

    def test_init_with_custom_baseline_dir(self, temp_baseline_dir):
        """Initialize with custom baseline directory."""
        # Act
        manager = BaselineManager(baseline_dir=temp_baseline_dir)

        # Assert
        assert manager.baseline_dir == temp_baseline_dir

    def test_init_with_default_baseline_dir(self):
        """Initialize with default baseline directory."""
        # Act
        manager = BaselineManager()

        # Assert
        expected = Path.cwd() / ".confluence-sync" / "baseline"
        assert manager.baseline_dir == expected

    def test_initialize_creates_baseline_directory(self, manager):
        """Initialize should create baseline directory."""
        # Act
        manager.initialize()

        # Assert
        assert manager.baseline_dir.exists()
        assert manager.baseline_dir.is_dir()

    def test_initialize_creates_git_repository(self, manager):
        """Initialize should create .git directory."""
        # Act
        manager.initialize()

        # Assert
        git_dir = manager.baseline_dir / ".git"
        assert git_dir.exists()
        assert git_dir.is_dir()

    def test_initialize_configures_git_user(self, manager):
        """Initialize should configure git user name and email."""
        # Act
        manager.initialize()

        # Assert - Check git config
        result = subprocess.run(
            ["git", "config", "user.name"],
            cwd=manager.baseline_dir,
            capture_output=True,
            text=True,
            check=True
        )
        assert result.stdout.strip() == "Confluence Sync Baseline"

        result = subprocess.run(
            ["git", "config", "user.email"],
            cwd=manager.baseline_dir,
            capture_output=True,
            text=True,
            check=True
        )
        assert result.stdout.strip() == "baseline@confluence-sync.local"

    def test_initialize_is_idempotent(self, manager):
        """Initialize should be safe to call multiple times."""
        # Act
        manager.initialize()
        manager.initialize()  # Second call should not fail

        # Assert
        git_dir = manager.baseline_dir / ".git"
        assert git_dir.exists()

    def test_initialize_fails_if_directory_creation_fails(self):
        """Initialize should raise CLIError if directory creation fails."""
        # Arrange - Create a file where directory should be (not using fixture)
        with tempfile.TemporaryDirectory() as tmpdir:
            parent_dir = Path(tmpdir) / "parent"
            parent_dir.mkdir(parents=True, exist_ok=True)
            blocking_file = parent_dir / "baseline"
            blocking_file.write_text("blocking file")

            manager = BaselineManager(baseline_dir=blocking_file)

            # Act & Assert
            with pytest.raises(CLIError) as exc_info:
                manager.initialize()

            assert "Failed to create baseline directory" in str(exc_info.value)

    @patch('subprocess.run')
    def test_initialize_fails_if_git_not_found(self, mock_run, manager):
        """Initialize should raise CLIError if git command not found."""
        # Arrange
        mock_run.side_effect = FileNotFoundError()

        # Act & Assert
        with pytest.raises(CLIError) as exc_info:
            manager.initialize()

        assert "git command not found" in str(exc_info.value)

    @patch('subprocess.run')
    def test_initialize_fails_if_git_init_fails(self, mock_run, manager):
        """Initialize should raise CLIError if git init fails."""
        # Arrange
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["git", "init"], stderr="git init failed"
        )

        # Act & Assert
        with pytest.raises(CLIError) as exc_info:
            manager.initialize()

        assert "Failed to initialize git repository" in str(exc_info.value)

    def test_is_initialized_returns_false_before_init(self, manager):
        """is_initialized should return False before initialization."""
        # Assert
        assert manager.is_initialized() is False

    def test_is_initialized_returns_true_after_init(self, manager):
        """is_initialized should return True after initialization."""
        # Act
        manager.initialize()

        # Assert
        assert manager.is_initialized() is True


class TestUpdateBaseline(TestBaselineManager):
    """Test baseline update operations."""

    def test_update_baseline_creates_file(self, initialized_manager):
        """update_baseline should create baseline file."""
        # Arrange
        page_id = "123456"
        content = "# Test Page\n\nContent here"

        # Act
        initialized_manager.update_baseline(page_id, content)

        # Assert
        baseline_file = initialized_manager.baseline_dir / f"{page_id}.md"
        assert baseline_file.exists()
        assert baseline_file.read_text(encoding="utf-8") == content

    def test_update_baseline_commits_to_git(self, initialized_manager):
        """update_baseline should commit the file to git."""
        # Arrange
        page_id = "123456"
        content = "# Test Page\n\nContent here"

        # Act
        initialized_manager.update_baseline(page_id, content)

        # Assert - Check git log
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=initialized_manager.baseline_dir,
            capture_output=True,
            text=True,
            check=True
        )
        assert f"Update baseline for page {page_id}" in result.stdout

    def test_update_baseline_overwrites_existing_file(self, initialized_manager):
        """update_baseline should overwrite existing baseline."""
        # Arrange
        page_id = "123456"
        old_content = "# Old Content"
        new_content = "# New Content"

        # Act
        initialized_manager.update_baseline(page_id, old_content)
        initialized_manager.update_baseline(page_id, new_content)

        # Assert
        baseline_file = initialized_manager.baseline_dir / f"{page_id}.md"
        assert baseline_file.read_text(encoding="utf-8") == new_content

    def test_update_baseline_handles_no_changes(self, initialized_manager):
        """update_baseline should handle no changes gracefully."""
        # Arrange
        page_id = "123456"
        content = "# Test Page"

        # Act - Update with same content twice
        initialized_manager.update_baseline(page_id, content)
        initialized_manager.update_baseline(page_id, content)  # No changes

        # Assert - Should not raise error
        baseline_file = initialized_manager.baseline_dir / f"{page_id}.md"
        assert baseline_file.exists()

    @patch('subprocess.run')
    def test_update_baseline_handles_nothing_added_to_commit(self, mock_run, initialized_manager):
        """update_baseline should handle 'nothing added to commit' gracefully.

        Git outputs 'nothing added to commit but untracked files present' when
        git add is run on an unchanged file and then commit is attempted.
        This should not be treated as an error.
        """
        # Arrange
        page_id = "123456"
        content = "# Test Page"

        # Mock git add to succeed, but git commit to return "nothing added to commit"
        def side_effect(*args, **kwargs):
            if "add" in args[0]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if "commit" in args[0]:
                return MagicMock(
                    returncode=1,
                    stdout="On branch master\nnothing added to commit but untracked files present",
                    stderr=""
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect

        # Act - Should not raise error
        initialized_manager.update_baseline(page_id, content)

        # Assert - File should exist
        baseline_file = initialized_manager.baseline_dir / f"{page_id}.md"
        assert baseline_file.exists()

    def test_update_baseline_fails_if_not_initialized(self, manager):
        """update_baseline should raise CLIError if not initialized."""
        # Arrange
        page_id = "123456"
        content = "# Test Page"

        # Act & Assert
        with pytest.raises(CLIError) as exc_info:
            manager.update_baseline(page_id, content)

        assert "not initialized" in str(exc_info.value)

    def test_update_baseline_handles_unicode_content(self, initialized_manager):
        """update_baseline should handle unicode content correctly."""
        # Arrange
        page_id = "123456"
        content = "# Test Page\n\nUnicode: ❤️ 你好 🚀"

        # Act
        initialized_manager.update_baseline(page_id, content)

        # Assert
        baseline_file = initialized_manager.baseline_dir / f"{page_id}.md"
        assert baseline_file.read_text(encoding="utf-8") == content

    @patch('subprocess.run')
    def test_update_baseline_fails_if_git_add_fails(self, mock_run, initialized_manager):
        """update_baseline should raise CLIError if git add fails."""
        # Arrange
        page_id = "123456"
        content = "# Test Page"

        # Mock git add to fail
        def side_effect(*args, **kwargs):
            if "add" in args[0]:
                raise subprocess.CalledProcessError(
                    1, ["git", "add"], stderr="git add failed"
                )
            # Let other git commands succeed
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect

        # Act & Assert
        with pytest.raises(CLIError) as exc_info:
            initialized_manager.update_baseline(page_id, content)

        assert "Failed to stage baseline file" in str(exc_info.value)


class TestGetBaselineContent(TestBaselineManager):
    """Test baseline content retrieval."""

    def test_get_baseline_content_returns_content(self, initialized_manager):
        """get_baseline_content should return stored content."""
        # Arrange
        page_id = "123456"
        content = "# Test Page\n\nContent here"
        initialized_manager.update_baseline(page_id, content)

        # Act
        retrieved = initialized_manager.get_baseline_content(page_id)

        # Assert
        assert retrieved == content

    def test_get_baseline_content_returns_none_if_not_found(self, initialized_manager):
        """get_baseline_content should return None if baseline doesn't exist."""
        # Arrange
        page_id = "999999999"

        # Act
        retrieved = initialized_manager.get_baseline_content(page_id)

        # Assert
        assert retrieved is None

    def test_get_baseline_content_fails_if_not_initialized(self, manager):
        """get_baseline_content should raise CLIError if not initialized."""
        # Arrange
        page_id = "123456"

        # Act & Assert
        with pytest.raises(CLIError) as exc_info:
            manager.get_baseline_content(page_id)

        assert "not initialized" in str(exc_info.value)

    def test_get_baseline_content_handles_unicode(self, initialized_manager):
        """get_baseline_content should handle unicode content correctly."""
        # Arrange
        page_id = "123456"
        content = "# Test Page\n\nUnicode: ❤️ 你好 🚀"
        initialized_manager.update_baseline(page_id, content)

        # Act
        retrieved = initialized_manager.get_baseline_content(page_id)

        # Assert
        assert retrieved == content


class TestMergeFile(TestBaselineManager):
    """Test 3-way merge operations."""

    def test_merge_file_clean_merge_no_conflicts(self, manager):
        """merge_file should auto-merge non-overlapping changes."""
        # Arrange
        baseline_content = "# Title\n\nOriginal content\n\nMore content"
        local_content = "# Title\n\nLocal changes\n\nMore content"
        remote_content = "# Title\n\nOriginal content\n\nRemote changes"
        page_id = "123456"

        # Act
        result = manager.merge_file(
            baseline_content, local_content, remote_content, page_id
        )

        # Assert
        assert isinstance(result, MergeResult)
        assert result.has_conflicts is False
        assert result.conflict_count == 0
        assert "Local changes" in result.merged_content
        assert "Remote changes" in result.merged_content

    def test_merge_file_detects_conflicts(self, manager):
        """merge_file should detect overlapping changes."""
        # Arrange - Both modify the same line
        baseline_content = "# Title\n\nOriginal content"
        local_content = "# Title\n\nLocal changes"
        remote_content = "# Title\n\nRemote changes"
        page_id = "123456"

        # Act
        result = manager.merge_file(
            baseline_content, local_content, remote_content, page_id
        )

        # Assert
        assert result.has_conflicts is True
        assert result.conflict_count == 1
        assert "<<<<<<<" in result.merged_content
        assert "=======" in result.merged_content
        assert ">>>>>>>" in result.merged_content

    def test_merge_file_conflict_markers_contain_labels(self, manager):
        """merge_file should include labels in conflict markers."""
        # Arrange
        baseline_content = "Original"
        local_content = "Local"
        remote_content = "Remote"
        page_id = "123456"

        # Act
        result = manager.merge_file(
            baseline_content, local_content, remote_content, page_id
        )

        # Assert
        assert "local" in result.merged_content.lower()
        assert "remote" in result.merged_content.lower()

    def test_merge_file_multiple_conflicts(self, manager):
        """merge_file should detect multiple conflict regions."""
        # Arrange - Multiple conflicting sections with unchanged sections between
        baseline_content = "Section 1\n\nUnchanged A\n\nSection 2\n\nUnchanged B\n\nSection 3"
        local_content = "Local 1\n\nUnchanged A\n\nLocal 2\n\nUnchanged B\n\nLocal 3"
        remote_content = "Remote 1\n\nUnchanged A\n\nRemote 2\n\nUnchanged B\n\nRemote 3"
        page_id = "123456"

        # Act
        result = manager.merge_file(
            baseline_content, local_content, remote_content, page_id
        )

        # Assert
        assert result.has_conflicts is True
        assert result.conflict_count >= 1  # At least one conflict region (may be merged into one)

    def test_merge_file_identical_changes_no_conflict(self, manager):
        """merge_file should not create conflict for identical changes."""
        # Arrange - Both make the same change
        baseline_content = "# Title\n\nOriginal"
        local_content = "# Title\n\nSame change"
        remote_content = "# Title\n\nSame change"
        page_id = "123456"

        # Act
        result = manager.merge_file(
            baseline_content, local_content, remote_content, page_id
        )

        # Assert
        assert result.has_conflicts is False
        assert result.conflict_count == 0
        assert "Same change" in result.merged_content

    def test_merge_file_handles_empty_baseline(self, manager):
        """merge_file should handle empty baseline (new file)."""
        # Arrange
        baseline_content = ""
        local_content = "Local content"
        remote_content = "Remote content"
        page_id = "123456"

        # Act
        result = manager.merge_file(
            baseline_content, local_content, remote_content, page_id
        )

        # Assert
        assert isinstance(result, MergeResult)
        # Both added different content - should conflict
        assert result.has_conflicts is True

    def test_merge_file_handles_unicode_content(self, manager):
        """merge_file should handle unicode content correctly."""
        # Arrange
        baseline_content = "# Title\n\nOriginal"
        local_content = "# Title\n\nLocal: ❤️ 你好"
        remote_content = "# Title\n\nRemote: 🚀 мир"
        page_id = "123456"

        # Act
        result = manager.merge_file(
            baseline_content, local_content, remote_content, page_id
        )

        # Assert
        assert isinstance(result, MergeResult)
        # Both modified same section - should conflict
        assert result.has_conflicts is True

    @patch('src.cli.baseline_manager.merge_content_with_table_awareness')
    @patch('subprocess.run')
    def test_merge_file_fails_if_git_not_found(self, mock_run, mock_table_merge, manager):
        """merge_file should raise CLIError if git command not found."""
        # Arrange - table merge fails, forcing git fallback
        mock_table_merge.side_effect = Exception("Table merge failed")
        mock_run.side_effect = FileNotFoundError()

        # Act & Assert
        with pytest.raises(CLIError) as exc_info:
            manager.merge_file("baseline", "local", "remote", "123456")

        assert "git command not found" in str(exc_info.value)

    @patch('src.cli.baseline_manager.merge_content_with_table_awareness')
    @patch('subprocess.run')
    def test_merge_file_fails_on_unexpected_error(self, mock_run, mock_table_merge, manager):
        """merge_file should raise CLIError on unexpected git errors."""
        # Arrange - table merge fails, forcing git fallback
        mock_table_merge.side_effect = Exception("Table merge failed")
        mock_run.return_value = MagicMock(
            returncode=2,  # Unexpected error (not 0 or 1)
            stderr="unexpected error"
        )

        # Act & Assert
        with pytest.raises(CLIError) as exc_info:
            manager.merge_file("baseline", "local", "remote", "123456")

        assert "git merge-file failed" in str(exc_info.value)

    def test_merge_file_cleans_up_temp_files(self, manager):
        """merge_file should clean up temporary files."""
        # Arrange
        baseline_content = "baseline"
        local_content = "local"
        remote_content = "remote"
        page_id = "123456"

        # Get temp directory before merge
        initial_temp_count = len(list(Path(tempfile.gettempdir()).glob("confluence-merge-*")))

        # Act
        result = manager.merge_file(
            baseline_content, local_content, remote_content, page_id
        )

        # Assert - Temp directory should be cleaned up
        final_temp_count = len(list(Path(tempfile.gettempdir()).glob("confluence-merge-*")))
        assert final_temp_count == initial_temp_count


class TestEdgeCases(TestBaselineManager):
    """Test edge cases and boundary conditions."""

    def test_baseline_survives_reinitialization(self, initialized_manager):
        """Baseline content should survive reinitialization."""
        # Arrange
        page_id = "123456"
        content = "# Test Page"
        initialized_manager.update_baseline(page_id, content)

        # Act - Reinitialize
        initialized_manager.initialize()

        # Assert - Content should still be there
        retrieved = initialized_manager.get_baseline_content(page_id)
        assert retrieved == content

    def test_update_multiple_pages(self, initialized_manager):
        """Should handle multiple pages independently."""
        # Arrange
        pages = {
            "111": "# Page 1",
            "222": "# Page 2",
            "333": "# Page 3",
        }

        # Act
        for page_id, content in pages.items():
            initialized_manager.update_baseline(page_id, content)

        # Assert
        for page_id, content in pages.items():
            retrieved = initialized_manager.get_baseline_content(page_id)
            assert retrieved == content

    def test_empty_content_handling(self, initialized_manager):
        """Should handle empty content correctly."""
        # Arrange
        page_id = "123456"
        content = ""

        # Act
        initialized_manager.update_baseline(page_id, content)

        # Assert
        retrieved = initialized_manager.get_baseline_content(page_id)
        assert retrieved == content

    def test_large_content_handling(self, initialized_manager):
        """Should handle large content correctly."""
        # Arrange
        page_id = "123456"
        # Create large content (100KB)
        content = "# Large Page\n\n" + ("Lorem ipsum dolor sit amet. " * 3600)

        # Act
        initialized_manager.update_baseline(page_id, content)

        # Assert
        retrieved = initialized_manager.get_baseline_content(page_id)
        assert retrieved == content
        assert len(retrieved) > 100000

    def test_page_id_with_special_characters(self, initialized_manager):
        """Should reject page IDs with special characters (H4 security)."""
        # Arrange
        page_id = "page-123_456"  # Non-numeric characters should be rejected
        content = "# Test"

        # Act & Assert - should reject invalid page_id
        with pytest.raises(CLIError) as exc_info:
            initialized_manager.update_baseline(page_id, content)

        assert "Invalid page_id format" in str(exc_info.value)


class TestLogging(TestBaselineManager):
    """Test logging behavior."""

    def test_initialize_logs_creation(self, manager, caplog):
        """initialize should log baseline repository creation."""
        # Act
        with caplog.at_level("INFO"):
            manager.initialize()

        # Assert
        assert "Initializing baseline repository" in caplog.text
        assert "initialized successfully" in caplog.text

    def test_update_baseline_logs_update(self, initialized_manager, caplog):
        """update_baseline should log baseline updates."""
        # Arrange
        page_id = "123456"
        content = "# Test"

        # Act
        with caplog.at_level("INFO"):
            initialized_manager.update_baseline(page_id, content)

        # Assert
        assert f"Updating baseline for page {page_id}" in caplog.text
        assert "updated successfully" in caplog.text

    def test_merge_file_logs_merge_operation(self, manager, caplog):
        """merge_file should log merge operation."""
        # Arrange
        page_id = "123456"

        # Act
        with caplog.at_level("INFO"):
            result = manager.merge_file(
                "baseline", "local", "remote", page_id
            )

        # Assert
        assert f"Performing 3-way merge for page {page_id}" in caplog.text
        if result.has_conflicts:
            # Table-aware merge uses different log message
            assert "conflict" in caplog.text.lower()
        else:
            # Table-aware merge success message
            assert "successful" in caplog.text.lower() or "clean" in caplog.text.lower()


class TestConflictMarkerDetectionInBaseline:
    """Test cases for conflict marker detection in baseline updates."""

    @pytest.fixture
    def temp_baseline_dir(self):
        """Create a temporary directory for baseline testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manager(self, temp_baseline_dir):
        """Create BaselineManager instance with temp directory."""
        return BaselineManager(baseline_dir=temp_baseline_dir)

    @pytest.fixture
    def initialized_manager(self, manager):
        """Create and initialize baseline manager."""
        manager.initialize()
        return manager

    def test_update_baseline_refuses_content_with_conflict_markers(
        self, initialized_manager, temp_baseline_dir, caplog
    ):
        """update_baseline should refuse content with unresolved conflict markers."""
        # Arrange
        page_id = "12345"
        corrupted_content = """# Test Page

<<<<<<< local
My local version
=======
Their version
>>>>>>> remote

More content
"""

        # Act
        with caplog.at_level("ERROR"):
            initialized_manager.update_baseline(page_id, corrupted_content)

        # Assert - should NOT create baseline file
        baseline_file = temp_baseline_dir / f"{page_id}.md"
        assert not baseline_file.exists(), "Baseline file should not be created for content with conflict markers"

        # Should log error
        assert "REFUSING to update baseline" in caplog.text
        assert "conflict markers" in caplog.text

    def test_update_baseline_allows_clean_content(
        self, initialized_manager, temp_baseline_dir
    ):
        """update_baseline should allow clean content without conflict markers."""
        # Arrange
        page_id = "12345"
        clean_content = """# Test Page

Normal content here.
Some math: 5 < 10 and 20 > 15
All clean, no conflict markers.
"""

        # Act
        initialized_manager.update_baseline(page_id, clean_content)

        # Assert - should create baseline file
        baseline_file = temp_baseline_dir / f"{page_id}.md"
        assert baseline_file.exists(), "Baseline file should be created for clean content"
        assert baseline_file.read_text() == clean_content
