"""Unit tests for cli.conflict_resolver module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.cli.conflict_resolver import ConflictResolver
from src.cli.errors import CLIError
from src.cli.models import ConflictInfo, ConflictResolutionResult, MergeResult


class TestConflictResolver:
    """Test cases for ConflictResolver."""

    @pytest.fixture
    def mock_baseline_manager(self):
        """Create mock BaselineManager."""
        manager = Mock()
        manager.is_initialized.return_value = True
        return manager

    @pytest.fixture
    def resolver(self, mock_baseline_manager):
        """Create ConflictResolver instance with mock dependencies."""
        return ConflictResolver(baseline_manager=mock_baseline_manager)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def create_temp_file(self, temp_dir: Path, name: str, content: str) -> Path:
        """Helper to create a temporary file with content."""
        file_path = temp_dir / name
        file_path.write_text(content, encoding="utf-8")
        return file_path


class TestAutoMergeSuccess(TestConflictResolver):
    """Test successful auto-merge scenarios."""

    def test_auto_merge_non_overlapping_changes(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """Auto-merge succeeds when local and remote changes don't overlap."""
        # Arrange
        baseline_content = "Line 1\nLine 2\nLine 3\n"
        local_content = "Line 1 LOCAL\nLine 2\nLine 3\n"
        remote_content = "Line 1\nLine 2\nLine 3 REMOTE\n"
        merged_content = "Line 1 LOCAL\nLine 2\nLine 3 REMOTE\n"

        local_file = self.create_temp_file(temp_dir, "page_123.md", local_content)
        local_pages = {"123": str(local_file)}
        remote_pages = {"123": remote_content}

        # Mock baseline manager
        mock_baseline_manager.get_baseline_content.return_value = baseline_content
        mock_baseline_manager.merge_file.return_value = MergeResult(
            merged_content=merged_content,
            has_conflicts=False,
            conflict_count=0
        )

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["123"],
            local_pages=local_pages,
            remote_content=remote_pages,
            dryrun=False
        )

        # Assert
        assert result.auto_merged_count == 1
        assert result.failed_count == 0
        assert len(result.conflicts) == 0

        # Verify merged content was written to file
        assert local_file.read_text(encoding="utf-8") == merged_content

        # Verify baseline manager was called correctly
        mock_baseline_manager.get_baseline_content.assert_called_once_with("123")
        mock_baseline_manager.merge_file.assert_called_once_with(
            baseline_content=baseline_content,
            local_content=local_content,
            remote_content=remote_content,
            page_id="123"
        )

    def test_auto_merge_multiple_pages(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """Auto-merge multiple pages successfully."""
        # Arrange
        baseline1 = "Content A\n"
        local1 = "Content A modified\n"
        remote1 = "Content A\nNew line\n"
        merged1 = "Content A modified\nNew line\n"

        baseline2 = "Content B\n"
        local2 = "Content B local\n"
        remote2 = "Content B remote\n"
        merged2 = "Content B merged\n"

        file1 = self.create_temp_file(temp_dir, "page_1.md", local1)
        file2 = self.create_temp_file(temp_dir, "page_2.md", local2)

        local_pages = {"1": str(file1), "2": str(file2)}
        remote_pages = {"1": remote1, "2": remote2}

        # Mock baseline manager for both pages
        mock_baseline_manager.get_baseline_content.side_effect = [baseline1, baseline2]
        mock_baseline_manager.merge_file.side_effect = [
            MergeResult(merged_content=merged1, has_conflicts=False, conflict_count=0),
            MergeResult(merged_content=merged2, has_conflicts=False, conflict_count=0)
        ]

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["1", "2"],
            local_pages=local_pages,
            remote_content=remote_pages
        )

        # Assert
        assert result.auto_merged_count == 2
        assert result.failed_count == 0
        assert len(result.conflicts) == 0
        assert file1.read_text(encoding="utf-8") == merged1
        assert file2.read_text(encoding="utf-8") == merged2


class TestConflictMarkers(TestConflictResolver):
    """Test scenarios where merge produces conflict markers."""

    def test_merge_with_overlapping_changes(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """Merge produces conflict markers when changes overlap."""
        # Arrange
        baseline_content = "Line 1\nLine 2\nLine 3\n"
        local_content = "Line 1\nLine 2 LOCAL\nLine 3\n"
        remote_content = "Line 1\nLine 2 REMOTE\nLine 3\n"
        conflict_markers = (
            "Line 1\n"
            "<<<<<<< LOCAL\n"
            "Line 2 LOCAL\n"
            "=======\n"
            "Line 2 REMOTE\n"
            ">>>>>>> REMOTE\n"
            "Line 3\n"
        )

        local_file = self.create_temp_file(temp_dir, "page_123.md", local_content)
        local_pages = {"123": str(local_file)}
        remote_pages = {"123": remote_content}
        page_titles = {"123": "Test Page"}

        # Mock baseline manager
        mock_baseline_manager.get_baseline_content.return_value = baseline_content
        mock_baseline_manager.merge_file.return_value = MergeResult(
            merged_content=conflict_markers,
            has_conflicts=True,
            conflict_count=1
        )

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["123"],
            local_pages=local_pages,
            remote_content=remote_pages,
            page_titles=page_titles,
            dryrun=False
        )

        # Assert
        assert result.auto_merged_count == 0
        assert result.failed_count == 1
        assert len(result.conflicts) == 1

        conflict_info = result.conflicts[0]
        assert conflict_info.page_id == "123"
        assert conflict_info.title == "Test Page"
        assert conflict_info.local_path == local_file
        assert conflict_info.conflict_markers == conflict_markers

        # Verify conflict markers were written to file
        assert local_file.read_text(encoding="utf-8") == conflict_markers

    def test_multiple_conflict_regions(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """Merge produces multiple conflict regions."""
        # Arrange
        baseline_content = "A\nB\nC\nD\n"
        local_content = "A local\nB\nC local\nD\n"
        remote_content = "A remote\nB\nC remote\nD\n"
        conflict_markers = (
            "<<<<<<< LOCAL\nA local\n=======\nA remote\n>>>>>>> REMOTE\n"
            "B\n"
            "<<<<<<< LOCAL\nC local\n=======\nC remote\n>>>>>>> REMOTE\n"
            "D\n"
        )

        local_file = self.create_temp_file(temp_dir, "page_456.md", local_content)
        local_pages = {"456": str(local_file)}
        remote_pages = {"456": remote_content}

        # Mock baseline manager
        mock_baseline_manager.get_baseline_content.return_value = baseline_content
        mock_baseline_manager.merge_file.return_value = MergeResult(
            merged_content=conflict_markers,
            has_conflicts=True,
            conflict_count=2
        )

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["456"],
            local_pages=local_pages,
            remote_content=remote_pages
        )

        # Assert
        assert result.failed_count == 1
        assert result.conflicts[0].conflict_markers == conflict_markers


class TestMissingBaseline(TestConflictResolver):
    """Test scenarios where baseline content is missing."""

    def test_no_baseline_writes_manual_conflict_markers(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """When baseline is missing, write manual conflict markers."""
        # Arrange
        local_content = "Local version\n"
        remote_content = "Remote version\n"
        expected_markers = (
            "<<<<<<< LOCAL\n"
            "Local version\n"
            "\n"
            "=======\n"
            "Remote version\n"
            "\n"
            ">>>>>>> REMOTE\n"
        )

        local_file = self.create_temp_file(temp_dir, "page_789.md", local_content)
        local_pages = {"789": str(local_file)}
        remote_pages = {"789": remote_content}
        page_titles = {"789": "No Baseline Page"}

        # Mock baseline manager - no baseline content
        mock_baseline_manager.get_baseline_content.return_value = None

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["789"],
            local_pages=local_pages,
            remote_content=remote_pages,
            page_titles=page_titles
        )

        # Assert
        assert result.auto_merged_count == 0
        assert result.failed_count == 1
        assert len(result.conflicts) == 1

        conflict_info = result.conflicts[0]
        assert conflict_info.page_id == "789"
        assert conflict_info.title == "No Baseline Page"
        assert conflict_info.conflict_markers == expected_markers

        # Verify manual conflict markers were written
        assert local_file.read_text(encoding="utf-8") == expected_markers

        # Verify merge_file was NOT called (no baseline = no 3-way merge)
        mock_baseline_manager.merge_file.assert_not_called()


class TestDryrunMode(TestConflictResolver):
    """Test dryrun mode behavior."""

    def test_dryrun_auto_merge_no_file_write(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """Dryrun mode: auto-merge detected but file not written."""
        # Arrange
        baseline_content = "Original\n"
        local_content = "Local change\n"
        remote_content = "Remote change\n"
        merged_content = "Merged content\n"

        local_file = self.create_temp_file(temp_dir, "page_dry.md", local_content)
        local_pages = {"dry": str(local_file)}
        remote_pages = {"dry": remote_content}

        mock_baseline_manager.get_baseline_content.return_value = baseline_content
        mock_baseline_manager.merge_file.return_value = MergeResult(
            merged_content=merged_content,
            has_conflicts=False,
            conflict_count=0
        )

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["dry"],
            local_pages=local_pages,
            remote_content=remote_pages,
            dryrun=True
        )

        # Assert
        assert result.auto_merged_count == 1
        assert result.failed_count == 0

        # Verify file was NOT modified
        assert local_file.read_text(encoding="utf-8") == local_content

    def test_dryrun_conflict_no_file_write(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """Dryrun mode: conflict detected but markers not written."""
        # Arrange
        baseline_content = "Original\n"
        local_content = "Local\n"
        remote_content = "Remote\n"
        conflict_markers = "<<<<<<< LOCAL\nLocal\n=======\nRemote\n>>>>>>> REMOTE\n"

        local_file = self.create_temp_file(temp_dir, "page_dry2.md", local_content)
        local_pages = {"dry2": str(local_file)}
        remote_pages = {"dry2": remote_content}

        mock_baseline_manager.get_baseline_content.return_value = baseline_content
        mock_baseline_manager.merge_file.return_value = MergeResult(
            merged_content=conflict_markers,
            has_conflicts=True,
            conflict_count=1
        )

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["dry2"],
            local_pages=local_pages,
            remote_content=remote_pages,
            dryrun=True
        )

        # Assert
        assert result.failed_count == 1

        # Verify file was NOT modified
        assert local_file.read_text(encoding="utf-8") == local_content

    def test_dryrun_missing_baseline_no_file_write(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """Dryrun mode: missing baseline conflict markers not written."""
        # Arrange
        local_content = "Local\n"
        remote_content = "Remote\n"

        local_file = self.create_temp_file(temp_dir, "page_dry3.md", local_content)
        local_pages = {"dry3": str(local_file)}
        remote_pages = {"dry3": remote_content}

        mock_baseline_manager.get_baseline_content.return_value = None

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["dry3"],
            local_pages=local_pages,
            remote_content=remote_pages,
            dryrun=True
        )

        # Assert
        assert result.failed_count == 1

        # Verify file was NOT modified
        assert local_file.read_text(encoding="utf-8") == local_content


class TestErrorHandling(TestConflictResolver):
    """Test error handling scenarios."""

    def test_baseline_not_initialized_raises_error(
        self, mock_baseline_manager
    ):
        """Raise CLIError when baseline repository is not initialized."""
        # Arrange
        mock_baseline_manager.is_initialized.return_value = False
        resolver = ConflictResolver(baseline_manager=mock_baseline_manager)

        # Act & Assert
        with pytest.raises(CLIError) as exc_info:
            resolver.resolve_conflicts(
                conflicting_page_ids=["123"],
                local_pages={"123": "/path/to/file.md"},
                remote_content={"123": "content"}
            )

        assert "Baseline repository not initialized" in str(exc_info.value)

    def test_missing_local_path_skips_page(
        self, resolver, mock_baseline_manager
    ):
        """Skip page when local path is missing."""
        # Arrange
        local_pages = {}  # No local path for page 123
        remote_pages = {"123": "remote content"}

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["123"],
            local_pages=local_pages,
            remote_content=remote_pages
        )

        # Assert
        assert result.auto_merged_count == 0
        assert result.failed_count == 0
        assert len(result.conflicts) == 0

        # Verify no merge attempt
        mock_baseline_manager.get_baseline_content.assert_not_called()

    def test_missing_remote_content_skips_page(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """Skip page when remote content is missing."""
        # Arrange
        local_file = self.create_temp_file(temp_dir, "page.md", "local content")
        local_pages = {"123": str(local_file)}
        remote_pages = {}  # No remote content

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["123"],
            local_pages=local_pages,
            remote_content=remote_pages
        )

        # Assert
        assert result.auto_merged_count == 0
        assert result.failed_count == 0
        assert len(result.conflicts) == 0

        # Verify no merge attempt
        mock_baseline_manager.get_baseline_content.assert_not_called()

    def test_local_file_read_error_marks_as_conflict(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """File read error marks page as unresolved conflict."""
        # Arrange
        # Create a file path that doesn't exist
        local_file = temp_dir / "nonexistent.md"
        local_pages = {"123": str(local_file)}
        remote_pages = {"123": "remote content"}
        page_titles = {"123": "Error Page"}

        mock_baseline_manager.get_baseline_content.return_value = "baseline"

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["123"],
            local_pages=local_pages,
            remote_content=remote_pages,
            page_titles=page_titles
        )

        # Assert
        assert result.auto_merged_count == 0
        assert result.failed_count == 1
        assert len(result.conflicts) == 1

        conflict_info = result.conflicts[0]
        assert conflict_info.page_id == "123"
        assert conflict_info.title == "Error Page"
        assert "Error reading local file" in conflict_info.conflict_markers

    def test_exception_during_merge_continues_processing(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """Exception during merge is caught and processing continues."""
        # Arrange
        file1 = self.create_temp_file(temp_dir, "page1.md", "content 1")
        file2 = self.create_temp_file(temp_dir, "page2.md", "content 2")

        local_pages = {"1": str(file1), "2": str(file2)}
        remote_pages = {"1": "remote 1", "2": "remote 2"}

        # Mock: First page throws exception, second succeeds
        mock_baseline_manager.get_baseline_content.side_effect = [
            Exception("Baseline error"),
            "baseline 2"
        ]
        mock_baseline_manager.merge_file.return_value = MergeResult(
            merged_content="merged 2",
            has_conflicts=False,
            conflict_count=0
        )

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["1", "2"],
            local_pages=local_pages,
            remote_content=remote_pages
        )

        # Assert
        # Page 1 failed, page 2 succeeded
        assert result.auto_merged_count == 1
        assert result.failed_count == 1
        assert len(result.conflicts) == 1
        assert result.conflicts[0].page_id == "1"


class TestPageTitles(TestConflictResolver):
    """Test page title handling."""

    def test_page_titles_used_in_conflict_info(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """Page titles are included in conflict info."""
        # Arrange
        local_file = self.create_temp_file(temp_dir, "page.md", "local")
        local_pages = {"123": str(local_file)}
        remote_pages = {"123": "remote"}
        page_titles = {"123": "My Awesome Page"}

        mock_baseline_manager.get_baseline_content.return_value = "baseline"
        mock_baseline_manager.merge_file.return_value = MergeResult(
            merged_content="<<<conflict>>>",
            has_conflicts=True,
            conflict_count=1
        )

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["123"],
            local_pages=local_pages,
            remote_content=remote_pages,
            page_titles=page_titles
        )

        # Assert
        assert result.conflicts[0].title == "My Awesome Page"

    def test_missing_page_title_uses_page_id(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """When page title is missing, use page ID as title."""
        # Arrange
        local_file = self.create_temp_file(temp_dir, "page.md", "local")
        local_pages = {"456": str(local_file)}
        remote_pages = {"456": "remote"}
        page_titles = {}  # No title provided

        mock_baseline_manager.get_baseline_content.return_value = "baseline"
        mock_baseline_manager.merge_file.return_value = MergeResult(
            merged_content="<<<conflict>>>",
            has_conflicts=True,
            conflict_count=1
        )

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["456"],
            local_pages=local_pages,
            remote_content=remote_pages,
            page_titles=page_titles
        )

        # Assert
        assert result.conflicts[0].title == "456"

    def test_none_page_titles_dict_uses_page_id(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """When page_titles is None, use page ID as title."""
        # Arrange
        local_file = self.create_temp_file(temp_dir, "page.md", "local")
        local_pages = {"789": str(local_file)}
        remote_pages = {"789": "remote"}

        mock_baseline_manager.get_baseline_content.return_value = "baseline"
        mock_baseline_manager.merge_file.return_value = MergeResult(
            merged_content="<<<conflict>>>",
            has_conflicts=True,
            conflict_count=1
        )

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["789"],
            local_pages=local_pages,
            remote_content=remote_pages,
            page_titles=None  # None instead of dict
        )

        # Assert
        assert result.conflicts[0].title == "789"


class TestMixedResults(TestConflictResolver):
    """Test scenarios with mixed auto-merge and conflict results."""

    def test_mixed_auto_merge_and_conflicts(
        self, resolver, mock_baseline_manager, temp_dir
    ):
        """Process multiple pages with some auto-merged and some conflicted."""
        # Arrange
        file1 = self.create_temp_file(temp_dir, "page1.md", "local 1")
        file2 = self.create_temp_file(temp_dir, "page2.md", "local 2")
        file3 = self.create_temp_file(temp_dir, "page3.md", "local 3")

        local_pages = {"1": str(file1), "2": str(file2), "3": str(file3)}
        remote_pages = {"1": "remote 1", "2": "remote 2", "3": "remote 3"}

        # Mock baseline manager
        mock_baseline_manager.get_baseline_content.side_effect = [
            "baseline 1", "baseline 2", "baseline 3"
        ]
        mock_baseline_manager.merge_file.side_effect = [
            MergeResult(merged_content="merged 1", has_conflicts=False, conflict_count=0),  # Auto-merge
            MergeResult(merged_content="<<<conflict>>>", has_conflicts=True, conflict_count=1),  # Conflict
            MergeResult(merged_content="merged 3", has_conflicts=False, conflict_count=0)  # Auto-merge
        ]

        # Act
        result = resolver.resolve_conflicts(
            conflicting_page_ids=["1", "2", "3"],
            local_pages=local_pages,
            remote_content=remote_pages
        )

        # Assert
        assert result.auto_merged_count == 2  # Pages 1 and 3
        assert result.failed_count == 1  # Page 2
        assert len(result.conflicts) == 1
        assert result.conflicts[0].page_id == "2"

        # Verify files
        assert file1.read_text(encoding="utf-8") == "merged 1"
        assert file2.read_text(encoding="utf-8") == "<<<conflict>>>"
        assert file3.read_text(encoding="utf-8") == "merged 3"
