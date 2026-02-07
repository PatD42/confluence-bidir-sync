"""Integration tests for move flow.

This module tests the end-to-end move flow from change detection
through move execution. Tests verify:
- detect_moves correctly identifies moved pages
- MoveHandler processes moves in both directions
- update_page_parent API call successfully updates Confluence page parents
- Integration between ChangeDetector, MoveHandler, and PageOperations
- File system operations for local file moves
- API operations for Confluence page parent updates

Requirements:
- Temporary test directories (provided by fixtures)
- Mock Confluence API for testing (no actual API calls)
- Real filesystem operations for local file moves
"""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from src.cli.change_detector import ChangeDetector
from src.cli.move_handler import MoveHandler
from src.cli.models import MoveInfo, MoveResult
from src.page_operations.page_operations import PageOperations


@pytest.mark.integration
class TestMoveFlow:
    """Integration tests for move detection and execution flow."""

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
            Mock PageOperations with update_page_parent method
        """
        mock = Mock(spec=PageOperations)

        # Mock update_page_parent to return success dict
        # Note: The move_handler code expects a dict, not an UpdateResult object
        def mock_update_parent(page_id, parent_id):
            return {
                'success': True,
                'page_id': page_id,
                'old_version': 1,
                'new_version': 2,
                'operations_applied': 1
            }

        mock.update_page_parent = Mock(side_effect=mock_update_parent)
        return mock

    @pytest.fixture(scope="function")
    def move_handler(self, mock_page_operations: Mock) -> MoveHandler:
        """Create a MoveHandler instance with mock dependencies.

        Args:
            mock_page_operations: Mock PageOperations fixture

        Returns:
            MoveHandler instance
        """
        return MoveHandler(page_operations=mock_page_operations)

    @pytest.fixture(scope="function")
    def sample_tracked_pages(self, temp_test_dir: Path) -> dict:
        """Create sample tracked pages for testing.

        Args:
            temp_test_dir: Temporary test directory fixture

        Returns:
            Dict mapping page_id to local file path
        """
        return {
            "123": str(temp_test_dir / "old-location" / "page1.md"),
            "456": str(temp_test_dir / "section-a" / "page2.md"),
            "789": str(temp_test_dir / "section-b" / "page3.md"),
        }

    @pytest.fixture(scope="function")
    def sample_pages_with_ancestors(self) -> dict:
        """Create sample page data with ancestor information.

        Returns:
            Dict mapping page_id to page data with ancestors
        """
        return {
            "123": {
                "title": "Page 1",
                "ancestors": []  # At space root
            },
            "456": {
                "title": "Page 2",
                "ancestors": []  # At space root
            },
            "789": {
                "title": "Page 3",
                "ancestors": []  # At space root
            },
        }

    def test_detect_moves_confluence_only(
        self,
        change_detector: ChangeDetector,
        sample_tracked_pages: dict,
        sample_pages_with_ancestors: dict,
        temp_test_dir: Path
    ):
        """Test detecting pages moved in Confluence.

        Verifies:
        - Pages with different paths from ancestors are detected
        - Move direction is set correctly
        - Old and new paths are captured

        Args:
            change_detector: ChangeDetector fixture
            sample_tracked_pages: Sample tracked pages fixture
            sample_pages_with_ancestors: Sample pages with ancestors fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Current local pages (unchanged from tracked)
        local_pages = {
            "123": sample_tracked_pages["123"],
            "456": sample_tracked_pages["456"],
            "789": sample_tracked_pages["789"],
        }

        # Mock expected path from ancestors for page 456 (moved in Confluence)
        with patch.object(
            change_detector,
            '_get_expected_path_from_ancestors',
            side_effect=lambda page_id, page_data: {
                "123": sample_tracked_pages["123"],  # No move
                "456": str(temp_test_dir / "new-location" / "page2.md"),  # Moved
                "789": sample_tracked_pages["789"],  # No move
            }.get(page_id)
        ):
            # Detect moves
            result = change_detector.detect_moves(
                local_pages=local_pages,
                tracked_pages=sample_tracked_pages,
                pages_with_ancestors=sample_pages_with_ancestors
            )

        # Verify results
        assert len(result.moved_in_confluence) == 1, \
            "Should detect 1 move in Confluence"
        assert len(result.moved_locally) == 0, \
            "Should detect 0 local moves"

        move = result.moved_in_confluence[0]
        assert move.page_id == "456"
        assert move.direction == "confluence_to_local"
        assert move.old_path == Path(sample_tracked_pages["456"])
        assert move.new_path == Path(temp_test_dir / "new-location" / "page2.md")

    def test_detect_moves_local_only(
        self,
        change_detector: ChangeDetector,
        sample_tracked_pages: dict,
        sample_pages_with_ancestors: dict,
        temp_test_dir: Path
    ):
        """Test detecting pages moved locally.

        Verifies:
        - Pages with different local paths are detected
        - Move direction is set correctly
        - Old and new paths are captured

        Args:
            change_detector: ChangeDetector fixture
            sample_tracked_pages: Sample tracked pages fixture
            sample_pages_with_ancestors: Sample pages with ancestors fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Page 456 moved locally
        local_pages = {
            "123": sample_tracked_pages["123"],
            "456": str(temp_test_dir / "new-location" / "page2.md"),  # Moved
            "789": sample_tracked_pages["789"],
        }

        # Mock expected paths from ancestors (no Confluence moves)
        with patch.object(
            change_detector,
            '_get_expected_path_from_ancestors',
            side_effect=lambda page_id, page_data: sample_tracked_pages.get(page_id)
        ):
            # Detect moves
            result = change_detector.detect_moves(
                local_pages=local_pages,
                tracked_pages=sample_tracked_pages,
                pages_with_ancestors=sample_pages_with_ancestors
            )

        # Verify results
        assert len(result.moved_in_confluence) == 0, \
            "Should detect 0 moves in Confluence"
        assert len(result.moved_locally) == 1, \
            "Should detect 1 local move"

        move = result.moved_locally[0]
        assert move.page_id == "456"
        assert move.direction == "local_to_confluence"
        assert move.old_path == Path(sample_tracked_pages["456"])
        assert move.new_path == Path(temp_test_dir / "new-location" / "page2.md")

    def test_detect_moves_both_sides(
        self,
        change_detector: ChangeDetector,
        sample_tracked_pages: dict,
        sample_pages_with_ancestors: dict,
        temp_test_dir: Path
    ):
        """Test detecting moves on both sides.

        Verifies:
        - Multiple moves detected correctly
        - Each move categorized by direction
        - Confluence moves take precedence over local moves

        Args:
            change_detector: ChangeDetector fixture
            sample_tracked_pages: Sample tracked pages fixture
            sample_pages_with_ancestors: Sample pages with ancestors fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Page 456 moved locally, page 789 unchanged locally
        local_pages = {
            "123": sample_tracked_pages["123"],
            "456": str(temp_test_dir / "new-local" / "page2.md"),  # Local move
            "789": sample_tracked_pages["789"],
        }

        # Mock expected paths - page 789 moved in Confluence
        with patch.object(
            change_detector,
            '_get_expected_path_from_ancestors',
            side_effect=lambda page_id, page_data: {
                "123": sample_tracked_pages["123"],
                "456": sample_tracked_pages["456"],  # No Confluence move
                "789": str(temp_test_dir / "new-confluence" / "page3.md"),  # Confluence move
            }.get(page_id)
        ):
            # Detect moves
            result = change_detector.detect_moves(
                local_pages=local_pages,
                tracked_pages=sample_tracked_pages,
                pages_with_ancestors=sample_pages_with_ancestors
            )

        # Verify results
        assert len(result.moved_in_confluence) == 1, \
            "Should detect 1 move in Confluence"
        assert len(result.moved_locally) == 1, \
            "Should detect 1 local move"

        # Check Confluence move
        conf_move = result.moved_in_confluence[0]
        assert conf_move.page_id == "789"
        assert conf_move.direction == "confluence_to_local"

        # Check local move
        local_move = result.moved_locally[0]
        assert local_move.page_id == "456"
        assert local_move.direction == "local_to_confluence"

    def test_move_local_files_integration(
        self,
        move_handler: MoveHandler,
        temp_test_dir: Path
    ):
        """Test moving local files end-to-end.

        Verifies:
        - Files are actually moved on filesystem
        - Moved page IDs are returned
        - Multiple files handled correctly
        - Parent directories created

        Args:
            move_handler: MoveHandler fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create test files
        old_dir = temp_test_dir / "old-location"
        old_dir.mkdir(parents=True)
        file1 = old_dir / "page1.md"
        file2 = old_dir / "page2.md"
        file1.write_text("# Page 1\n\nContent", encoding='utf-8')
        file2.write_text("# Page 2\n\nContent", encoding='utf-8')

        # Verify files exist
        assert file1.exists()
        assert file2.exists()

        # Create move infos
        new_dir = temp_test_dir / "new-location"
        moves = [
            MoveInfo(
                page_id="123",
                title="Page 1",
                old_path=file1,
                new_path=new_dir / "page1.md",
                direction="confluence_to_local"
            ),
            MoveInfo(
                page_id="456",
                title="Page 2",
                old_path=file2,
                new_path=new_dir / "page2.md",
                direction="confluence_to_local"
            ),
        ]

        # Execute moves
        result = move_handler.move_local_files(moves, dryrun=False)

        # Verify results
        assert len(result) == 2
        assert "123" in result
        assert "456" in result
        assert not file1.exists(), "Old file 1 should not exist"
        assert not file2.exists(), "Old file 2 should not exist"
        assert (new_dir / "page1.md").exists(), "New file 1 should exist"
        assert (new_dir / "page2.md").exists(), "New file 2 should exist"

    def test_move_local_files_dryrun(
        self,
        move_handler: MoveHandler,
        temp_test_dir: Path
    ):
        """Test dry run mode for local file moves.

        Verifies:
        - Files are NOT moved in dry run mode
        - Empty result returned
        - Files still exist in original location

        Args:
            move_handler: MoveHandler fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create test file
        old_dir = temp_test_dir / "old-location"
        old_dir.mkdir(parents=True)
        test_file = old_dir / "page.md"
        test_file.write_text("# Page\n\nContent", encoding='utf-8')

        # Verify file exists
        assert test_file.exists()

        # Create move info
        new_dir = temp_test_dir / "new-location"
        moves = [
            MoveInfo(
                page_id="123",
                title="Page",
                old_path=test_file,
                new_path=new_dir / "page.md",
                direction="confluence_to_local"
            ),
        ]

        # Execute dry run
        result = move_handler.move_local_files(moves, dryrun=True)

        # Verify results
        assert len(result) == 0, "Dry run should return empty result"
        assert test_file.exists(), "File should still exist in old location"
        assert not (new_dir / "page.md").exists(), "File should not be in new location"

    def test_move_confluence_pages_integration(
        self,
        move_handler: MoveHandler,
        mock_page_operations: Mock,
        temp_test_dir: Path
    ):
        """Test moving Confluence pages via API.

        Verifies:
        - update_page_parent API called for each move
        - Correct page IDs and parent IDs passed to API
        - Moved page IDs returned

        Args:
            move_handler: MoveHandler fixture
            mock_page_operations: Mock PageOperations fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create move infos
        parent_dir = temp_test_dir / "parent-section"
        moves = [
            MoveInfo(
                page_id="123",
                title="Page 1",
                old_path=Path(temp_test_dir / "old" / "page1.md"),
                new_path=parent_dir / "page1.md",
                direction="local_to_confluence"
            ),
            MoveInfo(
                page_id="456",
                title="Page 2",
                old_path=Path(temp_test_dir / "old" / "page2.md"),
                new_path=parent_dir / "page2.md",
                direction="local_to_confluence"
            ),
        ]

        # Mock resolve_parent_page_id to return a parent ID
        with patch.object(move_handler, 'resolve_parent_page_id', return_value="999"):
            # Execute moves
            result = move_handler.move_confluence_pages(moves, dryrun=False)

        # Verify results
        assert len(result) == 2
        assert "123" in result
        assert "456" in result

        # Verify API calls
        assert mock_page_operations.update_page_parent.call_count == 2
        mock_page_operations.update_page_parent.assert_any_call(
            page_id="123",
            parent_id="999"
        )
        mock_page_operations.update_page_parent.assert_any_call(
            page_id="456",
            parent_id="999"
        )

    def test_move_confluence_pages_dryrun(
        self,
        move_handler: MoveHandler,
        mock_page_operations: Mock,
        temp_test_dir: Path
    ):
        """Test dry run mode for Confluence page moves.

        Verifies:
        - API is NOT called in dry run mode
        - Empty result returned
        - No pages moved

        Args:
            move_handler: MoveHandler fixture
            mock_page_operations: Mock PageOperations fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create move info
        parent_dir = temp_test_dir / "parent-section"
        moves = [
            MoveInfo(
                page_id="123",
                title="Page",
                old_path=Path(temp_test_dir / "old" / "page.md"),
                new_path=parent_dir / "page.md",
                direction="local_to_confluence"
            ),
        ]

        # Mock resolve_parent_page_id to return a parent ID
        with patch.object(move_handler, 'resolve_parent_page_id', return_value="999"):
            # Execute dry run
            result = move_handler.move_confluence_pages(moves, dryrun=True)

        # Verify results
        assert len(result) == 0, "Dry run should return empty result"
        mock_page_operations.update_page_parent.assert_not_called()

    def test_full_move_flow_confluence_to_local(
        self,
        change_detector: ChangeDetector,
        move_handler: MoveHandler,
        temp_test_dir: Path
    ):
        """Test complete move flow: detect + move (Confluence → local).

        Verifies:
        - Full integration from detection to execution
        - Confluence moves propagate to local filesystem
        - Files moved to correct locations

        Args:
            change_detector: ChangeDetector fixture
            move_handler: MoveHandler fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Setup: Create test file
        old_dir = temp_test_dir / "old-location"
        old_dir.mkdir(parents=True)
        test_file = old_dir / "page.md"
        test_file.write_text("# Page\n\nContent", encoding='utf-8')

        # Tracked pages (page existed at old location)
        tracked_pages = {
            "123": str(test_file),
        }

        # Current state (page still at old location locally)
        local_pages = {
            "123": str(test_file),
        }

        # Page data with ancestors
        pages_with_ancestors = {
            "123": {
                "title": "Page",
                "ancestors": []
            }
        }

        # Mock expected path from ancestors (moved in Confluence)
        new_file = temp_test_dir / "new-location" / "page.md"
        with patch.object(
            change_detector,
            '_get_expected_path_from_ancestors',
            return_value=str(new_file)
        ):
            # Step 1: Detect moves
            move_result = change_detector.detect_moves(
                local_pages=local_pages,
                tracked_pages=tracked_pages,
                pages_with_ancestors=pages_with_ancestors
            )

        # Verify detection
        assert len(move_result.moved_in_confluence) == 1
        assert move_result.moved_in_confluence[0].page_id == "123"

        # Step 2: Execute moves
        moved_page_ids = move_handler.move_local_files(
            move_result.moved_in_confluence,
            dryrun=False
        )

        # Verify execution
        assert len(moved_page_ids) == 1
        assert "123" in moved_page_ids
        assert not test_file.exists(), "File should be moved from old location"
        assert new_file.exists(), "File should exist in new location"

    def test_full_move_flow_local_to_confluence(
        self,
        change_detector: ChangeDetector,
        move_handler: MoveHandler,
        mock_page_operations: Mock,
        temp_test_dir: Path
    ):
        """Test complete move flow: detect + move (local → Confluence).

        Verifies:
        - Full integration from detection to execution
        - Local moves propagate to Confluence
        - API called correctly with parent ID

        Args:
            change_detector: ChangeDetector fixture
            move_handler: MoveHandler fixture
            mock_page_operations: Mock PageOperations fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Setup: Create parent directory
        parent_dir = temp_test_dir / "parent-section"
        parent_dir.mkdir(parents=True)

        # Tracked pages (page existed at old location)
        tracked_pages = {
            "123": str(temp_test_dir / "old-location" / "page.md"),
        }

        # Current state (page moved locally to new location)
        current_path = parent_dir / "page.md"
        local_pages = {
            "123": str(current_path),
        }

        # Page data with ancestors
        pages_with_ancestors = {
            "123": {
                "title": "Page",
                "ancestors": []
            }
        }

        # Mock expected path from ancestors (no Confluence move)
        with patch.object(
            change_detector,
            '_get_expected_path_from_ancestors',
            return_value=tracked_pages["123"]
        ):
            # Step 1: Detect moves
            move_result = change_detector.detect_moves(
                local_pages=local_pages,
                tracked_pages=tracked_pages,
                pages_with_ancestors=pages_with_ancestors
            )

        # Verify detection
        assert len(move_result.moved_locally) == 1
        assert move_result.moved_locally[0].page_id == "123"

        # Mock resolve_parent_page_id to return a parent ID
        with patch.object(move_handler, 'resolve_parent_page_id', return_value="999"):
            # Step 2: Execute moves
            moved_page_ids = move_handler.move_confluence_pages(
                move_result.moved_locally,
                dryrun=False
            )

        # Verify execution
        assert len(moved_page_ids) == 1
        assert "123" in moved_page_ids
        mock_page_operations.update_page_parent.assert_called_once_with(
            page_id="123",
            parent_id="999"
        )

    def test_move_flow_with_errors(
        self,
        move_handler: MoveHandler,
        temp_test_dir: Path
    ):
        """Test move flow with filesystem errors.

        Verifies:
        - Errors logged but don't stop processing
        - Partial success handled correctly
        - Only successful moves returned

        Args:
            move_handler: MoveHandler fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create one valid file
        old_dir = temp_test_dir / "old-location"
        old_dir.mkdir(parents=True)
        valid_file = old_dir / "valid.md"
        valid_file.write_text("# Valid\n\nContent", encoding='utf-8')

        # Create move infos (one valid, one non-existent source)
        new_dir = temp_test_dir / "new-location"
        moves = [
            MoveInfo(
                page_id="123",
                title="Valid Page",
                old_path=valid_file,
                new_path=new_dir / "valid.md",
                direction="confluence_to_local"
            ),
            MoveInfo(
                page_id="456",
                title="Missing Page",
                old_path=Path(temp_test_dir / "nonexistent.md"),
                new_path=new_dir / "missing.md",
                direction="confluence_to_local"
            ),
        ]

        # Execute moves
        result = move_handler.move_local_files(moves, dryrun=False)

        # Verify results
        assert len(result) == 1, "Only successful move returned"
        assert "123" in result
        assert "456" not in result
        assert not valid_file.exists(), "Valid file should be moved"
        assert (new_dir / "valid.md").exists(), "Valid file should exist in new location"

    def test_move_flow_empty_result(
        self,
        change_detector: ChangeDetector,
        sample_tracked_pages: dict,
        sample_pages_with_ancestors: dict
    ):
        """Test move detection with no moves.

        Verifies:
        - Empty result when no moves detected
        - All pages still in same location

        Args:
            change_detector: ChangeDetector fixture
            sample_tracked_pages: Sample tracked pages fixture
            sample_pages_with_ancestors: Sample pages with ancestors fixture
        """
        # All pages unchanged
        local_pages = {
            "123": sample_tracked_pages["123"],
            "456": sample_tracked_pages["456"],
            "789": sample_tracked_pages["789"],
        }

        # Mock expected paths (all same as tracked)
        with patch.object(
            change_detector,
            '_get_expected_path_from_ancestors',
            side_effect=lambda page_id, page_data: sample_tracked_pages.get(page_id)
        ):
            # Detect moves
            result = change_detector.detect_moves(
                local_pages=local_pages,
                tracked_pages=sample_tracked_pages,
                pages_with_ancestors=sample_pages_with_ancestors
            )

        # Verify no moves detected
        assert len(result.moved_in_confluence) == 0
        assert len(result.moved_locally) == 0
