"""Data models for CLI operations.

This module defines all data models used by the CLI module.
All models use dataclasses for clean, type-safe data structures,
following the patterns established in src/file_mapper/models.py.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Dict, List, Literal, Optional


class ExitCode(IntEnum):
    """Exit codes for CLI operations per ADR-016.

    These exit codes provide meaningful feedback about the operation result:
    - SUCCESS (0): Operation completed successfully
    - GENERAL_ERROR (1): General error (config issues, validation failures)
    - CONFLICTS (2): Unresolved conflicts detected during sync
    - AUTH_ERROR (3): Authentication or authorization failure
    - NETWORK_ERROR (4): Network connectivity or API availability issues

    Example:
        >>> exit_code = ExitCode.SUCCESS
        >>> sys.exit(exit_code)
    """
    SUCCESS = 0
    GENERAL_ERROR = 1
    CONFLICTS = 2
    AUTH_ERROR = 3
    NETWORK_ERROR = 4


@dataclass
class SyncState:
    """Project-level sync state tracked in .confluence-sync/state.yaml.

    The sync state maintains the last successful sync timestamp at the
    project level (not per-file) per ADR-013. This timestamp is used
    for bidirectional change detection.

    Attributes:
        last_synced: ISO 8601 timestamp of last successful sync (None if never synced)
        tracked_pages: Dict mapping page_id to local file path for all synced pages

    Example:
        >>> state = SyncState(last_synced="2024-01-15T10:30:00Z")
        >>> state = SyncState()  # Never synced
    """
    last_synced: Optional[str] = None
    tracked_pages: Dict[str, str] = field(default_factory=dict)


@dataclass
class ChangeDetectionResult:
    """Result of timestamp-based change detection per ADR-014.

    Contains categorized lists of pages based on timestamp comparison:
    - unchanged: Neither local nor remote modified since last sync
    - to_push: Local modified, remote unchanged (push to Confluence)
    - to_pull: Remote modified, local unchanged (pull from Confluence)
    - conflicts: Both local and remote modified (requires resolution)

    Attributes:
        unchanged: List of page IDs with no changes detected
        to_push: List of page IDs that need to be pushed to Confluence
        to_pull: List of page IDs that need to be pulled from Confluence
        conflicts: List of page IDs with conflicting changes on both sides

    Example:
        >>> result = ChangeDetectionResult(
        ...     to_push=["123", "456"],
        ...     to_pull=["789"],
        ...     conflicts=["012"]
        ... )
    """
    unchanged: List[str] = field(default_factory=list)
    to_push: List[str] = field(default_factory=list)
    to_pull: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)


@dataclass
class SyncSummary:
    """Summary of sync operation results for display to user.

    Contains counts of pages processed in each category. Used by
    OutputHandler to display human-readable sync summaries.

    Attributes:
        pushed_count: Number of pages successfully pushed to Confluence
        pulled_count: Number of pages successfully pulled from Confluence
        conflict_count: Number of conflicts detected or resolved
        unchanged_count: Number of pages with no changes detected

    Example:
        >>> summary = SyncSummary(pushed_count=5, pulled_count=3)
        >>> print(f"Pushed {summary.pushed_count} pages")
    """
    pushed_count: int = 0
    pulled_count: int = 0
    conflict_count: int = 0
    unchanged_count: int = 0


@dataclass
class DeletionInfo:
    """Represents a pending deletion operation.

    Contains information about a page that needs to be deleted in either
    Confluence or the local file system. The direction field indicates
    which side the deletion will be executed on.

    Attributes:
        page_id: Confluence page ID
        title: Page title for display purposes
        local_path: Local file path (None if deleted locally already)
        direction: Direction of deletion operation

    Example:
        >>> info = DeletionInfo(
        ...     page_id="123456",
        ...     title="My Page",
        ...     local_path=Path("docs/my-page.md"),
        ...     direction="confluence_to_local"
        ... )
    """
    page_id: str
    title: str
    local_path: Optional[Path]
    direction: Literal["confluence_to_local", "local_to_confluence"]


@dataclass
class DeletionResult:
    """Result of deletion detection.

    Contains lists of deletions detected in both directions during
    change detection. Used to coordinate deletion operations.

    Attributes:
        deleted_in_confluence: Pages deleted in Confluence (delete local files)
        deleted_locally: Pages deleted locally (delete in Confluence)

    Example:
        >>> result = DeletionResult(
        ...     deleted_in_confluence=[deletion_info_1],
        ...     deleted_locally=[deletion_info_2]
        ... )
    """
    deleted_in_confluence: List[DeletionInfo] = field(default_factory=list)
    deleted_locally: List[DeletionInfo] = field(default_factory=list)


@dataclass
class MoveInfo:
    """Represents a pending move operation.

    Contains information about a page that has been moved in either
    Confluence or the local file system. The direction field indicates
    which side initiated the move.

    Attributes:
        page_id: Confluence page ID
        title: Page title for display purposes
        old_path: Original file path before the move
        new_path: Target file path after the move
        direction: Direction of move operation

    Example:
        >>> info = MoveInfo(
        ...     page_id="123456",
        ...     title="My Page",
        ...     old_path=Path("docs/old-location/my-page.md"),
        ...     new_path=Path("docs/new-location/my-page.md"),
        ...     direction="confluence_to_local"
        ... )
    """
    page_id: str
    title: str
    old_path: Path
    new_path: Path
    direction: Literal["confluence_to_local", "local_to_confluence"]


@dataclass
class MoveResult:
    """Result of move detection.

    Contains lists of moves detected in both directions during
    change detection. Used to coordinate move operations.

    Attributes:
        moved_in_confluence: Pages moved in Confluence (move local files)
        moved_locally: Pages moved locally (update Confluence parent)

    Example:
        >>> result = MoveResult(
        ...     moved_in_confluence=[move_info_1],
        ...     moved_locally=[move_info_2]
        ... )
    """
    moved_in_confluence: List[MoveInfo] = field(default_factory=list)
    moved_locally: List[MoveInfo] = field(default_factory=list)


@dataclass
class MergeResult:
    """Result of a 3-way merge operation for a single file.

    Contains the merged content and conflict status from a 3-way merge
    using git merge-file. The merged_content may contain git-style
    conflict markers if has_conflicts is True.

    Attributes:
        merged_content: The resulting content after merge attempt (may contain markers)
        has_conflicts: True if the merge produced conflicts requiring manual resolution
        conflict_count: Number of conflict regions detected in the merge

    Example:
        >>> result = MergeResult(
        ...     merged_content="# Title\nMerged content...",
        ...     has_conflicts=False,
        ...     conflict_count=0
        ... )
        >>> conflict_result = MergeResult(
        ...     merged_content="<<<<<<< local\nlocal version\n=======\nremote version\n>>>>>>> remote",
        ...     has_conflicts=True,
        ...     conflict_count=1
        ... )
    """
    merged_content: str
    has_conflicts: bool
    conflict_count: int = 0


@dataclass
class ConflictInfo:
    """Information about a page with unresolved merge conflicts.

    Contains details about a page that has conflicting changes that
    could not be auto-merged. The conflict_markers field contains
    the full file content with git-style conflict markers.

    Attributes:
        page_id: Confluence page ID
        title: Page title for display purposes
        local_path: Local file path where conflicts exist
        conflict_markers: Full file content with <<<<<<< ======= >>>>>>> markers

    Example:
        >>> info = ConflictInfo(
        ...     page_id="123456",
        ...     title="My Page",
        ...     local_path=Path("docs/my-page.md"),
        ...     conflict_markers="<<<<<<< local\n...\n=======\n...\n>>>>>>> remote"
        ... )
    """
    page_id: str
    title: str
    local_path: Path
    conflict_markers: str


@dataclass
class ConflictResolutionResult:
    """Result of conflict resolution phase for all pages.

    Contains summary counts and details of conflicts detected during
    the 3-way merge phase. Used by OutputHandler to display conflict
    summaries to the user.

    Attributes:
        auto_merged_count: Number of pages successfully auto-merged
        failed_count: Number of pages with unresolved conflicts
        conflicts: Details of pages requiring manual resolution

    Example:
        >>> result = ConflictResolutionResult(
        ...     auto_merged_count=5,
        ...     failed_count=2,
        ...     conflicts=[conflict_info_1, conflict_info_2]
        ... )
    """
    auto_merged_count: int = 0
    failed_count: int = 0
    conflicts: List[ConflictInfo] = field(default_factory=list)
