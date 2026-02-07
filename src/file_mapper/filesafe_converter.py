"""Filesafe filename conversion with case preservation.

This module converts Confluence page titles to valid filenames that are safe
for all file systems while preserving the original case (ADR-010).
"""

import re


class FilesafeConverter:
    """Converts Confluence page titles to filesafe filenames with case preservation.

    Implements ADR-010: Filesafe conversion with case preservation.

    Conversion rules:
    - Spaces → hyphens (-)
    - Colons (:) → double hyphens (--)
    - Special characters (/, \\, ?, %, *, |, ", <, >, &) → hyphens (-)
    - Leading/trailing spaces/hyphens → trimmed
    - Multiple consecutive hyphens → collapsed to single hyphen
    - Case is preserved exactly as in original title
    - .md extension is appended

    Examples:
        - "Customer Feedback" → "Customer-Feedback.md"
        - "API Reference: Getting Started" → "API-Reference--Getting-Started.md"
        - "Q&A Session" → "Q-A-Session.md"
    """

    @staticmethod
    def title_to_filename(title: str) -> str:
        """Convert a Confluence page title to a filesafe filename.

        Args:
            title: The Confluence page title

        Returns:
            A filesafe filename with .md extension

        Examples:
            >>> FilesafeConverter.title_to_filename("Customer Feedback")
            'Customer-Feedback.md'
            >>> FilesafeConverter.title_to_filename("API Reference: Getting Started")
            'API-Reference--Getting-Started.md'
            >>> FilesafeConverter.title_to_filename("Q&A Session")
            'Q-A-Session.md'
        """
        # First, replace ": " (colon followed by space) with "--"
        # This preserves the double hyphen for colons in the final output
        filename = title.replace(': ', '--')

        # Replace any remaining colons (without spaces) with double hyphens
        filename = filename.replace(':', '--')

        # Replace spaces with single hyphens
        filename = filename.replace(' ', '-')

        # Replace other special characters with hyphens
        # These are characters that are invalid or problematic on various file systems:
        # / \ ? % * | " < > &
        special_chars = r'[/\\?%*|"<>&]'
        filename = re.sub(special_chars, '-', filename)

        # Collapse three or more consecutive hyphens into two hyphens
        # This preserves double hyphens from colons while cleaning up excessive hyphens
        filename = re.sub(r'-{3,}', '--', filename)

        # Remove leading and trailing hyphens
        filename = filename.strip('-')

        # Append .md extension
        return f"{filename}.md"

    @staticmethod
    def filename_to_title(filename: str) -> str:
        """Convert a filesafe filename back to a title (best effort).

        Note: This is a lossy conversion - we cannot distinguish between
        "--" from a colon vs two consecutive hyphens in the original title.

        Args:
            filename: The filesafe filename (with or without .md extension)

        Returns:
            The reconstructed title (may not match original exactly)

        Examples:
            >>> FilesafeConverter.filename_to_title("Customer-Feedback.md")
            'Customer Feedback'
            >>> FilesafeConverter.filename_to_title("API-Reference--Getting-Started.md")
            'API Reference: Getting Started'
        """
        # Remove .md extension if present
        if filename.endswith('.md'):
            filename = filename[:-3]

        # Replace double hyphens with colons
        title = filename.replace('--', ':')

        # Replace single hyphens with spaces
        title = title.replace('-', ' ')

        return title
