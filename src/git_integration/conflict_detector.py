"""Conflict detection for Confluence page synchronization.

This module provides the ConflictDetector class for detecting version conflicts
between local markdown files and remote Confluence pages. It uses parallel fetches
for efficient batch conflict detection and leverages caching to minimize API calls.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.confluence_client.errors import APIAccessError, PageNotFoundError
from src.git_integration.errors import GitRepositoryError
from src.git_integration.models import (
    ConflictDetectionResult,
    ConflictInfo,
    LocalPage,
    ThreeWayMergeInputs,
)

if TYPE_CHECKING:
    from src.git_integration.git_repository import GitRepository
    from src.git_integration.xhtml_cache import XHTMLCache
    from src.page_operations.page_operations import PageOperations

logger = logging.getLogger(__name__)

# Maximum parallel threads for batch conflict detection
MAX_WORKERS = 10


class ConflictDetector:
    """Detects conflicts by comparing local and remote versions.

    This class performs batch conflict detection across multiple pages using
    parallel API fetches. It leverages the XHTML cache to minimize API calls
    and retrieves base versions from the git repository for three-way merges.

    Example:
        >>> detector = ConflictDetector(page_ops, git_repo, cache)
        >>> result = detector.detect_conflicts(local_pages)
        >>> for conflict in result.conflicts:
        ...     print(f"Conflict: {conflict.page_id}")
    """

    def __init__(
        self,
        page_ops: "PageOperations",
        git_repo: "GitRepository",
        cache: "XHTMLCache",
    ):
        """Initialize conflict detector.

        Args:
            page_ops: PageOperations for Confluence API access
            git_repo: GitRepository for base version retrieval
            cache: XHTMLCache for XHTML caching
        """
        self.page_ops = page_ops
        self.git_repo = git_repo
        self.cache = cache

    def detect_conflicts(
        self,
        local_pages: list[LocalPage],
    ) -> ConflictDetectionResult:
        """Batch detect conflicts for multiple pages.

        This method performs parallel conflict detection across all pages in
        the sync scope. It fetches page metadata from Confluence in parallel
        (max 10 concurrent threads) and compares versions to detect conflicts.

        Args:
            local_pages: List of LocalPage with page_id, local_version, file_path

        Returns:
            ConflictDetectionResult with conflicts and auto-mergeable pages

        Raises:
            APIAccessError: If Confluence API unreachable (fails all pages)
        """
        logger.info(f"Starting batch conflict detection for {len(local_pages)} pages")

        conflicts = []
        auto_mergeable = []
        errors = []

        # Use ThreadPoolExecutor for parallel fetches
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all tasks
            futures = {
                executor.submit(self._check_single_page, page): page
                for page in local_pages
            }

            # Process results as they complete
            for i, future in enumerate(as_completed(futures), 1):
                page = futures[future]
                logger.info(f"Checking page {i}/{len(local_pages)}: {page.page_id}")

                try:
                    result = future.result()
                    if result is None:
                        # No conflict - versions match
                        auto_mergeable.append(page)
                        logger.debug(f"  ✓ No conflict: {page.page_id}")
                    else:
                        # Conflict detected
                        conflicts.append(result)
                        logger.warning(
                            f"  ⚠ Conflict: {page.page_id} "
                            f"(local v{result.local_version} → remote v{result.remote_version})"
                        )
                except Exception as e:
                    error_msg = str(e)
                    errors.append((page.page_id, error_msg))
                    logger.error(f"  ✗ Error checking {page.page_id}: {error_msg}")

        logger.info(
            f"Conflict detection complete: {len(conflicts)} conflicts, "
            f"{len(auto_mergeable)} auto-mergeable, {len(errors)} errors"
        )

        return ConflictDetectionResult(
            conflicts=conflicts,
            auto_mergeable=auto_mergeable,
            errors=errors,
        )

    def _check_single_page(self, page: LocalPage) -> Optional[ConflictInfo]:
        """Check a single page for conflicts.

        Args:
            page: LocalPage to check

        Returns:
            ConflictInfo if conflict detected, None if versions match

        Raises:
            PageNotFoundError: If page doesn't exist on Confluence
            APIAccessError: If API call fails
        """
        # Fetch current version from Confluence
        try:
            snapshot = self.page_ops.get_page_snapshot(page.page_id)
        except PageNotFoundError:
            raise PageNotFoundError(
                f"Page {page.page_id} not found on Confluence. "
                f"It may have been deleted remotely."
            )
        except APIAccessError as e:
            raise APIAccessError(f"Failed to fetch page {page.page_id}: {e}") from e

        remote_version = snapshot.version

        # Compare versions
        if page.local_version == remote_version:
            # No conflict - versions match
            return None

        # Conflict detected - check if base version exists in git
        has_base = self._check_base_exists(page.page_id, page.local_version)

        return ConflictInfo(
            page_id=page.page_id,
            file_path=page.file_path,
            local_version=page.local_version,
            remote_version=remote_version,
            has_base=has_base,
        )

    def _check_base_exists(self, page_id: str, version: int) -> bool:
        """Check if base version exists in git repository.

        Args:
            page_id: Confluence page ID
            version: Version number to check

        Returns:
            True if base version found, False otherwise
        """
        try:
            base_markdown = self.git_repo.get_version(page_id, version)
            return base_markdown is not None
        except GitRepositoryError:
            logger.warning(
                f"Error checking base version for {page_id} v{version}"
            )
            return False

    def get_three_way_merge_inputs(
        self,
        page_id: str,
        local_version: int,
        remote_version: int,
    ) -> ThreeWayMergeInputs:
        """Fetch base, local (cached), and remote markdown for merge.

        This method retrieves the three versions needed for a three-way merge:
        - Base: From git history (last synced version)
        - Local: From git history (should match local file)
        - Remote: From Confluence (current version)

        It uses the XHTML cache to minimize API calls for the remote version.

        Args:
            page_id: Confluence page ID
            local_version: Version in local frontmatter
            remote_version: Current version on Confluence

        Returns:
            ThreeWayMergeInputs with base, local, remote markdown

        Raises:
            APIAccessError: If Confluence fetch fails
            GitRepositoryError: If base version not in git history
        """
        logger.info(
            f"Fetching three-way merge inputs for {page_id}: "
            f"local v{local_version} → remote v{remote_version}"
        )

        # 1. Fetch base version from git (last synced version)
        base_markdown = self.git_repo.get_version(page_id, local_version)
        if base_markdown is None:
            raise GitRepositoryError(
                repo_path=self.git_repo.repo_path,
                message=f"Base version {local_version} not found in git history for page {page_id}",
            )

        # 2. Fetch local version from git (should match local file)
        # Using git as source of truth for consistency
        local_markdown = self.git_repo.get_version(page_id, local_version)
        if local_markdown is None:
            raise GitRepositoryError(
                repo_path=self.git_repo.repo_path,
                message=f"Local version {local_version} not found in git history for page {page_id}",
            )

        # 3. Fetch remote version from Confluence (via cache)
        try:
            snapshot = self.page_ops.get_page_snapshot(page_id)
        except PageNotFoundError:
            raise PageNotFoundError(
                f"Page {page_id} not found on Confluence. "
                f"It may have been deleted remotely."
            )
        except APIAccessError as e:
            raise APIAccessError(
                f"Failed to fetch remote version for {page_id}: {e}"
            )

        # Cache the XHTML for future use
        try:
            self.cache.put(
                page_id=page_id,
                version=remote_version,
                xhtml=snapshot.xhtml,
                last_modified=snapshot.last_modified,
            )
            logger.debug(f"Cached XHTML for {page_id} v{remote_version}")
        except Exception as e:
            # Don't fail the merge if caching fails
            logger.warning(f"Failed to cache XHTML for {page_id}: {e}")

        remote_markdown = snapshot.markdown

        logger.info(
            f"  Retrieved: base ({len(base_markdown)} chars), "
            f"local ({len(local_markdown)} chars), "
            f"remote ({len(remote_markdown)} chars)"
        )

        return ThreeWayMergeInputs(
            page_id=page_id,
            base_markdown=base_markdown,
            local_markdown=local_markdown,
            remote_markdown=remote_markdown,
            local_version=local_version,
            remote_version=remote_version,
        )
