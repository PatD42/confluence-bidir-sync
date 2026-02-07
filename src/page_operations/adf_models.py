"""Data models for ADF (Atlassian Document Format) operations.

This module defines data structures for working with ADF, Confluence's JSON-based
document format. ADF nodes have localId fields that allow precise identification
for surgical updates without position signatures.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AdfNodeType(Enum):
    """Types of ADF nodes."""

    # Document root
    DOC = "doc"

    # Block nodes
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    BULLET_LIST = "bulletList"
    ORDERED_LIST = "orderedList"
    LIST_ITEM = "listItem"
    TABLE = "table"
    TABLE_ROW = "tableRow"
    TABLE_HEADER = "tableHeader"
    TABLE_CELL = "tableCell"
    CODE_BLOCK = "codeBlock"
    BLOCKQUOTE = "blockquote"
    RULE = "rule"
    MEDIA_SINGLE = "mediaSingle"
    MEDIA_GROUP = "mediaGroup"
    PANEL = "panel"
    EXPAND = "expand"

    # Inline nodes
    TEXT = "text"
    HARD_BREAK = "hardBreak"
    MENTION = "mention"
    EMOJI = "emoji"
    INLINE_CARD = "inlineCard"
    STATUS = "status"
    DATE = "date"

    # Extensions (macros)
    EXTENSION = "extension"
    INLINE_EXTENSION = "inlineExtension"
    BODIED_EXTENSION = "bodiedExtension"

    # Other
    UNKNOWN = "unknown"


# ADF node types that are block-level content
BLOCK_NODE_TYPES = {
    AdfNodeType.PARAGRAPH,
    AdfNodeType.HEADING,
    AdfNodeType.BULLET_LIST,
    AdfNodeType.ORDERED_LIST,
    AdfNodeType.LIST_ITEM,
    AdfNodeType.TABLE,
    AdfNodeType.TABLE_ROW,
    AdfNodeType.TABLE_HEADER,
    AdfNodeType.TABLE_CELL,
    AdfNodeType.CODE_BLOCK,
    AdfNodeType.BLOCKQUOTE,
    AdfNodeType.RULE,
    AdfNodeType.MEDIA_SINGLE,
    AdfNodeType.MEDIA_GROUP,
    AdfNodeType.PANEL,
    AdfNodeType.EXPAND,
    AdfNodeType.EXTENSION,
    AdfNodeType.BODIED_EXTENSION,
}

# ADF node types that are macros (should not be modified)
MACRO_NODE_TYPES = {
    AdfNodeType.EXTENSION,
    AdfNodeType.INLINE_EXTENSION,
    AdfNodeType.BODIED_EXTENSION,
}


@dataclass
class AdfMark:
    """Represents a text mark (formatting) in ADF.

    Marks are applied to text nodes to add formatting like bold, italic,
    links, and inline comments.

    Attributes:
        type: Mark type (strong, em, link, code, annotation, etc.)
        attrs: Mark-specific attributes
    """

    type: str
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdfNode:
    """Represents a node in the ADF tree.

    Each node has a type, optional content (child nodes), optional text,
    optional attributes, and optional marks (for text nodes).

    The localId attribute is crucial - it provides stable identification
    for surgical updates.

    Attributes:
        type: Node type (paragraph, heading, text, etc.)
        content: List of child nodes
        text: Text content (for text nodes)
        attrs: Node attributes including localId
        marks: Text formatting marks
        local_id: Extracted localId for convenience (from attrs)
    """

    type: str
    content: List["AdfNode"] = field(default_factory=list)
    text: Optional[str] = None
    attrs: Dict[str, Any] = field(default_factory=dict)
    marks: List[AdfMark] = field(default_factory=list)

    @property
    def local_id(self) -> Optional[str]:
        """Get the localId from attrs."""
        return self.attrs.get("localId")

    @property
    def node_type(self) -> AdfNodeType:
        """Get the AdfNodeType enum value."""
        try:
            return AdfNodeType(self.type)
        except ValueError:
            return AdfNodeType.UNKNOWN

    @property
    def is_macro(self) -> bool:
        """Check if this node is a macro (extension)."""
        return self.node_type in MACRO_NODE_TYPES

    @property
    def is_block(self) -> bool:
        """Check if this node is a block-level element."""
        return self.node_type in BLOCK_NODE_TYPES

    def get_text_content(self) -> str:
        """Extract all text content from this node and its children.

        Uses space separator between block-level children (like list items
        in table cells) to match markdown parsing behavior.

        Returns:
            Concatenated text from all text nodes in the subtree.
        """
        if self.text:
            return self.text

        texts = []
        for child in self.content:
            child_text = child.get_text_content()
            if child_text:
                texts.append(child_text)

        # Use space separator for block-level children (listItem, paragraph, etc.)
        # This matches how markdown parser extracts content
        if texts and self.content and self.content[0].is_block:
            return " ".join(texts)
        return "".join(texts)

    def find_by_local_id(self, local_id: str) -> Optional["AdfNode"]:
        """Find a descendant node by its localId.

        Args:
            local_id: The localId to search for

        Returns:
            The node with matching localId, or None if not found
        """
        if self.local_id == local_id:
            return self

        for child in self.content:
            result = child.find_by_local_id(local_id)
            if result:
                return result

        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert this node back to ADF JSON format.

        Returns:
            Dictionary suitable for JSON serialization
        """
        result: Dict[str, Any] = {"type": self.type}

        if self.text is not None:
            result["text"] = self.text

        if self.attrs:
            result["attrs"] = self.attrs

        if self.marks:
            result["marks"] = [
                {"type": m.type, **({"attrs": m.attrs} if m.attrs else {})}
                for m in self.marks
            ]

        if self.content:
            result["content"] = [child.to_dict() for child in self.content]

        return result


@dataclass
class AdfDocument:
    """Represents a complete ADF document.

    The root document contains version information and the content tree.

    Attributes:
        version: ADF schema version (usually 1)
        content: List of top-level block nodes
    """

    version: int = 1
    content: List[AdfNode] = field(default_factory=list)

    def find_by_local_id(self, local_id: str) -> Optional[AdfNode]:
        """Find a node anywhere in the document by its localId.

        Args:
            local_id: The localId to search for

        Returns:
            The node with matching localId, or None if not found
        """
        for node in self.content:
            result = node.find_by_local_id(local_id)
            if result:
                return result
        return None

    def get_all_nodes_with_ids(self) -> Dict[str, AdfNode]:
        """Get a mapping of all localIds to their nodes.

        Returns:
            Dictionary mapping localId strings to AdfNode objects
        """
        result: Dict[str, AdfNode] = {}

        def collect(node: AdfNode):
            if node.local_id:
                result[node.local_id] = node
            for child in node.content:
                collect(child)

        for node in self.content:
            collect(node)

        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert the document to ADF JSON format.

        Returns:
            Dictionary suitable for JSON serialization
        """
        return {
            "type": "doc",
            "version": self.version,
            "content": [node.to_dict() for node in self.content],
        }


@dataclass
class AdfBlock:
    """A content block extracted from ADF for diff analysis.

    Similar to ContentBlock but includes the localId for matching.
    This allows surgical updates by ID rather than position signature.

    Attributes:
        node_type: Type of ADF node
        content: Text content (for matching)
        local_id: The localId from ADF (key for surgical updates)
        level: Heading level (1-6) for headings
        node: Reference to the original AdfNode
        rows: Table rows as list of cell lists (for tables)
        index: Position in document (fallback if no localId)
    """

    node_type: AdfNodeType
    content: str
    local_id: Optional[str] = None
    level: int = 0
    node: Optional[AdfNode] = None
    rows: List[List[str]] = field(default_factory=list)
    index: int = 0

    @property
    def is_macro(self) -> bool:
        """Check if this block is a macro."""
        return self.node_type in MACRO_NODE_TYPES


@dataclass
class AdfOperation:
    """Describes a surgical operation to apply to an ADF document.

    Operations target nodes by localId, avoiding position signature problems.
    If target_local_id is None, the operation uses position-based fallback.

    Attributes:
        op_type: Type of operation (from models.OperationType)
        target_local_id: LocalId of the node to modify
        target_content: Content to find (fallback if no localId)
        new_content: New content for updates
        new_level: New heading level (for level changes)
        row_index: Row position (for table operations)
        cell_index: Cell position (for table cell updates)
        after_local_id: LocalId to insert after (for inserts)
    """

    op_type: str  # Will be OperationType value
    target_local_id: Optional[str] = None
    target_content: str = ""
    new_content: str = ""
    new_level: int = 0
    row_index: int = 0
    cell_index: int = 0
    after_local_id: Optional[str] = None


@dataclass
class AdfUpdateResult:
    """Result of applying ADF surgical operations.

    Attributes:
        success: Whether the update succeeded
        page_id: Page that was updated
        old_version: Version before update
        new_version: Version after update
        operations_applied: Number of operations successfully applied
        operations_failed: Number of operations that failed
        modified_adf: The resulting ADF document (as dict)
        error: Error message if success is False
        fallback_used: True if fell back to full replacement
    """

    success: bool
    page_id: str
    old_version: int
    new_version: int
    operations_applied: int
    operations_failed: int = 0
    modified_adf: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    fallback_used: bool = False
