"""Unit tests for file_mapper.errors module."""

import pytest
from src.file_mapper.errors import (
    FileMapperError,
    FilesystemError,
    ConfigError,
    FrontmatterError,
    PageLimitExceededError,
)


class TestFileMapperError:
    """Test cases for FileMapperError base exception."""

    def test_is_exception(self):
        """FileMapperError should inherit from Exception."""
        assert issubclass(FileMapperError, Exception)

    def test_can_be_raised(self):
        """FileMapperError can be raised and caught."""
        with pytest.raises(FileMapperError):
            raise FileMapperError("test error")

    def test_message_is_preserved(self):
        """FileMapperError preserves the error message."""
        with pytest.raises(FileMapperError) as exc_info:
            raise FileMapperError("custom message")
        assert str(exc_info.value) == "custom message"


class TestFilesystemError:
    """Test cases for FilesystemError."""

    def test_inherits_from_file_mapper_error(self):
        """FilesystemError should inherit from FileMapperError."""
        assert issubclass(FilesystemError, FileMapperError)

    def test_message_format_without_reason(self):
        """FilesystemError should format message with file_path and operation."""
        error = FilesystemError("/path/to/file.md", "read")
        assert "Filesystem operation 'read' failed for /path/to/file.md" == str(error)

    def test_message_format_with_reason(self):
        """FilesystemError should format message with file_path, operation, and reason."""
        error = FilesystemError("/path/to/file.md", "write", "Permission denied")
        assert "Filesystem operation 'write' failed for /path/to/file.md: Permission denied" == str(error)

    def test_stores_file_path_attribute(self):
        """FilesystemError should store file_path as attribute."""
        error = FilesystemError("/path/to/file.md", "read")
        assert error.file_path == "/path/to/file.md"

    def test_stores_operation_attribute(self):
        """FilesystemError should store operation as attribute."""
        error = FilesystemError("/path/to/file.md", "read")
        assert error.operation == "read"

    def test_stores_reason_attribute(self):
        """FilesystemError should store reason as attribute."""
        error = FilesystemError("/path/to/file.md", "write", "Permission denied")
        assert error.reason == "Permission denied"

    def test_reason_defaults_to_none(self):
        """FilesystemError reason defaults to None."""
        error = FilesystemError("/path/to/file.md", "read")
        assert error.reason is None


class TestConfigError:
    """Test cases for ConfigError."""

    def test_inherits_from_file_mapper_error(self):
        """ConfigError should inherit from FileMapperError."""
        assert issubclass(ConfigError, FileMapperError)

    def test_message_without_config_field(self):
        """ConfigError message without config_field."""
        error = ConfigError("Invalid configuration")
        assert str(error) == "Configuration error: Invalid configuration"

    def test_message_with_config_field(self):
        """ConfigError message with config_field."""
        error = ConfigError("Value must be positive", "page_limit")
        assert str(error) == "Configuration error in field 'page_limit': Value must be positive"

    def test_stores_config_field_attribute(self):
        """ConfigError should store config_field as attribute."""
        error = ConfigError("Value must be positive", "page_limit")
        assert error.config_field == "page_limit"

    def test_stores_original_message_attribute(self):
        """ConfigError should store original_message as attribute."""
        error = ConfigError("Value must be positive", "page_limit")
        assert error.original_message == "Value must be positive"

    def test_config_field_defaults_to_none(self):
        """ConfigError config_field defaults to None."""
        error = ConfigError("Invalid configuration")
        assert error.config_field is None


class TestFrontmatterError:
    """Test cases for FrontmatterError."""

    def test_inherits_from_file_mapper_error(self):
        """FrontmatterError should inherit from FileMapperError."""
        assert issubclass(FrontmatterError, FileMapperError)

    def test_message_format(self):
        """FrontmatterError should format message with file_path and message."""
        error = FrontmatterError("/path/to/file.md", "Missing required field: page_id")
        assert str(error) == "Frontmatter error in /path/to/file.md: Missing required field: page_id"

    def test_stores_file_path_attribute(self):
        """FrontmatterError should store file_path as attribute."""
        error = FrontmatterError("/path/to/file.md", "Invalid YAML")
        assert error.file_path == "/path/to/file.md"

    def test_stores_message_attribute(self):
        """FrontmatterError should store message as attribute."""
        error = FrontmatterError("/path/to/file.md", "Invalid YAML")
        assert error.message == "Invalid YAML"


class TestPageLimitExceededError:
    """Test cases for PageLimitExceededError."""

    def test_inherits_from_file_mapper_error(self):
        """PageLimitExceededError should inherit from FileMapperError."""
        assert issubclass(PageLimitExceededError, FileMapperError)

    def test_message_format(self):
        """PageLimitExceededError should format message with current_count and limit."""
        error = PageLimitExceededError(150, 100)
        assert str(error) == "Page limit exceeded: 150 pages found, but limit is 100"

    def test_stores_current_count_attribute(self):
        """PageLimitExceededError should store current_count as attribute."""
        error = PageLimitExceededError(150, 100)
        assert error.current_count == 150

    def test_stores_limit_attribute(self):
        """PageLimitExceededError should store limit as attribute."""
        error = PageLimitExceededError(150, 100)
        assert error.limit == 100
