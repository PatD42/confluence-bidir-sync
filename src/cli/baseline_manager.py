"""Baseline management for 3-way merge conflict resolution.

This module implements the BaselineManager which maintains a hidden git
repository at .confluence-sync/baseline/ to store page content at the time
of last successful sync. This baseline enables 3-way merge for conflict
resolution per ADR-014.

The 3-way merge approach:
- baseline: Content from last successful sync (stored in hidden repo)
- local: Current local file content
- remote: Current Confluence page content

When both local and remote have changed since last sync, the merge process:
1. First attempts table-aware merge using merge3 library (cell-level granularity)
2. Falls back to git merge-file for non-table content
This allows changes to different cells in the same table row to auto-merge.
"""

import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

# Import fcntl for POSIX file locking (not available on Windows)
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

from src.cli.errors import CLIError

# Pattern to detect unresolved merge conflict markers
CONFLICT_MARKER_PATTERN = re.compile(
    r'^<{7}\s|^={7}\s*$|^>{7}\s',
    re.MULTILINE
)
from src.cli.models import MergeResult
from src.git_integration.table_merge import merge_content_with_table_awareness

logger = logging.getLogger(__name__)


class BaselineManager:
    """Manages hidden git repository for 3-way merge baselines.

    This class handles the lifecycle of the baseline repository:
    - Initialization: Creates .confluence-sync/baseline/.git/ on first use
    - Updates: Commits baseline snapshots after successful sync
    - Merging: Uses git merge-file for 3-way conflict resolution

    The baseline repository is a standard git repo but hidden in
    .confluence-sync/baseline/. It mirrors the structure of synced pages
    and is automatically updated after each successful sync.

    Example:
        >>> manager = BaselineManager()
        >>> manager.initialize()
        >>> # After successful sync:
        >>> manager.update_baseline(page_id, content)
    """

    def __init__(self, baseline_dir: Optional[Path] = None):
        """Initialize baseline manager.

        Args:
            baseline_dir: Optional custom baseline directory path.
                         Defaults to .confluence-sync/baseline/
        """
        if baseline_dir:
            self.baseline_dir = baseline_dir
        else:
            # Default to .confluence-sync/baseline/ in current working directory
            self.baseline_dir = Path.cwd() / ".confluence-sync" / "baseline"

        logger.debug(f"BaselineManager initialized with baseline_dir: {self.baseline_dir}")

    def _validate_page_id(self, page_id: str) -> None:
        """Validate page_id format to prevent command injection.

        Ensures page_id only contains safe characters before using in
        subprocess calls. Confluence page IDs are numeric only.

        Args:
            page_id: The page ID to validate

        Raises:
            CLIError: If page_id contains unsafe characters
        """
        if not page_id or not str(page_id).strip():
            raise CLIError("page_id cannot be empty")

        page_id_str = str(page_id).strip()

        # Validate format: numeric only (Confluence page IDs)
        if not re.match(r'^\d+$', page_id_str):
            raise CLIError(
                f"Invalid page_id format: '{page_id}'. "
                f"Page IDs must contain only numeric characters to prevent command injection."
            )

    def initialize(self) -> None:
        """Initialize the baseline git repository if it doesn't exist.

        Creates the baseline directory and initializes a git repository
        within it. If the repository already exists, this is a no-op.

        The git repo is configured with:
        - user.name: "Confluence Sync Baseline"
        - user.email: "baseline@confluence-sync.local"

        Raises:
            CLIError: If git initialization fails
        """
        logger.info(f"Initializing baseline repository at {self.baseline_dir}")

        # Create baseline directory if it doesn't exist
        try:
            self.baseline_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created baseline directory: {self.baseline_dir}")
        except OSError as e:
            logger.error(f"Failed to create baseline directory: {e}")
            raise CLIError(f"Failed to create baseline directory: {e}") from e

        # Check if git repo already exists
        git_dir = self.baseline_dir / ".git"
        if git_dir.exists():
            logger.info("Baseline repository already initialized")
            return

        # Initialize git repository
        try:
            logger.debug("Running git init")
            result = subprocess.run(
                ["git", "init"],
                cwd=self.baseline_dir,
                capture_output=True,
                text=True,
                check=True
            )
            logger.debug(f"Git init output: {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Git init failed: {e.stderr}")
            raise CLIError(f"Failed to initialize git repository: {e.stderr}")
        except FileNotFoundError:
            logger.error("git command not found - ensure git is installed")
            raise CLIError("git command not found - ensure git is installed and in PATH")

        # Configure git user (required for commits)
        try:
            logger.debug("Configuring git user")
            subprocess.run(
                ["git", "config", "user.name", "Confluence Sync Baseline"],
                cwd=self.baseline_dir,
                capture_output=True,
                text=True,
                check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "baseline@confluence-sync.local"],
                cwd=self.baseline_dir,
                capture_output=True,
                text=True,
                check=True
            )
            logger.debug("Git user configured")
        except subprocess.CalledProcessError as e:
            logger.error(f"Git config failed: {e.stderr}")
            raise CLIError(f"Failed to configure git repository: {e.stderr}")

        logger.info("Baseline repository initialized successfully")

    def is_initialized(self) -> bool:
        """Check if the baseline repository is initialized.

        Returns:
            True if .git directory exists, False otherwise
        """
        git_dir = self.baseline_dir / ".git"
        return git_dir.exists()

    def _acquire_baseline_lock(self, timeout: float = 30.0):
        """Acquire an exclusive lock for baseline repository operations.

        Uses fcntl advisory locking on POSIX systems to prevent race
        conditions during concurrent baseline updates. This locks the
        entire git repository, not just individual pages, because git
        operations (add, commit) affect shared repository state.

        Args:
            timeout: Maximum time to wait for lock acquisition (seconds)

        Returns:
            Context manager that acquires/releases the lock

        Raises:
            CLIError: If lock cannot be acquired within timeout
        """
        from contextlib import contextmanager

        @contextmanager
        def lock_context():
            # Use a single repository-wide lock for all git operations
            lock_file_path = self.baseline_dir / ".git_lock"
            lock_file = None
            lock_acquired = False

            try:
                # Ensure baseline directory exists
                self.baseline_dir.mkdir(parents=True, exist_ok=True)

                # Open lock file
                lock_file = open(lock_file_path, 'w')

                if HAS_FCNTL:
                    # POSIX: Use fcntl for proper locking
                    logger.debug("Acquiring exclusive lock for baseline repository")
                    start_time = time.time()

                    while True:
                        try:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            lock_acquired = True
                            logger.debug("Repository lock acquired")
                            break
                        except IOError:
                            # Lock is held by another process
                            if time.time() - start_time > timeout:
                                raise CLIError(
                                    f"Timeout acquiring baseline repository lock "
                                    f"after {timeout}s. Another sync may be in progress."
                                )
                            # Wait a bit and retry
                            time.sleep(0.1)
                else:
                    # Windows or no fcntl: Log warning but continue
                    logger.warning(
                        "File locking not available on this platform. "
                        "Concurrent baseline updates may cause corruption."
                    )

                yield

            finally:
                # Release lock and cleanup
                if lock_file:
                    if HAS_FCNTL and lock_acquired:
                        try:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                            logger.debug("Repository lock released")
                        except Exception as e:
                            logger.warning(f"Failed to release lock: {e}")

                    lock_file.close()

                # Remove lock file
                try:
                    if lock_file_path.exists():
                        lock_file_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to remove lock file: {e}")

        return lock_context()

    def update_baseline(self, page_id: str, content: str) -> None:
        """Update baseline content for a page and commit to git.

        This method stores the current page content as a baseline snapshot
        after a successful sync. The content is written to {page_id}.md
        in the baseline directory and committed to git.

        Args:
            page_id: Confluence page ID
            content: Page content (markdown) to store as baseline

        Raises:
            CLIError: If baseline repo not initialized or git operations fail

        Example:
            >>> manager = BaselineManager()
            >>> manager.initialize()
            >>> manager.update_baseline("123456", "# Page content\\n...")
        """
        logger.info(f"Updating baseline for page {page_id}")

        # Validate page_id to prevent command injection
        self._validate_page_id(page_id)

        # Check for unresolved conflict markers - refuse to save corrupted content
        if CONFLICT_MARKER_PATTERN.search(content):
            logger.error(
                f"REFUSING to update baseline for page {page_id}: "
                "content contains unresolved merge conflict markers"
            )
            # Don't raise - just log and skip to avoid breaking the sync flow
            return

        # Ensure baseline repo is initialized
        if not self.is_initialized():
            logger.error("Baseline repository not initialized")
            raise CLIError(
                "Baseline repository not initialized. Call initialize() first."
            )

        # Acquire exclusive repository lock to prevent race conditions during baseline update
        # Note: Lock is repository-wide because git operations affect shared state
        with self._acquire_baseline_lock():
            # Write content to baseline file
            baseline_file = self.baseline_dir / f"{page_id}.md"
            try:
                logger.debug(f"Writing baseline content to {baseline_file}")
                baseline_file.write_text(content, encoding="utf-8")
            except OSError as e:
                logger.error(f"Failed to write baseline file {baseline_file}: {e}")
                raise CLIError(f"Failed to write baseline file: {e}") from e

            # Stage the file in git
            try:
                logger.debug(f"Staging baseline file: {page_id}.md")
                subprocess.run(
                    ["git", "add", f"{page_id}.md"],
                    cwd=self.baseline_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
            except subprocess.CalledProcessError as e:
                logger.error(f"Git add failed: {e.stderr}")
                raise CLIError(f"Failed to stage baseline file: {e.stderr}")
            except FileNotFoundError:
                logger.error("git command not found")
                raise CLIError("git command not found - ensure git is installed and in PATH")

            # Commit the baseline update
            commit_message = f"Update baseline for page {page_id}"
            try:
                logger.debug(f"Committing baseline update: {commit_message}")
                result = subprocess.run(
                    ["git", "commit", "-m", commit_message],
                    cwd=self.baseline_dir,
                    capture_output=True,
                    text=True,
                    check=False  # Don't raise on non-zero exit (handles "nothing to commit")
                )

                # Check if commit succeeded or if there was nothing to commit
                # Git may output "nothing to commit" or "nothing added to commit"
                combined_output = result.stdout + result.stderr
                if result.returncode == 0:
                    logger.debug(f"Baseline committed: {result.stdout.strip()}")
                elif "nothing to commit" in combined_output or "nothing added to commit" in combined_output:
                    logger.debug(f"No changes to commit for page {page_id} (content unchanged)")
                else:
                    # Unexpected error - include both stdout and stderr for debugging
                    error_details = result.stderr or result.stdout or "unknown error"
                    logger.error(f"Git commit failed: {error_details}")
                    raise CLIError(f"Failed to commit baseline: {error_details}")

            except FileNotFoundError:
                logger.error("git command not found")
                raise CLIError("git command not found - ensure git is installed and in PATH")

            logger.info(f"Baseline updated successfully for page {page_id}")

    def get_baseline_content(self, page_id: str) -> Optional[str]:
        """Retrieve baseline content for a page.

        This method reads the baseline content stored during the last
        successful sync. Returns None if no baseline exists for the page.

        Args:
            page_id: Confluence page ID

        Returns:
            Baseline content (markdown) or None if not found

        Raises:
            CLIError: If baseline repo not initialized or file read fails critically

        Example:
            >>> manager = BaselineManager()
            >>> manager.initialize()
            >>> content = manager.get_baseline_content("123456")
            >>> if content:
            ...     print("Baseline found")
        """
        logger.debug(f"Retrieving baseline content for page {page_id}")

        # Validate page_id to prevent path traversal
        self._validate_page_id(page_id)

        # Ensure baseline repo is initialized
        if not self.is_initialized():
            logger.error("Baseline repository not initialized")
            raise CLIError(
                "Baseline repository not initialized. Call initialize() first."
            )

        # Read baseline file
        baseline_file = self.baseline_dir / f"{page_id}.md"

        if not baseline_file.exists():
            logger.debug(f"No baseline found for page {page_id}")
            return None

        try:
            logger.debug(f"Reading baseline from {baseline_file}")
            content = baseline_file.read_text(encoding="utf-8")
            logger.debug(f"Baseline retrieved for page {page_id} ({len(content)} bytes)")
            return content
        except OSError as e:
            logger.error(f"Failed to read baseline file {baseline_file}: {e}")
            raise CLIError(f"Failed to read baseline file: {e}") from e

    def merge_file(
        self,
        baseline_content: str,
        local_content: str,
        remote_content: str,
        page_id: str
    ) -> MergeResult:
        """Perform 3-way merge with table-aware cell-level merging.

        This method first attempts a table-aware merge using the merge3 library,
        which provides cell-level granularity for markdown tables. If the content
        has no tables or table structure differs, it falls back to git merge-file.

        The table-aware merge enables:
        - Changes to different cells in the same row → auto-merge
        - Changes to the same cell → conflict (requires manual resolution)

        The merge algorithm:
        1. Try table-aware merge with merge3 (cell-level for tables)
        2. If tables don't match or no tables, fall back to git merge-file
        - Non-overlapping changes: Auto-merged successfully
        - Overlapping changes: Conflict markers inserted
        - Conflict markers format: <<<<<<< local ... ======= ... >>>>>>> remote

        Args:
            baseline_content: Content from last successful sync (common ancestor)
            local_content: Current local file content
            remote_content: Current Confluence page content
            page_id: Confluence page ID (for logging purposes)

        Returns:
            MergeResult with merged content, conflict status, and conflict count

        Raises:
            CLIError: If git merge-file command fails critically

        Example:
            >>> manager = BaselineManager()
            >>> result = manager.merge_file(
            ...     baseline_content="# Title\nOld content",
            ...     local_content="# Title\nLocal changes",
            ...     remote_content="# Title\nRemote changes",
            ...     page_id="123456"
            ... )
            >>> if result.has_conflicts:
            ...     print(f"Manual resolution needed: {result.conflict_count} conflicts")
        """
        logger.info(f"Performing 3-way merge for page {page_id}")

        # Validate page_id to prevent command injection
        self._validate_page_id(page_id)

        # First, try table-aware merge using merge3 library
        try:
            logger.debug(f"Attempting table-aware merge for page {page_id}")
            merged_content, has_conflicts = merge_content_with_table_awareness(
                base_content=baseline_content,
                local_content=local_content,
                remote_content=remote_content
            )

            if not has_conflicts:
                logger.info(f"Table-aware merge successful for page {page_id} (no conflicts)")
                return MergeResult(
                    merged_content=merged_content,
                    has_conflicts=False,
                    conflict_count=0
                )
            else:
                # Table-aware merge has conflicts - count them
                conflict_count = merged_content.count("<<<<<<< local")
                logger.info(
                    f"Table-aware merge has {conflict_count} conflict(s) for page {page_id}"
                )
                return MergeResult(
                    merged_content=merged_content,
                    has_conflicts=True,
                    conflict_count=conflict_count
                )

        except Exception as e:
            # Table-aware merge failed - fall back to git merge-file
            logger.warning(
                f"Table-aware merge failed for page {page_id}: {e}. "
                f"Falling back to git merge-file"
            )

        # Fall back to git merge-file
        logger.debug(f"Using git merge-file for page {page_id}")

        # Create temporary files for the 3-way merge
        # We need to write baseline, local, and remote to temp files
        temp_dir = None
        try:
            # Create a temporary directory for merge files
            temp_dir = tempfile.mkdtemp(prefix="confluence-merge-")
            logger.debug(f"Created temp directory for merge: {temp_dir}")

            # Write content to temporary files
            # git merge-file syntax: git merge-file <current> <base> <other>
            # current = local, base = baseline, other = remote
            local_file = Path(temp_dir) / "local.md"
            baseline_file = Path(temp_dir) / "baseline.md"
            remote_file = Path(temp_dir) / "remote.md"

            logger.debug("Writing merge input files")
            local_file.write_text(local_content, encoding="utf-8")
            baseline_file.write_text(baseline_content, encoding="utf-8")
            remote_file.write_text(remote_content, encoding="utf-8")

            # Run git merge-file
            # Exit codes: 0 = clean merge, 1 = conflicts, >1 = error
            logger.debug(f"Running git merge-file for page {page_id}")
            try:
                result = subprocess.run(
                    [
                        "git", "merge-file",
                        "--marker-size=7",  # Standard conflict marker size
                        "-L", "local",       # Label for local version
                        "-L", "baseline",    # Label for base version
                        "-L", "remote",      # Label for remote version
                        str(local_file),     # Current file (modified in-place)
                        str(baseline_file),  # Base file
                        str(remote_file)     # Other file
                    ],
                    capture_output=True,
                    text=True,
                    check=False  # Don't raise on exit code 1 (conflicts)
                )
            except FileNotFoundError:
                logger.error("git command not found")
                raise CLIError("git command not found - ensure git is installed and in PATH")

            # Read the merged result from local_file (modified in-place by git merge-file)
            try:
                merged_content = local_file.read_text(encoding="utf-8")
                logger.debug(f"Merged content read ({len(merged_content)} bytes)")
            except OSError as e:
                logger.error(f"Failed to read merged content: {e}")
                raise CLIError(f"Failed to read merged content: {e}") from e

            # Determine if merge has conflicts based on exit code
            if result.returncode == 0:
                # Clean merge - no conflicts
                logger.info(f"Clean merge for page {page_id} (no conflicts)")
                return MergeResult(
                    merged_content=merged_content,
                    has_conflicts=False,
                    conflict_count=0
                )
            elif result.returncode == 1:
                # Conflicts detected
                # Count conflict markers in the merged content
                conflict_count = merged_content.count("<<<<<<<")
                logger.info(
                    f"Merge conflicts detected for page {page_id}: "
                    f"{conflict_count} conflict region(s)"
                )
                return MergeResult(
                    merged_content=merged_content,
                    has_conflicts=True,
                    conflict_count=conflict_count
                )
            else:
                # Unexpected error
                logger.error(
                    f"git merge-file failed with exit code {result.returncode}: "
                    f"{result.stderr}"
                )
                raise CLIError(
                    f"git merge-file failed: {result.stderr or 'Unknown error'}"
                )

        except OSError as e:
            logger.error(f"Failed to create temporary files for merge: {e}")
            raise CLIError(f"Failed to create temporary files for merge: {e}") from e

        finally:
            # Clean up temporary directory
            if temp_dir:
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temp directory: {temp_dir}")
                except Exception as e:
                    # Log but don't fail if cleanup fails
                    logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")
