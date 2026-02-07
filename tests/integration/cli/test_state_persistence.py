"""Integration tests for state persistence.

This module tests the StateManager's state persistence functionality
against a real filesystem. Tests verify:
- Loading YAML state files from disk
- Saving YAML state files to disk
- Round-trip persistence (save then load, verify data preserved)
- Directory creation for state files
- Error handling for filesystem issues
- Integration with SyncState model

Requirements:
- Temporary test directories (provided by fixtures)
- No external API calls (filesystem only)
"""

import pytest
import os
from pathlib import Path

from src.cli.config import StateManager
from src.cli.models import SyncState
from src.cli.errors import StateError, StateFilesystemError


@pytest.mark.integration
class TestStatePersistence:
    """Integration tests for state file persistence."""

    @pytest.fixture(scope="function")
    def sample_sync_state(self) -> SyncState:
        """Create a sample SyncState for testing.

        Returns:
            SyncState with test data
        """
        return SyncState(last_synced="2024-01-15T10:30:00Z")

    def test_save_state_creates_file(
        self,
        temp_test_dir: Path,
        sample_sync_state: SyncState
    ):
        """Test saving state creates a YAML file on disk.

        Verifies:
        - File is created at specified path
        - File contains valid YAML
        - File is readable

        Args:
            temp_test_dir: Temporary test directory fixture
            sample_sync_state: Sample state fixture
        """
        state_path = temp_test_dir / "state.yaml"

        # Save state
        StateManager.save(str(state_path), sample_sync_state)

        # Verify file exists
        assert state_path.exists(), "State file should be created"
        assert state_path.is_file(), "State path should be a file"

        # Verify file is readable
        content = state_path.read_text(encoding='utf-8')
        assert len(content) > 0, "State file should not be empty"
        assert "last_synced:" in content, "State should contain last_synced field"

    def test_save_state_creates_parent_directory(
        self,
        temp_test_dir: Path,
        sample_sync_state: SyncState
    ):
        """Test saving state creates parent directories if needed.

        Verifies:
        - Parent directories are created automatically
        - Nested directory structure is created
        - State file is created in correct location

        Args:
            temp_test_dir: Temporary test directory fixture
            sample_sync_state: Sample state fixture
        """
        # Use nested path that doesn't exist
        state_path = temp_test_dir / ".confluence-sync" / "state.yaml"
        assert not state_path.parent.exists(), "Parent directory should not exist yet"

        # Save state
        StateManager.save(str(state_path), sample_sync_state)

        # Verify directory structure created
        assert state_path.parent.exists(), "Parent directory should be created"
        assert state_path.exists(), "State file should be created"

    def test_load_state_from_file(
        self,
        temp_test_dir: Path
    ):
        """Test loading state from YAML file.

        Verifies:
        - State is loaded from disk
        - All fields are parsed correctly
        - Data types are correct

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file manually
        state_path = temp_test_dir / "state.yaml"
        state_content = """last_synced: "2024-01-15T10:30:00Z"
"""
        state_path.write_text(state_content, encoding='utf-8')

        # Load state
        sync_state = StateManager.load(str(state_path))

        # Verify state
        assert isinstance(sync_state, SyncState)
        assert sync_state.last_synced == "2024-01-15T10:30:00Z"

    def test_load_state_file_not_found_returns_fresh_state(
        self,
        temp_test_dir: Path
    ):
        """Test loading state from non-existent file returns fresh state.

        Verifies:
        - No exception is raised
        - Fresh SyncState is returned
        - last_synced is None

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        nonexistent_path = temp_test_dir / "does-not-exist.yaml"

        # Load state
        sync_state = StateManager.load(str(nonexistent_path))

        # Verify fresh state returned
        assert isinstance(sync_state, SyncState)
        assert sync_state.last_synced is None

    def test_load_state_empty_file_returns_fresh_state(
        self,
        temp_test_dir: Path
    ):
        """Test loading state from empty file returns fresh state.

        Verifies:
        - Empty file is handled gracefully
        - Fresh SyncState is returned
        - last_synced is None

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create empty file
        state_path = temp_test_dir / "state.yaml"
        state_path.write_text("", encoding='utf-8')

        # Load state
        sync_state = StateManager.load(str(state_path))

        # Verify fresh state returned
        assert isinstance(sync_state, SyncState)
        assert sync_state.last_synced is None

    def test_load_state_null_last_synced(
        self,
        temp_test_dir: Path
    ):
        """Test loading state with null last_synced field.

        Verifies:
        - Null value is handled correctly
        - SyncState has None for last_synced

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file with null
        state_path = temp_test_dir / "state.yaml"
        state_content = """last_synced: null
"""
        state_path.write_text(state_content, encoding='utf-8')

        # Load state
        sync_state = StateManager.load(str(state_path))

        # Verify state
        assert isinstance(sync_state, SyncState)
        assert sync_state.last_synced is None

    def test_load_state_invalid_yaml_raises_error(
        self,
        temp_test_dir: Path
    ):
        """Test loading state with invalid YAML syntax.

        Verifies:
        - StateError is raised
        - Error message mentions YAML syntax

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create file with invalid YAML
        state_path = temp_test_dir / "state.yaml"
        state_content = """last_synced: [unclosed bracket
"""
        state_path.write_text(state_content, encoding='utf-8')

        # Attempt to load
        with pytest.raises(StateError) as exc_info:
            StateManager.load(str(state_path))

        # Verify error details
        error = exc_info.value
        assert "Invalid YAML syntax" in str(error)

    def test_load_state_permission_error(
        self,
        temp_test_dir: Path
    ):
        """Test loading state from unreadable file.

        Verifies:
        - StateFilesystemError is raised
        - Error contains file path and operation
        - Error message mentions permission

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file
        state_path = temp_test_dir / "state.yaml"
        state_path.write_text("last_synced: '2024-01-15T10:30:00Z'\n", encoding='utf-8')

        # Make file unreadable
        os.chmod(state_path, 0o000)

        try:
            # Attempt to load
            with pytest.raises(StateFilesystemError) as exc_info:
                StateManager.load(str(state_path))

            # Verify error details
            error = exc_info.value
            assert error.file_path == str(state_path)
            assert error.operation == "read"
            assert "Permission denied" in str(error)
        finally:
            # Restore permissions for cleanup
            os.chmod(state_path, 0o644)

    def test_save_state_with_last_synced(
        self,
        temp_test_dir: Path
    ):
        """Test saving state with last_synced timestamp.

        Verifies:
        - File is created
        - YAML contains last_synced field
        - Timestamp value is correct

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        state_path = temp_test_dir / "state.yaml"
        sync_state = SyncState(last_synced="2024-01-15T10:30:00Z")

        # Save state
        StateManager.save(str(state_path), sync_state)

        # Verify file created
        assert state_path.exists()

        # Verify content
        content = state_path.read_text(encoding='utf-8')
        assert "last_synced: '2024-01-15T10:30:00Z'" in content or \
               'last_synced: "2024-01-15T10:30:00Z"' in content or \
               "last_synced: 2024-01-15T10:30:00Z" in content

    def test_save_state_without_last_synced(
        self,
        temp_test_dir: Path
    ):
        """Test saving state without last_synced (null).

        Verifies:
        - File is created
        - YAML contains last_synced: null
        - Fresh state is saved correctly

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        state_path = temp_test_dir / "state.yaml"
        sync_state = SyncState()

        # Save state
        StateManager.save(str(state_path), sync_state)

        # Verify file created
        assert state_path.exists()

        # Verify content
        content = state_path.read_text(encoding='utf-8')
        assert "last_synced:" in content
        assert "null" in content.lower() or "last_synced: null" in content

    def test_save_state_overwrites_existing_file(
        self,
        temp_test_dir: Path
    ):
        """Test saving state overwrites existing file.

        Verifies:
        - Existing file is overwritten
        - New content replaces old content
        - Timestamps are updated correctly

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        state_path = temp_test_dir / "state.yaml"

        # Save initial state
        initial_state = SyncState(last_synced="2024-01-15T10:30:00Z")
        StateManager.save(str(state_path), initial_state)

        # Save updated state
        updated_state = SyncState(last_synced="2024-01-16T14:45:00Z")
        StateManager.save(str(state_path), updated_state)

        # Load and verify
        loaded_state = StateManager.load(str(state_path))
        assert loaded_state.last_synced == "2024-01-16T14:45:00Z"

    def test_save_state_permission_error(
        self,
        temp_test_dir: Path
    ):
        """Test saving state to unwritable file.

        Verifies:
        - StateFilesystemError is raised
        - Error contains file path and operation
        - Error message mentions permission

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file and make it unwritable
        state_path = temp_test_dir / "state.yaml"
        state_path.write_text("", encoding='utf-8')
        os.chmod(state_path, 0o444)

        try:
            sync_state = SyncState(last_synced="2024-01-15T10:30:00Z")

            # Attempt to save
            with pytest.raises(StateFilesystemError) as exc_info:
                StateManager.save(str(state_path), sync_state)

            # Verify error details
            error = exc_info.value
            assert error.file_path == str(state_path)
            assert error.operation == "write"
            assert "Permission denied" in str(error)
        finally:
            # Restore permissions for cleanup
            os.chmod(state_path, 0o644)

    def test_save_state_creates_nested_directories(
        self,
        temp_test_dir: Path
    ):
        """Test saving state creates multiple nested directories.

        Verifies:
        - Multiple directory levels are created
        - State file is created in correct location

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        state_path = temp_test_dir / "a" / "b" / "c" / "state.yaml"
        sync_state = SyncState(last_synced="2024-01-15T10:30:00Z")

        # Save state
        StateManager.save(str(state_path), sync_state)

        # Verify all directories and file exist
        assert state_path.exists()
        assert state_path.is_file()

    def test_round_trip_persistence_with_timestamp(
        self,
        temp_test_dir: Path
    ):
        """Test save and load round-trip preserves timestamp.

        Verifies:
        - Data is preserved through save/load cycle
        - Timestamp is identical after round-trip

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        state_path = temp_test_dir / "state.yaml"
        original_state = SyncState(last_synced="2024-01-15T10:30:00Z")

        # Save
        StateManager.save(str(state_path), original_state)

        # Load
        loaded_state = StateManager.load(str(state_path))

        # Verify
        assert loaded_state.last_synced == original_state.last_synced

    def test_round_trip_persistence_with_null(
        self,
        temp_test_dir: Path
    ):
        """Test save and load round-trip preserves null state.

        Verifies:
        - Fresh state is preserved through save/load cycle
        - Null value is maintained

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        state_path = temp_test_dir / "state.yaml"
        original_state = SyncState()

        # Save
        StateManager.save(str(state_path), original_state)

        # Load
        loaded_state = StateManager.load(str(state_path))

        # Verify
        assert loaded_state.last_synced is None

    def test_multiple_save_load_cycles(
        self,
        temp_test_dir: Path
    ):
        """Test multiple save/load cycles maintain data integrity.

        Verifies:
        - Multiple cycles work correctly
        - State updates are persisted
        - Data integrity is maintained

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        state_path = temp_test_dir / "state.yaml"

        # Cycle 1: Save and load with timestamp
        state1 = SyncState(last_synced="2024-01-15T10:30:00Z")
        StateManager.save(str(state_path), state1)
        loaded1 = StateManager.load(str(state_path))
        assert loaded1.last_synced == "2024-01-15T10:30:00Z"

        # Cycle 2: Update timestamp
        state2 = SyncState(last_synced="2024-01-16T11:45:00Z")
        StateManager.save(str(state_path), state2)
        loaded2 = StateManager.load(str(state_path))
        assert loaded2.last_synced == "2024-01-16T11:45:00Z"

        # Cycle 3: Clear timestamp
        state3 = SyncState()
        StateManager.save(str(state_path), state3)
        loaded3 = StateManager.load(str(state_path))
        assert loaded3.last_synced is None

    def test_state_persistence_in_default_location(
        self,
        temp_test_dir: Path
    ):
        """Test state persistence in default .confluence-sync directory.

        Verifies:
        - State can be saved in standard location
        - Directory structure matches expected layout

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Use default directory structure
        state_path = temp_test_dir / ".confluence-sync" / "state.yaml"
        sync_state = SyncState(last_synced="2024-01-15T10:30:00Z")

        # Save state
        StateManager.save(str(state_path), sync_state)

        # Verify directory structure
        assert (temp_test_dir / ".confluence-sync").exists()
        assert (temp_test_dir / ".confluence-sync").is_dir()
        assert state_path.exists()
        assert state_path.is_file()

        # Verify content
        loaded_state = StateManager.load(str(state_path))
        assert loaded_state.last_synced == "2024-01-15T10:30:00Z"

    def test_save_state_directory_creation_error(
        self,
        temp_test_dir: Path
    ):
        """Test error handling when directory cannot be created.

        Verifies:
        - StateFilesystemError is raised
        - Error indicates create_directory operation

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create a file where we want to create a directory
        blocking_file = temp_test_dir / "blocker"
        blocking_file.write_text("blocking", encoding='utf-8')

        # Try to create state file with blocker as directory
        state_path = blocking_file / "state.yaml"
        sync_state = SyncState(last_synced="2024-01-15T10:30:00Z")

        # Attempt to save
        with pytest.raises(StateFilesystemError) as exc_info:
            StateManager.save(str(state_path), sync_state)

        # Verify error details
        error = exc_info.value
        assert error.operation == "create_directory"

    def test_load_state_from_directory_raises_error(
        self,
        temp_test_dir: Path
    ):
        """Test loading state from a directory path raises error.

        Verifies:
        - StateFilesystemError is raised
        - Error indicates read operation failed

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Use directory path instead of file
        state_dir = temp_test_dir / "state_dir"
        state_dir.mkdir()

        # Attempt to load
        with pytest.raises(StateFilesystemError) as exc_info:
            StateManager.load(str(state_dir))

        # Verify error details
        error = exc_info.value
        assert error.file_path == str(state_dir)
        assert error.operation == "read"

    def test_state_file_with_extra_fields_ignored(
        self,
        temp_test_dir: Path
    ):
        """Test that extra fields in state file are ignored.

        Verifies:
        - Extra fields don't cause errors
        - Only known fields are parsed
        - Future compatibility is maintained

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create state file with extra fields
        state_path = temp_test_dir / "state.yaml"
        state_content = """last_synced: "2024-01-15T10:30:00Z"
extra_field: "ignored"
another_field: 12345
"""
        state_path.write_text(state_content, encoding='utf-8')

        # Load state
        sync_state = StateManager.load(str(state_path))

        # Verify only known field is parsed
        assert isinstance(sync_state, SyncState)
        assert sync_state.last_synced == "2024-01-15T10:30:00Z"
        assert not hasattr(sync_state, 'extra_field')
        assert not hasattr(sync_state, 'another_field')
