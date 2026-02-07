"""Unit tests for cli.deletion_handler module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.cli.deletion_handler import DeletionHandler
from src.cli.errors import CLIError
from src.cli.models import DeletionInfo


class TestDeletionHandler:
    """Test cases for DeletionHandler."""

    @pytest.fixture
    def mock_page_operations(self):
        """Create mock PageOperations instance."""
        mock = Mock()
        mock.delete_page = Mock()
        return mock

    @pytest.fixture
    def mock_file_mapper(self):
        """Create mock FileMapper instance."""
        return Mock()

    @pytest.fixture
    def handler(self, mock_page_operations, mock_file_mapper):
        """Create DeletionHandler instance with mocks."""
        return DeletionHandler(
            page_operations=mock_page_operations,
            file_mapper=mock_file_mapper
        )

    @pytest.fixture
    def handler_no_deps(self):
        """Create DeletionHandler instance without dependencies."""
        return DeletionHandler()

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


class TestDeleteLocalFiles(TestDeletionHandler):
    """Test cases for delete_local_files method."""

    def test_delete_single_file_success(self, handler, temp_file):
        """Successfully delete a single local file."""
        # Arrange
        deletion = DeletionInfo(
            page_id="123",
            title="Test Page",
            local_path=Path(temp_file),
            direction="confluence_to_local"
        )

        # Act
        result = handler.delete_local_files([deletion], dryrun=False)

        # Assert
        assert result == ["123"]
        assert not os.path.exists(temp_file)

    def test_delete_multiple_files_success(self, handler):
        """Successfully delete multiple local files."""
        # Arrange
        temp_files = []
        deletions = []

        for i in range(3):
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                f.write(f"Test content {i}")
                temp_files.append(f.name)
                deletions.append(DeletionInfo(
                    page_id=str(100 + i),
                    title=f"Test Page {i}",
                    local_path=Path(f.name),
                    direction="confluence_to_local"
                ))

        try:
            # Act
            result = handler.delete_local_files(deletions, dryrun=False)

            # Assert
            assert len(result) == 3
            assert "100" in result
            assert "101" in result
            assert "102" in result
            for temp_file in temp_files:
                assert not os.path.exists(temp_file)
        finally:
            # Cleanup any remaining files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

    def test_delete_dryrun_mode(self, handler, temp_file):
        """Dry run mode should not delete files."""
        # Arrange
        deletion = DeletionInfo(
            page_id="123",
            title="Test Page",
            local_path=Path(temp_file),
            direction="confluence_to_local"
        )

        # Act
        result = handler.delete_local_files([deletion], dryrun=True)

        # Assert
        assert result == []
        assert os.path.exists(temp_file)  # File still exists

    def test_delete_empty_list(self, handler):
        """Empty deletion list should return empty result."""
        # Act
        result = handler.delete_local_files([], dryrun=False)

        # Assert
        assert result == []

    def test_delete_missing_local_path(self, handler, temp_file):
        """Skip deletion when local_path is None."""
        # Arrange
        deletion = DeletionInfo(
            page_id="123",
            title="Test Page",
            local_path=None,
            direction="confluence_to_local"
        )

        # Act
        result = handler.delete_local_files([deletion], dryrun=False)

        # Assert
        assert result == []

    def test_delete_non_existent_file(self, handler):
        """Skip deletion when file does not exist."""
        # Arrange
        deletion = DeletionInfo(
            page_id="123",
            title="Test Page",
            local_path=Path("/nonexistent/file.md"),
            direction="confluence_to_local"
        )

        # Act
        result = handler.delete_local_files([deletion], dryrun=False)

        # Assert
        assert result == []

    def test_delete_wrong_direction(self, handler, temp_file):
        """Skip deletion when direction is wrong."""
        # Arrange
        deletion = DeletionInfo(
            page_id="123",
            title="Test Page",
            local_path=Path(temp_file),
            direction="local_to_confluence"  # Wrong direction
        )

        # Act
        result = handler.delete_local_files([deletion], dryrun=False)

        # Assert
        assert result == []
        assert os.path.exists(temp_file)  # File still exists

    def test_delete_partial_failure(self, handler, temp_file):
        """Continue processing after file deletion failure."""
        # Arrange
        temp_file2 = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                f.write("Test content 2")
                temp_file2 = f.name

            deletions = [
                DeletionInfo(
                    page_id="123",
                    title="Test Page 1",
                    local_path=Path("/nonexistent/file.md"),  # This will fail
                    direction="confluence_to_local"
                ),
                DeletionInfo(
                    page_id="456",
                    title="Test Page 2",
                    local_path=Path(temp_file),
                    direction="confluence_to_local"
                ),
                DeletionInfo(
                    page_id="789",
                    title="Test Page 3",
                    local_path=Path(temp_file2),
                    direction="confluence_to_local"
                )
            ]

            # Act
            result = handler.delete_local_files(deletions, dryrun=False)

            # Assert
            assert len(result) == 2
            assert "456" in result
            assert "789" in result
            assert not os.path.exists(temp_file)
            assert not os.path.exists(temp_file2)
        finally:
            if temp_file2 and os.path.exists(temp_file2):
                os.unlink(temp_file2)

    def test_delete_os_error_handling(self, handler, temp_file):
        """Handle OSError gracefully and continue processing."""
        # Arrange
        temp_file2 = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                f.write("Test content 2")
                temp_file2 = f.name

            deletions = [
                DeletionInfo(
                    page_id="123",
                    title="Test Page 1",
                    local_path=Path(temp_file),
                    direction="confluence_to_local"
                ),
                DeletionInfo(
                    page_id="456",
                    title="Test Page 2",
                    local_path=Path(temp_file2),
                    direction="confluence_to_local"
                )
            ]

            # Mock os.unlink to raise OSError for first file
            original_unlink = os.unlink
            call_count = [0]

            def mock_unlink(path):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise OSError("Permission denied")
                return original_unlink(path)

            with patch('os.unlink', side_effect=mock_unlink):
                # Act
                result = handler.delete_local_files(deletions, dryrun=False)

            # Assert
            assert len(result) == 1
            assert "456" in result
            assert os.path.exists(temp_file)  # First file still exists
            assert not os.path.exists(temp_file2)  # Second file deleted
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
            if temp_file2 and os.path.exists(temp_file2):
                os.unlink(temp_file2)


class TestDeleteConfluencePages(TestDeletionHandler):
    """Test cases for delete_confluence_pages method."""

    def test_delete_single_page_success(self, handler, mock_page_operations):
        """Successfully delete a single Confluence page."""
        # Arrange
        deletion = DeletionInfo(
            page_id="123",
            title="Test Page",
            local_path=Path("docs/test.md"),
            direction="local_to_confluence"
        )

        # Act
        result = handler.delete_confluence_pages([deletion], dryrun=False)

        # Assert
        assert result == ["123"]
        mock_page_operations.delete_page.assert_called_once_with("123")

    def test_delete_multiple_pages_success(self, handler, mock_page_operations):
        """Successfully delete multiple Confluence pages."""
        # Arrange
        deletions = [
            DeletionInfo(
                page_id="123",
                title="Test Page 1",
                local_path=Path("docs/test1.md"),
                direction="local_to_confluence"
            ),
            DeletionInfo(
                page_id="456",
                title="Test Page 2",
                local_path=Path("docs/test2.md"),
                direction="local_to_confluence"
            )
        ]

        # Act
        result = handler.delete_confluence_pages(deletions, dryrun=False)

        # Assert
        assert len(result) == 2
        assert "123" in result
        assert "456" in result
        assert mock_page_operations.delete_page.call_count == 2

    def test_delete_dryrun_mode(self, handler, mock_page_operations):
        """Dry run mode should not delete pages."""
        # Arrange
        deletion = DeletionInfo(
            page_id="123",
            title="Test Page",
            local_path=Path("docs/test.md"),
            direction="local_to_confluence"
        )

        # Act
        result = handler.delete_confluence_pages([deletion], dryrun=True)

        # Assert
        assert result == []
        mock_page_operations.delete_page.assert_not_called()

    def test_delete_empty_list(self, handler, mock_page_operations):
        """Empty deletion list should return empty result."""
        # Act
        result = handler.delete_confluence_pages([], dryrun=False)

        # Assert
        assert result == []
        mock_page_operations.delete_page.assert_not_called()

    def test_delete_missing_page_id(self, handler, mock_page_operations):
        """Skip deletion when page_id is None."""
        # Arrange
        deletion = DeletionInfo(
            page_id=None,
            title="Test Page",
            local_path=Path("docs/test.md"),
            direction="local_to_confluence"
        )

        # Act
        result = handler.delete_confluence_pages([deletion], dryrun=False)

        # Assert
        assert result == []
        mock_page_operations.delete_page.assert_not_called()

    def test_delete_wrong_direction(self, handler, mock_page_operations):
        """Skip deletion when direction is wrong."""
        # Arrange
        deletion = DeletionInfo(
            page_id="123",
            title="Test Page",
            local_path=Path("docs/test.md"),
            direction="confluence_to_local"  # Wrong direction
        )

        # Act
        result = handler.delete_confluence_pages([deletion], dryrun=False)

        # Assert
        assert result == []
        mock_page_operations.delete_page.assert_not_called()

    def test_delete_api_error_handling(self, handler, mock_page_operations):
        """Handle API error gracefully and continue processing."""
        # Arrange
        deletions = [
            DeletionInfo(
                page_id="123",
                title="Test Page 1",
                local_path=Path("docs/test1.md"),
                direction="local_to_confluence"
            ),
            DeletionInfo(
                page_id="456",
                title="Test Page 2",
                local_path=Path("docs/test2.md"),
                direction="local_to_confluence"
            ),
            DeletionInfo(
                page_id="789",
                title="Test Page 3",
                local_path=Path("docs/test3.md"),
                direction="local_to_confluence"
            )
        ]

        # Mock delete_page to raise exception for second page
        def mock_delete(page_id):
            if page_id == "456":
                raise Exception("API error")

        mock_page_operations.delete_page.side_effect = mock_delete

        # Act
        result = handler.delete_confluence_pages(deletions, dryrun=False)

        # Assert
        assert len(result) == 2
        assert "123" in result
        assert "789" in result
        assert "456" not in result
        assert mock_page_operations.delete_page.call_count == 3

    def test_delete_partial_failure(self, handler, mock_page_operations):
        """Continue processing after page deletion failure."""
        # Arrange
        deletions = [
            DeletionInfo(
                page_id=None,  # This will be skipped
                title="Test Page 1",
                local_path=Path("docs/test1.md"),
                direction="local_to_confluence"
            ),
            DeletionInfo(
                page_id="456",
                title="Test Page 2",
                local_path=Path("docs/test2.md"),
                direction="local_to_confluence"
            ),
            DeletionInfo(
                page_id="789",
                title="Test Page 3",
                local_path=Path("docs/test3.md"),
                direction="local_to_confluence"
            )
        ]

        # Act
        result = handler.delete_confluence_pages(deletions, dryrun=False)

        # Assert
        assert len(result) == 2
        assert "456" in result
        assert "789" in result
        assert mock_page_operations.delete_page.call_count == 2

    def test_delete_no_page_operations(self, handler_no_deps):
        """Raise CLIError when page_operations is not provided."""
        # Arrange
        deletion = DeletionInfo(
            page_id="123",
            title="Test Page",
            local_path=Path("docs/test.md"),
            direction="local_to_confluence"
        )

        # Act & Assert
        with pytest.raises(CLIError, match="Cannot delete Confluence pages"):
            handler_no_deps.delete_confluence_pages([deletion], dryrun=False)

    def test_delete_no_page_operations_dryrun_ok(self, handler_no_deps):
        """Dry run should work without page_operations."""
        # Arrange
        deletion = DeletionInfo(
            page_id="123",
            title="Test Page",
            local_path=Path("docs/test.md"),
            direction="local_to_confluence"
        )

        # Act
        result = handler_no_deps.delete_confluence_pages([deletion], dryrun=True)

        # Assert
        assert result == []  # No error, just empty result


class TestInitialization(TestDeletionHandler):
    """Test cases for DeletionHandler initialization."""

    def test_init_with_dependencies(self, mock_page_operations, mock_file_mapper):
        """Initialize with page_operations and file_mapper."""
        # Act
        handler = DeletionHandler(
            page_operations=mock_page_operations,
            file_mapper=mock_file_mapper
        )

        # Assert
        assert handler.page_operations == mock_page_operations
        assert handler.file_mapper == mock_file_mapper

    def test_init_without_dependencies(self):
        """Initialize without dependencies."""
        # Act
        handler = DeletionHandler()

        # Assert
        assert handler.page_operations is None
        assert handler.file_mapper is None

    def test_init_partial_dependencies(self, mock_page_operations):
        """Initialize with only some dependencies."""
        # Act
        handler = DeletionHandler(page_operations=mock_page_operations)

        # Assert
        assert handler.page_operations == mock_page_operations
        assert handler.file_mapper is None
