"""Unit tests for hierarchy_builder module."""

import pytest
from unittest.mock import Mock, patch, call
from src.file_mapper.hierarchy_builder import HierarchyBuilder
from src.file_mapper.models import PageNode
from src.file_mapper.errors import PageLimitExceededError
from src.confluence_client.errors import (
    PageNotFoundError,
    APIUnreachableError,
    APIAccessError,
    InvalidCredentialsError,
)


def create_mock_auth():
    """Create a mock authenticator."""
    return Mock()


def create_page_data(page_id, title, space_key='TEST', last_modified='2024-01-01T00:00:00.000Z'):
    """Create mock page data dictionary."""
    return {
        'id': page_id,
        'title': title,
        'version': {'when': last_modified, 'number': 1},
        'space': {'key': space_key}
    }


class TestHierarchyBuilder:
    """Test cases for HierarchyBuilder class."""

    def test_init_creates_api_wrapper(self):
        """__init__ should create APIWrapper with provided authenticator."""
        mock_auth = create_mock_auth()

        with patch('src.file_mapper.hierarchy_builder.APIWrapper') as mock_wrapper:
            builder = HierarchyBuilder(mock_auth)

            # Should create APIWrapper with authenticator
            mock_wrapper.assert_called_once_with(mock_auth)

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_success_no_children(self, mock_wrapper_class):
        """build_hierarchy should create root node with no children."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        # Parent page with no children
        parent_data = create_page_data('123', 'Parent Page')
        mock_api.get_page_by_id.return_value = parent_data

        # Mock get_page_child_by_type to return empty results (no children)
        mock_api.get_page_child_by_type.return_value = {'results': []}

        builder = HierarchyBuilder(mock_auth)
        result = builder.build_hierarchy('123', 'TEST')

        # Should return root node
        assert result.page_id == '123'
        assert result.title == 'Parent Page'
        assert result.parent_id is None
        assert result.space_key == 'TEST'
        assert len(result.children) == 0

        # Should have called get_page_by_id with expand (including body.storage for content)
        mock_api.get_page_by_id.assert_called_once_with(
            page_id='123',
            expand='version,space,ancestors,body.storage'
        )

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_with_single_child(self, mock_wrapper_class):
        """build_hierarchy should build tree with one child."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        # Parent and child data
        parent_data = create_page_data('123', 'Parent Page')
        child_data = create_page_data('456', 'Child Page')

        mock_api.get_page_by_id.return_value = parent_data

        # Mock get_page_child_by_type - first call returns child, second returns empty
        mock_api.get_page_child_by_type.side_effect = [
            {'results': [child_data]},  # Children of parent
            {'results': []}  # Children of child (none)
        ]

        builder = HierarchyBuilder(mock_auth)
        result = builder.build_hierarchy('123', 'TEST')

        # Should have root with one child
        assert result.page_id == '123'
        assert len(result.children) == 1
        assert result.children[0].page_id == '456'
        assert result.children[0].title == 'Child Page'
        assert result.children[0].parent_id == '123'
        assert len(result.children[0].children) == 0

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_with_nested_children(self, mock_wrapper_class):
        """build_hierarchy should build multi-level tree."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        # Parent, child, and grandchild data
        parent_data = create_page_data('123', 'Parent')
        child_data = create_page_data('456', 'Child')
        grandchild_data = create_page_data('789', 'Grandchild')

        mock_api.get_page_by_id.return_value = parent_data

        # Mock get_page_child_by_type for each level
        mock_api.get_page_child_by_type.side_effect = [
            {'results': [child_data]},  # Children of parent
            {'results': [grandchild_data]},  # Children of child
            {'results': []}  # Children of grandchild (none)
        ]

        builder = HierarchyBuilder(mock_auth)
        result = builder.build_hierarchy('123', 'TEST')

        # Verify tree structure
        assert result.page_id == '123'
        assert len(result.children) == 1
        assert result.children[0].page_id == '456'
        assert len(result.children[0].children) == 1
        assert result.children[0].children[0].page_id == '789'
        assert result.children[0].children[0].parent_id == '456'

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_with_multiple_children(self, mock_wrapper_class):
        """build_hierarchy should handle multiple children at same level."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        parent_data = create_page_data('123', 'Parent')
        child1_data = create_page_data('456', 'Child 1')
        child2_data = create_page_data('457', 'Child 2')

        mock_api.get_page_by_id.return_value = parent_data

        # Mock get_page_child_by_type
        mock_api.get_page_child_by_type.side_effect = [
            {'results': [child1_data, child2_data]},  # Children of parent
            {'results': []},  # Children of child 1
            {'results': []}  # Children of child 2
        ]

        builder = HierarchyBuilder(mock_auth)
        result = builder.build_hierarchy('123', 'TEST')

        # Should have two children
        assert len(result.children) == 2
        assert result.children[0].page_id == '456'
        assert result.children[1].page_id == '457'

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_excludes_pages(self, mock_wrapper_class):
        """build_hierarchy should exclude pages in exclude_page_ids list."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        parent_data = create_page_data('123', 'Parent')
        child1_data = create_page_data('456', 'Child 1')
        child2_data = create_page_data('457', 'Child 2 - Excluded')

        mock_api.get_page_by_id.return_value = parent_data

        # Mock get_page_child_by_type - API returns both, but child2 will be filtered
        mock_api.get_page_child_by_type.side_effect = [
            {'results': [child1_data, child2_data]},  # API returns both
            {'results': []}  # Children of child 1
        ]

        builder = HierarchyBuilder(mock_auth)
        result = builder.build_hierarchy('123', 'TEST', exclude_page_ids=['457'])

        # Should only have child1, child2 is excluded
        assert len(result.children) == 1
        assert result.children[0].page_id == '456'

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_excludes_parent(self, mock_wrapper_class):
        """build_hierarchy should build minimal tree if parent is excluded."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        parent_data = create_page_data('123', 'Parent')
        mock_api.get_page_by_id.return_value = parent_data

        builder = HierarchyBuilder(mock_auth)
        result = builder.build_hierarchy('123', 'TEST', exclude_page_ids=['123'])

        # Should return root node without querying for children
        assert result.page_id == '123'
        assert len(result.children) == 0

        # Should not call _get_client or cql
        mock_api._get_client.assert_not_called()

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_raises_page_limit_exceeded(self, mock_wrapper_class):
        """build_hierarchy should raise PageLimitExceededError when limit exceeded."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        parent_data = create_page_data('123', 'Parent')
        mock_api.get_page_by_id.return_value = parent_data

        # Create 3 children (exceeds limit of 2)
        children_data = [
            create_page_data('456', 'Child 1'),
            create_page_data('457', 'Child 2'),
            create_page_data('458', 'Child 3'),
        ]

        # Mock get_page_child_by_type to return 3 children
        mock_api.get_page_child_by_type.return_value = {'results': children_data}

        builder = HierarchyBuilder(mock_auth)

        with pytest.raises(PageLimitExceededError) as exc_info:
            builder.build_hierarchy('123', 'TEST', page_limit=2)

        assert exc_info.value.current_count == 3
        assert exc_info.value.limit == 2

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_raises_page_not_found(self, mock_wrapper_class):
        """build_hierarchy should raise PageNotFoundError when parent doesn't exist."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        # API raises PageNotFoundError
        mock_api.get_page_by_id.side_effect = PageNotFoundError('999')

        builder = HierarchyBuilder(mock_auth)

        with pytest.raises(PageNotFoundError):
            builder.build_hierarchy('999', 'TEST')

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_raises_invalid_credentials(self, mock_wrapper_class):
        """build_hierarchy should raise InvalidCredentialsError on auth failure."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        mock_api.get_page_by_id.side_effect = InvalidCredentialsError(
            user='test@example.com',
            endpoint='https://test.atlassian.net/wiki'
        )

        builder = HierarchyBuilder(mock_auth)

        with pytest.raises(InvalidCredentialsError):
            builder.build_hierarchy('123', 'TEST')

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_raises_api_unreachable(self, mock_wrapper_class):
        """build_hierarchy should raise APIUnreachableError when API is down."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        mock_api.get_page_by_id.side_effect = APIUnreachableError('https://test.com')

        builder = HierarchyBuilder(mock_auth)

        with pytest.raises(APIUnreachableError):
            builder.build_hierarchy('123', 'TEST')

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_validates_space_key(self, mock_wrapper_class):
        """build_hierarchy should log warning if page is in different space."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        # Page is in different space
        parent_data = create_page_data('123', 'Parent', space_key='OTHER')
        mock_api.get_page_by_id.return_value = parent_data

        # Mock get_page_child_by_type to return empty results
        mock_api.get_page_child_by_type.return_value = {'results': []}

        builder = HierarchyBuilder(mock_auth)

        # Should still build tree but log warning
        with patch('src.file_mapper.hierarchy_builder.logger') as mock_logger:
            result = builder.build_hierarchy('123', 'TEST')

            # Should log warning about space mismatch
            mock_logger.warning.assert_called()
            assert "not 'TEST' as expected" in str(mock_logger.warning.call_args)

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_query_children_cql_success(self, mock_wrapper_class):
        """_query_children_cql should fetch child pages and return results."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        expected_results = [
            create_page_data('456', 'Child 1'),
            create_page_data('457', 'Child 2')
        ]
        # Mock get_page_child_by_type to return results
        mock_api.get_page_child_by_type.return_value = {'results': expected_results}

        builder = HierarchyBuilder(mock_auth)
        results = builder._query_children_cql('123', 'TEST')

        # Should return results list
        assert results == expected_results

        # Should call get_page_child_by_type with correct parameters
        mock_api.get_page_child_by_type.assert_called_once_with(
            page_id='123',
            child_type='page',
            expand='version,space,body.storage'
        )

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_query_children_cql_handles_empty_results(self, mock_wrapper_class):
        """_query_children_cql should handle empty results gracefully."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        # Mock get_page_child_by_type to return empty results
        mock_api.get_page_child_by_type.return_value = {'results': []}

        builder = HierarchyBuilder(mock_auth)
        results = builder._query_children_cql('123', 'TEST')

        assert results == []

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_query_children_cql_raises_api_access_error(self, mock_wrapper_class):
        """_query_children_cql should raise APIAccessError on API failure."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        # Mock get_page_child_by_type to raise exception
        mock_api.get_page_child_by_type.side_effect = Exception("API error")

        builder = HierarchyBuilder(mock_auth)

        with pytest.raises(APIAccessError) as exc_info:
            builder._query_children_cql('123', 'TEST')

        assert "Failed to fetch child pages" in str(exc_info.value)

    def test_create_page_node_success(self):
        """_create_page_node should create PageNode from API data."""
        mock_auth = create_mock_auth()

        with patch('src.file_mapper.hierarchy_builder.APIWrapper'):
            builder = HierarchyBuilder(mock_auth)

            page_data = {
                'id': '123',
                'title': 'Test Page',
                'version': {'when': '2024-01-15T10:30:00.000Z', 'number': 5},
                'space': {'key': 'TEST'}
            }

            result = builder._create_page_node(page_data, parent_id='999')

            assert result.page_id == '123'
            assert result.title == 'Test Page'
            assert result.parent_id == '999'
            assert result.last_modified == '2024-01-15T10:30:00.000Z'
            assert result.space_key == 'TEST'
            assert result.children == []

    def test_create_page_node_with_none_parent(self):
        """_create_page_node should handle None parent_id for root nodes."""
        mock_auth = create_mock_auth()

        with patch('src.file_mapper.hierarchy_builder.APIWrapper'):
            builder = HierarchyBuilder(mock_auth)

            page_data = create_page_data('123', 'Root Page')
            result = builder._create_page_node(page_data, parent_id=None)

            assert result.parent_id is None

    def test_create_page_node_handles_missing_version(self):
        """_create_page_node should handle missing version info."""
        mock_auth = create_mock_auth()

        with patch('src.file_mapper.hierarchy_builder.APIWrapper'):
            builder = HierarchyBuilder(mock_auth)

            page_data = {
                'id': '123',
                'title': 'Test Page',
                'space': {'key': 'TEST'}
            }

            result = builder._create_page_node(page_data, parent_id=None)

            assert result.last_modified == ''

    def test_create_page_node_handles_missing_space(self):
        """_create_page_node should handle missing space info."""
        mock_auth = create_mock_auth()

        with patch('src.file_mapper.hierarchy_builder.APIWrapper'):
            builder = HierarchyBuilder(mock_auth)

            page_data = {
                'id': '123',
                'title': 'Test Page',
                'version': {'when': '2024-01-01T00:00:00.000Z'}
            }

            result = builder._create_page_node(page_data, parent_id=None)

            assert result.space_key == ''

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_hierarchy_with_custom_page_limit(self, mock_wrapper_class):
        """build_hierarchy should respect custom page_limit parameter."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        parent_data = create_page_data('123', 'Parent')
        mock_api.get_page_by_id.return_value = parent_data

        # Create children under the limit
        children_data = [create_page_data(f'{i}', f'Child {i}') for i in range(5)]

        # Mock get_page_child_by_type - first call returns 5 children, then empty for each
        mock_api.get_page_child_by_type.side_effect = [
            {'results': children_data},
        ] + [{'results': []} for _ in range(5)]  # No grandchildren

        builder = HierarchyBuilder(mock_auth)
        result = builder.build_hierarchy('123', 'TEST', page_limit=10)

        # Should succeed with 5 children under limit of 10
        assert len(result.children) == 5

    @patch('src.file_mapper.hierarchy_builder.APIWrapper')
    def test_build_children_recursive_logs_debug_messages(self, mock_wrapper_class):
        """_build_children_recursive should log debug messages."""
        mock_auth = create_mock_auth()
        mock_api = Mock()
        mock_wrapper_class.return_value = mock_api

        parent_data = create_page_data('123', 'Parent')
        mock_api.get_page_by_id.return_value = parent_data

        # Mock get_page_child_by_type to return empty results
        mock_api.get_page_child_by_type.return_value = {'results': []}

        builder = HierarchyBuilder(mock_auth)

        with patch('src.file_mapper.hierarchy_builder.logger') as mock_logger:
            builder.build_hierarchy('123', 'TEST')

            # Should log info and debug messages
            mock_logger.info.assert_called()
            mock_logger.debug.assert_called()
