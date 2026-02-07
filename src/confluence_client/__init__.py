"""Confluence client library for bidirectional sync.

This package provides Python abstractions over the Confluence Cloud REST API v2,
enabling clean and type-safe interactions with Confluence pages.
"""

from .errors import (
    SyncError,
    ConfluenceError,
    InvalidCredentialsError,
    PageNotFoundError,
    PageAlreadyExistsError,
    APIUnreachableError,
    APIAccessError,
    ConversionError,
)

__all__ = [
    "SyncError",
    "ConfluenceError",
    "InvalidCredentialsError",
    "PageNotFoundError",
    "PageAlreadyExistsError",
    "APIUnreachableError",
    "APIAccessError",
    "ConversionError",
]
