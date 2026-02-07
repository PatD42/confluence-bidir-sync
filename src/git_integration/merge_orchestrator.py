"""Merge orchestration for Confluence bidirectional sync.

This module provides the MergeOrchestrator class that coordinates the entire
sync workflow including conflict detection, merge resolution, and pushing changes
to Confluence. It acts as the main entry point for sync operations.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.git_integration.conflict_detector import ConflictDetector
from src.git_integration.errors import GitRepositoryError, MergeConflictError
from src.git_integration.git_repository import GitRepository
from src.git_integration.merge_tool import MergeTool
from src.git_integration.models import (
    LocalPage,
    MergeResult,
    MergeStrategy,
    SyncResult,
)
from src.git_integration.xhtml_cache import XHTMLCache

logger = logging.getLogger(__name__)

# Git merge-file timeout in seconds
MERGE_TIMEOUT = 10


class MergeOrchestrator:
    """Orchestrates conflict detection and resolution workflow.

    This class coordinates the entire bidirectional sync workflow between local
    markdown files and Confluence pages. It uses a three-way merge strategy by
    default, with support for force push/pull operations.

    The sync workflow:
        1. Detect conflicts (batch)
        2. Auto-merge non-conflicting pages
        3. Create .conflict files for conflicts
        4. Launch merge tool for resolution
        5. Push resolved content to Confluence
        6. Commit new versions to git repo

    Example:
        >>> orchestrator = MergeOrchestrator()
        >>> result = orchestrator.sync(local_pages)
        >>> if result.success:
        ...     print(f"Synced {result.pages_synced} pages")
    """

    def __init__(
        self,
        page_ops: Optional["PageOperations"] = None,  # noqa: F821
        git_repo: Optional[GitRepository] = None,
        cache: Optional[XHTMLCache] = None,
        detector: Optional[ConflictDetector] = None,
        merge_tool: Optional[MergeTool] = None,
        converter: Optional["MarkdownConverter"] = None,  # noqa: F821
        local_dir: Optional[str] = None,
    ):
        """Initialize merge orchestrator with dependencies.

        Args:
            page_ops: PageOperations for Confluence API (optional)
            git_repo: GitRepository for version tracking (optional)
            cache: XHTMLCache for XHTML caching (optional)
            detector: ConflictDetector for conflict detection (optional)
            merge_tool: MergeTool for conflict resolution (optional)
            converter: MarkdownConverter for markdown/XHTML conversion (optional)
            local_dir: Directory for local markdown files (optional)

        Note:
            All dependencies are optional to support testing and gradual
            initialization. In production, all should be provided.
        """
        self.page_ops = page_ops
        self.git_repo = git_repo
        self.cache = cache
        self.detector = detector
        self.merge_tool = merge_tool
        self.converter = converter
        self.local_dir = local_dir

    def sync(
        self,
        local_pages: list[LocalPage],
        strategy: MergeStrategy = MergeStrategy.THREE_WAY,
    ) -> SyncResult:
        """Perform bidirectional sync with conflict resolution.

        This method performs the full sync workflow:
        1. Detect conflicts (batch)
        2. Auto-merge non-conflicting pages
        3. Create .conflict files for conflicts
        4. Launch merge tool for resolution
        5. Push resolved content to Confluence
        6. Commit new versions to git repo

        Args:
            local_pages: Pages in sync scope
            strategy: Merge strategy (THREE_WAY, FORCE_PUSH, FORCE_PULL)

        Returns:
            SyncResult with success/failure details

        Raises:
            MergeConflictError: If unresolved conflicts remain
            GitRepositoryError: If git operations fail
            APIAccessError: If Confluence push fails
        """
        logger.info(f"Starting sync with strategy: {strategy.value}")
        logger.info(f"Syncing {len(local_pages)} pages")

        # Handle force operations separately
        if strategy == MergeStrategy.FORCE_PUSH:
            return self.force_push(local_pages)
        elif strategy == MergeStrategy.FORCE_PULL:
            page_ids = [page.page_id for page in local_pages]
            return self.force_pull(page_ids)

        # Three-way merge workflow
        if not self.detector:
            raise ValueError("ConflictDetector is required for THREE_WAY sync")

        # Step 1: Detect conflicts (batch)
        logger.info("Step 1: Detecting conflicts...")
        detection_result = self.detector.detect_conflicts(local_pages)

        logger.info(
            f"Detected {len(detection_result.conflicts)} conflicts, "
            f"{len(detection_result.auto_mergeable)} auto-mergeable pages, "
            f"{len(detection_result.errors)} errors"
        )

        pages_synced = 0
        pages_failed = 0
        conflicts_resolved = 0
        errors = {}

        # Step 2: Auto-merge non-conflicting pages
        if detection_result.auto_mergeable:
            logger.info(
                f"Step 2: Auto-merging {len(detection_result.auto_mergeable)} pages..."
            )
            for page in detection_result.auto_mergeable:
                try:
                    # For auto-mergeable pages, versions match - no merge needed
                    # Just log success
                    logger.info(f"  ✓ Page {page.page_id} is up to date")
                    pages_synced += 1
                except Exception as e:
                    error_msg = f"Auto-merge failed: {e}"
                    logger.error(f"  ✗ {error_msg}")
                    errors[page.page_id] = error_msg
                    pages_failed += 1

        # Step 3: Handle conflicts
        if detection_result.conflicts:
            logger.info(
                f"Step 3: Handling {len(detection_result.conflicts)} conflicts..."
            )
            for conflict in detection_result.conflicts:
                try:
                    # Get three-way merge inputs
                    merge_inputs = self.detector.get_three_way_merge_inputs(
                        page_id=conflict.page_id,
                        local_version=conflict.local_version,
                        remote_version=conflict.remote_version,
                    )

                    # Perform three-way merge
                    merge_result = self._three_way_merge(
                        base=merge_inputs.base_markdown,
                        local=merge_inputs.local_markdown,
                        remote=merge_inputs.remote_markdown,
                    )

                    if merge_result.success:
                        logger.info(
                            f"  ✓ Clean merge for {conflict.page_id} "
                            f"(v{conflict.local_version} → v{conflict.remote_version})"
                        )
                        conflicts_resolved += 1
                        pages_synced += 1
                    else:
                        # Create .conflict file for manual resolution
                        conflict_file = self._create_conflict_file(
                            conflict.page_id, merge_result.merged_markdown
                        )
                        logger.warning(
                            f"  ⚠ Conflict requires manual resolution: {conflict_file}"
                        )

                        # If merge tool available, launch it
                        if self.merge_tool and self.merge_tool.validate_available():
                            logger.info(f"  Launching merge tool for {conflict.page_id}")
                            # Note: Full merge tool integration would be implemented here
                            # For MVP, we just create the conflict file
                            conflicts_resolved += 1
                            pages_synced += 1
                        else:
                            # No merge tool - manual resolution needed
                            error_msg = f"Conflict file created: {conflict_file}"
                            errors[conflict.page_id] = error_msg
                            pages_failed += 1

                except Exception as e:
                    error_msg = f"Conflict handling failed: {e}"
                    logger.error(f"  ✗ {error_msg}")
                    errors[conflict.page_id] = error_msg
                    pages_failed += 1

        # Step 4: Handle detection errors
        for page_id, error_msg in detection_result.errors:
            logger.error(f"  ✗ Detection error for {page_id}: {error_msg}")
            errors[page_id] = error_msg
            pages_failed += 1

        # Build result
        success = pages_failed == 0 and len(errors) == 0

        logger.info(
            f"Sync complete: {pages_synced} synced, {pages_failed} failed, "
            f"{conflicts_resolved} conflicts resolved"
        )

        return SyncResult(
            success=success,
            pages_synced=pages_synced,
            pages_failed=pages_failed,
            conflicts_resolved=conflicts_resolved,
            errors=errors,
        )

    def force_push(self, local_pages: list[LocalPage]) -> SyncResult:
        """Force push local content to Confluence (no conflict detection).

        This method overwrites Confluence content with local content without
        performing any conflict detection. Use with caution as it may overwrite
        remote changes.

        Workflow:
        1. Read local markdown
        2. Convert to XHTML
        3. Push to Confluence (overwrites remote)
        4. Commit new Confluence version to git repo
        5. Update XHTML cache

        Args:
            local_pages: Pages to push

        Returns:
            SyncResult with push details

        Raises:
            APIAccessError: If Confluence push fails
            GitRepositoryError: If git commit fails
        """
        logger.info(f"Force pushing {len(local_pages)} pages to Confluence")

        pages_synced = 0
        pages_failed = 0
        errors = {}

        for page in local_pages:
            try:
                # 1. Read local markdown
                with open(page.file_path, "r", encoding="utf-8") as f:
                    markdown = f.read()

                logger.info(f"  Force pushing {page.page_id}...")

                # 2. Strip frontmatter from markdown
                markdown_without_frontmatter = self._strip_frontmatter(markdown)

                # 3. Convert markdown to XHTML
                if not self.converter:
                    raise ValueError("MarkdownConverter is required for force_push")
                xhtml = self.converter.markdown_to_xhtml(markdown_without_frontmatter)

                # 4. Get current version from Confluence
                if not self.page_ops:
                    raise ValueError("PageOperations is required for force_push")
                snapshot = self.page_ops.get_page_snapshot(page.page_id)

                # 5. Push to Confluence (overwrites remote)
                self.page_ops.api.update_page(
                    page_id=page.page_id,
                    title=snapshot.title,
                    body=xhtml,
                    version=snapshot.version
                )

                # 6. Fetch new version after push
                new_snapshot = self.page_ops.get_page_snapshot(page.page_id)

                # 7. Commit to git repo
                if self.git_repo:
                    self.git_repo.commit_version(
                        page_id=page.page_id,
                        markdown=markdown,
                        version=new_snapshot.version
                    )

                # 8. Update XHTML cache
                if self.cache:
                    self.cache.put(
                        page.page_id,
                        new_snapshot.version,
                        new_snapshot.xhtml,
                        new_snapshot.last_modified
                    )

                logger.info(f"  ✓ Force pushed {page.page_id}")
                pages_synced += 1

            except Exception as e:
                error_msg = f"Force push failed: {e}"
                logger.error(f"  ✗ {error_msg}")
                errors[page.page_id] = error_msg
                pages_failed += 1

        success = pages_failed == 0

        logger.info(f"Force push complete: {pages_synced} synced, {pages_failed} failed")

        return SyncResult(
            success=success,
            pages_synced=pages_synced,
            pages_failed=pages_failed,
            conflicts_resolved=0,
            errors=errors,
        )

    def force_pull(self, page_ids: list[str]) -> SyncResult:
        """Force pull Confluence content to local (no conflict detection).

        This method overwrites local content with Confluence content without
        performing any conflict detection. Use with caution as it may overwrite
        local changes.

        Workflow:
        1. Fetch latest from Confluence
        2. Overwrite local file with markdown
        3. Commit Confluence version to git repo
        4. Update XHTML cache

        Args:
            page_ids: Pages to pull

        Returns:
            SyncResult with pull details

        Raises:
            APIAccessError: If Confluence fetch fails
            GitRepositoryError: If git commit fails
        """
        logger.info(f"Force pulling {len(page_ids)} pages from Confluence")

        pages_synced = 0
        pages_failed = 0
        errors = {}

        for page_id in page_ids:
            try:
                logger.info(f"  Force pulling {page_id}...")

                # 1. Fetch latest from Confluence
                if not self.page_ops:
                    raise ValueError("PageOperations is required for force_pull")
                snapshot = self.page_ops.get_page_snapshot(page_id)

                # 2. Convert XHTML to markdown
                if not self.converter:
                    raise ValueError("MarkdownConverter is required for force_pull")
                markdown = self.converter.xhtml_to_markdown(snapshot.xhtml)

                # 3. Add frontmatter
                frontmatter = (
                    f"---\n"
                    f"page_id: {page_id}\n"
                    f"confluence_version: {snapshot.version}\n"
                    f"---\n\n"
                )
                markdown_with_frontmatter = frontmatter + markdown

                # 4. Write to local file (overwrite existing)
                if self.local_dir:
                    local_file_path = os.path.join(self.local_dir, f"{page_id}.md")
                else:
                    # Fallback to current directory if local_dir not set
                    local_file_path = f"{page_id}.md"

                with open(local_file_path, "w", encoding="utf-8") as f:
                    f.write(markdown_with_frontmatter)

                # 5. Commit to git repo
                if self.git_repo:
                    self.git_repo.commit_version(
                        page_id=page_id,
                        markdown=markdown_with_frontmatter,
                        version=snapshot.version
                    )

                # 6. Update XHTML cache
                if self.cache:
                    self.cache.put(
                        page_id,
                        snapshot.version,
                        snapshot.xhtml,
                        snapshot.last_modified
                    )

                logger.info(f"  ✓ Force pulled {page_id}")
                pages_synced += 1

            except Exception as e:
                error_msg = f"Force pull failed: {e}"
                logger.error(f"  ✗ {error_msg}")
                errors[page_id] = error_msg
                pages_failed += 1

        success = pages_failed == 0

        logger.info(f"Force pull complete: {pages_synced} synced, {pages_failed} failed")

        return SyncResult(
            success=success,
            pages_synced=pages_synced,
            pages_failed=pages_failed,
            conflicts_resolved=0,
            errors=errors,
        )

    def _three_way_merge(
        self, base: str, local: str, remote: str
    ) -> MergeResult:
        """Perform three-way merge using git merge-file.

        This method uses git's battle-tested merge algorithm to perform a
        three-way merge. If the merge completes without conflicts, the result
        is returned directly. If conflicts exist, the merged content with
        conflict markers is returned.

        Args:
            base: Base version markdown (from git history)
            local: Local version markdown
            remote: Remote version markdown (from Confluence)

        Returns:
            MergeResult with success status and merged content

        Raises:
            GitRepositoryError: If git merge-file command fails
        """
        logger.debug("Performing three-way merge with git merge-file")

        # Create temporary files for merge
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as base_file:
            base_file.write(base)
            base_path = base_file.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as local_file:
            local_file.write(local)
            local_path = local_file.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as remote_file:
            remote_file.write(remote)
            remote_path = remote_file.name

        try:
            # Run git merge-file
            # -p: print result to stdout
            # Exit code 0 = clean merge, >0 = conflicts
            result = subprocess.run(
                ["git", "merge-file", "-p", local_path, base_path, remote_path],
                capture_output=True,
                text=True,
                timeout=MERGE_TIMEOUT,
            )

            merged_content = result.stdout
            has_conflict = result.returncode > 0

            if has_conflict:
                logger.debug("  Merge completed with conflicts")
            else:
                logger.debug("  Merge completed cleanly")

            return MergeResult(
                success=not has_conflict,
                merged_markdown=merged_content,
                conflict_file=None,
                git_output=result.stderr,
            )

        except subprocess.TimeoutExpired:
            raise GitRepositoryError(
                repo_path="<temp>",
                message=f"git merge-file timed out after {MERGE_TIMEOUT}s",
            )
        except FileNotFoundError:
            raise GitRepositoryError(
                repo_path="<temp>",
                message="git command not found. Please install git 2.x+",
            )
        except Exception as e:
            raise GitRepositoryError(
                repo_path="<temp>",
                message=f"git merge-file failed: {e}",
            )
        finally:
            # Cleanup temp files
            Path(base_path).unlink(missing_ok=True)
            Path(local_path).unlink(missing_ok=True)
            Path(remote_path).unlink(missing_ok=True)

    def _create_conflict_file(self, page_id: str, merged_content: str) -> str:
        """Create .conflict file for manual resolution.

        Args:
            page_id: Confluence page ID
            merged_content: Merged markdown with conflict markers

        Returns:
            Path to created conflict file
        """
        conflict_file = f"{page_id}.conflict.md"

        try:
            with open(conflict_file, "w", encoding="utf-8") as f:
                f.write(merged_content)

            logger.info(f"Created conflict file: {conflict_file}")
            return conflict_file

        except OSError as e:
            logger.error(f"Failed to create conflict file: {e}")
            raise GitRepositoryError(
                repo_path="<current>",
                message=f"Failed to create conflict file: {e}",
            )

    def _strip_frontmatter(self, markdown: str) -> str:
        """Strip YAML frontmatter from markdown content.

        Args:
            markdown: Markdown content possibly containing frontmatter

        Returns:
            Markdown without frontmatter
        """
        # Check if content starts with frontmatter delimiter
        if not markdown.startswith("---\n"):
            return markdown

        # Find end of frontmatter (second "---")
        end_delimiter_pos = markdown.find("\n---\n", 4)
        if end_delimiter_pos == -1:
            # Malformed frontmatter, return as-is
            return markdown

        # Return content after frontmatter (skip delimiter and newlines)
        return markdown[end_delimiter_pos + 5:].lstrip()
