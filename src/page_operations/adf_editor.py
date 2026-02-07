"""ADF Surgical Editor for Confluence.

This module provides surgical editing of ADF (Atlassian Document Format)
documents. Operations target nodes by localId, avoiding the position
signature problems that plague XHTML surgery.
"""

import copy
import logging
from typing import Any, Dict, List, Optional, Tuple

from .adf_models import (
    AdfDocument,
    AdfNode,
    AdfNodeType,
    AdfOperation,
    MACRO_NODE_TYPES,
)
from .adf_parser import AdfParser
from .models import OperationType, SurgicalOperation

logger = logging.getLogger(__name__)


class AdfEditor:
    """Surgical editor for ADF documents.

    Applies operations to ADF documents by targeting nodes via localId.
    This approach avoids the fragile position signature matching needed
    for XHTML surgery.

    Key principle: Never modify macro nodes (extension, inlineExtension,
    bodiedExtension). They remain untouched in their original positions.
    """

    def __init__(self):
        """Initialize the ADF editor."""
        self.parser = AdfParser()

    def apply_operations(
        self,
        adf_doc: AdfDocument,
        operations: List[SurgicalOperation],
        local_id_map: Optional[Dict[str, str]] = None,
    ) -> Tuple[AdfDocument, int, int]:
        """Apply surgical operations to an ADF document.

        Args:
            adf_doc: The ADF document to modify
            operations: List of SurgicalOperation to apply
            local_id_map: Optional mapping of content → localId for matching

        Returns:
            Tuple of (modified_doc, success_count, failure_count)
        """
        # Work on a deep copy to preserve original
        modified = self._deep_copy_document(adf_doc)

        success_count = 0
        failure_count = 0

        # Build localId lookup if not provided
        if local_id_map is None:
            local_id_map = self._build_content_to_id_map(adf_doc)

        for op in operations:
            success = self._apply_single_operation(modified, op, local_id_map)
            if success:
                success_count += 1
                logger.debug(f"Applied operation: {op.op_type.value}")
            else:
                failure_count += 1
                logger.warning(
                    f"Failed to apply operation: {op.op_type.value} "
                    f"(target: {op.target_content[:50] if op.target_content else 'N/A'}...)"
                )

        return modified, success_count, failure_count

    def _apply_single_operation(
        self,
        doc: AdfDocument,
        op: SurgicalOperation,
        local_id_map: Dict[str, str],
    ) -> bool:
        """Apply a single operation to the document.

        Args:
            doc: Document to modify (in-place)
            op: Operation to apply
            local_id_map: Content to localId mapping

        Returns:
            True if operation succeeded, False otherwise
        """
        op_type = op.op_type

        if op_type == OperationType.UPDATE_TEXT:
            return self._update_text(doc, op, local_id_map)

        elif op_type == OperationType.DELETE_BLOCK:
            return self._delete_block(doc, op, local_id_map)

        elif op_type == OperationType.INSERT_BLOCK:
            return self._insert_block(doc, op, local_id_map)

        elif op_type == OperationType.CHANGE_HEADING_LEVEL:
            return self._change_heading_level(doc, op, local_id_map)

        elif op_type == OperationType.TABLE_UPDATE_CELL:
            return self._table_update_cell(doc, op, local_id_map)

        elif op_type == OperationType.TABLE_INSERT_ROW:
            return self._table_insert_row(doc, op, local_id_map)

        elif op_type == OperationType.TABLE_DELETE_ROW:
            return self._table_delete_row(doc, op, local_id_map)

        else:
            logger.warning(f"Unsupported operation type: {op_type}")
            return False

    def _update_text(
        self,
        doc: AdfDocument,
        op: SurgicalOperation,
        local_id_map: Dict[str, str],
    ) -> bool:
        """Update text content in a node.

        Args:
            doc: Document to modify
            op: UPDATE_TEXT operation
            local_id_map: Content to localId mapping

        Returns:
            True if update succeeded
        """
        # Find target node by content → localId
        local_id = local_id_map.get(op.target_content)

        if not local_id:
            # Try partial match
            local_id = self._find_id_by_partial_content(
                local_id_map, op.target_content
            )

        if not local_id:
            logger.debug(f"No localId found for content: {op.target_content[:50]}...")
            return False

        # Find the node
        node = doc.find_by_local_id(local_id)
        if not node:
            logger.debug(f"Node not found for localId: {local_id}")
            return False

        # Don't modify macros
        if node.node_type in MACRO_NODE_TYPES:
            logger.warning(f"Refusing to modify macro node: {local_id}")
            return False

        # Update the text content
        return self._replace_node_text(node, op.new_content)

    def _delete_block(
        self,
        doc: AdfDocument,
        op: SurgicalOperation,
        local_id_map: Dict[str, str],
    ) -> bool:
        """Delete a block node from the document.

        Args:
            doc: Document to modify
            op: DELETE_BLOCK operation
            local_id_map: Content to localId mapping

        Returns:
            True if deletion succeeded
        """
        local_id = local_id_map.get(op.target_content)

        if not local_id:
            local_id = self._find_id_by_partial_content(
                local_id_map, op.target_content
            )

        if not local_id:
            return False

        # Find and remove from parent
        return self._remove_node_by_id(doc, local_id)

    def _insert_block(
        self,
        doc: AdfDocument,
        op: SurgicalOperation,
        local_id_map: Dict[str, str],
    ) -> bool:
        """Insert a new block after a target node.

        Args:
            doc: Document to modify
            op: INSERT_BLOCK operation
            local_id_map: Content to localId mapping

        Returns:
            True if insertion succeeded
        """
        # Find the anchor node (insert after this)
        anchor_local_id = local_id_map.get(op.after_content)

        if not anchor_local_id:
            anchor_local_id = self._find_id_by_partial_content(
                local_id_map, op.after_content
            )

        if not anchor_local_id:
            # Insert at end if no anchor found
            logger.debug("No anchor found, inserting at end")
            new_node = self._create_paragraph_node(op.new_content)
            doc.content.append(new_node)
            return True

        # Find anchor and insert after it
        return self._insert_after_node(doc, anchor_local_id, op.new_content)

    def _change_heading_level(
        self,
        doc: AdfDocument,
        op: SurgicalOperation,
        local_id_map: Dict[str, str],
    ) -> bool:
        """Change the level of a heading.

        Args:
            doc: Document to modify
            op: CHANGE_HEADING_LEVEL operation
            local_id_map: Content to localId mapping

        Returns:
            True if change succeeded
        """
        local_id = local_id_map.get(op.target_content)

        if not local_id:
            local_id = self._find_id_by_partial_content(
                local_id_map, op.target_content
            )

        if not local_id:
            return False

        node = doc.find_by_local_id(local_id)
        if not node:
            return False

        if node.node_type != AdfNodeType.HEADING:
            logger.warning(f"Node is not a heading: {local_id}")
            return False

        # Update the level attribute
        node.attrs["level"] = op.new_level
        return True

    def _table_update_cell(
        self,
        doc: AdfDocument,
        op: SurgicalOperation,
        local_id_map: Dict[str, str],
    ) -> bool:
        """Update a cell in a table.

        Args:
            doc: Document to modify
            op: TABLE_UPDATE_CELL operation
            local_id_map: Content to localId mapping

        Returns:
            True if update succeeded
        """
        # Find table node
        table_node = self._find_table_by_content(doc, op.target_content)

        if not table_node:
            logger.debug(f"Table not found for content: {op.target_content[:30]}...")
            return False

        # Navigate to the cell
        row_idx = op.row_index
        cell_idx = op.cell_index

        if row_idx >= len(table_node.content):
            logger.debug(f"Row index out of bounds: {row_idx}")
            return False

        row_node = table_node.content[row_idx]
        if row_node.type != "tableRow":
            return False

        if cell_idx >= len(row_node.content):
            logger.debug(f"Cell index out of bounds: {cell_idx}")
            return False

        cell_node = row_node.content[cell_idx]
        if cell_node.type not in ("tableCell", "tableHeader"):
            return False

        # Replace cell content
        return self._replace_node_text(cell_node, op.new_content)

    def _table_insert_row(
        self,
        doc: AdfDocument,
        op: SurgicalOperation,
        local_id_map: Dict[str, str],
    ) -> bool:
        """Insert a row into a table.

        The operation's new_content contains the cell values in pipe-delimited format.
        The after_content (if present) contains the row content to insert after.

        Args:
            doc: Document to modify
            op: TABLE_INSERT_ROW operation
            local_id_map: Content to localId mapping

        Returns:
            True if insertion succeeded
        """
        # Find table
        table_node = self._find_table_by_content(doc, op.target_content)

        if not table_node:
            logger.debug("Table not found for insert row operation")
            return False

        # Determine column count from existing rows
        if not table_node.content:
            logger.debug("Table has no rows, cannot determine column count")
            return False

        first_row = table_node.content[0]
        col_count = len(first_row.content)

        # Parse cell content from pipe-delimited format
        cell_values = op.new_content.split("|") if op.new_content else []

        # Pad or trim to match column count
        while len(cell_values) < col_count:
            cell_values.append("")
        cell_values = cell_values[:col_count]

        # Create new row with cell content
        new_row = self._create_table_row_with_content(cell_values)

        # Determine insertion position
        insert_idx = op.row_index

        # If after_content is provided, find that row and insert after it
        if op.after_content:
            found_idx = self._find_row_by_content(table_node, op.after_content)
            if found_idx is not None:
                insert_idx = found_idx + 1

        # Clamp to valid range
        insert_idx = max(0, min(insert_idx, len(table_node.content)))

        table_node.content.insert(insert_idx, new_row)
        logger.debug(f"Inserted row at index {insert_idx}")
        return True

    def _table_delete_row(
        self,
        doc: AdfDocument,
        op: SurgicalOperation,
        local_id_map: Dict[str, str],
    ) -> bool:
        """Delete a row from a table by matching its content.

        The operation's new_content contains the row's cell values in pipe-delimited
        format, which is used to find the row to delete.

        Args:
            doc: Document to modify
            op: TABLE_DELETE_ROW operation
            local_id_map: Content to localId mapping

        Returns:
            True if deletion succeeded
        """
        table_node = self._find_table_by_content(doc, op.target_content)

        if not table_node:
            logger.debug("Table not found for delete row operation")
            return False

        # Find the row by content match
        row_content = op.new_content  # Row content in pipe-delimited format

        if row_content:
            row_idx = self._find_row_by_content(table_node, row_content)
            if row_idx is not None:
                table_node.content.pop(row_idx)
                logger.debug(f"Deleted row at index {row_idx} (found by content)")
                return True

        # Fallback: try by index
        row_idx = op.row_index
        if row_idx < len(table_node.content):
            table_node.content.pop(row_idx)
            logger.debug(f"Deleted row at index {row_idx} (fallback)")
            return True

        logger.debug(f"Could not find row to delete")
        return False

    def _find_row_by_content(
        self,
        table_node: AdfNode,
        row_content: str,
    ) -> Optional[int]:
        """Find a row in a table by matching its cell content.

        Args:
            table_node: Table node to search
            row_content: Pipe-delimited cell content to match

        Returns:
            Row index if found, None otherwise
        """
        target_cells = [c.strip().lower() for c in row_content.split("|")]
        target_normalized = "|".join(" ".join(c.split()) for c in target_cells)

        for i, row in enumerate(table_node.content):
            if row.type != "tableRow":
                continue

            # Extract cell text from this row
            row_cells = []
            for cell in row.content:
                if cell.type in ("tableCell", "tableHeader"):
                    cell_text = cell.get_text_content().strip().lower()
                    row_cells.append(" ".join(cell_text.split()))

            row_normalized = "|".join(row_cells)

            # Check for match
            if row_normalized == target_normalized:
                return i

            # Also try partial match (in case of slight formatting differences)
            if len(row_cells) == len(target_cells):
                matching = sum(
                    1 for rc, tc in zip(row_cells, target_cells)
                    if rc == " ".join(tc.split())
                )
                if matching == len(target_cells):
                    return i

        return None

    def _create_table_row_with_content(
        self,
        cell_values: List[str],
    ) -> AdfNode:
        """Create a new table row with specified cell content.

        Args:
            cell_values: List of cell content strings

        Returns:
            New AdfNode of type tableRow
        """
        import uuid

        cells = []
        for value in cell_values:
            para = self._create_paragraph_node(value.strip())
            cell = AdfNode(
                type="tableCell",
                content=[para],
                attrs={"localId": str(uuid.uuid4())},
            )
            cells.append(cell)

        return AdfNode(
            type="tableRow",
            content=cells,
            attrs={"localId": str(uuid.uuid4())},
        )

    # --- Helper Methods ---

    def _deep_copy_document(self, doc: AdfDocument) -> AdfDocument:
        """Create a deep copy of an ADF document."""
        return copy.deepcopy(doc)

    def _build_content_to_id_map(self, doc: AdfDocument) -> Dict[str, str]:
        """Build a mapping from text content to localId.

        This enables finding nodes when we only have the text content
        (from markdown diff).

        Args:
            doc: ADF document to analyze

        Returns:
            Dictionary mapping text content → localId
        """
        content_map: Dict[str, str] = {}

        def collect(node: AdfNode):
            if node.local_id:
                text = node.get_text_content().strip()
                if text:
                    content_map[text] = node.local_id

            for child in node.content:
                collect(child)

        for node in doc.content:
            collect(node)

        return content_map

    def _find_id_by_partial_content(
        self,
        content_map: Dict[str, str],
        target: str,
        threshold: float = 0.8,
    ) -> Optional[str]:
        """Find localId by partial content match.

        Args:
            content_map: Content → localId mapping
            target: Target content to find
            threshold: Minimum similarity for match

        Returns:
            LocalId if found, None otherwise
        """
        target_words = set(target.lower().split())
        if not target_words:
            return None

        best_match = None
        best_score = 0.0

        for content, local_id in content_map.items():
            content_words = set(content.lower().split())
            if not content_words:
                continue

            # Calculate word overlap
            overlap = len(target_words & content_words)
            score = overlap / min(len(target_words), len(content_words))

            if score > best_score and score >= threshold:
                best_score = score
                best_match = local_id

        return best_match

    def _replace_node_text(self, node: AdfNode, new_text: str) -> bool:
        """Replace text content within a node.

        For nodes with text children, replaces ALL text/hardBreak content.
        Preserves marks (formatting) from the first text node.
        Handles <br> tags by converting them to hardBreak nodes.

        Args:
            node: Node to modify
            new_text: New text content (may contain <br> tags)

        Returns:
            True if replacement succeeded
        """
        # For tables, we need to find which specific text changed
        if node.type == "table":
            return self._replace_table_text(node, new_text)

        # Check if content is primarily text/hardBreak
        # (we need to replace ALL of it, not just the first text node)
        text_types = {"text", "hardBreak"}
        has_text_content = any(child.type in text_types for child in node.content)

        if has_text_content:
            # Get marks from first text node to preserve
            first_marks = []
            for child in node.content:
                if child.type == "text" and child.marks:
                    first_marks = child.marks
                    break

            # Separate non-text content (to preserve) from text content (to replace)
            non_text_content = [c for c in node.content if c.type not in text_types]

            # Create new text nodes
            new_nodes = self._text_to_adf_nodes(new_text)

            # Preserve marks on the first text node
            if new_nodes and new_nodes[0].type == "text" and first_marks:
                new_nodes[0].marks = first_marks

            # Replace content: new text nodes + any preserved non-text nodes
            node.content = new_nodes + non_text_content
            return True

        # If no text children, look for paragraph wrapper
        for child in node.content:
            if child.type == "paragraph":
                return self._replace_node_text(child, new_text)

        # Last resort: create new text nodes
        if not node.content:
            node.content = self._text_to_adf_nodes(new_text)
            return True

        return False

    def _replace_table_text(self, table_node: AdfNode, new_text: str) -> bool:
        """Replace text content within a table by finding changed cells.

        Compares old and new text to identify specific changes and applies
        them to individual cells.

        Args:
            table_node: Table node to modify
            new_text: New table text content (space-separated cells)

        Returns:
            True if replacement succeeded
        """
        # Get current table content as word list
        old_text = table_node.get_text_content()
        old_words = old_text.lower().split()
        new_words = new_text.lower().split()

        # Find words that differ
        # Create a mapping of old → new for differing words
        replacements = {}
        for i, (old_word, new_word) in enumerate(zip(old_words, new_words)):
            if old_word != new_word:
                # Store both lowercase and original case replacements
                replacements[old_word] = new_word

        if not replacements:
            logger.debug("No text differences found in table")
            return True  # No changes needed

        logger.debug(f"Table replacements to apply: {replacements}")

        # Apply replacements to all text nodes in the table
        replaced = False
        for row in table_node.content:
            if row.type != "tableRow":
                continue
            for cell in row.content:
                if cell.type not in ("tableCell", "tableHeader"):
                    continue
                if self._apply_text_replacements(cell, replacements):
                    replaced = True

        return replaced

    def _apply_text_replacements(
        self,
        node: AdfNode,
        replacements: Dict[str, str],
    ) -> bool:
        """Apply text replacements to all text nodes within a node.

        Args:
            node: Node to search
            replacements: Dictionary of old_word → new_word replacements

        Returns:
            True if any replacement was made
        """
        replaced = False

        for i, child in enumerate(node.content):
            if child.type == "text" and child.text:
                new_text = child.text
                text_lower = child.text.lower()
                for old_word, new_word in replacements.items():
                    if old_word in text_lower:
                        # Do case-insensitive replacement while trying to preserve case
                        import re
                        def replace_preserve_case(match):
                            matched = match.group(0)
                            # If original was capitalized, capitalize replacement
                            if matched[0].isupper():
                                return new_word.capitalize()
                            return new_word
                        new_text = re.sub(
                            re.escape(old_word),
                            replace_preserve_case,
                            new_text,
                            flags=re.IGNORECASE
                        )
                        replaced = True
                if new_text != child.text:
                    node.content[i] = AdfNode(
                        type="text",
                        text=new_text,
                        marks=child.marks,
                    )
            else:
                # Recurse into child nodes
                if self._apply_text_replacements(child, replacements):
                    replaced = True

        return replaced

    def _remove_node_by_id(self, doc: AdfDocument, local_id: str) -> bool:
        """Remove a node from the document by its localId.

        Args:
            doc: Document to modify
            local_id: LocalId of node to remove

        Returns:
            True if removal succeeded
        """
        # Check top-level nodes
        for i, node in enumerate(doc.content):
            if node.local_id == local_id:
                # Don't remove macros
                if node.node_type in MACRO_NODE_TYPES:
                    logger.warning(f"Refusing to delete macro: {local_id}")
                    return False
                doc.content.pop(i)
                return True

            # Check nested nodes (recursive removal not implemented for safety)
            # Would need parent tracking to implement properly

        return False

    def _insert_after_node(
        self,
        doc: AdfDocument,
        anchor_id: str,
        content: str,
    ) -> bool:
        """Insert a new paragraph after a node.

        Args:
            doc: Document to modify
            anchor_id: LocalId of anchor node
            content: Text content for new paragraph

        Returns:
            True if insertion succeeded
        """
        for i, node in enumerate(doc.content):
            if node.local_id == anchor_id:
                new_node = self._create_paragraph_node(content)
                doc.content.insert(i + 1, new_node)
                return True

        return False

    def _create_paragraph_node(self, text: str) -> AdfNode:
        """Create a new paragraph node with text content.

        Handles <br> tags by converting them to hardBreak nodes.

        Args:
            text: Text content (may contain <br> tags)

        Returns:
            New AdfNode of type paragraph
        """
        import uuid

        content_nodes = self._text_to_adf_nodes(text)
        return AdfNode(
            type="paragraph",
            content=content_nodes,
            attrs={"localId": str(uuid.uuid4())},
        )

    def _text_to_adf_nodes(self, text: str) -> List[AdfNode]:
        """Convert text with <br> tags to a list of ADF nodes.

        Splits text by <br> tags and creates alternating text and hardBreak nodes.

        Args:
            text: Text content with potential <br> tags

        Returns:
            List of AdfNode (text and hardBreak nodes)
        """
        import re

        if not text:
            return [AdfNode(type="text", text="")]

        # Normalize <br> variants
        text = re.sub(r'<br\s*/?>', '<br>', text)

        # If no <br> tags, return simple text node
        if '<br>' not in text:
            return [AdfNode(type="text", text=text)]

        # Split by <br> and create alternating text/hardBreak nodes
        parts = text.split('<br>')
        nodes: List[AdfNode] = []

        for i, part in enumerate(parts):
            if part:  # Add text node if not empty
                nodes.append(AdfNode(type="text", text=part))
            if i < len(parts) - 1:  # Add hardBreak between parts
                nodes.append(AdfNode(type="hardBreak"))

        return nodes if nodes else [AdfNode(type="text", text="")]

    def _create_table_row(
        self,
        col_count: int,
        first_cell_content: str = "",
    ) -> AdfNode:
        """Create a new table row with empty cells (legacy method).

        Args:
            col_count: Number of columns
            first_cell_content: Optional content for first cell

        Returns:
            New AdfNode of type tableRow
        """
        cell_values = [""] * col_count
        if first_cell_content:
            cell_values[0] = first_cell_content
        return self._create_table_row_with_content(cell_values)

    def _find_table_by_content(
        self,
        doc: AdfDocument,
        content: str,
    ) -> Optional[AdfNode]:
        """Find a table node by its content.

        Uses normalized whitespace comparison to handle formatting differences
        between markdown and ADF.

        Args:
            doc: Document to search
            content: Content to match (from first cell or table overall)

        Returns:
            Table AdfNode if found, None otherwise
        """
        # Normalize the target content
        normalized_content = " ".join(content.lower().split())

        for node in doc.content:
            if node.type == "table":
                table_text = node.get_text_content()
                normalized_table = " ".join(table_text.lower().split())

                # Check if normalized content is in normalized table text
                if normalized_content in normalized_table:
                    return node

                # Also try checking if first few words match (handles truncated content)
                content_words = normalized_content.split()[:5]
                if content_words:
                    content_prefix = " ".join(content_words)
                    if content_prefix in normalized_table:
                        return node

        return None

    def count_macros(self, doc: AdfDocument) -> int:
        """Count macro nodes in the document.

        Args:
            doc: ADF document to analyze

        Returns:
            Number of macro nodes
        """
        count = 0

        def count_recursive(node: AdfNode):
            nonlocal count
            if node.node_type in MACRO_NODE_TYPES:
                count += 1
            for child in node.content:
                count_recursive(child)

        for node in doc.content:
            count_recursive(node)

        return count
