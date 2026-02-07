"""Unit tests for confluence_client.errors module."""

import pytest
from src.confluence_client.errors import (
    ConfluenceError,
    InvalidCredentialsError,
    PageNotFoundError,
    PageAlreadyExistsError,
    APIUnreachableError,
    APIAccessError,
    ConversionError,
)


class TestConfluenceError:
    """Test cases for ConfluenceError base exception."""

    def test_is_exception(self):
        """ConfluenceError should inherit from Exception."""
        assert issubclass(ConfluenceError, Exception)

    def test_can_be_raised(self):
        """ConfluenceError can be raised and caught."""
        with pytest.raises(ConfluenceError):
            raise ConfluenceError("test error")

    def test_message_is_preserved(self):
        """ConfluenceError preserves the error message."""
        with pytest.raises(ConfluenceError) as exc_info:
            raise ConfluenceError("custom message")
        assert str(exc_info.value) == "custom message"


class TestInvalidCredentialsError:
    """Test cases for InvalidCredentialsError."""

    def test_inherits_from_confluence_error(self):
        """InvalidCredentialsError should inherit from ConfluenceError."""
        assert issubclass(InvalidCredentialsError, ConfluenceError)

    def test_message_format(self):
        """InvalidCredentialsError should format message with user and endpoint."""
        error = InvalidCredentialsError("test@example.com", "https://example.atlassian.net")
        assert "API key is invalid" in str(error)
        assert "test@example.com" in str(error)
        assert "https://example.atlassian.net" in str(error)

    def test_stores_user_attribute(self):
        """InvalidCredentialsError should store user as attribute."""
        error = InvalidCredentialsError("test@example.com", "https://example.atlassian.net")
        assert error.user == "test@example.com"

    def test_stores_endpoint_attribute(self):
        """InvalidCredentialsError should store endpoint as attribute."""
        error = InvalidCredentialsError("test@example.com", "https://example.atlassian.net")
        assert error.endpoint == "https://example.atlassian.net"


class TestPageNotFoundError:
    """Test cases for PageNotFoundError."""

    def test_inherits_from_confluence_error(self):
        """PageNotFoundError should inherit from ConfluenceError."""
        assert issubclass(PageNotFoundError, ConfluenceError)

    def test_message_format(self):
        """PageNotFoundError should format message with page_id."""
        error = PageNotFoundError("12345")
        assert "Page 12345 not found" == str(error)

    def test_stores_page_id_attribute(self):
        """PageNotFoundError should store page_id as attribute."""
        error = PageNotFoundError("12345")
        assert error.page_id == "12345"


class TestPageAlreadyExistsError:
    """Test cases for PageAlreadyExistsError."""

    def test_inherits_from_confluence_error(self):
        """PageAlreadyExistsError should inherit from ConfluenceError."""
        assert issubclass(PageAlreadyExistsError, ConfluenceError)

    def test_message_without_parent(self):
        """PageAlreadyExistsError message without parent_id."""
        error = PageAlreadyExistsError("Test Page")
        assert str(error) == "Page with title 'Test Page' already exists"

    def test_message_with_parent(self):
        """PageAlreadyExistsError message with parent_id."""
        error = PageAlreadyExistsError("Test Page", "67890")
        assert str(error) == "Page with title 'Test Page' already exists under parent 67890"

    def test_stores_title_attribute(self):
        """PageAlreadyExistsError should store title as attribute."""
        error = PageAlreadyExistsError("Test Page")
        assert error.title == "Test Page"

    def test_stores_parent_id_attribute(self):
        """PageAlreadyExistsError should store parent_id as attribute."""
        error = PageAlreadyExistsError("Test Page", "67890")
        assert error.parent_id == "67890"

    def test_parent_id_defaults_to_none(self):
        """PageAlreadyExistsError parent_id defaults to None."""
        error = PageAlreadyExistsError("Test Page")
        assert error.parent_id is None


class TestAPIUnreachableError:
    """Test cases for APIUnreachableError."""

    def test_inherits_from_confluence_error(self):
        """APIUnreachableError should inherit from ConfluenceError."""
        assert issubclass(APIUnreachableError, ConfluenceError)

    def test_message_format(self):
        """APIUnreachableError should format message with endpoint."""
        error = APIUnreachableError("https://example.atlassian.net")
        assert "API is not available at https://example.atlassian.net" == str(error)

    def test_stores_endpoint_attribute(self):
        """APIUnreachableError should store endpoint as attribute."""
        error = APIUnreachableError("https://example.atlassian.net")
        assert error.endpoint == "https://example.atlassian.net"


class TestAPIAccessError:
    """Test cases for APIAccessError."""

    def test_inherits_from_confluence_error(self):
        """APIAccessError should inherit from ConfluenceError."""
        assert issubclass(APIAccessError, ConfluenceError)

    def test_default_message(self):
        """APIAccessError should have default message for retry exhaustion."""
        error = APIAccessError()
        assert str(error) == "Confluence API failure (after 3 retries)"

    def test_custom_message(self):
        """APIAccessError should accept custom message."""
        error = APIAccessError("Custom access error")
        assert str(error) == "Custom access error"


class TestConversionError:
    """Test cases for ConversionError."""

    def test_inherits_from_confluence_error(self):
        """ConversionError should inherit from ConfluenceError."""
        assert issubclass(ConversionError, ConfluenceError)

    def test_message_is_preserved(self):
        """ConversionError should preserve custom message."""
        error = ConversionError("Failed to convert XHTML to markdown")
        assert str(error) == "Failed to convert XHTML to markdown"
