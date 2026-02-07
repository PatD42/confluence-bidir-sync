"""Integration tests for state tracking (tracked_pages).

This module tests the StateManager's tracked_pages functionality
against a real filesystem. Tests verify:
- Loading tracked_pages from state YAML files
- Saving tracked_pages to state YAML files
- Round-trip persistence (save then load, verify data preserved)
- Adding pages to tracked_pages
- Removing pages from tracked_pages
- Validation of tracked_pages structure (dict with string keys/values)
- Integration with SyncState model

Requirements:
- Temporary test directories (provided by fixtures)
- No external API calls (filesystem only)
"""

import pytest
from pathlib import Path

from src.cli.config import StateManager
from src.cli.models import SyncState
from src.cli.errors import StateError


@pytest.mark.integration
class TestStateTracking:
    """Integration tests for tracked_pages state functionality."""

    @pytest.fixture(scope="function")
    def sample_tracked_pages(self) -> dict:
        """Create sample tracked_pages for testing.

        Returns:
            Dict mapping page_id to local file path
        """
        return {
            "123456": "docs/page-one.md",
            "789012": "docs/section/page-two.md",
            "345678": "docs/another-page.md"
        }

    @pytest.fixture(scope="function")
    def sample_sync_state_with_tracking(self, sample_tracked_pages: dict) -> SyncState:
        """Create a SyncState with tracked_pages for testing.

        Args:
            sample_tracked_pages: Sample tracked_pages fixture

        Returns:
            SyncState with test data including tracked_pages
        """
        return SyncState(
            last_synced="2024-01-15T10:30:00Z",
            tracked_pages=sample_tracked_pages
        )

    def test_save_state_with_tracked_pages(
        self,
        temp_test_dir: Path,
        sample_sync_state_with_tracking: SyncState
    ):
        """Test saving state with tracked_pages creates valid YAML.

        Verifies:
        - File is created with tracked_pages section
        - tracked_pages is saved as YAML dictionary
        - All page_id to path mappings are preserved

        Args:
            temp_test_dir: Temporary test directory fixture
            sample_sync_state_with_tracking: Sample state with tracking fixture
        """
        state_path = temp_test_dir / "state.yaml"

        # Save state
        StateManager.save(str(state_path), sample_sync_state_with_tracking)

        # Verify file exists
        assert state_path.exists(), "State file should be created"

        # Verify content
        content = state_path.read_text(encoding='utf-8')
        assert "tracked_pages:" in content, "State should contain tracked_pages field"
        assert "'123456':" in content, "Should contain first page_id"
        assert "'789012':" in content, "Should contain second page_id"
        assert "docs/page-one.md" in content, "Should contain first path"

    def test_load_state_with_tracked_pages(
        self,
        temp_test_dir: Path
    ):
        """Test loading state with tracked_pages from YAML file.

        Verifies:
        - tracked_pages is loaded correctly as dictionary
        - All page_id to path mappings are preserved
        - Data types are correct (strings)

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file with tracked_pages
        state_path = temp_test_dir / "state.yaml"
        state_content = """last_synced: "2024-01-15T10:30:00Z"
tracked_pages:
  '123456': docs/page-one.md
  '789012': docs/section/page-two.md
  '345678': docs/another-page.md
"""
        state_path.write_text(state_content, encoding='utf-8')

        # Load state
        sync_state = StateManager.load(str(state_path))

        # Verify state
        assert isinstance(sync_state, SyncState)
        assert sync_state.last_synced == "2024-01-15T10:30:00Z"
        assert isinstance(sync_state.tracked_pages, dict)
        assert len(sync_state.tracked_pages) == 3
        assert sync_state.tracked_pages["123456"] == "docs/page-one.md"
        assert sync_state.tracked_pages["789012"] == "docs/section/page-two.md"
        assert sync_state.tracked_pages["345678"] == "docs/another-page.md"

    def test_load_state_empty_tracked_pages(
        self,
        temp_test_dir: Path
    ):
        """Test loading state with empty tracked_pages.

        Verifies:
        - Empty tracked_pages is handled correctly
        - SyncState has empty dict for tracked_pages

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file with empty tracked_pages
        state_path = temp_test_dir / "state.yaml"
        state_content = """last_synced: "2024-01-15T10:30:00Z"
tracked_pages: {}
"""
        state_path.write_text(state_content, encoding='utf-8')

        # Load state
        sync_state = StateManager.load(str(state_path))

        # Verify state
        assert isinstance(sync_state, SyncState)
        assert isinstance(sync_state.tracked_pages, dict)
        assert len(sync_state.tracked_pages) == 0

    def test_load_state_missing_tracked_pages(
        self,
        temp_test_dir: Path
    ):
        """Test loading state without tracked_pages field.

        Verifies:
        - Missing tracked_pages defaults to empty dict
        - State is valid even without tracked_pages

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file without tracked_pages
        state_path = temp_test_dir / "state.yaml"
        state_content = """last_synced: "2024-01-15T10:30:00Z"
"""
        state_path.write_text(state_content, encoding='utf-8')

        # Load state
        sync_state = StateManager.load(str(state_path))

        # Verify state
        assert isinstance(sync_state, SyncState)
        assert isinstance(sync_state.tracked_pages, dict)
        assert len(sync_state.tracked_pages) == 0

    def test_round_trip_tracked_pages_persistence(
        self,
        temp_test_dir: Path,
        sample_sync_state_with_tracking: SyncState
    ):
        """Test round-trip persistence of tracked_pages.

        Verifies:
        - Save then load preserves all tracked_pages data
        - No data loss or corruption occurs
        - Data types remain correct

        Args:
            temp_test_dir: Temporary test directory fixture
            sample_sync_state_with_tracking: Sample state with tracking fixture
        """
        state_path = temp_test_dir / "state.yaml"
        original_state = sample_sync_state_with_tracking

        # Save state
        StateManager.save(str(state_path), original_state)

        # Load state
        loaded_state = StateManager.load(str(state_path))

        # Verify all data preserved
        assert loaded_state.last_synced == original_state.last_synced
        assert loaded_state.tracked_pages == original_state.tracked_pages
        assert len(loaded_state.tracked_pages) == len(original_state.tracked_pages)

        # Verify each mapping
        for page_id, path in original_state.tracked_pages.items():
            assert page_id in loaded_state.tracked_pages
            assert loaded_state.tracked_pages[page_id] == path

    def test_update_tracked_pages_add_page(
        self,
        temp_test_dir: Path
    ):
        """Test adding a page to tracked_pages.

        Verifies:
        - New pages can be added to existing tracked_pages
        - Existing pages are preserved
        - Save and load works after adding

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        state_path = temp_test_dir / "state.yaml"

        # Create initial state with one page
        initial_state = SyncState(
            last_synced="2024-01-15T10:30:00Z",
            tracked_pages={"123456": "docs/page-one.md"}
        )
        StateManager.save(str(state_path), initial_state)

        # Load, add page, and save
        loaded_state = StateManager.load(str(state_path))
        loaded_state.tracked_pages["789012"] = "docs/page-two.md"
        StateManager.save(str(state_path), loaded_state)

        # Load again and verify
        final_state = StateManager.load(str(state_path))
        assert len(final_state.tracked_pages) == 2
        assert final_state.tracked_pages["123456"] == "docs/page-one.md"
        assert final_state.tracked_pages["789012"] == "docs/page-two.md"

    def test_update_tracked_pages_remove_page(
        self,
        temp_test_dir: Path,
        sample_sync_state_with_tracking: SyncState
    ):
        """Test removing a page from tracked_pages.

        Verifies:
        - Pages can be removed from tracked_pages
        - Remaining pages are preserved
        - Save and load works after removing

        Args:
            temp_test_dir: Temporary test directory fixture
            sample_sync_state_with_tracking: Sample state with tracking fixture
        """
        state_path = temp_test_dir / "state.yaml"

        # Save initial state with multiple pages
        StateManager.save(str(state_path), sample_sync_state_with_tracking)

        # Load, remove page, and save
        loaded_state = StateManager.load(str(state_path))
        original_count = len(loaded_state.tracked_pages)
        del loaded_state.tracked_pages["789012"]
        StateManager.save(str(state_path), loaded_state)

        # Load again and verify
        final_state = StateManager.load(str(state_path))
        assert len(final_state.tracked_pages) == original_count - 1
        assert "789012" not in final_state.tracked_pages
        assert "123456" in final_state.tracked_pages
        assert "345678" in final_state.tracked_pages

    def test_load_state_invalid_tracked_pages_type(
        self,
        temp_test_dir: Path
    ):
        """Test loading state with invalid tracked_pages type raises error.

        Verifies:
        - Non-dict tracked_pages raises StateError
        - Error message indicates type issue

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file with tracked_pages as list
        state_path = temp_test_dir / "state.yaml"
        state_content = """last_synced: "2024-01-15T10:30:00Z"
tracked_pages:
  - page1
  - page2
"""
        state_path.write_text(state_content, encoding='utf-8')

        # Load state - should raise error
        with pytest.raises(StateError) as exc_info:
            StateManager.load(str(state_path))

        assert "tracked_pages" in str(exc_info.value)
        assert "dictionary" in str(exc_info.value).lower()

    def test_load_state_invalid_tracked_pages_key_type(
        self,
        temp_test_dir: Path
    ):
        """Test loading state with non-string keys in tracked_pages raises error.

        Verifies:
        - Integer keys in tracked_pages raise StateError
        - Error message indicates key type issue

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file with integer key
        state_path = temp_test_dir / "state.yaml"
        state_content = """last_synced: "2024-01-15T10:30:00Z"
tracked_pages:
  123456: docs/page-one.md
"""
        state_path.write_text(state_content, encoding='utf-8')

        # Load state - should raise error
        with pytest.raises(StateError) as exc_info:
            StateManager.load(str(state_path))

        assert "tracked_pages" in str(exc_info.value)
        assert "string" in str(exc_info.value).lower()

    def test_load_state_invalid_tracked_pages_value_type(
        self,
        temp_test_dir: Path
    ):
        """Test loading state with non-string values in tracked_pages raises error.

        Verifies:
        - Non-string values in tracked_pages raise StateError
        - Error message indicates value type issue

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file with integer value
        state_path = temp_test_dir / "state.yaml"
        state_content = """last_synced: "2024-01-15T10:30:00Z"
tracked_pages:
  '123456': 12345
"""
        state_path.write_text(state_content, encoding='utf-8')

        # Load state - should raise error
        with pytest.raises(StateError) as exc_info:
            StateManager.load(str(state_path))

        assert "tracked_pages" in str(exc_info.value)
        assert "string" in str(exc_info.value).lower()

    def test_save_and_load_large_tracked_pages(
        self,
        temp_test_dir: Path
    ):
        """Test handling large number of tracked pages.

        Verifies:
        - Large tracked_pages dictionaries are handled correctly
        - Performance is reasonable for typical use cases
        - No data loss with many entries

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        state_path = temp_test_dir / "state.yaml"

        # Create state with many tracked pages (100 pages)
        tracked_pages = {
            f"page{i:06d}": f"docs/section{i % 10}/page{i}.md"
            for i in range(100)
        }
        large_state = SyncState(
            last_synced="2024-01-15T10:30:00Z",
            tracked_pages=tracked_pages
        )

        # Save state
        StateManager.save(str(state_path), large_state)

        # Load state
        loaded_state = StateManager.load(str(state_path))

        # Verify all pages preserved
        assert len(loaded_state.tracked_pages) == 100
        assert loaded_state.tracked_pages == tracked_pages

    def test_tracked_pages_with_special_characters_in_paths(
        self,
        temp_test_dir: Path
    ):
        """Test tracked_pages with special characters in file paths.

        Verifies:
        - Paths with spaces, dots, hyphens are handled correctly
        - Unicode characters in paths are preserved
        - Round-trip works with special characters

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        state_path = temp_test_dir / "state.yaml"

        # Create state with special character paths
        tracked_pages = {
            "123456": "docs/my page with spaces.md",
            "789012": "docs/file-with-dashes.md",
            "345678": "docs/file.with.dots.md",
            "901234": "docs/café-résumé.md"
        }
        state = SyncState(
            last_synced="2024-01-15T10:30:00Z",
            tracked_pages=tracked_pages
        )

        # Save and load
        StateManager.save(str(state_path), state)
        loaded_state = StateManager.load(str(state_path))

        # Verify all paths preserved
        assert loaded_state.tracked_pages == tracked_pages
        assert loaded_state.tracked_pages["123456"] == "docs/my page with spaces.md"
        assert loaded_state.tracked_pages["901234"] == "docs/café-résumé.md"

    def test_tracked_pages_null_value_in_yaml(
        self,
        temp_test_dir: Path
    ):
        """Test loading state with null tracked_pages.

        Verifies:
        - Null tracked_pages is treated as empty dict
        - No error is raised

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file with null tracked_pages
        state_path = temp_test_dir / "state.yaml"
        state_content = """last_synced: "2024-01-15T10:30:00Z"
tracked_pages: null
"""
        state_path.write_text(state_content, encoding='utf-8')

        # Load state
        sync_state = StateManager.load(str(state_path))

        # Verify state
        assert isinstance(sync_state, SyncState)
        assert isinstance(sync_state.tracked_pages, dict)
        assert len(sync_state.tracked_pages) == 0
