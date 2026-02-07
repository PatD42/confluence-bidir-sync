"""Data models for git integration module.

This module defines the data structures used throughout the git integration
module for conflict detection, merging, and synchronization.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class MergeStrategy(Enum):
    """Merge strategies for sync operation."""

    THREE_WAY = "three_way"  # Default: git merge with conflict detection
    FORCE_PUSH = "force_push"  # Overwrite Confluence with local
    FORCE_PULL = "force_pull"  # Overwrite local with Confluence


@dataclass
class LocalPage:
    """Represents a local markdown file in sync scope.

    Attributes:
        page_id: Confluence page ID (from frontmatter)
        file_path: Path to local .md file
        local_version: Version from frontmatter
        title: Page title (for display)
    """

    page_id: str
    file_path: str
    local_version: int
    title: str


@dataclass
class ConflictInfo:
    """Information about a detected conflict.

    Attributes:
        page_id: Confluence page ID
        file_path: Local file path
        local_version: Version in local frontmatter
        remote_version: Current Confluence version
        has_base: Whether base version found in git history
    """

    page_id: str
    file_path: str
    local_version: int
    remote_version: int
    has_base: bool


@dataclass
class ConflictDetectionResult:
    """Result of batch conflict detection.

    Attributes:
        conflicts: Pages with conflicts requiring resolution
        auto_mergeable: Pages that can auto-merge (no conflicts)
        errors: Pages that failed conflict detection
    """

    conflicts: List[ConflictInfo]
    auto_mergeable: List[LocalPage]
    errors: List[tuple[str, str]]  # (page_id, error_message)


@dataclass
class ThreeWayMergeInputs:
    """Inputs for three-way git merge.

    Attributes:
        page_id: Confluence page ID
        base_markdown: Base version markdown (from git history)
        local_markdown: Local file markdown
        remote_markdown: Confluence current version markdown
        local_version: Version number for base/local
        remote_version: Version number for remote
    """

    page_id: str
    base_markdown: str
    local_markdown: str
    remote_markdown: str
    local_version: int
    remote_version: int


@dataclass
class MergeResult:
    """Result of git merge operation.

    Attributes:
        success: Whether merge succeeded without conflicts
        merged_markdown: Merged content (if success or after resolution)
        conflict_file: Path to .conflict file (if conflicts)
        git_output: Git merge command output
    """

    success: bool
    merged_markdown: str = ""
    conflict_file: Optional[str] = None
    git_output: str = ""


@dataclass
class MergeToolResult:
    """Result of merge tool execution.

    Attributes:
        success: Whether tool exited successfully
        resolved_content: Merged content from tool
        error: Error message if tool failed
    """

    success: bool
    resolved_content: str = ""
    error: Optional[str] = None


@dataclass
class SyncResult:
    """Overall result of sync operation.

    Attributes:
        success: Whether entire sync succeeded
        pages_synced: Number of pages successfully synced
        pages_failed: Number of pages that failed
        conflicts_resolved: Number of conflicts resolved
        errors: Error messages by page_id
    """

    success: bool
    pages_synced: int
    pages_failed: int
    conflicts_resolved: int
    errors: dict[str, str] = field(default_factory=dict)  # page_id -> error


@dataclass
class CachedPage:
    """Cached XHTML metadata.

    Attributes:
        page_id: Confluence page ID
        version: Version number
        xhtml: XHTML content
        last_modified: Confluence last_modified timestamp
        cached_at: When this entry was cached
    """

    page_id: str
    version: int
    xhtml: str
    last_modified: datetime
    cached_at: datetime
