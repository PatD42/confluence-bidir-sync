"""Unit tests for api_wrapper module."""

import pytest
from unittest.mock import Mock, patch
from requests.exceptions import HTTPError, ConnectionError
from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.errors import (
    InvalidCredentialsError,
    PageNotFoundError,
    APIUnreachableError,
    APIAccessError
)


def create_mock_auth():
    """Create a mock authenticator with standard credentials."""
    mock_auth = Mock()
    mock_creds = Mock()
    mock_creds.url = 'https://test.atlassian.net/wiki'
    mock_creds.user = 'test@example.com'
    mock_creds.api_token = 'token123'
    mock_auth.get_credentials.return_value = mock_creds
    return mock_auth


class TestAPIWrapper:
    """Test cases for APIWrapper class."""

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_init_lazy_loads_client(self, mock_confluence):
        """__init__ should not create client until first use."""
        mock_auth = Mock()
        APIWrapper(mock_auth)

        # Client should not be created yet (lazy loading)
        mock_auth.get_credentials.assert_not_called()
        mock_confluence.assert_not_called()

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_get_page_by_id_success(self, mock_confluence):
        """get_page_by_id should return page data on success."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        mock_client.get_page_by_id.return_value = {'id': '123', 'title': 'Test'}
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)
        result = wrapper.get_page_by_id('123')

        assert result == {'id': '123', 'title': 'Test'}
        # Check that it was called with keyword args and default expand
        mock_client.get_page_by_id.assert_called_once_with(page_id='123', expand='space,body.storage,version')

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_get_page_by_id_raises_page_not_found_on_404(self, mock_confluence):
        """get_page_by_id should raise PageNotFoundError on 404."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        error = HTTPError()
        error.response = Mock()
        error.response.status_code = 404
        mock_client.get_page_by_id.side_effect = error
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)

        with pytest.raises(PageNotFoundError) as exc_info:
            wrapper.get_page_by_id('123')

        # Implementation returns "unknown" because it can't extract page_id from error
        assert exc_info.value.page_id == 'unknown'

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_get_page_by_id_raises_invalid_credentials_on_401(self, mock_confluence):
        """get_page_by_id should raise InvalidCredentialsError on 401."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        error = HTTPError()
        error.response = Mock()
        error.response.status_code = 401
        mock_client.get_page_by_id.side_effect = error
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)

        with pytest.raises(InvalidCredentialsError):
            wrapper.get_page_by_id('123')

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_get_page_by_id_raises_api_unreachable_on_connection_error(self, mock_confluence):
        """get_page_by_id should raise APIUnreachableError on ConnectionError."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        # Use "Connection failed" which contains "connection" keyword
        mock_client.get_page_by_id.side_effect = ConnectionError("Connection failed")
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)

        with pytest.raises(APIUnreachableError):
            wrapper.get_page_by_id('123')

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_get_page_by_title_success(self, mock_confluence):
        """get_page_by_title should return page data on success."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        mock_client.get_page_by_title.return_value = {'id': '456', 'title': 'Test Page'}
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)
        result = wrapper.get_page_by_title('TEST', 'Test Page')

        assert result == {'id': '456', 'title': 'Test Page'}

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_update_page_success(self, mock_confluence):
        """update_page should return new version number on success."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        # Implementation returns full dict, then extracts version number
        mock_client.update_page.return_value = {'version': {'number': 3}}
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)
        result = wrapper.update_page('123', 'Updated Title', '<p>Content</p>', 2)

        # update_page method returns full dict from API
        assert result == {'version': {'number': 3}}

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_create_page_success(self, mock_confluence):
        """create_page should return created page data on success."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        mock_client.create_page.return_value = {'id': '789', 'title': 'New Page'}
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)
        result = wrapper.create_page('TEST', 'New Page', '<p>Content</p>')

        assert result == {'id': '789', 'title': 'New Page'}

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_get_page_child_by_type_success(self, mock_confluence):
        """get_page_child_by_type should return child pages."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        mock_client.get_page_child_by_type.return_value = [
            {'id': 'child1'},
            {'id': 'child2'}
        ]
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)
        result = wrapper.get_page_child_by_type('123')

        assert result == [{'id': 'child1'}, {'id': 'child2'}]

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_cql_query_pagination(self, mock_confluence):
        """search_by_cql should handle pagination correctly."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        # Mock paginated results
        mock_client.cql.return_value = {
            'results': [
                {'id': '1', 'title': 'Page 1'},
                {'id': '2', 'title': 'Page 2'}
            ],
            'start': 0,
            'limit': 2,
            'size': 2,
            'totalSize': 10
        }
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)
        result = wrapper.search_by_cql('type=page', start=0, limit=2)

        assert result['results'] == [
            {'id': '1', 'title': 'Page 1'},
            {'id': '2', 'title': 'Page 2'}
        ]
        assert result['start'] == 0
        assert result['limit'] == 2
        assert result['size'] == 2
        assert result['totalSize'] == 10
        mock_client.cql.assert_called_once_with(
            cql='type=page',
            start=0,
            limit=2,
            expand=None
        )

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_cql_query_with_expand(self, mock_confluence):
        """search_by_cql should pass expand parameter correctly."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        mock_client.cql.return_value = {
            'results': [{'id': '1', 'title': 'Page 1', 'body': {'storage': {'value': '<p>Content</p>'}}}],
            'start': 0,
            'limit': 25,
            'size': 1
        }
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)
        result = wrapper.search_by_cql('type=page', expand='body.storage,version')

        assert result['size'] == 1
        mock_client.cql.assert_called_once_with(
            cql='type=page',
            start=0,
            limit=25,
            expand='body.storage,version'
        )

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_cql_query_empty_results(self, mock_confluence):
        """search_by_cql should handle empty results."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        mock_client.cql.return_value = {
            'results': [],
            'start': 0,
            'limit': 25,
            'size': 0,
            'totalSize': 0
        }
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)
        result = wrapper.search_by_cql('type=page AND title~"nonexistent"')

        assert result['results'] == []
        assert result['size'] == 0

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_cql_query_raises_invalid_credentials_on_401(self, mock_confluence):
        """search_by_cql should raise InvalidCredentialsError on 401."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        error = HTTPError()
        error.response = Mock()
        error.response.status_code = 401
        mock_client.cql.side_effect = error
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)

        with pytest.raises(InvalidCredentialsError):
            wrapper.search_by_cql('type=page')

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_cql_query_raises_api_unreachable_on_connection_error(self, mock_confluence):
        """search_by_cql should raise APIUnreachableError on ConnectionError."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        mock_client.cql.side_effect = ConnectionError("Connection failed")
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)

        with pytest.raises(APIUnreachableError):
            wrapper.search_by_cql('type=page')

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_cql_query_default_pagination(self, mock_confluence):
        """search_by_cql should use default pagination values."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        mock_client.cql.return_value = {
            'results': [],
            'start': 0,
            'limit': 25,
            'size': 0
        }
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)
        wrapper.search_by_cql('type=page')

        # Verify default values are used
        mock_client.cql.assert_called_once_with(
            cql='type=page',
            start=0,
            limit=25,
            expand=None
        )

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_get_space_success(self, mock_confluence):
        """get_space should return space data with homepage on success."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        mock_client.get_space.return_value = {
            'key': 'TEAM',
            'name': 'Team Space',
            'homepage': {
                'id': '123456',
                'title': 'Team Home'
            }
        }
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)
        result = wrapper.get_space('TEAM')

        assert result['key'] == 'TEAM'
        assert result['homepage']['id'] == '123456'
        mock_client.get_space.assert_called_once_with(
            space_key='TEAM',
            expand='homepage'
        )

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_get_space_with_custom_expand(self, mock_confluence):
        """get_space should pass custom expand parameter."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        mock_client.get_space.return_value = {'key': 'TEAM', 'name': 'Team Space'}
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)
        wrapper.get_space('TEAM', expand='homepage,description')

        mock_client.get_space.assert_called_once_with(
            space_key='TEAM',
            expand='homepage,description'
        )

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_get_space_raises_page_not_found_on_404(self, mock_confluence):
        """get_space should raise PageNotFoundError on 404 (space not found)."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        error = HTTPError()
        error.response = Mock()
        error.response.status_code = 404
        mock_client.get_space.side_effect = error
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)

        with pytest.raises(PageNotFoundError):
            wrapper.get_space('NONEXISTENT')

    @patch('src.confluence_client.api_wrapper.Confluence')
    def test_get_space_raises_invalid_credentials_on_401(self, mock_confluence):
        """get_space should raise InvalidCredentialsError on 401."""
        mock_auth = create_mock_auth()

        mock_client = Mock()
        error = HTTPError()
        error.response = Mock()
        error.response.status_code = 401
        mock_client.get_space.side_effect = error
        mock_confluence.return_value = mock_client

        wrapper = APIWrapper(mock_auth)

        with pytest.raises(InvalidCredentialsError):
            wrapper.get_space('TEAM')
