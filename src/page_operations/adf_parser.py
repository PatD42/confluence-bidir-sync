"""Parser for ADF (Atlassian Document Format) documents.

This module provides parsing of ADF JSON into structured objects
for diff analysis and surgical updates.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .adf_models import (
    AdfBlock,
    AdfDocument,
    AdfMark,
    AdfNode,
    AdfNodeType,
    MACRO_NODE_TYPES,
)
from .models import BlockType

logger = logging.getLogger(__name__)


class AdfParser:
    """Parser for ADF documents.

    Converts ADF JSON to structured AdfDocument and AdfNode objects,
    and extracts AdfBlocks for diff analysis.
    """

    def parse_document(self, adf_json: Dict[str, Any]) -> AdfDocument:
        """Parse an ADF JSON document into an AdfDocument object.

        Args:
            adf_json: The ADF document as a dictionary (parsed JSON)

        Returns:
            AdfDocument object with parsed content tree

        Raises:
            ValueError: If the JSON is not valid ADF format
        """
        if not isinstance(adf_json, dict):
            raise ValueError("ADF must be a dictionary")

        doc_type = adf_json.get("type")
        if doc_type != "doc":
            raise ValueError(f"Expected type 'doc', got '{doc_type}'")

        version = adf_json.get("version", 1)
        content_data = adf_json.get("content", [])

        content = [self._parse_node(node_data) for node_data in content_data]

        return AdfDocument(version=version, content=content)

    def parse_from_string(self, adf_string: str) -> AdfDocument:
        """Parse an ADF JSON string into an AdfDocument object.

        Args:
            adf_string: The ADF document as a JSON string

        Returns:
            AdfDocument object with parsed content tree
        """
        adf_json = json.loads(adf_string)
        return self.parse_document(adf_json)

    def _parse_node(self, node_data: Dict[str, Any]) -> AdfNode:
        """Parse a single ADF node from JSON.

        Args:
            node_data: Node data as a dictionary

        Returns:
            Parsed AdfNode object
        """
        node_type = node_data.get("type", "unknown")
        text = node_data.get("text")
        attrs = node_data.get("attrs", {})

        # Parse marks (text formatting)
        marks_data = node_data.get("marks", [])
        marks = [
            AdfMark(type=m.get("type", "unknown"), attrs=m.get("attrs", {}))
            for m in marks_data
        ]

        # Parse child content recursively
        content_data = node_data.get("content", [])
        content = [self._parse_node(child) for child in content_data]

        return AdfNode(
            type=node_type,
            content=content,
            text=text,
            attrs=attrs,
            marks=marks,
        )

    def extract_blocks(self, adf_doc: AdfDocument) -> List[AdfBlock]:
        """Extract content blocks from an ADF document for diff analysis.

        Converts ADF nodes to AdfBlock objects that can be compared
        with markdown blocks.

        Note: Lists are extracted as individual items (one block per item)
        to match how markdown parser extracts list items.

        Args:
            adf_doc: Parsed ADF document

        Returns:
            List of AdfBlock objects representing content blocks
        """
        blocks: List[AdfBlock] = []
        index = 0

        for node in adf_doc.content:
            # Handle lists specially - extract each item as separate block
            if node.node_type in (AdfNodeType.BULLET_LIST, AdfNodeType.ORDERED_LIST):
                items = self._extract_list_items_as_blocks(node, index)
                blocks.extend(items)
                index += len(items)
            else:
                extracted = self._extract_block_from_node(node, index)
                if extracted:
                    blocks.append(extracted)
                    index += 1

        return blocks

    def _extract_list_items_as_blocks(
        self, list_node: AdfNode, start_index: int
    ) -> List[AdfBlock]:
        """Extract individual list items as separate AdfBlocks.

        This matches how the markdown parser extracts list items,
        enabling proper diff matching.

        Args:
            list_node: A bulletList or orderedList ADF node
            start_index: Starting index for blocks

        Returns:
            List of AdfBlock objects, one per list item
        """
        blocks = []
        index = start_index

        for item_node in list_node.content:
            if item_node.type != "listItem":
                continue

            content = item_node.get_text_content()
            blocks.append(
                AdfBlock(
                    node_type=AdfNodeType.LIST_ITEM,
                    content=content,
                    local_id=item_node.local_id,
                    node=item_node,
                    index=index,
                )
            )
            index += 1

        return blocks

    def _extract_block_from_node(
        self, node: AdfNode, index: int
    ) -> Optional[AdfBlock]:
        """Extract an AdfBlock from an ADF node.

        Args:
            node: The ADF node to extract from
            index: Position index in document

        Returns:
            AdfBlock or None if node should be skipped
        """
        node_type = node.node_type

        # Handle different node types
        if node_type == AdfNodeType.PARAGRAPH:
            return AdfBlock(
                node_type=node_type,
                content=node.get_text_content(),
                local_id=node.local_id,
                node=node,
                index=index,
            )

        elif node_type == AdfNodeType.HEADING:
            level = node.attrs.get("level", 1)
            return AdfBlock(
                node_type=node_type,
                content=node.get_text_content(),
                local_id=node.local_id,
                level=level,
                node=node,
                index=index,
            )

        elif node_type == AdfNodeType.TABLE:
            rows = self._extract_table_rows(node)
            # Use space-joined text from ALL cells (matches markdown parser behavior)
            content = " ".join(
                " ".join(cell for cell in row)
                for row in rows
            )
            return AdfBlock(
                node_type=node_type,
                content=content,
                local_id=node.local_id,
                rows=rows,
                node=node,
                index=index,
            )

        elif node_type in (AdfNodeType.BULLET_LIST, AdfNodeType.ORDERED_LIST):
            # Lists are handled specially - we return None here
            # and extract individual items in extract_blocks()
            # This matches how markdown parser extracts list items as separate blocks
            return None

        elif node_type == AdfNodeType.CODE_BLOCK:
            return AdfBlock(
                node_type=node_type,
                content=node.get_text_content(),
                local_id=node.local_id,
                node=node,
                index=index,
            )

        elif node_type in MACRO_NODE_TYPES:
            # Macros - preserve but don't include in diff
            extension_key = node.attrs.get("extensionKey", "unknown")
            return AdfBlock(
                node_type=node_type,
                content=f"[MACRO:{extension_key}]",
                local_id=node.local_id,
                node=node,
                index=index,
            )

        elif node_type == AdfNodeType.BLOCKQUOTE:
            return AdfBlock(
                node_type=node_type,
                content=node.get_text_content(),
                local_id=node.local_id,
                node=node,
                index=index,
            )

        elif node_type == AdfNodeType.RULE:
            return AdfBlock(
                node_type=node_type,
                content="---",
                local_id=node.local_id,
                node=node,
                index=index,
            )

        # Skip unknown node types
        logger.debug(f"Skipping unknown node type: {node.type}")
        return None

    def _extract_table_rows(self, table_node: AdfNode) -> List[List[str]]:
        """Extract table content as rows of cells.

        Args:
            table_node: A table ADF node

        Returns:
            List of rows, each row is a list of cell text content
        """
        rows = []

        for row_node in table_node.content:
            if row_node.type != "tableRow":
                continue

            cells = []
            for cell_node in row_node.content:
                if cell_node.type not in ("tableCell", "tableHeader"):
                    continue
                cells.append(cell_node.get_text_content())

            rows.append(cells)

        return rows

    def _extract_list_items(self, list_node: AdfNode) -> List[str]:
        """Extract list items as text strings.

        Args:
            list_node: A bulletList or orderedList ADF node

        Returns:
            List of item text content
        """
        items = []

        for item_node in list_node.content:
            if item_node.type != "listItem":
                continue
            items.append(item_node.get_text_content())

        return items


def adf_block_type_to_content_block_type(adf_type: AdfNodeType) -> BlockType:
    """Convert ADF node type to ContentBlock BlockType.

    This allows using the existing DiffAnalyzer with ADF blocks.

    Args:
        adf_type: ADF node type

    Returns:
        Equivalent BlockType
    """
    mapping = {
        AdfNodeType.PARAGRAPH: BlockType.PARAGRAPH,
        AdfNodeType.HEADING: BlockType.HEADING,
        AdfNodeType.TABLE: BlockType.TABLE,
        AdfNodeType.BULLET_LIST: BlockType.LIST,
        AdfNodeType.ORDERED_LIST: BlockType.LIST,
        AdfNodeType.LIST_ITEM: BlockType.LIST,
        AdfNodeType.CODE_BLOCK: BlockType.CODE,
        AdfNodeType.EXTENSION: BlockType.MACRO,
        AdfNodeType.INLINE_EXTENSION: BlockType.MACRO,
        AdfNodeType.BODIED_EXTENSION: BlockType.MACRO,
        AdfNodeType.BLOCKQUOTE: BlockType.PARAGRAPH,
        AdfNodeType.RULE: BlockType.OTHER,
    }
    return mapping.get(adf_type, BlockType.OTHER)
