"""Git test utilities for unit and integration tests.

These utilities provide helper functions for testing git-related functionality
without the overhead of context managers. They complement the fixtures in
tests.fixtures.git_test_repos.

Usage:
    from tests.helpers.git_test_utils import create_temp_git_repo, verify_git_command

    # In a test function
    repo_path = create_temp_git_repo()
    # Use repo_path for testing...
    cleanup_git_repo(repo_path)
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, List, Optional


def create_temp_git_repo() -> Path:
    """Create a temporary git repository for testing.

    This function creates a temporary directory, initializes a git repository,
    and configures basic git settings (user.name, user.email). The repository
    is ready to accept commits immediately.

    Returns:
        Path: Path to the temporary git repository directory

    Note:
        Caller is responsible for cleanup using cleanup_git_repo() or shutil.rmtree()

    Example:
        >>> repo_path = create_temp_git_repo()
        >>> assert (repo_path / ".git").exists()
        >>> cleanup_git_repo(repo_path)
    """
    temp_dir = tempfile.mkdtemp(prefix="test_git_")
    repo_path = Path(temp_dir)

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

    return repo_path


def cleanup_git_repo(repo_path: Path) -> None:
    """Clean up a temporary git repository.

    Args:
        repo_path: Path to the git repository to remove

    Example:
        >>> repo_path = create_temp_git_repo()
        >>> cleanup_git_repo(repo_path)
        >>> assert not repo_path.exists()
    """
    if repo_path.exists():
        shutil.rmtree(repo_path, ignore_errors=True)


def create_test_commit(
    repo_path: Path,
    filename: str,
    content: str,
    commit_message: str
) -> str:
    """Create a test commit in a git repository.

    Args:
        repo_path: Path to the git repository
        filename: Name of the file to create/update
        content: Content to write to the file
        commit_message: Git commit message

    Returns:
        str: SHA hash of the created commit

    Example:
        >>> repo_path = create_temp_git_repo()
        >>> sha = create_test_commit(
        ...     repo_path,
        ...     "test.md",
        ...     "# Test",
        ...     "Add test file"
        ... )
        >>> assert len(sha) == 40  # Full SHA length
    """
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
    subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=repo_path,
        check=True,
        capture_output=True
    )

    # Get commit SHA
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()


def verify_git_command(
    mock_run: Any,
    expected_args: List[str],
    cwd: Optional[str] = None
) -> bool:
    """Verify that a git command was called with expected arguments.

    This helper simplifies assertions in unit tests that mock subprocess.run()
    for git operations.

    Args:
        mock_run: The mocked subprocess.run object
        expected_args: List of expected command arguments (e.g., ["git", "init"])
        cwd: Optional expected working directory

    Returns:
        bool: True if the command was called with expected arguments

    Example:
        >>> from unittest.mock import patch, MagicMock
        >>> @patch("subprocess.run")
        ... def test_git_init(mock_run):
        ...     mock_run.return_value = MagicMock(returncode=0, stderr="")
        ...     # ... code that calls git init ...
        ...     assert verify_git_command(mock_run, ["git", "init"], cwd="/tmp/repo")
    """
    for call_args in mock_run.call_args_list:
        args, kwargs = call_args
        if args and args[0] == expected_args:
            if cwd is None or kwargs.get("cwd") == cwd:
                return True
    return False


def get_git_command_calls(mock_run: Any, command: str) -> List[Any]:
    """Extract all calls to a specific git command from a mock.

    Args:
        mock_run: The mocked subprocess.run object
        command: The git command to filter for (e.g., "init", "add", "commit")

    Returns:
        List of call objects matching the command

    Example:
        >>> from unittest.mock import patch, MagicMock
        >>> @patch("subprocess.run")
        ... def test_multiple_commits(mock_run):
        ...     # ... code that makes multiple git commits ...
        ...     commit_calls = get_git_command_calls(mock_run, "commit")
        ...     assert len(commit_calls) == 3
    """
    git_command = ["git", command]
    matching_calls = []

    for call_args in mock_run.call_args_list:
        args, kwargs = call_args
        if args and len(args[0]) >= 2:
            if args[0][:2] == git_command:
                matching_calls.append(call_args)

    return matching_calls


def assert_git_command_called(
    mock_run: Any,
    expected_args: List[str],
    message: str = ""
) -> None:
    """Assert that a git command was called with expected arguments.

    Args:
        mock_run: The mocked subprocess.run object
        expected_args: List of expected command arguments
        message: Optional custom error message

    Raises:
        AssertionError: If the command was not called with expected arguments

    Example:
        >>> from unittest.mock import patch, MagicMock
        >>> @patch("subprocess.run")
        ... def test_git_add(mock_run):
        ...     # ... code that calls git add ...
        ...     assert_git_command_called(mock_run, ["git", "add", "test.md"])
    """
    if not verify_git_command(mock_run, expected_args):
        actual_calls = [str(args[0]) for args, _ in mock_run.call_args_list if args]
        error_msg = (
            f"Expected git command {expected_args} was not called.\n"
            f"Actual calls: {actual_calls}"
        )
        if message:
            error_msg = f"{message}\n{error_msg}"
        raise AssertionError(error_msg)


def create_git_repo_with_file(
    filename: str,
    content: str,
    commit_message: str = "Initial commit"
) -> Path:
    """Create a git repository with a single committed file.

    This is a convenience function that combines create_temp_git_repo()
    and create_test_commit() for simple test scenarios.

    Args:
        filename: Name of the file to create
        content: Content to write to the file
        commit_message: Git commit message (default: "Initial commit")

    Returns:
        Path: Path to the temporary git repository directory

    Note:
        Caller is responsible for cleanup using cleanup_git_repo()

    Example:
        >>> repo_path = create_git_repo_with_file(
        ...     "README.md",
        ...     "# Test Repository"
        ... )
        >>> assert (repo_path / "README.md").exists()
        >>> cleanup_git_repo(repo_path)
    """
    repo_path = create_temp_git_repo()
    create_test_commit(repo_path, filename, content, commit_message)
    return repo_path


def get_file_at_commit(
    repo_path: Path,
    filename: str,
    commit_ref: str = "HEAD"
) -> str:
    """Get file content at a specific commit.

    Args:
        repo_path: Path to the git repository
        filename: Name of the file to retrieve
        commit_ref: Git commit reference (default: "HEAD")

    Returns:
        str: File content at the specified commit

    Raises:
        subprocess.CalledProcessError: If the file doesn't exist at that commit

    Example:
        >>> repo_path = create_temp_git_repo()
        >>> create_test_commit(repo_path, "test.md", "Version 1", "v1")
        >>> create_test_commit(repo_path, "test.md", "Version 2", "v2")
        >>> content = get_file_at_commit(repo_path, "test.md", "HEAD~1")
        >>> assert content == "Version 1"
    """
    result = subprocess.run(
        ["git", "show", f"{commit_ref}:{filename}"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout


def get_commit_sha(repo_path: Path, ref: str = "HEAD") -> str:
    """Get the SHA hash of a commit.

    Args:
        repo_path: Path to the git repository
        ref: Git reference (default: "HEAD")

    Returns:
        str: Full SHA hash of the commit

    Example:
        >>> repo_path = create_temp_git_repo()
        >>> create_test_commit(repo_path, "test.md", "Content", "Commit")
        >>> sha = get_commit_sha(repo_path)
        >>> assert len(sha) == 40
    """
    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()


def count_commits(repo_path: Path) -> int:
    """Count the number of commits in a repository.

    Args:
        repo_path: Path to the git repository

    Returns:
        int: Number of commits (0 if no commits exist)

    Example:
        >>> repo_path = create_temp_git_repo()
        >>> assert count_commits(repo_path) == 0
        >>> create_test_commit(repo_path, "test.md", "Content", "Commit")
        >>> assert count_commits(repo_path) == 1
    """
    result = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False  # Don't raise if no commits
    )

    if result.returncode != 0:
        return 0  # No commits yet

    return int(result.stdout.strip())


def find_commit_by_message(repo_path: Path, search_pattern: str) -> Optional[str]:
    """Find a commit SHA by searching commit messages.

    Args:
        repo_path: Path to the git repository
        search_pattern: Pattern to search for in commit messages (grep pattern)

    Returns:
        Optional[str]: SHA of the first matching commit, or None if not found

    Example:
        >>> repo_path = create_temp_git_repo()
        >>> create_test_commit(repo_path, "test.md", "v1", "Page 123: version 1")
        >>> sha = find_commit_by_message(repo_path, "version 1")
        >>> assert sha is not None
    """
    result = subprocess.run(
        ["git", "log", "--all", "--grep", search_pattern, "--format=%H", "-n", "1"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True
    )

    sha = result.stdout.strip()
    return sha if sha else None
