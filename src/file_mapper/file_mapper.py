"""Main orchestration class for file mapping operations.

This module provides the FileMapper class which orchestrates all file mapping
operations including syncing between Confluence and local markdown files,
managing hierarchies, and ensuring atomic file operations (ADR-011).
"""

import hashlib
import logging
import os
import re
import shutil
from datetime import datetime, UTC
from typing import Dict, List, Optional, Set, Tuple

from ..confluence_client.auth import Authenticator
from ..confluence_client.api_wrapper import APIWrapper
from ..page_operations.page_operations import PageOperations
from .hierarchy_builder import HierarchyBuilder
from .config_loader import ConfigLoader
from .filesafe_converter import FilesafeConverter
from .frontmatter_handler import FrontmatterHandler
from .models import PageNode, LocalPage, SpaceConfig, SyncConfig
from .errors import FilesystemError, ConfigError


logger = logging.getLogger(__name__)

# Pattern to detect unresolved merge conflict markers
CONFLICT_MARKER_PATTERN = re.compile(
    r'^<{7}\s|^={7}\s*$|^>{7}\s',
    re.MULTILINE
)

# Maximum file size to prevent memory exhaustion (M1)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB in bytes

# Maximum recursion depth to prevent stack overflow (M2)
MAX_RECURSION_DEPTH = 50


class FileMapper:
    """Main orchestration class for bidirectional Confluence-filesystem mapping.

    This class coordinates all file mapping operations, providing high-level
    methods for syncing between Confluence page hierarchies and local markdown
    files. It implements atomic file operations (ADR-011) and handles initial
    sync direction detection (ADR-014).

    The FileMapper uses:
    - HierarchyBuilder: For discovering page hierarchies via CQL
    - FilesafeConverter: For title-to-filename conversion
    - FrontmatterHandler: For YAML frontmatter operations
    - ConfigLoader: For configuration management
    - APIWrapper: For Confluence API access

    Example:
        >>> auth = Authenticator()
        >>> mapper = FileMapper(auth)
        >>> config = ConfigLoader.load('.confluence-sync/config.yaml')
        >>> mapper.sync_spaces(config)
    """

    def __init__(self, authenticator: Optional[Authenticator] = None):
        """Initialize the file mapper with authentication.

        Args:
            authenticator: Optional Authenticator instance. If not provided,
                          a new one will be created with default credentials.

        Raises:
            InvalidCredentialsError: If credentials are missing or invalid
        """
        if authenticator is None:
            authenticator = Authenticator()

        self._auth = authenticator
        self._api = APIWrapper(authenticator)
        self._hierarchy_builder = HierarchyBuilder(authenticator)
        self._base_path = ""  # Set during sync to calculate relative paths
        self._confluence_base_url: Optional[str] = None  # Cached base URL

    def _get_confluence_base_url(self) -> str:
        """Get the Confluence base URL from credentials.

        Caches the result for efficiency.

        Returns:
            Confluence base URL (e.g., https://domain.atlassian.net/wiki)
        """
        if self._confluence_base_url is None:
            creds = self._auth.get_credentials()
            self._confluence_base_url = creds.url
        return self._confluence_base_url

    def _sync_print(self, message: str) -> None:
        """Print a sync status message to console.

        Always prints to stdout regardless of log level.
        Used for user-facing progress messages.

        Args:
            message: Message to print
        """
        print(message)

    def _log_page_action(self, action: str, file_path: str) -> None:
        """Print a page modification action with action indicator and file path.

        Always prints regardless of log level.

        Args:
            action: Action type indicator:
                '←' = Confluence updated (push from local)
                '→' = Local updated (pull from Confluence)
                '↔' = Both sides merged (bidirectional)
                '=' = Unchanged (no action needed)
            file_path: Absolute or relative file path
        """
        # Calculate relative path from base
        if self._base_path and os.path.isabs(file_path):
            rel_path = os.path.relpath(file_path, self._base_path)
        else:
            rel_path = file_path

        # Show the full relative path (not just filename)
        self._sync_print(f"  {action} {rel_path}")

    def _has_conflict_markers(self, content: str) -> bool:
        """Check if content contains unresolved merge conflict markers.

        Detects the standard Git merge conflict markers:
        - <<<<<<< (conflict start)
        - ======= (conflict divider)
        - >>>>>>> (conflict end)

        Args:
            content: File content to check

        Returns:
            True if conflict markers found, False otherwise
        """
        return bool(CONFLICT_MARKER_PATTERN.search(content))

    def _log_conflict_marker_error(self, file_path: str) -> None:
        """Log error for file with unresolved conflict markers.

        Args:
            file_path: Path to the file with conflicts
        """
        rel_path = file_path
        if self._base_path and os.path.isabs(file_path):
            rel_path = os.path.relpath(file_path, self._base_path)
        logger.error(f"CONFLICT MARKERS: {rel_path} has unresolved merge conflicts - skipping")
        self._sync_print(f"  ⚠ {rel_path} (CONFLICT MARKERS - skipped)")

    def _validate_path_safety(self, file_path: str, base_directory: str) -> None:
        """Validate that a file path is safe and within the base directory.

        Prevents path traversal attacks by resolving symlinks and ensuring
        the resolved path is within the base directory.

        Args:
            file_path: Path to validate
            base_directory: Base directory that must contain the path

        Raises:
            FilesystemError: If path is outside base directory or unsafe
        """
        # Resolve the base directory to handle symlinks
        real_base = os.path.realpath(base_directory)

        # Resolve the file path to handle symlinks and relative paths
        real_path = os.path.realpath(file_path)

        # Check if the resolved path is within the base directory
        if not real_path.startswith(real_base + os.sep) and real_path != real_base:
            raise FilesystemError(
                file_path,
                'validate',
                f'Path traversal detected: {file_path} is outside base directory {base_directory}'
            )

    def _validate_file_size(self, file_path: str, max_size: int = MAX_FILE_SIZE) -> None:
        """Validate that a file size is within acceptable limits.

        Prevents memory exhaustion by checking file size before reading
        into memory (M1: Memory leak on large files).

        Args:
            file_path: Path to the file to check
            max_size: Maximum allowed file size in bytes (default: MAX_FILE_SIZE)

        Raises:
            FilesystemError: If file size exceeds maximum allowed size
        """
        try:
            file_size = os.path.getsize(file_path)
            if file_size > max_size:
                # Format size in human-readable units
                size_mb = file_size / (1024 * 1024)
                max_mb = max_size / (1024 * 1024)
                raise FilesystemError(
                    file_path,
                    'read',
                    f'File size ({size_mb:.2f} MB) exceeds maximum allowed size ({max_mb:.0f} MB). '
                    f'Large files can cause memory exhaustion.'
                )
        except OSError as e:
            raise FilesystemError(
                file_path,
                'stat',
                f'Failed to check file size: {e}'
            )

    def sync_spaces(self, config: SyncConfig) -> "SyncResult":
        """Sync all configured spaces according to sync configuration.

        This is the main entry point for syncing operations. It processes
        each space in the configuration and syncs according to the sync
        direction and force flags.

        Args:
            config: SyncConfig with spaces to sync and sync options

        Raises:
            PageNotFoundError: If parent page doesn't exist
            PageLimitExceededError: If page limit is exceeded
            FilesystemError: If file operations fail
            ConfigError: If configuration is invalid
            APIAccessError: If API operations fail
        """
        from .models import SyncResult

        logger.info(f"Starting sync for {len(config.spaces)} space(s)")

        # Aggregate results from all spaces
        combined_result = SyncResult()

        for space_config in config.spaces:
            logger.info(
                f"Syncing space {space_config.space_key} "
                f"(parent page: {space_config.parent_page_id})"
            )
            space_result = self._sync_space(space_config, config)
            if space_result:
                combined_result.pushed_count += space_result.pushed_count
                combined_result.pulled_count += space_result.pulled_count
                combined_result.conflict_page_ids.extend(space_result.conflict_page_ids)
                combined_result.conflict_local_paths.update(space_result.conflict_local_paths)
                combined_result.conflict_remote_content.update(space_result.conflict_remote_content)
                combined_result.conflict_titles.update(space_result.conflict_titles)

        logger.info("All spaces synced successfully")
        return combined_result

    def _sync_space(self, space_config: SpaceConfig, sync_config: SyncConfig) -> "SyncResult":
        """Sync a single space.

        Args:
            space_config: Configuration for the space to sync
            sync_config: Overall sync configuration with options

        Returns:
            SyncResult with push/pull counts and conflict information
        """
        from .models import SyncResult

        # Set base path for relative path logging
        self._base_path = str(space_config.local_path)

        # Build hierarchy from Confluence
        self._sync_print("Querying Confluence...")
        logger.debug(f"Building hierarchy for space {space_config.space_key}")
        hierarchy = self._hierarchy_builder.build_hierarchy(
            parent_page_id=space_config.parent_page_id,
            space_key=space_config.space_key,
            page_limit=sync_config.page_limit,
            exclude_page_ids=space_config.exclude_page_ids
        )

        # Read local files
        logger.debug(f"Reading local files from {space_config.local_path}")
        local_pages = self._read_local_files(space_config.local_path)

        # Determine sync direction
        sync_direction = self._detect_sync_direction(
            hierarchy=hierarchy,
            local_pages=local_pages,
            force_pull=sync_config.force_pull,
            force_push=sync_config.force_push
        )

        logger.debug(f"Sync direction: {sync_direction}")

        # Perform sync based on direction
        if sync_direction == 'pull':
            # Get all page IDs from hierarchy - pull everything
            all_page_ids = self._collect_page_ids_from_hierarchy(hierarchy)

            # Exclude parent page if configured (ADR: exclude_parent option)
            if space_config.exclude_parent:
                all_page_ids.discard(hierarchy.page_id)
                logger.debug(f"Excluding parent page {hierarchy.page_id} from sync (exclude_parent=True)")

            pulled_count = self._pull_from_confluence(
                hierarchy=hierarchy,
                space_config=space_config,
                sync_config=sync_config,
                page_ids_to_pull=all_page_ids
            )
            return SyncResult(pulled_count=pulled_count)
        elif sync_direction == 'push':
            actual_pushed = self._push_to_confluence(
                local_pages=local_pages,
                space_config=space_config,
                sync_config=sync_config
            )
            return SyncResult(pushed_count=actual_pushed)
        elif sync_direction == 'bidirectional':
            # For bidirectional sync, we need to merge changes
            logger.info("Bidirectional sync detected - comparing changes")
            return self._bidirectional_sync(
                hierarchy=hierarchy,
                local_pages=local_pages,
                space_config=space_config,
                sync_config=sync_config
            )

        return SyncResult()

    def _detect_sync_direction(
        self,
        hierarchy: PageNode,
        local_pages: Dict[str, LocalPage],
        force_pull: bool,
        force_push: bool
    ) -> str:
        """Detect which direction to sync (pull, push, or bidirectional).

        Implements ADR-014: Strict initial sync requirement.
        - If local is empty, sync direction is 'pull'
        - If remote is empty (only root page), sync direction is 'push'
        - If both have content and force_pull, sync direction is 'pull'
        - If both have content and force_push, sync direction is 'push'
        - Otherwise, sync direction is 'bidirectional'

        Args:
            hierarchy: PageNode tree from Confluence
            local_pages: Dictionary of local pages by file path
            force_pull: Whether to force pull even if both sides have content
            force_push: Whether to force push even if both sides have content

        Returns:
            Sync direction: 'pull', 'push', or 'bidirectional'

        Raises:
            ConfigError: If both sides have content and no force flag is set
        """
        # Check if Confluence has children (only root doesn't count as content)
        confluence_has_content = len(hierarchy.children) > 0

        # Check if local directory has markdown files
        local_has_content = len(local_pages) > 0

        # Determine sync direction
        if not local_has_content and not confluence_has_content:
            # Both empty - nothing to sync
            logger.warning("Both Confluence and local are empty - nothing to sync")
            return 'pull'
        elif not local_has_content:
            # Local is empty - pull from Confluence
            return 'pull'
        elif not confluence_has_content:
            # Confluence is empty - push to Confluence
            return 'push'
        else:
            # Both have content - check force flags
            if force_pull:
                return 'pull'
            elif force_push:
                return 'push'
            else:
                # No force flag - bidirectional sync
                return 'bidirectional'

    def _pull_from_confluence(
        self,
        hierarchy: PageNode,
        space_config: SpaceConfig,
        sync_config: SyncConfig,
        page_ids_to_pull: Set[str]
    ) -> int:
        """Pull specified pages from Confluence to local files.

        Converts the specified pages from the PageNode hierarchy into local
        markdown files with YAML frontmatter. Uses atomic file operations (ADR-011).

        This method always requires an explicit set of page IDs to pull.
        For full pulls, pass all page IDs from the hierarchy.
        For selective pulls, pass only the modified page IDs.

        Args:
            hierarchy: PageNode tree from Confluence
            space_config: Space configuration
            sync_config: Overall sync configuration
            page_ids_to_pull: Set of page IDs to pull (required)

        Returns:
            Number of files written
        """
        logger.debug(f"Pulling {len(page_ids_to_pull)} page(s) from Confluence")

        # Determine if this is a full pull (all pages) for orphan cleanup
        all_page_ids = self._collect_page_ids_from_hierarchy(hierarchy)
        is_full_pull = page_ids_to_pull == all_page_ids

        # Scan existing local files before pulling (for cleanup of renamed/deleted pages)
        # Only needed for full pull - partial pull shouldn't delete unchanged files
        existing_files = set()
        if is_full_pull and os.path.exists(space_config.local_path):
            for root, dirs, files in os.walk(space_config.local_path):
                for filename in files:
                    if filename.endswith('.md'):
                        file_path = os.path.join(root, filename)
                        existing_files.add(file_path)

        # Build list of files to write (only pages in page_ids_to_pull)
        files_to_write: List[Tuple[str, str]] = []
        self._build_file_list_from_hierarchy(
            node=hierarchy,
            parent_path=space_config.local_path,
            files_to_write=files_to_write,
            space_config=space_config,
            page_ids_filter=page_ids_to_pull
        )

        # Log each file being pulled (→ = local updated from Confluence)
        for file_path, _ in files_to_write:
            self._log_page_action("→", file_path)

        # Write files atomically
        self._write_files_atomic(
            files_to_write=files_to_write,
            temp_dir=sync_config.temp_dir
        )

        # Delete orphaned files (files that existed before but aren't in new hierarchy)
        # Only for full pull - partial pull doesn't delete files
        if is_full_pull:
            new_files = {file_path for file_path, _ in files_to_write}
            orphaned_files = existing_files - new_files

            if orphaned_files:
                logger.debug(f"Cleaning up {len(orphaned_files)} orphaned file(s)")
                for orphaned_file in orphaned_files:
                    try:
                        os.remove(orphaned_file)
                        logger.debug(f"Deleted orphaned file: {orphaned_file}")

                        # Clean up empty parent directories
                        parent_dir = os.path.dirname(orphaned_file)
                        while parent_dir and parent_dir != space_config.local_path:
                            try:
                                # Only remove if directory is empty
                                if not os.listdir(parent_dir):
                                    os.rmdir(parent_dir)
                                    logger.debug(f"Deleted empty directory: {parent_dir}")
                                    parent_dir = os.path.dirname(parent_dir)
                                else:
                                    break
                            except OSError:
                                # Directory not empty or other error - stop cleanup
                                break
                    except Exception as e:
                        logger.warning(f"Failed to delete orphaned file {orphaned_file}: {e}")

        logger.debug(f"Successfully pulled {len(files_to_write)} file(s)")
        return len(files_to_write)

    def _build_file_list_from_hierarchy(
        self,
        node: PageNode,
        parent_path: str,
        files_to_write: List[Tuple[str, str]],
        space_config: SpaceConfig,
        page_ids_filter: Set[str],
        depth: int = 0
    ) -> None:
        """Recursively build list of files to write from PageNode hierarchy.

        Args:
            node: Current PageNode in the tree
            parent_path: Parent directory path
            files_to_write: List to append (file_path, content) tuples to
            space_config: Space configuration
            page_ids_filter: Set of page IDs to include (required). Only pages
                             with IDs in this set are included in the output.
            depth: Current recursion depth (default: 0, increments with each level)

        Raises:
            FilesystemError: If recursion depth exceeds MAX_RECURSION_DEPTH
        """
        # Check recursion depth to prevent stack overflow (M2)
        if depth > MAX_RECURSION_DEPTH:
            raise FilesystemError(
                parent_path,
                'hierarchy',
                f'Page hierarchy exceeds maximum depth of {MAX_RECURSION_DEPTH}. '
                f'This may indicate a circular reference or excessively deep nesting.'
            )
        # Convert title to filename
        filename = FilesafeConverter.title_to_filename(node.title)
        file_path = os.path.join(parent_path, filename)

        # Only include this page if page_id is in the filter
        include_this_page = node.page_id in page_ids_filter

        if include_this_page:
            # Build content with H1 heading as title
            # Confluence stores title separately, so we need to prepend it as H1
            markdown_content = node.markdown_content or ""

            # Check if content already has an H1 heading
            if markdown_content.strip().startswith("# "):
                content = markdown_content
            else:
                # Prepend title as H1 heading
                content = f"# {node.title}\n\n{markdown_content}".strip() + "\n"

            # Create LocalPage with confluence_url info for frontmatter
            local_page = LocalPage(
                file_path=file_path,
                page_id=node.page_id,
                content=content,
                space_key=node.space_key or space_config.space_key,
                confluence_base_url=self._get_confluence_base_url()
            )

            # Generate markdown with frontmatter
            content = FrontmatterHandler.generate(local_page)
            files_to_write.append((file_path, content))

        # Process children (always recurse to find matching pages in subtree)
        if node.children:
            # Determine child directory:
            # - If this page is included, children go in a subdirectory named after this page
            # - If this page is excluded (e.g., exclude_parent), children stay in current directory
            if include_this_page:
                # Create subdirectory for children
                # Remove .md extension from filename for directory name
                dir_name = filename[:-3] if filename.endswith('.md') else filename
                child_dir = os.path.join(parent_path, dir_name)
            else:
                # Page is excluded - children stay in the same directory
                child_dir = parent_path

            for child in node.children:
                self._build_file_list_from_hierarchy(
                    node=child,
                    parent_path=child_dir,
                    files_to_write=files_to_write,
                    space_config=space_config,
                    page_ids_filter=page_ids_filter,
                    depth=depth + 1
                )

    def _push_to_confluence(
        self,
        local_pages: Dict[str, LocalPage],
        space_config: SpaceConfig,
        sync_config: SyncConfig
    ) -> int:
        """Push local files to Confluence.

        Creates or updates pages in Confluence from local markdown files.
        For pages without page_id (new pages), creates them in Confluence
        and updates the local frontmatter with the new page_id.

        Args:
            local_pages: Dictionary of local pages by file path
            space_config: Space configuration
            sync_config: Overall sync configuration

        Returns:
            Number of pages actually pushed (created or updated) in Confluence.

        Raises:
            PageAlreadyExistsError: If page with same title already exists
            APIAccessError: If API operations fail
            FilesystemError: If file operations fail
        """
        logger.debug(f"Pushing {len(local_pages)} local file(s) to Confluence")

        if not local_pages:
            logger.debug("No local pages to push")
            return 0

        # Create PageOperations for creating/updating pages
        page_ops = PageOperations()

        # Build hierarchy from local files to determine parent-child relationships
        # and ensure we create parents before children
        hierarchy = self._build_local_hierarchy(local_pages, space_config)

        # Track created/updated pages for frontmatter updates
        files_to_update: List[Tuple[str, str]] = []

        # Create/update pages in hierarchical order (parents before children)
        self._push_hierarchy_to_confluence(
            hierarchy=hierarchy,
            page_ops=page_ops,
            space_config=space_config,
            sync_config=sync_config,
            files_to_update=files_to_update,
            parent_page_id=space_config.parent_page_id
        )

        # Update local files with new page_ids atomically
        actual_pushed = len(files_to_update)
        if files_to_update:
            logger.debug(f"Updating {len(files_to_update)} local file(s) with page IDs")
            self._write_files_atomic(
                files_to_write=files_to_update,
                temp_dir=sync_config.temp_dir
            )

        logger.debug(f"Successfully pushed {actual_pushed} page(s) to Confluence")
        return actual_pushed

    def _build_local_hierarchy(
        self,
        local_pages: Dict[str, LocalPage],
        space_config: SpaceConfig
    ) -> Dict[str, List[str]]:
        """Build hierarchy map from local file structure.

        Analyzes the directory structure to determine parent-child relationships.
        Uses the file path structure where subdirectories represent child pages.

        When files exist in subdirectories without a corresponding parent .md file
        (e.g., docs/Core-Messaging/*.md but no docs/Core-Messaging.md), intermediate
        directory entries are created so the hierarchy is reachable from __root__.

        Args:
            local_pages: Dictionary of local pages by file path
            space_config: Space configuration

        Returns:
            Dictionary mapping parent paths to list of child paths.
            Intermediate directories without .md files get special entries
            prefixed with '__dir__:' in their parent's child list.
        """
        hierarchy: Dict[str, List[str]] = {}
        local_path_base = space_config.local_path

        for file_path in sorted(local_pages.keys()):
            # Get relative path from local_path base
            rel_path = os.path.relpath(file_path, local_path_base)

            # Determine parent directory
            parent_dir = os.path.dirname(rel_path)

            # If parent_dir is empty string, it's a top-level file
            if not parent_dir or parent_dir == '.':
                parent_key = '__root__'
            else:
                parent_key = parent_dir

            # Add to hierarchy
            if parent_key not in hierarchy:
                hierarchy[parent_key] = []
            hierarchy[parent_key].append(file_path)

        # Ensure all intermediate directories are reachable from __root__.
        # When files exist in subdirectories without a corresponding parent .md
        # file (e.g., docs/Core-Messaging/*.md but no docs/Core-Messaging.md),
        # create the missing .md file as a placeholder so the hierarchy is
        # properly represented both locally and in Confluence.
        all_dir_keys = sorted(set(hierarchy.keys()) - {'__root__'})
        for dir_key in all_dir_keys:
            # Walk up the path, creating placeholder .md files for any
            # directory level that doesn't have a corresponding file
            parts = dir_key.split(os.sep)
            for i in range(len(parts)):
                sub_dir = os.sep.join(parts[:i + 1])
                if i == 0:
                    parent_key = '__root__'
                else:
                    parent_key = os.sep.join(parts[:i])

                # Check if any file in parent's list would create this child dir
                already_covered = False
                for entry in hierarchy.get(parent_key, []):
                    entry_rel = os.path.relpath(entry, local_path_base)
                    entry_filename = os.path.basename(entry_rel)
                    entry_dir_name = entry_filename[:-3] if entry_filename.endswith('.md') else entry_filename
                    entry_parent = os.path.dirname(entry_rel)
                    if entry_parent and entry_parent != '.':
                        expected_child_dir = os.path.join(entry_parent, entry_dir_name)
                    else:
                        expected_child_dir = entry_dir_name
                    if expected_child_dir == sub_dir:
                        already_covered = True
                        break

                if not already_covered:
                    # Create placeholder .md file for this directory
                    dir_name = os.path.basename(sub_dir)
                    title = dir_name.replace('-', ' ').replace('_', ' ')
                    placeholder_path = os.path.join(local_path_base, sub_dir + '.md')

                    if not os.path.exists(placeholder_path):
                        logger.info(f"Creating placeholder file for directory '{dir_name}': {placeholder_path}")
                        placeholder_content = f"# {title}\n\n## Place holder\n"
                        os.makedirs(os.path.dirname(placeholder_path), exist_ok=True)
                        with open(placeholder_path, 'w', encoding='utf-8') as f:
                            f.write(placeholder_content)

                    # Add to hierarchy so it gets processed
                    if parent_key not in hierarchy:
                        hierarchy[parent_key] = []
                    hierarchy[parent_key].append(placeholder_path)

        return hierarchy

    def _push_hierarchy_to_confluence(
        self,
        hierarchy: Dict[str, List[str]],
        page_ops: PageOperations,
        space_config: SpaceConfig,
        sync_config: SyncConfig,
        files_to_update: List[Tuple[str, str]],
        parent_page_id: str,
        current_dir: str = '__root__',
        depth: int = 0
    ) -> None:
        """Recursively push pages to Confluence maintaining hierarchy.

        Args:
            hierarchy: Hierarchy map from _build_local_hierarchy
            page_ops: PageOperations instance for creating/updating pages
            space_config: Space configuration
            sync_config: Sync configuration with get_baseline callback
            files_to_update: List to append (file_path, content) tuples for updates
            parent_page_id: Parent page ID in Confluence
            current_dir: Current directory being processed
            depth: Current recursion depth (default: 0, increments with each level)

        Raises:
            FilesystemError: If recursion depth exceeds MAX_RECURSION_DEPTH
        """
        # Check recursion depth to prevent stack overflow (M2)
        if depth > MAX_RECURSION_DEPTH:
            raise FilesystemError(
                current_dir,
                'hierarchy',
                f'Directory hierarchy exceeds maximum depth of {MAX_RECURSION_DEPTH}. '
                f'This may indicate a circular reference or excessively deep nesting.'
            )

        if current_dir not in hierarchy:
            return

        # Process all files in current directory level
        for file_path in hierarchy[current_dir]:
            # Validate file size to prevent memory exhaustion (M1)
            self._validate_file_size(file_path)

            # Read the local file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse frontmatter
            local_page = FrontmatterHandler.parse(file_path, content)

            # Check for unresolved conflict markers during bidirectional sync only
            # For force-push, user explicitly wants to overwrite - don't block
            if not sync_config.force_push and self._has_conflict_markers(local_page.content or ""):
                self._log_conflict_marker_error(file_path)
                # Still need to process children even if this file is skipped
                filename = os.path.basename(file_path)
                dir_name = filename[:-3] if filename.endswith('.md') else filename
                rel_path = os.path.relpath(file_path, space_config.local_path)
                parent_dir = os.path.dirname(rel_path)
                child_dir_key = os.path.join(parent_dir, dir_name) if parent_dir and parent_dir != '.' else dir_name
                # Use existing page_id if available for children, otherwise skip children too
                if local_page.page_id:
                    self._push_hierarchy_to_confluence(
                        hierarchy=hierarchy,
                        page_ops=page_ops,
                        space_config=space_config,
                        sync_config=sync_config,
                        files_to_update=files_to_update,
                        parent_page_id=local_page.page_id,
                        current_dir=child_dir_key,
                        depth=depth + 1
                    )
                continue

            # Derive title from content (H1 heading or filename)
            title = self._derive_title_from_content(local_page.content, file_path)

            # Check if page needs to be created (no page_id)
            if not local_page.page_id:
                logger.debug(f"Creating new page in Confluence: {title}")

                # Create page in Confluence
                try:
                    result = page_ops.create_page(
                        space_key=space_config.space_key,
                        title=title,
                        markdown_content=local_page.content or "",
                        parent_id=parent_page_id
                    )

                    # Handle duplicate title (create_page returns success=False
                    # with the existing page's ID - do NOT use that ID)
                    if not result.success and 'already exists' in (result.error or '').lower():
                        filename = os.path.basename(file_path)
                        fallback_title = filename[:-3] if filename.endswith('.md') else filename
                        logger.warning(
                            f"Page '{title}' already exists under same parent "
                            f"- retrying with filename-based title '{fallback_title}'"
                        )
                        result = page_ops.create_page(
                            space_key=space_config.space_key,
                            title=fallback_title,
                            markdown_content=local_page.content or "",
                            parent_id=parent_page_id
                        )
                        if not result.success:
                            raise RuntimeError(
                                f"Failed to create page with fallback title '{fallback_title}': {result.error}"
                            )
                        title = fallback_title

                    created_page_id = result.page_id

                    # Log the page action (← = Confluence updated from local)
                    self._log_page_action("←", file_path)
                    logger.debug(f"Created page '{title}' with ID {created_page_id}")

                    # Update local_page with new page_id and context for confluence_url
                    local_page.page_id = created_page_id
                    local_page.title = title
                    local_page.space_key = space_config.space_key
                    local_page.confluence_base_url = self._get_confluence_base_url()

                    # Generate updated content with new frontmatter
                    updated_content = FrontmatterHandler.generate(local_page)

                    # Add to files to update
                    files_to_update.append((file_path, updated_content))

                except Exception as e:
                    logger.error(f"Failed to create page '{title}': {e}")
                    raise

            else:
                # Page already exists - update it using surgical operations
                logger.debug(f"Updating existing page (ID: {local_page.page_id})")

                try:
                    # BASELINE-CENTRIC DIFFING: Compare local against baseline, not remote
                    # This ensures we're comparing markdown-to-markdown (same format)
                    baseline_content = None
                    if sync_config.get_baseline:
                        baseline_content = sync_config.get_baseline(local_page.page_id)

                    # Normalize content for comparison (strip whitespace)
                    local_content_normalized = (local_page.content or "").strip()

                    # Compare against baseline (not remote!)
                    if baseline_content is not None:
                        # Strip frontmatter from baseline for content comparison
                        baseline_parsed = FrontmatterHandler.parse(file_path, baseline_content)
                        baseline_content_normalized = (baseline_parsed.content or "").strip()

                        # Check if local content differs from baseline
                        if local_content_normalized != baseline_content_normalized:
                            # Use ADF surgical update with baseline for accurate diffing
                            result = page_ops.update_page_surgical_adf(
                                page_id=local_page.page_id,
                                new_markdown_content=local_page.content or "",
                                baseline_markdown=baseline_parsed.content or "",
                            )

                            if result.success:
                                # Log the page action (← = Confluence updated from local)
                                self._log_page_action("←", file_path)
                                logger.debug(
                                    f"Updated page (ID: {local_page.page_id}) "
                                    f"with {result.operations_applied} surgical operations"
                                )
                            else:
                                logger.warning(f"Page update returned: {result.error}")
                        else:
                            # Log unchanged pages during force-push so user sees all files
                            if sync_config.force_push:
                                self._log_page_action("=", file_path)  # = means unchanged
                            logger.debug(f"No changes for page {local_page.page_id} (baseline match) - skipping")
                    else:
                        # No baseline available - use full replacement
                        logger.warning(f"No baseline for page {local_page.page_id} - using full replacement")
                        result = page_ops.update_page_surgical_adf(
                            page_id=local_page.page_id,
                            new_markdown_content=local_page.content or "",
                            baseline_markdown=None,  # Triggers full replacement
                        )

                        if result.success:
                            self._log_page_action("←", file_path)
                            logger.debug(f"Updated page (ID: {local_page.page_id}) via full replacement")
                        else:
                            logger.warning(f"Page update returned: {result.error}")

                    # Ensure local_page has context for confluence_url generation
                    if not local_page.space_key:
                        local_page.space_key = space_config.space_key
                    if not local_page.confluence_base_url:
                        local_page.confluence_base_url = self._get_confluence_base_url()

                    # Generate updated content with new frontmatter
                    updated_content = FrontmatterHandler.generate(local_page)

                    # Add to files to update
                    files_to_update.append((file_path, updated_content))

                except Exception as e:
                    logger.error(f"Failed to update page (ID: {local_page.page_id}): {e}")
                    raise

                created_page_id = local_page.page_id

            # Process children (subdirectory with same name as file without .md)
            filename = os.path.basename(file_path)
            dir_name = filename[:-3] if filename.endswith('.md') else filename
            rel_path = os.path.relpath(file_path, space_config.local_path)
            parent_dir = os.path.dirname(rel_path)
            child_dir_key = os.path.join(parent_dir, dir_name) if parent_dir and parent_dir != '.' else dir_name

            # Recursively push children
            self._push_hierarchy_to_confluence(
                hierarchy=hierarchy,
                page_ops=page_ops,
                space_config=space_config,
                sync_config=sync_config,
                files_to_update=files_to_update,
                parent_page_id=created_page_id,
                current_dir=child_dir_key,
                depth=depth + 1
            )

    def _bidirectional_sync(
        self,
        hierarchy: PageNode,
        local_pages: Dict[str, LocalPage],
        space_config: SpaceConfig,
        sync_config: SyncConfig
    ) -> "SyncResult":
        """Perform bidirectional sync comparing changes on both sides.

        Uses hybrid change detection (mtime + baseline) to determine which
        pages need to be synced:
        1. Filter local pages to only those actually modified
        2. Filter remote pages to only those actually modified
        3. Detect conflicts (modified on both sides) - exclude from auto-sync
        4. Push non-conflicting modified local pages to Confluence
        5. Pull non-conflicting modified remote pages to local
        6. Return conflict info for resolution by CLI layer

        Args:
            hierarchy: PageNode tree from Confluence
            local_pages: Dictionary of local pages by file path
            space_config: Space configuration
            sync_config: Overall sync configuration

        Returns:
            SyncResult with push/pull counts and conflict information
        """
        from .models import SyncResult
        logger.debug("Performing bidirectional sync")

        # Build a map of page_id to PageNode for easier lookup
        confluence_pages: Dict[str, PageNode] = {}
        self._build_page_map(hierarchy, confluence_pages)

        # Exclude parent page if configured (ADR: exclude_parent option)
        if space_config.exclude_parent and hierarchy.page_id in confluence_pages:
            del confluence_pages[hierarchy.page_id]
            logger.debug(f"Excluding parent page {hierarchy.page_id} from bidirectional sync (exclude_parent=True)")

        # Step 1: Filter local pages to only those actually modified
        modified_local_pages: Dict[str, LocalPage] = {}
        for path, page in local_pages.items():
            if self._is_locally_modified(path, page, sync_config):
                modified_local_pages[path] = page

        logger.debug(
            f"Change detection: {len(modified_local_pages)}/{len(local_pages)} "
            f"local pages modified"
        )

        # Step 2: Filter remote pages to only those actually modified
        modified_remote_pages: List[PageNode] = []
        all_remote_pages = list(confluence_pages.values())
        for page_node in all_remote_pages:
            if self._is_remotely_modified(page_node, sync_config):
                modified_remote_pages.append(page_node)

        logger.debug(
            f"Change detection: {len(modified_remote_pages)}/{len(all_remote_pages)} "
            f"remote pages modified"
        )

        # Step 3: Detect conflicts (same page modified on both sides)
        local_modified_ids = {
            page.page_id for page in modified_local_pages.values()
            if page.page_id
        }
        remote_modified_ids = {page.page_id for page in modified_remote_pages}
        conflict_ids = local_modified_ids & remote_modified_ids

        # Build sync result to return conflict information
        sync_result = SyncResult()

        if conflict_ids:
            logger.info(
                f"Both sides modified: {len(conflict_ids)} page(s) - attempting auto-merge"
            )
            # Collect conflict data for resolution by CLI layer
            for page_id in conflict_ids:
                page_node = confluence_pages.get(page_id)
                if page_node:
                    sync_result.conflict_page_ids.append(page_id)
                    sync_result.conflict_titles[page_id] = page_node.title

                    # Build remote content WITH frontmatter to match local/baseline format
                    # This is critical for 3-way merge to work correctly
                    markdown_content = page_node.markdown_content or ""
                    if markdown_content.strip().startswith("# "):
                        content = markdown_content
                    else:
                        content = f"# {page_node.title}\n\n{markdown_content}".strip() + "\n"

                    remote_local_page = LocalPage(
                        file_path="",  # Not used for content generation
                        page_id=page_id,
                        content=content,
                        space_key=page_node.space_key,
                        confluence_base_url=self._get_confluence_base_url()
                    )
                    sync_result.conflict_remote_content[page_id] = FrontmatterHandler.generate(remote_local_page)

                    # Find local path for this page_id
                    for path, local_page in local_pages.items():
                        if local_page.page_id == page_id:
                            sync_result.conflict_local_paths[page_id] = path
                            break
                    logger.info(f"  → {page_node.title} (ID: {page_id})")

        # Step 4: Push modified local pages to Confluence (excluding conflicts)
        non_conflict_local = {
            path: page for path, page in modified_local_pages.items()
            if page.page_id not in conflict_ids
        }
        if non_conflict_local:
            logger.debug(f"Pushing {len(non_conflict_local)} modified local page(s) to Confluence")
            # Use direct update for existing pages (more efficient than hierarchy traversal)
            self._update_modified_pages(non_conflict_local, space_config, sync_config)
            sync_result.pushed_count = len(non_conflict_local)
        else:
            logger.debug("No local pages to push (excluding conflicts)")

        # Step 5: Pull modified remote pages to local (excluding conflicts)
        non_conflict_remote = [
            page for page in modified_remote_pages
            if page.page_id not in conflict_ids
        ]
        if non_conflict_remote:
            logger.debug(f"Pulling {len(non_conflict_remote)} modified remote page(s) to local")
            # Build set of page IDs to selectively pull (only modified pages)
            page_ids_to_pull = {page.page_id for page in non_conflict_remote}
            sync_result.pulled_count = self._pull_from_confluence(
                hierarchy, space_config, sync_config,
                page_ids_to_pull=page_ids_to_pull
            )
        else:
            logger.debug("No remote pages to pull (excluding conflicts)")

        logger.info(
            f"Bidirectional sync completed: {sync_result.pushed_count} pushed, "
            f"{sync_result.pulled_count} pulled, {len(sync_result.conflict_page_ids)} conflicts"
        )
        return sync_result

    def _count_hierarchy_pages(self, node: PageNode) -> int:
        """Count total pages in a hierarchy tree.

        Args:
            node: Root PageNode of the hierarchy

        Returns:
            Total number of pages including the root and all descendants
        """
        count = 1  # Count this node
        for child in node.children:
            count += self._count_hierarchy_pages(child)
        return count

    def _collect_page_ids_from_hierarchy(
        self,
        node: PageNode,
        depth: int = 0
    ) -> Set[str]:
        """Collect all page IDs from a hierarchy tree.

        Args:
            node: Root PageNode of the hierarchy
            depth: Current recursion depth (default: 0, increments with each level)

        Returns:
            Set of all page IDs in the hierarchy

        Raises:
            FilesystemError: If recursion depth exceeds MAX_RECURSION_DEPTH
        """
        # Check recursion depth to prevent stack overflow (M2)
        if depth > MAX_RECURSION_DEPTH:
            raise FilesystemError(
                str(node.page_id),
                'hierarchy',
                f'Page hierarchy exceeds maximum depth of {MAX_RECURSION_DEPTH}. '
                f'This may indicate a circular reference or excessively deep nesting.'
            )

        page_ids = {node.page_id}
        for child in node.children:
            page_ids.update(self._collect_page_ids_from_hierarchy(child, depth=depth + 1))
        return page_ids

    def _build_page_map(
        self,
        node: PageNode,
        page_map: Dict[str, PageNode]
    ) -> None:
        """Recursively build a map of page_id to PageNode.

        Args:
            node: Current PageNode to process
            page_map: Dictionary to populate with page_id -> PageNode mappings
        """
        page_map[node.page_id] = node
        for child in node.children:
            self._build_page_map(child, page_map)

    def _update_modified_pages(
        self,
        local_pages: Dict[str, LocalPage],
        space_config: SpaceConfig,
        sync_config: SyncConfig
    ) -> None:
        """Update specific modified pages directly in Confluence.

        This method is optimized for bidirectional sync where we only need
        to update specific pages that have been modified locally. Unlike
        _push_to_confluence which handles hierarchy creation, this method
        directly updates existing pages by their page_id.

        Args:
            local_pages: Dictionary mapping file_path to LocalPage objects
            space_config: Space configuration
            sync_config: Overall sync configuration
        """
        logger.debug(f"Updating {len(local_pages)} modified page(s) in Confluence")

        if not local_pages:
            logger.debug("No pages to update")
            return

        page_ops = PageOperations()
        files_to_update: List[Tuple[str, str]] = []
        updated_count = 0
        skipped_count = 0

        for file_path, local_page in local_pages.items():
            if not local_page.page_id:
                # New page without page_id - use full push for creation
                logger.warning(f"Skipping new page without page_id: {file_path}")
                skipped_count += 1
                continue

            # Check for unresolved conflict markers - refuse to sync corrupted files
            if self._has_conflict_markers(local_page.content or ""):
                self._log_conflict_marker_error(file_path)
                skipped_count += 1
                continue

            try:
                # BASELINE-CENTRIC DIFFING: Compare local against baseline, not remote
                # This ensures we're comparing markdown-to-markdown (same format)
                baseline_content = None
                if sync_config.get_baseline:
                    baseline_content = sync_config.get_baseline(local_page.page_id)

                # Normalize content for comparison (strip whitespace)
                local_content_normalized = (local_page.content or "").strip()

                # Compare against baseline (not remote!)
                if baseline_content is not None:
                    # Strip frontmatter from baseline for content comparison
                    baseline_parsed = FrontmatterHandler.parse(file_path, baseline_content)
                    baseline_content_normalized = (baseline_parsed.content or "").strip()

                    # Check if local content differs from baseline
                    if local_content_normalized != baseline_content_normalized:
                        # Use ADF surgical update with baseline for accurate diffing
                        result = page_ops.update_page_surgical_adf(
                            page_id=local_page.page_id,
                            new_markdown_content=local_page.content or "",
                            baseline_markdown=baseline_parsed.content or "",
                        )

                        if result.success:
                            # Log the page action (← = Confluence updated from local)
                            self._log_page_action("←", file_path)
                            logger.debug(
                                f"Updated page (ID: {local_page.page_id}) "
                                f"with {result.operations_applied} surgical operations"
                            )
                            updated_count += 1
                        else:
                            logger.warning(f"Page update returned: {result.error}")
                    else:
                        # Content matches baseline - skip update
                        logger.debug(f"No changes for page {local_page.page_id} (baseline match) - skipping")
                        skipped_count += 1
                        continue  # Skip to next page without updating local file
                else:
                    # No baseline available - use full replacement
                    logger.warning(f"No baseline for page {local_page.page_id} - using full replacement")
                    result = page_ops.update_page_surgical_adf(
                        page_id=local_page.page_id,
                        new_markdown_content=local_page.content or "",
                        baseline_markdown=None,  # Triggers full replacement
                    )

                    if result.success:
                        self._log_page_action("←", file_path)
                        logger.debug(f"Updated page (ID: {local_page.page_id}) via full replacement")
                        updated_count += 1
                    else:
                        logger.warning(f"Page update returned: {result.error}")

                # Ensure local_page has context for confluence_url generation
                if not local_page.space_key:
                    local_page.space_key = space_config.space_key
                if not local_page.confluence_base_url:
                    local_page.confluence_base_url = self._get_confluence_base_url()

                # Generate updated content with frontmatter for local file
                updated_content = FrontmatterHandler.generate(local_page)
                files_to_update.append((file_path, updated_content))

            except Exception as e:
                logger.error(f"Failed to update page (ID: {local_page.page_id}): {e}")
                raise

        # Write updated frontmatter back to local files atomically
        if files_to_update:
            logger.debug(f"Updating {len(files_to_update)} local file(s) with page IDs")
            self._write_files_atomic(
                files_to_write=files_to_update,
                temp_dir=sync_config.temp_dir
            )

        logger.debug(f"Successfully updated {updated_count} page(s), skipped {skipped_count}")

    def _is_locally_modified(
        self,
        file_path: str,
        local_page: LocalPage,
        sync_config: SyncConfig
    ) -> bool:
        """Check if a local file has been modified since last sync.

        Uses hybrid approach for change detection:
        1. mtime check (fast filter): Skip if file mtime < last_synced
        2. baseline check (confirmation): Compare content to baseline

        Args:
            file_path: Path to the local file
            local_page: LocalPage object with content
            sync_config: SyncConfig with last_synced and get_baseline

        Returns:
            True if file is modified (should be pushed), False otherwise
        """
        # New pages (no page_id) are always considered "modified" (need to be created)
        if not local_page.page_id:
            logger.debug(f"New local page (no page_id): {file_path}")
            return True

        # Step 1: mtime check (fast filter)
        if sync_config.last_synced:
            try:
                file_mtime = os.path.getmtime(file_path)
                # Parse ISO 8601 timestamp to Unix timestamp
                last_synced_dt = datetime.fromisoformat(
                    sync_config.last_synced.replace('Z', '+00:00')
                )
                last_synced_ts = last_synced_dt.timestamp()

                if file_mtime <= last_synced_ts:
                    logger.debug(
                        f"File unchanged (mtime check): {file_path} "
                        f"(mtime={file_mtime:.0f} <= last_synced={last_synced_ts:.0f})"
                    )
                    return False
                else:
                    logger.debug(
                        f"File potentially modified (mtime check): {file_path} "
                        f"(mtime={file_mtime:.0f} > last_synced={last_synced_ts:.0f})"
                    )
            except (ValueError, OSError) as e:
                logger.warning(f"mtime check failed for {file_path}: {e}, proceeding to baseline check")

        # Step 2: baseline check (confirmation)
        if sync_config.get_baseline and local_page.page_id:
            try:
                baseline_content = sync_config.get_baseline(local_page.page_id)
                if baseline_content is not None:
                    # Compare full file content (frontmatter + content)
                    current_content = FrontmatterHandler.generate(local_page)
                    if current_content == baseline_content:
                        logger.debug(f"File unchanged (baseline check): {file_path}")
                        return False
                    else:
                        logger.debug(f"File modified (baseline check): {file_path}")
                        return True
                else:
                    # No baseline exists - treat as modified (first sync for this page)
                    logger.debug(f"No baseline found for page {local_page.page_id}: {file_path}")
                    return True
            except Exception as e:
                logger.warning(f"Baseline check failed for {file_path}: {e}, assuming modified")
                return True

        # No checks available or passed mtime check - assume modified
        logger.debug(f"Assuming modified (no baseline available): {file_path}")
        return True

    def _is_remotely_modified(
        self,
        page_node: PageNode,
        sync_config: SyncConfig
    ) -> bool:
        """Check if a remote page has been modified since last sync.

        Compares remote content to baseline to detect changes.

        Args:
            page_node: PageNode from Confluence hierarchy
            sync_config: SyncConfig with get_baseline callback

        Returns:
            True if page is modified (should be pulled), False otherwise
        """
        if not sync_config.get_baseline:
            # No baseline available - assume modified (pull everything)
            logger.debug(f"No baseline callback, assuming modified: {page_node.title}")
            return True

        try:
            baseline_content = sync_config.get_baseline(page_node.page_id)
            if baseline_content is None:
                # No baseline exists - this is a new page, pull it
                logger.debug(f"No baseline for remote page {page_node.page_id}: {page_node.title}")
                return True

            # Build the expected file content from the remote page
            # (same format as would be written locally)
            markdown_content = page_node.markdown_content or ""
            if markdown_content.strip().startswith("# "):
                content = markdown_content
            else:
                content = f"# {page_node.title}\n\n{markdown_content}".strip() + "\n"

            remote_local_page = LocalPage(
                file_path="",  # Not used for comparison
                page_id=page_node.page_id,
                content=content,
                space_key=page_node.space_key,
                confluence_base_url=self._get_confluence_base_url()
            )
            remote_content = FrontmatterHandler.generate(remote_local_page)

            if remote_content == baseline_content:
                logger.debug(f"Remote unchanged (baseline check): {page_node.title}")
                return False
            else:
                logger.debug(f"Remote modified (baseline check): {page_node.title}")
                return True

        except Exception as e:
            logger.warning(f"Baseline check failed for remote page {page_node.page_id}: {e}, assuming modified")
            return True

    def _derive_title_from_content(self, content: str, file_path: str) -> str:
        """Derive page title from markdown content or filename.

        Implements title derivation strategy:
        1. Extract from H1 header (# Title) in markdown content
        2. Fall back to filename (without .md extension)

        Note: CQL-based titles from Confluence are handled separately
        via the API and PageNode structure.

        Args:
            content: Markdown content to extract title from
            file_path: Path to file (used as fallback)

        Returns:
            Derived title string

        Example:
            >>> content = "# My Page Title\\n\\nContent here"
            >>> title = mapper._derive_title_from_content(content, "page.md")
            >>> assert title == "My Page Title"
        """
        import re

        # Try to extract H1 header from content
        # Match lines starting with # followed by space and title text
        h1_pattern = r'^#\s+(.+)$'
        match = re.search(h1_pattern, content, re.MULTILINE)

        if match:
            title = match.group(1).strip()
            logger.debug(f"Extracted title from H1: {title}")
            return title

        # Fall back to filename (without .md extension)
        filename = os.path.basename(file_path)
        title = filename[:-3] if filename.endswith('.md') else filename
        logger.debug(f"Using filename as title: {title}")
        return title

    def _read_local_files(self, local_path: str) -> Dict[str, LocalPage]:
        """Read all markdown files from local directory.

        Recursively scans the directory for .md files and parses their
        frontmatter to create LocalPage objects.

        Args:
            local_path: Root directory to scan

        Returns:
            Dictionary mapping file paths to LocalPage objects

        Raises:
            FilesystemError: If directory cannot be read
            FrontmatterError: If frontmatter is invalid
        """
        local_pages: Dict[str, LocalPage] = {}

        # Check if directory exists
        if not os.path.exists(local_path):
            logger.info(f"Local path {local_path} does not exist - treating as empty")
            return local_pages

        if not os.path.isdir(local_path):
            raise FilesystemError(
                local_path,
                'read',
                'Path exists but is not a directory'
            )

        # Walk directory tree
        try:
            for root, dirs, files in os.walk(local_path):
                for filename in files:
                    if filename.endswith('.md'):
                        file_path = os.path.join(root, filename)
                        try:
                            # Validate path safety to prevent traversal attacks
                            self._validate_path_safety(file_path, local_path)

                            # Validate file size to prevent memory exhaustion (M1)
                            self._validate_file_size(file_path)

                            # Read file content
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()

                            # Parse frontmatter
                            local_page = FrontmatterHandler.parse(file_path, content)
                            local_pages[file_path] = local_page

                        except Exception as e:
                            logger.warning(
                                f"Failed to parse {file_path}: {e} - skipping"
                            )
                            # Continue processing other files

        except PermissionError:
            raise FilesystemError(
                local_path,
                'read',
                'Permission denied'
            )
        except Exception as e:
            raise FilesystemError(
                local_path,
                'read',
                str(e)
            )

        logger.debug(f"Found {len(local_pages)} local markdown file(s)")
        return local_pages

    def _write_files_atomic(
        self,
        files_to_write: List[Tuple[str, str]],
        temp_dir: str
    ) -> None:
        """Write multiple files atomically using two-phase commit.

        Implements ADR-011: Atomic file operations.

        Phase 1: Write all files to temporary directory
        Phase 2: Move files from temp to final location (atomic on most filesystems)

        If any operation fails, rollback is performed automatically.

        Args:
            files_to_write: List of (file_path, content) tuples
            temp_dir: Temporary directory for staging files

        Raises:
            FilesystemError: If file operations fail
        """
        if not files_to_write:
            logger.debug("No files to write")
            return

        logger.debug(f"Writing {len(files_to_write)} file(s) atomically")

        # Create temp directory
        try:
            os.makedirs(temp_dir, exist_ok=True)
        except Exception as e:
            raise FilesystemError(
                temp_dir,
                'create_directory',
                str(e)
            )

        # Use try-finally to ensure temp directory cleanup on all exit paths
        try:
            # Phase 1: Write to temp directory
            temp_files: List[Tuple[str, str]] = []
            try:
                for file_path, content in files_to_write:
                    # Validate path safety to prevent traversal attacks
                    if self._base_path:
                        self._validate_path_safety(file_path, self._base_path)

                    # Create temp file path preserving full relative structure to avoid collisions
                    # Use hash of full path to ensure uniqueness while keeping filename readable
                    path_hash = hashlib.md5(file_path.encode()).hexdigest()[:8]
                    basename = os.path.basename(file_path)
                    temp_file_path = os.path.join(temp_dir, f"{path_hash}_{basename}")

                    # Write to temp file
                    with open(temp_file_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    temp_files.append((temp_file_path, file_path))

            except Exception as e:
                # Rollback: clean up temp files
                logger.error(f"Phase 1 failed: {e} - rolling back")
                self._cleanup_temp_files(temp_files)
                raise FilesystemError(
                    file_path,
                    'write',
                    f"Atomic write phase 1 failed: {str(e)}"
                )

            # Phase 2: Move from temp to final location
            moved_files: List[str] = []
            try:
                for temp_file_path, final_file_path in temp_files:
                    # Ensure target directory exists
                    final_dir = os.path.dirname(final_file_path)
                    if final_dir:
                        os.makedirs(final_dir, exist_ok=True)

                    # Move file (atomic on most filesystems)
                    shutil.move(temp_file_path, final_file_path)
                    moved_files.append(final_file_path)

            except Exception as e:
                # Rollback: restore from temp if possible
                logger.error(f"Phase 2 failed: {e} - attempting rollback")
                # Note: Full rollback is complex (would need to restore original files)
                # For MVP, we log the error and clean up temp
                self._cleanup_temp_files(temp_files)
                raise FilesystemError(
                    final_file_path,
                    'move',
                    f"Atomic write phase 2 failed: {str(e)}"
                )

            logger.debug(f"Successfully wrote {len(moved_files)} file(s)")

        finally:
            # CRITICAL: Always clean up temp directory on all exit paths (success/failure)
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")

    def _cleanup_temp_files(self, temp_files: List[Tuple[str, str]]) -> None:
        """Clean up temporary files after failed atomic operation.

        Args:
            temp_files: List of (temp_path, final_path) tuples
        """
        for temp_path, _ in temp_files:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Failed to remove temp file {temp_path}: {e}")
