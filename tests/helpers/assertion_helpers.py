"""Custom assertion helpers for XHTML and markdown comparison.

These helpers normalize whitespace and formatting differences to make
content comparisons more reliable in tests.
"""

import re
from typing import Any


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text for comparison.

    This function:
    1. Strips leading/trailing whitespace
    2. Collapses multiple spaces into single space
    3. Normalizes line endings to \n
    4. Removes blank lines

    Args:
        text: The text to normalize

    Returns:
        str: Normalized text with consistent whitespace

    Example:
        >>> normalize_whitespace("  Hello   World  \\n\\n")
        'Hello World'
    """
    if not text:
        return ""

    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Split into lines and strip each line
    lines = [line.strip() for line in text.split('\n')]

    # Remove blank lines
    lines = [line for line in lines if line]

    # Join lines and collapse multiple spaces
    result = ' '.join(lines)
    result = re.sub(r'\s+', ' ', result)

    return result.strip()


def assert_xhtml_similar(actual: str, expected: str, message: str = "") -> None:
    """Assert that two XHTML strings are similar (ignoring whitespace differences).

    This assertion normalizes whitespace before comparison to handle
    formatting differences that don't affect semantic meaning.

    Args:
        actual: The actual XHTML string
        expected: The expected XHTML string
        message: Optional custom error message

    Raises:
        AssertionError: If the XHTML strings differ (after normalization)

    Example:
        >>> assert_xhtml_similar("<p>  Hello  </p>", "<p>Hello</p>")
        >>> assert_xhtml_similar("<p>A</p>", "<p>B</p>")  # Raises AssertionError
    """
    actual_normalized = normalize_whitespace(actual)
    expected_normalized = normalize_whitespace(expected)

    if actual_normalized != expected_normalized:
        error_msg = f"XHTML mismatch:\nExpected:\n{expected_normalized}\n\nActual:\n{actual_normalized}"
        if message:
            error_msg = f"{message}\n{error_msg}"
        raise AssertionError(error_msg)


def assert_markdown_similar(actual: str, expected: str, message: str = "") -> None:
    """Assert that two markdown strings are similar (ignoring whitespace differences).

    This assertion normalizes whitespace before comparison to handle
    formatting differences that don't affect semantic meaning.

    Args:
        actual: The actual markdown string
        expected: The expected markdown string
        message: Optional custom error message

    Raises:
        AssertionError: If the markdown strings differ (after normalization)

    Example:
        >>> assert_markdown_similar("# Hello\\n\\nWorld", "# Hello\\nWorld")
        >>> assert_markdown_similar("# A", "# B")  # Raises AssertionError
    """
    actual_normalized = normalize_whitespace(actual)
    expected_normalized = normalize_whitespace(expected)

    if actual_normalized != expected_normalized:
        error_msg = f"Markdown mismatch:\nExpected:\n{expected_normalized}\n\nActual:\n{actual_normalized}"
        if message:
            error_msg = f"{message}\n{error_msg}"
        raise AssertionError(error_msg)


def assert_contains(haystack: Any, needle: Any, message: str = "") -> None:
    """Assert that haystack contains needle.

    Args:
        haystack: The container to search in
        needle: The item to search for
        message: Optional custom error message

    Raises:
        AssertionError: If needle is not in haystack

    Example:
        >>> assert_contains("Hello World", "World")
        >>> assert_contains([1, 2, 3], 2)
        >>> assert_contains("Hello", "Goodbye")  # Raises AssertionError
    """
    if needle not in haystack:
        error_msg = f"Expected to find '{needle}' in '{haystack}'"
        if message:
            error_msg = f"{message}\n{error_msg}"
        raise AssertionError(error_msg)


def assert_not_contains(haystack: Any, needle: Any, message: str = "") -> None:
    """Assert that haystack does not contain needle.

    Args:
        haystack: The container to search in
        needle: The item that should not be present
        message: Optional custom error message

    Raises:
        AssertionError: If needle is in haystack

    Example:
        >>> assert_not_contains("Hello World", "Goodbye")
        >>> assert_not_contains([1, 2, 3], 4)
        >>> assert_not_contains("Hello", "Hello")  # Raises AssertionError
    """
    if needle in haystack:
        error_msg = f"Expected not to find '{needle}' in '{haystack}'"
        if message:
            error_msg = f"{message}\n{error_msg}"
        raise AssertionError(error_msg)
