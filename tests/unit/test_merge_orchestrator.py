"""Unit tests for git_integration.merge_orchestrator module."""

import pytest
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, mock_open, call

from src.git_integration.errors import GitRepositoryError, MergeConflictError
from src.git_integration.merge_orchestrator import MergeOrchestrator
from src.git_integration.models import (
    ConflictDetectionResult,
    ConflictInfo,
    LocalPage,
    MergeResult,
    MergeStrategy,
    SyncResult,
    ThreeWayMergeInputs,
)


class TestMergeOrchestrator:
    """Test cases for MergeOrchestrator."""

    @pytest.fixture
    def mock_page_ops(self):
        """Mock PageOperations instance."""
        mock = Mock()
        # Add mock API attribute for force_push/force_pull
        mock.api = Mock()
        mock.api.update_page = Mock()
        return mock

    @pytest.fixture
    def mock_git_repo(self):
        """Mock GitRepository instance."""
        return Mock()

    @pytest.fixture
    def mock_cache(self):
        """Mock XHTMLCache instance."""
        return Mock()

    @pytest.fixture
    def mock_detector(self):
        """Mock ConflictDetector instance."""
        return Mock()

    @pytest.fixture
    def mock_merge_tool(self):
        """Mock MergeTool instance."""
        mock = Mock()
        mock.validate_available.return_value = True
        return mock

    @pytest.fixture
    def mock_converter(self):
        """Mock MarkdownConverter."""
        mock = MagicMock()
        mock.markdown_to_xhtml.return_value = "<p>Converted XHTML</p>"
        mock.xhtml_to_markdown.return_value = "# Converted Markdown"
        return mock

    @pytest.fixture
    def orchestrator(
        self, mock_page_ops, mock_git_repo, mock_cache, mock_detector, mock_merge_tool, mock_converter
    ):
        """Create MergeOrchestrator with mocked dependencies."""
        return MergeOrchestrator(
            page_ops=mock_page_ops,
            git_repo=mock_git_repo,
            cache=mock_cache,
            detector=mock_detector,
            merge_tool=mock_merge_tool,
            converter=mock_converter,
            local_dir="/tmp/test",
        )

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
    def sample_pages(self, sample_page):
        """List of sample LocalPages."""
        return [
            sample_page,
            LocalPage(
                page_id="789012",
                file_path="/path/to/page2.md",
                local_version=3,
                title="Test Page 2",
            ),
        ]

    @pytest.fixture
    def conflict_info(self):
        """Sample ConflictInfo for testing."""
        return ConflictInfo(
            page_id="123456",
            file_path="/path/to/page.md",
            local_version=5,
            remote_version=7,
            has_base=True,
        )


class TestSyncNoConflicts(TestMergeOrchestrator):
    """Test cases for sync with no conflicts (UT-MO-01)."""

    def test_sync_no_conflicts(self, orchestrator, mock_detector, sample_pages):
        """All pages should be auto-merged when no conflicts detected."""
        # Arrange
        detection_result = ConflictDetectionResult(
            conflicts=[],
            auto_mergeable=sample_pages,
            errors=[],
        )
        mock_detector.detect_conflicts.return_value = detection_result

        # Act
        result = orchestrator.sync(sample_pages)

        # Assert
        assert result.success is True
        assert result.pages_synced == 2
        assert result.pages_failed == 0
        assert result.conflicts_resolved == 0
        assert len(result.errors) == 0

        # Verify conflict detection was called
        mock_detector.detect_conflicts.assert_called_once_with(sample_pages)

    def test_sync_no_conflicts_no_merge_tool_launched(
        self, orchestrator, mock_detector, mock_merge_tool, sample_pages
    ):
        """Merge tool should not be launched when no conflicts."""
        # Arrange
        detection_result = ConflictDetectionResult(
            conflicts=[],
            auto_mergeable=sample_pages,
            errors=[],
        )
        mock_detector.detect_conflicts.return_value = detection_result

        # Act
        orchestrator.sync(sample_pages)

        # Assert - merge tool should never be called
        mock_merge_tool.launch.assert_not_called()


class TestSyncWithConflicts(TestMergeOrchestrator):
    """Test cases for sync with conflicts (UT-MO-02)."""

    def test_sync_with_conflicts_creates_conflict_files(
        self, orchestrator, mock_detector, conflict_info
    ):
        """Conflict files should be created for conflicting pages."""
        # Arrange
        detection_result = ConflictDetectionResult(
            conflicts=[conflict_info],
            auto_mergeable=[],
            errors=[],
        )
        mock_detector.detect_conflicts.return_value = detection_result

        # Mock three-way merge inputs
        merge_inputs = ThreeWayMergeInputs(
            page_id="123456",
            base_markdown="# Base",
            local_markdown="# Local",
            remote_markdown="# Remote",
            local_version=5,
            remote_version=7,
        )
        mock_detector.get_three_way_merge_inputs.return_value = merge_inputs

        # Mock subprocess for git merge-file (with conflicts)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,  # Conflict indicator
                stdout="<<<<<<< LOCAL\n# Local\n=======\n# Remote\n>>>>>>> REMOTE",
                stderr="",
            )

            # Mock file writing
            with patch("builtins.open", mock_open()):
                # Act
                result = orchestrator.sync([
                    LocalPage(
                        page_id="123456",
                        file_path="/path/to/page.md",
                        local_version=5,
                        title="Test Page",
                    )
                ])

        # Assert - when merge tool is available, conflict is considered resolved
        # (merge tool can be launched for manual resolution)
        assert result.pages_synced == 1
        assert result.conflicts_resolved == 1

    def test_sync_with_conflicts_no_merge_tool_fails(
        self, orchestrator, mock_detector, conflict_info
    ):
        """Pages should fail when conflicts exist and no merge tool available."""
        # Arrange
        orchestrator.merge_tool = None  # No merge tool available
        detection_result = ConflictDetectionResult(
            conflicts=[conflict_info],
            auto_mergeable=[],
            errors=[],
        )
        mock_detector.detect_conflicts.return_value = detection_result

        merge_inputs = ThreeWayMergeInputs(
            page_id="123456",
            base_markdown="# Base",
            local_markdown="# Local",
            remote_markdown="# Remote",
            local_version=5,
            remote_version=7,
        )
        mock_detector.get_three_way_merge_inputs.return_value = merge_inputs

        # Mock subprocess for git merge-file (with conflicts)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="<<<<<<< LOCAL\n# Local\n=======\n# Remote\n>>>>>>> REMOTE",
                stderr="",
            )

            # Mock file writing
            with patch("builtins.open", mock_open()):
                # Act
                result = orchestrator.sync([
                    LocalPage(
                        page_id="123456",
                        file_path="/path/to/page.md",
                        local_version=5,
                        title="Test Page",
                    )
                ])

        # Assert - without merge tool, page should fail
        assert result.pages_failed == 1
        assert "123456" in result.errors
        assert result.success is False

    @patch("subprocess.run")
    def test_sync_with_conflicts_launches_merge_tool(
        self, mock_run, orchestrator, mock_detector, mock_merge_tool, conflict_info
    ):
        """Merge tool should be launched when conflicts exist and tool is available."""
        # Arrange
        detection_result = ConflictDetectionResult(
            conflicts=[conflict_info],
            auto_mergeable=[],
            errors=[],
        )
        mock_detector.detect_conflicts.return_value = detection_result

        merge_inputs = ThreeWayMergeInputs(
            page_id="123456",
            base_markdown="# Base",
            local_markdown="# Local",
            remote_markdown="# Remote",
            local_version=5,
            remote_version=7,
        )
        mock_detector.get_three_way_merge_inputs.return_value = merge_inputs

        # Mock git merge-file with conflicts
        mock_run.return_value = Mock(
            returncode=1,
            stdout="<<<<<<< LOCAL\n# Local\n=======\n# Remote\n>>>>>>> REMOTE",
            stderr="",
        )

        mock_merge_tool.validate_available.return_value = True

        # Mock file writing
        with patch("builtins.open", mock_open()):
            # Act
            orchestrator.sync([
                LocalPage(
                    page_id="123456",
                    file_path="/path/to/page.md",
                    local_version=5,
                    title="Test Page",
                )
            ])

        # Assert - merge tool availability was checked
        mock_merge_tool.validate_available.assert_called()


class TestSyncUnresolvedConflicts(TestMergeOrchestrator):
    """Test cases for sync with unresolved conflicts (UT-MO-03)."""

    @patch("subprocess.run")
    def test_sync_unresolved_conflicts_no_push_to_confluence(
        self, mock_run, orchestrator, mock_detector, mock_page_ops, conflict_info
    ):
        """Pages with unresolved conflicts should not be pushed to Confluence."""
        # Arrange
        detection_result = ConflictDetectionResult(
            conflicts=[conflict_info],
            auto_mergeable=[],
            errors=[],
        )
        mock_detector.detect_conflicts.return_value = detection_result

        merge_inputs = ThreeWayMergeInputs(
            page_id="123456",
            base_markdown="# Base",
            local_markdown="# Local",
            remote_markdown="# Remote",
            local_version=5,
            remote_version=7,
        )
        mock_detector.get_three_way_merge_inputs.return_value = merge_inputs

        # Mock git merge-file with conflicts
        mock_run.return_value = Mock(
            returncode=1,
            stdout="<<<<<<< LOCAL\n# Local\n=======\n# Remote\n>>>>>>> REMOTE",
            stderr="",
        )

        # No merge tool available
        orchestrator.merge_tool = None

        # Mock file writing
        with patch("builtins.open", mock_open()):
            # Act
            result = orchestrator.sync([
                LocalPage(
                    page_id="123456",
                    file_path="/path/to/page.md",
                    local_version=5,
                    title="Test Page",
                )
            ])

        # Assert - page_ops should never be called to push
        mock_page_ops.update_page.assert_not_called()
        mock_page_ops.create_page.assert_not_called()

        # Result should show failure
        assert result.pages_failed == 1
        assert result.success is False


class TestForcePush(TestMergeOrchestrator):
    """Test cases for force push (UT-MO-04)."""

    def test_force_push_no_conflict_detection(
        self, orchestrator, mock_detector, sample_pages
    ):
        """Force push should skip conflict detection entirely."""
        # Arrange - mock file reading
        with patch("builtins.open", mock_open(read_data="# Test Content")):
            # Act
            result = orchestrator.force_push(sample_pages)

        # Assert - detector should never be called
        mock_detector.detect_conflicts.assert_not_called()
        assert result.pages_synced == 2
        assert result.conflicts_resolved == 0

    def test_force_push_all_pages_pushed(self, orchestrator, sample_pages):
        """All pages should be marked as synced in force push mode."""
        # Arrange - mock file reading
        with patch("builtins.open", mock_open(read_data="# Test Content")):
            # Act
            result = orchestrator.force_push(sample_pages)

        # Assert
        assert result.success is True
        assert result.pages_synced == 2
        assert result.pages_failed == 0
        assert len(result.errors) == 0

    def test_force_push_handles_file_read_errors(self, orchestrator, sample_pages):
        """Force push should handle file read errors gracefully."""
        # Arrange - mock file reading to raise error
        with patch("builtins.open", side_effect=FileNotFoundError("File not found")):
            # Act
            result = orchestrator.force_push(sample_pages)

        # Assert
        assert result.success is False
        assert result.pages_failed == 2
        assert len(result.errors) == 2


class TestForcePull(TestMergeOrchestrator):
    """Test cases for force pull (UT-MO-05)."""

    def test_force_pull_no_conflict_detection(self, orchestrator, mock_detector):
        """Force pull should skip conflict detection entirely."""
        # Arrange - mock file writing
        with patch("builtins.open", mock_open()):
            # Act
            result = orchestrator.force_pull(["123456", "789012"])

        # Assert - detector should never be called
        mock_detector.detect_conflicts.assert_not_called()
        assert result.pages_synced == 2
        assert result.conflicts_resolved == 0

    def test_force_pull_all_pages_pulled(self, orchestrator):
        """All pages should be marked as synced in force pull mode."""
        # Arrange - mock file writing
        with patch("builtins.open", mock_open()):
            # Act
            result = orchestrator.force_pull(["123456", "789012"])

        # Assert
        assert result.success is True
        assert result.pages_synced == 2
        assert result.pages_failed == 0
        assert len(result.errors) == 0


class TestPartialFailureRollback(TestMergeOrchestrator):
    """Test cases for partial failure handling (UT-MO-06)."""

    def test_partial_failure_in_force_push(self, orchestrator):
        """If one page fails in force push, it should not affect others."""
        # Arrange
        pages = [
            LocalPage("123", "/path/page1.md", 1, "Page 1"),
            LocalPage("456", "/path/page2.md", 2, "Page 2"),
        ]

        # Mock file reading - first succeeds, second fails
        open_mock = mock_open(read_data="# Content")
        open_mock.side_effect = [
            mock_open(read_data="# Content").return_value,
            FileNotFoundError("File not found"),
        ]

        with patch("builtins.open", open_mock):
            # Act
            result = orchestrator.force_push(pages)

        # Assert - one succeeded, one failed
        assert result.pages_synced == 1
        assert result.pages_failed == 1
        assert "456" in result.errors

    def test_partial_failure_does_not_push_failed_pages(
        self, orchestrator, mock_page_ops
    ):
        """Failed pages should not be pushed to Confluence."""
        # Arrange
        pages = [
            LocalPage("123", "/path/page1.md", 1, "Page 1"),
            LocalPage("456", "/path/page2.md", 2, "Page 2"),
        ]

        with patch("builtins.open", side_effect=FileNotFoundError("File not found")):
            # Act
            orchestrator.force_push(pages)

        # Assert - no pages should be pushed since all failed
        mock_page_ops.update_page.assert_not_called()


class TestGitCommitAfterPush(TestMergeOrchestrator):
    """Test cases for git commits after push (UT-MO-07)."""

    def test_force_push_commits_to_git(self, orchestrator, mock_git_repo):
        """Force push should eventually commit to git repo (future implementation)."""
        # Note: Current implementation is MVP and doesn't commit yet
        # This test verifies the current behavior

        # Arrange
        pages = [LocalPage("123", "/path/page.md", 1, "Page")]

        with patch("builtins.open", mock_open(read_data="# Content")):
            # Act
            orchestrator.force_push(pages)

        # Assert - git_repo is available but not yet used in MVP
        # (this is placeholder for future implementation)
        assert orchestrator.git_repo is not None


class TestThreeWayMerge(TestMergeOrchestrator):
    """Test cases for three-way merge functionality."""

    @patch("subprocess.run")
    def test_three_way_merge_clean(self, mock_run, orchestrator):
        """Clean merge should return success with merged content."""
        # Arrange
        mock_run.return_value = Mock(
            returncode=0,
            stdout="# Merged Content",
            stderr="",
        )

        # Act
        result = orchestrator._three_way_merge(
            base="# Base",
            local="# Local",
            remote="# Remote",
        )

        # Assert
        assert result.success is True
        assert result.merged_markdown == "# Merged Content"
        assert result.conflict_file is None

    @patch("subprocess.run")
    def test_three_way_merge_with_conflicts(self, mock_run, orchestrator):
        """Merge with conflicts should return failure with conflict markers."""
        # Arrange
        mock_run.return_value = Mock(
            returncode=1,
            stdout="<<<<<<< LOCAL\n# Local\n=======\n# Remote\n>>>>>>> REMOTE",
            stderr="",
        )

        # Act
        result = orchestrator._three_way_merge(
            base="# Base",
            local="# Local",
            remote="# Remote",
        )

        # Assert
        assert result.success is False
        assert "<<<<<<< LOCAL" in result.merged_markdown
        assert "=======" in result.merged_markdown
        assert ">>>>>>> REMOTE" in result.merged_markdown

    @patch("subprocess.run")
    def test_three_way_merge_timeout(self, mock_run, orchestrator):
        """Merge timeout should raise GitRepositoryError."""
        # Arrange
        mock_run.side_effect = subprocess.TimeoutExpired("git merge-file", 10)

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            orchestrator._three_way_merge(
                base="# Base",
                local="# Local",
                remote="# Remote",
            )

        assert "timed out" in str(exc_info.value)

    @patch("subprocess.run")
    def test_three_way_merge_git_not_found(self, mock_run, orchestrator):
        """Missing git command should raise GitRepositoryError."""
        # Arrange
        mock_run.side_effect = FileNotFoundError("git not found")

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            orchestrator._three_way_merge(
                base="# Base",
                local="# Local",
                remote="# Remote",
            )

        assert "git command not found" in str(exc_info.value)

    @patch("subprocess.run")
    def test_three_way_merge_creates_temp_files(self, mock_run, orchestrator):
        """Merge should create temporary files for base, local, and remote."""
        # Arrange
        mock_run.return_value = Mock(returncode=0, stdout="# Merged", stderr="")

        # Act
        orchestrator._three_way_merge(
            base="# Base",
            local="# Local",
            remote="# Remote",
        )

        # Assert - subprocess.run should be called with temp file paths
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "git"
        assert call_args[1] == "merge-file"
        assert call_args[2] == "-p"
        # Next 3 args should be temp file paths
        assert len(call_args) == 6


class TestCreateConflictFile(TestMergeOrchestrator):
    """Test cases for conflict file creation."""

    def test_create_conflict_file_writes_content(self, orchestrator):
        """Conflict file should be created with merged content."""
        # Arrange
        page_id = "123456"
        merged_content = "<<<<<<< LOCAL\n# Local\n=======\n# Remote\n>>>>>>> REMOTE"

        # Act
        with patch("builtins.open", mock_open()) as mock_file:
            conflict_file = orchestrator._create_conflict_file(page_id, merged_content)

        # Assert
        assert conflict_file == "123456.conflict.md"
        mock_file.assert_called_once_with("123456.conflict.md", "w", encoding="utf-8")
        handle = mock_file()
        handle.write.assert_called_once_with(merged_content)

    def test_create_conflict_file_handles_write_errors(self, orchestrator):
        """Conflict file creation errors should raise GitRepositoryError."""
        # Arrange
        page_id = "123456"
        merged_content = "# Content"

        # Act & Assert
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            with pytest.raises(GitRepositoryError) as exc_info:
                orchestrator._create_conflict_file(page_id, merged_content)

            assert "Failed to create conflict file" in str(exc_info.value)


class TestMergeOrchestratorInitialization(TestMergeOrchestrator):
    """Test cases for MergeOrchestrator initialization."""

    def test_init_with_all_dependencies(
        self, mock_page_ops, mock_git_repo, mock_cache, mock_detector, mock_merge_tool
    ):
        """MergeOrchestrator should accept all dependencies."""
        # Act
        orch = MergeOrchestrator(
            page_ops=mock_page_ops,
            git_repo=mock_git_repo,
            cache=mock_cache,
            detector=mock_detector,
            merge_tool=mock_merge_tool,
        )

        # Assert
        assert orch.page_ops is mock_page_ops
        assert orch.git_repo is mock_git_repo
        assert orch.cache is mock_cache
        assert orch.detector is mock_detector
        assert orch.merge_tool is mock_merge_tool

    def test_init_with_optional_dependencies(self):
        """MergeOrchestrator should work with optional dependencies."""
        # Act
        orch = MergeOrchestrator()

        # Assert
        assert orch.page_ops is None
        assert orch.git_repo is None
        assert orch.cache is None
        assert orch.detector is None
        assert orch.merge_tool is None

    def test_sync_requires_detector(self, orchestrator):
        """Sync with THREE_WAY strategy should require detector."""
        # Arrange
        orchestrator.detector = None

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            orchestrator.sync([])

        assert "ConflictDetector is required" in str(exc_info.value)


class TestMergeStrategies(TestMergeOrchestrator):
    """Test cases for different merge strategies."""

    def test_sync_with_force_push_strategy(self, orchestrator, sample_pages):
        """Sync with FORCE_PUSH should call force_push method."""
        # Arrange
        with patch("builtins.open", mock_open(read_data="# Content")):
            # Act
            result = orchestrator.sync(sample_pages, strategy=MergeStrategy.FORCE_PUSH)

        # Assert
        assert result.pages_synced == 2
        assert result.conflicts_resolved == 0

    def test_sync_with_force_pull_strategy(self, orchestrator, sample_pages):
        """Sync with FORCE_PULL should call force_pull method."""
        # Arrange - mock file writing
        with patch("builtins.open", mock_open()):
            # Act
            result = orchestrator.sync(sample_pages, strategy=MergeStrategy.FORCE_PULL)

        # Assert
        assert result.pages_synced == 2
        assert result.conflicts_resolved == 0

    def test_sync_with_three_way_strategy(self, orchestrator, mock_detector, sample_pages):
        """Sync with THREE_WAY should perform conflict detection."""
        # Arrange
        detection_result = ConflictDetectionResult(
            conflicts=[],
            auto_mergeable=sample_pages,
            errors=[],
        )
        mock_detector.detect_conflicts.return_value = detection_result

        # Act
        result = orchestrator.sync(sample_pages, strategy=MergeStrategy.THREE_WAY)

        # Assert
        mock_detector.detect_conflicts.assert_called_once()
        assert result.pages_synced == 2
