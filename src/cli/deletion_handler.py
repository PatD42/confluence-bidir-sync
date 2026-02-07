"""Deletion handler for bidirectional sync.

This module implements deletion operations for bidirectional sync per Epic CONF-SYNC-005.
It handles page deletions in both directions:
- Confluence → Local: Delete local files for pages deleted in Confluence
- Local → Confluence: Move Confluence pages to trash for locally deleted files

Deletions are executed without confirmation prompts (use --dryrun to preview).
Confluence pages are soft-deleted (moved to trash, recoverable).
"""

import logging
from typing import Optional

from src.cli.errors import CLIError
from src.cli.models import DeletionInfo, DeletionResult

logger = logging.getLogger(__name__)


class DeletionHandler:
    """Handles deletion operations for bidirectional sync.

    This class executes deletion operations detected by ChangeDetector.
    It processes deletions in both directions:
    - delete_local_files(): Removes local files for Confluence-deleted pages
    - delete_confluence_pages(): Moves Confluence pages to trash for locally-deleted files

    Per ADR requirements:
    - No confirmation prompts (use --dryrun flag for preview)
    - Confluence pages soft-deleted (trash, recoverable)
    - Each page tracked independently (no automatic child deletion)
    - Errors logged and operation continues with remaining pages

    Example:
        >>> handler = DeletionHandler(page_operations, file_mapper)
        >>> result = handler.delete_local_files(deletions, dryrun=False)
        >>> print(f"Deleted {len(result)} local files")
    """

    def __init__(
        self,
        page_operations: Optional[object] = None,
        file_mapper: Optional[object] = None,
    ):
        """Initialize deletion handler.

        Args:
            page_operations: PageOperations instance for Confluence API calls (optional)
            file_mapper: FileMapper instance for local file operations (optional)
        """
        self.page_operations = page_operations
        self.file_mapper = file_mapper
        logger.debug("DeletionHandler initialized")

    def delete_local_files(
        self,
        deletions: list[DeletionInfo],
        dryrun: bool = False,
    ) -> list[str]:
        """Delete local files for pages deleted in Confluence.

        This method processes pages that have been deleted in Confluence and
        removes their corresponding local markdown files. Each deletion is
        handled independently - errors are logged but don't stop processing
        of other deletions.

        Per ADR requirements:
        - No confirmation prompts (use dryrun parameter for preview)
        - Each page tracked independently (no automatic child deletion)
        - Errors logged and operation continues with remaining files
        - Dry run mode shows what would be deleted without executing

        Args:
            deletions: List of DeletionInfo for pages deleted in Confluence
            dryrun: If True, log deletions without executing (default: False)

        Returns:
            List of page IDs successfully deleted (empty list in dryrun mode)

        Raises:
            CLIError: If critical error prevents any deletion processing

        Example:
            >>> handler = DeletionHandler(page_operations, file_mapper)
            >>> deletions = [
            ...     DeletionInfo(
            ...         page_id="123",
            ...         title="My Page",
            ...         local_path=Path("docs/my-page.md"),
            ...         direction="confluence_to_local"
            ...     )
            ... ]
            >>> result = handler.delete_local_files(deletions, dryrun=False)
            >>> print(f"Deleted {len(result)} files")
        """
        import os

        logger.info(
            f"Processing {len(deletions)} local file deletion(s) "
            f"(dryrun={dryrun})"
        )

        if not deletions:
            logger.debug("No deletions to process")
            return []

        deleted_page_ids = []

        for deletion in deletions:
            try:
                # Validate deletion info
                if not deletion.local_path:
                    logger.warning(
                        f"Page {deletion.page_id} ({deletion.title}): "
                        f"No local path specified, skipping"
                    )
                    continue

                # Check if file exists
                if not os.path.exists(deletion.local_path):
                    logger.warning(
                        f"Page {deletion.page_id} ({deletion.title}): "
                        f"File {deletion.local_path} does not exist, skipping"
                    )
                    continue

                # Check direction is correct
                if deletion.direction != "confluence_to_local":
                    logger.warning(
                        f"Page {deletion.page_id} ({deletion.title}): "
                        f"Incorrect direction '{deletion.direction}' for local deletion, skipping"
                    )
                    continue

                if dryrun:
                    # Dry run mode - just log what would be deleted
                    logger.info(
                        f"[DRYRUN] Would delete: {deletion.local_path} "
                        f"(page {deletion.page_id}: {deletion.title})"
                    )
                else:
                    # Actually delete the file
                    logger.info(
                        f"Deleting local file: {deletion.local_path} "
                        f"(page {deletion.page_id}: {deletion.title})"
                    )
                    os.unlink(deletion.local_path)
                    deleted_page_ids.append(deletion.page_id)
                    logger.debug(f"Successfully deleted {deletion.local_path}")

            except OSError as e:
                # File system error - log and continue
                logger.error(
                    f"Failed to delete {deletion.local_path} "
                    f"(page {deletion.page_id}): {e}"
                )
                continue
            except Exception as e:
                # Unexpected error - log and continue
                logger.error(
                    f"Unexpected error deleting {deletion.local_path} "
                    f"(page {deletion.page_id}): {e}"
                )
                continue

        if dryrun:
            logger.info(
                f"Dry run complete: Would delete {len(deletions)} file(s)"
            )
        else:
            logger.info(
                f"Local file deletion complete: "
                f"{len(deleted_page_ids)} deleted, "
                f"{len(deletions) - len(deleted_page_ids)} failed/skipped"
            )

        return deleted_page_ids

    def delete_confluence_pages(
        self,
        deletions: list[DeletionInfo],
        dryrun: bool = False,
    ) -> list[str]:
        """Delete Confluence pages for locally deleted files.

        This method processes local files that have been deleted and
        moves their corresponding Confluence pages to trash. Each deletion is
        handled independently - errors are logged but don't stop processing
        of other deletions.

        Per ADR requirements:
        - No confirmation prompts (use dryrun parameter for preview)
        - Confluence pages soft-deleted (moved to trash, recoverable)
        - Each page tracked independently (no automatic child deletion)
        - Errors logged and operation continues with remaining pages
        - Dry run mode shows what would be deleted without executing

        Args:
            deletions: List of DeletionInfo for locally deleted files
            dryrun: If True, log deletions without executing (default: False)

        Returns:
            List of page IDs successfully deleted (empty list in dryrun mode)

        Raises:
            CLIError: If critical error prevents any deletion processing

        Example:
            >>> handler = DeletionHandler(page_operations, file_mapper)
            >>> deletions = [
            ...     DeletionInfo(
            ...         page_id="123",
            ...         title="My Page",
            ...         local_path=Path("docs/my-page.md"),
            ...         direction="local_to_confluence"
            ...     )
            ... ]
            >>> result = handler.delete_confluence_pages(deletions, dryrun=False)
            >>> print(f"Deleted {len(result)} pages")
        """
        logger.info(
            f"Processing {len(deletions)} Confluence page deletion(s) "
            f"(dryrun={dryrun})"
        )

        if not deletions:
            logger.debug("No deletions to process")
            return []

        # Validate page_operations is available
        if not self.page_operations and not dryrun:
            logger.error("PageOperations instance not provided")
            raise CLIError("Cannot delete Confluence pages: PageOperations not initialized")

        deleted_page_ids = []

        for deletion in deletions:
            try:
                # Validate deletion info
                if not deletion.page_id:
                    logger.warning(
                        f"Deletion ({deletion.title}): "
                        f"No page ID specified, skipping"
                    )
                    continue

                # Check direction is correct
                if deletion.direction != "local_to_confluence":
                    logger.warning(
                        f"Page {deletion.page_id} ({deletion.title}): "
                        f"Incorrect direction '{deletion.direction}' for Confluence deletion, skipping"
                    )
                    continue

                if dryrun:
                    # Dry run mode - just log what would be deleted
                    logger.info(
                        f"[DRYRUN] Would delete Confluence page: {deletion.page_id} "
                        f"({deletion.title})"
                    )
                else:
                    # Actually delete the page (move to trash)
                    logger.info(
                        f"Deleting Confluence page: {deletion.page_id} "
                        f"({deletion.title})"
                    )
                    self.page_operations.delete_page(deletion.page_id)
                    deleted_page_ids.append(deletion.page_id)
                    logger.debug(f"Successfully deleted page {deletion.page_id}")

            except Exception as e:
                # Any error - log and continue
                logger.error(
                    f"Failed to delete Confluence page {deletion.page_id} "
                    f"({deletion.title}): {e}"
                )
                continue

        if dryrun:
            logger.info(
                f"Dry run complete: Would delete {len(deletions)} page(s)"
            )
        else:
            logger.info(
                f"Confluence page deletion complete: "
                f"{len(deleted_page_ids)} deleted, "
                f"{len(deletions) - len(deleted_page_ids)} failed/skipped"
            )

        return deleted_page_ids
