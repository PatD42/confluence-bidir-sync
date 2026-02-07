"""Data models for page operations module.

This module defines the data structures used throughout the page operations
module for surgical XHTML updates.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional


class BlockType(Enum):
    """Types of content blocks in a document."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    CODE = "code"
    MACRO = "macro"
    OTHER = "other"


class OperationType(Enum):
    """Types of surgical operations that can be applied to XHTML."""

    UPDATE_TEXT = "update_text"
    DELETE_BLOCK = "delete_block"
    INSERT_BLOCK = "insert_block"
    CHANGE_HEADING_LEVEL = "change_heading_level"
    TABLE_INSERT_ROW = "table_insert_row"
    TABLE_DELETE_ROW = "table_delete_row"
    TABLE_UPDATE_CELL = "table_update_cell"


@dataclass
class ContentBlock:
    """Represents a content block (paragraph, heading, table, etc.).

    Used for mapping between markdown and XHTML elements during
    diff analysis.

    Attributes:
        block_type: Type of content block
        content: Text content for matching
        level: Heading level (1-6) for headings, 0 otherwise
        element: BeautifulSoup element reference (for XHTML blocks)
        rows: Table rows as list of cell lists (for tables)
        index: Position in document (for position-based matching)
    """

    block_type: BlockType
    content: str
    level: int = 0
    element: Any = None
    rows: List[List[str]] = field(default_factory=list)
    index: int = 0


@dataclass
class SurgicalOperation:
    """Describes a single surgical operation to apply to XHTML.

    Operations are provided by the caller (from diff analysis) and
    applied by the SurgicalEditor to the original XHTML.

    Attributes:
        op_type: Type of operation to perform
        target_content: Content to find/match in XHTML
        new_content: New content for updates/inserts
        old_level: Original heading level (for level changes)
        new_level: New heading level (for level changes)
        row_index: Row position (for table operations)
        cell_index: Cell position within row (for cell updates)
        after_content: Content to insert after (for inserts)
    """

    op_type: OperationType
    target_content: str = ""
    new_content: str = ""
    old_level: int = 0
    new_level: int = 0
    row_index: int = 0
    cell_index: int = 0
    after_content: str = ""


@dataclass
class PageSnapshot:
    """Complete page state for update operations.

    Contains both XHTML (for surgical updates) and markdown (for agents/diff).
    The xhtml field is the reference that surgical operations are applied to.

    Attributes:
        page_id: Unique Confluence page identifier
        space_key: Space key where page resides
        title: Page title
        xhtml: Original XHTML content (reference for surgical updates)
        markdown: Converted markdown (for agents/tools)
        version: Current version number (for optimistic locking)
        parent_id: Parent page ID (None if at space root)
        labels: List of label names
        last_modified: When the page was last modified
    """

    page_id: str
    space_key: str
    title: str
    xhtml: str
    markdown: str
    version: int
    parent_id: Optional[str]
    labels: List[str]
    last_modified: datetime


@dataclass
class PageVersion:
    """Page version metadata for history listing.

    Attributes:
        version: Version number
        modified_at: When this version was created
        modified_by: User who created this version
        message: Optional version message/comment
    """

    version: int
    modified_at: datetime
    modified_by: str
    message: Optional[str] = None


@dataclass
class UpdateResult:
    """Result of applying surgical operations to a page.

    Attributes:
        success: Whether the update succeeded
        page_id: Page that was updated
        old_version: Version before update
        new_version: Version after update
        operations_applied: Number of operations successfully applied
        modified_xhtml: The resulting XHTML content
        error: Error message if success is False
    """

    success: bool
    page_id: str
    old_version: int
    new_version: int
    operations_applied: int
    modified_xhtml: str = ""
    error: Optional[str] = None


@dataclass
class CreateResult:
    """Result of creating a new page.

    Attributes:
        success: Whether creation succeeded
        page_id: ID of created page (None if failed)
        space_key: Space where page was created
        title: Page title
        version: Initial version (usually 1)
        error: Error message if success is False
    """

    success: bool
    page_id: Optional[str]
    space_key: str
    title: str
    version: int = 1
    error: Optional[str] = None
