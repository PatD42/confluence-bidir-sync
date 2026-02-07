"""Page operations module for surgical Confluence updates.

This module provides low-level page operations that enable surgical
XHTML and ADF updates based on markdown changes, preserving all
Confluence-specific formatting (macros, labels, local-ids, table structure).

Key classes:
    PageOperations: Main interface for page read/write operations
    SurgicalEditor: Applies surgical operations to XHTML DOM
    AdfEditor: Applies surgical operations to ADF documents
    AdfParser: Parses ADF JSON documents
    ContentParser: Extracts content blocks from XHTML/markdown
    DiffAnalyzer: Generates surgical operations from content block diffs
    MacroPreserver: Handles macro preservation during conversion
    PageSnapshot: Complete page state for update operations
    SurgicalOperation: Describes a single surgical operation
"""

from .models import (
    PageSnapshot,
    PageVersion,
    SurgicalOperation,
    OperationType,
    ContentBlock,
    BlockType,
    UpdateResult,
    CreateResult,
)
from .adf_models import (
    AdfDocument,
    AdfNode,
    AdfBlock,
    AdfNodeType,
    AdfOperation,
    AdfUpdateResult,
)
from .adf_parser import AdfParser
from .adf_editor import AdfEditor
from .surgical_editor import SurgicalEditor
from .content_parser import ContentParser
from .diff_analyzer import DiffAnalyzer
from .macro_preserver import MacroPreserver, MacroInfo
from .page_operations import PageOperations

__all__ = [
    # Main interface
    "PageOperations",
    # Core classes
    "SurgicalEditor",
    "AdfEditor",
    "AdfParser",
    "ContentParser",
    "DiffAnalyzer",
    "MacroPreserver",
    "MacroInfo",
    # Data models
    "PageSnapshot",
    "PageVersion",
    "SurgicalOperation",
    "OperationType",
    "ContentBlock",
    "BlockType",
    "UpdateResult",
    "CreateResult",
    # ADF models
    "AdfDocument",
    "AdfNode",
    "AdfBlock",
    "AdfNodeType",
    "AdfOperation",
    "AdfUpdateResult",
]
