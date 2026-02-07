"""Unit tests for file size limits in FileMapper.

Tests M1: Memory leak on large files - file size validation to prevent
memory exhaustion.
"""

import os
import pytest
import tempfile
from pathlib import Path

from src.file_mapper.file_mapper import FileMapper, MAX_FILE_SIZE
from src.file_mapper.errors import FilesystemError


class TestFileSizeLimits:
    """Test cases for file size validation (M1)."""

    @pytest.fixture
    def file_mapper(self):
        """Create a FileMapper instance."""
        return FileMapper()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_small_file_passes_validation(self, file_mapper, temp_dir):
        """Verify small files pass size validation."""
        # Create a small file (1 KB)
        test_file = temp_dir / "small.md"
        test_file.write_text("# Small File\n\n" + "x" * 1000)

        # Should not raise exception
        file_mapper._validate_file_size(str(test_file))

    def test_max_size_file_passes_validation(self, file_mapper, temp_dir):
        """Verify files at exactly max size pass validation."""
        # Create a file at exactly MAX_FILE_SIZE
        test_file = temp_dir / "max.md"
        test_file.write_bytes(b"x" * MAX_FILE_SIZE)

        # Should not raise exception
        file_mapper._validate_file_size(str(test_file))

    def test_oversized_file_rejected(self, file_mapper, temp_dir):
        """Verify oversized files are rejected (CRITICAL TEST)."""
        # Create a file larger than MAX_FILE_SIZE
        test_file = temp_dir / "large.md"
        test_file.write_bytes(b"x" * (MAX_FILE_SIZE + 1))

        # Should raise FilesystemError
        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._validate_file_size(str(test_file))

        error = exc_info.value
        assert "exceeds maximum allowed size" in str(error)
        assert "10 MB" in str(error)

    def test_very_large_file_rejected(self, file_mapper, temp_dir):
        """Verify very large files (>100MB) are rejected."""
        # Create a sparse file (100MB)
        test_file = temp_dir / "huge.md"
        with open(test_file, 'wb') as f:
            f.seek(100 * 1024 * 1024 - 1)
            f.write(b'\0')

        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._validate_file_size(str(test_file))

        assert "exceeds maximum allowed size" in str(exc_info.value)

    def test_custom_max_size(self, file_mapper, temp_dir):
        """Verify custom max size parameter works."""
        # Create a 2 MB file
        test_file = temp_dir / "medium.md"
        test_file.write_bytes(b"x" * (2 * 1024 * 1024))

        # Should pass with 5 MB limit
        file_mapper._validate_file_size(str(test_file), max_size=5 * 1024 * 1024)

        # Should fail with 1 MB limit
        with pytest.raises(FilesystemError):
            file_mapper._validate_file_size(str(test_file), max_size=1 * 1024 * 1024)

    def test_nonexistent_file_raises_error(self, file_mapper, temp_dir):
        """Verify nonexistent files raise appropriate error."""
        test_file = temp_dir / "nonexistent.md"

        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._validate_file_size(str(test_file))

        assert "Failed to check file size" in str(exc_info.value)

    def test_empty_file_passes(self, file_mapper, temp_dir):
        """Verify empty files pass validation."""
        test_file = temp_dir / "empty.md"
        test_file.touch()

        # Should not raise exception
        file_mapper._validate_file_size(str(test_file))

    def test_error_message_includes_size_info(self, file_mapper, temp_dir):
        """Verify error message includes helpful size information."""
        # Create 15 MB file
        test_file = temp_dir / "large.md"
        test_file.write_bytes(b"x" * (15 * 1024 * 1024))

        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._validate_file_size(str(test_file))

        error_msg = str(exc_info.value)
        # Should mention actual size (~15 MB)
        assert "15" in error_msg or "14.9" in error_msg  # Allow for rounding
        # Should mention max size (10 MB)
        assert "10 MB" in error_msg
        # Should mention the reason
        assert "memory exhaustion" in error_msg.lower()

    def test_max_file_size_constant_is_10mb(self):
        """Verify MAX_FILE_SIZE constant is set correctly."""
        assert MAX_FILE_SIZE == 10 * 1024 * 1024
        assert MAX_FILE_SIZE == 10485760  # 10 MB in bytes

    def test_boundary_cases(self, file_mapper, temp_dir):
        """Test files around the size boundary."""
        # Just under max size
        under_file = temp_dir / "under.md"
        under_file.write_bytes(b"x" * (MAX_FILE_SIZE - 1))
        file_mapper._validate_file_size(str(under_file))  # Should pass

        # Just over max size
        over_file = temp_dir / "over.md"
        over_file.write_bytes(b"x" * (MAX_FILE_SIZE + 1))
        with pytest.raises(FilesystemError):
            file_mapper._validate_file_size(str(over_file))  # Should fail
