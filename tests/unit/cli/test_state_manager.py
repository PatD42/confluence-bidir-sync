"""Unit tests for cli.config.StateManager module."""

import os
import tempfile
import pytest
import yaml

from src.cli.config import StateManager
from src.cli.errors import StateError, StateFilesystemError
from src.cli.models import SyncState


class TestStateManagerLoad:
    """Test cases for StateManager.load() method."""

    def test_load_valid_state_with_last_synced(self, tmp_path):
        """Load valid state file with last_synced timestamp."""
        state_file = tmp_path / "state.yaml"
        state_content = """
last_synced: "2024-01-15T10:30:00Z"
"""
        state_file.write_text(state_content)

        result = StateManager.load(str(state_file))

        assert isinstance(result, SyncState)
        assert result.last_synced == "2024-01-15T10:30:00Z"

    def test_load_valid_state_without_last_synced(self, tmp_path):
        """Load valid state file without last_synced field."""
        state_file = tmp_path / "state.yaml"
        state_content = """
{}
"""
        state_file.write_text(state_content)

        result = StateManager.load(str(state_file))

        assert isinstance(result, SyncState)
        assert result.last_synced is None

    def test_load_valid_state_with_null_last_synced(self, tmp_path):
        """Load valid state file with null last_synced."""
        state_file = tmp_path / "state.yaml"
        state_content = """
last_synced: null
"""
        state_file.write_text(state_content)

        result = StateManager.load(str(state_file))

        assert isinstance(result, SyncState)
        assert result.last_synced is None

    def test_load_file_not_found_returns_fresh_state(self, tmp_path):
        """Load non-existent file returns fresh SyncState."""
        state_file = tmp_path / "nonexistent.yaml"

        result = StateManager.load(str(state_file))

        assert isinstance(result, SyncState)
        assert result.last_synced is None

    def test_load_permission_error_raises_filesystem_error(self, tmp_path):
        """Load file without read permission raises StateFilesystemError."""
        state_file = tmp_path / "state.yaml"
        state_file.write_text("last_synced: '2024-01-15T10:30:00Z'\n")

        # Make file unreadable
        os.chmod(state_file, 0o000)

        try:
            with pytest.raises(StateFilesystemError) as exc_info:
                StateManager.load(str(state_file))

            assert exc_info.value.file_path == str(state_file)
            assert exc_info.value.operation == "read"
            assert "Permission denied" in str(exc_info.value)
        finally:
            # Restore permissions for cleanup
            os.chmod(state_file, 0o644)

    def test_load_generic_file_error_raises_filesystem_error(self, tmp_path):
        """Load with generic file error raises StateFilesystemError."""
        # Test using a directory path instead of file (causes IsADirectoryError)
        state_dir = tmp_path / "state_dir"
        state_dir.mkdir()

        with pytest.raises(StateFilesystemError) as exc_info:
            StateManager.load(str(state_dir))

        assert exc_info.value.file_path == str(state_dir)
        assert exc_info.value.operation == "read"

    def test_load_invalid_yaml_syntax_raises_error(self, tmp_path):
        """Load file with invalid YAML syntax raises StateError."""
        state_file = tmp_path / "state.yaml"
        state_content = """
last_synced: [unclosed bracket
"""
        state_file.write_text(state_content)

        with pytest.raises(StateError) as exc_info:
            StateManager.load(str(state_file))

        assert "Invalid YAML syntax" in str(exc_info.value)

    def test_load_empty_file_returns_fresh_state(self, tmp_path):
        """Load empty file returns fresh SyncState."""
        state_file = tmp_path / "state.yaml"
        state_file.write_text("")

        result = StateManager.load(str(state_file))

        assert isinstance(result, SyncState)
        assert result.last_synced is None

    def test_load_whitespace_only_file_returns_fresh_state(self, tmp_path):
        """Load file with only whitespace returns fresh SyncState."""
        state_file = tmp_path / "state.yaml"
        state_file.write_text("   \n  \t  \n  ")

        result = StateManager.load(str(state_file))

        assert isinstance(result, SyncState)
        assert result.last_synced is None

    def test_load_yaml_not_dict_raises_error(self, tmp_path):
        """Load file with non-dict YAML raises StateError."""
        state_file = tmp_path / "state.yaml"
        state_file.write_text("- item1\n- item2\n")

        with pytest.raises(StateError) as exc_info:
            StateManager.load(str(state_file))

        assert "must be a YAML dictionary" in str(exc_info.value)
        assert "got list" in str(exc_info.value)

    def test_load_yaml_string_raises_error(self, tmp_path):
        """Load file with string YAML raises StateError."""
        state_file = tmp_path / "state.yaml"
        state_file.write_text("just a string")

        with pytest.raises(StateError) as exc_info:
            StateManager.load(str(state_file))

        assert "must be a YAML dictionary" in str(exc_info.value)
        assert "got str" in str(exc_info.value)

    def test_load_last_synced_wrong_type_raises_error(self, tmp_path):
        """Load file with non-string last_synced raises StateError."""
        state_file = tmp_path / "state.yaml"
        state_content = """
last_synced: 12345
"""
        state_file.write_text(state_content)

        with pytest.raises(StateError) as exc_info:
            StateManager.load(str(state_file))

        assert "last_synced" in str(exc_info.value)
        assert "must be a string" in str(exc_info.value)

    def test_load_last_synced_empty_string_raises_error(self, tmp_path):
        """Load file with empty string last_synced raises StateError."""
        state_file = tmp_path / "state.yaml"
        state_content = """
last_synced: ""
"""
        state_file.write_text(state_content)

        with pytest.raises(StateError) as exc_info:
            StateManager.load(str(state_file))

        assert "last_synced" in str(exc_info.value)
        assert "cannot be empty" in str(exc_info.value)

    def test_load_last_synced_whitespace_only_raises_error(self, tmp_path):
        """Load file with whitespace-only last_synced raises StateError."""
        state_file = tmp_path / "state.yaml"
        state_content = """
last_synced: "   "
"""
        state_file.write_text(state_content)

        with pytest.raises(StateError) as exc_info:
            StateManager.load(str(state_file))

        assert "last_synced" in str(exc_info.value)
        assert "cannot be empty" in str(exc_info.value)

    def test_load_last_synced_with_surrounding_whitespace(self, tmp_path):
        """Load file with whitespace around last_synced strips it."""
        state_file = tmp_path / "state.yaml"
        state_content = """
last_synced: "  2024-01-15T10:30:00Z  "
"""
        state_file.write_text(state_content)

        result = StateManager.load(str(state_file))

        assert result.last_synced == "2024-01-15T10:30:00Z"


class TestStateManagerSave:
    """Test cases for StateManager.save() method."""

    def test_save_state_with_last_synced(self, tmp_path):
        """Save state with last_synced timestamp."""
        state_file = tmp_path / "state.yaml"
        sync_state = SyncState(last_synced="2024-01-15T10:30:00Z")

        StateManager.save(str(state_file), sync_state)

        # Verify file exists
        assert state_file.exists()

        # Verify content
        with open(state_file, 'r', encoding='utf-8') as f:
            content = yaml.safe_load(f)

        assert content['last_synced'] == "2024-01-15T10:30:00Z"

    def test_save_state_without_last_synced(self, tmp_path):
        """Save state without last_synced (null)."""
        state_file = tmp_path / "state.yaml"
        sync_state = SyncState()

        StateManager.save(str(state_file), sync_state)

        # Verify file exists
        assert state_file.exists()

        # Verify content
        with open(state_file, 'r', encoding='utf-8') as f:
            content = yaml.safe_load(f)

        assert content['last_synced'] is None

    def test_save_creates_directory_if_missing(self, tmp_path):
        """Save creates parent directory if it doesn't exist."""
        state_dir = tmp_path / ".confluence-sync"
        state_file = state_dir / "state.yaml"
        sync_state = SyncState(last_synced="2024-01-15T10:30:00Z")

        # Directory shouldn't exist yet
        assert not state_dir.exists()

        StateManager.save(str(state_file), sync_state)

        # Directory and file should now exist
        assert state_dir.exists()
        assert state_file.exists()

    def test_save_creates_nested_directories(self, tmp_path):
        """Save creates nested directories if they don't exist."""
        state_file = tmp_path / "a" / "b" / "c" / "state.yaml"
        sync_state = SyncState(last_synced="2024-01-15T10:30:00Z")

        StateManager.save(str(state_file), sync_state)

        # All directories and file should exist
        assert state_file.exists()

    def test_save_overwrites_existing_file(self, tmp_path):
        """Save overwrites existing state file."""
        state_file = tmp_path / "state.yaml"

        # Save initial state
        initial_state = SyncState(last_synced="2024-01-15T10:30:00Z")
        StateManager.save(str(state_file), initial_state)

        # Save updated state
        updated_state = SyncState(last_synced="2024-01-16T14:45:00Z")
        StateManager.save(str(state_file), updated_state)

        # Verify updated content
        with open(state_file, 'r', encoding='utf-8') as f:
            content = yaml.safe_load(f)

        assert content['last_synced'] == "2024-01-16T14:45:00Z"

    def test_save_permission_error_raises_filesystem_error(self, tmp_path):
        """Save to file without write permission raises StateFilesystemError."""
        state_file = tmp_path / "state.yaml"
        state_file.write_text("")

        # Make file unwritable
        os.chmod(state_file, 0o444)

        try:
            sync_state = SyncState(last_synced="2024-01-15T10:30:00Z")

            with pytest.raises(StateFilesystemError) as exc_info:
                StateManager.save(str(state_file), sync_state)

            assert exc_info.value.file_path == str(state_file)
            assert exc_info.value.operation == "write"
            assert "Permission denied" in str(exc_info.value)
        finally:
            # Restore permissions for cleanup
            os.chmod(state_file, 0o644)

    def test_save_directory_creation_error_raises_filesystem_error(self, tmp_path):
        """Save with directory creation error raises StateFilesystemError."""
        # Create a file where we want to create a directory
        blocking_file = tmp_path / "blocker"
        blocking_file.write_text("blocking")

        # Try to create state file with blocker as directory
        state_file = blocking_file / "state.yaml"
        sync_state = SyncState(last_synced="2024-01-15T10:30:00Z")

        with pytest.raises(StateFilesystemError) as exc_info:
            StateManager.save(str(state_file), sync_state)

        assert exc_info.value.operation == "create_directory"


class TestStateManagerRoundTrip:
    """Test cases for save/load round-trip operations."""

    def test_save_and_load_round_trip(self, tmp_path):
        """Save and load state maintains all data."""
        state_file = tmp_path / "state.yaml"
        original_state = SyncState(last_synced="2024-01-15T10:30:00Z")

        # Save
        StateManager.save(str(state_file), original_state)

        # Load
        loaded_state = StateManager.load(str(state_file))

        # Verify
        assert loaded_state.last_synced == original_state.last_synced

    def test_save_and_load_round_trip_with_null(self, tmp_path):
        """Save and load state with null last_synced."""
        state_file = tmp_path / "state.yaml"
        original_state = SyncState()

        # Save
        StateManager.save(str(state_file), original_state)

        # Load
        loaded_state = StateManager.load(str(state_file))

        # Verify
        assert loaded_state.last_synced is None

    def test_multiple_save_load_cycles(self, tmp_path):
        """Multiple save/load cycles maintain data integrity."""
        state_file = tmp_path / "state.yaml"

        # Cycle 1
        state1 = SyncState(last_synced="2024-01-15T10:30:00Z")
        StateManager.save(str(state_file), state1)
        loaded1 = StateManager.load(str(state_file))
        assert loaded1.last_synced == "2024-01-15T10:30:00Z"

        # Cycle 2 - Update
        state2 = SyncState(last_synced="2024-01-16T11:45:00Z")
        StateManager.save(str(state_file), state2)
        loaded2 = StateManager.load(str(state_file))
        assert loaded2.last_synced == "2024-01-16T11:45:00Z"

        # Cycle 3 - Clear
        state3 = SyncState()
        StateManager.save(str(state_file), state3)
        loaded3 = StateManager.load(str(state_file))
        assert loaded3.last_synced is None


class TestStateManagerParseState:
    """Test cases for StateManager._parse_state() private method."""

    def test_parse_state_with_valid_last_synced(self):
        """Parse state dict with valid last_synced."""
        state_dict = {'last_synced': '2024-01-15T10:30:00Z'}

        result = StateManager._parse_state(state_dict)

        assert result.last_synced == '2024-01-15T10:30:00Z'

    def test_parse_state_without_last_synced(self):
        """Parse state dict without last_synced field."""
        state_dict = {}

        result = StateManager._parse_state(state_dict)

        assert result.last_synced is None

    def test_parse_state_with_null_last_synced(self):
        """Parse state dict with null last_synced."""
        state_dict = {'last_synced': None}

        result = StateManager._parse_state(state_dict)

        assert result.last_synced is None

    def test_parse_state_with_invalid_type(self):
        """Parse state dict with non-string last_synced raises StateError."""
        state_dict = {'last_synced': 12345}

        with pytest.raises(StateError) as exc_info:
            StateManager._parse_state(state_dict)

        assert exc_info.value.state_field == 'last_synced'
        assert "must be a string" in str(exc_info.value)

    def test_parse_state_with_empty_string(self):
        """Parse state dict with empty string last_synced raises StateError."""
        state_dict = {'last_synced': ''}

        with pytest.raises(StateError) as exc_info:
            StateManager._parse_state(state_dict)

        assert exc_info.value.state_field == 'last_synced'
        assert "cannot be empty" in str(exc_info.value)

    def test_parse_state_with_whitespace_only(self):
        """Parse state dict with whitespace-only last_synced raises StateError."""
        state_dict = {'last_synced': '   '}

        with pytest.raises(StateError) as exc_info:
            StateManager._parse_state(state_dict)

        assert exc_info.value.state_field == 'last_synced'
        assert "cannot be empty" in str(exc_info.value)

    def test_parse_state_strips_whitespace(self):
        """Parse state dict strips whitespace from last_synced."""
        state_dict = {'last_synced': '  2024-01-15T10:30:00Z  '}

        result = StateManager._parse_state(state_dict)

        assert result.last_synced == '2024-01-15T10:30:00Z'
