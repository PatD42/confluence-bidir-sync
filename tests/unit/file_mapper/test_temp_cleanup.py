"""Unit tests for temp directory cleanup in FileMapper.

Tests C3: Temp directory cleanup on all exit paths.
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.errors import FilesystemError
from src.confluence_client.auth import Authenticator


class TestTempDirectoryCleanup:
    """Test cases for temp directory cleanup (C3)."""

    @pytest.fixture
    def file_mapper(self, mocker):
        """Create a FileMapper instance with mocked authentication."""
        mock_auth = mocker.Mock(spec=Authenticator)
        mock_auth.get_credentials.return_value = mocker.Mock(
            url="https://test.atlassian.net/wiki",
            user="test@example.com",
            api_token="fake-token"
        )
        mapper = FileMapper(mock_auth)
        # Set base_path for validation
        mapper._base_path = "/fake/base"
        return mapper

    @pytest.fixture
    def temp_base_dir(self):
        """Create a temporary base directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_temp_directory_cleaned_on_success(self, file_mapper, temp_base_dir):
        """Verify temp directory is cleaned up after successful write."""
        # Setup
        test_file = os.path.join(temp_base_dir, "test.md")
        temp_dir = os.path.join(temp_base_dir, ".temp")
        files_to_write = [(test_file, "Test content")]

        # Set base_path for validation
        file_mapper._base_path = temp_base_dir

        # Execute
        file_mapper._write_files_atomic(files_to_write, temp_dir)

        # Verify temp directory was cleaned up
        assert not os.path.exists(temp_dir), "Temp directory should be cleaned up on success"
        # Verify final file was written
        assert os.path.exists(test_file)
        with open(test_file, 'r') as f:
            assert f.read() == "Test content"

    def test_temp_directory_cleaned_on_phase1_failure(self, file_mapper, temp_base_dir, mocker):
        """Verify temp directory is cleaned up when Phase 1 fails (CRITICAL TEST)."""
        # Setup
        test_file = os.path.join(temp_base_dir, "test.md")
        temp_dir = os.path.join(temp_base_dir, ".temp")
        files_to_write = [(test_file, "Test content")]

        # Set base_path for validation
        file_mapper._base_path = temp_base_dir

        # Mock open to raise exception during Phase 1
        original_open = open
        def mock_open(*args, **kwargs):
            if '.temp' in str(args[0]) and 'w' in args[1]:
                raise IOError("Simulated write failure")
            return original_open(*args, **kwargs)

        # Execute and expect failure
        with patch('builtins.open', side_effect=mock_open):
            with pytest.raises(FilesystemError) as exc_info:
                file_mapper._write_files_atomic(files_to_write, temp_dir)

            assert "Atomic write phase 1 failed" in str(exc_info.value)

        # Verify temp directory was cleaned up despite failure
        assert not os.path.exists(temp_dir), "Temp directory should be cleaned up on Phase 1 failure"

    def test_temp_directory_cleaned_on_phase2_failure(self, file_mapper, temp_base_dir, mocker):
        """Verify temp directory is cleaned up when Phase 2 fails."""
        # Setup
        test_file = os.path.join(temp_base_dir, "test.md")
        temp_dir = os.path.join(temp_base_dir, ".temp")
        files_to_write = [(test_file, "Test content")]

        # Set base_path for validation
        file_mapper._base_path = temp_base_dir

        # Mock shutil.move to raise exception during Phase 2
        with patch('shutil.move', side_effect=IOError("Simulated move failure")):
            with pytest.raises(FilesystemError) as exc_info:
                file_mapper._write_files_atomic(files_to_write, temp_dir)

            assert "Atomic write phase 2 failed" in str(exc_info.value)

        # Verify temp directory was cleaned up despite failure
        assert not os.path.exists(temp_dir), "Temp directory should be cleaned up on Phase 2 failure"

    def test_temp_directory_cleaned_on_validation_failure(self, file_mapper, temp_base_dir):
        """Verify temp directory is cleaned up when path validation fails."""
        # Setup - use a path that will fail validation
        malicious_file = os.path.join(temp_base_dir, "..", "malicious.md")
        temp_dir = os.path.join(temp_base_dir, ".temp")
        files_to_write = [(malicious_file, "Malicious content")]

        # Set base_path for validation
        file_mapper._base_path = temp_base_dir

        # Execute and expect failure due to path traversal
        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._write_files_atomic(files_to_write, temp_dir)

        assert "Path traversal detected" in str(exc_info.value)

        # Verify temp directory was cleaned up despite failure
        assert not os.path.exists(temp_dir), "Temp directory should be cleaned up on validation failure"

    def test_temp_directory_cleaned_on_mkdir_failure(self, file_mapper, temp_base_dir, mocker):
        """Verify temp directory is cleaned up when directory creation fails."""
        # Setup
        test_file = os.path.join(temp_base_dir, "subdir", "test.md")
        temp_dir = os.path.join(temp_base_dir, ".temp")
        files_to_write = [(test_file, "Test content")]

        # Set base_path for validation
        file_mapper._base_path = temp_base_dir

        # Mock os.makedirs to fail on the final directory creation
        original_makedirs = os.makedirs
        call_count = [0]

        def mock_makedirs(path, *args, **kwargs):
            call_count[0] += 1
            # Let the temp dir creation succeed, but fail on final dir
            if call_count[0] > 1 and 'subdir' in str(path):
                raise IOError("Simulated mkdir failure")
            return original_makedirs(path, *args, **kwargs)

        # Execute and expect failure
        with patch('os.makedirs', side_effect=mock_makedirs):
            with pytest.raises(FilesystemError) as exc_info:
                file_mapper._write_files_atomic(files_to_write, temp_dir)

            assert "Atomic write phase 2 failed" in str(exc_info.value)

        # Verify temp directory was cleaned up despite failure
        assert not os.path.exists(temp_dir), "Temp directory should be cleaned up on mkdir failure"

    def test_multiple_files_cleanup_on_partial_failure(self, file_mapper, temp_base_dir, mocker):
        """Verify all temp files cleaned up when one file fails mid-batch."""
        # Setup - multiple files where second one will fail
        test_file1 = os.path.join(temp_base_dir, "test1.md")
        test_file2 = os.path.join(temp_base_dir, "test2.md")
        test_file3 = os.path.join(temp_base_dir, "test3.md")
        temp_dir = os.path.join(temp_base_dir, ".temp")
        files_to_write = [
            (test_file1, "Content 1"),
            (test_file2, "Content 2"),
            (test_file3, "Content 3"),
        ]

        # Set base_path for validation
        file_mapper._base_path = temp_base_dir

        # Mock to fail on second file
        original_open = open
        call_count = [0]

        def mock_open(*args, **kwargs):
            if '.temp' in str(args[0]) and 'w' in args[1]:
                call_count[0] += 1
                if call_count[0] == 2:  # Fail on second file
                    raise IOError("Simulated write failure on file 2")
            return original_open(*args, **kwargs)

        # Execute and expect failure
        with patch('builtins.open', side_effect=mock_open):
            with pytest.raises(FilesystemError):
                file_mapper._write_files_atomic(files_to_write, temp_dir)

        # Verify temp directory was completely cleaned up
        assert not os.path.exists(temp_dir), "Temp directory should be cleaned up on partial failure"

    def test_cleanup_handles_permission_error_gracefully(self, file_mapper, temp_base_dir, mocker):
        """Verify cleanup handles permission errors without crashing."""
        # Setup
        test_file = os.path.join(temp_base_dir, "test.md")
        temp_dir = os.path.join(temp_base_dir, ".temp")
        files_to_write = [(test_file, "Test content")]

        # Set base_path for validation
        file_mapper._base_path = temp_base_dir

        # Mock rmtree to raise permission error
        original_rmtree = __import__('shutil').rmtree

        def mock_rmtree(path, *args, **kwargs):
            if '.temp' in str(path):
                raise PermissionError("Simulated permission error")
            return original_rmtree(path, *args, **kwargs)

        # Execute - should complete despite cleanup failure
        with patch('shutil.rmtree', side_effect=mock_rmtree):
            # Should not raise exception (cleanup error is logged but not raised)
            file_mapper._write_files_atomic(files_to_write, temp_dir)

        # File should still be written successfully
        assert os.path.exists(test_file)

    def test_empty_files_list_does_not_create_temp_dir(self, file_mapper, temp_base_dir):
        """Verify no temp directory is created when files list is empty."""
        temp_dir = os.path.join(temp_base_dir, ".temp")

        # Execute with empty list
        file_mapper._write_files_atomic([], temp_dir)

        # Verify no temp directory was created
        assert not os.path.exists(temp_dir)

    def test_cleanup_handles_nonexistent_temp_dir(self, file_mapper, temp_base_dir, mocker):
        """Verify cleanup handles case where temp dir was already deleted."""
        # Setup
        test_file = os.path.join(temp_base_dir, "test.md")
        temp_dir = os.path.join(temp_base_dir, ".temp")
        files_to_write = [(test_file, "Test content")]

        # Set base_path for validation
        file_mapper._base_path = temp_base_dir

        # Mock rmtree to delete dir before it's called again
        original_rmtree = __import__('shutil').rmtree

        def mock_rmtree(path, *args, **kwargs):
            # Delete the dir, then raise error to simulate race condition
            if os.path.exists(path):
                original_rmtree(path, *args, **kwargs)
            # Raise error as if dir doesn't exist
            raise FileNotFoundError(f"No such file or directory: {path}")

        # Execute - should complete gracefully
        with patch('shutil.rmtree', side_effect=mock_rmtree):
            file_mapper._write_files_atomic(files_to_write, temp_dir)

        # File should still be written successfully
        assert os.path.exists(test_file)
