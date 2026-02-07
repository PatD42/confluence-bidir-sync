"""Macro preserver for Confluence content conversion.

This module provides the MacroPreserver class which handles preservation
of Confluence macros during XHTML-to-markdown conversion and restoration
during markdown-to-XHTML conversion.

Special handling is provided for inline comment markers (ac:inline-comment-marker)
which contain visible text that should appear in the markdown while preserving
the comment reference for restoration.
"""

import logging
from dataclasses import dataclass
from typing import List, Tuple

from bs4 import BeautifulSoup, Comment, NavigableString

logger = logging.getLogger(__name__)


@dataclass
class MacroInfo:
    """Information about a preserved macro.

    Attributes:
        placeholder: Placeholder string used in markdown
        html: Original HTML of the macro
        name: Macro name (ac:macro-name or macro name attribute)
        macro_type: Type of macro ('inline-comment' or 'block-macro')
        ref: Reference ID for inline comments (optional)
        text: Text content for inline comments (optional)
    """

    placeholder: str
    html: str
    name: str
    macro_type: str
    ref: str = ""
    text: str = ""


class MacroPreserver:
    """Preserves Confluence macros during content conversion.

    Handles two categories of macros differently:

    1. Inline comment markers (ac:inline-comment-marker):
       - Contain visible text that should appear in markdown
       - Text is extracted and kept visible
       - Marker info is stored for potential restoration

    2. Block macros (other ac: elements):
       - Replaced with placeholder comments
       - Fully restored during markdown-to-XHTML conversion

    This enables round-trip conversion while preserving both the user's
    edits and Confluence-specific functionality.
    """

    def __init__(self):
        """Initialize MacroPreserver."""
        self.parser = "lxml"

    def preserve_macros(self, xhtml: str) -> Tuple[str, List[MacroInfo]]:
        """Replace macros with placeholders, preserving inline comment text.

        Inline comment markers are handled specially - their text content
        is preserved in the output while storing the marker info for
        potential restoration.

        Args:
            xhtml: Confluence XHTML content

        Returns:
            Tuple of (processed XHTML, list of MacroInfo objects)
        """
        soup = BeautifulSoup(xhtml, self.parser)
        macros: List[MacroInfo] = []
        placeholder_index = 0

        # First pass: handle inline comment markers specially
        # These contain text that should be visible in markdown
        for tag in list(soup.find_all("ac:inline-comment-marker")):
            ref = tag.get("ac:ref", "")
            text_content = tag.get_text()

            macros.append(
                MacroInfo(
                    placeholder=f"INLINE_COMMENT_{placeholder_index}",
                    html=str(tag),
                    name="ac:inline-comment-marker",
                    macro_type="inline-comment",
                    ref=ref,
                    text=text_content,
                )
            )

            # Replace marker with just its text content (preserve the text!)
            tag.replace_with(NavigableString(text_content))
            placeholder_index += 1

        # Second pass: handle other ac: elements (block macros)
        for tag in list(soup.find_all(True)):
            if tag.name and tag.name.startswith("ac:"):
                # Skip nested macros (already handled with parent)
                if tag.parent and tag.parent.name and tag.parent.name.startswith("ac:"):
                    continue

                macro_html = str(tag)
                placeholder = f"CONFLUENCE_MACRO_PLACEHOLDER_{placeholder_index}"

                macros.append(
                    MacroInfo(
                        placeholder=placeholder,
                        html=macro_html,
                        name=tag.get("ac:name", tag.name),
                        macro_type="block-macro",
                    )
                )

                # Replace macro with HTML comment placeholder
                comment = Comment(f" {placeholder} ")
                tag.replace_with(comment)
                placeholder_index += 1

        # Extract body content
        body = soup.find("body")
        if body:
            result = "".join(str(child) for child in body.children)
        else:
            result = str(soup)

        logger.debug(f"Preserved {len(macros)} macros ({sum(1 for m in macros if m.macro_type == 'inline-comment')} inline comments)")
        return result, macros

    def restore_macros(self, xhtml: str, macros: List[MacroInfo]) -> str:
        """Restore macros from placeholders.

        Note: Inline comment markers that had their text edited will NOT
        be fully restored as the original marker wrapped specific text.
        Block macros are always fully restored.

        Args:
            xhtml: XHTML with placeholders
            macros: List of MacroInfo objects from preserve_macros

        Returns:
            XHTML with macros restored
        """
        result = xhtml

        for macro in macros:
            if macro.macro_type == "inline-comment":
                # Inline comments are special - text was preserved, not replaced
                # We don't restore the marker as the text may have been edited
                # and the marker would be invalid
                logger.debug(f"Skipping inline comment restoration for ref={macro.ref}")
                continue

            # Block macro restoration
            placeholder = macro.placeholder
            macro_html = macro.html

            # Try various placeholder formats
            patterns = [
                f"<!-- {placeholder} -->",
                f"<!--{placeholder}-->",
                placeholder,
            ]

            for pattern in patterns:
                if pattern in result:
                    result = result.replace(pattern, macro_html)
                    logger.debug(f"Restored macro: {macro.name}")
                    break

        return result

    def count_inline_comments(self, xhtml: str) -> int:
        """Count inline comment markers in XHTML.

        Useful for verifying inline comments are preserved after operations.

        Args:
            xhtml: XHTML content to count markers in

        Returns:
            Number of ac:inline-comment-marker elements found
        """
        soup = BeautifulSoup(xhtml, self.parser)
        return len(soup.find_all("ac:inline-comment-marker"))

    def extract_inline_comments(self, xhtml: str) -> List[dict]:
        """Extract inline comment information from XHTML.

        Args:
            xhtml: XHTML content

        Returns:
            List of dicts with 'ref' and 'text' for each inline comment
        """
        soup = BeautifulSoup(xhtml, self.parser)
        comments = []

        for marker in soup.find_all("ac:inline-comment-marker"):
            comments.append(
                {
                    "ref": marker.get("ac:ref", ""),
                    "text": marker.get_text(),
                }
            )

        return comments
