"""Typed exception hierarchy for git integration errors.

This module defines all custom exceptions used by the git integration module.
All exceptions inherit from ConfluenceError base class for easy catching and
include descriptive messages with context to help with debugging.
"""

from typing import TYPE_CHECKING

from src.confluence_client.errors import SyncError

if TYPE_CHECKING:
    from src.git_integration.models import ConflictInfo


class GitRepositoryError(SyncError):
    """Raised when git repository operations fail.

    Attributes:
        repo_path: Path to git repository
        message: Error description
        git_output: Git command stderr output
    """

    def __init__(self, repo_path: str, message: str, git_output: str = ""):
        super().__init__(f"Git repository error at {repo_path}: {message}")
        self.repo_path = repo_path
        self.message = message
        self.git_output = git_output


class MergeConflictError(SyncError):
    """Raised when merge conflicts are detected and unresolved.

    Attributes:
        conflicts: List of ConflictInfo for unresolved conflicts
    """

    def __init__(self, conflicts: list["ConflictInfo"]):
        page_ids = ", ".join([c.page_id for c in conflicts])
        super().__init__(f"Unresolved merge conflicts for pages: {page_ids}")
        self.conflicts = conflicts


class MergeToolError(SyncError):
    """Raised when merge tool fails to launch or execute.

    Attributes:
        tool_name: Name of merge tool
        error: Error description
    """

    def __init__(self, tool_name: str, error: str):
        super().__init__(f"Merge tool '{tool_name}' failed: {error}")
        self.tool_name = tool_name
        self.error = error


class CacheError(SyncError):
    """Raised when cache operations fail.

    Attributes:
        cache_path: Path to cache file
        message: Error description
    """

    def __init__(self, cache_path: str, message: str):
        super().__init__(f"Cache error at {cache_path}: {message}")
        self.cache_path = cache_path
        self.message = message
