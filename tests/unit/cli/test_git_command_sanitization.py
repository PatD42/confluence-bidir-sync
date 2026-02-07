"""Unit tests for git command sanitization in BaselineManager.

Tests H4: Git command sanitization to prevent injection attacks.
"""

import pytest
import tempfile
from pathlib import Path

from src.cli.baseline_manager import BaselineManager
from src.cli.errors import CLIError


class TestGitCommandSanitization:
    """Test cases for git command sanitization (H4)."""

    @pytest.fixture
    def temp_baseline_dir(self):
        """Create a temporary baseline directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def baseline_manager(self, temp_baseline_dir):
        """Create a BaselineManager instance with temp directory."""
        manager = BaselineManager(baseline_dir=temp_baseline_dir)
        manager.initialize()
        return manager

    def test_valid_numeric_page_id_accepted(self, baseline_manager):
        """Verify valid numeric page_id is accepted."""
        # Should not raise
        baseline_manager.update_baseline("123456", "# Test Content\n")

        # Verify content was saved
        content = baseline_manager.get_baseline_content("123456")
        assert content == "# Test Content\n"

    def test_command_injection_page_id_rejected(self, baseline_manager):
        """Verify page_id with command injection is rejected (CRITICAL TEST)."""
        malicious_page_id = "123; rm -rf /"

        with pytest.raises(CLIError) as exc_info:
            baseline_manager.update_baseline(malicious_page_id, "# Content")

        assert "Invalid page_id format" in str(exc_info.value)
        assert "must contain only numeric characters" in str(exc_info.value)

    def test_path_traversal_page_id_rejected(self, baseline_manager):
        """Verify page_id with path traversal is rejected."""
        malicious_page_id = "../../etc/passwd"

        with pytest.raises(CLIError) as exc_info:
            baseline_manager.update_baseline(malicious_page_id, "# Content")

        assert "Invalid page_id format" in str(exc_info.value)

    def test_script_injection_page_id_rejected(self, baseline_manager):
        """Verify page_id with script tag is rejected."""
        malicious_page_id = "<script>alert('xss')</script>"

        with pytest.raises(CLIError) as exc_info:
            baseline_manager.update_baseline(malicious_page_id, "# Content")

        assert "Invalid page_id format" in str(exc_info.value)

    def test_sql_injection_page_id_rejected(self, baseline_manager):
        """Verify page_id with SQL injection is rejected."""
        malicious_page_id = "123' OR '1'='1"

        with pytest.raises(CLIError) as exc_info:
            baseline_manager.update_baseline(malicious_page_id, "# Content")

        assert "Invalid page_id format" in str(exc_info.value)

    def test_null_byte_page_id_rejected(self, baseline_manager):
        """Verify page_id with null byte is rejected."""
        malicious_page_id = "123\\x00../../etc/passwd"

        with pytest.raises(CLIError) as exc_info:
            baseline_manager.update_baseline(malicious_page_id, "# Content")

        assert "Invalid page_id format" in str(exc_info.value)

    def test_empty_page_id_rejected(self, baseline_manager):
        """Verify empty page_id is rejected."""
        with pytest.raises(CLIError) as exc_info:
            baseline_manager.update_baseline("", "# Content")

        assert "page_id cannot be empty" in str(exc_info.value)

    def test_whitespace_only_page_id_rejected(self, baseline_manager):
        """Verify whitespace-only page_id is rejected."""
        with pytest.raises(CLIError) as exc_info:
            baseline_manager.update_baseline("   ", "# Content")

        assert "page_id cannot be empty" in str(exc_info.value)

    def test_alphanumeric_page_id_rejected(self, baseline_manager):
        """Verify alphanumeric page_id is rejected (only numeric allowed)."""
        with pytest.raises(CLIError) as exc_info:
            baseline_manager.update_baseline("page123", "# Content")

        assert "Invalid page_id format" in str(exc_info.value)

    def test_special_characters_page_id_rejected(self, baseline_manager):
        """Verify page_id with special characters is rejected."""
        special_chars = ["123-456", "123_456", "123.456", "123@456", "123#456"]

        for page_id in special_chars:
            with pytest.raises(CLIError) as exc_info:
                baseline_manager.update_baseline(page_id, "# Content")

            assert "Invalid page_id format" in str(exc_info.value)

    def test_validation_in_get_baseline_content(self, baseline_manager):
        """Verify validation also applies to get_baseline_content."""
        malicious_page_id = "123; cat /etc/passwd"

        with pytest.raises(CLIError) as exc_info:
            baseline_manager.get_baseline_content(malicious_page_id)

        assert "Invalid page_id format" in str(exc_info.value)

    def test_validation_in_merge_file(self, baseline_manager):
        """Verify validation also applies to merge_file."""
        malicious_page_id = "123 && rm -rf /"

        with pytest.raises(CLIError) as exc_info:
            baseline_manager.merge_file(
                baseline_content="# Base",
                local_content="# Local",
                remote_content="# Remote",
                page_id=malicious_page_id
            )

        assert "Invalid page_id format" in str(exc_info.value)

    def test_large_numeric_page_id_accepted(self, baseline_manager):
        """Verify large numeric page_id is accepted."""
        large_page_id = "9" * 20  # 20-digit number

        # Should not raise
        baseline_manager.update_baseline(large_page_id, "# Test")

        content = baseline_manager.get_baseline_content(large_page_id)
        assert content == "# Test"

    def test_leading_zeros_page_id_accepted(self, baseline_manager):
        """Verify page_id with leading zeros is accepted."""
        page_id_with_zeros = "00123456"

        # Should not raise
        baseline_manager.update_baseline(page_id_with_zeros, "# Test")

        content = baseline_manager.get_baseline_content(page_id_with_zeros)
        assert content == "# Test"
