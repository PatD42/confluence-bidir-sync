"""Typed exception hierarchy for CLI-related errors.

This module defines all custom exceptions used by the CLI.
All exceptions inherit from CLIError base class for easy catching and
include descriptive messages with context to help with debugging.
"""

from typing import Optional

from src.confluence_client.errors import SyncError


class CLIError(SyncError):
    """Base exception for all CLI-related errors."""
    pass


class ConfigNotFoundError(CLIError):
    """Raised when configuration file is not found."""

    def __init__(self, config_path: str):
        super().__init__(
            f"Configuration file not found at {config_path}"
        )
        self.config_path = config_path


class InitError(CLIError):
    """Raised when initialization fails."""

    def __init__(self, message: str):
        super().__init__(message)


class StateError(CLIError):
    """Raised when state file operations or validation fail."""

    def __init__(self, message: str, state_field: Optional[str] = None):
        if state_field:
            full_message = f"State error in field '{state_field}': {message}"
        else:
            full_message = f"State error: {message}"
        super().__init__(full_message)
        self.state_field = state_field
        self.original_message = message


class StateFilesystemError(CLIError):
    """Raised when state file filesystem operations fail."""

    def __init__(self, file_path: str, operation: str, reason: Optional[str] = None):
        message = f"State file operation '{operation}' failed for {file_path}"
        if reason:
            message += f": {reason}"
        super().__init__(message)
        self.file_path = file_path
        self.operation = operation
        self.reason = reason
