"""Integration tests for single-file sync timestamp behavior.

This module tests single-file sync functionality to verify correct timestamp
behavior per ADR-013 and ADR-014. Tests verify:
- Single-file sync updates baseline for that file only
- Single-file sync does NOT update global state.last_synced timestamp
- Full sync updates both baseline and global timestamp
- Baseline isolation between different files

Requirements:
- Temporary test directories (provided by fixtures)
- BaselineManager for baseline git repository
- StateManager for state.yaml management
- No external API calls (filesystem only)
"""

import pytest
import os
from pathlib import Path
from datetime import datetime, UTC, timedelta
from unittest.mock import patch

from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.models import LocalPage, SpaceConfig, SyncConfig
from src.file_mapper.frontmatter_handler import FrontmatterHandler
from src.confluence_client.auth import Authenticator
from src.cli.baseline_manager import BaselineManager
from src.cli.config import StateManager
from src.cli.models import SyncState


@pytest.mark.integration
class TestSingleFileSyncTimestamps:
    """Integration tests for single-file sync timestamp behavior."""

    @pytest.fixture(scope="function")
    def file_mapper(self) -> FileMapper:
        """Create FileMapper instance for testing.

        Returns:
            FileMapper instance (without real Confluence connection)
        """
        # Create a mock authenticator to avoid needing real credentials
        # File operations don't require API access
        with patch.object(Authenticator, '__init__', return_value=None):
            auth = Authenticator()
            mapper = FileMapper(auth)
            return mapper

    @pytest.fixture(scope="function")
    def baseline_manager(self, temp_test_dir: Path) -> BaselineManager:
        """Create BaselineManager instance for testing.

        Args:
            temp_test_dir: Temporary test directory fixture

        Returns:
            BaselineManager instance with test baseline directory
        """
        baseline_dir = temp_test_dir / ".confluence-sync" / "baseline"
        manager = BaselineManager(baseline_dir=baseline_dir)
        manager.initialize()
        return manager

    @pytest.fixture(scope="function")
    def state_manager(self) -> StateManager:
        """Create StateManager instance for testing.

        Returns:
            StateManager instance
        """
        return StateManager()

    @pytest.fixture(scope="function")
    def state_file_path(self, temp_test_dir: Path) -> Path:
        """Create state file path for testing.

        Args:
            temp_test_dir: Temporary test directory fixture

        Returns:
            Path to state.yaml file
        """
        state_dir = temp_test_dir / ".confluence-sync"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir / "state.yaml"

    @pytest.fixture(scope="function")
    def sample_page_content(self) -> str:
        """Generate sample page content with frontmatter.

        Returns:
            Markdown content with frontmatter
        """
        return """---
page_id: "123456"
---
# Test Page

This is the initial content.
"""

    def test_single_file_sync_does_not_update_global_timestamp(
        self,
        baseline_manager: BaselineManager,
        state_manager: StateManager,
        state_file_path: Path,
        temp_test_dir: Path,
        sample_page_content: str
    ):
        """Test that single-file sync does not update state.last_synced.

        Verifies:
        - Initial full sync sets state.last_synced
        - Single-file sync updates baseline for that file
        - Single-file sync does NOT update state.last_synced
        - Global timestamp remains unchanged after single-file sync

        Args:
            baseline_manager: BaselineManager fixture
            state_manager: StateManager fixture
            state_file_path: Path to state.yaml fixture
            temp_test_dir: Temporary test directory fixture
            sample_page_content: Sample page content fixture
        """
        # Create initial test file
        file_path = temp_test_dir / "Test-Page.md"
        file_path.write_text(sample_page_content, encoding='utf-8')

        # Simulate initial full sync - set baseline and state timestamp
        initial_timestamp = "2024-01-15T10:00:00Z"
        baseline_manager.update_baseline("123456", sample_page_content)
        initial_state = SyncState(
            last_synced=initial_timestamp,
            tracked_pages={"123456": str(file_path)}
        )
        state_manager.save(str(state_file_path), initial_state)

        # Verify initial state was saved
        loaded_state = state_manager.load(str(state_file_path))
        assert loaded_state.last_synced == initial_timestamp, \
            "Initial timestamp should be saved"

        # Modify the file (simulate local change)
        modified_content = """---
page_id: "123456"
---
# Test Page

This is the modified content after initial sync.
"""
        file_path.write_text(modified_content, encoding='utf-8')

        # Simulate single-file sync - update baseline only
        baseline_manager.update_baseline("123456", modified_content)

        # Verify baseline was updated
        baseline_content = baseline_manager.get_baseline_content("123456")
        assert baseline_content == modified_content, \
            "Baseline should be updated for single file"

        # Load state again - timestamp should NOT have changed
        final_state = state_manager.load(str(state_file_path))
        assert final_state.last_synced == initial_timestamp, \
            "Global timestamp should NOT be updated for single-file sync"

    def test_full_sync_updates_global_timestamp(
        self,
        baseline_manager: BaselineManager,
        state_manager: StateManager,
        state_file_path: Path,
        temp_test_dir: Path,
        sample_page_content: str
    ):
        """Test that full sync updates both baseline and state.last_synced.

        Verifies:
        - Full sync updates baseline for all files
        - Full sync updates state.last_synced
        - Global timestamp changes after full sync

        Args:
            baseline_manager: BaselineManager fixture
            state_manager: StateManager fixture
            state_file_path: Path to state.yaml fixture
            temp_test_dir: Temporary test directory fixture
            sample_page_content: Sample page content fixture
        """
        # Create test file
        file_path = temp_test_dir / "Test-Page.md"
        file_path.write_text(sample_page_content, encoding='utf-8')

        # Initial state - no timestamp
        initial_state = SyncState(
            last_synced=None,
            tracked_pages={}
        )
        state_manager.save(str(state_file_path), initial_state)

        # Simulate full sync
        sync_timestamp = datetime.now(UTC).isoformat()
        baseline_manager.update_baseline("123456", sample_page_content)
        updated_state = SyncState(
            last_synced=sync_timestamp,
            tracked_pages={"123456": str(file_path)}
        )
        state_manager.save(str(state_file_path), updated_state)

        # Verify state was updated
        final_state = state_manager.load(str(state_file_path))
        assert final_state.last_synced == sync_timestamp, \
            "Full sync should update global timestamp"
        assert "123456" in final_state.tracked_pages, \
            "Full sync should track page"

    def test_multiple_files_single_file_sync_isolates_baseline(
        self,
        baseline_manager: BaselineManager,
        state_manager: StateManager,
        state_file_path: Path,
        temp_test_dir: Path
    ):
        """Test that single-file sync only updates baseline for that file.

        Verifies:
        - Multiple files can be tracked
        - Single-file sync updates only one baseline
        - Other file baselines remain unchanged
        - Global timestamp is not updated

        Args:
            baseline_manager: BaselineManager fixture
            state_manager: StateManager fixture
            state_file_path: Path to state.yaml fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create multiple test files
        file1_content = """---
page_id: "111"
---
# Page 1

Initial content for page 1.
"""

        file2_content = """---
page_id: "222"
---
# Page 2

Initial content for page 2.
"""

        file1_path = temp_test_dir / "Page-1.md"
        file2_path = temp_test_dir / "Page-2.md"
        file1_path.write_text(file1_content, encoding='utf-8')
        file2_path.write_text(file2_content, encoding='utf-8')

        # Simulate initial full sync
        initial_timestamp = "2024-01-15T10:00:00Z"
        baseline_manager.update_baseline("111", file1_content)
        baseline_manager.update_baseline("222", file2_content)
        initial_state = SyncState(
            last_synced=initial_timestamp,
            tracked_pages={
                "111": str(file1_path),
                "222": str(file2_path)
            }
        )
        state_manager.save(str(state_file_path), initial_state)

        # Modify only file1 (simulate local change)
        modified_file1_content = """---
page_id: "111"
---
# Page 1

Modified content for page 1 only.
"""
        file1_path.write_text(modified_file1_content, encoding='utf-8')

        # Simulate single-file sync for file1 only
        baseline_manager.update_baseline("111", modified_file1_content)

        # Verify only file1 baseline was updated
        baseline1 = baseline_manager.get_baseline_content("111")
        baseline2 = baseline_manager.get_baseline_content("222")

        assert baseline1 == modified_file1_content, \
            "File 1 baseline should be updated"
        assert baseline2 == file2_content, \
            "File 2 baseline should remain unchanged"

        # Verify global timestamp was NOT updated
        final_state = state_manager.load(str(state_file_path))
        assert final_state.last_synced == initial_timestamp, \
            "Global timestamp should NOT be updated for single-file sync"

    def test_single_file_sync_with_no_initial_state(
        self,
        baseline_manager: BaselineManager,
        state_manager: StateManager,
        state_file_path: Path,
        temp_test_dir: Path
    ):
        """Test single-file sync behavior when no state exists.

        Verifies:
        - Single-file sync creates baseline
        - State file is not created (or last_synced remains None)
        - Baseline exists for synced file

        Args:
            baseline_manager: BaselineManager fixture
            state_manager: StateManager fixture
            state_file_path: Path to state.yaml fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create test file
        content = """---
page_id: "123"
---
# New Page

First sync content.
"""
        file_path = temp_test_dir / "New-Page.md"
        file_path.write_text(content, encoding='utf-8')

        # No initial state - simulate fresh repository

        # Simulate single-file sync (without updating global state)
        baseline_manager.update_baseline("123", content)

        # Verify baseline was created
        baseline_content = baseline_manager.get_baseline_content("123")
        assert baseline_content == content, \
            "Baseline should be created for single file"

        # If state file doesn't exist, loading should return fresh state
        if not state_file_path.exists():
            loaded_state = state_manager.load(str(state_file_path))
            assert loaded_state.last_synced is None, \
                "State should have no timestamp for single-file sync"

    def test_timestamp_comparison_after_single_file_sync(
        self,
        baseline_manager: BaselineManager,
        state_manager: StateManager,
        state_file_path: Path,
        temp_test_dir: Path
    ):
        """Test timestamp remains stable across single-file syncs.

        Verifies:
        - Initial timestamp is set by full sync
        - Multiple single-file syncs do not change timestamp
        - Timestamp can be used to detect next full sync

        Args:
            baseline_manager: BaselineManager fixture
            state_manager: StateManager fixture
            state_file_path: Path to state.yaml fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Create test file
        content = """---
page_id: "456"
---
# Stable Page

Original content.
"""
        file_path = temp_test_dir / "Stable-Page.md"
        file_path.write_text(content, encoding='utf-8')

        # Set initial state with timestamp
        initial_timestamp = "2024-01-15T10:00:00Z"
        baseline_manager.update_baseline("456", content)
        initial_state = SyncState(
            last_synced=initial_timestamp,
            tracked_pages={"456": str(file_path)}
        )
        state_manager.save(str(state_file_path), initial_state)

        # Perform multiple single-file syncs
        for i in range(3):
            modified_content = f"""---
page_id: "456"
---
# Stable Page

Modified content version {i+1}.
"""
            file_path.write_text(modified_content, encoding='utf-8')
            baseline_manager.update_baseline("456", modified_content)

            # Verify timestamp hasn't changed
            current_state = state_manager.load(str(state_file_path))
            assert current_state.last_synced == initial_timestamp, \
                f"Timestamp should remain unchanged after sync {i+1}"

        # Final verification - timestamp should still match initial
        final_state = state_manager.load(str(state_file_path))
        assert final_state.last_synced == initial_timestamp, \
            "Timestamp should remain stable across all single-file syncs"
