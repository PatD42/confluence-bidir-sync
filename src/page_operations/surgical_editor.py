"""Surgical editor for applying operations to XHTML.

This module provides the SurgicalEditor class which applies surgical
operations to Confluence XHTML content while preserving all Confluence-specific
formatting (macros, labels, local-ids, table structure).
"""

import ast
import logging
import re
from typing import List

from bs4 import BeautifulSoup, NavigableString

from .models import OperationType, SurgicalOperation

logger = logging.getLogger(__name__)


class SurgicalEditor:
    """Applies surgical operations to Confluence XHTML.

    The surgical editor modifies XHTML content by applying discrete
    operations (update, delete, insert) while preserving Confluence-specific
    elements like macros, labels, and local-ids.

    Key principle: Never modify macro content (ac: namespace elements).
    Only modify regular HTML elements based on content matching.
    """

    def __init__(self):
        """Initialize SurgicalEditor with html.parser.

        Uses Python's built-in html.parser instead of lxml to prevent
        XXE (XML External Entity) attacks (M3: Parser security).
        """
        self.parser = "html.parser"

    def apply_operations(
        self, xhtml: str, operations: List[SurgicalOperation]
    ) -> tuple:
        """Apply all surgical operations to XHTML content.

        Args:
            xhtml: Original Confluence XHTML content
            operations: List of operations to apply

        Returns:
            Tuple of (modified XHTML, success count, failure count)
        """
        soup = BeautifulSoup(xhtml, self.parser)
        success_count = 0
        failure_count = 0

        for op in operations:
            logger.info(f"Applying operation: {op.op_type.value}")
            success = False

            if op.op_type == OperationType.UPDATE_TEXT:
                success = self._update_text(soup, op.target_content, op.new_content)

            elif op.op_type == OperationType.DELETE_BLOCK:
                success = self._delete_block(soup, op.target_content)

            elif op.op_type == OperationType.INSERT_BLOCK:
                success = self._insert_block(soup, op.new_content, op.after_content)

            elif op.op_type == OperationType.CHANGE_HEADING_LEVEL:
                success = self._change_heading_level(
                    soup, op.target_content, op.old_level, op.new_level, op.new_content
                )

            elif op.op_type == OperationType.TABLE_INSERT_ROW:
                success = self._table_insert_row(
                    soup, op.target_content, op.new_content, op.row_index
                )

            elif op.op_type == OperationType.TABLE_DELETE_ROW:
                success = self._table_delete_row(soup, op.target_content, op.row_index)

            elif op.op_type == OperationType.TABLE_UPDATE_CELL:
                success = self._table_update_cell(
                    soup,
                    op.target_content,
                    op.new_content,
                    op.row_index,
                    op.cell_index,
                )

            if success:
                success_count += 1
            else:
                failure_count += 1

        # Return body content (lxml wraps in html/body)
        body = soup.find("body")
        if body:
            result = "".join(str(child) for child in body.children)
        else:
            result = str(soup)

        return result, success_count, failure_count

    def _update_text(
        self, soup: BeautifulSoup, target: str, new_text: str
    ) -> bool:
        """Update text content within an element.

        Finds the MOST SPECIFIC element containing the target text and replaces
        it with new text. "Most specific" means the element with the shortest
        text that still contains the target - this prevents modifying a parent
        <div> when we should modify the <li> inside it.

        Handles text that may span across inline comment markers by
        normalizing whitespace for comparison.

        Args:
            soup: BeautifulSoup object to modify
            target: Text to find and replace
            new_text: Replacement text

        Returns:
            True if text was updated, False otherwise
        """
        # Normalize target for comparison (collapse whitespace)
        target_normalized = " ".join(target.split())

        # Search through relevant elements
        searchable_tags = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "span", "div"]

        # Collect all matching elements with their text lengths
        candidates = []
        for element in soup.find_all(searchable_tags):
            # Skip macro containers but search inside inline comment markers
            if element.name and element.name.startswith("ac:"):
                if element.name != "ac:inline-comment-marker":
                    continue

            # Get full text with separator to preserve spacing around inline elements
            full_text = element.get_text(separator=" ", strip=True)
            full_text_normalized = " ".join(full_text.split())
            # Remove spaces before punctuation (artifact of separator between tags)
            full_text_normalized = re.sub(r"\s+([,:;.!?])", r"\1", full_text_normalized)

            if target_normalized in full_text_normalized:
                candidates.append((element, len(full_text_normalized)))

        if not candidates:
            logger.warning(f"  Target text not found: {target[:50]}...")
            return False

        # Select the most specific element (shortest text that contains target)
        # This ensures we modify <li> instead of its parent <div>
        candidates.sort(key=lambda x: x[1])
        best_element = candidates[0][0]

        self._replace_text_in_element(best_element, target, new_text)
        logger.info(f"  Updated text in <{best_element.name}>")
        return True

    def _replace_text_in_element(
        self, element, target: str, new_text: str
    ) -> None:
        """Replace target text within an element, handling inline comment markers.

        Tries multiple strategies to replace text while preserving structure:
        1. Direct text nodes in the element
        2. Text inside inline comment markers (ac:inline-comment-marker)
        3. Text inside other inline elements (strong, em, etc.)
        4. Any text node anywhere in the element tree
        5. Last resort: replace entire element content (loses formatting)

        Args:
            element: BeautifulSoup element to modify
            target: Text to replace
            new_text: Replacement text
        """
        # Normalize target for matching
        target_normalized = " ".join(target.split())
        target_normalized = re.sub(r"\s+([,:;.!?])", r"\1", target_normalized)

        # Strategy 1: Try direct text nodes
        for text_node in element.find_all(string=True, recursive=False):
            text_str = str(text_node)
            text_normalized = " ".join(text_str.split())
            text_normalized = re.sub(r"\s+([,:;.!?])", r"\1", text_normalized)
            if target_normalized in text_normalized:
                new_node = NavigableString(text_str.replace(target, new_text))
                text_node.replace_with(new_node)
                return

        # Strategy 2: Try text inside inline comment markers
        for marker in element.find_all("ac:inline-comment-marker"):
            marker_text = marker.get_text()
            marker_text_normalized = " ".join(marker_text.split())
            marker_text_normalized = re.sub(r"\s+([,:;.!?])", r"\1", marker_text_normalized)
            if target_normalized in marker_text_normalized:
                # Replace text inside the marker while preserving the marker
                new_marker_text = marker_text.replace(target, new_text)
                marker.string = new_marker_text
                logger.info("  Replaced text inside inline comment marker")
                return

        # Strategy 3: Try text inside other inline elements (strong, em, span, etc.)
        for inline in element.find_all(["strong", "em", "b", "i", "span", "code"]):
            inline_text = inline.get_text()
            inline_text_normalized = " ".join(inline_text.split())
            inline_text_normalized = re.sub(r"\s+([,:;.!?])", r"\1", inline_text_normalized)
            if target_normalized in inline_text_normalized:
                new_inline_text = inline_text.replace(target, new_text)
                inline.string = new_inline_text
                logger.info(f"  Replaced text inside <{inline.name}>")
                return

        # Strategy 4: Try any text node in the tree
        for text_node in element.find_all(string=True, recursive=True):
            text_str = str(text_node)
            text_normalized = " ".join(text_str.split())
            text_normalized = re.sub(r"\s+([,:;.!?])", r"\1", text_normalized)
            if target_normalized in text_normalized:
                new_node = NavigableString(text_str.replace(target, new_text))
                text_node.replace_with(new_node)
                logger.info("  Replaced text in nested node")
                return

        # Check if the full text even contains the target
        full_text = element.get_text(separator=" ", strip=True)
        full_text_normalized = " ".join(full_text.split())
        full_text_normalized = re.sub(r"\s+([,:;.!?])", r"\1", full_text_normalized)

        if target_normalized not in full_text_normalized:
            return

        # Strategy 5: Last resort - replace entire element content
        # This happens when target spans multiple nodes
        new_full_text = full_text_normalized.replace(target_normalized, new_text)
        logger.warning("  Target spans inline comment boundary - replacing entire element content")
        element.clear()
        element.string = new_full_text

    def _delete_block(self, soup: BeautifulSoup, target: str) -> bool:
        """Delete an element containing target text.

        Only deletes leaf-level elements (p, h1-h6, li) to avoid
        accidentally removing container elements or macros.

        Handles text that may be inside inline comment markers by
        normalizing whitespace for comparison.

        Args:
            soup: BeautifulSoup object to modify
            target: Text content to find for deletion

        Returns:
            True if element was deleted, False otherwise
        """
        # Only delete leaf elements to avoid removing containers
        deletable_tags = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"]

        # Normalize target for comparison (collapse whitespace)
        target_normalized = " ".join(target.split())

        # Collect all matching elements, prefer most specific (shortest text)
        candidates = []
        for element in soup.find_all(deletable_tags):
            # Skip macro elements
            if element.name and element.name.startswith("ac:"):
                continue

            # Get full text with separator to preserve spacing around inline elements
            text = element.get_text(separator=" ", strip=True)
            text_normalized = " ".join(text.split())
            # Remove spaces before punctuation (artifact of separator between tags)
            text_normalized = re.sub(r"\s+([,:;.!?])", r"\1", text_normalized)

            if text_normalized == target_normalized or target_normalized in text_normalized:
                candidates.append((element, len(text_normalized)))

        if not candidates:
            logger.warning(f"  Target block not found: {target[:50]}...")
            return False

        # Select most specific element (shortest text)
        candidates.sort(key=lambda x: x[1])
        best_element = candidates[0][0]
        best_element.decompose()
        logger.info(f"  Deleted <{best_element.name}> containing: {target[:30]}...")
        return True

    def _insert_block(
        self, soup: BeautifulSoup, content: str, after_content: str
    ) -> bool:
        """Insert a new block element after specified content.

        Creates a new paragraph element with the given content and
        inserts it after the element containing after_content.

        Args:
            soup: BeautifulSoup object to modify
            content: Content for the new paragraph
            after_content: Content to insert after

        Returns:
            True if element was inserted, False otherwise
        """
        for element in soup.find_all(True):
            if element.name and element.name.startswith("ac:"):
                continue

            text = element.get_text(strip=True)
            if after_content in text:
                # Create new paragraph
                new_p = soup.new_tag("p")
                new_p.string = content
                element.insert_after(new_p)
                logger.info(f"  Inserted paragraph after: {after_content[:30]}...")
                return True

        # If no after_content found, append to body
        body = soup.find("body") or soup
        new_p = soup.new_tag("p")
        new_p.string = content
        body.append(new_p)
        logger.info(f"  Inserted paragraph at end of document")
        return True

    def _change_heading_level(
        self,
        soup: BeautifulSoup,
        target: str,
        old_level: int,
        new_level: int,
        new_text: str,
    ) -> bool:
        """Change the level of a heading element.

        Finds a heading with the target text and changes its tag
        from h{old_level} to h{new_level}. Preserves all attributes.

        Args:
            soup: BeautifulSoup object to modify
            target: Heading text to find
            old_level: Current heading level (1-6)
            new_level: New heading level (1-6)
            new_text: New heading text (may be same as target)

        Returns:
            True if heading was changed, False otherwise
        """
        old_tag = f"h{old_level}"
        new_tag = f"h{new_level}"

        for element in soup.find_all(old_tag):
            if target in element.get_text():
                element.name = new_tag
                # Update text if changed
                if new_text and new_text != target:
                    # Preserve child elements, update text
                    for text_node in element.find_all(string=True):
                        if target in str(text_node):
                            new_node = NavigableString(
                                str(text_node).replace(target, new_text)
                            )
                            text_node.replace_with(new_node)
                            break
                logger.info(f"  Changed <{old_tag}> to <{new_tag}>")
                return True

        logger.warning(f"  Heading not found: {target[:50]}...")
        return False

    def _table_insert_row(
        self,
        soup: BeautifulSoup,
        table_content: str,
        new_row_content: str,
        row_index: int,
    ) -> bool:
        """Insert a row into a table.

        Args:
            soup: BeautifulSoup object to modify
            table_content: Identifier for the table (content string)
            new_row_content: Row data as string repr of list
            row_index: Position to insert the row

        Returns:
            True if row was inserted, False otherwise
        """
        # Parse new row content (expects string repr of list)
        try:
            new_row_cells = ast.literal_eval(new_row_content)
        except (SyntaxError, ValueError) as e:
            logger.warning(f"  Failed to parse row content: {e}")
            return False

        for table in soup.find_all("table"):
            tbody = table.find("tbody") or table
            rows = tbody.find_all("tr")

            # Create new row with proper Confluence structure
            new_tr = soup.new_tag("tr")
            for cell_content in new_row_cells:
                td = soup.new_tag("td")
                p = soup.new_tag("p")
                p.string = str(cell_content) if cell_content else ""
                td.append(p)
                new_tr.append(td)

            # Insert at position
            if row_index < len(rows):
                rows[row_index].insert_before(new_tr)
            else:
                tbody.append(new_tr)

            logger.info(f"  Inserted table row at position {row_index}")
            return True

        logger.warning("  Table not found for row insertion")
        return False

    def _table_delete_row(
        self, soup: BeautifulSoup, row_content: str, row_index: int
    ) -> bool:
        """Delete a row from a table.

        Args:
            soup: BeautifulSoup object to modify
            row_content: Row data as string repr of list
            row_index: Row position (used as fallback)

        Returns:
            True if row was deleted, False otherwise
        """
        # Parse row content
        try:
            row_cells = ast.literal_eval(row_content)
        except (SyntaxError, ValueError):
            row_cells = None

        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if row_cells and cells == row_cells:
                    tr.decompose()
                    logger.info(f"  Deleted table row: {row_cells}")
                    return True

        logger.warning(f"  Table row not found: {row_content[:50]}...")
        return False

    def _table_update_cell(
        self,
        soup: BeautifulSoup,
        table_content: str,
        new_content: str,
        row_index: int,
        cell_index: int,
    ) -> bool:
        """Update a specific cell in a table.

        Args:
            soup: BeautifulSoup object to modify
            table_content: Identifier for the table
            new_content: New cell content
            row_index: Row position (0-based)
            cell_index: Cell position within row (0-based)

        Returns:
            True if cell was updated, False otherwise
        """
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if row_index < len(rows):
                cells = rows[row_index].find_all(["td", "th"])
                if cell_index < len(cells):
                    cell = cells[cell_index]
                    # Update the cell content
                    p = cell.find("p")
                    if p:
                        p.string = new_content
                    else:
                        cell.string = new_content
                    logger.info(
                        f"  Updated cell [{row_index}][{cell_index}]: {new_content}"
                    )
                    return True

        logger.warning(
            f"  Table cell not found: row {row_index}, cell {cell_index}"
        )
        return False

    def count_macros(self, xhtml: str) -> int:
        """Count Confluence macros in XHTML content.

        Useful for verifying macros are preserved after operations.

        Args:
            xhtml: XHTML content to count macros in

        Returns:
            Number of ac: namespace elements found
        """
        soup = BeautifulSoup(xhtml, self.parser)
        return len(
            [t for t in soup.find_all(True) if t.name and t.name.startswith("ac:")]
        )
