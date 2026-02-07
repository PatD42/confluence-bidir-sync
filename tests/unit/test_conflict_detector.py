"""Unit tests for git_integration.conflict_detector module."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

from src.confluence_client.errors import APIAccessError, PageNotFoundError
from src.git_integration.conflict_detector import ConflictDetector
from src.git_integration.errors import GitRepositoryError
from src.git_integration.models import (
    ConflictInfo,
    LocalPage,
    ThreeWayMergeInputs,
)


class TestConflictDetector:
    """Test cases for ConflictDetector."""

    @pytest.fixture
    def mock_page_ops(self):
        """Mock PageOperations instance."""
        return Mock()

    @pytest.fixture
    def mock_git_repo(self):
        """Mock GitRepository instance."""
        return Mock()

    @pytest.fixture
    def mock_cache(self):
        """Mock XHTMLCache instance."""
        return Mock()

    @pytest.fixture
    def detector(self, mock_page_ops, mock_git_repo, mock_cache):
        """Create ConflictDetector with mocked dependencies."""
        return ConflictDetector(mock_page_ops, mock_git_repo, mock_cache)

    @pytest.fixture
    def sample_page(self):
        """Sample LocalPage for testing."""
        return LocalPage(
            page_id="123456",
            file_path="/path/to/page.md",
            local_version=5,
            title="Test Page",
        )

    @pytest.fixture
    def mock_snapshot(self):
        """Mock PageSnapshot."""
        snapshot = Mock()
        snapshot.version = 5
        snapshot.markdown = "# Remote Content"
        snapshot.xhtml = "<h1>Remote Content</h1>"
        snapshot.last_modified = datetime(2026, 1, 30, 12, 0, 0)
        return snapshot


class TestDetectConflicts(TestConflictDetector):
    """Test cases for detect_conflicts method."""

    def test_no_conflicts(self, detector, mock_page_ops, sample_page, mock_snapshot):
        """All pages should be in auto_mergeable when versions match."""
        # Arrange
        mock_page_ops.get_page_snapshot.return_value = mock_snapshot
        local_pages = [sample_page]

        # Act
        result = detector.detect_conflicts(local_pages)

        # Assert
        assert len(result.auto_mergeable) == 1
        assert len(result.conflicts) == 0
        assert len(result.errors) == 0
        assert result.auto_mergeable[0].page_id == "123456"

    def test_version_mismatch_conflict(
        self, detector, mock_page_ops, mock_git_repo, sample_page, mock_snapshot
    ):
        """Conflict should be detected when local version != remote version."""
        # Arrange
        mock_snapshot.version = 7  # Different from sample_page.local_version=5
        mock_page_ops.get_page_snapshot.return_value = mock_snapshot
        mock_git_repo.get_version.return_value = "# Base Content"
        local_pages = [sample_page]

        # Act
        result = detector.detect_conflicts(local_pages)

        # Assert
        assert len(result.conflicts) == 1
        assert len(result.auto_mergeable) == 0
        conflict = result.conflicts[0]
        assert conflict.page_id == "123456"
        assert conflict.local_version == 5
        assert conflict.remote_version == 7

    def test_version_match_no_conflict(
        self, detector, mock_page_ops, sample_page, mock_snapshot
    ):
        """No conflict should be detected when local version == remote version."""
        # Arrange
        mock_snapshot.version = 5  # Same as sample_page.local_version
        mock_page_ops.get_page_snapshot.return_value = mock_snapshot
        local_pages = [sample_page]

        # Act
        result = detector.detect_conflicts(local_pages)

        # Assert
        assert len(result.auto_mergeable) == 1
        assert len(result.conflicts) == 0

    def test_base_version_found(
        self, detector, mock_page_ops, mock_git_repo, sample_page, mock_snapshot
    ):
        """ConflictInfo.has_base should be True when base version exists in git."""
        # Arrange
        mock_snapshot.version = 7  # Conflict: different from local_version=5
        mock_page_ops.get_page_snapshot.return_value = mock_snapshot
        mock_git_repo.get_version.return_value = "# Base Content"  # Base exists
        local_pages = [sample_page]

        # Act
        result = detector.detect_conflicts(local_pages)

        # Assert
        assert len(result.conflicts) == 1
        assert result.conflicts[0].has_base is True

    def test_base_version_missing(
        self, detector, mock_page_ops, mock_git_repo, sample_page, mock_snapshot
    ):
        """ConflictInfo.has_base should be False when base version not in git."""
        # Arrange
        mock_snapshot.version = 7  # Conflict: different from local_version=5
        mock_page_ops.get_page_snapshot.return_value = mock_snapshot
        mock_git_repo.get_version.return_value = None  # Base doesn't exist
        local_pages = [sample_page]

        # Act
        result = detector.detect_conflicts(local_pages)

        # Assert
        assert len(result.conflicts) == 1
        assert result.conflicts[0].has_base is False

    def test_parallel_detection(
        self, detector, mock_page_ops, mock_git_repo, mock_snapshot
    ):
        """All pages should be checked in parallel and results consistent."""
        # Arrange
        pages = [
            LocalPage("111", "/path/1.md", 5, "Page 1"),
            LocalPage("222", "/path/2.md", 6, "Page 2"),
            LocalPage("333", "/path/3.md", 7, "Page 3"),
            LocalPage("444", "/path/4.md", 8, "Page 4"),
        ]

        # Mock different scenarios for each page
        def get_snapshot_side_effect(page_id):
            snapshot = Mock()
            if page_id == "111":
                snapshot.version = 5  # No conflict
            elif page_id == "222":
                snapshot.version = 10  # Conflict
            elif page_id == "333":
                snapshot.version = 7  # No conflict
            elif page_id == "444":
                snapshot.version = 12  # Conflict
            return snapshot

        mock_page_ops.get_page_snapshot.side_effect = get_snapshot_side_effect
        mock_git_repo.get_version.return_value = "# Base"

        # Act
        result = detector.detect_conflicts(pages)

        # Assert
        assert len(result.auto_mergeable) == 2  # Pages 111 and 333
        assert len(result.conflicts) == 2  # Pages 222 and 444
        assert len(result.errors) == 0

        # Verify all pages were checked
        assert mock_page_ops.get_page_snapshot.call_count == 4

        # Verify conflict details
        conflict_ids = {c.page_id for c in result.conflicts}
        assert conflict_ids == {"222", "444"}

    def test_api_error_in_errors_list(
        self, detector, mock_page_ops, mock_git_repo, sample_page
    ):
        """API failures should be added to errors list, not crash."""
        # Arrange
        mock_page_ops.get_page_snapshot.side_effect = APIAccessError(
            "API connection failed"
        )
        local_pages = [sample_page]

        # Act
        result = detector.detect_conflicts(local_pages)

        # Assert
        assert len(result.errors) == 1
        assert len(result.conflicts) == 0
        assert len(result.auto_mergeable) == 0
        assert result.errors[0][0] == "123456"
        assert "API connection failed" in result.errors[0][1]

    def test_page_not_found_in_errors_list(
        self, detector, mock_page_ops, sample_page
    ):
        """PageNotFoundError should be added to errors list."""
        # Arrange
        mock_page_ops.get_page_snapshot.side_effect = PageNotFoundError("123456")
        local_pages = [sample_page]

        # Act
        result = detector.detect_conflicts(local_pages)

        # Assert
        assert len(result.errors) == 1
        assert result.errors[0][0] == "123456"

    def test_multiple_pages_mixed_results(
        self, detector, mock_page_ops, mock_git_repo
    ):
        """Mixed results with conflicts, auto-mergeable, and errors."""
        # Arrange
        pages = [
            LocalPage("111", "/path/1.md", 5, "No Conflict"),
            LocalPage("222", "/path/2.md", 6, "Has Conflict"),
            LocalPage("333", "/path/3.md", 7, "API Error"),
        ]

        def get_snapshot_side_effect(page_id):
            if page_id == "111":
                snapshot = Mock()
                snapshot.version = 5  # No conflict
                return snapshot
            elif page_id == "222":
                snapshot = Mock()
                snapshot.version = 10  # Conflict
                return snapshot
            elif page_id == "333":
                raise APIAccessError("Connection timeout")

        mock_page_ops.get_page_snapshot.side_effect = get_snapshot_side_effect
        mock_git_repo.get_version.return_value = "# Base"

        # Act
        result = detector.detect_conflicts(pages)

        # Assert
        assert len(result.auto_mergeable) == 1
        assert len(result.conflicts) == 1
        assert len(result.errors) == 1
        assert result.auto_mergeable[0].page_id == "111"
        assert result.conflicts[0].page_id == "222"
        assert result.errors[0][0] == "333"


class TestGetThreeWayMergeInputs(TestConflictDetector):
    """Test cases for get_three_way_merge_inputs method."""

    def test_successful_fetch_all_versions(
        self, detector, mock_page_ops, mock_git_repo, mock_cache, mock_snapshot
    ):
        """Should fetch base, local, and remote markdown successfully."""
        # Arrange
        mock_git_repo.get_version.return_value = "# Local/Base Content"
        mock_snapshot.markdown = "# Remote Content"
        mock_snapshot.xhtml = "<h1>Remote Content</h1>"
        mock_snapshot.version = 7
        mock_snapshot.last_modified = datetime(2026, 1, 30, 12, 0, 0)
        mock_page_ops.get_page_snapshot.return_value = mock_snapshot

        # Act
        result = detector.get_three_way_merge_inputs(
            page_id="123456", local_version=5, remote_version=7
        )

        # Assert
        assert isinstance(result, ThreeWayMergeInputs)
        assert result.page_id == "123456"
        assert result.base_markdown == "# Local/Base Content"
        assert result.local_markdown == "# Local/Base Content"
        assert result.remote_markdown == "# Remote Content"
        assert result.local_version == 5
        assert result.remote_version == 7

    def test_caches_remote_xhtml(
        self, detector, mock_page_ops, mock_git_repo, mock_cache, mock_snapshot
    ):
        """Should cache the remote XHTML after fetching."""
        # Arrange
        mock_git_repo.get_version.return_value = "# Content"
        mock_snapshot.version = 7
        mock_snapshot.xhtml = "<h1>Remote Content</h1>"
        mock_snapshot.last_modified = datetime(2026, 1, 30, 12, 0, 0)
        mock_page_ops.get_page_snapshot.return_value = mock_snapshot

        # Act
        detector.get_three_way_merge_inputs(
            page_id="123456", local_version=5, remote_version=7
        )

        # Assert
        mock_cache.put.assert_called_once_with(
            page_id="123456",
            version=7,
            xhtml="<h1>Remote Content</h1>",
            last_modified=datetime(2026, 1, 30, 12, 0, 0),
        )

    def test_base_version_not_found_raises_error(
        self, detector, mock_page_ops, mock_git_repo
    ):
        """Should raise GitRepositoryError when base version not in git."""
        # Arrange
        mock_git_repo.get_version.return_value = None  # Base not found
        mock_git_repo.repo_path = "/tmp/repo"

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            detector.get_three_way_merge_inputs(
                page_id="123456", local_version=5, remote_version=7
            )

        assert "Base version 5 not found" in str(exc_info.value)
        assert exc_info.value.repo_path == "/tmp/repo"

    def test_remote_page_not_found_raises_error(
        self, detector, mock_page_ops, mock_git_repo
    ):
        """Should raise PageNotFoundError when remote page doesn't exist."""
        # Arrange
        mock_git_repo.get_version.return_value = "# Base Content"
        mock_page_ops.get_page_snapshot.side_effect = PageNotFoundError("123456")

        # Act & Assert
        with pytest.raises(PageNotFoundError) as exc_info:
            detector.get_three_way_merge_inputs(
                page_id="123456", local_version=5, remote_version=7
            )

        assert "123456" in str(exc_info.value)

    def test_api_access_error_propagates(
        self, detector, mock_page_ops, mock_git_repo
    ):
        """Should raise APIAccessError when Confluence API fails."""
        # Arrange
        mock_git_repo.get_version.return_value = "# Base Content"
        mock_page_ops.get_page_snapshot.side_effect = APIAccessError(
            "Connection timeout"
        )

        # Act & Assert
        with pytest.raises(APIAccessError) as exc_info:
            detector.get_three_way_merge_inputs(
                page_id="123456", local_version=5, remote_version=7
            )

        assert "Failed to fetch remote version" in str(exc_info.value)

    def test_cache_failure_does_not_crash(
        self, detector, mock_page_ops, mock_git_repo, mock_cache, mock_snapshot
    ):
        """Should continue successfully even if cache.put fails."""
        # Arrange
        mock_git_repo.get_version.return_value = "# Content"
        mock_snapshot.markdown = "# Remote"
        mock_page_ops.get_page_snapshot.return_value = mock_snapshot
        mock_cache.put.side_effect = Exception("Disk full")

        # Act - should not raise
        result = detector.get_three_way_merge_inputs(
            page_id="123456", local_version=5, remote_version=7
        )

        # Assert
        assert result.remote_markdown == "# Remote"

    def test_git_error_checking_base_returns_false(
        self, detector, mock_git_repo, mock_page_ops, mock_snapshot
    ):
        """GitRepositoryError when checking base should result in has_base=False."""
        # Arrange
        mock_snapshot.version = 7  # Create conflict
        mock_page_ops.get_page_snapshot.return_value = mock_snapshot
        mock_git_repo.get_version.side_effect = GitRepositoryError(
            repo_path="/tmp/repo", message="Git command failed"
        )

        page = LocalPage("123456", "/path/to/page.md", 5, "Test")

        # Act
        result = detector.detect_conflicts([page])

        # Assert
        assert len(result.conflicts) == 1
        assert result.conflicts[0].has_base is False


class TestCheckBaseExists(TestConflictDetector):
    """Test cases for _check_base_exists helper method."""

    def test_base_exists_returns_true(self, detector, mock_git_repo):
        """Should return True when base version exists in git."""
        # Arrange
        mock_git_repo.get_version.return_value = "# Base Content"

        # Act
        result = detector._check_base_exists("123456", 5)

        # Assert
        assert result is True
        mock_git_repo.get_version.assert_called_once_with("123456", 5)

    def test_base_not_found_returns_false(self, detector, mock_git_repo):
        """Should return False when base version not found."""
        # Arrange
        mock_git_repo.get_version.return_value = None

        # Act
        result = detector._check_base_exists("123456", 5)

        # Assert
        assert result is False

    def test_git_error_returns_false(self, detector, mock_git_repo):
        """Should return False when GitRepositoryError occurs."""
        # Arrange
        mock_git_repo.get_version.side_effect = GitRepositoryError(
            repo_path="/tmp/repo", message="Git failed"
        )

        # Act
        result = detector._check_base_exists("123456", 5)

        # Assert
        assert result is False
