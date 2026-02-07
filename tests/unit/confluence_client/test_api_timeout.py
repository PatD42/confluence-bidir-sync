"""Unit tests for API timeout configuration in APIWrapper.

Tests H2: API timeouts to prevent application hangs.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import Timeout, ConnectTimeout, ReadTimeout

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator
from src.confluence_client.errors import APIUnreachableError


class TestAPITimeout:
    """Test cases for API timeout configuration (H2)."""

    @pytest.fixture
    def mock_authenticator(self):
        """Create a mock authenticator with valid credentials."""
        auth = Mock(spec=Authenticator)
        creds = Mock()
        creds.url = "https://test.atlassian.net/wiki"
        creds.user = "test@example.com"
        creds.api_token = "fake-token"
        auth.get_credentials.return_value = creds
        return auth

    @pytest.fixture
    def api_wrapper(self, mock_authenticator):
        """Create an APIWrapper instance with mocked authenticator."""
        return APIWrapper(mock_authenticator)

    def test_confluence_client_initialized_with_timeout(self, api_wrapper):
        """Verify Confluence client is initialized with 30s timeout."""
        with patch('src.confluence_client.api_wrapper.Confluence') as MockConfluence:
            # Access client to trigger initialization
            api_wrapper._get_client()

            # Verify Confluence was instantiated with timeout
            MockConfluence.assert_called_once()
            call_kwargs = MockConfluence.call_args.kwargs
            assert 'timeout' in call_kwargs
            assert call_kwargs['timeout'] == 30

    def test_timeout_prevents_indefinite_hang(self, api_wrapper):
        """Verify timeout prevents indefinite hang on slow API (CRITICAL TEST)."""
        with patch('src.confluence_client.api_wrapper.Confluence') as MockConfluence:
            # Mock a slow API that times out
            mock_client = Mock()
            mock_client.get_page_by_id.side_effect = Timeout("Request timed out after 30s")
            MockConfluence.return_value = mock_client

            # Should raise APIUnreachableError due to timeout
            with pytest.raises(APIUnreachableError):
                api_wrapper.get_page_by_id("123456")

    def test_connect_timeout_handled(self, api_wrapper):
        """Verify connection timeout is handled properly."""
        with patch('src.confluence_client.api_wrapper.Confluence') as MockConfluence:
            mock_client = Mock()
            mock_client.get_page_by_id.side_effect = ConnectTimeout("Connection timed out")
            MockConfluence.return_value = mock_client

            with pytest.raises(APIUnreachableError):
                api_wrapper.get_page_by_id("123456")

    def test_read_timeout_handled(self, api_wrapper):
        """Verify read timeout is handled properly."""
        with patch('src.confluence_client.api_wrapper.Confluence') as MockConfluence:
            mock_client = Mock()
            mock_client.get_page_by_id.side_effect = ReadTimeout("Read timed out")
            MockConfluence.return_value = mock_client

            with pytest.raises(APIUnreachableError):
                api_wrapper.get_page_by_id("123456")

    def test_timeout_on_update_page(self, api_wrapper):
        """Verify timeout applies to update_page operations."""
        with patch('src.confluence_client.api_wrapper.Confluence') as MockConfluence:
            mock_client = Mock()
            mock_client.update_page.side_effect = Timeout("Request timed out")
            MockConfluence.return_value = mock_client

            with pytest.raises(APIUnreachableError):
                api_wrapper.update_page(
                    page_id="123456",
                    title="Test",
                    body="<p>Content</p>",
                    version=2
                )

    def test_timeout_on_create_page(self, api_wrapper):
        """Verify timeout applies to create_page operations."""
        with patch('src.confluence_client.api_wrapper.Confluence') as MockConfluence:
            mock_client = Mock()
            mock_client.create_page.side_effect = ReadTimeout("Read timed out")
            MockConfluence.return_value = mock_client

            with pytest.raises(APIUnreachableError):
                api_wrapper.create_page(
                    space="TEST",
                    title="Test Page",
                    body="<p>Content</p>"
                )

    def test_timeout_on_delete_page(self, api_wrapper):
        """Verify timeout applies to delete_page operations."""
        with patch('src.confluence_client.api_wrapper.Confluence') as MockConfluence:
            mock_client = Mock()
            mock_client.remove_page.side_effect = ConnectTimeout("Connection timeout")
            MockConfluence.return_value = mock_client

            with pytest.raises(APIUnreachableError):
                api_wrapper.delete_page("123456")

    def test_successful_request_within_timeout(self, api_wrapper):
        """Verify successful requests complete within timeout."""
        with patch('src.confluence_client.api_wrapper.Confluence') as MockConfluence:
            mock_client = Mock()
            mock_client.get_page_by_id.return_value = {
                'id': '123456',
                'title': 'Test Page',
                'version': {'number': 1},
                'body': {'storage': {'value': '<p>Content</p>'}}
            }
            MockConfluence.return_value = mock_client

            # Should succeed without timeout
            page = api_wrapper.get_page_by_id("123456")
            assert page['id'] == '123456'

    def test_timeout_value_is_reasonable(self, api_wrapper):
        """Verify timeout value is set to a reasonable duration (30s)."""
        with patch('src.confluence_client.api_wrapper.Confluence') as MockConfluence:
            api_wrapper._get_client()

            # 30 seconds is reasonable - not too short (false timeouts)
            # and not too long (user waiting)
            call_kwargs = MockConfluence.call_args.kwargs
            timeout = call_kwargs.get('timeout')
            assert timeout == 30
            assert 10 <= timeout <= 60  # Reasonable range

    def test_client_reuses_same_instance(self, api_wrapper):
        """Verify client is initialized only once (timeout set once)."""
        with patch('src.confluence_client.api_wrapper.Confluence') as MockConfluence:
            # Call _get_client multiple times
            client1 = api_wrapper._get_client()
            client2 = api_wrapper._get_client()

            # Should be same instance
            assert client1 is client2

            # Confluence constructor should be called only once
            assert MockConfluence.call_count == 1
