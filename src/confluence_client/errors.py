"""Typed exception hierarchy for Confluence-related errors.

This module defines all custom exceptions used by the Confluence client library.
All exceptions inherit from ConfluenceError base class for easy catching and
include descriptive messages with context to help with debugging.
"""

from typing import Optional


class SyncError(Exception):
    """Base exception for all confluence-bidir-sync errors.

    Use this to catch any application-level error from the sync tool.
    """
    pass


class ConfluenceError(SyncError):
    """Base exception for all Confluence-related errors."""
    pass


class InvalidCredentialsError(ConfluenceError):
    """Raised when API credentials are invalid or authentication fails."""

    def __init__(self, user: str, endpoint: str):
        super().__init__(
            f"API key is invalid (user: {user}, endpoint: {endpoint})"
        )
        self.user = user
        self.endpoint = endpoint


class PageNotFoundError(ConfluenceError):
    """Raised when a requested page does not exist."""

    def __init__(self, page_id: str):
        super().__init__(f"Page {page_id} not found")
        self.page_id = page_id


class PageAlreadyExistsError(ConfluenceError):
    """Raised when attempting to create a page with a duplicate title."""

    def __init__(self, title: str, parent_id: Optional[str] = None):
        if parent_id:
            message = f"Page with title '{title}' already exists under parent {parent_id}"
        else:
            message = f"Page with title '{title}' already exists"
        super().__init__(message)
        self.title = title
        self.parent_id = parent_id


class APIUnreachableError(ConfluenceError):
    """Raised when the Confluence API is not available or unreachable."""

    def __init__(self, endpoint: str):
        super().__init__(f"API is not available at {endpoint}")
        self.endpoint = endpoint


class APIAccessError(ConfluenceError):
    """Raised when API access fails after retries or due to access restrictions."""

    def __init__(self, message: str = "Confluence API failure (after 3 retries)"):
        super().__init__(message)


class ConversionError(ConfluenceError):
    """Raised when content conversion between formats fails."""

    def __init__(self, message: str):
        super().__init__(message)
