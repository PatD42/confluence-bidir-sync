"""Integration tests for deletion flow.

This module tests the end-to-end deletion flow from change detection
through deletion execution. Tests verify:
- detect_deletions correctly identifies deleted pages
- DeletionHandler processes deletions in both directions
- delete_page API call successfully deletes Confluence pages
- Integration between ChangeDetector, DeletionHandler, and PageOperations
- File system operations for local file deletion
- API operations for Confluence page deletion

Requirements:
- Temporary test directories (provided by fixtures)
- Mock Confluence API for testing (no actual API calls)
- Real filesystem operations for local file deletion
"""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from src.cli.change_detector import ChangeDetector
from src.cli.deletion_handler import DeletionHandler
from src.cli.models import DeletionInfo, DeletionResult
from src.page_operations.page_operations import PageOperations


@pytest.mark.integration
class TestDeletionFlow:
    """Integration tests for deletion detection and execution flow."""

    @pytest.fixture(scope="function")
    def change_detector(self) -> ChangeDetector:
        """Create a ChangeDetector instance for testing.

        Returns:
            ChangeDetector instance
        """
        return ChangeDetector()

    @pytest.fixture(scope="function")
    def mock_page_operations(self) -> Mock:
        """Create a mock PageOperations instance.

        Returns:
            Mock PageOperations with delete_page method
        """
        mock = Mock(spec=PageOperations)
        mock.delete_page = Mock()
        return mock

    @pytest.fixture(scope="function")
    def deletion_handler(self, mock_page_operations: Mock) -> DeletionHandler:
        """Create a DeletionHandler instance with mock dependencies.

        Args:
            mock_page_operations: Mock PageOperations fixture

        Returns:
            DeletionHandler instance
        """
        return DeletionHandler(
            page_operations=mock_page_operations,
            file_mapper=None
        )

    @pytest.fixture(scope="function")
    def sample_tracked_pages(self, temp_test_dir: Path) -> dict:
        """Create sample tracked pages for testing.

        Args:
            temp_test_dir: Temporary test directory fixture

        Returns:
            Dict mapping page_id to local file path
        """
        return {
            "123": str(temp_test_dir / "page1.md"),
            "456": str(temp_test_dir / "page2.md"),
            "789": str(temp_test_dir / "page3.md"),
        }

    def test_detect_deletions_confluence_only(
        self,
        change_detector: ChangeDetector,
        sample_tracked_pages: dict
    ):
        """Test detecting pages deleted in Confluence.

        Verifies:
        - Pages in tracked_pages but not in remote_pages are detected
        - Deletion direction is set correctly
        - Local path is preserved in deletion info

        Args:
            change_detector: ChangeDetector fixture
            sample_tracked_pages: Sample tracked pages fixture
        """
        # All pages exist locally, but page 456 was deleted in Confluence
        local_pages = {
            "123": sample_tracked_pages["123"],
            "456": sample_tracked_pages["456"],
            "789": sample_tracked_pages["789"],
        }

        # Page 456 missing from remote (deleted in Confluence)
        remote_pages = {
            "123": "2024-01-15T10:30:00Z",
            "789": "2024-01-15T10:30:00Z",
        }

        # Detect deletions
        result = change_detector.detect_deletions(
            local_pages=local_pages,
            tracked_pages=sample_tracked_pages,
            remote_pages=remote_pages
        )

        # Verify results
        assert len(result.deleted_in_confluence) == 1, \
            "Should detect 1 deletion in Confluence"
        assert len(result.deleted_locally) == 0, \
            "Should detect 0 local deletions"

        deletion = result.deleted_in_confluence[0]
        assert deletion.page_id == "456"
        assert deletion.direction == "confluence_to_local"
        assert deletion.local_path == Path(sample_tracked_pages["456"])

    def test_detect_deletions_local_only(
        self,
        change_detector: ChangeDetector,
        sample_tracked_pages: dict
    ):
        """Test detecting pages deleted locally.

        Verifies:
        - Pages in tracked_pages but not in local_pages are detected
        - Only pages still in remote are marked as local deletions
        - Deletion direction is set correctly

        Args:
            change_detector: ChangeDetector fixture
            sample_tracked_pages: Sample tracked pages fixture
        """
        # Page 456 deleted locally (not in local_pages)
        local_pages = {
            "123": sample_tracked_pages["123"],
            "789": sample_tracked_pages["789"],
        }

        # All pages still exist remotely
        remote_pages = {
            "123": "2024-01-15T10:30:00Z",
            "456": "2024-01-15T10:30:00Z",
            "789": "2024-01-15T10:30:00Z",
        }

        # Detect deletions
        result = change_detector.detect_deletions(
            local_pages=local_pages,
            tracked_pages=sample_tracked_pages,
            remote_pages=remote_pages
        )

        # Verify results
        assert len(result.deleted_in_confluence) == 0, \
            "Should detect 0 deletions in Confluence"
        assert len(result.deleted_locally) == 1, \
            "Should detect 1 local deletion"

        deletion = result.deleted_locally[0]
        assert deletion.page_id == "456"
        assert deletion.direction == "local_to_confluence"
        assert deletion.local_path is None  # File no longer exists

    def test_detect_deletions_both_sides(
        self,
        change_detector: ChangeDetector,
        sample_tracked_pages: dict
    ):
        """Test detecting deletions on both sides.

        Verifies:
        - Multiple deletions detected correctly
        - Each deletion categorized by direction
        - Pages deleted on both sides handled correctly

        Args:
            change_detector: ChangeDetector fixture
            sample_tracked_pages: Sample tracked pages fixture
        """
        # Page 456 deleted locally, page 789 exists locally
        local_pages = {
            "123": sample_tracked_pages["123"],
            "789": sample_tracked_pages["789"],
        }

        # Page 789 deleted in Confluence
        remote_pages = {
            "123": "2024-01-15T10:30:00Z",
            "456": "2024-01-15T10:30:00Z",
        }

        # Detect deletions
        result = change_detector.detect_deletions(
            local_pages=local_pages,
            tracked_pages=sample_tracked_pages,
            remote_pages=remote_pages
        )

        # Verify results
        assert len(result.deleted_in_confluence) == 1, \
            "Should detect 1 deletion in Confluence"
        assert len(result.deleted_locally) == 1, \
            "Should detect 1 local deletion"

        # Check Confluence deletion
        conf_deletion = result.deleted_in_confluence[0]
        assert conf_deletion.page_id == "789"
        assert conf_deletion.direction == "confluence_to_local"

        # Check local deletion
        local_deletion = result.deleted_locally[0]
        assert local_deletion.page_id == "456"
        assert local_deletion.direction == "local_to_confluence"

    def test_detect_deletions_deleted_both_sides(
        self,
        change_detector: ChangeDetector,
        sample_tracked_pages: dict
    ):
        """Test page deleted on both sides.

        Verifies:
        - Page deleted on both sides only appears in deleted_in_confluence
        - No duplicate entries in deleted_locally

        Args:
            change_detector: ChangeDetector fixture
            sample_tracked_pages: Sample tracked pages fixture
        """
        # Page 456 deleted locally
        local_pages = {
            "123": sample_tracked_pages["123"],
            "789": sample_tracked_pages["789"],
        }

        # Page 456 also deleted in Confluence
        remote_pages = {
            "123": "2024-01-15T10:30:00Z",
            "789": "2024-01-15T10:30:00Z",
        }

        # Detect deletions
        result = change_detector.detect_deletions(
            local_pages=local_pages,
            tracked_pages=sample_tracked_pages,
            remote_pages=remote_pages
        )

        # Verify results - page 456 should only appear in deleted_in_confluence
        assert len(result.deleted_in_confluence) == 1
        assert len(result.deleted_locally) == 0

        deletion = result.deleted_in_confluence[0]
        assert deletion.page_id == "456"

    def test_delete_local_files_integration(
        self,
        deletion_handler: DeletionHandler,
        temp_test_dir: Path
    ):
        """Test deleting local files end-to-end.

        Verifies:
        - Files are actually deleted from filesystem
        - Deleted page IDs are returned
        - Multiple files handled correctly

        Args:
            deletion_handler: DeletionHandler fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create test files
        file1 = temp_test_dir / "page1.md"
        file2 = temp_test_dir / "page2.md"
        file1.write_text("# Page 1\n\nContent", encoding='utf-8')
        file2.write_text("# Page 2\n\nContent", encoding='utf-8')

        # Verify files exist
        assert file1.exists()
        assert file2.exists()

        # Create deletion infos
        deletions = [
            DeletionInfo(
                page_id="123",
                title="Page 1",
                local_path=file1,
                direction="confluence_to_local"
            ),
            DeletionInfo(
                page_id="456",
                title="Page 2",
                local_path=file2,
                direction="confluence_to_local"
            ),
        ]

        # Execute deletions
        result = deletion_handler.delete_local_files(deletions, dryrun=False)

        # Verify results
        assert len(result) == 2
        assert "123" in result
        assert "456" in result
        assert not file1.exists(), "File 1 should be deleted"
        assert not file2.exists(), "File 2 should be deleted"

    def test_delete_local_files_dryrun(
        self,
        deletion_handler: DeletionHandler,
        temp_test_dir: Path
    ):
        """Test dry run mode for local file deletion.

        Verifies:
        - Files are NOT deleted in dry run mode
        - Empty result returned
        - Files still exist after dry run

        Args:
            deletion_handler: DeletionHandler fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create test file
        test_file = temp_test_dir / "page.md"
        test_file.write_text("# Page\n\nContent", encoding='utf-8')

        # Verify file exists
        assert test_file.exists()

        # Create deletion info
        deletions = [
            DeletionInfo(
                page_id="123",
                title="Page",
                local_path=test_file,
                direction="confluence_to_local"
            ),
        ]

        # Execute dry run
        result = deletion_handler.delete_local_files(deletions, dryrun=True)

        # Verify results
        assert len(result) == 0, "Dry run should return empty result"
        assert test_file.exists(), "File should still exist after dry run"

    def test_delete_confluence_pages_integration(
        self,
        deletion_handler: DeletionHandler,
        mock_page_operations: Mock
    ):
        """Test deleting Confluence pages via API.

        Verifies:
        - delete_page API called for each deletion
        - Correct page IDs passed to API
        - Deleted page IDs returned

        Args:
            deletion_handler: DeletionHandler fixture
            mock_page_operations: Mock PageOperations fixture
        """
        # Create deletion infos
        deletions = [
            DeletionInfo(
                page_id="123",
                title="Page 1",
                local_path=None,
                direction="local_to_confluence"
            ),
            DeletionInfo(
                page_id="456",
                title="Page 2",
                local_path=None,
                direction="local_to_confluence"
            ),
        ]

        # Execute deletions
        result = deletion_handler.delete_confluence_pages(deletions, dryrun=False)

        # Verify results
        assert len(result) == 2
        assert "123" in result
        assert "456" in result

        # Verify API calls
        assert mock_page_operations.delete_page.call_count == 2
        mock_page_operations.delete_page.assert_any_call("123")
        mock_page_operations.delete_page.assert_any_call("456")

    def test_delete_confluence_pages_dryrun(
        self,
        deletion_handler: DeletionHandler,
        mock_page_operations: Mock
    ):
        """Test dry run mode for Confluence page deletion.

        Verifies:
        - API is NOT called in dry run mode
        - Empty result returned
        - No pages deleted

        Args:
            deletion_handler: DeletionHandler fixture
            mock_page_operations: Mock PageOperations fixture
        """
        # Create deletion info
        deletions = [
            DeletionInfo(
                page_id="123",
                title="Page",
                local_path=None,
                direction="local_to_confluence"
            ),
        ]

        # Execute dry run
        result = deletion_handler.delete_confluence_pages(deletions, dryrun=True)

        # Verify results
        assert len(result) == 0, "Dry run should return empty result"
        mock_page_operations.delete_page.assert_not_called()

    def test_full_deletion_flow_confluence_to_local(
        self,
        change_detector: ChangeDetector,
        deletion_handler: DeletionHandler,
        temp_test_dir: Path
    ):
        """Test complete deletion flow: detect + delete (Confluence → local).

        Verifies:
        - Full integration from detection to execution
        - Confluence deletions propagate to local filesystem
        - State updates correctly after deletion

        Args:
            change_detector: ChangeDetector fixture
            deletion_handler: DeletionHandler fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Setup: Create test file
        test_file = temp_test_dir / "page.md"
        test_file.write_text("# Page\n\nContent", encoding='utf-8')

        # Tracked pages (page existed at last sync)
        tracked_pages = {
            "123": str(test_file),
        }

        # Current state (page still exists locally)
        local_pages = {
            "123": str(test_file),
        }

        # Remote state (page deleted in Confluence)
        remote_pages = {}

        # Step 1: Detect deletions
        deletion_result = change_detector.detect_deletions(
            local_pages=local_pages,
            tracked_pages=tracked_pages,
            remote_pages=remote_pages
        )

        # Verify detection
        assert len(deletion_result.deleted_in_confluence) == 1
        assert deletion_result.deleted_in_confluence[0].page_id == "123"

        # Step 2: Execute deletions
        deleted_page_ids = deletion_handler.delete_local_files(
            deletion_result.deleted_in_confluence,
            dryrun=False
        )

        # Verify execution
        assert len(deleted_page_ids) == 1
        assert "123" in deleted_page_ids
        assert not test_file.exists(), "File should be deleted"

    def test_full_deletion_flow_local_to_confluence(
        self,
        change_detector: ChangeDetector,
        deletion_handler: DeletionHandler,
        mock_page_operations: Mock,
        temp_test_dir: Path
    ):
        """Test complete deletion flow: detect + delete (local → Confluence).

        Verifies:
        - Full integration from detection to execution
        - Local deletions propagate to Confluence
        - API called correctly

        Args:
            change_detector: ChangeDetector fixture
            deletion_handler: DeletionHandler fixture
            mock_page_operations: Mock PageOperations fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Tracked pages (page existed at last sync)
        tracked_pages = {
            "123": str(temp_test_dir / "page.md"),
        }

        # Current state (page deleted locally)
        local_pages = {}

        # Remote state (page still exists in Confluence)
        remote_pages = {
            "123": "2024-01-15T10:30:00Z",
        }

        # Step 1: Detect deletions
        deletion_result = change_detector.detect_deletions(
            local_pages=local_pages,
            tracked_pages=tracked_pages,
            remote_pages=remote_pages
        )

        # Verify detection
        assert len(deletion_result.deleted_locally) == 1
        assert deletion_result.deleted_locally[0].page_id == "123"

        # Step 2: Execute deletions
        deleted_page_ids = deletion_handler.delete_confluence_pages(
            deletion_result.deleted_locally,
            dryrun=False
        )

        # Verify execution
        assert len(deleted_page_ids) == 1
        assert "123" in deleted_page_ids
        mock_page_operations.delete_page.assert_called_once_with("123")

    def test_deletion_flow_with_errors(
        self,
        deletion_handler: DeletionHandler,
        temp_test_dir: Path
    ):
        """Test deletion flow with filesystem errors.

        Verifies:
        - Errors logged but don't stop processing
        - Partial success handled correctly
        - Only successful deletions returned

        Args:
            deletion_handler: DeletionHandler fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create one valid file
        valid_file = temp_test_dir / "valid.md"
        valid_file.write_text("# Valid\n\nContent", encoding='utf-8')

        # Create deletion infos (one valid, one non-existent)
        deletions = [
            DeletionInfo(
                page_id="123",
                title="Valid Page",
                local_path=valid_file,
                direction="confluence_to_local"
            ),
            DeletionInfo(
                page_id="456",
                title="Missing Page",
                local_path=Path(temp_test_dir / "nonexistent.md"),
                direction="confluence_to_local"
            ),
        ]

        # Execute deletions
        result = deletion_handler.delete_local_files(deletions, dryrun=False)

        # Verify results
        assert len(result) == 1, "Only successful deletion returned"
        assert "123" in result
        assert "456" not in result
        assert not valid_file.exists(), "Valid file should be deleted"

    def test_deletion_flow_empty_result(
        self,
        change_detector: ChangeDetector,
        sample_tracked_pages: dict
    ):
        """Test deletion detection with no deletions.

        Verifies:
        - Empty result when no deletions detected
        - All pages still exist on both sides

        Args:
            change_detector: ChangeDetector fixture
            sample_tracked_pages: Sample tracked pages fixture
        """
        # All pages exist on both sides
        local_pages = {
            "123": sample_tracked_pages["123"],
            "456": sample_tracked_pages["456"],
            "789": sample_tracked_pages["789"],
        }

        remote_pages = {
            "123": "2024-01-15T10:30:00Z",
            "456": "2024-01-15T10:30:00Z",
            "789": "2024-01-15T10:30:00Z",
        }

        # Detect deletions
        result = change_detector.detect_deletions(
            local_pages=local_pages,
            tracked_pages=sample_tracked_pages,
            remote_pages=remote_pages
        )

        # Verify no deletions detected
        assert len(result.deleted_in_confluence) == 0
        assert len(result.deleted_locally) == 0
