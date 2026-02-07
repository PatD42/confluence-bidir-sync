"""Unit tests for error message sanitization in APIWrapper.

Tests H5: Credentials in error messages should be masked to prevent
information disclosure.
"""

import pytest
from unittest.mock import Mock, patch

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator


class TestErrorMessageSanitization:
    """Test cases for error message sanitization (H5)."""

    @pytest.fixture
    def mock_authenticator(self):
        """Create a mock authenticator with credentials."""
        auth = Mock(spec=Authenticator)
        creds = Mock()
        creds.url = "https://test.atlassian.net/wiki"
        creds.user = "test@example.com"
        creds.api_token = "sk-test-token-abc123xyz456"
        auth.get_credentials.return_value = creds
        return auth

    @pytest.fixture
    def api_wrapper(self, mock_authenticator):
        """Create an APIWrapper instance with mocked authenticator."""
        return APIWrapper(mock_authenticator)

    def test_sanitize_api_tokens(self, api_wrapper):
        """Verify API tokens are masked in error messages (CRITICAL TEST)."""
        error_msg = "Authentication failed with token sk-test-abc123xyz456def789ghi012"
        sanitized = api_wrapper._sanitize_credentials(error_msg)

        # Token should be masked
        assert "sk-test-abc123xyz456def789ghi012" not in sanitized
        assert "***REDACTED***" in sanitized

    def test_sanitize_password_in_url(self, api_wrapper):
        """Verify passwords in URLs are masked."""
        error_msg = "Connection failed to https://user:secretpass@example.com/wiki"
        sanitized = api_wrapper._sanitize_credentials(error_msg)

        # Password should be masked
        assert "secretpass" not in sanitized
        assert "***:***@" in sanitized
        assert "example.com" in sanitized

    def test_sanitize_email_addresses(self, api_wrapper):
        """Verify email addresses show domain only."""
        error_msg = "Invalid credentials for user john.doe@example.com"
        sanitized = api_wrapper._sanitize_credentials(error_msg)

        # Username should be masked, domain preserved
        assert "john.doe" not in sanitized
        assert "***@example.com" in sanitized

    def test_sanitize_password_field(self, api_wrapper):
        """Verify password field values are masked."""
        error_msg = 'Failed to authenticate: password="SuperSecret123"'
        sanitized = api_wrapper._sanitize_credentials(error_msg)

        # Password value should be masked
        assert "SuperSecret123" not in sanitized
        assert "password=***REDACTED***" in sanitized

    def test_sanitize_api_token_field(self, api_wrapper):
        """Verify api_token field values are masked."""
        error_msg = "Config error: api_token=sk-abc123xyz456"
        sanitized = api_wrapper._sanitize_credentials(error_msg)

        # Token value should be masked
        assert "sk-abc123xyz456" not in sanitized
        assert "api_token=***REDACTED***" in sanitized

    def test_sanitize_authorization_header(self, api_wrapper):
        """Verify Authorization headers are masked."""
        error_msg = "Request failed with Authorization: Basic dXNlcjpwYXNz"
        sanitized = api_wrapper._sanitize_credentials(error_msg)

        # Auth header should be masked
        assert "dXNlcjpwYXNz" not in sanitized
        assert "Authorization: ***REDACTED***" in sanitized

    def test_sanitize_bearer_token(self, api_wrapper):
        """Verify Bearer tokens are masked."""
        error_msg = "API returned 401 with Bearer sk-abc123xyz456"
        sanitized = api_wrapper._sanitize_credentials(error_msg)

        # Bearer token should be masked
        assert "sk-abc123xyz456" not in sanitized
        assert "Bearer ***REDACTED***" in sanitized

    def test_sanitize_multiple_credentials(self, api_wrapper):
        """Verify multiple credentials in same message are all masked."""
        error_msg = (
            "Auth failed for user alice@example.com with token sk-abc123 "
            "to https://user:pass@test.com/api"
        )
        sanitized = api_wrapper._sanitize_credentials(error_msg)

        # All credentials should be masked
        assert "alice" not in sanitized
        assert "sk-abc123" not in sanitized
        assert "pass" not in sanitized
        assert "***@example.com" in sanitized
        assert "***:***@test.com" in sanitized

    def test_sanitize_preserves_safe_content(self, api_wrapper):
        """Verify sanitization preserves non-sensitive information."""
        error_msg = "Page 123456 not found in space DEV"
        sanitized = api_wrapper._sanitize_credentials(error_msg)

        # Safe content should be preserved
        assert sanitized == error_msg
        assert "123456" in sanitized
        assert "DEV" in sanitized

    def test_sanitize_empty_string(self, api_wrapper):
        """Verify empty strings are handled gracefully."""
        sanitized = api_wrapper._sanitize_credentials("")
        assert sanitized == ""

    def test_sanitize_none_returns_none(self, api_wrapper):
        """Verify None input returns None."""
        sanitized = api_wrapper._sanitize_credentials(None)
        assert sanitized is None

    @patch('src.confluence_client.api_wrapper.logger')
    def test_error_logging_uses_sanitization(self, mock_logger, api_wrapper):
        """Verify error logs don't contain credentials."""
        with patch('src.confluence_client.api_wrapper.Confluence') as MockConfluence:
            mock_client = Mock()
            # Simulate error with credentials in message
            mock_client.get_page_by_id.side_effect = Exception(
                "Auth failed with token sk-secret123abc456"
            )
            MockConfluence.return_value = mock_client

            try:
                api_wrapper.get_page_by_id("123456")
            except Exception:
                pass  # Expected

            # Check that logged error was sanitized
            assert mock_logger.error.called
            logged_msg = mock_logger.error.call_args[0][0]
            assert "sk-secret123abc456" not in logged_msg
            assert "***REDACTED***" in logged_msg

    def test_sanitize_multiline_credentials(self, api_wrapper):
        """Verify credentials across multiple lines are sanitized."""
        error_msg = """
        Authentication Error:
        User: admin@example.com
        Token: sk-abc123xyz456
        URL: https://user:pass@test.com
        """
        sanitized = api_wrapper._sanitize_credentials(error_msg)

        # All credentials should be masked
        assert "admin@example.com" not in sanitized
        assert "sk-abc123xyz456" not in sanitized
        assert "pass" not in sanitized
        assert "***@example.com" in sanitized

    def test_sanitize_json_with_credentials(self, api_wrapper):
        """Verify credentials in JSON-like strings are sanitized."""
        error_msg = '{"user": "admin@example.com", "token": "sk-abc123"}'
        sanitized = api_wrapper._sanitize_credentials(error_msg)

        # Credentials in JSON should be masked
        assert "admin@example.com" not in sanitized
        assert "sk-abc123" not in sanitized
        assert "***@example.com" in sanitized
