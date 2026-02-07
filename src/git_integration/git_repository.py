"""Git repository management for Confluence markdown mirror.

This module provides the GitRepository class for managing a git repository that
stores historical versions of Confluence pages as markdown files. It uses subprocess
to execute git commands and provides version tracking for conflict detection.
"""

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from src.git_integration.errors import GitRepositoryError

logger = logging.getLogger(__name__)

# Git command timeout in seconds
GIT_TIMEOUT = 10


class GitRepository:
    """Manages git repository for Confluence markdown mirror.

    This class handles initialization, committing, and retrieval of markdown
    versions using a git repository. Files are stored as {page-id}.md in a flat
    structure with commit messages encoding version information.

    File structure:
        .confluence-sync/MYSPACE_md/
          .git/                  # Git internals
          123456.md              # Page ID 123456
          789012.md              # Page ID 789012
          README.md              # Auto-generated description

    Commit message format:
        "Page {page_id}: version {version}"

    Example:
        >>> repo = GitRepository(".confluence-sync/MYSPACE_md")
        >>> repo.init_if_not_exists()
        >>> sha = repo.commit_version("123456", "# Hello", 1)
        >>> content = repo.get_version("123456", 1)
    """

    def __init__(self, repo_path: str):
        """Initialize git repository manager.

        Args:
            repo_path: Path to git repo (e.g., .confluence-sync/MYSPACE_md)
        """
        self.repo_path = repo_path
        self._ensure_absolute_path()

    def _ensure_absolute_path(self) -> None:
        """Convert repo_path to absolute path if relative."""
        if not os.path.isabs(self.repo_path):
            self.repo_path = os.path.abspath(self.repo_path)

    def init_if_not_exists(self) -> None:
        """Initialize git repo if it doesn't exist.

        Creates directory and runs 'git init'. If repo already exists (has .git),
        this is a no-op. Also creates a README.md file to document the repo.

        Raises:
            GitRepositoryError: If initialization fails
        """
        git_dir = os.path.join(self.repo_path, ".git")

        if os.path.exists(git_dir):
            logger.debug(f"Git repository already exists at {self.repo_path}")
            return

        # Create directory if it doesn't exist
        try:
            os.makedirs(self.repo_path, exist_ok=True)
            logger.info(f"Created directory: {self.repo_path}")
        except OSError as e:
            raise GitRepositoryError(
                repo_path=self.repo_path,
                message=f"Failed to create directory: {e}",
            )

        # Initialize git repository
        try:
            result = subprocess.run(
                ["git", "init"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
            )

            if result.returncode != 0:
                raise GitRepositoryError(
                    repo_path=self.repo_path,
                    message="Failed to initialize git repository",
                    git_output=result.stderr,
                )

            logger.info(f"Initialized git repository at {self.repo_path}")

        except subprocess.TimeoutExpired:
            raise GitRepositoryError(
                repo_path=self.repo_path,
                message=f"Git init timed out after {GIT_TIMEOUT} seconds",
            )
        except FileNotFoundError:
            raise GitRepositoryError(
                repo_path=self.repo_path,
                message="Git command not found. Please install git.",
            )

        # Create README.md
        self._create_readme()

    def _create_readme(self) -> None:
        """Create README.md file in repository root."""
        readme_path = os.path.join(self.repo_path, "README.md")
        readme_content = (
            "# Confluence Markdown Mirror\n\n"
            "This repository is managed by confluence-bidir-sync.\n\n"
            "It stores historical versions of Confluence pages as markdown files "
            "for conflict detection and three-way merge resolution.\n\n"
            "**Do not modify files in this repository manually.**\n"
        )

        try:
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(readme_content)

            # Commit README
            subprocess.run(
                ["git", "add", "README.md"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
            )

            subprocess.run(
                ["git", "commit", "-m", "Initial commit: Add README"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
            )

            logger.debug("Created and committed README.md")

        except Exception as e:
            # Non-critical error - log and continue
            logger.warning(f"Failed to create README.md: {e}")

    def commit_version(
        self,
        page_id: str,
        markdown: str,
        version: int,
        message: Optional[str] = None,
    ) -> str:
        """Commit markdown version to git repo.

        Creates/updates {page_id}.md file with markdown content and commits
        with a message encoding the version number.

        Args:
            page_id: Confluence page ID
            markdown: Markdown content to commit
            version: Confluence version number
            message: Optional custom commit message (defaults to standard format)

        Returns:
            Commit SHA

        Raises:
            GitRepositoryError: If commit fails
        """
        file_name = f"{page_id}.md"
        file_path = os.path.join(self.repo_path, file_name)

        # Write markdown to file
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(markdown)
        except OSError as e:
            raise GitRepositoryError(
                repo_path=self.repo_path,
                message=f"Failed to write file {file_name}: {e}",
            )

        # Add file to git
        try:
            result = subprocess.run(
                ["git", "add", file_name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
            )

            if result.returncode != 0:
                raise GitRepositoryError(
                    repo_path=self.repo_path,
                    message=f"Failed to add file {file_name}",
                    git_output=result.stderr,
                )

        except subprocess.TimeoutExpired:
            raise GitRepositoryError(
                repo_path=self.repo_path,
                message=f"Git add timed out after {GIT_TIMEOUT} seconds",
            )

        # Commit file
        commit_message = message or f"Page {page_id}: version {version}"

        try:
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
            )

            if result.returncode != 0:
                # Check if it's because nothing changed
                if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                    logger.debug(f"No changes to commit for page {page_id} version {version}")
                    # Get current HEAD SHA
                    return self._get_head_sha()
                else:
                    raise GitRepositoryError(
                        repo_path=self.repo_path,
                        message=f"Failed to commit {file_name}",
                        git_output=result.stderr,
                    )

        except subprocess.TimeoutExpired:
            raise GitRepositoryError(
                repo_path=self.repo_path,
                message=f"Git commit timed out after {GIT_TIMEOUT} seconds",
            )

        # Get commit SHA
        sha = self._get_head_sha()
        logger.info(f"Committed page {page_id} version {version}: {sha[:8]}")
        return sha

    def _get_head_sha(self) -> str:
        """Get current HEAD commit SHA.

        Returns:
            Full commit SHA

        Raises:
            GitRepositoryError: If git command fails
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
            )

            if result.returncode != 0:
                raise GitRepositoryError(
                    repo_path=self.repo_path,
                    message="Failed to get HEAD SHA",
                    git_output=result.stderr,
                )

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            raise GitRepositoryError(
                repo_path=self.repo_path,
                message=f"Git rev-parse timed out after {GIT_TIMEOUT} seconds",
            )

    def get_version(self, page_id: str, version: int) -> Optional[str]:
        """Retrieve markdown for specific version from git history.

        Searches git log for commit with matching page_id and version number,
        then retrieves the file content at that commit.

        Args:
            page_id: Confluence page ID
            version: Version number to retrieve

        Returns:
            Markdown content, or None if version not found

        Raises:
            GitRepositoryError: If git command fails
        """
        file_name = f"{page_id}.md"

        # Search for commit with matching page and version
        search_pattern = f"Page {page_id}: version {version}"

        try:
            # Get commit SHA matching the version
            result = subprocess.run(
                ["git", "log", "--all", "--grep", search_pattern, "--format=%H", "-n", "1"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
            )

            if result.returncode != 0:
                raise GitRepositoryError(
                    repo_path=self.repo_path,
                    message=f"Failed to search git log for page {page_id} version {version}",
                    git_output=result.stderr,
                )

            commit_sha = result.stdout.strip()

            if not commit_sha:
                logger.debug(f"Version {version} not found for page {page_id}")
                return None

            # Get file content at that commit
            result = subprocess.run(
                ["git", "show", f"{commit_sha}:{file_name}"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
            )

            if result.returncode != 0:
                # File might not exist at that commit
                logger.warning(
                    f"File {file_name} not found at commit {commit_sha[:8]}"
                )
                return None

            return result.stdout

        except subprocess.TimeoutExpired:
            raise GitRepositoryError(
                repo_path=self.repo_path,
                message=f"Git command timed out after {GIT_TIMEOUT} seconds",
            )

    def get_latest_version_number(self, page_id: str) -> Optional[int]:
        """Get latest version number committed for page.

        Parses commit messages to extract version numbers and returns the highest.

        Args:
            page_id: Confluence page ID

        Returns:
            Latest version number, or None if no commits

        Raises:
            GitRepositoryError: If git log fails
        """
        # Search for commits matching "Page {page_id}: version X"
        search_pattern = f"Page {page_id}: version"

        try:
            result = subprocess.run(
                ["git", "log", "--all", "--grep", search_pattern, "--format=%s"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
            )

            if result.returncode != 0:
                raise GitRepositoryError(
                    repo_path=self.repo_path,
                    message=f"Failed to get version history for page {page_id}",
                    git_output=result.stderr,
                )

            commit_messages = result.stdout.strip().split("\n")

            if not commit_messages or commit_messages == [""]:
                logger.debug(f"No commit history found for page {page_id}")
                return None

            # Extract version numbers from commit messages
            version_pattern = re.compile(rf"Page {re.escape(page_id)}: version (\d+)")
            versions = []

            for msg in commit_messages:
                match = version_pattern.search(msg)
                if match:
                    versions.append(int(match.group(1)))

            if not versions:
                logger.debug(f"No version numbers found in commits for page {page_id}")
                return None

            latest = max(versions)
            logger.debug(f"Latest version for page {page_id}: {latest}")
            return latest

        except subprocess.TimeoutExpired:
            raise GitRepositoryError(
                repo_path=self.repo_path,
                message=f"Git log timed out after {GIT_TIMEOUT} seconds",
            )

    def validate_repo(self) -> bool:
        """Check if repo is valid git repository.

        Runs 'git fsck' to detect corruption. This is a comprehensive check
        that validates the integrity of the git repository.

        Returns:
            True if valid, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "fsck", "--no-progress"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT * 3,  # fsck can take longer
            )

            if result.returncode == 0:
                logger.debug(f"Repository validation passed: {self.repo_path}")
                return True
            else:
                logger.warning(
                    f"Repository validation failed: {self.repo_path}\n{result.stderr}"
                )
                return False

        except subprocess.TimeoutExpired:
            logger.warning(
                f"Repository validation timed out after {GIT_TIMEOUT * 3} seconds"
            )
            return False
        except Exception as e:
            logger.warning(f"Repository validation error: {e}")
            return False
