"""Unit tests for confluence_client.auth module."""

import pytest
from unittest.mock import patch
from src.confluence_client.auth import Authenticator, Credentials
from src.confluence_client.errors import InvalidCredentialsError


class TestCredentials:
    """Test cases for Credentials NamedTuple."""

    def test_credentials_creation(self):
        """Credentials can be created with url, user, and api_token."""
        creds = Credentials(
            url="https://test.atlassian.net/wiki",
            user="test@example.com",
            api_token="test-token-123"
        )
        assert creds.url == "https://test.atlassian.net/wiki"
        assert creds.user == "test@example.com"
        assert creds.api_token == "test-token-123"

    def test_credentials_are_immutable(self):
        """Credentials fields cannot be modified after creation."""
        creds = Credentials(
            url="https://test.atlassian.net/wiki",
            user="test@example.com",
            api_token="test-token-123"
        )
        with pytest.raises(AttributeError):
            creds.url = "different-url"


class TestAuthenticator:
    """Test cases for Authenticator class."""

    @patch('src.confluence_client.auth.load_dotenv')
    def test_init_loads_dotenv(self, mock_load_dotenv):
        """Authenticator __init__ should call load_dotenv()."""
        Authenticator()
        mock_load_dotenv.assert_called_once()

    @patch('src.confluence_client.auth.load_dotenv')
    @patch('os.getenv')
    def test_get_credentials_success(self, mock_getenv, mock_load_dotenv):
        """get_credentials should return Credentials when all env vars are set."""
        # Mock environment variables
        def getenv_side_effect(key):
            env_vars = {
                'CONFLUENCE_URL': 'https://test.atlassian.net/wiki',
                'CONFLUENCE_USER': 'test@example.com',
                'CONFLUENCE_API_TOKEN': 'test-token-123'
            }
            return env_vars.get(key)

        mock_getenv.side_effect = getenv_side_effect

        auth = Authenticator()
        creds = auth.get_credentials()

        assert isinstance(creds, Credentials)
        assert creds.url == 'https://test.atlassian.net/wiki'
        assert creds.user == 'test@example.com'
        assert creds.api_token == 'test-token-123'

    @patch('src.confluence_client.auth.load_dotenv')
    @patch('os.getenv')
    def test_get_credentials_missing_url(self, mock_getenv, mock_load_dotenv):
        """get_credentials should raise InvalidCredentialsError if URL is missing."""
        def getenv_side_effect(key):
            env_vars = {
                'CONFLUENCE_URL': None,
                'CONFLUENCE_USER': 'test@example.com',
                'CONFLUENCE_API_TOKEN': 'test-token-123'
            }
            return env_vars.get(key)

        mock_getenv.side_effect = getenv_side_effect

        auth = Authenticator()
        with pytest.raises(InvalidCredentialsError) as exc_info:
            auth.get_credentials()

        assert exc_info.value.user == 'test@example.com'
        assert exc_info.value.endpoint == 'unknown'

    @patch('src.confluence_client.auth.load_dotenv')
    @patch('os.getenv')
    def test_get_credentials_missing_user(self, mock_getenv, mock_load_dotenv):
        """get_credentials should raise InvalidCredentialsError if user is missing."""
        def getenv_side_effect(key):
            env_vars = {
                'CONFLUENCE_URL': 'https://test.atlassian.net/wiki',
                'CONFLUENCE_USER': None,
                'CONFLUENCE_API_TOKEN': 'test-token-123'
            }
            return env_vars.get(key)

        mock_getenv.side_effect = getenv_side_effect

        auth = Authenticator()
        with pytest.raises(InvalidCredentialsError) as exc_info:
            auth.get_credentials()

        assert exc_info.value.user == 'unknown'
        assert exc_info.value.endpoint == 'https://test.atlassian.net/wiki'

    @patch('src.confluence_client.auth.load_dotenv')
    @patch('os.getenv')
    def test_get_credentials_missing_token(self, mock_getenv, mock_load_dotenv):
        """get_credentials should raise InvalidCredentialsError if api_token is missing."""
        def getenv_side_effect(key):
            env_vars = {
                'CONFLUENCE_URL': 'https://test.atlassian.net/wiki',
                'CONFLUENCE_USER': 'test@example.com',
                'CONFLUENCE_API_TOKEN': None
            }
            return env_vars.get(key)

        mock_getenv.side_effect = getenv_side_effect

        auth = Authenticator()
        with pytest.raises(InvalidCredentialsError):
            auth.get_credentials()

    @patch('src.confluence_client.auth.load_dotenv')
    @patch('os.getenv')
    def test_get_credentials_all_missing(self, mock_getenv, mock_load_dotenv):
        """get_credentials should raise InvalidCredentialsError if all env vars are missing."""
        mock_getenv.return_value = None

        auth = Authenticator()
        with pytest.raises(InvalidCredentialsError) as exc_info:
            auth.get_credentials()

        assert exc_info.value.user == 'unknown'
        assert exc_info.value.endpoint == 'unknown'

    @patch('src.confluence_client.auth.load_dotenv')
    @patch('os.getenv')
    def test_get_credentials_empty_strings(self, mock_getenv, mock_load_dotenv):
        """get_credentials should treat empty strings as missing credentials."""
        def getenv_side_effect(key):
            env_vars = {
                'CONFLUENCE_URL': '',
                'CONFLUENCE_USER': '',
                'CONFLUENCE_API_TOKEN': ''
            }
            return env_vars.get(key)

        mock_getenv.side_effect = getenv_side_effect

        auth = Authenticator()
        with pytest.raises(InvalidCredentialsError):
            auth.get_credentials()
