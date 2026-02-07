"""Change detection logic for bidirectional sync.

This module implements timestamp-based change detection per ADR-014.
It compares local file modification times (mtime) and Confluence page
last_modified timestamps against the project-level last_synced timestamp
to categorize pages into unchanged, to_push, to_pull, and conflicts.

The change detector accepts data from CQL query results (PageNode trees)
rather than making separate API calls. This improves performance by reusing
data already fetched during hierarchy building.
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Union

from src.cli.errors import CLIError
from src.cli.models import ChangeDetectionResult, MoveResult
from src.file_mapper.models import PageNode

logger = logging.getLogger(__name__)


class ChangeDetector:
    """Timestamp-based change detector for bidirectional sync.

    This class implements the core change detection logic that determines
    which pages need to be synced in which direction. It uses a three-way
    comparison between:
    - Local file modification time (mtime)
    - Confluence page last_modified timestamp
    - Project-level last_synced timestamp

    The detection logic per ADR-014:
    - unchanged: Both local and remote unchanged since last_synced
    - to_push: Local changed, remote unchanged (push to Confluence)
    - to_pull: Remote changed, local unchanged (pull from Confluence)
    - conflicts: Both changed since last_synced (requires resolution)

    Example:
        >>> detector = ChangeDetector()
        >>> result = detector.detect_changes(
        ...     local_pages=pages,
        ...     remote_pages=remote_data,
        ...     last_synced="2024-01-15T10:30:00Z"
        ... )
        >>> print(f"To push: {len(result.to_push)}")
        >>> print(f"Conflicts: {len(result.conflicts)}")
    """

    def __init__(self):
        """Initialize change detector."""
        pass

    @staticmethod
    def flatten_page_tree(root: PageNode) -> Dict[str, str]:
        """Flatten PageNode tree to dict mapping page_id to last_modified timestamp.

        This helper method converts the hierarchical PageNode tree structure
        (from CQL query results) into the flat dictionary format expected by
        change detection methods.

        Args:
            root: Root PageNode of the hierarchy tree

        Returns:
            Dict mapping page_id (str) to last_modified ISO timestamp (str)

        Example:
            >>> tree = hierarchy_builder.build_hierarchy("123", "SPACE")
            >>> remote_pages = ChangeDetector.flatten_page_tree(tree)
            >>> # Returns: {"123": "2024-01-15T10:30:00Z", "456": "2024-01-15T11:00:00Z", ...}
        """
        pages = {}

        def collect_pages(node: PageNode):
            """Recursively collect all pages from tree."""
            # Add current node
            pages[str(node.page_id)] = node.last_modified
            # Add all children recursively
            for child in node.children:
                collect_pages(child)

        collect_pages(root)
        return pages

    @staticmethod
    def flatten_page_tree_with_metadata(root: PageNode) -> Dict[str, Dict]:
        """Flatten PageNode tree to dict with full page metadata.

        This helper method converts the hierarchical PageNode tree structure
        into a flat dictionary with complete page data including ancestors.
        Used for move detection which needs ancestor information.

        Args:
            root: Root PageNode of the hierarchy tree

        Returns:
            Dict mapping page_id (str) to dict with page metadata including
            title, last_modified, space_key, and parent_id

        Example:
            >>> tree = hierarchy_builder.build_hierarchy("123", "SPACE")
            >>> pages_with_ancestors = ChangeDetector.flatten_page_tree_with_metadata(tree)
            >>> # Returns: {"123": {"title": "Page", "parent_id": None, ...}, ...}
        """
        pages = {}

        def collect_pages_with_metadata(node: PageNode):
            """Recursively collect all pages with full metadata."""
            # Add current node with metadata
            pages[str(node.page_id)] = {
                "title": node.title,
                "last_modified": node.last_modified,
                "space_key": node.space_key,
                "parent_id": node.parent_id,
                "page_id": node.page_id,
            }
            # Add all children recursively
            for child in node.children:
                collect_pages_with_metadata(child)

        collect_pages_with_metadata(root)
        return pages

    def detect_changes(
        self,
        local_pages: Dict[str, str],
        remote_pages: Union[Dict[str, str], PageNode],
        last_synced: Optional[str] = None,
    ) -> ChangeDetectionResult:
        """Detect changes between local and remote pages.

        This method performs timestamp comparison to categorize all pages
        in the sync scope. It handles the following scenarios:
        - First sync (last_synced is None): All local pages marked to_push
        - Normal sync: Three-way timestamp comparison
        - Missing files: Gracefully handled (logged and skipped)

        The remote_pages data comes from CQL query results (PageNode tree from
        HierarchyBuilder) rather than separate API calls. This reuses data
        already fetched during page hierarchy discovery.

        Args:
            local_pages: Dict mapping page_id to local file path
            remote_pages: Either a Dict mapping page_id to last_modified ISO timestamp,
                         or a PageNode tree from HierarchyBuilder (will be flattened automatically)
            last_synced: ISO 8601 timestamp of last sync (None if first sync)

        Returns:
            ChangeDetectionResult with categorized page IDs

        Raises:
            CLIError: If timestamp parsing or file access fails critically

        Example:
            >>> # Using dict format
            >>> local = {"123": "/path/to/page.md"}
            >>> remote = {"123": "2024-01-15T10:30:00Z"}
            >>> result = detector.detect_changes(local, remote, "2024-01-15T09:00:00Z")
            >>>
            >>> # Using PageNode tree from CQL results
            >>> tree = hierarchy_builder.build_hierarchy("123", "SPACE")
            >>> result = detector.detect_changes(local, tree, "2024-01-15T09:00:00Z")
        """
        # Convert PageNode tree to dict if needed
        if isinstance(remote_pages, PageNode):
            remote_pages_dict = self.flatten_page_tree(remote_pages)
        else:
            remote_pages_dict = remote_pages

        logger.info(
            f"Detecting changes for {len(local_pages)} local pages, "
            f"{len(remote_pages_dict)} remote pages"
        )

        if last_synced:
            logger.info(f"Last synced: {last_synced}")
        else:
            logger.info("First sync (no last_synced timestamp)")

        result = ChangeDetectionResult()

        # Parse last_synced timestamp once
        last_synced_dt = None
        if last_synced:
            try:
                last_synced_dt = self._parse_timestamp(last_synced)
            except ValueError as e:
                logger.error(f"Invalid last_synced timestamp: {e}")
                raise CLIError(f"Invalid last_synced timestamp: {last_synced}")

        # Get all unique page IDs from both local and remote
        all_page_ids = set(local_pages.keys()) | set(remote_pages_dict.keys())
        logger.debug(f"Total unique page IDs: {len(all_page_ids)}")

        # Categorize each page
        for page_id in all_page_ids:
            try:
                self._categorize_page(
                    page_id=page_id,
                    local_path=local_pages.get(page_id),
                    remote_modified=remote_pages_dict.get(page_id),
                    last_synced_dt=last_synced_dt,
                    result=result,
                )
            except Exception as e:
                # Log error but continue processing other pages
                logger.error(f"Error processing page {page_id}: {e}")
                # For safety, treat errors as conflicts so they get manual attention
                result.conflicts.append(page_id)

        logger.info(
            f"Change detection complete: "
            f"{len(result.unchanged)} unchanged, "
            f"{len(result.to_push)} to push, "
            f"{len(result.to_pull)} to pull, "
            f"{len(result.conflicts)} conflicts"
        )

        return result

    def _categorize_page(
        self,
        page_id: str,
        local_path: Optional[str],
        remote_modified: Optional[Union[str, dict]],
        last_synced_dt: Optional[datetime],
        result: ChangeDetectionResult,
    ) -> None:
        """Categorize a single page based on timestamp comparison.

        Args:
            page_id: Confluence page ID
            local_path: Local file path (None if page doesn't exist locally)
            remote_modified: Remote last_modified ISO timestamp (None if not in Confluence).
                           Can be a string timestamp or a dict with 'last_modified' key.
            last_synced_dt: Parsed last_synced datetime (None for first sync)
            result: ChangeDetectionResult to update in-place
        """
        # Extract timestamp from dict if needed (supports new richer format)
        if isinstance(remote_modified, dict):
            remote_modified = remote_modified.get("last_modified")

        # Handle missing pages (only on one side)
        if not local_path and remote_modified:
            # Page exists only remotely - pull it
            logger.debug(f"Page {page_id}: Remote only -> to_pull")
            result.to_pull.append(page_id)
            return

        if local_path and not remote_modified:
            # Page exists only locally - push it
            logger.debug(f"Page {page_id}: Local only -> to_push")
            result.to_push.append(page_id)
            return

        # At this point, page exists both locally and remotely
        if not local_path or not remote_modified:
            # This shouldn't happen given above checks, but be defensive
            logger.warning(f"Page {page_id}: Unexpected state, marking as conflict")
            result.conflicts.append(page_id)
            return

        # First sync case: push everything
        if last_synced_dt is None:
            logger.debug(f"Page {page_id}: First sync -> to_push")
            result.to_push.append(page_id)
            return

        # Get local file mtime
        try:
            local_mtime = self._get_file_mtime(local_path)
        except OSError as e:
            logger.warning(f"Page {page_id}: Cannot read file {local_path}: {e}")
            # Treat as conflict to get manual attention
            result.conflicts.append(page_id)
            return

        # Parse remote timestamp
        try:
            remote_dt = self._parse_timestamp(remote_modified)
        except ValueError as e:
            logger.warning(f"Page {page_id}: Invalid remote timestamp: {e}")
            # Treat as conflict
            result.conflicts.append(page_id)
            return

        # Three-way comparison
        local_changed = local_mtime > last_synced_dt
        remote_changed = remote_dt > last_synced_dt

        if not local_changed and not remote_changed:
            # Neither changed
            logger.debug(f"Page {page_id}: Unchanged")
            result.unchanged.append(page_id)
        elif local_changed and not remote_changed:
            # Only local changed
            logger.debug(f"Page {page_id}: Local changed -> to_push")
            result.to_push.append(page_id)
        elif remote_changed and not local_changed:
            # Only remote changed
            logger.debug(f"Page {page_id}: Remote changed -> to_pull")
            result.to_pull.append(page_id)
        else:
            # Both changed - conflict
            logger.debug(f"Page {page_id}: Both changed -> conflict")
            result.conflicts.append(page_id)

    def _get_file_mtime(self, file_path: str) -> datetime:
        """Get file modification time as datetime.

        Args:
            file_path: Path to file

        Returns:
            File modification time as timezone-aware datetime (UTC)

        Raises:
            OSError: If file cannot be accessed
        """
        # Get mtime as timestamp
        mtime_timestamp = os.path.getmtime(file_path)

        # Convert to datetime (UTC)
        # Use fromtimestamp with UTC timezone to match Confluence timestamps
        mtime_dt = datetime.fromtimestamp(mtime_timestamp)

        return mtime_dt

    def detect_deletions(
        self,
        local_pages: Dict[str, str],
        tracked_pages: Dict[str, str],
        remote_pages: Union[Dict[str, str], PageNode],
    ) -> "DeletionResult":
        """Detect page deletions in both Confluence and local filesystem.

        This method compares the tracked_pages from state.yaml (pages that
        existed at last sync) with current local and remote state to identify
        deletions in either direction.

        Detection logic:
        - Confluence deletion: Page in tracked_pages but not in remote_pages
        - Local deletion: Page in tracked_pages but not in local_pages

        The remote_pages data comes from CQL query results (PageNode tree)
        rather than separate API calls.

        Args:
            local_pages: Dict mapping page_id to local file path (current state)
            tracked_pages: Dict mapping page_id to local file path (from state.yaml)
            remote_pages: Either a Dict mapping page_id to last_modified ISO timestamp,
                         or a PageNode tree from HierarchyBuilder (will be flattened automatically)

        Returns:
            DeletionResult with categorized deletions

        Example:
            >>> tracked = {"123": "/path/to/page.md", "456": "/path/to/other.md"}
            >>> local = {"123": "/path/to/page.md"}  # 456 deleted locally
            >>> remote = {"123": "2024-01-15T10:30:00Z"}  # 456 deleted in Confluence
            >>> result = detector.detect_deletions(local, tracked, remote)
        """
        from src.cli.models import DeletionResult, DeletionInfo
        from pathlib import Path

        # Convert PageNode tree to dict if needed
        if isinstance(remote_pages, PageNode):
            remote_pages_dict = self.flatten_page_tree(remote_pages)
        else:
            remote_pages_dict = remote_pages

        logger.info(
            f"Detecting deletions: {len(tracked_pages)} tracked pages, "
            f"{len(local_pages)} local pages, {len(remote_pages_dict)} remote pages"
        )

        result = DeletionResult()

        # Detect deletions in Confluence (tracked but not in remote)
        for page_id, local_path in tracked_pages.items():
            if page_id not in remote_pages_dict:
                # Page was tracked but no longer exists in Confluence
                logger.debug(f"Page {page_id}: Deleted in Confluence")
                result.deleted_in_confluence.append(
                    DeletionInfo(
                        page_id=page_id,
                        title=Path(local_path).stem if local_path else f"Page {page_id}",
                        local_path=Path(local_path) if local_path else None,
                        direction="confluence_to_local",
                    )
                )

        # Detect local deletions (tracked but not in local)
        for page_id, local_path in tracked_pages.items():
            if page_id not in local_pages:
                # Page was tracked but no longer exists locally
                # Only treat as deletion if it still exists remotely
                if page_id in remote_pages_dict:
                    logger.debug(f"Page {page_id}: Deleted locally")
                    result.deleted_locally.append(
                        DeletionInfo(
                            page_id=page_id,
                            title=Path(local_path).stem if local_path else f"Page {page_id}",
                            local_path=None,  # File no longer exists
                            direction="local_to_confluence",
                        )
                    )
                else:
                    # Deleted on both sides - already handled in deleted_in_confluence
                    logger.debug(f"Page {page_id}: Deleted on both sides (already processed)")

        logger.info(
            f"Deletion detection complete: "
            f"{len(result.deleted_in_confluence)} deleted in Confluence, "
            f"{len(result.deleted_locally)} deleted locally"
        )

        return result

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse ISO 8601 timestamp string to datetime.

        Handles various ISO 8601 formats including:
        - 2024-01-15T10:30:00Z
        - 2024-01-15T10:30:00+00:00
        - 2024-01-15T10:30:00.123Z

        Args:
            timestamp_str: ISO 8601 timestamp string

        Returns:
            Parsed datetime object

        Raises:
            ValueError: If timestamp cannot be parsed
        """
        # Try standard ISO format with Z suffix
        if timestamp_str.endswith('Z'):
            # Replace Z with +00:00 for Python's fromisoformat
            timestamp_str = timestamp_str[:-1] + '+00:00'

        try:
            # Python 3.7+ supports fromisoformat
            dt = datetime.fromisoformat(timestamp_str)
            # Remove timezone info for comparison (treat all as UTC)
            return dt.replace(tzinfo=None)
        except ValueError:
            # Try fallback formats
            for fmt in [
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
            ]:
                try:
                    return datetime.strptime(timestamp_str.rstrip('Z'), fmt)
                except ValueError:
                    continue

            # All formats failed
            raise ValueError(f"Cannot parse timestamp: {timestamp_str}")

    def detect_moves(
        self,
        local_pages: Dict[str, str],
        tracked_pages: Dict[str, str],
        pages_with_ancestors: Union[Dict[str, Dict], PageNode],
    ) -> MoveResult:
        """Detect page moves in both Confluence and local filesystem.

        This method compares the tracked_pages from state.yaml (pages that
        existed at last sync) with current local and remote state to identify
        moves in either direction.

        Detection logic:
        - Confluence move: Page path from ancestors differs from tracked path
        - Local move: Current local path differs from tracked path

        The pages_with_ancestors data comes from CQL query results (PageNode tree)
        rather than separate API calls.

        Args:
            local_pages: Dict mapping page_id to current local file path
            tracked_pages: Dict mapping page_id to tracked file path (from state.yaml)
            pages_with_ancestors: Either a Dict mapping page_id to page data with ancestor chain,
                                 or a PageNode tree from HierarchyBuilder (will be flattened automatically)

        Returns:
            MoveResult with categorized moves

        Example:
            >>> tracked = {"123": "/old/path/page.md"}
            >>> local = {"123": "/new/path/page.md"}  # Moved locally
            >>> ancestors = {"123": {"ancestors": [...], "title": "Page"}}
            >>> result = detector.detect_moves(local, tracked, ancestors)
        """
        from src.cli.models import MoveInfo
        from pathlib import Path

        # Convert PageNode tree to dict if needed
        if isinstance(pages_with_ancestors, PageNode):
            pages_dict = self.flatten_page_tree_with_metadata(pages_with_ancestors)
        else:
            pages_dict = pages_with_ancestors

        logger.info(
            f"Detecting moves: {len(tracked_pages)} tracked pages, "
            f"{len(local_pages)} local pages, {len(pages_dict)} pages with ancestors"
        )

        result = MoveResult()

        # Detect moves for each tracked page
        for page_id, tracked_path in tracked_pages.items():
            try:
                # Get current local path and ancestor data
                current_local_path = local_pages.get(page_id)
                page_data = pages_dict.get(page_id)

                # Skip if page was deleted (handled by detect_deletions)
                if not current_local_path and not page_data:
                    # Deleted on both sides
                    logger.debug(f"Page {page_id}: Deleted, skipping move detection")
                    continue

                if not current_local_path:
                    # Deleted locally
                    logger.debug(f"Page {page_id}: Deleted locally, skipping move detection")
                    continue

                if not page_data:
                    # Deleted in Confluence
                    logger.debug(f"Page {page_id}: Deleted in Confluence, skipping move detection")
                    continue

                # Get expected path from Confluence ancestors
                expected_path_from_ancestors = self._get_expected_path_from_ancestors(
                    page_id, page_data
                )

                # Normalize paths for comparison
                tracked_path_normalized = str(Path(tracked_path))
                current_path_normalized = str(Path(current_local_path))
                expected_path_normalized = str(Path(expected_path_from_ancestors)) if expected_path_from_ancestors else None

                # Detect Confluence moves
                if expected_path_normalized and expected_path_normalized != tracked_path_normalized:
                    # Page moved in Confluence (path from ancestors differs from tracked)
                    logger.debug(
                        f"Page {page_id}: Moved in Confluence from {tracked_path_normalized} "
                        f"to {expected_path_normalized}"
                    )
                    result.moved_in_confluence.append(
                        MoveInfo(
                            page_id=page_id,
                            title=page_data.get("title", f"Page {page_id}"),
                            old_path=Path(tracked_path),
                            new_path=Path(expected_path_from_ancestors),
                            direction="confluence_to_local",
                        )
                    )
                # Detect local moves
                elif current_path_normalized != tracked_path_normalized:
                    # Page moved locally (current local path differs from tracked)
                    logger.debug(
                        f"Page {page_id}: Moved locally from {tracked_path_normalized} "
                        f"to {current_path_normalized}"
                    )
                    result.moved_locally.append(
                        MoveInfo(
                            page_id=page_id,
                            title=page_data.get("title", f"Page {page_id}"),
                            old_path=Path(tracked_path),
                            new_path=Path(current_local_path),
                            direction="local_to_confluence",
                        )
                    )
                else:
                    # No move detected
                    logger.debug(f"Page {page_id}: No move detected")

            except Exception as e:
                # Log error but continue processing other pages
                logger.error(f"Error processing page {page_id} for moves: {e}")
                # Continue with next page

        logger.info(
            f"Move detection complete: "
            f"{len(result.moved_in_confluence)} moved in Confluence, "
            f"{len(result.moved_locally)} moved locally"
        )

        return result

    def _get_expected_path_from_ancestors(
        self, page_id: str, page_data: Dict
    ) -> Optional[str]:
        """Build expected local path from Confluence ancestor chain.

        This helper method reconstructs the expected local file path based on
        the page's ancestor hierarchy in Confluence. Used to detect moves.

        Args:
            page_id: Confluence page ID
            page_data: Page data with ancestor information

        Returns:
            Expected local file path based on ancestors, or None if cannot be determined

        Raises:
            No exceptions raised - errors are logged and None is returned
        """
        try:
            # Import AncestorResolver to build path from ancestors
            from src.cli.ancestor_resolver import AncestorResolver

            # Create resolver instance (no page_operations needed for path building)
            resolver = AncestorResolver(page_operations=None)

            # Build path from ancestors
            expected_path = resolver.build_path_from_ancestors(
                page_id=page_id,
                page_data=page_data,
                space_local_path=".",  # Relative to current directory
            )

            return expected_path

        except Exception as e:
            logger.warning(
                f"Page {page_id}: Cannot determine expected path from ancestors: {e}"
            )
            return None
