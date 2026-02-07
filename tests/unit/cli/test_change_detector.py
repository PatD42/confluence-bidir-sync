"""Unit tests for cli.change_detector module."""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.cli.change_detector import ChangeDetector
from src.cli.errors import CLIError
from src.cli.models import ChangeDetectionResult


class TestChangeDetector:
    """Test cases for ChangeDetector."""

    @pytest.fixture
    def detector(self):
        """Create ChangeDetector instance."""
        return ChangeDetector()

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("Test content")
            temp_path = f.name
        yield temp_path
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def base_time(self):
        """Base timestamp for testing (T0 = last_synced)."""
        return datetime(2026, 1, 30, 10, 0, 0)

    def set_file_mtime(self, file_path: str, dt: datetime) -> None:
        """Helper to set file modification time."""
        timestamp = dt.timestamp()
        os.utime(file_path, (timestamp, timestamp))

    def format_iso(self, dt: datetime) -> str:
        """Helper to format datetime as ISO 8601 with Z suffix."""
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestTimestampScenarios(TestChangeDetector):
    """Test AC-0.3 timestamp scenarios."""

    def test_unchanged_both_unchanged_since_last_sync(
        self, detector, temp_file, base_time
    ):
        """AC-0.3: T1 <= T0 AND T2 <= T0 → unchanged."""
        # Arrange
        T0 = base_time
        T1 = base_time - timedelta(hours=1)  # Local older
        T2 = base_time - timedelta(hours=2)  # Remote older

        self.set_file_mtime(temp_file, T1)
        local_pages = {"123": temp_file}
        remote_pages = {"123": self.format_iso(T2)}
        last_synced = self.format_iso(T0)

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.unchanged) == 1
        assert result.unchanged[0] == "123"
        assert len(result.to_push) == 0
        assert len(result.to_pull) == 0
        assert len(result.conflicts) == 0

    def test_push_local_changed_remote_unchanged(
        self, detector, temp_file, base_time
    ):
        """AC-0.3: T1 > T0 AND T2 <= T0 → to_push."""
        # Arrange
        T0 = base_time
        T1 = base_time + timedelta(hours=1)  # Local newer
        T2 = base_time - timedelta(hours=1)  # Remote older

        self.set_file_mtime(temp_file, T1)
        local_pages = {"123": temp_file}
        remote_pages = {"123": self.format_iso(T2)}
        last_synced = self.format_iso(T0)

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.to_push) == 1
        assert result.to_push[0] == "123"
        assert len(result.unchanged) == 0
        assert len(result.to_pull) == 0
        assert len(result.conflicts) == 0

    def test_pull_remote_changed_local_unchanged(
        self, detector, temp_file, base_time
    ):
        """AC-0.3: T1 <= T0 AND T2 > T0 → to_pull."""
        # Arrange
        T0 = base_time
        T1 = base_time - timedelta(hours=1)  # Local older
        T2 = base_time + timedelta(hours=1)  # Remote newer

        self.set_file_mtime(temp_file, T1)
        local_pages = {"123": temp_file}
        remote_pages = {"123": self.format_iso(T2)}
        last_synced = self.format_iso(T0)

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.to_pull) == 1
        assert result.to_pull[0] == "123"
        assert len(result.unchanged) == 0
        assert len(result.to_push) == 0
        assert len(result.conflicts) == 0

    def test_conflict_both_changed_since_last_sync(
        self, detector, temp_file, base_time
    ):
        """AC-0.3: T1 > T0 AND T2 > T0 → conflicts."""
        # Arrange
        T0 = base_time
        T1 = base_time + timedelta(hours=1)  # Local newer
        T2 = base_time + timedelta(hours=2)  # Remote newer

        self.set_file_mtime(temp_file, T1)
        local_pages = {"123": temp_file}
        remote_pages = {"123": self.format_iso(T2)}
        last_synced = self.format_iso(T0)

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.conflicts) == 1
        assert result.conflicts[0] == "123"
        assert len(result.unchanged) == 0
        assert len(result.to_push) == 0
        assert len(result.to_pull) == 0


class TestFirstSync(TestChangeDetector):
    """Test first sync scenarios (last_synced is None)."""

    def test_first_sync_all_pages_marked_to_push(
        self, detector, temp_file, base_time
    ):
        """First sync: All local pages should be pushed."""
        # Arrange
        local_pages = {"123": temp_file, "456": temp_file}
        remote_pages = {"123": self.format_iso(base_time)}
        last_synced = None  # First sync

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.to_push) == 2
        assert "123" in result.to_push
        assert "456" in result.to_push
        assert len(result.unchanged) == 0
        assert len(result.to_pull) == 0
        assert len(result.conflicts) == 0


class TestMissingPages(TestChangeDetector):
    """Test scenarios with pages only on one side."""

    def test_page_only_on_remote(self, detector, base_time):
        """Page exists only remotely → to_pull."""
        # Arrange
        local_pages = {}  # No local file
        remote_pages = {"123": self.format_iso(base_time)}
        last_synced = self.format_iso(base_time - timedelta(days=1))

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.to_pull) == 1
        assert result.to_pull[0] == "123"
        assert len(result.to_push) == 0
        assert len(result.conflicts) == 0

    def test_page_only_on_local(self, detector, temp_file, base_time):
        """Page exists only locally → to_push."""
        # Arrange
        local_pages = {"123": temp_file}
        remote_pages = {}  # Not in Confluence
        last_synced = self.format_iso(base_time - timedelta(days=1))

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.to_push) == 1
        assert result.to_push[0] == "123"
        assert len(result.to_pull) == 0
        assert len(result.conflicts) == 0


class TestErrorHandling(TestChangeDetector):
    """Test error scenarios."""

    def test_missing_file_marked_as_conflict(self, detector, base_time):
        """Missing local file should be marked as conflict for safety."""
        # Arrange
        local_pages = {"123": "/nonexistent/file.md"}
        remote_pages = {"123": self.format_iso(base_time)}
        last_synced = self.format_iso(base_time - timedelta(hours=1))

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.conflicts) == 1
        assert result.conflicts[0] == "123"

    def test_invalid_remote_timestamp_marked_as_conflict(
        self, detector, temp_file, base_time
    ):
        """Invalid remote timestamp should be marked as conflict."""
        # Arrange
        local_pages = {"123": temp_file}
        remote_pages = {"123": "invalid-timestamp"}
        last_synced = self.format_iso(base_time)

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.conflicts) == 1
        assert result.conflicts[0] == "123"

    def test_invalid_last_synced_raises_error(self, detector, temp_file):
        """Invalid last_synced timestamp should raise CLIError."""
        # Arrange
        local_pages = {"123": temp_file}
        remote_pages = {"123": "2026-01-30T10:00:00Z"}
        last_synced = "invalid-timestamp"

        # Act & Assert
        with pytest.raises(CLIError) as exc_info:
            detector.detect_changes(local_pages, remote_pages, last_synced)

        assert "Invalid last_synced timestamp" in str(exc_info.value)


class TestMultiplePages(TestChangeDetector):
    """Test scenarios with multiple pages."""

    def test_mixed_scenarios(self, detector, base_time):
        """Multiple pages with different scenarios."""
        # Arrange - Create temp files for each scenario
        with tempfile.TemporaryDirectory() as tmpdir:
            # Page 1: unchanged (T1 <= T0, T2 <= T0)
            file1 = Path(tmpdir) / "page1.md"
            file1.write_text("content1")
            T1_unchanged = base_time - timedelta(hours=2)
            self.set_file_mtime(str(file1), T1_unchanged)

            # Page 2: to_push (T1 > T0, T2 <= T0)
            file2 = Path(tmpdir) / "page2.md"
            file2.write_text("content2")
            T1_push = base_time + timedelta(hours=1)
            self.set_file_mtime(str(file2), T1_push)

            # Page 3: to_pull (T1 <= T0, T2 > T0)
            file3 = Path(tmpdir) / "page3.md"
            file3.write_text("content3")
            T1_pull = base_time - timedelta(hours=1)
            self.set_file_mtime(str(file3), T1_pull)

            # Page 4: conflict (T1 > T0, T2 > T0)
            file4 = Path(tmpdir) / "page4.md"
            file4.write_text("content4")
            T1_conflict = base_time + timedelta(hours=2)
            self.set_file_mtime(str(file4), T1_conflict)

            local_pages = {
                "111": str(file1),
                "222": str(file2),
                "333": str(file3),
                "444": str(file4),
            }

            remote_pages = {
                "111": self.format_iso(base_time - timedelta(hours=3)),  # Unchanged
                "222": self.format_iso(base_time - timedelta(hours=1)),  # Push
                "333": self.format_iso(base_time + timedelta(hours=1)),  # Pull
                "444": self.format_iso(base_time + timedelta(hours=3)),  # Conflict
            }

            last_synced = self.format_iso(base_time)

            # Act
            result = detector.detect_changes(local_pages, remote_pages, last_synced)

            # Assert
            assert len(result.unchanged) == 1
            assert "111" in result.unchanged

            assert len(result.to_push) == 1
            assert "222" in result.to_push

            assert len(result.to_pull) == 1
            assert "333" in result.to_pull

            assert len(result.conflicts) == 1
            assert "444" in result.conflicts

    def test_error_in_one_page_continues_processing(
        self, detector, temp_file, base_time
    ):
        """Error in one page should not stop processing of others."""
        # Arrange
        # Set temp file mtime to be old so it's unchanged
        old_time = base_time - timedelta(hours=2)
        self.set_file_mtime(temp_file, old_time)

        local_pages = {
            "111": temp_file,  # Valid - should be unchanged
            "222": "/nonexistent/file.md",  # Error
            "333": temp_file,  # Valid - should be unchanged
        }
        remote_pages = {
            "111": self.format_iso(base_time - timedelta(hours=2)),  # Unchanged
            "222": self.format_iso(base_time),
            "333": self.format_iso(base_time - timedelta(hours=2)),  # Unchanged
        }
        last_synced = self.format_iso(base_time - timedelta(hours=1))

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        # Page 222 should be in conflicts due to error
        assert "222" in result.conflicts
        # Other pages should be unchanged (both local and remote older than last_synced)
        assert len(result.unchanged) == 2
        assert "111" in result.unchanged
        assert "333" in result.unchanged


class TestTimestampParsing(TestChangeDetector):
    """Test timestamp parsing edge cases."""

    def test_parse_iso_with_z_suffix(self, detector, temp_file, base_time):
        """Parse ISO 8601 timestamp with Z suffix."""
        # Arrange
        local_pages = {"123": temp_file}
        remote_pages = {"123": "2026-01-30T10:00:00Z"}
        last_synced = "2026-01-30T09:00:00Z"

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert - Should not raise error
        assert len(result.to_push) + len(result.to_pull) + len(result.unchanged) + len(result.conflicts) == 1

    def test_parse_iso_with_timezone(self, detector, temp_file, base_time):
        """Parse ISO 8601 timestamp with timezone offset."""
        # Arrange
        local_pages = {"123": temp_file}
        remote_pages = {"123": "2026-01-30T10:00:00+00:00"}
        last_synced = "2026-01-30T09:00:00+00:00"

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert - Should not raise error
        assert len(result.to_push) + len(result.to_pull) + len(result.unchanged) + len(result.conflicts) == 1

    def test_parse_iso_with_milliseconds(self, detector, temp_file, base_time):
        """Parse ISO 8601 timestamp with milliseconds."""
        # Arrange
        local_pages = {"123": temp_file}
        remote_pages = {"123": "2026-01-30T10:00:00.123Z"}
        last_synced = "2026-01-30T09:00:00.456Z"

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert - Should not raise error
        assert len(result.to_push) + len(result.to_pull) + len(result.unchanged) + len(result.conflicts) == 1


class TestEdgeCases(TestChangeDetector):
    """Test edge cases and boundary conditions."""

    def test_empty_local_and_remote(self, detector):
        """Empty local and remote should return empty result."""
        # Arrange
        local_pages = {}
        remote_pages = {}
        last_synced = "2026-01-30T10:00:00Z"

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.unchanged) == 0
        assert len(result.to_push) == 0
        assert len(result.to_pull) == 0
        assert len(result.conflicts) == 0

    def test_exact_timestamp_match(self, detector, temp_file, base_time):
        """Timestamps exactly equal to last_synced should be unchanged."""
        # Arrange
        T0 = base_time
        self.set_file_mtime(temp_file, T0)  # T1 = T0
        local_pages = {"123": temp_file}
        remote_pages = {"123": self.format_iso(T0)}  # T2 = T0
        last_synced = self.format_iso(T0)

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.unchanged) == 1
        assert result.unchanged[0] == "123"

    def test_microsecond_difference_detected(self, detector, temp_file, base_time):
        """Small time differences should still be detected."""
        # Arrange
        T0 = base_time
        T1 = base_time + timedelta(microseconds=1)  # Just slightly newer
        self.set_file_mtime(temp_file, T1)

        local_pages = {"123": temp_file}
        remote_pages = {"123": self.format_iso(base_time - timedelta(hours=1))}
        last_synced = self.format_iso(T0)

        # Act
        result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert len(result.to_push) == 1
        assert result.to_push[0] == "123"


class TestLogging(TestChangeDetector):
    """Test logging behavior."""

    def test_logs_summary(self, detector, temp_file, base_time, caplog):
        """Change detection should log summary of results."""
        # Arrange
        local_pages = {"123": temp_file}
        remote_pages = {"123": self.format_iso(base_time)}
        last_synced = self.format_iso(base_time - timedelta(hours=1))

        # Act
        with caplog.at_level("INFO"):
            result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert "Detecting changes" in caplog.text
        assert "Change detection complete" in caplog.text

    def test_logs_first_sync(self, detector, temp_file, caplog):
        """First sync should log 'no last_synced timestamp'."""
        # Arrange
        local_pages = {"123": temp_file}
        remote_pages = {}
        last_synced = None

        # Act
        with caplog.at_level("INFO"):
            result = detector.detect_changes(local_pages, remote_pages, last_synced)

        # Assert
        assert "First sync" in caplog.text or "no last_synced" in caplog.text


class TestDetectDeletions(TestChangeDetector):
    """Test detect_deletions method."""

    def test_deleted_in_confluence_only(self, detector, base_time):
        """Page deleted in Confluence should be detected."""
        # Arrange
        tracked_pages = {"123": "/path/to/page.md", "456": "/path/to/other.md"}
        local_pages = {"123": "/path/to/page.md", "456": "/path/to/other.md"}
        remote_pages = {"123": self.format_iso(base_time)}  # 456 deleted remotely

        # Act
        result = detector.detect_deletions(local_pages, tracked_pages, remote_pages)

        # Assert
        assert len(result.deleted_in_confluence) == 1
        assert result.deleted_in_confluence[0].page_id == "456"
        assert result.deleted_in_confluence[0].title == "other"
        assert result.deleted_in_confluence[0].direction == "confluence_to_local"
        assert len(result.deleted_locally) == 0

    def test_deleted_locally_only(self, detector, base_time):
        """Page deleted locally should be detected."""
        # Arrange
        tracked_pages = {"123": "/path/to/page.md", "456": "/path/to/other.md"}
        local_pages = {"123": "/path/to/page.md"}  # 456 deleted locally
        remote_pages = {
            "123": self.format_iso(base_time),
            "456": self.format_iso(base_time),
        }

        # Act
        result = detector.detect_deletions(local_pages, tracked_pages, remote_pages)

        # Assert
        assert len(result.deleted_locally) == 1
        assert result.deleted_locally[0].page_id == "456"
        assert result.deleted_locally[0].title == "other"
        assert result.deleted_locally[0].direction == "local_to_confluence"
        assert result.deleted_locally[0].local_path is None  # File no longer exists
        assert len(result.deleted_in_confluence) == 0

    def test_deleted_on_both_sides(self, detector, base_time):
        """Page deleted on both sides should only appear in deleted_in_confluence."""
        # Arrange
        tracked_pages = {"123": "/path/to/page.md", "456": "/path/to/other.md"}
        local_pages = {"123": "/path/to/page.md"}  # 456 deleted locally
        remote_pages = {"123": self.format_iso(base_time)}  # 456 deleted remotely

        # Act
        result = detector.detect_deletions(local_pages, tracked_pages, remote_pages)

        # Assert
        # Should only appear in deleted_in_confluence
        assert len(result.deleted_in_confluence) == 1
        assert result.deleted_in_confluence[0].page_id == "456"
        # Should NOT appear in deleted_locally (handled by Confluence deletion)
        assert len(result.deleted_locally) == 0

    def test_no_deletions(self, detector, base_time):
        """No deletions should return empty lists."""
        # Arrange
        tracked_pages = {"123": "/path/to/page.md", "456": "/path/to/other.md"}
        local_pages = {"123": "/path/to/page.md", "456": "/path/to/other.md"}
        remote_pages = {
            "123": self.format_iso(base_time),
            "456": self.format_iso(base_time),
        }

        # Act
        result = detector.detect_deletions(local_pages, tracked_pages, remote_pages)

        # Assert
        assert len(result.deleted_in_confluence) == 0
        assert len(result.deleted_locally) == 0

    def test_multiple_deletions_mixed(self, detector, base_time):
        """Multiple deletions in both directions."""
        # Arrange
        tracked_pages = {
            "111": "/path/to/page1.md",
            "222": "/path/to/page2.md",
            "333": "/path/to/page3.md",
            "444": "/path/to/page4.md",
        }
        # 222 and 444 deleted locally, 333 deleted in Confluence
        local_pages = {"111": "/path/to/page1.md", "333": "/path/to/page3.md"}
        remote_pages = {
            "111": self.format_iso(base_time),
            "222": self.format_iso(base_time),
            "444": self.format_iso(base_time),
        }

        # Act
        result = detector.detect_deletions(local_pages, tracked_pages, remote_pages)

        # Assert
        # Deleted in Confluence: 333
        assert len(result.deleted_in_confluence) == 1
        assert result.deleted_in_confluence[0].page_id == "333"

        # Deleted locally: 222 and 444 (both still exist remotely)
        assert len(result.deleted_locally) == 2
        deleted_ids = {d.page_id for d in result.deleted_locally}
        assert deleted_ids == {"222", "444"}

    def test_empty_tracked_pages(self, detector, base_time):
        """Empty tracked pages should return no deletions."""
        # Arrange
        tracked_pages = {}
        local_pages = {"123": "/path/to/page.md"}
        remote_pages = {"123": self.format_iso(base_time)}

        # Act
        result = detector.detect_deletions(local_pages, tracked_pages, remote_pages)

        # Assert
        assert len(result.deleted_in_confluence) == 0
        assert len(result.deleted_locally) == 0

    def test_deletion_info_has_correct_fields(self, detector, base_time):
        """DeletionInfo should have all required fields."""
        # Arrange
        tracked_pages = {"123": "/path/to/my_page.md"}
        local_pages = {}  # Deleted locally
        remote_pages = {"123": self.format_iso(base_time)}

        # Act
        result = detector.detect_deletions(local_pages, tracked_pages, remote_pages)

        # Assert
        assert len(result.deleted_locally) == 1
        deletion = result.deleted_locally[0]
        assert deletion.page_id == "123"
        assert deletion.title == "my_page"
        assert deletion.local_path is None
        assert deletion.direction == "local_to_confluence"


class TestDetectMoves(TestChangeDetector):
    """Test detect_moves method."""

    @pytest.fixture
    def mock_build_path(self):
        """Mock the _get_expected_path_from_ancestors method."""
        with patch.object(ChangeDetector, "_get_expected_path_from_ancestors") as mock:
            yield mock

    def test_moved_in_confluence(self, detector, mock_build_path):
        """Page moved in Confluence should be detected."""
        # Arrange
        tracked_pages = {"123": "old/path/page.md"}
        local_pages = {"123": "old/path/page.md"}  # Not moved locally
        pages_with_ancestors = {
            "123": {"title": "My Page", "ancestors": [{"title": "New Parent"}]}
        }

        # Mock the path building to return a different path
        mock_build_path.return_value = "new/path/page.md"

        # Act
        result = detector.detect_moves(
            local_pages, tracked_pages, pages_with_ancestors
        )

        # Assert
        assert len(result.moved_in_confluence) == 1
        assert result.moved_in_confluence[0].page_id == "123"
        assert result.moved_in_confluence[0].title == "My Page"
        assert str(result.moved_in_confluence[0].old_path) == "old/path/page.md"
        assert str(result.moved_in_confluence[0].new_path) == "new/path/page.md"
        assert result.moved_in_confluence[0].direction == "confluence_to_local"
        assert len(result.moved_locally) == 0

    def test_moved_locally(self, detector, mock_build_path):
        """Page moved locally should be detected."""
        # Arrange
        tracked_pages = {"123": "old/path/page.md"}
        local_pages = {"123": "new/local/page.md"}  # Moved locally
        pages_with_ancestors = {
            "123": {"title": "My Page", "ancestors": [{"title": "Parent"}]}
        }

        # Mock the path building to return the tracked path (no Confluence move)
        mock_build_path.return_value = "old/path/page.md"

        # Act
        result = detector.detect_moves(
            local_pages, tracked_pages, pages_with_ancestors
        )

        # Assert
        assert len(result.moved_locally) == 1
        assert result.moved_locally[0].page_id == "123"
        assert result.moved_locally[0].title == "My Page"
        assert str(result.moved_locally[0].old_path) == "old/path/page.md"
        assert str(result.moved_locally[0].new_path) == "new/local/page.md"
        assert result.moved_locally[0].direction == "local_to_confluence"
        assert len(result.moved_in_confluence) == 0

    def test_no_moves(self, detector, mock_build_path):
        """No moves should return empty lists."""
        # Arrange
        tracked_pages = {"123": "same/path/page.md"}
        local_pages = {"123": "same/path/page.md"}
        pages_with_ancestors = {
            "123": {"title": "My Page", "ancestors": [{"title": "Parent"}]}
        }

        # Mock the path building to return the same path
        mock_build_path.return_value = "same/path/page.md"

        # Act
        result = detector.detect_moves(
            local_pages, tracked_pages, pages_with_ancestors
        )

        # Assert
        assert len(result.moved_in_confluence) == 0
        assert len(result.moved_locally) == 0

    def test_deleted_page_skipped_in_move_detection(
        self, detector, mock_build_path
    ):
        """Deleted pages should be skipped in move detection."""
        # Arrange
        tracked_pages = {"123": "old/path/page.md", "456": "other/page.md"}
        local_pages = {"123": "old/path/page.md"}  # 456 deleted locally
        pages_with_ancestors = {
            "123": {"title": "My Page", "ancestors": [{"title": "Parent"}]}
            # 456 not in remote (deleted in Confluence)
        }

        # Mock the path building
        mock_build_path.return_value = "old/path/page.md"

        # Act
        result = detector.detect_moves(
            local_pages, tracked_pages, pages_with_ancestors
        )

        # Assert - 456 should be skipped
        assert len(result.moved_in_confluence) == 0
        assert len(result.moved_locally) == 0

    def test_multiple_moves_mixed(self, detector, mock_build_path):
        """Multiple moves in both directions."""
        # Arrange
        tracked_pages = {
            "111": "old/path1/page1.md",
            "222": "old/path2/page2.md",
            "333": "same/path/page3.md",
        }
        local_pages = {
            "111": "old/path1/page1.md",  # Will be moved in Confluence
            "222": "new/local/page2.md",  # Moved locally
            "333": "same/path/page3.md",  # Not moved
        }
        pages_with_ancestors = {
            "111": {"title": "Page 1", "ancestors": []},
            "222": {"title": "Page 2", "ancestors": []},
            "333": {"title": "Page 3", "ancestors": []},
        }

        # Mock the path building
        def build_path_side_effect(page_id, page_data):
            if page_id == "111":
                return "new/confluence/page1.md"  # Moved in Confluence
            elif page_id == "222":
                return "old/path2/page2.md"  # Not moved in Confluence
            elif page_id == "333":
                return "same/path/page3.md"  # Not moved
            return None

        mock_build_path.side_effect = build_path_side_effect

        # Act
        result = detector.detect_moves(
            local_pages, tracked_pages, pages_with_ancestors
        )

        # Assert
        # Page 111 moved in Confluence
        assert len(result.moved_in_confluence) == 1
        assert result.moved_in_confluence[0].page_id == "111"
        assert str(result.moved_in_confluence[0].old_path) == "old/path1/page1.md"
        assert str(result.moved_in_confluence[0].new_path) == "new/confluence/page1.md"

        # Page 222 moved locally
        assert len(result.moved_locally) == 1
        assert result.moved_locally[0].page_id == "222"
        assert str(result.moved_locally[0].old_path) == "old/path2/page2.md"
        assert str(result.moved_locally[0].new_path) == "new/local/page2.md"

    def test_path_normalization(self, detector, mock_build_path):
        """Paths should be normalized for comparison."""
        # Arrange
        tracked_pages = {"123": "path/to/page.md"}
        local_pages = {"123": "./path/to/page.md"}  # Different format, same path
        pages_with_ancestors = {
            "123": {"title": "My Page", "ancestors": [{"title": "Parent"}]}
        }

        # Mock the path building to return non-normalized path
        mock_build_path.return_value = "./path/to/page.md"

        # Act
        result = detector.detect_moves(
            local_pages, tracked_pages, pages_with_ancestors
        )

        # Assert - Should detect no moves (paths are equivalent)
        assert len(result.moved_in_confluence) == 0
        assert len(result.moved_locally) == 0

    def test_error_in_one_page_continues_processing(
        self, detector, mock_build_path
    ):
        """Error in one page should not stop processing of others."""
        # Arrange
        tracked_pages = {"111": "path1/page1.md", "222": "path2/page2.md"}
        local_pages = {"111": "new/path1/page1.md", "222": "path2/page2.md"}
        pages_with_ancestors = {
            "111": {"title": "Page 1", "ancestors": []},
            "222": {"title": "Page 2", "ancestors": []},
        }

        # Mock the path building to raise error for 222
        def build_path_side_effect(page_id, page_data):
            if page_id == "111":
                return "path1/page1.md"  # No Confluence move
            elif page_id == "222":
                raise Exception("Test error")
            return None

        mock_build_path.side_effect = build_path_side_effect

        # Act
        result = detector.detect_moves(
            local_pages, tracked_pages, pages_with_ancestors
        )

        # Assert - Page 111 should still be processed
        assert len(result.moved_locally) == 1
        assert result.moved_locally[0].page_id == "111"

    def test_move_info_has_correct_fields(self, detector, mock_build_path):
        """MoveInfo should have all required fields."""
        # Arrange
        tracked_pages = {"123": "old/path/page.md"}
        local_pages = {"123": "new/path/page.md"}
        pages_with_ancestors = {
            "123": {"title": "Test Page", "ancestors": [{"title": "Parent"}]}
        }

        # Mock the path building
        mock_build_path.return_value = "old/path/page.md"

        # Act
        result = detector.detect_moves(
            local_pages, tracked_pages, pages_with_ancestors
        )

        # Assert
        assert len(result.moved_locally) == 1
        move = result.moved_locally[0]
        assert move.page_id == "123"
        assert move.title == "Test Page"
        assert str(move.old_path) == "old/path/page.md"
        assert str(move.new_path) == "new/path/page.md"
        assert move.direction == "local_to_confluence"
