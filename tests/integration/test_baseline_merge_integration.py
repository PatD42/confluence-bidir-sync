"""Integration tests for baseline usage in 3-way merge operations.

Tests that the BaselineManager correctly stores and retrieves baseline
content for use as the common ancestor in 3-way merge operations.
"""

import pytest
from pathlib import Path

from src.cli.baseline_manager import BaselineManager
from src.git_integration.table_merge import merge_content_with_table_awareness


@pytest.mark.integration
class TestBaselineMergeIntegration:
    """Integration tests for baseline in 3-way merge."""

    def test_baseline_used_as_merge_ancestor(self, mock_baseline_manager, temp_test_dir):
        """AC-9.1: Baseline content is used as common ancestor in merge."""
        # Given: A baseline exists for a page
        baseline_content = """| Col1 | Col2 |
|------|------|
| Original A | Original B |
"""
        mock_baseline_manager.update_baseline('123456', baseline_content)

        # And: Both local and remote have changes from baseline
        local_content = """| Col1 | Col2 |
|------|------|
| Modified A | Original B |
"""
        remote_content = """| Col1 | Col2 |
|------|------|
| Original A | Modified B |
"""

        # When: 3-way merge is performed
        baseline = mock_baseline_manager.get_baseline_content('123456')
        result, _ = merge_content_with_table_awareness(
            baseline.strip(),
            local_content.strip(),
            remote_content.strip()
        )

        # Then: Both changes should be merged (identified from baseline)
        assert "Modified A" in result, "Local change should be present"
        assert "Modified B" in result, "Remote change should be present"
        assert "Original A" not in result, "Original A should be replaced"
        assert "Original B" not in result, "Original B should be replaced"

    def test_missing_baseline_fallback(self, mock_baseline_manager):
        """AC-9.2: Missing baseline is handled gracefully."""
        # Given: No baseline exists for page
        baseline = mock_baseline_manager.get_baseline_content('999999')

        # Then: Should return None (not crash)
        assert baseline is None, "Missing baseline should return None"

    def test_missing_baseline_merge_behavior(self, mock_baseline_manager):
        """AC-9.2b: Merge without baseline uses one version as ancestor."""
        # Given: No baseline exists
        local_content = """| Col1 | Col2 |
|------|------|
| A-local | B |
"""
        remote_content = """| Col1 | Col2 |
|------|------|
| A-remote | B |
"""

        # When: Merge with local as "baseline" (2-way comparison)
        # This simulates fallback behavior when no real baseline exists
        result, _ = merge_content_with_table_awareness(
            local_content.strip(),  # Use local as baseline
            local_content.strip(),
            remote_content.strip()
        )

        # Then: Remote changes should be detected
        assert "A-remote" in result, "Remote content should be merged"

    def test_baseline_refresh_saves_content(self, mock_baseline_manager):
        """AC-9.3: Baseline is updated after successful sync."""
        # Given: Initial baseline
        initial_content = "| Old | Content |"
        mock_baseline_manager.update_baseline('456789', initial_content)

        # When: New content is synced and baseline is refreshed
        new_content = "| New | Content |"
        mock_baseline_manager.update_baseline('456789', new_content)

        # Then: Baseline should be updated
        baseline = mock_baseline_manager.get_baseline_content('456789')
        assert baseline == new_content, "Baseline should be updated"
        assert baseline != initial_content, "Old content should be replaced"

    def test_baseline_available_for_next_cycle(self, mock_baseline_manager):
        """AC-9.3b: Updated baseline is available for subsequent merges."""
        # Given: A sync cycle completes with content
        content_v1 = """| Feature | Status |
|---------|--------|
| Login | Done |
"""
        mock_baseline_manager.update_baseline('789012', content_v1)

        # And: A subsequent sync cycle with changes
        local_v2 = """| Feature | Status |
|---------|--------|
| Login | Done |
| Logout | Pending |
"""

        # When: Baseline from first cycle is used
        baseline = mock_baseline_manager.get_baseline_content('789012')

        # Then: First cycle's content is available as baseline
        assert baseline == content_v1, "Previous baseline should be available"

        # And: Can detect additions from baseline
        result, _ = merge_content_with_table_awareness(
            baseline.strip(),
            local_v2.strip(),
            baseline.strip()  # Remote unchanged
        )
        assert "Logout" in result, "New row should be in merge result"


@pytest.mark.integration
class TestBaselineManager:
    """Integration tests for BaselineManager operations."""

    def test_save_and_retrieve_baseline(self, mock_baseline_manager):
        """Verify save and retrieve operations work correctly."""
        content = "Test baseline content\nWith multiple lines"

        mock_baseline_manager.update_baseline('111111', content)
        retrieved = mock_baseline_manager.get_baseline_content('111111')

        assert retrieved == content, "Retrieved content should match saved"

    def test_baseline_stored_in_correct_location(self, temp_test_dir):
        """Verify baseline files are stored in expected directory."""
        config_dir = temp_test_dir / '.confluence-sync'
        config_dir.mkdir(parents=True, exist_ok=True)
        baseline_dir = config_dir / 'baseline'
        baseline_dir.mkdir(parents=True, exist_ok=True)

        # BaselineManager stores files directly in the directory passed to it
        manager = BaselineManager(baseline_dir)
        manager.initialize()
        manager.update_baseline('222222', 'Test content')

        # Check file exists in baseline directory
        baseline_file = baseline_dir / '222222.md'
        assert baseline_file.exists(), f"Baseline file should exist at {baseline_file}"

    def test_multiple_page_baselines(self, mock_baseline_manager):
        """Verify multiple pages can have separate baselines."""
        mock_baseline_manager.update_baseline('333333', 'Content for page 1')
        mock_baseline_manager.update_baseline('444444', 'Content for page 2')
        mock_baseline_manager.update_baseline('555555', 'Content for page 3')

        assert mock_baseline_manager.get_baseline_content('333333') == 'Content for page 1'
        assert mock_baseline_manager.get_baseline_content('444444') == 'Content for page 2'
        assert mock_baseline_manager.get_baseline_content('555555') == 'Content for page 3'

    def test_baseline_overwrite(self, mock_baseline_manager):
        """Verify baseline can be overwritten with new content."""
        mock_baseline_manager.update_baseline('666666', 'Version 1')
        mock_baseline_manager.update_baseline('666666', 'Version 2')
        mock_baseline_manager.update_baseline('666666', 'Version 3')

        result = mock_baseline_manager.get_baseline_content('666666')
        assert result == 'Version 3', "Should have latest version"

    def test_baseline_with_special_characters(self, mock_baseline_manager):
        """Verify baseline handles content with special characters."""
        content = """| Feature | Description |
|---------|-------------|
| <br> tags | Line breaks: Line1<br>Line2 |
| Unicode | 日本語 émojis 🎉 |
| Code | `const x = 1;` |
"""
        mock_baseline_manager.update_baseline('777777', content)
        retrieved = mock_baseline_manager.get_baseline_content('777777')

        assert retrieved == content, "Special characters should be preserved"
        assert "<br>" in retrieved
        assert "日本語" in retrieved
        assert "🎉" in retrieved


@pytest.mark.integration
class TestThreeWayMergeWithBaseline:
    """Integration tests for complete 3-way merge scenarios."""

    def test_no_changes_results_in_base(self, mock_baseline_with_content):
        """Verify no changes from base results in base content."""
        baseline = mock_baseline_with_content.get_baseline_content('12345')

        result, _ = merge_content_with_table_awareness(
            baseline.strip(),
            baseline.strip(),  # Local unchanged
            baseline.strip()   # Remote unchanged
        )

        # Normalize for comparison (remove extra whitespace)
        assert result.strip() == baseline.strip(), \
            "No changes should result in baseline content"

    def test_local_only_changes_preserved(self, mock_baseline_with_content):
        """Verify local-only changes are preserved."""
        baseline = mock_baseline_with_content.get_baseline_content('12345')

        local = """| Col1 | Col2 |
|------|------|
| A-local | B |
| C | D |
"""

        result, _ = merge_content_with_table_awareness(
            baseline.strip(),
            local.strip(),
            baseline.strip()  # Remote unchanged
        )

        assert "A-local" in result, "Local change should be preserved"

    def test_remote_only_changes_preserved(self, mock_baseline_with_content):
        """Verify remote-only changes are preserved."""
        baseline = mock_baseline_with_content.get_baseline_content('12345')

        remote = """| Col1 | Col2 |
|------|------|
| A | B-remote |
| C | D |
"""

        result, _ = merge_content_with_table_awareness(
            baseline.strip(),
            baseline.strip(),  # Local unchanged
            remote.strip()
        )

        assert "B-remote" in result, "Remote change should be preserved"
