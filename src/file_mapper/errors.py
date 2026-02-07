"""Typed exception hierarchy for file mapper errors.

This module defines all custom exceptions used by the file mapper library.
All exceptions inherit from FileMapperError base class for easy catching and
include descriptive messages with context to help with debugging.
"""

from typing import Optional

from src.confluence_client.errors import SyncError


class FileMapperError(SyncError):
    """Base exception for all file mapper errors."""
    pass


class FilesystemError(FileMapperError):
    """Raised when filesystem operations fail (read, write, permissions, etc)."""

    def __init__(self, file_path: str, operation: str, reason: Optional[str] = None):
        message = f"Filesystem operation '{operation}' failed for {file_path}"
        if reason:
            message += f": {reason}"
        super().__init__(message)
        self.file_path = file_path
        self.operation = operation
        self.reason = reason


class ConfigError(FileMapperError):
    """Raised when configuration validation fails."""

    def __init__(self, message: str, config_field: Optional[str] = None):
        if config_field:
            full_message = f"Configuration error in field '{config_field}': {message}"
        else:
            full_message = f"Configuration error: {message}"
        super().__init__(full_message)
        self.config_field = config_field
        self.original_message = message


class FrontmatterError(FileMapperError):
    """Raised when YAML frontmatter parsing or validation fails."""

    def __init__(self, file_path: str, message: str):
        super().__init__(
            f"Frontmatter error in {file_path}: {message}"
        )
        self.file_path = file_path
        self.message = message


class PageLimitExceededError(FileMapperError):
    """Raised when the number of mapped pages exceeds the configured limit."""

    def __init__(self, current_count: int, limit: int):
        super().__init__(
            f"Page limit exceeded: {current_count} pages found, but limit is {limit}"
        )
        self.current_count = current_count
        self.limit = limit
