"""Git repository fixtures for testing.

These fixtures provide pre-configured git repositories for testing
the git integration module. They use temporary directories and real
git operations to create realistic test scenarios.

Usage:
    from tests.fixtures.git_test_repos import empty_git_repo, repo_with_history

    # In a test function
    with empty_git_repo() as repo_path:
        # repo_path is a temporary directory with initialized git repo
        pass
"""

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List, Tuple


@contextmanager
def empty_git_repo() -> Generator[Path, None, None]:
    """Create a temporary empty git repository.

    Yields:
        Path to the temporary git repository directory.

    Example:
        with empty_git_repo() as repo_path:
            # repo_path contains an initialized git repo with no commits
            assert (repo_path / ".git").exists()
    """
    temp_dir = tempfile.mkdtemp(prefix="test_git_repo_")
    repo_path = Path(temp_dir)

    try:
        # Initialize git repository
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )

        # Configure git user for commits
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True
        )

        yield repo_path
    finally:
        # Cleanup temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)


@contextmanager
def repo_with_history(
    commits: List[Tuple[str, str]] = None
) -> Generator[Path, None, None]:
    """Create a temporary git repository with commit history.

    Args:
        commits: List of (filename, content) tuples to commit.
                 If None, creates default history with 3 commits.

    Yields:
        Path to the temporary git repository directory.

    Example:
        commits = [
            ("README.md", "# Project"),
            ("page_123.md", "# Version 1"),
            ("page_123.md", "# Version 2"),
        ]
        with repo_with_history(commits) as repo_path:
            # repo_path contains git repo with 3 commits
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            assert result.stdout.strip() == "3"
    """
    # Default commit history if none provided
    if commits is None:
        commits = [
            ("README.md", "# Test Repository\n\nInitial commit\n"),
            ("123456.md", "# Test Page\n\nVersion 1 content\n"),
            ("123456.md", "# Test Page\n\nVersion 2 content with updates\n"),
        ]

    temp_dir = tempfile.mkdtemp(prefix="test_git_repo_history_")
    repo_path = Path(temp_dir)

    try:
        # Initialize git repository
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )

        # Configure git user for commits
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True
        )

        # Create commits
        for idx, (filename, content) in enumerate(commits, start=1):
            # Write file
            file_path = repo_path / filename
            file_path.write_text(content, encoding="utf-8")

            # Stage file
            subprocess.run(
                ["git", "add", filename],
                cwd=repo_path,
                check=True,
                capture_output=True
            )

            # Commit
            commit_msg = f"Commit {idx}: Update {filename}"
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=repo_path,
                check=True,
                capture_output=True
            )

        yield repo_path
    finally:
        # Cleanup temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)


@contextmanager
def repo_with_page_versions(
    page_id: str,
    versions: List[Tuple[int, str]]
) -> Generator[Path, None, None]:
    """Create a git repository with multiple versions of a Confluence page.

    This fixture creates a realistic scenario where a page has been synced
    multiple times with incrementing version numbers.

    Args:
        page_id: Confluence page ID (e.g., "123456")
        versions: List of (version_number, markdown_content) tuples

    Yields:
        Path to the temporary git repository directory.

    Example:
        versions = [
            (1, "# Initial Version"),
            (2, "# Updated Version"),
            (3, "# Latest Version"),
        ]
        with repo_with_page_versions("123456", versions) as repo_path:
            # repo_path contains commits with messages:
            # "Page 123456: version 1"
            # "Page 123456: version 2"
            # "Page 123456: version 3"
            pass
    """
    temp_dir = tempfile.mkdtemp(prefix="test_git_repo_versions_")
    repo_path = Path(temp_dir)

    try:
        # Initialize git repository
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )

        # Configure git user for commits
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True
        )

        # Create initial README
        readme_path = repo_path / "README.md"
        readme_path.write_text(
            f"# Confluence Page Repository\n\nPage ID: {page_id}\n",
            encoding="utf-8"
        )
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=repo_path,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial repository setup"],
            cwd=repo_path,
            check=True,
            capture_output=True
        )

        # Create version commits
        filename = f"{page_id}.md"
        for version_num, content in versions:
            # Write page file
            file_path = repo_path / filename
            file_path.write_text(content, encoding="utf-8")

            # Stage file
            subprocess.run(
                ["git", "add", filename],
                cwd=repo_path,
                check=True,
                capture_output=True
            )

            # Commit with version number in message (matches GitRepository format)
            commit_msg = f"Page {page_id}: version {version_num}"
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=repo_path,
                check=True,
                capture_output=True
            )

        yield repo_path
    finally:
        # Cleanup temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)


def get_commit_count(repo_path: Path) -> int:
    """Get the number of commits in a git repository.

    Args:
        repo_path: Path to the git repository

    Returns:
        Number of commits in the repository

    Example:
        with repo_with_history() as repo_path:
            count = get_commit_count(repo_path)
            assert count == 3
    """
    result = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True
    )
    return int(result.stdout.strip())


def get_file_content_at_commit(
    repo_path: Path,
    filename: str,
    commit: str = "HEAD"
) -> str:
    """Get file content at a specific commit.

    Args:
        repo_path: Path to the git repository
        filename: Name of the file to retrieve
        commit: Git commit reference (default: HEAD)

    Returns:
        File content as string

    Example:
        with repo_with_history() as repo_path:
            content = get_file_content_at_commit(repo_path, "123456.md", "HEAD~1")
            assert "Version 1" in content
    """
    result = subprocess.run(
        ["git", "show", f"{commit}:{filename}"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout


def get_latest_commit_sha(repo_path: Path) -> str:
    """Get the SHA of the latest commit.

    Args:
        repo_path: Path to the git repository

    Returns:
        Full SHA hash of HEAD commit

    Example:
        with repo_with_history() as repo_path:
            sha = get_latest_commit_sha(repo_path)
            assert len(sha) == 40  # Full SHA length
    """
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()
