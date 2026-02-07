"""Unit tests for page ID validation in APIWrapper.

Tests C2: Page ID validation to prevent injection attacks.
"""

import pytest

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator


class TestPageIDValidation:
    """Test cases for page ID validation (C2)."""

    @pytest.fixture
    def api_wrapper(self, mocker):
        """Create an APIWrapper instance with mocked authentication."""
        mock_auth = mocker.Mock(spec=Authenticator)
        mock_auth.get_credentials.return_value = mocker.Mock(
            url="https://test.atlassian.net/wiki",
            user="test@example.com",
            api_token="fake-token"
        )
        return APIWrapper(mock_auth)

    def test_validate_numeric_page_id(self, api_wrapper):
        """Verify that valid numeric page IDs are accepted."""
        # Valid page IDs should not raise exception
        api_wrapper._validate_page_id("123456")
        api_wrapper._validate_page_id("789")
        api_wrapper._validate_page_id("1")
        api_wrapper._validate_page_id("9876543210")

    def test_reject_empty_page_id(self, api_wrapper):
        """Verify that empty page IDs are rejected."""
        with pytest.raises(ValueError) as exc_info:
            api_wrapper._validate_page_id("")

        assert "page_id cannot be empty" in str(exc_info.value)

    def test_reject_whitespace_only_page_id(self, api_wrapper):
        """Verify that whitespace-only page IDs are rejected."""
        with pytest.raises(ValueError) as exc_info:
            api_wrapper._validate_page_id("   ")

        assert "page_id cannot be empty" in str(exc_info.value)

    def test_reject_sql_injection_attempt(self, api_wrapper):
        """Verify that SQL injection attempts are rejected (CRITICAL TEST)."""
        malicious_ids = [
            "'; DROP TABLE pages--",
            "123' OR '1'='1",
            "123; DELETE FROM pages;--",
            "123' UNION SELECT * FROM users--",
        ]

        for malicious_id in malicious_ids:
            with pytest.raises(ValueError) as exc_info:
                api_wrapper._validate_page_id(malicious_id)

            assert "Invalid page_id format" in str(exc_info.value)
            assert "must contain only numeric characters" in str(exc_info.value)

    def test_reject_path_traversal_attempt(self, api_wrapper):
        """Verify that path traversal attempts are rejected."""
        traversal_attempts = [
            "../../../etc/passwd",
            "../../config",
            "../secret",
        ]

        for attempt in traversal_attempts:
            with pytest.raises(ValueError) as exc_info:
                api_wrapper._validate_page_id(attempt)

            assert "Invalid page_id format" in str(exc_info.value)

    def test_reject_script_injection_attempt(self, api_wrapper):
        """Verify that script injection attempts are rejected."""
        script_attempts = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "123<script>",
            "javascript:alert(1)",
        ]

        for attempt in script_attempts:
            with pytest.raises(ValueError) as exc_info:
                api_wrapper._validate_page_id(attempt)

            assert "Invalid page_id format" in str(exc_info.value)

    def test_reject_alphanumeric_page_id(self, api_wrapper):
        """Verify that alphanumeric page IDs are rejected."""
        with pytest.raises(ValueError) as exc_info:
            api_wrapper._validate_page_id("abc123")

        assert "Invalid page_id format" in str(exc_info.value)
        assert "must contain only numeric characters" in str(exc_info.value)

    def test_reject_special_characters(self, api_wrapper):
        """Verify that special characters in page IDs are rejected."""
        invalid_ids = [
            "123!",
            "123@456",
            "123#456",
            "123$",
            "123%",
            "123^",
            "123&",
            "123*",
            "123()",
            "123-456",
            "123_456",
            "123.456",
            "123,456",
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(ValueError) as exc_info:
                api_wrapper._validate_page_id(invalid_id)

            assert "Invalid page_id format" in str(exc_info.value)

    def test_get_page_by_id_validates_input(self, api_wrapper, mocker):
        """Integration test: get_page_by_id validates page ID."""
        # Mock the underlying Confluence client
        mock_client = mocker.Mock()
        mocker.patch.object(api_wrapper, '_get_client', return_value=mock_client)

        with pytest.raises(ValueError) as exc_info:
            api_wrapper.get_page_by_id("'; DROP TABLE--")

        assert "Invalid page_id format" in str(exc_info.value)
        # API should not be called
        mock_client.get_page_by_id.assert_not_called()

    def test_get_page_version_validates_input(self, api_wrapper, mocker):
        """Integration test: get_page_version validates page ID."""
        mock_client = mocker.Mock()
        mocker.patch.object(api_wrapper, '_get_client', return_value=mock_client)

        with pytest.raises(ValueError) as exc_info:
            api_wrapper.get_page_version("../../../config", 1)

        assert "Invalid page_id format" in str(exc_info.value)
        mock_client.get.assert_not_called()

    def test_update_page_validates_input(self, api_wrapper, mocker):
        """Integration test: update_page validates page ID."""
        mock_client = mocker.Mock()
        mocker.patch.object(api_wrapper, '_get_client', return_value=mock_client)

        with pytest.raises(ValueError) as exc_info:
            api_wrapper.update_page(
                page_id="<script>alert('xss')</script>",
                title="Test",
                body="Content",
                version=1
            )

        assert "Invalid page_id format" in str(exc_info.value)
        mock_client.update_page.assert_not_called()

    def test_delete_page_validates_input(self, api_wrapper, mocker):
        """Integration test: delete_page validates page ID."""
        mock_client = mocker.Mock()
        mocker.patch.object(api_wrapper, '_get_client', return_value=mock_client)

        with pytest.raises(ValueError) as exc_info:
            api_wrapper.delete_page("123; rm -rf /")

        assert "Invalid page_id format" in str(exc_info.value)
        mock_client.remove_page.assert_not_called()

    def test_get_page_child_by_type_validates_input(self, api_wrapper, mocker):
        """Integration test: get_page_child_by_type validates page ID."""
        mock_client = mocker.Mock()
        mocker.patch.object(api_wrapper, '_get_client', return_value=mock_client)

        with pytest.raises(ValueError) as exc_info:
            api_wrapper.get_page_child_by_type("abc123")

        assert "Invalid page_id format" in str(exc_info.value)
        mock_client.get_page_child_by_type.assert_not_called()

    def test_get_page_adf_validates_input(self, api_wrapper, mocker):
        """Integration test: get_page_adf validates page ID."""
        mock_client = mocker.Mock()
        mocker.patch.object(api_wrapper, '_get_client', return_value=mock_client)

        with pytest.raises(ValueError) as exc_info:
            api_wrapper.get_page_adf("malicious' OR '1'='1")

        assert "Invalid page_id format" in str(exc_info.value)
        mock_client.get_page_by_id.assert_not_called()

    def test_update_page_adf_validates_input(self, api_wrapper, mocker):
        """Integration test: update_page_adf validates page ID."""
        mock_client = mocker.Mock()
        mocker.patch.object(api_wrapper, '_get_client', return_value=mock_client)

        with pytest.raises(ValueError) as exc_info:
            api_wrapper.update_page_adf(
                page_id="123'; DROP TABLE pages;--",
                title="Test",
                adf_content={"type": "doc"},
                version=1
            )

        assert "Invalid page_id format" in str(exc_info.value)
        mock_client.update.assert_not_called()
