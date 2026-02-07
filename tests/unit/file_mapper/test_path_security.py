"""Unit tests for path traversal security in FileMapper.

Tests C1: Path traversal vulnerability protection.
"""

import os
import pytest
import tempfile
from pathlib import Path

from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.errors import FilesystemError
from src.confluence_client.auth import Authenticator


class TestPathTraversalProtection:
    """Test cases for path traversal security (C1)."""

    @pytest.fixture
    def file_mapper(self, mock_authenticator):
        """Create a FileMapper instance with mocked authentication."""
        return FileMapper(mock_authenticator)

    @pytest.fixture
    def mock_authenticator(self, mocker):
        """Mock authenticator to avoid real API calls."""
        mock_auth = mocker.Mock(spec=Authenticator)
        mock_auth.get_credentials.return_value = mocker.Mock(
            url="https://test.atlassian.net/wiki",
            user="test@example.com",
            token="fake-token"
        )
        return mock_auth

    @pytest.fixture
    def temp_base_dir(self):
        """Create a temporary base directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_validate_path_within_base_directory(self, file_mapper, temp_base_dir):
        """Verify that valid paths within base directory are accepted."""
        # Create a file within the base directory
        valid_file = os.path.join(temp_base_dir, "valid.md")

        # Should not raise any exception
        file_mapper._validate_path_safety(valid_file, temp_base_dir)

    def test_validate_nested_path_within_base_directory(self, file_mapper, temp_base_dir):
        """Verify that nested paths within base directory are accepted."""
        # Create nested path
        nested_file = os.path.join(temp_base_dir, "subdir", "nested.md")

        # Should not raise any exception
        file_mapper._validate_path_safety(nested_file, temp_base_dir)

    def test_reject_path_traversal_with_dotdot(self, file_mapper, temp_base_dir):
        """Verify that path traversal using ../ is rejected (CRITICAL TEST)."""
        # Attempt path traversal: ../../etc/passwd
        traversal_path = os.path.join(temp_base_dir, "..", "..", "etc", "passwd")

        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._validate_path_safety(traversal_path, temp_base_dir)

        assert "Path traversal detected" in str(exc_info.value)
        assert "outside base directory" in str(exc_info.value)

    def test_reject_absolute_path_outside_base(self, file_mapper, temp_base_dir):
        """Verify that absolute paths outside base directory are rejected."""
        # Try to access /etc/passwd directly
        malicious_path = "/etc/passwd"

        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._validate_path_safety(malicious_path, temp_base_dir)

        assert "Path traversal detected" in str(exc_info.value)

    def test_reject_path_with_symlink_outside_base(self, file_mapper, temp_base_dir):
        """Verify that symlinks pointing outside base directory are rejected."""
        # Create a symlink pointing outside the base directory
        symlink_path = os.path.join(temp_base_dir, "malicious_link.md")
        target_path = "/etc/passwd"

        try:
            os.symlink(target_path, symlink_path)

            with pytest.raises(FilesystemError) as exc_info:
                file_mapper._validate_path_safety(symlink_path, temp_base_dir)

            assert "Path traversal detected" in str(exc_info.value)
        except OSError:
            # Symlink creation may fail on some systems (Windows)
            pytest.skip("Symlink creation not supported on this system")

    def test_validate_path_with_relative_components_within_base(self, file_mapper, temp_base_dir):
        """Verify that relative paths that resolve within base are accepted."""
        # Create: base/a/b/../../c/file.md which resolves to base/c/file.md
        # This should be valid as it stays within base
        relative_path = os.path.join(temp_base_dir, "a", "b", "..", "..", "c", "file.md")

        # Should not raise exception as it resolves within base
        file_mapper._validate_path_safety(relative_path, temp_base_dir)

    def test_read_local_files_rejects_traversal_attack(self, file_mapper, temp_base_dir, mocker):
        """Integration test: _read_local_files() rejects path traversal."""
        # Create a markdown file with traversal path
        # Note: We can't actually create ../../etc/passwd, but we can test the validation

        # Mock os.walk to return a malicious path
        malicious_path = os.path.join(temp_base_dir, "..", "..", "etc", "passwd.md")
        mocker.patch('os.walk', return_value=[
            (temp_base_dir, [], ['test.md'])
        ])
        mocker.patch('os.path.join', return_value=malicious_path)

        # Set base path
        file_mapper._base_path = temp_base_dir

        # Should log warning and continue (not crash)
        result = file_mapper._read_local_files(temp_base_dir)

        # The malicious file should be skipped (not in results)
        assert len(result) == 0

    def test_write_files_atomic_rejects_traversal_attack(self, file_mapper, temp_base_dir):
        """Integration test: _write_files_atomic() rejects path traversal."""
        # Set base path
        file_mapper._base_path = temp_base_dir

        # Attempt to write to path outside base directory
        malicious_path = os.path.join(temp_base_dir, "..", "..", "etc", "malicious.md")
        files_to_write = [(malicious_path, "malicious content")]

        temp_dir = os.path.join(temp_base_dir, ".temp")

        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._write_files_atomic(files_to_write, temp_dir)

        assert "Path traversal detected" in str(exc_info.value)

    def test_multiple_traversal_attempts(self, file_mapper, temp_base_dir):
        """Test various creative path traversal attempts are blocked."""
        traversal_attempts = [
            os.path.join(temp_base_dir, "..", "secret.md"),
            os.path.join(temp_base_dir, "..", "..", "secret.md"),
            os.path.join(temp_base_dir, "..", "..", "..", "etc", "passwd"),
            os.path.join(temp_base_dir, "subdir", "..", "..", "secret.md"),
        ]

        for attempt in traversal_attempts:
            with pytest.raises(FilesystemError) as exc_info:
                file_mapper._validate_path_safety(attempt, temp_base_dir)

            assert "Path traversal detected" in str(exc_info.value), \
                f"Failed to detect traversal in: {attempt}"
