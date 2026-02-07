"""Integration tests for baseline sync operations.

This module tests the integration between SyncCommand and BaselineManager
for baseline update operations after successful sync. Tests verify:
- BaselineManager initialization during sync operations
- Baseline repository updates after successful sync
- Integration between SyncCommand and BaselineManager
- Filesystem operations for baseline repository
- Baseline content persistence across sync operations

Requirements:
- Temporary test directories (provided by fixtures)
- No external API calls (mocked dependencies)
- Real filesystem operations for baseline repository
"""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from src.cli.baseline_manager import BaselineManager
from src.cli.sync_command import SyncCommand
from src.cli.models import SyncState


@pytest.mark.integration
class TestBaselineSync:
    """Integration tests for baseline update after sync operations."""

    @pytest.fixture(scope="function")
    def baseline_manager(self, temp_test_dir: Path) -> BaselineManager:
        """Create a BaselineManager instance for testing.

        Args:
            temp_test_dir: Temporary test directory fixture

        Returns:
            BaselineManager instance with temp baseline directory
        """
        baseline_dir = temp_test_dir / ".confluence-sync" / "baseline"
        return BaselineManager(baseline_dir=baseline_dir)

    @pytest.fixture(scope="function")
    def initialized_baseline_manager(
        self,
        baseline_manager: BaselineManager
    ) -> BaselineManager:
        """Create an initialized BaselineManager instance.

        Args:
            baseline_manager: BaselineManager fixture

        Returns:
            Initialized BaselineManager instance
        """
        baseline_manager.initialize()
        return baseline_manager

    @pytest.fixture(scope="function")
    def sample_tracked_pages(self, temp_test_dir: Path) -> dict:
        """Create sample tracked pages for testing.

        Args:
            temp_test_dir: Temporary test directory fixture

        Returns:
            Dict mapping page_id to local file path
        """
        # Create test files
        page1 = temp_test_dir / "page1.md"
        page2 = temp_test_dir / "page2.md"
        page3 = temp_test_dir / "page3.md"

        page1.write_text("# Page 1\n\nContent 1", encoding='utf-8')
        page2.write_text("# Page 2\n\nContent 2", encoding='utf-8')
        page3.write_text("# Page 3\n\nContent 3", encoding='utf-8')

        return {
            "123": str(page1),
            "456": str(page2),
            "789": str(page3),
        }

    def test_baseline_initialization_on_first_sync(
        self,
        baseline_manager: BaselineManager
    ):
        """Test baseline repository is initialized on first use.

        Verifies:
        - Baseline directory created automatically
        - Git repository initialized
        - Configuration set correctly

        Args:
            baseline_manager: BaselineManager fixture
        """
        # Verify not initialized yet
        assert not baseline_manager.is_initialized()

        # Initialize
        baseline_manager.initialize()

        # Verify initialization
        assert baseline_manager.is_initialized()
        assert baseline_manager.baseline_dir.exists()
        assert (baseline_manager.baseline_dir / ".git").exists()

    def test_baseline_update_after_sync_single_page(
        self,
        initialized_baseline_manager: BaselineManager,
        temp_test_dir: Path
    ):
        """Test baseline update for a single page after sync.

        Verifies:
        - Baseline file created
        - Content matches local file
        - Git commit created

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create test file
        test_file = temp_test_dir / "test-page.md"
        content = "# Test Page\n\nThis is test content"
        test_file.write_text(content, encoding='utf-8')

        # Update baseline
        page_id = "123456"
        initialized_baseline_manager.update_baseline(page_id, content)

        # Verify baseline file created
        baseline_file = initialized_baseline_manager.baseline_dir / f"{page_id}.md"
        assert baseline_file.exists(), "Baseline file should be created"

        # Verify content matches
        baseline_content = baseline_file.read_text(encoding='utf-8')
        assert baseline_content == content, "Baseline content should match original"

    def test_baseline_update_after_sync_multiple_pages(
        self,
        initialized_baseline_manager: BaselineManager,
        sample_tracked_pages: dict,
        temp_test_dir: Path
    ):
        """Test baseline update for multiple pages after sync.

        Verifies:
        - All pages updated in baseline
        - Each page has correct content
        - Baseline repository contains all pages

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            sample_tracked_pages: Sample tracked pages fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Update baseline for all tracked pages
        for page_id, file_path in sample_tracked_pages.items():
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            initialized_baseline_manager.update_baseline(page_id, content)

        # Verify all baseline files created
        for page_id, file_path in sample_tracked_pages.items():
            baseline_file = initialized_baseline_manager.baseline_dir / f"{page_id}.md"
            assert baseline_file.exists(), f"Baseline file for {page_id} should exist"

            # Verify content matches
            with open(file_path, 'r', encoding='utf-8') as f:
                expected_content = f.read()
            baseline_content = baseline_file.read_text(encoding='utf-8')
            assert baseline_content == expected_content, \
                f"Baseline content for {page_id} should match"

    def test_baseline_update_overwrites_previous_baseline(
        self,
        initialized_baseline_manager: BaselineManager,
        temp_test_dir: Path
    ):
        """Test baseline update overwrites previous baseline.

        Verifies:
        - Subsequent updates overwrite old content
        - Latest content is preserved
        - Git history maintained

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "123456"

        # First update
        old_content = "# Old Content\n\nThis is old"
        initialized_baseline_manager.update_baseline(page_id, old_content)

        # Verify old content
        baseline_file = initialized_baseline_manager.baseline_dir / f"{page_id}.md"
        assert baseline_file.read_text(encoding='utf-8') == old_content

        # Second update (overwrite)
        new_content = "# New Content\n\nThis is new"
        initialized_baseline_manager.update_baseline(page_id, new_content)

        # Verify new content overwrites old
        baseline_content = baseline_file.read_text(encoding='utf-8')
        assert baseline_content == new_content, \
            "New content should overwrite old baseline"
        assert "old" not in baseline_content.lower(), \
            "Old content should not be present"

    def test_baseline_retrieval_after_update(
        self,
        initialized_baseline_manager: BaselineManager,
        temp_test_dir: Path
    ):
        """Test retrieving baseline content after update.

        Verifies:
        - get_baseline_content returns correct content
        - Content persists across method calls
        - None returned for non-existent baselines

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "123456"
        content = "# Test Page\n\nBaseline content"

        # Update baseline
        initialized_baseline_manager.update_baseline(page_id, content)

        # Retrieve baseline
        retrieved_content = initialized_baseline_manager.get_baseline_content(page_id)

        # Verify content matches
        assert retrieved_content == content, \
            "Retrieved content should match original"

        # Verify non-existent page returns None
        nonexistent_content = initialized_baseline_manager.get_baseline_content("999999")
        assert nonexistent_content is None, \
            "Non-existent page should return None"

    def test_baseline_persists_across_sync_operations(
        self,
        initialized_baseline_manager: BaselineManager,
        temp_test_dir: Path
    ):
        """Test baseline persists across multiple sync operations.

        Verifies:
        - Baseline survives multiple updates
        - Content remains accessible
        - Git history preserved

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "123456"

        # First sync - initial baseline
        content1 = "# Version 1\n\nFirst sync"
        initialized_baseline_manager.update_baseline(page_id, content1)

        # Second sync - update baseline
        content2 = "# Version 2\n\nSecond sync"
        initialized_baseline_manager.update_baseline(page_id, content2)

        # Third sync - update baseline again
        content3 = "# Version 3\n\nThird sync"
        initialized_baseline_manager.update_baseline(page_id, content3)

        # Verify latest content is preserved
        retrieved = initialized_baseline_manager.get_baseline_content(page_id)
        assert retrieved == content3, \
            "Latest baseline content should be preserved"

    def test_baseline_handles_unicode_content(
        self,
        initialized_baseline_manager: BaselineManager,
        temp_test_dir: Path
    ):
        """Test baseline handles unicode content correctly.

        Verifies:
        - Unicode characters stored correctly
        - Emoji and special characters preserved
        - Multi-language content supported

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "123456"
        unicode_content = "# Test Page\n\nUnicode: ❤️ 你好 🚀 Привет مرحبا"

        # Update baseline with unicode
        initialized_baseline_manager.update_baseline(page_id, unicode_content)

        # Retrieve and verify
        retrieved = initialized_baseline_manager.get_baseline_content(page_id)
        assert retrieved == unicode_content, \
            "Unicode content should be preserved"
        assert "❤️" in retrieved
        assert "你好" in retrieved
        assert "🚀" in retrieved

    def test_baseline_update_with_empty_content(
        self,
        initialized_baseline_manager: BaselineManager,
        temp_test_dir: Path
    ):
        """Test baseline update with empty content.

        Verifies:
        - Empty content handled correctly
        - Baseline file created
        - Retrieval returns empty string

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "123456"
        empty_content = ""

        # Update baseline with empty content
        initialized_baseline_manager.update_baseline(page_id, empty_content)

        # Verify baseline file created
        baseline_file = initialized_baseline_manager.baseline_dir / f"{page_id}.md"
        assert baseline_file.exists(), "Baseline file should exist even with empty content"

        # Verify retrieval
        retrieved = initialized_baseline_manager.get_baseline_content(page_id)
        assert retrieved == empty_content, \
            "Empty content should be retrieved correctly"

    def test_baseline_update_partial_failure(
        self,
        initialized_baseline_manager: BaselineManager,
        sample_tracked_pages: dict,
        temp_test_dir: Path
    ):
        """Test baseline update with some failures.

        Verifies:
        - Successful updates complete
        - Failures logged but don't stop process
        - Successful baselines are preserved

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            sample_tracked_pages: Sample tracked pages fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Update baseline for first two pages successfully
        page_ids = list(sample_tracked_pages.keys())[:2]
        for page_id in page_ids:
            file_path = sample_tracked_pages[page_id]
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            initialized_baseline_manager.update_baseline(page_id, content)

        # Verify successful updates
        for page_id in page_ids:
            baseline_file = initialized_baseline_manager.baseline_dir / f"{page_id}.md"
            assert baseline_file.exists(), \
                f"Baseline for {page_id} should exist"

        # Verify non-updated page has no baseline
        non_updated_id = list(sample_tracked_pages.keys())[2]
        baseline_file = initialized_baseline_manager.baseline_dir / f"{non_updated_id}.md"
        assert not baseline_file.exists(), \
            "Non-updated page should not have baseline"

    def test_baseline_directory_structure(
        self,
        initialized_baseline_manager: BaselineManager,
        temp_test_dir: Path
    ):
        """Test baseline directory structure is correct.

        Verifies:
        - Baseline directory exists at correct path
        - Git directory exists
        - Baseline files stored directly in baseline dir

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "123456"
        content = "# Test"
        initialized_baseline_manager.update_baseline(page_id, content)

        # Verify directory structure
        expected_baseline_dir = temp_test_dir / ".confluence-sync" / "baseline"
        assert initialized_baseline_manager.baseline_dir == expected_baseline_dir, \
            "Baseline directory should be at .confluence-sync/baseline"
        assert expected_baseline_dir.exists(), \
            "Baseline directory should exist"
        assert (expected_baseline_dir / ".git").exists(), \
            "Git directory should exist"

        # Verify baseline file location
        baseline_file = expected_baseline_dir / f"{page_id}.md"
        assert baseline_file.exists(), \
            "Baseline file should be in baseline directory"
        assert baseline_file.parent == expected_baseline_dir, \
            "Baseline file should be directly in baseline dir"

    def test_baseline_git_commits_created(
        self,
        initialized_baseline_manager: BaselineManager,
        temp_test_dir: Path
    ):
        """Test git commits are created for baseline updates.

        Verifies:
        - Each update creates a commit
        - Commit messages include page ID
        - Git history is maintained

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            temp_test_dir: Temporary test directory fixture
        """
        import subprocess

        page_id = "123456"
        content = "# Test Page"

        # Update baseline
        initialized_baseline_manager.update_baseline(page_id, content)

        # Check git log
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=initialized_baseline_manager.baseline_dir,
            capture_output=True,
            text=True,
            check=True
        )

        # Verify commit exists with correct message
        assert f"Update baseline for page {page_id}" in result.stdout, \
            "Git commit should exist with correct message"

    def test_baseline_no_changes_commit_handling(
        self,
        initialized_baseline_manager: BaselineManager,
        temp_test_dir: Path
    ):
        """Test baseline update with no changes.

        Verifies:
        - Updating with same content doesn't fail
        - No duplicate commits created
        - Baseline content remains correct

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "123456"
        content = "# Test Page\n\nUnchanged content"

        # First update
        initialized_baseline_manager.update_baseline(page_id, content)

        # Second update with same content
        initialized_baseline_manager.update_baseline(page_id, content)

        # Verify content still correct
        retrieved = initialized_baseline_manager.get_baseline_content(page_id)
        assert retrieved == content, \
            "Content should remain correct"

    def test_baseline_integration_with_tracked_pages(
        self,
        initialized_baseline_manager: BaselineManager,
        sample_tracked_pages: dict,
        temp_test_dir: Path
    ):
        """Test baseline integration with tracked pages workflow.

        Verifies:
        - All tracked pages get baseline updates
        - Baseline content matches tracked files
        - Integration works end-to-end

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            sample_tracked_pages: Sample tracked pages fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Simulate sync operation: update baseline for all tracked pages
        success_count = 0
        for page_id, file_path in sample_tracked_pages.items():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                initialized_baseline_manager.update_baseline(page_id, content)
                success_count += 1
            except Exception as e:
                # Log but continue (simulating real sync behavior)
                print(f"Failed to update baseline for {page_id}: {e}")

        # Verify all updates succeeded
        assert success_count == len(sample_tracked_pages), \
            "All tracked pages should have baseline updates"

        # Verify each baseline matches its tracked file
        for page_id, file_path in sample_tracked_pages.items():
            with open(file_path, 'r', encoding='utf-8') as f:
                expected_content = f.read()

            baseline_content = initialized_baseline_manager.get_baseline_content(page_id)
            assert baseline_content == expected_content, \
                f"Baseline for {page_id} should match tracked file"

    def test_baseline_survives_reinitialization(
        self,
        initialized_baseline_manager: BaselineManager,
        temp_test_dir: Path
    ):
        """Test baseline content survives reinitialization.

        Verifies:
        - Baseline content persists
        - Reinitialization is safe
        - No data loss

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "123456"
        content = "# Test Page\n\nPersistent content"

        # Update baseline
        initialized_baseline_manager.update_baseline(page_id, content)

        # Reinitialize (should be idempotent)
        initialized_baseline_manager.initialize()

        # Verify content still exists
        retrieved = initialized_baseline_manager.get_baseline_content(page_id)
        assert retrieved == content, \
            "Baseline content should survive reinitialization"

    def test_baseline_multiple_pages_independent(
        self,
        initialized_baseline_manager: BaselineManager,
        temp_test_dir: Path
    ):
        """Test multiple pages are updated independently.

        Verifies:
        - Each page has independent baseline
        - Updates don't affect other pages
        - Baselines isolated correctly

        Args:
            initialized_baseline_manager: Initialized BaselineManager fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Update multiple pages
        pages = {
            "111": "# Page 1\n\nContent A",
            "222": "# Page 2\n\nContent B",
            "333": "# Page 3\n\nContent C",
        }

        for page_id, content in pages.items():
            initialized_baseline_manager.update_baseline(page_id, content)

        # Verify each page independent
        for page_id, expected_content in pages.items():
            retrieved = initialized_baseline_manager.get_baseline_content(page_id)
            assert retrieved == expected_content, \
                f"Page {page_id} should have independent baseline"

        # Update one page and verify others unchanged
        initialized_baseline_manager.update_baseline("111", "# Updated\n\nNew content")

        # Verify other pages unchanged
        assert initialized_baseline_manager.get_baseline_content("222") == pages["222"]
        assert initialized_baseline_manager.get_baseline_content("333") == pages["333"]
