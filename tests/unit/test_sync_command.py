"""Unit tests for cli.sync_command module.

Tests cover:
- run() entry point with different modes
- _run_bidirectional_sync (no changes, local changes, remote changes, conflicts)
- _run_force_push success
- _run_force_pull success
- _run_dry_run mode
- Single file sync
- Error handling and exit codes
"""

import pytest
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock

from src.cli.sync_command import SyncCommand
from src.cli.models import ExitCode
from src.cli.errors import CLIError, ConfigNotFoundError
from src.confluence_client.errors import (
    InvalidCredentialsError,
    APIUnreachableError,
    APIAccessError,
)
from src.file_mapper.errors import ConfigError


class TestSyncCommandRun:
    """Tests for SyncCommand.run() entry point."""

    @pytest.fixture
    def mock_dependencies(self, tmp_path):
        """Create mock dependencies for SyncCommand."""
        # Create temp config file
        config_path = tmp_path / "config.yaml"
        config_path.write_text("spaces:\n  - key: TEST\n    root_page_id: '123'\n")
        state_path = tmp_path / "state.yaml"

        return {
            "config_path": str(config_path),
            "state_path": str(state_path),
            "output_handler": Mock(),
            "state_manager": Mock(),
            "file_mapper": Mock(),
            "change_detector": Mock(),
            "merge_orchestrator": Mock(),
            "deletion_handler": Mock(),
            "move_handler": Mock(),
            "authenticator": Mock(),
            "ancestor_resolver": Mock(),
            "baseline_manager": Mock(),
            "conflict_resolver": Mock(),
        }

    @pytest.fixture
    def sync_cmd(self, mock_dependencies):
        """Create SyncCommand with mocked dependencies."""
        cmd = SyncCommand(**mock_dependencies)
        # Setup baseline_manager mock
        cmd.baseline_manager.is_initialized.return_value = True
        cmd.baseline_manager.get_baseline_content = Mock(return_value=None)
        return cmd

    def test_run_force_push_and_pull_exclusive(self, sync_cmd):
        """run() should reject both force_push and force_pull."""
        result = sync_cmd.run(force_push=True, force_pull=True)

        assert result == ExitCode.GENERAL_ERROR
        sync_cmd.output_handler.error.assert_called()

    def test_run_config_not_found(self, tmp_path):
        """run() should show init instructions when config not found."""
        output = Mock()
        cmd = SyncCommand(
            config_path=str(tmp_path / "nonexistent.yaml"),
            output_handler=output,
        )

        result = cmd.run()

        assert result == ExitCode.GENERAL_ERROR
        output.print.assert_called()  # Shows initialization instructions

    @patch('src.cli.sync_command.ConfigLoader')
    def test_run_auth_error_returns_auth_code(self, mock_config_loader, sync_cmd):
        """run() should return AUTH_ERROR on InvalidCredentialsError."""
        mock_config_loader.load.return_value = Mock(spaces=[])
        # State manager raises auth error
        sync_cmd.state_manager.load.side_effect = InvalidCredentialsError(
            user="test@example.com", endpoint="https://test.atlassian.net"
        )

        result = sync_cmd.run()

        assert result == ExitCode.AUTH_ERROR

    @patch('src.cli.sync_command.ConfigLoader')
    def test_run_network_error_returns_network_code(self, mock_config_loader, sync_cmd):
        """run() should return NETWORK_ERROR on API errors."""
        mock_config_loader.load.return_value = Mock(spaces=[])
        sync_cmd.state_manager.load.side_effect = APIUnreachableError(
            endpoint="https://test.atlassian.net"
        )

        result = sync_cmd.run()

        assert result == ExitCode.NETWORK_ERROR

    def test_run_config_error_returns_general_code(self, sync_cmd):
        """run() should return GENERAL_ERROR on ConfigError."""
        sync_cmd.state_manager.load.side_effect = ConfigError("Invalid config")

        result = sync_cmd.run()

        assert result == ExitCode.GENERAL_ERROR


class TestBidirectionalSync:
    """Tests for _run_bidirectional_sync method."""

    @pytest.fixture
    def mock_dependencies(self, tmp_path):
        """Create mock dependencies."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("spaces:\n  - key: TEST\n    root_page_id: '123'\n")
        state_path = tmp_path / "state.yaml"

        return {
            "config_path": str(config_path),
            "state_path": str(state_path),
            "output_handler": Mock(),
            "state_manager": Mock(),
            "file_mapper": Mock(),
            "change_detector": Mock(),
            "merge_orchestrator": Mock(),
            "deletion_handler": Mock(),
            "move_handler": Mock(),
            "authenticator": Mock(),
            "ancestor_resolver": Mock(),
            "baseline_manager": Mock(),
            "conflict_resolver": Mock(),
        }

    @pytest.fixture
    def sync_cmd(self, mock_dependencies):
        """Create SyncCommand with mocked dependencies."""
        cmd = SyncCommand(**mock_dependencies)
        # Setup baseline_manager mock
        cmd.baseline_manager.is_initialized.return_value = True
        cmd.baseline_manager.get_baseline_content = Mock(return_value=None)
        return cmd

    def test_bidirectional_sync_no_changes(self, sync_cmd):
        """_run_bidirectional_sync should handle no changes gracefully."""
        # Setup: no deletions, no moves, no conflicts
        sync_cmd.change_detector.detect_deletions.return_value = Mock(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        sync_cmd.change_detector.detect_moves.return_value = Mock(
            moved_in_confluence=[],
            moved_locally=[]
        )
        sync_cmd.file_mapper.sync_spaces.return_value = Mock(
            pushed_count=0,
            pulled_count=0,
            conflict_page_ids=[],
            conflict_local_paths={},
            conflict_remote_content={},
            conflict_titles={}
        )
        sync_cmd.state_manager.load.return_value = Mock(
            last_synced=None,
            tracked_pages={}
        )

        # Stub helper methods
        sync_cmd._discover_tracked_pages = Mock(return_value={})
        sync_cmd._get_remote_pages = Mock(return_value={})
        sync_cmd._update_baseline_repository = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        result = sync_cmd._run_bidirectional_sync(config, state)

        assert result == ExitCode.SUCCESS

    def test_bidirectional_sync_with_local_changes(self, sync_cmd):
        """_run_bidirectional_sync should push local changes."""
        sync_cmd.change_detector.detect_deletions.return_value = Mock(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        sync_cmd.change_detector.detect_moves.return_value = Mock(
            moved_in_confluence=[],
            moved_locally=[]
        )
        sync_cmd.file_mapper.sync_spaces.return_value = Mock(
            pushed_count=3,
            pulled_count=0,
            conflict_page_ids=[],
            conflict_local_paths={},
            conflict_remote_content={},
            conflict_titles={}
        )

        sync_cmd._discover_tracked_pages = Mock(return_value={})
        sync_cmd._get_remote_pages = Mock(return_value={})
        sync_cmd._update_baseline_repository = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        result = sync_cmd._run_bidirectional_sync(config, state)

        assert result == ExitCode.SUCCESS
        # Verify summary was printed
        sync_cmd.output_handler.print_summary.assert_called()

    def test_bidirectional_sync_with_remote_changes(self, sync_cmd):
        """_run_bidirectional_sync should pull remote changes."""
        sync_cmd.change_detector.detect_deletions.return_value = Mock(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        sync_cmd.change_detector.detect_moves.return_value = Mock(
            moved_in_confluence=[],
            moved_locally=[]
        )
        sync_cmd.file_mapper.sync_spaces.return_value = Mock(
            pushed_count=0,
            pulled_count=5,
            conflict_page_ids=[],
            conflict_local_paths={},
            conflict_remote_content={},
            conflict_titles={}
        )

        sync_cmd._discover_tracked_pages = Mock(return_value={})
        sync_cmd._get_remote_pages = Mock(return_value={})
        sync_cmd._update_baseline_repository = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        result = sync_cmd._run_bidirectional_sync(config, state)

        assert result == ExitCode.SUCCESS

    def test_bidirectional_sync_with_conflicts(self, sync_cmd):
        """_run_bidirectional_sync should handle conflicts."""
        sync_cmd.change_detector.detect_deletions.return_value = Mock(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        sync_cmd.change_detector.detect_moves.return_value = Mock(
            moved_in_confluence=[],
            moved_locally=[]
        )
        sync_cmd.file_mapper.sync_spaces.return_value = Mock(
            pushed_count=0,
            pulled_count=0,
            conflict_page_ids=["page1", "page2"],
            conflict_local_paths={"page1": "/path/to/page1.md", "page2": "/path/to/page2.md"},
            conflict_remote_content={"page1": "remote content 1", "page2": "remote content 2"},
            conflict_titles={"page1": "Page 1", "page2": "Page 2"}
        )
        sync_cmd.conflict_resolver.resolve_conflicts.return_value = Mock(
            auto_merged_count=1,
            failed_count=1,
            conflicts=[Mock(title="Page 2", local_path="/path/to/page2.md")]
        )

        sync_cmd._discover_tracked_pages = Mock(return_value={})
        sync_cmd._get_remote_pages = Mock(return_value={})
        sync_cmd._update_baseline_repository = Mock()
        sync_cmd._push_merged_pages = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        result = sync_cmd._run_bidirectional_sync(config, state)

        assert result == ExitCode.SUCCESS
        sync_cmd.conflict_resolver.resolve_conflicts.assert_called()

    def test_bidirectional_sync_with_deletions(self, sync_cmd):
        """_run_bidirectional_sync should process deletions."""
        sync_cmd.change_detector.detect_deletions.return_value = Mock(
            deleted_in_confluence=["page1"],  # Deleted in Confluence
            deleted_locally=["page2"]  # Deleted locally
        )
        sync_cmd.change_detector.detect_moves.return_value = Mock(
            moved_in_confluence=[],
            moved_locally=[]
        )
        sync_cmd.file_mapper.sync_spaces.return_value = Mock(
            pushed_count=0,
            pulled_count=0,
            conflict_page_ids=[]
        )

        sync_cmd._discover_tracked_pages = Mock(return_value={})
        sync_cmd._get_remote_pages = Mock(return_value={})
        sync_cmd._update_baseline_repository = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        result = sync_cmd._run_bidirectional_sync(config, state)

        assert result == ExitCode.SUCCESS
        sync_cmd.deletion_handler.delete_local_files.assert_called()
        sync_cmd.deletion_handler.delete_confluence_pages.assert_called()

    def test_bidirectional_sync_with_moves(self, sync_cmd):
        """_run_bidirectional_sync should process moves."""
        sync_cmd.change_detector.detect_deletions.return_value = Mock(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        sync_cmd.change_detector.detect_moves.return_value = Mock(
            moved_in_confluence=["page1"],
            moved_locally=["page2"]
        )
        sync_cmd.file_mapper.sync_spaces.return_value = Mock(
            pushed_count=0,
            pulled_count=0,
            conflict_page_ids=[]
        )

        sync_cmd._discover_tracked_pages = Mock(return_value={})
        sync_cmd._get_remote_pages = Mock(return_value={})
        sync_cmd._update_baseline_repository = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        result = sync_cmd._run_bidirectional_sync(config, state)

        assert result == ExitCode.SUCCESS
        sync_cmd.move_handler.move_local_files.assert_called()
        sync_cmd.move_handler.move_confluence_pages.assert_called()


class TestForcePush:
    """Tests for _run_force_push method."""

    @pytest.fixture
    def mock_dependencies(self, tmp_path):
        """Create mock dependencies."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("spaces:\n  - key: TEST\n")
        state_path = tmp_path / "state.yaml"

        return {
            "config_path": str(config_path),
            "state_path": str(state_path),
            "output_handler": Mock(),
            "state_manager": Mock(),
            "file_mapper": Mock(),
            "change_detector": Mock(),
            "baseline_manager": Mock(),
        }

    @pytest.fixture
    def sync_cmd(self, mock_dependencies):
        """Create SyncCommand with mocked dependencies."""
        cmd = SyncCommand(**mock_dependencies)
        cmd.baseline_manager.is_initialized.return_value = True
        return cmd

    def test_force_push_success(self, sync_cmd):
        """_run_force_push should push all local content."""
        sync_cmd.file_mapper.sync_spaces.return_value = Mock(pushed_count=10)
        sync_cmd._discover_tracked_pages = Mock(return_value={})
        sync_cmd._update_baseline_repository = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        result = sync_cmd._run_force_push(config, state)

        assert result == ExitCode.SUCCESS
        assert config.force_push is True
        sync_cmd.output_handler.print_force_summary.assert_called_with(
            count=10,
            direction="push"
        )

    def test_force_push_updates_state(self, sync_cmd):
        """_run_force_push should update state after success."""
        sync_cmd.file_mapper.sync_spaces.return_value = Mock(pushed_count=5)
        sync_cmd._discover_tracked_pages = Mock(return_value={"page1": {}})
        sync_cmd._update_baseline_repository = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        sync_cmd._run_force_push(config, state)

        sync_cmd.state_manager.save.assert_called()


class TestForcePull:
    """Tests for _run_force_pull method."""

    @pytest.fixture
    def mock_dependencies(self, tmp_path):
        """Create mock dependencies."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("spaces:\n  - key: TEST\n")
        state_path = tmp_path / "state.yaml"

        return {
            "config_path": str(config_path),
            "state_path": str(state_path),
            "output_handler": Mock(),
            "state_manager": Mock(),
            "file_mapper": Mock(),
            "change_detector": Mock(),
            "baseline_manager": Mock(),
        }

    @pytest.fixture
    def sync_cmd(self, mock_dependencies):
        """Create SyncCommand with mocked dependencies."""
        cmd = SyncCommand(**mock_dependencies)
        cmd.baseline_manager.is_initialized.return_value = True
        return cmd

    def test_force_pull_success(self, sync_cmd):
        """_run_force_pull should pull all remote content."""
        sync_cmd.file_mapper.sync_spaces.return_value = Mock(pulled_count=8)
        sync_cmd._discover_tracked_pages = Mock(return_value={})
        sync_cmd._update_baseline_repository = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        result = sync_cmd._run_force_pull(config, state)

        assert result == ExitCode.SUCCESS
        assert config.force_pull is True
        sync_cmd.output_handler.print_force_summary.assert_called_with(
            count=8,
            direction="pull"
        )


class TestDryRun:
    """Tests for _run_dry_run method."""

    @pytest.fixture
    def mock_dependencies(self, tmp_path):
        """Create mock dependencies."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("spaces:\n  - key: TEST\n")
        state_path = tmp_path / "state.yaml"

        return {
            "config_path": str(config_path),
            "state_path": str(state_path),
            "output_handler": Mock(),
            "state_manager": Mock(),
            "file_mapper": Mock(),
            "change_detector": Mock(),
            "baseline_manager": Mock(),
        }

    @pytest.fixture
    def sync_cmd(self, mock_dependencies):
        """Create SyncCommand with mocked dependencies."""
        cmd = SyncCommand(**mock_dependencies)
        cmd.baseline_manager.is_initialized.return_value = True
        cmd.baseline_manager.get_baseline_content = Mock(return_value=None)
        return cmd

    def test_dry_run_does_not_modify(self, sync_cmd):
        """_run_dry_run should preview changes without applying."""
        sync_cmd.change_detector.detect_changes.return_value = Mock(
            local_changes=["file1.md"],
            remote_changes=["page1"],
            conflicts=[]
        )
        sync_cmd._discover_tracked_pages = Mock(return_value={"page1": {}})
        sync_cmd._get_remote_pages = Mock(return_value={"page1": {}})

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        result = sync_cmd._run_dry_run(config, state, None)

        assert result == ExitCode.SUCCESS
        # Verify state was NOT saved
        sync_cmd.state_manager.save.assert_not_called()


class TestSingleFileSync:
    """Tests for single file sync mode."""

    @pytest.fixture
    def mock_dependencies(self, tmp_path):
        """Create mock dependencies."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("spaces:\n  - key: TEST\n")
        state_path = tmp_path / "state.yaml"

        return {
            "config_path": str(config_path),
            "state_path": str(state_path),
            "output_handler": Mock(),
            "state_manager": Mock(),
            "file_mapper": Mock(),
            "change_detector": Mock(),
            "baseline_manager": Mock(),
            "conflict_resolver": Mock(),
            "deletion_handler": Mock(),
            "move_handler": Mock(),
        }

    @pytest.fixture
    def sync_cmd(self, mock_dependencies):
        """Create SyncCommand with mocked dependencies."""
        cmd = SyncCommand(**mock_dependencies)
        cmd.baseline_manager.is_initialized.return_value = True
        cmd.baseline_manager.get_baseline_content = Mock(return_value=None)
        return cmd

    def test_single_file_sync_calls_sync_single_file(self, sync_cmd):
        """Bidirectional sync with single_file should use _sync_single_file."""
        sync_cmd.change_detector.detect_deletions.return_value = Mock(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        sync_cmd.change_detector.detect_moves.return_value = Mock(
            moved_in_confluence=[],
            moved_locally=[]
        )
        sync_cmd._discover_tracked_pages = Mock(return_value={})
        sync_cmd._get_remote_pages = Mock(return_value={})
        sync_cmd._update_baseline_repository = Mock()
        sync_cmd._sync_single_file = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        result = sync_cmd._run_bidirectional_sync(
            config, state, single_file="docs/test.md"
        )

        assert result == ExitCode.SUCCESS
        sync_cmd._sync_single_file.assert_called_once()


class TestErrorHandling:
    """Tests for error handling in SyncCommand."""

    @pytest.fixture
    def mock_dependencies(self, tmp_path):
        """Create mock dependencies."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("spaces:\n  - key: TEST\n")
        state_path = tmp_path / "state.yaml"

        return {
            "config_path": str(config_path),
            "state_path": str(state_path),
            "output_handler": Mock(),
            "state_manager": Mock(),
            "file_mapper": Mock(),
        }

    @pytest.fixture
    def sync_cmd(self, mock_dependencies):
        """Create SyncCommand with mocked dependencies."""
        return SyncCommand(**mock_dependencies)

    @patch('src.cli.sync_command.ConfigLoader')
    def test_api_access_error_returns_network_code(self, mock_config_loader, sync_cmd):
        """API access errors should return NETWORK_ERROR."""
        mock_config_loader.load.return_value = Mock(spaces=[])
        sync_cmd.state_manager.load.side_effect = APIAccessError("Forbidden")

        result = sync_cmd.run()

        assert result == ExitCode.NETWORK_ERROR

    @patch('src.cli.sync_command.ConfigLoader')
    def test_cli_error_returns_general_code(self, mock_config_loader, sync_cmd):
        """CLIError should return GENERAL_ERROR."""
        mock_config_loader.load.return_value = Mock(spaces=[])
        sync_cmd.state_manager.load.side_effect = CLIError("Something went wrong")

        result = sync_cmd.run()

        assert result == ExitCode.GENERAL_ERROR

    @patch('src.cli.sync_command.ConfigLoader')
    def test_unexpected_error_returns_general_code(self, mock_config_loader, sync_cmd):
        """Unexpected errors should return GENERAL_ERROR."""
        mock_config_loader.load.return_value = Mock(spaces=[])
        sync_cmd.state_manager.load.side_effect = RuntimeError("Unexpected")

        result = sync_cmd.run()

        assert result == ExitCode.GENERAL_ERROR


class TestStateManagement:
    """Tests for state management in SyncCommand."""

    @pytest.fixture
    def mock_dependencies(self, tmp_path):
        """Create mock dependencies."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("spaces:\n  - key: TEST\n")
        state_path = tmp_path / "state.yaml"

        return {
            "config_path": str(config_path),
            "state_path": str(state_path),
            "output_handler": Mock(),
            "state_manager": Mock(),
            "file_mapper": Mock(),
            "change_detector": Mock(),
            "baseline_manager": Mock(),
            "deletion_handler": Mock(),
            "move_handler": Mock(),
            "conflict_resolver": Mock(),
        }

    @pytest.fixture
    def sync_cmd(self, mock_dependencies):
        """Create SyncCommand with mocked dependencies."""
        cmd = SyncCommand(**mock_dependencies)
        cmd.baseline_manager.is_initialized.return_value = True
        cmd.baseline_manager.get_baseline_content = Mock(return_value=None)
        return cmd

    def test_timestamp_updated_after_sync(self, sync_cmd):
        """State timestamp should be updated after successful sync."""
        sync_cmd.change_detector.detect_deletions.return_value = Mock(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        sync_cmd.change_detector.detect_moves.return_value = Mock(
            moved_in_confluence=[],
            moved_locally=[]
        )
        sync_cmd.file_mapper.sync_spaces.return_value = Mock(
            pushed_count=0,
            pulled_count=0,
            conflict_page_ids=[]
        )
        sync_cmd._discover_tracked_pages = Mock(return_value={})
        sync_cmd._get_remote_pages = Mock(return_value={})
        sync_cmd._update_baseline_repository = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced=None, tracked_pages={})

        sync_cmd._run_bidirectional_sync(config, state, update_timestamp=True)

        # Verify state was saved
        sync_cmd.state_manager.save.assert_called()
        # Verify timestamp was updated
        assert state.last_synced is not None

    def test_timestamp_not_updated_when_disabled(self, sync_cmd):
        """State timestamp should not update when update_timestamp=False."""
        sync_cmd.change_detector.detect_deletions.return_value = Mock(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        sync_cmd.change_detector.detect_moves.return_value = Mock(
            moved_in_confluence=[],
            moved_locally=[]
        )
        sync_cmd.file_mapper.sync_spaces.return_value = Mock(
            pushed_count=0,
            pulled_count=0,
            conflict_page_ids=[]
        )
        sync_cmd._discover_tracked_pages = Mock(return_value={})
        sync_cmd._get_remote_pages = Mock(return_value={})
        sync_cmd._update_baseline_repository = Mock()

        config = Mock(spaces=[], force_push=False, force_pull=False)
        state = Mock(last_synced="2024-01-01T00:00:00Z", tracked_pages={})

        sync_cmd._run_bidirectional_sync(config, state, update_timestamp=False)

        # Verify original timestamp preserved
        assert state.last_synced == "2024-01-01T00:00:00Z"


class TestDependencyInitialization:
    """Tests for lazy dependency initialization."""

    def test_dependencies_created_when_not_provided(self, tmp_path):
        """Dependencies should be created lazily if not provided."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
spaces:
  - key: TEST
    root_page_id: '123'
    local_path: ./docs
""")

        cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(tmp_path / "state.yaml"),
        )

        # Dependencies should be None before run()
        assert cmd.file_mapper is None
        assert cmd.change_detector is None
        assert cmd.merge_orchestrator is None

    def test_provided_dependencies_used(self, tmp_path):
        """Provided dependencies should be used instead of created."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("spaces:\n  - key: TEST\n")

        mock_file_mapper = Mock()
        mock_change_detector = Mock()

        cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(tmp_path / "state.yaml"),
            file_mapper=mock_file_mapper,
            change_detector=mock_change_detector,
        )

        assert cmd.file_mapper is mock_file_mapper
        assert cmd.change_detector is mock_change_detector
