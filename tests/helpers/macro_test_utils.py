"""Macro test utilities for E2E tests.

NOTE: This is a TEST HELPER, not production code. The approach here
(converting macros to HTML comments) is the OLD approach from Epic 01.

The production code in page_operations/ uses a different approach:
surgical updates work directly on XHTML and never modify ac: elements,
preserving macros implicitly by not touching them.

This helper exists only to test the fetch journey workflow that was
implemented in Epic 01.
"""

from bs4 import BeautifulSoup, Tag, Comment
from typing import List, Dict


class MacroPreserver:
    """Test helper for macro preservation in fetch journey tests.

    WARNING: This is NOT how production code preserves macros.
    See module docstring for details.
    """

    def detect_macros(self, soup: BeautifulSoup) -> List[Tag]:
        """Detect all Confluence macros (ac: namespace elements)."""
        return soup.find_all(lambda tag: tag.name.startswith('ac:'))

    def preserve_as_comments(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Convert Confluence macros to HTML comments for preservation."""
        macros = self.detect_macros(soup)

        for macro in macros:
            macro_html = str(macro)
            comment_text = f" CONFLUENCE_MACRO: {macro_html} "
            comment = soup.new_string(comment_text, Comment)
            macro.replace_with(comment)

        return soup

    def restore_from_comments(self, html: str) -> str:
        """Restore Confluence macros from HTML comments."""
        soup = BeautifulSoup(html, 'lxml')

        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment_text = str(comment)

            if comment_text.strip().startswith('CONFLUENCE_MACRO:'):
                macro_html = comment_text.split('CONFLUENCE_MACRO:', 1)[1].strip()
                macro_soup = BeautifulSoup(macro_html, 'lxml')
                macro_element = macro_soup.find(lambda tag: tag.name.startswith('ac:'))

                if macro_element:
                    comment.replace_with(macro_element)

        body = soup.find('body')
        return str(body)[6:-7] if body else str(soup)

    def get_macro_types(self, soup: BeautifulSoup) -> Dict[str, int]:
        """Get counts of different macro types in the content."""
        macros = self.detect_macros(soup)
        macro_counts: Dict[str, int] = {}

        for macro in macros:
            macro_name = macro.name
            macro_counts[macro_name] = macro_counts.get(macro_name, 0) + 1

        return macro_counts
