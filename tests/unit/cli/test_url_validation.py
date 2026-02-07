"""Unit tests for URL validation in InitCommand.

Tests M4: Missing URL validation - using urlparse() to validate URLs
and ensure scheme and netloc are present.
"""

import pytest
from unittest.mock import Mock, patch

from src.cli.init_command import InitCommand
from src.cli.errors import InitError


class TestURLValidation:
    """Test cases for URL validation (M4)."""

    @pytest.fixture
    def init_command(self):
        """Create an InitCommand instance with mocked API."""
        with patch('src.cli.init_command.APIWrapper'):
            return InitCommand()

    def test_valid_https_url_passes(self, init_command):
        """Verify valid HTTPS URLs pass validation."""
        url = "https://example.atlassian.net/wiki/spaces/TEST/pages/123456"

        # Should not raise exception
        init_command._validate_url(url)

    def test_valid_http_url_passes(self, init_command):
        """Verify valid HTTP URLs pass validation."""
        url = "http://example.atlassian.net/wiki/spaces/TEST/pages/123456"

        # Should not raise exception
        init_command._validate_url(url)

    def test_missing_scheme_rejected(self, init_command):
        """Verify URLs without scheme are rejected (CRITICAL TEST)."""
        url = "example.atlassian.net/wiki/spaces/TEST"

        with pytest.raises(InitError) as exc_info:
            init_command._validate_url(url)

        assert "scheme" in str(exc_info.value).lower()

    def test_invalid_scheme_rejected(self, init_command):
        """Verify URLs with invalid schemes are rejected."""
        url = "ftp://example.atlassian.net/wiki/spaces/TEST"

        with pytest.raises(InitError) as exc_info:
            init_command._validate_url(url)

        assert "scheme" in str(exc_info.value).lower()
        assert "http" in str(exc_info.value).lower()

    def test_missing_netloc_rejected(self, init_command):
        """Verify URLs without domain are rejected."""
        url = "https:///wiki/spaces/TEST"

        with pytest.raises(InitError) as exc_info:
            init_command._validate_url(url)

        assert "domain" in str(exc_info.value).lower()

    def test_empty_url_rejected(self, init_command):
        """Verify empty URLs are rejected."""
        with pytest.raises(InitError) as exc_info:
            init_command._validate_url("")

        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_url_rejected(self, init_command):
        """Verify whitespace-only URLs are rejected."""
        with pytest.raises(InitError) as exc_info:
            init_command._validate_url("   ")

        assert "empty" in str(exc_info.value).lower()

    def test_none_url_rejected(self, init_command):
        """Verify None URLs are rejected."""
        with pytest.raises(InitError):
            init_command._validate_url(None)

    def test_javascript_protocol_rejected(self, init_command):
        """Verify javascript: URLs are rejected (security)."""
        url = "javascript:alert('xss')"

        with pytest.raises(InitError) as exc_info:
            init_command._validate_url(url)

        assert "scheme" in str(exc_info.value).lower()

    def test_file_protocol_rejected(self, init_command):
        """Verify file:// URLs are rejected."""
        url = "file:///etc/passwd"

        with pytest.raises(InitError) as exc_info:
            init_command._validate_url(url)

        assert "scheme" in str(exc_info.value).lower()

    def test_data_uri_rejected(self, init_command):
        """Verify data: URIs are rejected."""
        url = "data:text/html,<script>alert('xss')</script>"

        with pytest.raises(InitError) as exc_info:
            init_command._validate_url(url)

        assert "scheme" in str(exc_info.value).lower()

    def test_url_with_port_passes(self, init_command):
        """Verify URLs with port numbers pass validation."""
        url = "https://example.com:8443/wiki/spaces/TEST"

        # Should not raise exception
        init_command._validate_url(url)

    def test_url_with_subdomain_passes(self, init_command):
        """Verify URLs with subdomains pass validation."""
        url = "https://team.example.atlassian.net/wiki/spaces/TEST"

        # Should not raise exception
        init_command._validate_url(url)

    def test_url_with_auth_passes(self, init_command):
        """Verify URLs with authentication info pass validation."""
        url = "https://user:pass@example.atlassian.net/wiki/spaces/TEST"

        # Should not raise exception
        init_command._validate_url(url)

    def test_url_with_query_params_passes(self, init_command):
        """Verify URLs with query parameters pass validation."""
        url = "https://example.atlassian.net/wiki/spaces/TEST?foo=bar"

        # Should not raise exception
        init_command._validate_url(url)

    def test_url_with_fragment_passes(self, init_command):
        """Verify URLs with fragments pass validation."""
        url = "https://example.atlassian.net/wiki/spaces/TEST#section"

        # Should not raise exception
        init_command._validate_url(url)

    def test_parse_confluence_url_validates_first(self, init_command):
        """Verify _parse_confluence_url calls validation."""
        # Invalid URL should fail validation before regex matching
        invalid_url = "not-a-url"

        with pytest.raises(InitError) as exc_info:
            init_command._parse_confluence_url(invalid_url)

        # Should fail at validation stage
        error_msg = str(exc_info.value).lower()
        assert "scheme" in error_msg or "domain" in error_msg

    def test_valid_confluence_url_parses_correctly(self, init_command):
        """Verify valid Confluence URLs are parsed after validation."""
        url = "https://example.atlassian.net/wiki/spaces/TEST/pages/123456"

        base_url, space_key, page_id = init_command._parse_confluence_url(url)

        # Should parse successfully
        assert "https://" in base_url
        assert space_key == "TEST"
        assert page_id == "123456"

    def test_malformed_url_structure_rejected(self, init_command):
        """Verify completely malformed URLs are rejected."""
        malformed_urls = [
            "ht!tp://invalid",
            "https://",
            "://example.com",
            "https//example.com",  # Missing colon
        ]

        for url in malformed_urls:
            with pytest.raises(InitError):
                init_command._validate_url(url)
