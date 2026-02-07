"""Test helper modules for Confluence testing.

This package provides utilities for E2E and integration testing:
- confluence_test_setup: Create/delete test pages on Confluence
- assertion_helpers: Custom assertions for content comparison
"""

from .confluence_test_setup import setup_test_page, teardown_test_page
from .assertion_helpers import (
    assert_xhtml_similar,
    assert_markdown_similar,
    normalize_whitespace,
)

__all__ = [
    'setup_test_page',
    'teardown_test_page',
    'assert_xhtml_similar',
    'assert_markdown_similar',
    'normalize_whitespace',
]
