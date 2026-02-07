"""Conflict resolution orchestration for 3-way merge.

This module implements the ConflictResolver which orchestrates 3-way merge
conflict resolution using the BaselineManager. When both local and remote
versions of a page have changed since last sync, this resolver attempts to
auto-merge non-overlapping changes using git merge-file.

The 3-way merge process:
- baseline: Content from last successful sync (via BaselineManager)
- local: Current local file content
- remote: Current Confluence page content

Non-overlapping changes are auto-merged successfully. Overlapping changes
produce conflict markers in the local file for manual resolution.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from src.cli.baseline_manager import BaselineManager
from src.cli.errors import CLIError
from src.cli.models import ConflictInfo, ConflictResolutionResult, MergeResult

logger = logging.getLogger(__name__)


class ConflictResolver:
    """Orchestrates 3-way merge conflict resolution.

    This class handles the conflict resolution phase of bidirectional sync.
    For each page with conflicting changes, it attempts to auto-merge using
    a 3-way merge algorithm (git merge-file) via BaselineManager.

    The resolution process:
    1. For each conflicting page, fetch baseline content
    2. Perform 3-way merge with baseline, local, and remote content
    3. If merge succeeds: write auto-merged content to local file
    4. If merge fails: write conflict markers to local file for manual resolution

    Example:
        >>> resolver = ConflictResolver(baseline_manager, file_mapper)
        >>> result = resolver.resolve_conflicts(
        ...     conflicting_page_ids=["123", "456"],
        ...     local_pages={"123": "/path/to/page.md"},
        ...     remote_content={"123": "remote content..."}
        ... )
        >>> print(f"Auto-merged: {result.auto_merged_count}")
        >>> print(f"Conflicts: {result.failed_count}")
    """

    def __init__(
        self,
        baseline_manager: BaselineManager,
        file_mapper: Optional[object] = None
    ):
        """Initialize conflict resolver.

        Args:
            baseline_manager: BaselineManager for 3-way merge operations
            file_mapper: Optional FileMapper for file I/O operations
        """
        self.baseline_manager = baseline_manager
        self.file_mapper = file_mapper
        logger.debug("ConflictResolver initialized")

    def resolve_conflicts(
        self,
        conflicting_page_ids: List[str],
        local_pages: Dict[str, str],
        remote_content: Dict[str, str],
        page_titles: Optional[Dict[str, str]] = None,
        dryrun: bool = False,
    ) -> ConflictResolutionResult:
        """Resolve conflicts for all conflicting pages using 3-way merge.

        This method processes each conflicting page by attempting a 3-way merge
        using the baseline content (from last sync), current local content, and
        current remote content. Auto-merged pages have their local files updated
        with the merged content. Pages with overlapping conflicts have conflict
        markers written to the local file for manual resolution.

        Args:
            conflicting_page_ids: List of page IDs with conflicting changes
            local_pages: Dict mapping page_id to local file path
            remote_content: Dict mapping page_id to remote page content
            page_titles: Optional dict mapping page_id to page title (for display)
            dryrun: If True, perform merge analysis without writing files

        Returns:
            ConflictResolutionResult with counts and conflict details

        Raises:
            CLIError: If baseline repository is not initialized

        Example:
            >>> result = resolver.resolve_conflicts(
            ...     conflicting_page_ids=["123"],
            ...     local_pages={"123": "/path/to/page.md"},
            ...     remote_content={"123": "remote content..."},
            ...     page_titles={"123": "My Page"}
            ... )
        """
        logger.info(
            f"Resolving conflicts for {len(conflicting_page_ids)} pages "
            f"(dryrun={dryrun})"
        )

        # Validate baseline is initialized
        if not self.baseline_manager.is_initialized():
            logger.error("Baseline repository not initialized - cannot resolve conflicts")
            raise CLIError(
                "Baseline repository not initialized. Run sync at least once to "
                "create baseline before conflicts can be resolved."
            )

        result = ConflictResolutionResult()
        page_titles = page_titles or {}

        # Process each conflicting page
        for page_id in conflicting_page_ids:
            try:
                self._resolve_single_conflict(
                    page_id=page_id,
                    local_path=local_pages.get(page_id),
                    remote_content_str=remote_content.get(page_id),
                    page_title=page_titles.get(page_id, page_id),
                    result=result,
                    dryrun=dryrun,
                )
            except Exception as e:
                # Log error but continue processing other pages
                logger.error(f"Error resolving conflict for page {page_id}: {e}")
                # Treat as unresolved conflict
                local_path_str = local_pages.get(page_id, f"<unknown path for {page_id}>")
                local_path = Path(local_path_str) if local_path_str else Path(f"{page_id}.md")
                conflict_info = ConflictInfo(
                    page_id=page_id,
                    title=page_titles.get(page_id, page_id),
                    local_path=local_path,
                    conflict_markers=f"Error during merge: {e}",
                )
                result.conflicts.append(conflict_info)
                result.failed_count += 1

        logger.info(
            f"Conflict resolution complete: "
            f"{result.auto_merged_count} auto-merged, "
            f"{result.failed_count} require manual resolution"
        )

        return result

    def _resolve_single_conflict(
        self,
        page_id: str,
        local_path: Optional[str],
        remote_content_str: Optional[str],
        page_title: str,
        result: ConflictResolutionResult,
        dryrun: bool,
    ) -> None:
        """Resolve conflict for a single page using 3-way merge.

        Args:
            page_id: Confluence page ID
            local_path: Local file path (None if page doesn't exist locally)
            remote_content_str: Remote page content (None if not in Confluence)
            page_title: Page title for display purposes
            result: ConflictResolutionResult to update in-place
            dryrun: If True, analyze merge without writing files
        """
        # Validate inputs
        if not local_path:
            logger.warning(f"Page {page_id}: No local path found, skipping merge")
            return

        if not remote_content_str:
            logger.warning(f"Page {page_id}: No remote content found, skipping merge")
            return

        local_path_obj = Path(local_path)

        # Get baseline content
        baseline_content = self.baseline_manager.get_baseline_content(page_id)
        if baseline_content is None:
            logger.warning(
                f"Page {page_id}: No baseline content found - treating as new conflict"
            )
            # Without baseline, cannot perform 3-way merge
            # Write conflict markers to local file
            self._write_conflict_markers(
                local_path_obj,
                remote_content_str,
                page_id,
                page_title,
                result,
                dryrun,
            )
            return

        # Get local content
        try:
            local_content = local_path_obj.read_text(encoding="utf-8")
        except OSError as e:
            logger.error(f"Page {page_id}: Cannot read local file {local_path}: {e}")
            # Treat as unresolved conflict
            conflict_info = ConflictInfo(
                page_id=page_id,
                title=page_title,
                local_path=local_path_obj,
                conflict_markers=f"Error reading local file: {e}",
            )
            result.conflicts.append(conflict_info)
            result.failed_count += 1
            return

        # Perform 3-way merge
        logger.debug(f"Page {page_id}: Performing 3-way merge")
        merge_result = self.baseline_manager.merge_file(
            baseline_content=baseline_content,
            local_content=local_content,
            remote_content=remote_content_str,
            page_id=page_id,
        )

        # Handle merge result
        if merge_result.has_conflicts:
            logger.info(
                f"Page {page_id}: Merge produced {merge_result.conflict_count} "
                f"conflict(s) - writing conflict markers"
            )
            if not dryrun:
                # Write conflict markers to local file
                local_path_obj.write_text(
                    merge_result.merged_content,
                    encoding="utf-8"
                )
                logger.debug(f"Page {page_id}: Wrote conflict markers to {local_path}")

            conflict_info = ConflictInfo(
                page_id=page_id,
                title=page_title,
                local_path=local_path_obj,
                conflict_markers=merge_result.merged_content,
            )
            result.conflicts.append(conflict_info)
            result.failed_count += 1
        else:
            logger.info(f"Page {page_id}: Auto-merge successful")
            if not dryrun:
                # Write auto-merged content to local file
                local_path_obj.write_text(
                    merge_result.merged_content,
                    encoding="utf-8"
                )
                logger.debug(f"Page {page_id}: Wrote auto-merged content to {local_path}")

            result.auto_merged_count += 1

    def _write_conflict_markers(
        self,
        local_path: Path,
        remote_content: str,
        page_id: str,
        page_title: str,
        result: ConflictResolutionResult,
        dryrun: bool,
    ) -> None:
        """Write conflict markers when baseline is missing.

        Args:
            local_path: Local file path
            remote_content: Remote page content
            page_id: Confluence page ID
            page_title: Page title for display purposes
            result: ConflictResolutionResult to update in-place
            dryrun: If True, don't write files
        """
        try:
            local_content = local_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.error(f"Page {page_id}: Cannot read local file: {e}")
            local_content = f"<Error reading local file: {e}>"

        # Create manual conflict markers
        conflict_markers = (
            f"<<<<<<< LOCAL\n"
            f"{local_content}\n"
            f"=======\n"
            f"{remote_content}\n"
            f">>>>>>> REMOTE\n"
        )

        if not dryrun:
            local_path.write_text(conflict_markers, encoding="utf-8")
            logger.debug(f"Page {page_id}: Wrote conflict markers to {local_path}")

        conflict_info = ConflictInfo(
            page_id=page_id,
            title=page_title,
            local_path=local_path,
            conflict_markers=conflict_markers,
        )
        result.conflicts.append(conflict_info)
        result.failed_count += 1
