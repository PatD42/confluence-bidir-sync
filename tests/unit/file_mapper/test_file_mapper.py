"""Unit tests for file_mapper orchestration module."""

import os
import tempfile
import shutil
import pytest
from unittest.mock import Mock, patch, call, mock_open
from datetime import datetime

from src.file_mapper.file_mapper import FileMapper, CONFLICT_MARKER_PATTERN
from src.file_mapper.models import PageNode, LocalPage, SpaceConfig, SyncConfig
from src.file_mapper.errors import FilesystemError, ConfigError
from src.confluence_client.errors import PageNotFoundError, InvalidCredentialsError


def create_mock_auth():
    """Create a mock authenticator."""
    return Mock()


def create_page_node(page_id, title, space_key='TEST', children=None, parent_id=None):
    """Create a PageNode for testing."""
    return PageNode(
        page_id=page_id,
        title=title,
        parent_id=parent_id,
        last_modified='2024-01-01T00:00:00.000Z',
        space_key=space_key,
        children=children or []
    )


def create_local_page(file_path, page_id=None, content='# Test'):
    """Create a LocalPage for testing.

    Note: LocalPage now uses simplified model with only file_path, page_id, content.
    Title is derived from H1 heading or filename. Space key and sync metadata
    are tracked globally in state.yaml.
    """
    return LocalPage(
        file_path=file_path,
        page_id=page_id,
        content=content
    )


def create_space_config(space_key='TEST', parent_page_id='123', local_path='./test', exclude_page_ids=None):
    """Create a SpaceConfig for testing."""
    return SpaceConfig(
        space_key=space_key,
        parent_page_id=parent_page_id,
        local_path=local_path,
        exclude_page_ids=exclude_page_ids or []
    )


def create_sync_config(spaces=None, page_limit=100, force_pull=False, force_push=False, temp_dir='.test-temp', get_baseline=None, last_synced=None):
    """Create a SyncConfig for testing.

    Args:
        spaces: List of SpaceConfig objects
        page_limit: Maximum pages per level
        force_pull: Force sync from Confluence
        force_push: Force sync to Confluence
        temp_dir: Temporary directory for atomic operations
        get_baseline: Callback to retrieve baseline content for a page_id
        last_synced: ISO 8601 timestamp of last sync
    """
    return SyncConfig(
        spaces=spaces or [],
        page_limit=page_limit,
        force_pull=force_pull,
        force_push=force_push,
        temp_dir=temp_dir,
        get_baseline=get_baseline,
        last_synced=last_synced
    )


class TestFileMapperInit:
    """Test cases for FileMapper initialization."""

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    @patch('src.file_mapper.file_mapper.Authenticator')
    def test_init_creates_authenticator_when_none_provided(self, mock_auth_class, mock_api_class, mock_hierarchy_class):
        """__init__ should create Authenticator when none provided."""
        mock_auth = Mock()
        mock_auth_class.return_value = mock_auth

        mapper = FileMapper()

        # Should create Authenticator
        mock_auth_class.assert_called_once()

        # Should create APIWrapper with authenticator
        mock_api_class.assert_called_once_with(mock_auth)

        # Should create HierarchyBuilder with authenticator
        mock_hierarchy_class.assert_called_once_with(mock_auth)

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_init_uses_provided_authenticator(self, mock_api_class, mock_hierarchy_class):
        """__init__ should use provided Authenticator."""
        mock_auth = create_mock_auth()

        mapper = FileMapper(mock_auth)

        # Should use provided authenticator
        mock_api_class.assert_called_once_with(mock_auth)
        mock_hierarchy_class.assert_called_once_with(mock_auth)


class TestFileMapperSyncSpaces:
    """Test cases for FileMapper.sync_spaces() method."""

    @patch.object(FileMapper, '_sync_space')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_sync_spaces_single_space(self, mock_api_class, mock_hierarchy_class, mock_sync_space):
        """sync_spaces should sync single space."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        space_config = create_space_config()
        sync_config = create_sync_config(spaces=[space_config])

        mapper.sync_spaces(sync_config)

        # Should call _sync_space once
        mock_sync_space.assert_called_once_with(space_config, sync_config)

    @patch.object(FileMapper, '_sync_space')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_sync_spaces_multiple_spaces(self, mock_api_class, mock_hierarchy_class, mock_sync_space):
        """sync_spaces should sync multiple spaces in sequence."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        space1 = create_space_config(space_key='SPACE1', parent_page_id='123')
        space2 = create_space_config(space_key='SPACE2', parent_page_id='456')
        sync_config = create_sync_config(spaces=[space1, space2])

        mapper.sync_spaces(sync_config)

        # Should call _sync_space for each space
        assert mock_sync_space.call_count == 2
        mock_sync_space.assert_any_call(space1, sync_config)
        mock_sync_space.assert_any_call(space2, sync_config)

    @patch.object(FileMapper, '_sync_space')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_sync_spaces_empty_spaces_list(self, mock_api_class, mock_hierarchy_class, mock_sync_space):
        """sync_spaces should handle empty spaces list."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        sync_config = create_sync_config(spaces=[])

        mapper.sync_spaces(sync_config)

        # Should not call _sync_space
        mock_sync_space.assert_not_called()


class TestFileMapperDetectSyncDirection:
    """Test cases for FileMapper._detect_sync_direction() method."""

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_detect_sync_direction_both_empty(self, mock_api_class, mock_hierarchy_class):
        """_detect_sync_direction should return 'pull' when both empty."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Empty hierarchy (no children)
        hierarchy = create_page_node('123', 'Root', children=[])
        local_pages = {}

        direction = mapper._detect_sync_direction(hierarchy, local_pages, False, False)

        assert direction == 'pull'

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_detect_sync_direction_local_empty(self, mock_api_class, mock_hierarchy_class):
        """_detect_sync_direction should return 'pull' when local empty."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Hierarchy with children
        child = create_page_node('456', 'Child', parent_id='123')
        hierarchy = create_page_node('123', 'Root', children=[child])
        local_pages = {}

        direction = mapper._detect_sync_direction(hierarchy, local_pages, False, False)

        assert direction == 'pull'

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_detect_sync_direction_confluence_empty(self, mock_api_class, mock_hierarchy_class):
        """_detect_sync_direction should return 'push' when Confluence empty."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Empty hierarchy (no children)
        hierarchy = create_page_node('123', 'Root', children=[])
        local_pages = {
            'test.md': create_local_page('test.md', '456', '# Test Page')
        }

        direction = mapper._detect_sync_direction(hierarchy, local_pages, False, False)

        assert direction == 'push'

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_detect_sync_direction_both_have_content_force_pull(self, mock_api_class, mock_hierarchy_class):
        """_detect_sync_direction should return 'pull' when both have content and force_pull=True."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        child = create_page_node('456', 'Child', parent_id='123')
        hierarchy = create_page_node('123', 'Root', children=[child])
        local_pages = {
            'test.md': create_local_page('test.md', '789', '# Local Page')
        }

        direction = mapper._detect_sync_direction(hierarchy, local_pages, force_pull=True, force_push=False)

        assert direction == 'pull'

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_detect_sync_direction_both_have_content_force_push(self, mock_api_class, mock_hierarchy_class):
        """_detect_sync_direction should return 'push' when both have content and force_push=True."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        child = create_page_node('456', 'Child', parent_id='123')
        hierarchy = create_page_node('123', 'Root', children=[child])
        local_pages = {
            'test.md': create_local_page('test.md', '789', '# Local Page')
        }

        direction = mapper._detect_sync_direction(hierarchy, local_pages, force_pull=False, force_push=True)

        assert direction == 'push'

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_detect_sync_direction_both_have_content_no_force(self, mock_api_class, mock_hierarchy_class):
        """_detect_sync_direction should return 'bidirectional' when both have content and no force flag."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        child = create_page_node('456', 'Child', parent_id='123')
        hierarchy = create_page_node('123', 'Root', children=[child])
        local_pages = {
            'test.md': create_local_page('test.md', '789', '# Local Page')
        }

        direction = mapper._detect_sync_direction(hierarchy, local_pages, force_pull=False, force_push=False)

        assert direction == 'bidirectional'


class TestFileMapperReadLocalFiles:
    """Test cases for FileMapper._read_local_files() method."""

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_read_local_files_nonexistent_directory(self, mock_api_class, mock_hierarchy_class):
        """_read_local_files should return empty dict for nonexistent directory."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        result = mapper._read_local_files('/nonexistent/path')

        assert result == {}

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_read_local_files_raises_error_for_file_not_directory(self, mock_api_class, mock_hierarchy_class, tmp_path):
        """_read_local_files should raise FilesystemError if path is a file."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Create a file instead of directory
        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        with pytest.raises(FilesystemError) as exc_info:
            mapper._read_local_files(str(file_path))

        assert exc_info.value.file_path == str(file_path)
        assert exc_info.value.operation == 'read'
        assert 'not a directory' in exc_info.value.reason.lower()

    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_read_local_files_single_markdown_file(self, mock_api_class, mock_hierarchy_class, mock_frontmatter, tmp_path):
        """_read_local_files should parse single markdown file."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Create markdown file
        md_file = tmp_path / "test.md"
        md_content = "---\npage_id: '123'\ntitle: Test\n---\n# Test"
        md_file.write_text(md_content)

        # Mock frontmatter parsing
        expected_page = create_local_page(str(md_file), '123', '# Test')
        mock_frontmatter.parse.return_value = expected_page

        result = mapper._read_local_files(str(tmp_path))

        assert len(result) == 1
        assert str(md_file) in result
        assert result[str(md_file)] == expected_page
        mock_frontmatter.parse.assert_called_once_with(str(md_file), md_content)

    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_read_local_files_multiple_markdown_files(self, mock_api_class, mock_hierarchy_class, mock_frontmatter, tmp_path):
        """_read_local_files should parse multiple markdown files."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Create multiple markdown files
        md_file1 = tmp_path / "test1.md"
        md_file2 = tmp_path / "test2.md"
        md_file1.write_text("# Test 1")
        md_file2.write_text("# Test 2")

        # Mock frontmatter parsing
        page1 = create_local_page(str(md_file1), '123', '# Test 1')
        page2 = create_local_page(str(md_file2), '456', '# Test 2')
        mock_frontmatter.parse.side_effect = [page1, page2]

        result = mapper._read_local_files(str(tmp_path))

        assert len(result) == 2
        assert str(md_file1) in result
        assert str(md_file2) in result

    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_read_local_files_nested_directories(self, mock_api_class, mock_hierarchy_class, mock_frontmatter, tmp_path):
        """_read_local_files should recursively scan nested directories."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Create nested structure
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        md_file1 = tmp_path / "root.md"
        md_file2 = subdir / "nested.md"
        md_file1.write_text("# Root")
        md_file2.write_text("# Nested")

        # Mock frontmatter parsing
        page1 = create_local_page(str(md_file1), '123', '# Root')
        page2 = create_local_page(str(md_file2), '456', '# Nested')
        mock_frontmatter.parse.side_effect = [page1, page2]

        result = mapper._read_local_files(str(tmp_path))

        assert len(result) == 2
        assert str(md_file1) in result
        assert str(md_file2) in result

    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_read_local_files_ignores_non_markdown_files(self, mock_api_class, mock_hierarchy_class, mock_frontmatter, tmp_path):
        """_read_local_files should ignore non-.md files."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Create markdown and non-markdown files
        md_file = tmp_path / "test.md"
        txt_file = tmp_path / "test.txt"
        md_file.write_text("# Test")
        txt_file.write_text("Not markdown")

        page = create_local_page(str(md_file), '123', '# Test')
        mock_frontmatter.parse.return_value = page

        result = mapper._read_local_files(str(tmp_path))

        # Should only include .md file
        assert len(result) == 1
        assert str(md_file) in result
        assert str(txt_file) not in result

    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_read_local_files_skips_invalid_frontmatter(self, mock_api_class, mock_hierarchy_class, mock_frontmatter, tmp_path):
        """_read_local_files should skip files with invalid frontmatter and continue."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Create two files, one valid, one invalid
        md_file1 = tmp_path / "valid.md"
        md_file2 = tmp_path / "invalid.md"
        md_file1.write_text("# Valid")
        md_file2.write_text("# Invalid")

        page1 = create_local_page(str(md_file1), '123', '# Valid')
        mock_frontmatter.parse.side_effect = [page1, Exception("Invalid frontmatter")]

        # Should not raise exception, just log and skip
        result = mapper._read_local_files(str(tmp_path))

        # Should only include valid file
        assert len(result) == 1
        assert str(md_file1) in result
        assert str(md_file2) not in result

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_read_local_files_raises_error_on_permission_denied(self, mock_api_class, mock_hierarchy_class):
        """_read_local_files should raise FilesystemError on permission denied."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        test_path = '/some/path'
        # Mock the path checks first, then os.walk raises PermissionError
        with patch('os.path.exists', return_value=True):
            with patch('os.path.isdir', return_value=True):
                with patch('os.walk', side_effect=PermissionError("Permission denied")):
                    with pytest.raises(FilesystemError) as exc_info:
                        mapper._read_local_files(test_path)

                    assert exc_info.value.file_path == test_path
                    assert exc_info.value.operation == 'read'
                    assert 'Permission denied' in exc_info.value.reason


class TestFileMapperBuildFileListFromHierarchy:
    """Test cases for FileMapper._build_file_list_from_hierarchy() method."""

    @patch('src.file_mapper.file_mapper.FilesafeConverter')
    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_build_file_list_single_page(self, mock_api_class, mock_hierarchy_class, mock_frontmatter, mock_converter):
        """_build_file_list_from_hierarchy should create file for single page."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        node = create_page_node('123', 'Test Page')
        files_to_write = []
        space_config = create_space_config(local_path='/test')
        page_ids_filter = {'123'}  # Include this page

        mock_converter.title_to_filename.return_value = 'Test-Page.md'
        mock_frontmatter.generate.return_value = '---\npage_id: "123"\n---\n# Test Page\n\n'

        mapper._build_file_list_from_hierarchy(node, '/test', files_to_write, space_config, page_ids_filter)

        assert len(files_to_write) == 1
        assert files_to_write[0][0] == '/test/Test-Page.md'
        assert 'page_id: "123"' in files_to_write[0][1]

    @patch('src.file_mapper.file_mapper.FilesafeConverter')
    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_build_file_list_with_children(self, mock_api_class, mock_hierarchy_class, mock_frontmatter, mock_converter):
        """_build_file_list_from_hierarchy should create files for parent and children."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        child = create_page_node('456', 'Child Page', parent_id='123')
        parent = create_page_node('123', 'Parent Page', children=[child])
        files_to_write = []
        space_config = create_space_config(local_path='/test')
        page_ids_filter = {'123', '456'}  # Include both pages

        mock_converter.title_to_filename.side_effect = ['Parent-Page.md', 'Child-Page.md']
        mock_frontmatter.generate.side_effect = [
            '---\npage_id: "123"\n---\n# Parent Page\n\n',
            '---\npage_id: "456"\n---\n# Child Page\n\n'
        ]

        mapper._build_file_list_from_hierarchy(parent, '/test', files_to_write, space_config, page_ids_filter)

        assert len(files_to_write) == 2
        assert files_to_write[0][0] == '/test/Parent-Page.md'
        assert files_to_write[1][0] == '/test/Parent-Page/Child-Page.md'

    @patch('src.file_mapper.file_mapper.FilesafeConverter')
    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_build_file_list_nested_hierarchy(self, mock_api_class, mock_hierarchy_class, mock_frontmatter, mock_converter):
        """_build_file_list_from_hierarchy should handle multi-level nesting."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        grandchild = create_page_node('789', 'Grandchild', parent_id='456')
        child = create_page_node('456', 'Child', parent_id='123', children=[grandchild])
        parent = create_page_node('123', 'Parent', children=[child])
        files_to_write = []
        space_config = create_space_config(local_path='/test')
        page_ids_filter = {'123', '456', '789'}  # Include all pages

        mock_converter.title_to_filename.side_effect = ['Parent.md', 'Child.md', 'Grandchild.md']
        mock_frontmatter.generate.return_value = '---\n---\n'

        mapper._build_file_list_from_hierarchy(parent, '/test', files_to_write, space_config, page_ids_filter)

        assert len(files_to_write) == 3
        assert files_to_write[0][0] == '/test/Parent.md'
        assert files_to_write[1][0] == '/test/Parent/Child.md'
        assert files_to_write[2][0] == '/test/Parent/Child/Grandchild.md'


class TestFileMapperWriteFilesAtomic:
    """Test cases for FileMapper._write_files_atomic() method."""

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_write_files_atomic_empty_list(self, mock_api_class, mock_hierarchy_class):
        """_write_files_atomic should return early for empty list."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Should not raise any errors
        mapper._write_files_atomic([], '/tmp/test')

    @patch('src.file_mapper.file_mapper.shutil')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_write_files_atomic_success(self, mock_api_class, mock_hierarchy_class, mock_shutil, tmp_path):
        """_write_files_atomic should write files and clean up temp directory."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        final_dir = tmp_path / "final"
        final_dir.mkdir()

        files_to_write = [
            (str(final_dir / 'test1.md'), 'Content 1'),
            (str(final_dir / 'test2.md'), 'Content 2')
        ]

        # Mock shutil.move to succeed
        mock_shutil.move.return_value = None

        mapper._write_files_atomic(files_to_write, str(temp_dir))

        # Should call shutil.move for each file
        assert mock_shutil.move.call_count == 2

        # Should call shutil.rmtree to clean up temp directory
        mock_shutil.rmtree.assert_called_once_with(str(temp_dir))

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_write_files_atomic_handles_same_basename_different_dirs(self, mock_api_class, mock_hierarchy_class, tmp_path):
        """_write_files_atomic should handle files with same basename in different directories.

        This tests the collision scenario where two files like:
        - docs/Architecture/README.md
        - docs/Product/README.md
        should not overwrite each other in the temp directory.
        """
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        temp_dir = tmp_path / "temp"
        dir1 = tmp_path / "docs" / "Architecture"
        dir2 = tmp_path / "docs" / "Product"
        dir1.mkdir(parents=True)
        dir2.mkdir(parents=True)

        # Same basename, different directories
        files_to_write = [
            (str(dir1 / 'README.md'), 'Architecture content'),
            (str(dir2 / 'README.md'), 'Product content')
        ]

        mapper._write_files_atomic(files_to_write, str(temp_dir))

        # Both files should exist with correct content
        assert (dir1 / 'README.md').exists()
        assert (dir2 / 'README.md').exists()
        assert (dir1 / 'README.md').read_text() == 'Architecture content'
        assert (dir2 / 'README.md').read_text() == 'Product content'

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_write_files_atomic_creates_temp_directory(self, mock_api_class, mock_hierarchy_class, tmp_path):
        """_write_files_atomic should create temp directory if it doesn't exist."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        temp_dir = tmp_path / "temp"
        final_dir = tmp_path / "final"
        final_dir.mkdir()

        files_to_write = [(str(final_dir / 'test.md'), 'Content')]

        # Mock shutil to prevent cleanup
        with patch('shutil.move') as mock_move:
            with patch('shutil.rmtree') as mock_rmtree:
                mapper._write_files_atomic(files_to_write, str(temp_dir))

        # Temp directory should have been created (before cleanup attempt)
        # Since we mocked rmtree, directory should still exist
        assert temp_dir.exists() or mock_rmtree.called

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_write_files_atomic_raises_error_on_temp_dir_creation_failure(self, mock_api_class, mock_hierarchy_class):
        """_write_files_atomic should raise FilesystemError if temp dir creation fails."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        files_to_write = [('/test/file.md', 'Content')]

        with patch('os.makedirs', side_effect=OSError("Cannot create directory")):
            with pytest.raises(FilesystemError) as exc_info:
                mapper._write_files_atomic(files_to_write, '/invalid/temp')

            assert exc_info.value.operation == 'create_directory'

    @patch.object(FileMapper, '_cleanup_temp_files')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_write_files_atomic_rolls_back_on_phase1_failure(self, mock_api_class, mock_hierarchy_class, mock_cleanup, tmp_path):
        """_write_files_atomic should rollback on phase 1 failure."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        files_to_write = [('/test/file.md', 'Content')]

        # Mock file write to fail
        with patch('builtins.open', side_effect=OSError("Write failed")):
            with pytest.raises(FilesystemError) as exc_info:
                mapper._write_files_atomic(files_to_write, str(temp_dir))

            assert 'phase 1 failed' in str(exc_info.value).lower()
            # Should call cleanup
            mock_cleanup.assert_called_once()

    @patch.object(FileMapper, '_cleanup_temp_files')
    @patch('src.file_mapper.file_mapper.shutil')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_write_files_atomic_rolls_back_on_phase2_failure(self, mock_api_class, mock_hierarchy_class, mock_shutil, mock_cleanup, tmp_path):
        """_write_files_atomic should rollback on phase 2 failure."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        final_dir = tmp_path / "final"
        final_dir.mkdir()

        files_to_write = [(str(final_dir / 'test.md'), 'Content')]

        # Mock shutil.move to fail
        mock_shutil.move.side_effect = OSError("Move failed")

        with pytest.raises(FilesystemError) as exc_info:
            mapper._write_files_atomic(files_to_write, str(temp_dir))

        assert 'phase 2 failed' in str(exc_info.value).lower()
        # Should call cleanup
        mock_cleanup.assert_called_once()

    @patch('src.file_mapper.file_mapper.shutil')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_write_files_atomic_creates_final_directory_if_needed(self, mock_api_class, mock_hierarchy_class, mock_shutil, tmp_path):
        """_write_files_atomic should create final directory structure if needed."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        final_dir = tmp_path / "final" / "nested"  # Nested directory

        files_to_write = [(str(final_dir / 'test.md'), 'Content')]

        mock_shutil.move.return_value = None

        mapper._write_files_atomic(files_to_write, str(temp_dir))

        # Final directory should have been created
        assert final_dir.exists()


class TestFileMapperCleanupTempFiles:
    """Test cases for FileMapper._cleanup_temp_files() method."""

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_cleanup_temp_files_removes_existing_files(self, mock_api_class, mock_hierarchy_class, tmp_path):
        """_cleanup_temp_files should remove existing temporary files."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Create temp files
        temp_file1 = tmp_path / "temp1.md"
        temp_file2 = tmp_path / "temp2.md"
        temp_file1.write_text("Content 1")
        temp_file2.write_text("Content 2")

        temp_files = [
            (str(temp_file1), '/final/file1.md'),
            (str(temp_file2), '/final/file2.md')
        ]

        mapper._cleanup_temp_files(temp_files)

        # Files should be removed
        assert not temp_file1.exists()
        assert not temp_file2.exists()

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_cleanup_temp_files_handles_nonexistent_files(self, mock_api_class, mock_hierarchy_class):
        """_cleanup_temp_files should handle nonexistent files gracefully."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        temp_files = [
            ('/nonexistent/temp1.md', '/final/file1.md'),
            ('/nonexistent/temp2.md', '/final/file2.md')
        ]

        # Should not raise any errors
        mapper._cleanup_temp_files(temp_files)

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_cleanup_temp_files_logs_warning_on_error(self, mock_api_class, mock_hierarchy_class):
        """_cleanup_temp_files should log warning if file removal fails."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        temp_files = [('/test/temp.md', '/final/file.md')]

        with patch('os.path.exists', return_value=True):
            with patch('os.remove', side_effect=OSError("Cannot remove")):
                with patch('src.file_mapper.file_mapper.logger') as mock_logger:
                    mapper._cleanup_temp_files(temp_files)

                    # Should log warning
                    mock_logger.warning.assert_called()


class TestFileMapperPullFromConfluence:
    """Test cases for FileMapper._pull_from_confluence() method."""

    @patch.object(FileMapper, '_write_files_atomic')
    @patch.object(FileMapper, '_build_file_list_from_hierarchy')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_pull_from_confluence_builds_and_writes_files(self, mock_api_class, mock_hierarchy_class, mock_build_files, mock_write_atomic):
        """_pull_from_confluence should build file list and write atomically."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        hierarchy = create_page_node('123', 'Root')
        space_config = create_space_config(local_path='/test')
        sync_config = create_sync_config(temp_dir='/temp')
        page_ids_to_pull = {'123'}  # Required: explicit set of page IDs to pull

        mapper._pull_from_confluence(hierarchy, space_config, sync_config, page_ids_to_pull)

        # Should call _build_file_list_from_hierarchy with page_ids_filter
        mock_build_files.assert_called_once()
        call_args = mock_build_files.call_args
        assert call_args.kwargs['node'] == hierarchy or call_args[0][0] == hierarchy
        assert call_args.kwargs['parent_path'] == '/test' or call_args[0][1] == '/test'
        assert call_args.kwargs['page_ids_filter'] == page_ids_to_pull

        # Should call _write_files_atomic
        mock_write_atomic.assert_called_once()
        write_call_args = mock_write_atomic.call_args
        assert write_call_args.kwargs['temp_dir'] == '/temp' or write_call_args[0][1] == '/temp'


class TestFileMapperSyncSpace:
    """Test cases for FileMapper._sync_space() method."""

    @patch.object(FileMapper, '_pull_from_confluence')
    @patch.object(FileMapper, '_read_local_files')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_sync_space_pull_direction(self, mock_api_class, mock_hierarchy_class, mock_read_local, mock_pull):
        """_sync_space should pull from Confluence when direction is 'pull'."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Mock hierarchy builder
        hierarchy = create_page_node('123', 'Root')
        mapper._hierarchy_builder.build_hierarchy = Mock(return_value=hierarchy)

        # Mock read local files (empty)
        mock_read_local.return_value = {}

        space_config = create_space_config()
        sync_config = create_sync_config()

        mapper._sync_space(space_config, sync_config)

        # Should call pull from confluence
        mock_pull.assert_called_once()

    @patch.object(FileMapper, '_push_to_confluence')
    @patch.object(FileMapper, '_read_local_files')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_sync_space_push_direction(self, mock_api_class, mock_hierarchy_class, mock_read_local, mock_push):
        """_sync_space should push to Confluence when direction is 'push'."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Mock hierarchy builder (empty)
        hierarchy = create_page_node('123', 'Root', children=[])
        mapper._hierarchy_builder.build_hierarchy = Mock(return_value=hierarchy)

        # Mock read local files (has content)
        local_pages = {'test.md': create_local_page('test.md', '456', '# Test')}
        mock_read_local.return_value = local_pages

        space_config = create_space_config()
        sync_config = create_sync_config()

        mapper._sync_space(space_config, sync_config)

        # Should call push to confluence
        mock_push.assert_called_once()

    @patch.object(FileMapper, '_bidirectional_sync')
    @patch.object(FileMapper, '_read_local_files')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_sync_space_bidirectional_direction(self, mock_api_class, mock_hierarchy_class, mock_read_local, mock_bidirectional):
        """_sync_space should call bidirectional sync when both have content."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Mock hierarchy builder (has content)
        child = create_page_node('456', 'Child', parent_id='123')
        hierarchy = create_page_node('123', 'Root', children=[child])
        mapper._hierarchy_builder.build_hierarchy = Mock(return_value=hierarchy)

        # Mock read local files (has content)
        local_pages = {'test.md': create_local_page('test.md', '789', '# Test')}
        mock_read_local.return_value = local_pages

        space_config = create_space_config()
        sync_config = create_sync_config(force_pull=False, force_push=False)

        mapper._sync_space(space_config, sync_config)

        # Should call bidirectional sync
        mock_bidirectional.assert_called_once()


class TestFileMapperBuildLocalHierarchy:
    """Test cases for FileMapper._build_local_hierarchy() method."""

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_build_local_hierarchy_single_file(self, mock_api_class, mock_hierarchy_class):
        """_build_local_hierarchy should handle single top-level file."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        local_pages = {
            '/test/Page.md': create_local_page('/test/Page.md', '123', '# Page')
        }
        space_config = create_space_config(local_path='/test')

        hierarchy = mapper._build_local_hierarchy(local_pages, space_config)

        # Should have root with one file
        assert '__root__' in hierarchy
        assert '/test/Page.md' in hierarchy['__root__']

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_build_local_hierarchy_nested_files(self, mock_api_class, mock_hierarchy_class):
        """_build_local_hierarchy should handle nested directory structure."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        local_pages = {
            '/test/Parent.md': create_local_page('/test/Parent.md', '123', '# Parent'),
            '/test/Parent/Child.md': create_local_page('/test/Parent/Child.md', '456', '# Child'),
            '/test/Parent/Child/Grandchild.md': create_local_page('/test/Parent/Child/Grandchild.md', '789', '# Grandchild')
        }
        space_config = create_space_config(local_path='/test')

        hierarchy = mapper._build_local_hierarchy(local_pages, space_config)

        # Should have proper hierarchy
        assert '__root__' in hierarchy
        assert '/test/Parent.md' in hierarchy['__root__']
        assert 'Parent' in hierarchy
        assert '/test/Parent/Child.md' in hierarchy['Parent']
        assert 'Parent/Child' in hierarchy
        assert '/test/Parent/Child/Grandchild.md' in hierarchy['Parent/Child']

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_build_local_hierarchy_multiple_siblings(self, mock_api_class, mock_hierarchy_class):
        """_build_local_hierarchy should handle multiple sibling files."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        local_pages = {
            '/test/Page1.md': create_local_page('/test/Page1.md', '123', '# Page1'),
            '/test/Page2.md': create_local_page('/test/Page2.md', '456', '# Page2'),
            '/test/Page3.md': create_local_page('/test/Page3.md', '789', '# Page3')
        }
        space_config = create_space_config(local_path='/test')

        hierarchy = mapper._build_local_hierarchy(local_pages, space_config)

        # Should have all files under root
        assert '__root__' in hierarchy
        assert len(hierarchy['__root__']) == 3
        assert '/test/Page1.md' in hierarchy['__root__']
        assert '/test/Page2.md' in hierarchy['__root__']
        assert '/test/Page3.md' in hierarchy['__root__']


class TestFileMapperPushToConfluence:
    """Test cases for FileMapper._push_to_confluence() method."""

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_push_to_confluence_empty_local_pages(self, mock_api_class, mock_hierarchy_class):
        """_push_to_confluence should handle empty local pages gracefully."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        local_pages = {}
        space_config = create_space_config()
        sync_config = create_sync_config()

        with patch('src.file_mapper.file_mapper.logger') as mock_logger:
            mapper._push_to_confluence(local_pages, space_config, sync_config)

            # Should log debug about no pages to push
            mock_logger.debug.assert_any_call("No local pages to push")

    @patch('src.file_mapper.file_mapper.PageOperations')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_push_to_confluence_creates_page_creator(self, mock_api_class, mock_hierarchy_class, mock_page_ops_class):
        """_push_to_confluence should create PageOperations instance."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mapper = FileMapper(mock_auth)

        local_pages = {
            '/test/Page.md': create_local_page('/test/Page.md', None, '# Page')
        }
        space_config = create_space_config(local_path='/test')
        sync_config = create_sync_config()

        # Mock _build_local_hierarchy and _push_hierarchy_to_confluence
        with patch.object(mapper, '_build_local_hierarchy', return_value={'__root__': ['/test/Page.md']}):
            with patch.object(mapper, '_push_hierarchy_to_confluence'):
                with patch.object(mapper, '_write_files_atomic'):
                    mapper._push_to_confluence(local_pages, space_config, sync_config)

                    # Should create PageOperations
                    mock_page_ops_class.assert_called_once()

    @patch('src.file_mapper.file_mapper.PageOperations')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_push_to_confluence_calls_push_hierarchy(self, mock_api_class, mock_hierarchy_class, mock_page_ops_class):
        """_push_to_confluence should call _push_hierarchy_to_confluence."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        local_pages = {
            '/test/Page.md': create_local_page('/test/Page.md', None, '# Page')
        }
        space_config = create_space_config(local_path='/test')
        sync_config = create_sync_config()

        # Mock methods
        with patch.object(mapper, '_build_local_hierarchy', return_value={'__root__': ['/test/Page.md']}) as mock_build:
            with patch.object(mapper, '_push_hierarchy_to_confluence') as mock_push_hier:
                with patch.object(mapper, '_write_files_atomic'):
                    mapper._push_to_confluence(local_pages, space_config, sync_config)

                    # Should call _push_hierarchy_to_confluence
                    mock_push_hier.assert_called_once()

    @patch('src.file_mapper.file_mapper.PageOperations')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_push_to_confluence_updates_frontmatter(self, mock_api_class, mock_hierarchy_class, mock_page_ops_class):
        """_push_to_confluence should update frontmatter for created pages."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        local_pages = {
            '/test/Page.md': create_local_page('/test/Page.md', None, '# Page')
        }
        space_config = create_space_config(local_path='/test')
        sync_config = create_sync_config()

        # Mock methods
        files_to_update = [('/test/Page.md', 'updated content')]
        with patch.object(mapper, '_build_local_hierarchy', return_value={'__root__': ['/test/Page.md']}):
            with patch.object(mapper, '_push_hierarchy_to_confluence', side_effect=lambda **kwargs: kwargs['files_to_update'].extend(files_to_update)):
                with patch.object(mapper, '_write_files_atomic') as mock_write:
                    mapper._push_to_confluence(local_pages, space_config, sync_config)

                    # Should call _write_files_atomic with updated files
                    mock_write.assert_called_once()
                    call_args = mock_write.call_args
                    assert 'files_to_write' in call_args.kwargs
                    assert len(call_args.kwargs['files_to_write']) == 1


class TestFileMapperPushHierarchyToConfluence:
    """Test cases for FileMapper._push_hierarchy_to_confluence() method."""

    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_push_hierarchy_creates_new_page(self, mock_api_class, mock_hierarchy_class, mock_frontmatter_class, tmp_path):
        """_push_hierarchy_to_confluence should create new pages without page_id."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Create temp file
        test_file = tmp_path / "Page.md"
        test_file.write_text("---\ntitle: Test Page\n---\nContent")

        # Mock frontmatter parsing - page without page_id (new page)
        local_page = create_local_page(str(test_file), None, "Content")
        mock_frontmatter_class.parse.return_value = local_page
        mock_frontmatter_class.generate.return_value = "updated content"

        # Mock page operations
        mock_page_ops = Mock()
        from src.page_operations.models import CreateResult
        mock_page_ops.create_page.return_value = CreateResult(
            success=True,
            page_id="new-page-id",
            space_key="TEST",
            title="Test Page",
            version=1
        )

        hierarchy = {'__root__': [str(test_file)]}
        space_config = create_space_config()
        sync_config = create_sync_config()  # New pages don't need baseline
        files_to_update = []

        mapper._push_hierarchy_to_confluence(
            hierarchy=hierarchy,
            page_ops=mock_page_ops,
            space_config=space_config,
            sync_config=sync_config,
            files_to_update=files_to_update,
            parent_page_id='parent-123'
        )

        # Should create page
        mock_page_ops.create_page.assert_called_once()
        # Should update frontmatter
        assert len(files_to_update) == 1
        assert files_to_update[0][0] == str(test_file)

    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_push_hierarchy_skips_existing_page(self, mock_api_class, mock_hierarchy_class, mock_frontmatter_class, tmp_path):
        """_push_hierarchy_to_confluence should update pages with existing page_id."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Create temp file
        test_file = tmp_path / "Page.md"
        test_file.write_text("---\npage_id: existing-123\ntitle: Test Page\n---\nContent")

        # Mock frontmatter parsing - page already has page_id
        # Local content differs from baseline to trigger update
        local_page = create_local_page(str(test_file), 'existing-123', "Different Content")
        baseline_page = create_local_page(str(test_file), 'existing-123', "Original Content")

        # Use side_effect to return different values for local vs baseline parsing
        def mock_parse(file_path, content):
            # If parsing baseline content, return baseline_page
            if "Original Content" in content:
                return baseline_page
            return local_page

        mock_frontmatter_class.parse.side_effect = mock_parse

        # Mock page operations
        mock_page_ops = Mock()
        from src.page_operations.models import PageSnapshot, UpdateResult

        # Mock get_page_snapshot to return current page state
        mock_page_ops.get_page_snapshot.return_value = PageSnapshot(
            page_id="existing-123",
            space_key="TEST",
            title="Test Page",
            xhtml="<p>Original Content</p>",
            markdown="Original Content",
            version=1,
            parent_id=None,
            labels=[],
            last_modified=None
        )

        from src.page_operations.adf_models import AdfUpdateResult
        mock_page_ops.update_page_surgical_adf.return_value = AdfUpdateResult(
            success=True,
            page_id="existing-123",
            old_version=1,
            new_version=2,
            operations_applied=1,
        )

        # Create baseline content that differs from local (to trigger update)
        # Baseline uses frontmatter format
        baseline_content = "---\npage_id: 'existing-123'\n---\nOriginal Content"

        def get_baseline(page_id):
            """Mock baseline retrieval - returns baseline for existing page."""
            if page_id == "existing-123":
                return baseline_content
            return None

        hierarchy = {'__root__': [str(test_file)]}
        space_config = create_space_config()
        sync_config = create_sync_config(get_baseline=get_baseline)
        files_to_update = []

        mapper._push_hierarchy_to_confluence(
            hierarchy=hierarchy,
            page_ops=mock_page_ops,
            space_config=space_config,
            sync_config=sync_config,
            files_to_update=files_to_update,
            parent_page_id='parent-123'
        )

        # Should NOT create page (page already exists)
        mock_page_ops.create_page.assert_not_called()
        # Should UPDATE the page using ADF surgical operations (local differs from baseline)
        mock_page_ops.update_page_surgical_adf.assert_called_once()
        # Verify baseline_markdown was passed
        call_kwargs = mock_page_ops.update_page_surgical_adf.call_args.kwargs
        assert 'baseline_markdown' in call_kwargs
        assert call_kwargs['baseline_markdown'] == "Original Content"

    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_push_hierarchy_handles_duplicate_title_error(self, mock_api_class, mock_hierarchy_class, mock_frontmatter_class, tmp_path):
        """_push_hierarchy_to_confluence should handle duplicate title errors."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mapper = FileMapper(mock_auth)

        # Create temp file
        test_file = tmp_path / "Page.md"
        test_file.write_text("---\ntitle: Test Page\n---\nContent")

        # Mock frontmatter parsing - page without page_id (will trigger duplicate error)
        local_page = create_local_page(str(test_file), None, "Content")
        mock_frontmatter_class.parse.return_value = local_page
        mock_frontmatter_class.generate.return_value = "updated content"

        # Mock page operations - raises duplicate error
        mock_page_ops = Mock()
        mock_page_ops.create_page.side_effect = Exception("Page already exists in this space")

        # Mock get_page_by_title to return existing page
        mock_api.get_page_by_title.return_value = {'id': 'existing-page-id'}

        hierarchy = {'__root__': [str(test_file)]}
        space_config = create_space_config()
        sync_config = create_sync_config()  # New pages don't need baseline
        files_to_update = []

        mapper._push_hierarchy_to_confluence(
            hierarchy=hierarchy,
            page_ops=mock_page_ops,
            space_config=space_config,
            sync_config=sync_config,
            files_to_update=files_to_update,
            parent_page_id='parent-123'
        )

        # Should try to find existing page
        mock_api.get_page_by_title.assert_called_once()
        # Should update frontmatter with existing page ID
        assert len(files_to_update) == 1

    @patch('src.file_mapper.file_mapper.FrontmatterHandler')
    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_push_hierarchy_recursive_children(self, mock_api_class, mock_hierarchy_class, mock_frontmatter_class, tmp_path):
        """_push_hierarchy_to_confluence should recursively process children."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Create temp files for parent and child
        parent_file = tmp_path / "Parent.md"
        parent_file.write_text("---\ntitle: Parent\n---\nParent content")

        child_dir = tmp_path / "Parent"
        child_dir.mkdir()
        child_file = child_dir / "Child.md"
        child_file.write_text("---\ntitle: Child\n---\nChild content")

        # Mock frontmatter parsing
        def mock_parse(file_path, content):
            if "Parent.md" in file_path:
                return create_local_page(file_path, None, "Parent content")
            else:
                return create_local_page(file_path, None, "Child content")

        mock_frontmatter_class.parse.side_effect = mock_parse
        mock_frontmatter_class.generate.return_value = "updated content"

        # Mock page operations
        mock_page_ops = Mock()
        from src.page_operations.models import CreateResult
        mock_page_ops.create_page.side_effect = [
            CreateResult(success=True, page_id="parent-id", space_key="TEST", title="Parent", version=1),
            CreateResult(success=True, page_id="child-id", space_key="TEST", title="Child", version=1)
        ]

        hierarchy = {
            '__root__': [str(parent_file)],
            'Parent': [str(child_file)]
        }
        space_config = create_space_config(local_path=str(tmp_path))
        sync_config = create_sync_config()  # New pages don't need baseline
        files_to_update = []

        mapper._push_hierarchy_to_confluence(
            hierarchy=hierarchy,
            page_ops=mock_page_ops,
            space_config=space_config,
            sync_config=sync_config,
            files_to_update=files_to_update,
            parent_page_id='root-parent-123'
        )

        # Should create both parent and child
        assert mock_page_ops.create_page.call_count == 2
        # Should update frontmatter for both
        assert len(files_to_update) == 2


class TestFileMapperBidirectionalSync:
    """Test cases for FileMapper._bidirectional_sync() method."""

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_bidirectional_sync_detects_conflicts(self, mock_api_class, mock_hierarchy_class):
        """_bidirectional_sync should detect conflicts when same page modified on both sides."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Both local and remote have page '123' - will be a conflict
        hierarchy = create_page_node('123', 'Root')
        local_pages = {
            '/test/Page.md': create_local_page('/test/Page.md', '123', '# Modified Page')
        }
        space_config = create_space_config()
        sync_config = create_sync_config()

        # Mock the update and pull methods
        with patch.object(mapper, '_update_modified_pages') as mock_update:
            with patch.object(mapper, '_pull_from_confluence') as mock_pull:
                result = mapper._bidirectional_sync(hierarchy, local_pages, space_config, sync_config)

                # Should NOT call update or pull for conflicting pages
                mock_update.assert_not_called()
                mock_pull.assert_not_called()

                # Should report conflict
                assert '123' in result.conflict_page_ids
                assert result.pushed_count == 0
                assert result.pulled_count == 0

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_bidirectional_sync_calls_update_and_pull(self, mock_api_class, mock_hierarchy_class):
        """_bidirectional_sync should call update for local changes and pull for remote changes."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        # Remote page '456' is different from local page '123' - no conflict
        hierarchy = create_page_node('456', 'Remote Page')
        # Local page with different page_id
        local_pages = {
            '/test/Page.md': create_local_page('/test/Page.md', '123', '# Modified Page')
        }
        space_config = create_space_config()
        sync_config = create_sync_config()

        # Mock the update and pull methods
        with patch.object(mapper, '_update_modified_pages') as mock_update:
            with patch.object(mapper, '_pull_from_confluence') as mock_pull:
                result = mapper._bidirectional_sync(hierarchy, local_pages, space_config, sync_config)

                # Should call update for local modified pages (page '123')
                mock_update.assert_called_once()
                # Should call pull for remote modified pages (page '456') with selective filtering
                mock_pull.assert_called_once_with(
                    hierarchy, space_config, sync_config,
                    page_ids_to_pull={'456'}  # Only pull the modified page
                )
                # No conflicts
                assert len(result.conflict_page_ids) == 0


class TestConflictMarkerDetection:
    """Tests for conflict marker detection in file content."""

    def test_conflict_marker_pattern_detects_local_marker(self):
        """Pattern should detect <<<<<<< local marker."""
        content = """# Test Page

Some content before

<<<<<<< local
My local version
=======
Remote version
>>>>>>> remote

Content after
"""
        assert CONFLICT_MARKER_PATTERN.search(content) is not None

    def test_conflict_marker_pattern_detects_divider(self):
        """Pattern should detect ======= divider."""
        content = """# Test Page
<<<<<<< HEAD
local
=======
remote
>>>>>>> branch
"""
        assert CONFLICT_MARKER_PATTERN.search(content) is not None

    def test_conflict_marker_pattern_detects_remote_marker(self):
        """Pattern should detect >>>>>>> remote marker."""
        content = """conflict
>>>>>>> remote
end"""
        assert CONFLICT_MARKER_PATTERN.search(content) is not None

    def test_conflict_marker_pattern_ignores_clean_content(self):
        """Pattern should not match clean content without markers."""
        content = """# Test Page

This is normal content.
Some code examples with less than and greater than:
if (a < b && c > d)

No conflict markers here.
"""
        assert CONFLICT_MARKER_PATTERN.search(content) is None

    def test_conflict_marker_pattern_ignores_inline_arrows(self):
        """Pattern should not match inline < or > symbols."""
        content = """# Math Examples

The equation is: x < 7 and y > 3
Arrows: -> and <- and <-> are fine
HTML-like: <tag> </tag>
"""
        assert CONFLICT_MARKER_PATTERN.search(content) is None

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_has_conflict_markers_returns_true(self, mock_api_class, mock_hierarchy_class):
        """_has_conflict_markers should return True for conflicted content."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        conflicted = """# Page
<<<<<<< local
my version
=======
their version
>>>>>>> remote
"""
        assert mapper._has_conflict_markers(conflicted) is True

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_has_conflict_markers_returns_false(self, mock_api_class, mock_hierarchy_class):
        """_has_conflict_markers should return False for clean content."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)

        clean = """# Page
Normal content here.
No conflicts at all.
"""
        assert mapper._has_conflict_markers(clean) is False

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_update_modified_pages_skips_conflicted_file(self, mock_api_class, mock_hierarchy_class):
        """_update_modified_pages should skip files with conflict markers."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)
        mapper._base_path = '/test'

        # Create a local page with conflict markers
        conflicted_content = """# Page
<<<<<<< local
my version
=======
their version
>>>>>>> remote
"""
        local_pages = {
            '/test/Conflicted.md': create_local_page('/test/Conflicted.md', '123', conflicted_content)
        }
        space_config = create_space_config()
        sync_config = create_sync_config()

        # Mock PageOperations to verify it's NOT called
        with patch('src.file_mapper.file_mapper.PageOperations') as mock_page_ops_class:
            mock_page_ops = Mock()
            mock_page_ops_class.return_value = mock_page_ops

            # Capture printed output
            printed = []
            mapper._sync_print = lambda msg: printed.append(msg)

            mapper._update_modified_pages(local_pages, space_config, sync_config)

            # PageOperations.update_page_surgical_adf should NOT be called
            mock_page_ops.update_page_surgical_adf.assert_not_called()

            # Should have logged the conflict marker error
            assert any('CONFLICT MARKERS' in msg for msg in printed)

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_force_push_allows_files_with_conflict_markers(self, mock_api_class, mock_hierarchy_class):
        """Force-push should push files with conflict markers (user explicitly chose to overwrite)."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)
        mapper._base_path = '/test'

        # Create sync config with force_push = True
        sync_config = create_sync_config()
        sync_config.force_push = True
        sync_config.get_baseline = lambda page_id: None  # No baseline

        # File content WITH conflict markers
        conflicted_content = (
            "---\n"
            "confluence_url: https://example.atlassian.net/wiki/spaces/TEST/pages/123\n"
            "---\n"
            "# Page with Conflicts\n"
            "\n"
            "<<<<<<< local\n"
            "Local version\n"
            "=======\n"
            "Remote version\n"
            ">>>>>>> remote\n"
        )

        # Capture printed output
        printed = []
        mapper._sync_print = lambda msg: printed.append(msg)

        space_config = create_space_config(local_path='/test')

        # Mock file operations
        with patch('builtins.open', mock_open(read_data=conflicted_content)):
            with patch('os.path.getsize', return_value=1000):  # Mock file size for M1 validation
                with patch('src.file_mapper.file_mapper.PageOperations') as mock_page_ops_class:
                    mock_page_ops = Mock()
                    mock_page_ops_class.return_value = mock_page_ops

                    # Mock the update to return success
                    mock_result = Mock()
                    mock_result.success = True
                    mock_result.operations_applied = 0
                    mock_page_ops.update_page_surgical_adf.return_value = mock_result

                    hierarchy = {'__root__': ['/test/Conflicted.md']}

                    mapper._push_hierarchy_to_confluence(
                        hierarchy=hierarchy,
                        page_ops=mock_page_ops,
                        space_config=space_config,
                        sync_config=sync_config,
                        files_to_update=[],
                        parent_page_id='parent123'
                    )

                    # Should NOT have logged conflict marker error
                    assert not any('CONFLICT MARKERS' in msg for msg in printed), f"Should not skip during force-push. Printed: {printed}"

                    # PageOperations.update_page_surgical_adf SHOULD be called
                    mock_page_ops.update_page_surgical_adf.assert_called_once()


class TestForcePushFileLogging:
    """Tests for file logging during force-push operations."""

    @patch('src.file_mapper.file_mapper.HierarchyBuilder')
    @patch('src.file_mapper.file_mapper.APIWrapper')
    def test_force_push_logs_unchanged_files(self, mock_api_class, mock_hierarchy_class):
        """Force-push should log unchanged files with = indicator."""
        mock_auth = create_mock_auth()
        mapper = FileMapper(mock_auth)
        mapper._base_path = '/test'

        # Create sync config with force_push = True
        sync_config = create_sync_config()
        sync_config.force_push = True

        # File content with page_id extracted from confluence_url (already synced before)
        # The URL format must be: https://domain/wiki/spaces/{space-key}/pages/{page-id}
        file_content = (
            "---\n"
            "confluence_url: https://example.atlassian.net/wiki/spaces/TEST/pages/123\n"
            "---\n"
            "# Same Content\n"
            "\n"
            "Body text here."
        )

        # Create baseline that matches local content (same content)
        baseline_content = file_content

        sync_config.get_baseline = lambda page_id: baseline_content

        # Capture printed output
        printed = []
        mapper._sync_print = lambda msg: printed.append(msg)

        # Create a local page that matches baseline
        space_config = create_space_config(local_path='/test')

        # Mock file operations
        with patch('builtins.open', mock_open(read_data=file_content)):
            with patch('os.path.getsize', return_value=1000):  # Mock file size for M1 validation
                with patch('src.file_mapper.file_mapper.PageOperations') as mock_page_ops_class:
                    mock_page_ops = Mock()
                    mock_page_ops_class.return_value = mock_page_ops

                    # Create minimal hierarchy
                    hierarchy = {'__root__': ['/test/Page.md']}

                    mapper._push_hierarchy_to_confluence(
                        hierarchy=hierarchy,
                        page_ops=mock_page_ops,
                        space_config=space_config,
                        sync_config=sync_config,
                        files_to_update=[],
                        parent_page_id='parent123'
                    )

                    # Should have logged the unchanged file with = indicator
                    assert any('=' in msg and 'Page.md' in msg for msg in printed), f"Printed: {printed}"
