"""Data models for file mapper.

This module defines all data models used by the file mapper library.
All models use dataclasses for clean, type-safe data structures.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional


@dataclass
class PageNode:
    """Represents a node in the Confluence page hierarchy.

    Used for building the tree structure of pages discovered via CQL queries.
    Each node represents a single Confluence page with its metadata and
    relationships to other pages in the hierarchy.

    Attributes:
        page_id: Unique identifier for the page
        title: Page title
        parent_id: Parent page ID (None if page is at root level)
        children: List of child PageNode objects
        last_modified: ISO 8601 timestamp of last modification (from version.when)
        space_key: Space key where the page resides (e.g., "TEAM")
        markdown_content: Markdown content of the page (converted from XHTML)
        version: Confluence version number
    """
    page_id: str
    title: str
    parent_id: Optional[str]
    children: List['PageNode'] = field(default_factory=list)
    last_modified: str = ""
    space_key: str = ""
    markdown_content: str = ""
    version: int = 1


@dataclass
class LocalPage:
    """Represents a local markdown file with YAML frontmatter.

    Simplified model containing only essential data. Title and metadata
    are derived on-the-fly from CQL results, H1 headings, or filenames.

    Other metadata (space_key, title) is derived from config and file path.
    Sync timestamps are tracked globally in state.yaml, not per-file.

    Attributes:
        file_path: Absolute or relative path to the markdown file
        page_id: Confluence page ID (None for new local files not yet synced)
        content: Markdown content (without frontmatter)
        space_key: Confluence space key (for generating confluence_url)
        confluence_base_url: Base Confluence URL (e.g., https://domain.atlassian.net/wiki)
    """
    file_path: str
    page_id: Optional[str]
    content: str = ""
    space_key: Optional[str] = None
    confluence_base_url: Optional[str] = None


@dataclass
class SpaceConfig:
    """Configuration for a single Confluence space sync.

    Defines which Confluence space to sync and which pages to exclude.
    The parent_page_id serves as the anchor point for the hierarchy (ADR-012).

    Attributes:
        space_key: Space key to sync (e.g., "TEAM")
        parent_page_id: Page ID to use as root of the hierarchy
        local_path: Local directory path for synced files
        exclude_page_ids: List of page IDs to exclude from sync (ADR-015)
        exclude_parent: If True, exclude the parent page from sync (only sync children)
        confluence_base_url: Base Confluence URL (e.g., https://domain.atlassian.net/wiki)
    """
    space_key: str
    parent_page_id: str
    local_path: str
    exclude_page_ids: List[str] = field(default_factory=list)
    exclude_parent: bool = False
    confluence_base_url: str = ""


@dataclass
class SyncResult:
    """Result of a sync operation, including conflict information.

    Used to propagate conflict details from FileMapper to the CLI layer
    for conflict resolution via 3-way merge.

    Attributes:
        pushed_count: Number of pages pushed to Confluence
        pulled_count: Number of pages pulled from Confluence
        conflict_page_ids: List of page IDs with conflicts (modified on both sides)
        conflict_local_paths: Dict mapping page_id to local file path for conflicts
        conflict_remote_content: Dict mapping page_id to remote XHTML content
        conflict_titles: Dict mapping page_id to page title
    """
    pushed_count: int = 0
    pulled_count: int = 0
    conflict_page_ids: List[str] = field(default_factory=list)
    conflict_local_paths: dict = field(default_factory=dict)
    conflict_remote_content: dict = field(default_factory=dict)
    conflict_titles: dict = field(default_factory=dict)


@dataclass
class SyncConfig:
    """Overall sync configuration with options and space configs.

    Top-level configuration object that includes sync behavior options
    and one or more space configurations.

    Attributes:
        spaces: List of SpaceConfig objects to sync
        page_limit: Maximum pages allowed per level (default 100, ADR-013)
        force_pull: Force sync from Confluence even if local has changes
        force_push: Force sync to Confluence even if remote has changes
        temp_dir: Temporary directory for atomic operations (ADR-011)
        last_synced: ISO 8601 timestamp of last successful sync (for mtime comparison)
        get_baseline: Callback to retrieve baseline content for a page_id.
                      Signature: (page_id: str) -> Optional[str]
                      Returns baseline content or None if no baseline exists.
    """
    spaces: List[SpaceConfig] = field(default_factory=list)
    page_limit: int = 100
    force_pull: bool = False
    force_push: bool = False
    temp_dir: str = ".confluence-sync/temp"
    last_synced: Optional[str] = None
    get_baseline: Optional[Callable[[str], Optional[str]]] = None
