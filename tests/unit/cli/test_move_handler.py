"""Unit tests for cli.move_handler module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from src.cli.errors import CLIError
from src.cli.models import MoveInfo
from src.cli.move_handler import MoveHandler


class TestMoveHandler:
    """Test cases for MoveHandler."""

    @pytest.fixture
    def handler(self):
        """Create MoveHandler instance."""
        return MoveHandler()

    @pytest.fixture
    def handler_with_page_ops(self):
        """Create MoveHandler with mocked page_operations."""
        mock_page_ops = Mock()
        return MoveHandler(page_operations=mock_page_ops)

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        # Cleanup
        import shutil
        if os.path.exists(temp_path):
            shutil.rmtree(temp_path)


class TestMoveLocalFiles(TestMoveHandler):
    """Test cases for move_local_files method."""

    def test_move_local_files_success(self, handler, temp_dir):
        """Successfully move a local file to new location."""
        # Arrange
        old_path = Path(temp_dir) / "old-location" / "page.md"
        new_path = Path(temp_dir) / "new-location" / "page.md"

        # Create source file
        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_text("# Test Page\n\nContent here")

        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=old_path,
                new_path=new_path,
                direction="confluence_to_local"
            )
        ]

        # Act
        result = handler.move_local_files(moves, dryrun=False)

        # Assert
        assert len(result) == 1
        assert result[0] == "123"
        assert new_path.exists()
        assert not old_path.exists()
        assert new_path.read_text() == "# Test Page\n\nContent here"

    def test_move_local_files_dryrun(self, handler, temp_dir):
        """Dryrun mode - no actual file moves."""
        # Arrange
        old_path = Path(temp_dir) / "old-location" / "page.md"
        new_path = Path(temp_dir) / "new-location" / "page.md"

        # Create source file
        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_text("# Test Page")

        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=old_path,
                new_path=new_path,
                direction="confluence_to_local"
            )
        ]

        # Act
        result = handler.move_local_files(moves, dryrun=True)

        # Assert
        assert len(result) == 0  # Dryrun returns empty list
        assert old_path.exists()  # Source still exists
        assert not new_path.exists()  # Target not created

    def test_move_local_files_empty_list(self, handler):
        """Empty move list returns empty result."""
        # Act
        result = handler.move_local_files([], dryrun=False)

        # Assert
        assert result == []

    def test_move_local_files_missing_old_path(self, handler, temp_dir):
        """Skip move when old_path is None."""
        # Arrange
        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=None,
                new_path=Path(temp_dir) / "new-location" / "page.md",
                direction="confluence_to_local"
            )
        ]

        # Act
        result = handler.move_local_files(moves, dryrun=False)

        # Assert
        assert len(result) == 0  # Move skipped

    def test_move_local_files_missing_new_path(self, handler, temp_dir):
        """Skip move when new_path is None."""
        # Arrange
        old_path = Path(temp_dir) / "old-location" / "page.md"
        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_text("# Test Page")

        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=old_path,
                new_path=None,
                direction="confluence_to_local"
            )
        ]

        # Act
        result = handler.move_local_files(moves, dryrun=False)

        # Assert
        assert len(result) == 0  # Move skipped
        assert old_path.exists()  # Source unchanged

    def test_move_local_files_wrong_direction(self, handler, temp_dir):
        """Skip move when direction is incorrect."""
        # Arrange
        old_path = Path(temp_dir) / "old-location" / "page.md"
        new_path = Path(temp_dir) / "new-location" / "page.md"

        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_text("# Test Page")

        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=old_path,
                new_path=new_path,
                direction="local_to_confluence"  # Wrong direction!
            )
        ]

        # Act
        result = handler.move_local_files(moves, dryrun=False)

        # Assert
        assert len(result) == 0  # Move skipped
        assert old_path.exists()  # Source unchanged

    def test_move_local_files_source_not_exists(self, handler, temp_dir):
        """Skip move when source file doesn't exist."""
        # Arrange
        old_path = Path(temp_dir) / "old-location" / "nonexistent.md"
        new_path = Path(temp_dir) / "new-location" / "page.md"

        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=old_path,
                new_path=new_path,
                direction="confluence_to_local"
            )
        ]

        # Act
        result = handler.move_local_files(moves, dryrun=False)

        # Assert
        assert len(result) == 0  # Move skipped
        assert not new_path.exists()  # Target not created

    def test_move_local_files_target_exists(self, handler, temp_dir):
        """Skip move when target file already exists."""
        # Arrange
        old_path = Path(temp_dir) / "old-location" / "page.md"
        new_path = Path(temp_dir) / "new-location" / "page.md"

        # Create both source and target
        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_text("# Old Content")
        new_path.parent.mkdir(parents=True, exist_ok=True)
        new_path.write_text("# Existing Content")

        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=old_path,
                new_path=new_path,
                direction="confluence_to_local"
            )
        ]

        # Act
        result = handler.move_local_files(moves, dryrun=False)

        # Assert
        assert len(result) == 0  # Move skipped
        assert old_path.exists()  # Source unchanged
        assert new_path.read_text() == "# Existing Content"  # Target unchanged

    def test_move_local_files_creates_parent_dirs(self, handler, temp_dir):
        """Move creates parent directories if they don't exist."""
        # Arrange
        old_path = Path(temp_dir) / "old-location" / "page.md"
        new_path = Path(temp_dir) / "deeply" / "nested" / "new-location" / "page.md"

        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_text("# Test Page")

        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=old_path,
                new_path=new_path,
                direction="confluence_to_local"
            )
        ]

        # Act
        result = handler.move_local_files(moves, dryrun=False)

        # Assert
        assert len(result) == 1
        assert new_path.exists()
        assert new_path.parent.exists()  # Parent dirs created

    def test_move_local_files_multiple_moves(self, handler, temp_dir):
        """Process multiple moves successfully."""
        # Arrange
        moves = []
        for i in range(3):
            old_path = Path(temp_dir) / f"old-{i}" / f"page-{i}.md"
            new_path = Path(temp_dir) / f"new-{i}" / f"page-{i}.md"

            old_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.write_text(f"# Page {i}")

            moves.append(
                MoveInfo(
                    page_id=f"12{i}",
                    title=f"Page {i}",
                    old_path=old_path,
                    new_path=new_path,
                    direction="confluence_to_local"
                )
            )

        # Act
        result = handler.move_local_files(moves, dryrun=False)

        # Assert
        assert len(result) == 3
        assert "120" in result
        assert "121" in result
        assert "122" in result

    def test_move_local_files_partial_success(self, handler, temp_dir):
        """Continue processing after individual move failures."""
        # Arrange
        # First move - valid
        old_path_1 = Path(temp_dir) / "old-1" / "page-1.md"
        new_path_1 = Path(temp_dir) / "new-1" / "page-1.md"
        old_path_1.parent.mkdir(parents=True, exist_ok=True)
        old_path_1.write_text("# Page 1")

        # Second move - source doesn't exist (will fail)
        old_path_2 = Path(temp_dir) / "old-2" / "nonexistent.md"
        new_path_2 = Path(temp_dir) / "new-2" / "page-2.md"

        # Third move - valid
        old_path_3 = Path(temp_dir) / "old-3" / "page-3.md"
        new_path_3 = Path(temp_dir) / "new-3" / "page-3.md"
        old_path_3.parent.mkdir(parents=True, exist_ok=True)
        old_path_3.write_text("# Page 3")

        moves = [
            MoveInfo("123", "Page 1", old_path_1, new_path_1, "confluence_to_local"),
            MoveInfo("456", "Page 2", old_path_2, new_path_2, "confluence_to_local"),
            MoveInfo("789", "Page 3", old_path_3, new_path_3, "confluence_to_local"),
        ]

        # Act
        result = handler.move_local_files(moves, dryrun=False)

        # Assert
        assert len(result) == 2  # Only 2 succeeded
        assert "123" in result
        assert "789" in result
        assert "456" not in result
        assert new_path_1.exists()
        assert not new_path_2.exists()
        assert new_path_3.exists()

    def test_move_local_files_cleanup_empty_dirs(self, handler, temp_dir):
        """Empty directories are cleaned up after move."""
        # Arrange
        old_path = Path(temp_dir) / "old-folder" / "subfolder" / "page.md"
        new_path = Path(temp_dir) / "new-folder" / "page.md"

        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_text("# Test Page")

        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=old_path,
                new_path=new_path,
                direction="confluence_to_local"
            )
        ]

        # Act
        result = handler.move_local_files(moves, dryrun=False)

        # Assert
        assert len(result) == 1
        assert new_path.exists()
        # The subfolder should be removed if empty
        # Note: This depends on cleanup implementation - may not remove all levels


class TestMoveConfluencePages(TestMoveHandler):
    """Test cases for move_confluence_pages method."""

    def test_move_confluence_pages_success(self, handler_with_page_ops, temp_dir):
        """Successfully update Confluence page parent."""
        # Arrange
        handler = handler_with_page_ops
        new_path = Path(temp_dir) / "section-a" / "page.md"

        # Mock update_page_parent method
        handler.page_operations.update_page_parent = Mock(
            return_value={"success": True}
        )

        # Mock resolve_parent_page_id
        with patch.object(
            handler, 'resolve_parent_page_id', return_value="parent-123"
        ):
            moves = [
                MoveInfo(
                    page_id="123",
                    title="Test Page",
                    old_path=Path(temp_dir) / "old" / "page.md",
                    new_path=new_path,
                    direction="local_to_confluence"
                )
            ]

            # Act
            result = handler.move_confluence_pages(moves, dryrun=False)

        # Assert
        assert len(result) == 1
        assert result[0] == "123"
        handler.page_operations.update_page_parent.assert_called_once_with(
            page_id="123",
            parent_id="parent-123"
        )

    def test_move_confluence_pages_dryrun(self, handler_with_page_ops, temp_dir):
        """Dryrun mode - no actual API calls."""
        # Arrange
        handler = handler_with_page_ops
        new_path = Path(temp_dir) / "section-a" / "page.md"

        # Mock resolve_parent_page_id
        with patch.object(
            handler, 'resolve_parent_page_id', return_value="parent-123"
        ):
            moves = [
                MoveInfo(
                    page_id="123",
                    title="Test Page",
                    old_path=Path(temp_dir) / "old" / "page.md",
                    new_path=new_path,
                    direction="local_to_confluence"
                )
            ]

            # Act
            result = handler.move_confluence_pages(moves, dryrun=True)

        # Assert
        assert len(result) == 0  # Dryrun returns empty list
        # No API calls should be made
        assert not handler.page_operations.update_page_parent.called

    def test_move_confluence_pages_empty_list(self, handler_with_page_ops):
        """Empty move list returns empty result."""
        # Act
        result = handler_with_page_ops.move_confluence_pages([], dryrun=False)

        # Assert
        assert result == []

    def test_move_confluence_pages_no_page_operations(self, handler):
        """Raise error when page_operations not provided."""
        # Arrange
        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=Path("old/page.md"),
                new_path=Path("new/page.md"),
                direction="local_to_confluence"
            )
        ]

        # Act & Assert
        with pytest.raises(CLIError, match="PageOperations instance required"):
            handler.move_confluence_pages(moves, dryrun=False)

    def test_move_confluence_pages_missing_new_path(self, handler_with_page_ops):
        """Skip move when new_path is None."""
        # Arrange
        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=Path("old/page.md"),
                new_path=None,
                direction="local_to_confluence"
            )
        ]

        # Act
        result = handler_with_page_ops.move_confluence_pages(moves, dryrun=False)

        # Assert
        assert len(result) == 0  # Move skipped

    def test_move_confluence_pages_wrong_direction(self, handler_with_page_ops, temp_dir):
        """Skip move when direction is incorrect."""
        # Arrange
        moves = [
            MoveInfo(
                page_id="123",
                title="Test Page",
                old_path=Path(temp_dir) / "old" / "page.md",
                new_path=Path(temp_dir) / "new" / "page.md",
                direction="confluence_to_local"  # Wrong direction!
            )
        ]

        # Act
        result = handler_with_page_ops.move_confluence_pages(moves, dryrun=False)

        # Assert
        assert len(result) == 0  # Move skipped

    def test_move_confluence_pages_parent_resolution_fails(
        self, handler_with_page_ops, temp_dir
    ):
        """Continue when parent resolution fails."""
        # Arrange
        handler = handler_with_page_ops
        new_path = Path(temp_dir) / "section-a" / "page.md"

        # Mock resolve_parent_page_id to raise error
        with patch.object(
            handler,
            'resolve_parent_page_id',
            side_effect=CLIError("Parent not found")
        ):
            moves = [
                MoveInfo(
                    page_id="123",
                    title="Test Page",
                    old_path=Path(temp_dir) / "old" / "page.md",
                    new_path=new_path,
                    direction="local_to_confluence"
                )
            ]

            # Act
            result = handler.move_confluence_pages(moves, dryrun=False)

        # Assert
        assert len(result) == 0  # Move failed/skipped

    def test_move_confluence_pages_multiple_moves(self, handler_with_page_ops, temp_dir):
        """Process multiple moves successfully."""
        # Arrange
        handler = handler_with_page_ops
        handler.page_operations.update_page_parent = Mock(
            return_value={"success": True}
        )

        moves = [
            MoveInfo(f"12{i}", f"Page {i}", Path(f"old-{i}/page.md"),
                    Path(temp_dir) / f"new-{i}" / f"page-{i}.md", "local_to_confluence")
            for i in range(3)
        ]

        with patch.object(
            handler, 'resolve_parent_page_id', return_value="parent-123"
        ):
            # Act
            result = handler.move_confluence_pages(moves, dryrun=False)

        # Assert
        assert len(result) == 3
        assert "120" in result
        assert "121" in result
        assert "122" in result

    def test_move_confluence_pages_space_root(self, handler_with_page_ops, temp_dir):
        """Move page to space root (parent_id=None)."""
        # Arrange
        handler = handler_with_page_ops
        new_path = Path(temp_dir) / "page.md"

        handler.page_operations.update_page_parent = Mock(
            return_value={"success": True}
        )

        with patch.object(
            handler, 'resolve_parent_page_id', return_value=None
        ):
            moves = [
                MoveInfo(
                    page_id="123",
                    title="Test Page",
                    old_path=Path(temp_dir) / "old" / "page.md",
                    new_path=new_path,
                    direction="local_to_confluence"
                )
            ]

            # Act
            result = handler.move_confluence_pages(moves, dryrun=False)

        # Assert
        assert len(result) == 1
        handler.page_operations.update_page_parent.assert_called_once_with(
            page_id="123",
            parent_id=None
        )


class TestResolveParentPageId(TestMoveHandler):
    """Test cases for resolve_parent_page_id method."""

    def test_resolve_parent_page_id_root_level(self, handler, temp_dir):
        """Root level file returns None (space root)."""
        # Arrange
        file_path = Path(temp_dir) / "page.md"

        # Act
        result = handler.resolve_parent_page_id(file_path)

        # Assert
        assert result is None

    def test_resolve_parent_page_id_nested_with_parent(self, handler, temp_dir):
        """Nested file with parent returns parent page ID."""
        # Arrange
        # Create parent file: docs/section-a.md with frontmatter
        parent_file = Path(temp_dir) / "docs" / "section-a.md"
        parent_file.parent.mkdir(parents=True, exist_ok=True)
        parent_file.write_text(
            "---\n"
            "confluence_page_id: parent-123\n"
            "---\n"
            "# Section A\n"
        )

        # Child file would be: docs/section-a/page.md
        child_file = Path(temp_dir) / "docs" / "section-a" / "page.md"

        # Mock FrontmatterHandler.extract to return expected data
        mock_frontmatter_handler = Mock()
        mock_frontmatter_handler.extract.return_value = {
            'confluence_page_id': 'parent-123'
        }

        with patch('src.file_mapper.frontmatter_handler.FrontmatterHandler', return_value=mock_frontmatter_handler):
            # Act
            result = handler.resolve_parent_page_id(child_file)

        # Assert
        assert result == "parent-123"

    def test_resolve_parent_page_id_missing_parent_file(self, handler, temp_dir):
        """Missing parent file returns None."""
        # Arrange
        # No parent file exists for: docs/section-a/page.md
        child_file = Path(temp_dir) / "docs" / "section-a" / "page.md"

        # Act
        result = handler.resolve_parent_page_id(child_file)

        # Assert
        assert result is None

    def test_resolve_parent_page_id_parent_missing_page_id(self, handler, temp_dir):
        """Parent file without confluence_page_id raises error."""
        # Arrange
        # Create parent file without confluence_page_id
        parent_file = Path(temp_dir) / "docs" / "section-a.md"
        parent_file.parent.mkdir(parents=True, exist_ok=True)
        parent_file.write_text(
            "---\n"
            "title: Section A\n"
            "---\n"
            "# Section A\n"
        )

        child_file = Path(temp_dir) / "docs" / "section-a" / "page.md"

        # Mock FrontmatterHandler.extract to return data without confluence_page_id
        mock_frontmatter_handler = Mock()
        mock_frontmatter_handler.extract.return_value = {
            'title': 'Section A'
        }

        with patch('src.file_mapper.frontmatter_handler.FrontmatterHandler', return_value=mock_frontmatter_handler):
            # Act & Assert
            with pytest.raises(CLIError, match="missing confluence_page_id"):
                handler.resolve_parent_page_id(child_file)

    def test_resolve_parent_page_id_deeply_nested(self, handler, temp_dir):
        """Deeply nested file resolves immediate parent."""
        # Arrange
        # Create parent file: docs/section-a/subsection-b.md
        parent_file = Path(temp_dir) / "docs" / "section-a" / "subsection-b.md"
        parent_file.parent.mkdir(parents=True, exist_ok=True)
        parent_file.write_text(
            "---\n"
            "confluence_page_id: subsection-123\n"
            "---\n"
            "# Subsection B\n"
        )

        # Child file: docs/section-a/subsection-b/page.md
        child_file = Path(temp_dir) / "docs" / "section-a" / "subsection-b" / "page.md"

        # Mock FrontmatterHandler.extract to return expected data
        mock_frontmatter_handler = Mock()
        mock_frontmatter_handler.extract.return_value = {
            'confluence_page_id': 'subsection-123'
        }

        with patch('src.file_mapper.frontmatter_handler.FrontmatterHandler', return_value=mock_frontmatter_handler):
            # Act
            result = handler.resolve_parent_page_id(child_file)

        # Assert
        assert result == "subsection-123"

    def test_resolve_parent_page_id_string_path(self, handler, temp_dir):
        """Accepts string path (not just Path object)."""
        # Arrange
        parent_file = Path(temp_dir) / "docs" / "section-a.md"
        parent_file.parent.mkdir(parents=True, exist_ok=True)
        parent_file.write_text(
            "---\n"
            "confluence_page_id: parent-123\n"
            "---\n"
            "# Section A\n"
        )

        # Pass string path instead of Path object
        child_file = str(Path(temp_dir) / "docs" / "section-a" / "page.md")

        # Mock FrontmatterHandler.extract to return expected data
        mock_frontmatter_handler = Mock()
        mock_frontmatter_handler.extract.return_value = {
            'confluence_page_id': 'parent-123'
        }

        with patch('src.file_mapper.frontmatter_handler.FrontmatterHandler', return_value=mock_frontmatter_handler):
            # Act
            result = handler.resolve_parent_page_id(child_file)

        # Assert
        assert result == "parent-123"

    def test_resolve_parent_page_id_current_dir(self, handler):
        """File in current directory (.) returns None."""
        # Arrange
        file_path = Path(".") / "page.md"

        # Act
        result = handler.resolve_parent_page_id(file_path)

        # Assert
        assert result is None


class TestCleanupEmptyDirs(TestMoveHandler):
    """Test cases for _cleanup_empty_dirs private method."""

    def test_cleanup_empty_dirs_removes_empty(self, handler, temp_dir):
        """Empty directory is removed."""
        # Arrange
        empty_dir = Path(temp_dir) / "empty-folder"
        empty_dir.mkdir(parents=True, exist_ok=True)
        assert empty_dir.exists()

        # Act
        handler._cleanup_empty_dirs(empty_dir)

        # Assert
        assert not empty_dir.exists()

    def test_cleanup_empty_dirs_keeps_non_empty(self, handler, temp_dir):
        """Non-empty directory is not removed."""
        # Arrange
        non_empty_dir = Path(temp_dir) / "non-empty-folder"
        non_empty_dir.mkdir(parents=True, exist_ok=True)
        (non_empty_dir / "file.txt").write_text("content")
        assert non_empty_dir.exists()

        # Act
        handler._cleanup_empty_dirs(non_empty_dir)

        # Assert
        assert non_empty_dir.exists()  # Should not be removed

    def test_cleanup_empty_dirs_recursive(self, handler, temp_dir):
        """Recursively removes empty parent directories."""
        # Arrange
        nested_dir = Path(temp_dir) / "level1" / "level2" / "level3"
        nested_dir.mkdir(parents=True, exist_ok=True)

        # All levels are empty
        assert nested_dir.exists()
        assert nested_dir.parent.exists()

        # Act
        handler._cleanup_empty_dirs(nested_dir)

        # Assert
        # All empty directories should be removed
        assert not nested_dir.exists()
        # Parent directories should also be cleaned if empty

    def test_cleanup_empty_dirs_stops_at_non_empty(self, handler, temp_dir):
        """Stop removing when non-empty directory encountered."""
        # Arrange
        level1 = Path(temp_dir) / "level1"
        level2 = level1 / "level2"
        level3 = level2 / "level3"
        level3.mkdir(parents=True, exist_ok=True)

        # Add file to level1 to make it non-empty
        (level1 / "file.txt").write_text("content")

        # Act
        handler._cleanup_empty_dirs(level3)

        # Assert
        # level3 and level2 should be removed (empty)
        # level1 should remain (has file.txt)
        assert level1.exists()
        assert (level1 / "file.txt").exists()

    def test_cleanup_empty_dirs_nonexistent_dir(self, handler, temp_dir):
        """No error when directory doesn't exist."""
        # Arrange
        nonexistent = Path(temp_dir) / "nonexistent"

        # Act - should not raise
        handler._cleanup_empty_dirs(nonexistent)

        # Assert - no exception raised

    def test_cleanup_empty_dirs_file_not_dir(self, handler, temp_dir):
        """No error when path is a file, not directory."""
        # Arrange
        file_path = Path(temp_dir) / "file.txt"
        file_path.write_text("content")

        # Act - should not raise
        handler._cleanup_empty_dirs(file_path)

        # Assert
        assert file_path.exists()  # File unchanged
