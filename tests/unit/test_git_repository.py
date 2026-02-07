"""Unit tests for git_integration.git_repository module."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest

from src.git_integration.errors import GitRepositoryError
from src.git_integration.git_repository import GitRepository, GIT_TIMEOUT


class TestGitRepositoryInit:
    """Test cases for GitRepository initialization and repo setup."""

    @patch("builtins.open", create=True)
    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_init_creates_repo(self, mock_makedirs, mock_exists, mock_run, mock_open):
        """UT-GR-01: init_if_not_exists should initialize git repo and create README."""
        # Arrange
        mock_exists.return_value = False  # .git doesn't exist
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        mock_open.return_value.__enter__.return_value = MagicMock()
        repo = GitRepository("/tmp/test_repo")

        # Act
        repo.init_if_not_exists()

        # Assert
        mock_makedirs.assert_called_once()

        # Verify git init was called
        git_init_calls = [c for c in mock_run.call_args_list if c[0][0][0:2] == ["git", "init"]]
        assert len(git_init_calls) == 1
        assert git_init_calls[0][1]["cwd"] == repo.repo_path

        # Verify README.md was created and committed
        git_add_readme = [c for c in mock_run.call_args_list if "README.md" in str(c)]
        assert len(git_add_readme) >= 1

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_init_skips_if_exists(self, mock_exists, mock_run):
        """UT-GR-02: init_if_not_exists should skip if .git directory exists."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_exists.return_value = True  # .git exists

        # Act
        repo.init_if_not_exists()

        # Assert - git init should NOT be called
        mock_run.assert_not_called()

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_init_handles_git_init_failure(self, mock_makedirs, mock_exists, mock_run):
        """init_if_not_exists should raise GitRepositoryError on git init failure."""
        # Arrange
        mock_exists.return_value = False
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="fatal: not a git repository",
            stdout=""
        )
        repo = GitRepository("/tmp/test_repo")

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            repo.init_if_not_exists()

        assert "Failed to initialize git repository" in str(exc_info.value)
        assert exc_info.value.repo_path == repo.repo_path

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_init_handles_timeout(self, mock_makedirs, mock_exists, mock_run):
        """UT-GR-08: init_if_not_exists should raise GitRepositoryError on timeout."""
        # Arrange
        mock_exists.return_value = False
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["git", "init"],
            timeout=GIT_TIMEOUT
        )
        repo = GitRepository("/tmp/test_repo")

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            repo.init_if_not_exists()

        assert f"timed out after {GIT_TIMEOUT} seconds" in str(exc_info.value)


class TestCommitVersion:
    """Test cases for commit_version method."""

    @patch("subprocess.run")
    @patch("builtins.open", create=True)
    def test_commit_version(self, mock_open, mock_run):
        """UT-GR-03: commit_version should write file, git add, and git commit."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")

        # Mock successful git add and git commit
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr="", stdout=""),  # git add
            MagicMock(returncode=0, stderr="", stdout=""),  # git commit
            MagicMock(returncode=0, stderr="", stdout="abc123def456"),  # git rev-parse HEAD
        ]

        mock_file_handle = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file_handle

        # Act
        sha = repo.commit_version(
            page_id="123456",
            markdown="# Test Page",
            version=15
        )

        # Assert
        # Verify file was written
        mock_file_handle.write.assert_called_once_with("# Test Page")

        # Verify git add was called with correct file
        add_call = mock_run.call_args_list[0]
        assert add_call[0][0] == ["git", "add", "123456.md"]
        assert add_call[1]["cwd"] == repo.repo_path
        assert add_call[1]["timeout"] == GIT_TIMEOUT

        # Verify git commit was called with correct message
        commit_call = mock_run.call_args_list[1]
        assert commit_call[0][0] == ["git", "commit", "-m", "Page 123456: version 15"]
        assert commit_call[1]["cwd"] == repo.repo_path

        # Verify SHA was returned
        assert sha == "abc123def456"

    @patch("subprocess.run")
    @patch("builtins.open", create=True)
    def test_commit_version_with_custom_message(self, mock_open, mock_run):
        """commit_version should accept custom commit message."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr="", stdout=""),  # git add
            MagicMock(returncode=0, stderr="", stdout=""),  # git commit
            MagicMock(returncode=0, stderr="", stdout="sha123"),  # git rev-parse
        ]
        mock_open.return_value.__enter__.return_value = MagicMock()

        # Act
        repo.commit_version(
            page_id="123456",
            markdown="content",
            version=1,
            message="Custom commit message"
        )

        # Assert
        commit_call = mock_run.call_args_list[1]
        assert commit_call[0][0] == ["git", "commit", "-m", "Custom commit message"]

    @patch("subprocess.run")
    @patch("builtins.open", create=True)
    def test_commit_version_handles_failure(self, mock_open, mock_run):
        """UT-GR-09: commit_version should raise GitRepositoryError on git failure."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_open.return_value.__enter__.return_value = MagicMock()

        # git add succeeds, git commit fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr="", stdout=""),  # git add
            MagicMock(returncode=1, stderr="fatal: unable to commit", stdout=""),  # git commit
        ]

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            repo.commit_version("123456", "# Test", 1)

        assert "Failed to commit" in str(exc_info.value)
        assert exc_info.value.git_output == "fatal: unable to commit"

    @patch("subprocess.run")
    @patch("builtins.open", create=True)
    def test_commit_version_handles_timeout(self, mock_open, mock_run):
        """commit_version should raise GitRepositoryError on timeout."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_open.return_value.__enter__.return_value = MagicMock()

        # git add times out
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["git", "add"],
            timeout=GIT_TIMEOUT
        )

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            repo.commit_version("123456", "# Test", 1)

        assert "timed out" in str(exc_info.value)

    @patch("subprocess.run")
    @patch("builtins.open", create=True)
    def test_commit_version_nothing_to_commit(self, mock_open, mock_run):
        """commit_version should handle 'nothing to commit' gracefully."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_open.return_value.__enter__.return_value = MagicMock()

        # git add succeeds, git commit says nothing to commit
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr="", stdout=""),  # git add
            MagicMock(returncode=1, stderr="nothing to commit, working tree clean", stdout=""),  # git commit
            MagicMock(returncode=0, stderr="", stdout="current_sha"),  # git rev-parse HEAD
        ]

        # Act
        sha = repo.commit_version("123456", "# Test", 1)

        # Assert - should return current HEAD SHA
        assert sha == "current_sha"


class TestGetVersion:
    """Test cases for get_version method."""

    @patch("subprocess.run")
    def test_get_version_found(self, mock_run):
        """UT-GR-04: get_version should call git log and return markdown content."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")

        # Mock git log to find commit, then git show to get content
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr="", stdout="abc123def456\n"),  # git log
            MagicMock(returncode=0, stderr="", stdout="# Test Content\n\nBody text"),  # git show
        ]

        # Act
        content = repo.get_version("123456", 15)

        # Assert
        assert content == "# Test Content\n\nBody text"

        # Verify git log was called correctly
        log_call = mock_run.call_args_list[0]
        assert "git" in log_call[0][0]
        assert "log" in log_call[0][0]
        assert "--grep" in log_call[0][0]
        assert "Page 123456: version 15" in log_call[0][0]

        # Verify git show was called with commit SHA
        show_call = mock_run.call_args_list[1]
        assert show_call[0][0] == ["git", "show", "abc123def456:123456.md"]

    @patch("subprocess.run")
    def test_get_version_not_found(self, mock_run):
        """UT-GR-05: get_version should return None when version not found."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")

        # Mock git log returning empty (no matching commit)
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        # Act
        content = repo.get_version("123456", 999)

        # Assert
        assert content is None

    @patch("subprocess.run")
    def test_get_version_file_not_at_commit(self, mock_run):
        """get_version should return None if file doesn't exist at commit."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")

        # Mock git log finds commit, but git show fails (file not at that commit)
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr="", stdout="abc123\n"),  # git log
            MagicMock(returncode=128, stderr="fatal: path not in commit", stdout=""),  # git show
        ]

        # Act
        content = repo.get_version("123456", 15)

        # Assert
        assert content is None

    @patch("subprocess.run")
    def test_get_version_git_log_failure(self, mock_run):
        """get_version should raise GitRepositoryError on git log failure."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="fatal: not a git repository",
            stdout=""
        )

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            repo.get_version("123456", 15)

        assert "Failed to search git log" in str(exc_info.value)

    @patch("subprocess.run")
    def test_get_version_timeout(self, mock_run):
        """get_version should raise GitRepositoryError on timeout."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["git", "log"],
            timeout=GIT_TIMEOUT
        )

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            repo.get_version("123456", 15)

        assert "timed out" in str(exc_info.value)


class TestGetLatestVersionNumber:
    """Test cases for get_latest_version_number method."""

    @patch("subprocess.run")
    def test_get_latest_version_number(self, mock_run):
        """UT-GR-10: get_latest_version_number should parse commit messages and return highest."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")

        # Mock git log returning multiple commit messages
        mock_run.return_value = MagicMock(
            returncode=0,
            stderr="",
            stdout="Page 123456: version 5\nPage 123456: version 3\nPage 123456: version 10\n"
        )

        # Act
        latest = repo.get_latest_version_number("123456")

        # Assert
        assert latest == 10

        # Verify git log was called with correct grep pattern
        call_args = mock_run.call_args[0][0]
        assert "git" in call_args
        assert "log" in call_args
        assert "--grep" in call_args
        assert "Page 123456: version" in call_args

    @patch("subprocess.run")
    def test_get_latest_version_number_no_commits(self, mock_run):
        """get_latest_version_number should return None when no commits found."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        # Act
        latest = repo.get_latest_version_number("123456")

        # Assert
        assert latest is None

    @patch("subprocess.run")
    def test_get_latest_version_number_no_matching_pattern(self, mock_run):
        """get_latest_version_number should return None if no version numbers found."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")

        # Mock git log returning commits but not matching version pattern
        mock_run.return_value = MagicMock(
            returncode=0,
            stderr="",
            stdout="Initial commit\nSome other commit\n"
        )

        # Act
        latest = repo.get_latest_version_number("123456")

        # Assert
        assert latest is None

    @patch("subprocess.run")
    def test_get_latest_version_number_single_version(self, mock_run):
        """get_latest_version_number should work with single version."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.return_value = MagicMock(
            returncode=0,
            stderr="",
            stdout="Page 123456: version 42\n"
        )

        # Act
        latest = repo.get_latest_version_number("123456")

        # Assert
        assert latest == 42

    @patch("subprocess.run")
    def test_get_latest_version_number_git_failure(self, mock_run):
        """get_latest_version_number should raise GitRepositoryError on git failure."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="fatal: not a git repository",
            stdout=""
        )

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            repo.get_latest_version_number("123456")

        assert "Failed to get version history" in str(exc_info.value)

    @patch("subprocess.run")
    def test_get_latest_version_number_timeout(self, mock_run):
        """get_latest_version_number should raise GitRepositoryError on timeout."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["git", "log"],
            timeout=GIT_TIMEOUT
        )

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            repo.get_latest_version_number("123456")

        assert "timed out" in str(exc_info.value)


class TestValidateRepo:
    """Test cases for validate_repo method."""

    @patch("subprocess.run")
    def test_validate_repo_valid(self, mock_run):
        """UT-GR-06: validate_repo should return True when git fsck exits 0."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        # Act
        is_valid = repo.validate_repo()

        # Assert
        assert is_valid is True

        # Verify git fsck was called
        call_args = mock_run.call_args[0][0]
        assert call_args == ["git", "fsck", "--no-progress"]
        assert mock_run.call_args[1]["cwd"] == repo.repo_path
        assert mock_run.call_args[1]["timeout"] == GIT_TIMEOUT * 3

    @patch("subprocess.run")
    def test_validate_repo_invalid(self, mock_run):
        """UT-GR-07: validate_repo should return False when git fsck exits non-zero."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="error: corrupt commit",
            stdout=""
        )

        # Act
        is_valid = repo.validate_repo()

        # Assert
        assert is_valid is False

    @patch("subprocess.run")
    def test_validate_repo_timeout(self, mock_run):
        """validate_repo should return False on timeout."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["git", "fsck"],
            timeout=GIT_TIMEOUT * 3
        )

        # Act
        is_valid = repo.validate_repo()

        # Assert
        assert is_valid is False

    @patch("subprocess.run")
    def test_validate_repo_exception(self, mock_run):
        """validate_repo should return False on unexpected exception."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.side_effect = Exception("Unexpected error")

        # Act
        is_valid = repo.validate_repo()

        # Assert
        assert is_valid is False


class TestGitRepositoryMisc:
    """Test cases for miscellaneous GitRepository methods."""

    def test_ensure_absolute_path_relative(self):
        """GitRepository should convert relative paths to absolute."""
        # Arrange & Act
        repo = GitRepository("relative/path")

        # Assert
        assert os.path.isabs(repo.repo_path)
        assert repo.repo_path.endswith("relative/path")

    def test_ensure_absolute_path_already_absolute(self):
        """GitRepository should keep absolute paths unchanged."""
        # Arrange & Act
        repo = GitRepository("/absolute/path")

        # Assert
        assert repo.repo_path == "/absolute/path"

    @patch("subprocess.run")
    def test_get_head_sha(self, mock_run):
        """_get_head_sha should return current commit SHA."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.return_value = MagicMock(
            returncode=0,
            stderr="",
            stdout="abc123def456789\n"
        )

        # Act
        sha = repo._get_head_sha()

        # Assert
        assert sha == "abc123def456789"
        call_args = mock_run.call_args[0][0]
        assert call_args == ["git", "rev-parse", "HEAD"]

    @patch("subprocess.run")
    def test_get_head_sha_failure(self, mock_run):
        """_get_head_sha should raise GitRepositoryError on failure."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.return_value = MagicMock(
            returncode=128,
            stderr="fatal: not a git repository",
            stdout=""
        )

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            repo._get_head_sha()

        assert "Failed to get HEAD SHA" in str(exc_info.value)

    @patch("subprocess.run")
    def test_get_head_sha_timeout(self, mock_run):
        """_get_head_sha should raise GitRepositoryError on timeout."""
        # Arrange
        repo = GitRepository("/tmp/test_repo")
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["git", "rev-parse"],
            timeout=GIT_TIMEOUT
        )

        # Act & Assert
        with pytest.raises(GitRepositoryError) as exc_info:
            repo._get_head_sha()

        assert "timed out" in str(exc_info.value)
