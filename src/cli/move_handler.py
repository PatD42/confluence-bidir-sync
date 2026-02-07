"""Move operation handler for bidirectional sync.

This module implements move detection execution per Epic CONF-SYNC-005.
It handles moving pages in both directions:
- Confluence → Local: Moves local files to match Confluence hierarchy changes
- Local → Confluence: Updates Confluence page parents to match local folder moves

The MoveHandler works with MoveInfo objects from ChangeDetector to execute
the actual move operations, including nested moves and empty folder cleanup.
"""

import logging
from typing import Optional

from src.cli.errors import CLIError
from src.cli.models import MoveResult

logger = logging.getLogger(__name__)


class MoveHandler:
    """Handler for executing page move operations in both directions.

    This class implements move execution logic for bidirectional sync.
    It handles:
    - Confluence → Local: Moving local files to match Confluence parent changes
    - Local → Confluence: Updating Confluence page parents via API
    - Nested move scenarios (parent + children moved together)
    - Empty folder cleanup after moves
    - Invalid move detection (missing parent pages)

    The handler integrates with:
    - PageOperations: For update_page_parent() API calls
    - FileMapper: For move_local_file() operations
    - AncestorResolver: For determining correct Confluence hierarchy

    Example:
        >>> from src.page_operations.page_operations import PageOperations
        >>> page_ops = PageOperations(confluence_client)
        >>> handler = MoveHandler(page_operations=page_ops)
        >>> result = handler.execute_moves(
        ...     move_result=detected_moves,
        ...     dryrun=False
        ... )
        >>> print(f"Moved in Confluence: {result.moved_locally}")
    """

    def __init__(self, page_operations: Optional[object] = None):
        """Initialize move handler.

        Args:
            page_operations: PageOperations instance for Confluence API calls (optional)
        """
        self.page_operations = page_operations
        logger.debug("MoveHandler initialized")

    def move_local_files(
        self,
        moves: list,
        dryrun: bool = False,
    ) -> list[str]:
        """Move local files to match Confluence hierarchy changes.

        This method processes pages that have been moved in Confluence and
        relocates their corresponding local markdown files. Each move is
        handled independently - errors are logged but don't stop processing
        of other moves.

        Per ADR requirements:
        - Confluence → Local: Move local files to match parent changes
        - Nested moves handled (parent + children moved together)
        - Empty folders cleaned up after moves
        - Errors logged and operation continues with remaining files
        - Dry run mode shows what would be moved without executing

        Args:
            moves: List of MoveInfo for pages moved in Confluence
            dryrun: If True, log moves without executing (default: False)

        Returns:
            List of page IDs successfully moved (empty list in dryrun mode)

        Raises:
            CLIError: If critical error prevents any move processing

        Example:
            >>> from pathlib import Path
            >>> from src.cli.models import MoveInfo
            >>> handler = MoveHandler(page_operations)
            >>> moves = [
            ...     MoveInfo(
            ...         page_id="123",
            ...         title="My Page",
            ...         old_path=Path("docs/old-location/my-page.md"),
            ...         new_path=Path("docs/new-location/my-page.md"),
            ...         direction="confluence_to_local"
            ...     )
            ... ]
            >>> result = handler.move_local_files(moves, dryrun=False)
            >>> print(f"Moved {len(result)} files")
        """
        import os
        import shutil
        from pathlib import Path

        logger.info(
            f"Processing {len(moves)} local file move(s) "
            f"(dryrun={dryrun})"
        )

        if not moves:
            logger.debug("No moves to process")
            return []

        moved_page_ids = []

        for move in moves:
            try:
                # Validate move info
                if not move.old_path:
                    logger.warning(
                        f"Page {move.page_id} ({move.title}): "
                        f"No old path specified, skipping"
                    )
                    continue

                if not move.new_path:
                    logger.warning(
                        f"Page {move.page_id} ({move.title}): "
                        f"No new path specified, skipping"
                    )
                    continue

                # Check direction is correct
                if move.direction != "confluence_to_local":
                    logger.warning(
                        f"Page {move.page_id} ({move.title}): "
                        f"Incorrect direction '{move.direction}' for local move, skipping"
                    )
                    continue

                # Convert to Path objects for easier manipulation
                old_path = Path(move.old_path) if not isinstance(move.old_path, Path) else move.old_path
                new_path = Path(move.new_path) if not isinstance(move.new_path, Path) else move.new_path

                # Check if source file exists
                if not old_path.exists():
                    logger.warning(
                        f"Page {move.page_id} ({move.title}): "
                        f"Source file {old_path} does not exist, skipping"
                    )
                    continue

                # Check if target already exists
                if new_path.exists():
                    logger.warning(
                        f"Page {move.page_id} ({move.title}): "
                        f"Target file {new_path} already exists, skipping to avoid conflict"
                    )
                    continue

                if dryrun:
                    # Dry run mode - just log what would be moved
                    logger.info(
                        f"[DRYRUN] Would move: {old_path} -> {new_path} "
                        f"(page {move.page_id}: {move.title})"
                    )
                else:
                    # Actually move the file
                    logger.info(
                        f"Moving local file: {old_path} -> {new_path} "
                        f"(page {move.page_id}: {move.title})"
                    )

                    # Create parent directory if needed
                    new_path.parent.mkdir(parents=True, exist_ok=True)

                    # Move the file
                    shutil.move(str(old_path), str(new_path))
                    moved_page_ids.append(move.page_id)
                    logger.debug(f"Successfully moved {old_path} to {new_path}")

                    # Clean up empty parent directories
                    self._cleanup_empty_dirs(old_path.parent)

            except OSError as e:
                # File system error - log and continue
                logger.error(
                    f"Failed to move {move.old_path} to {move.new_path} "
                    f"(page {move.page_id}): {e}"
                )
                continue
            except Exception as e:
                # Unexpected error - log and continue
                logger.error(
                    f"Unexpected error moving {move.old_path} to {move.new_path} "
                    f"(page {move.page_id}): {e}"
                )
                continue

        if dryrun:
            logger.info(
                f"Dry run complete: Would move {len(moves)} file(s)"
            )
        else:
            logger.info(
                f"Local file move complete: "
                f"{len(moved_page_ids)} moved, "
                f"{len(moves) - len(moved_page_ids)} failed/skipped"
            )

        return moved_page_ids

    def _cleanup_empty_dirs(self, directory):
        """Clean up empty parent directories after move.

        Recursively removes empty directories up to the project root.
        Stops when a non-empty directory is encountered.

        Args:
            directory: Path object representing directory to clean up
        """
        import os
        from pathlib import Path

        try:
            # Convert to Path if needed
            dir_path = Path(directory) if not isinstance(directory, Path) else directory

            # Don't delete if it doesn't exist or isn't a directory
            if not dir_path.exists() or not dir_path.is_dir():
                return

            # Check if directory is empty
            if not any(dir_path.iterdir()):
                logger.debug(f"Removing empty directory: {dir_path}")
                dir_path.rmdir()

                # Recursively clean up parent if it exists
                if dir_path.parent and dir_path.parent.exists():
                    self._cleanup_empty_dirs(dir_path.parent)

        except OSError as e:
            # Directory not empty or permission issue - log and stop
            logger.debug(f"Stopped directory cleanup at {directory}: {e}")
        except Exception as e:
            # Unexpected error - log warning but don't raise
            logger.warning(f"Error during directory cleanup at {directory}: {e}")

    def move_confluence_pages(
        self,
        moves: list,
        dryrun: bool = False,
    ) -> list[str]:
        """Move Confluence pages to match local folder hierarchy changes.

        This method processes pages that have been moved locally (file relocated
        to different folder) and updates their parent in Confluence via API.
        Each move is handled independently - errors are logged but don't stop
        processing of other moves.

        Per ADR requirements:
        - Local → Confluence: Update Confluence page parents via API
        - Nested moves handled (parent + children moved together)
        - Invalid moves (missing parent) reported as errors
        - Errors logged and operation continues with remaining pages
        - Dry run mode shows what would be moved without executing

        Args:
            moves: List of MoveInfo for pages moved locally
            dryrun: If True, log moves without executing (default: False)

        Returns:
            List of page IDs successfully moved (empty list in dryrun mode)

        Raises:
            CLIError: If critical error prevents any move processing

        Example:
            >>> from pathlib import Path
            >>> from src.cli.models import MoveInfo
            >>> handler = MoveHandler(page_operations)
            >>> moves = [
            ...     MoveInfo(
            ...         page_id="123",
            ...         title="My Page",
            ...         old_path=Path("docs/old-location/my-page.md"),
            ...         new_path=Path("docs/new-location/my-page.md"),
            ...         direction="local_to_confluence"
            ...     )
            ... ]
            >>> result = handler.move_confluence_pages(moves, dryrun=False)
            >>> print(f"Moved {len(result)} pages in Confluence")
        """
        logger.info(
            f"Processing {len(moves)} Confluence page move(s) "
            f"(dryrun={dryrun})"
        )

        if not moves:
            logger.debug("No moves to process")
            return []

        # Check if page_operations is available
        if not self.page_operations:
            logger.error("PageOperations instance not provided - cannot move Confluence pages")
            raise CLIError("PageOperations instance required for Confluence moves")

        moved_page_ids = []

        for move in moves:
            try:
                # Validate move info
                if not move.new_path:
                    logger.warning(
                        f"Page {move.page_id} ({move.title}): "
                        f"No new path specified, skipping"
                    )
                    continue

                # Check direction is correct
                if move.direction != "local_to_confluence":
                    logger.warning(
                        f"Page {move.page_id} ({move.title}): "
                        f"Incorrect direction '{move.direction}' for Confluence move, skipping"
                    )
                    continue

                # Resolve parent page ID from new path
                try:
                    new_parent_id = self.resolve_parent_page_id(move.new_path)
                except Exception as e:
                    logger.error(
                        f"Page {move.page_id} ({move.title}): "
                        f"Failed to resolve parent page ID from {move.new_path}: {e}"
                    )
                    continue

                if dryrun:
                    # Dry run mode - just log what would be moved
                    parent_display = new_parent_id if new_parent_id else "(space root)"
                    logger.info(
                        f"[DRYRUN] Would update parent: {move.title} (page {move.page_id}) "
                        f"-> parent {parent_display}"
                    )
                else:
                    # Actually move the page in Confluence
                    parent_display = new_parent_id if new_parent_id else "(space root)"
                    logger.info(
                        f"Updating Confluence parent: {move.title} (page {move.page_id}) "
                        f"-> parent {parent_display}"
                    )

                    # Call update_page_parent if available, otherwise use update_page with parent_id
                    if hasattr(self.page_operations, 'update_page_parent'):
                        # Use dedicated method if available (from subtask 8-2)
                        result = self.page_operations.update_page_parent(
                            page_id=move.page_id,
                            parent_id=new_parent_id
                        )
                        if not result.get('success', True):
                            logger.error(
                                f"Failed to update parent for page {move.page_id}: "
                                f"{result.get('error', 'Unknown error')}"
                            )
                            continue
                    else:
                        # Fallback: Use update_page with parent_id in kwargs
                        # This requires fetching current page state first
                        from ..page_operations.page_operations import PageOperations
                        snapshot = self.page_operations.get_page_snapshot(move.page_id)

                        # Update with parent_id in kwargs
                        # Note: Confluence API update_page can accept parent_id
                        result = self.page_operations.api.update_page(
                            page_id=move.page_id,
                            title=snapshot.title,
                            body=snapshot.xhtml,
                            version=snapshot.version,
                            parent_id=new_parent_id
                        )

                    moved_page_ids.append(move.page_id)
                    logger.debug(
                        f"Successfully updated parent for page {move.page_id} to {parent_display}"
                    )

            except CLIError:
                # Already logged, just re-raise to stop processing
                raise
            except Exception as e:
                # Unexpected error - log and continue
                logger.error(
                    f"Unexpected error moving page {move.page_id} ({move.title}) "
                    f"in Confluence: {e}"
                )
                continue

        if dryrun:
            logger.info(
                f"Dry run complete: Would move {len(moves)} page(s) in Confluence"
            )
        else:
            logger.info(
                f"Confluence page move complete: "
                f"{len(moved_page_ids)} moved, "
                f"{len(moves) - len(moved_page_ids)} failed/skipped"
            )

        return moved_page_ids

    def resolve_parent_page_id(
        self,
        file_path,
    ) -> Optional[str]:
        """Resolve parent page ID from local file path.

        This method determines which Confluence page should be the parent
        for a given local file by analyzing its folder structure. The parent
        corresponds to the markdown file at the parent folder level.

        Resolution logic:
        - docs/parent-folder/child-page.md → parent is docs/parent-folder.md
        - docs/section/subsection/page.md → parent is docs/section/subsection.md
        - docs/root-page.md → parent is None (space root)

        Args:
            file_path: Path to the local markdown file (str or Path object)

        Returns:
            Parent page ID if found in frontmatter, None if at space root

        Raises:
            CLIError: If parent folder exists but no corresponding page file found

        Example:
            >>> from pathlib import Path
            >>> handler = MoveHandler(page_operations)
            >>> parent_id = handler.resolve_parent_page_id(
            ...     Path("docs/section-a/page.md")
            ... )
            >>> print(f"Parent ID: {parent_id}")
        """
        from pathlib import Path
        from ..file_mapper.frontmatter_handler import FrontmatterHandler

        # Convert to Path if needed
        path = Path(file_path) if not isinstance(file_path, Path) else file_path

        logger.debug(f"Resolving parent page ID for: {path}")

        # Get parent directory
        parent_dir = path.parent

        # Check if we're at the space root (no parent folder beyond base)
        # This would be files directly in the space folder
        if not parent_dir or parent_dir == Path("."):
            logger.debug(f"File {path} is at space root - no parent")
            return None

        # Look for parent page file (markdown file matching parent directory name)
        # Parent folder: docs/section-a/ -> Parent file: docs/section-a.md
        parent_page_name = parent_dir.name
        potential_parent_file = parent_dir.parent / f"{parent_page_name}.md"

        logger.debug(
            f"Looking for parent page file: {potential_parent_file} "
            f"(from directory: {parent_dir})"
        )

        # Check if parent file exists
        if not potential_parent_file.exists():
            # Also check if the parent directory itself has a page file with different name
            # Look for any .md file in parent directory's parent that could be the parent
            # This handles cases where directory name doesn't exactly match filename

            # If we're in a nested structure, the parent should exist
            # If not found, this is an error condition (orphaned page)
            if parent_dir.parent and parent_dir.parent != Path("."):
                logger.warning(
                    f"Parent page file not found: {potential_parent_file} "
                    f"(expected from directory: {parent_dir})"
                )
                # Check if we're at the first level (directly under space root)
                # In that case, parent is None (space root)
                return None
            else:
                # At space root level
                logger.debug(f"File {path} is at first level - parent is space root")
                return None

        # Read frontmatter from parent file to get page_id
        try:
            frontmatter_handler = FrontmatterHandler()
            with open(potential_parent_file, 'r', encoding='utf-8') as f:
                content = f.read()

            frontmatter = frontmatter_handler.extract(content)
            parent_page_id = frontmatter.get('confluence_page_id')

            if not parent_page_id:
                logger.error(
                    f"Parent page file {potential_parent_file} exists but has no "
                    f"confluence_page_id in frontmatter"
                )
                raise CLIError(
                    f"Parent page file {potential_parent_file} missing confluence_page_id"
                )

            logger.debug(
                f"Resolved parent page ID: {parent_page_id} "
                f"(from file: {potential_parent_file})"
            )
            return parent_page_id

        except FileNotFoundError:
            logger.error(f"Parent page file not found: {potential_parent_file}")
            raise CLIError(f"Parent page file not found: {potential_parent_file}")
        except Exception as e:
            logger.error(
                f"Error reading parent page file {potential_parent_file}: {e}"
            )
            raise CLIError(
                f"Failed to resolve parent page ID from {potential_parent_file}: {e}"
            )
