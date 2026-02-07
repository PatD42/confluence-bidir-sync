"""Confluence page data model."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ConfluencePage:
    """Confluence page with storage format content.

    Represents a Confluence page fetched from the API with all
    metadata required for read and update operations.

    Attributes:
        page_id: Unique identifier for the page
        space_key: Space key where the page resides (e.g., "TEAM")
        title: Page title
        content_storage: Page content in Confluence storage format (XHTML)
        version: Current version number (required for updates)
        labels: List of label names attached to the page
        parent_id: Parent page ID (None if page is at root level)
        children: List of child page IDs (for tree operations)
    """
    page_id: str
    space_key: str
    title: str
    content_storage: str  # XHTML format
    version: int
    labels: List[str]
    parent_id: Optional[str]
    children: List[str]  # Child page IDs
