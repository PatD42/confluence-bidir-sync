"""Unit tests for cli.sync_command.SyncCommand module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, UTC

from src.cli.sync_command import SyncCommand
from src.cli.models import ExitCode, SyncState, SyncSummary, DeletionResult, MoveResult
from src.cli.errors import CLIError, ConfigNotFoundError
from src.confluence_client.errors import (
    InvalidCredentialsError,
    APIUnreachableError,
    APIAccessError,
)
from src.file_mapper.errors import ConfigError
from src.file_mapper.models import SyncConfig, SpaceConfig, SyncResult


class TestSyncCommandInitialization:
    """Test cases for SyncCommand initialization."""

    def test_init_with_defaults(self):
        """Initialize with default paths and no dependencies."""
        sync_cmd = SyncCommand()

        assert sync_cmd.config_path == ".confluence-sync/config.yaml"
        assert sync_cmd.state_path == ".confluence-sync/state.yaml"
        assert sync_cmd.output_handler is not None
        assert sync_cmd.state_manager is not None
        assert sync_cmd.authenticator is None
        assert sync_cmd.file_mapper is None
        assert sync_cmd.change_detector is None
        assert sync_cmd.merge_orchestrator is None

    def test_init_with_custom_paths(self):
        """Initialize with custom configuration and state paths."""
        sync_cmd = SyncCommand(
            config_path="/custom/config.yaml",
            state_path="/custom/state.yaml",
        )

        assert sync_cmd.config_path == "/custom/config.yaml"
        assert sync_cmd.state_path == "/custom/state.yaml"

    def test_init_with_injected_dependencies(self):
        """Initialize with injected dependencies for testing."""
        mock_output = Mock()
        mock_state_manager = Mock()
        mock_file_mapper = Mock()
        mock_change_detector = Mock()
        mock_merge_orchestrator = Mock()
        mock_authenticator = Mock()

        sync_cmd = SyncCommand(
            output_handler=mock_output,
            state_manager=mock_state_manager,
            file_mapper=mock_file_mapper,
            change_detector=mock_change_detector,
            merge_orchestrator=mock_merge_orchestrator,
            authenticator=mock_authenticator,
        )

        assert sync_cmd.output_handler is mock_output
        assert sync_cmd.state_manager is mock_state_manager
        assert sync_cmd.file_mapper is mock_file_mapper
        assert sync_cmd.change_detector is mock_change_detector
        assert sync_cmd.merge_orchestrator is mock_merge_orchestrator
        assert sync_cmd.authenticator is mock_authenticator


class TestSyncCommandExitCodes:
    """Test cases for SyncCommand exit code behavior (UT-SC-01)."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mocked dependencies for SyncCommand."""
        mock_change_detector = Mock()
        # Mock deletion and move detection to return proper objects
        mock_change_detector.detect_deletions.return_value = DeletionResult(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        mock_change_detector.detect_moves.return_value = MoveResult(
            moved_in_confluence=[],
            moved_locally=[]
        )

        return {
            'output_handler': Mock(),
            'state_manager': Mock(),
            'file_mapper': Mock(),
            'change_detector': mock_change_detector,
            'merge_orchestrator': Mock(),
            'authenticator': Mock(),
        }

    @pytest.fixture
    def sample_config(self, tmp_path):
        """Create sample SyncConfig."""
        return SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="123456",
                    local_path=str(tmp_path / "docs"),
                    exclude_page_ids=[],
                )
            ],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=str(tmp_path / ".confluence-sync/temp"),
        )

    @pytest.fixture
    def sample_state(self):
        """Create sample SyncState."""
        return SyncState(last_synced="2024-01-15T10:30:00Z")

    def test_success_exit_code_on_normal_sync(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Return SUCCESS exit code on successful sync."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state
                mock_dependencies['state_manager'].save.return_value = None

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                exit_code = sync_cmd.run(dry_run=False, force_push=False, force_pull=False)

                # Assert
                assert exit_code == ExitCode.SUCCESS

    def test_general_error_exit_code_on_config_not_found(self, tmp_path, mock_dependencies):
        """Return GENERAL_ERROR exit code when config file not found."""
        # Arrange
        config_path = tmp_path / "nonexistent.yaml"
        sync_cmd = SyncCommand(
            config_path=str(config_path),
            **mock_dependencies
        )

        # Act
        exit_code = sync_cmd.run()

        # Assert
        assert exit_code == ExitCode.GENERAL_ERROR
        # Should print helpful message (not error) for better UX
        mock_dependencies['output_handler'].print.assert_called()

    def test_general_error_exit_code_on_both_force_flags(self, mock_dependencies):
        """Return GENERAL_ERROR exit code when both force flags used."""
        # Arrange
        sync_cmd = SyncCommand(**mock_dependencies)

        # Act
        exit_code = sync_cmd.run(force_push=True, force_pull=True)

        # Assert
        assert exit_code == ExitCode.GENERAL_ERROR
        mock_dependencies['output_handler'].error.assert_called_with(
            "Cannot use both --forcePush and --forcePull"
        )

    def test_auth_error_exit_code_on_invalid_credentials(
        self, tmp_path, mock_dependencies, sample_config
    ):
        """Return AUTH_ERROR exit code when authentication fails."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        sync_cmd = SyncCommand(
            config_path=str(config_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Mock state manager to raise auth error
                mock_dependencies['state_manager'].load.side_effect = InvalidCredentialsError(
                    user="test_user",
                    endpoint="https://test.atlassian.net"
                )

                # Act
                exit_code = sync_cmd.run()

                # Assert
                assert exit_code == ExitCode.AUTH_ERROR
                mock_dependencies['output_handler'].error.assert_called()
                mock_dependencies['output_handler'].info.assert_called()

    def test_network_error_exit_code_on_api_unreachable(
        self, tmp_path, mock_dependencies, sample_config
    ):
        """Return NETWORK_ERROR exit code when API is unreachable."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        sync_cmd = SyncCommand(
            config_path=str(config_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Mock state manager to raise network error
                mock_dependencies['state_manager'].load.side_effect = APIUnreachableError(
                    "Cannot reach Confluence API"
                )

                # Act
                exit_code = sync_cmd.run()

                # Assert
                assert exit_code == ExitCode.NETWORK_ERROR
                mock_dependencies['output_handler'].error.assert_called()

    def test_network_error_exit_code_on_api_access_error(
        self, tmp_path, mock_dependencies, sample_config
    ):
        """Return NETWORK_ERROR exit code when API access fails."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        sync_cmd = SyncCommand(
            config_path=str(config_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Mock state manager to raise API access error
                mock_dependencies['state_manager'].load.side_effect = APIAccessError(
                    "403 Forbidden"
                )

                # Act
                exit_code = sync_cmd.run()

                # Assert
                assert exit_code == ExitCode.NETWORK_ERROR

    def test_general_error_exit_code_on_config_error(
        self, tmp_path, mock_dependencies
    ):
        """Return GENERAL_ERROR exit code on configuration error."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        sync_cmd = SyncCommand(
            config_path=str(config_path),
            **mock_dependencies
        )

        # Mock config loading to raise ConfigError
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                mock_load.side_effect = ConfigError("Invalid YAML")

                # Act
                exit_code = sync_cmd.run()

                # Assert
                assert exit_code == ExitCode.GENERAL_ERROR
                mock_dependencies['output_handler'].error.assert_called()

    def test_general_error_exit_code_on_cli_error(
        self, tmp_path, mock_dependencies, sample_config
    ):
        """Return GENERAL_ERROR exit code on CLI error."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        sync_cmd = SyncCommand(
            config_path=str(config_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Mock state manager to raise CLI error
                mock_dependencies['state_manager'].load.side_effect = CLIError(
                    "State file corrupted"
                )

                # Act
                exit_code = sync_cmd.run()

                # Assert
                assert exit_code == ExitCode.GENERAL_ERROR

    def test_general_error_exit_code_on_unexpected_exception(
        self, tmp_path, mock_dependencies, sample_config
    ):
        """Return GENERAL_ERROR exit code on unexpected exception."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        sync_cmd = SyncCommand(
            config_path=str(config_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Mock state manager to raise unexpected exception
                mock_dependencies['state_manager'].load.side_effect = RuntimeError(
                    "Unexpected error"
                )

                # Act
                exit_code = sync_cmd.run()

                # Assert
                assert exit_code == ExitCode.GENERAL_ERROR
                mock_dependencies['output_handler'].error.assert_called()

    def test_conflicts_exit_code_on_dry_run_with_conflicts(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Return CONFLICTS exit code when dry run detects conflicts."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Mock _run_dry_run to return CONFLICTS
                with patch.object(sync_cmd, '_run_dry_run') as mock_dry_run:
                    mock_dry_run.return_value = ExitCode.CONFLICTS

                    # Act
                    exit_code = sync_cmd.run(dry_run=True)

                    # Assert
                    assert exit_code == ExitCode.CONFLICTS


class TestSyncCommandDryRunMode:
    """Test cases for SyncCommand dry run mode (UT-SC-02)."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mocked dependencies for SyncCommand."""
        mock_change_detector = Mock()
        # Mock deletion and move detection to return proper objects
        mock_change_detector.detect_deletions.return_value = DeletionResult(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        mock_change_detector.detect_moves.return_value = MoveResult(
            moved_in_confluence=[],
            moved_locally=[]
        )

        return {
            'output_handler': Mock(),
            'state_manager': Mock(),
            'file_mapper': Mock(),
            'change_detector': mock_change_detector,
            'merge_orchestrator': Mock(),
            'authenticator': Mock(),
        }

    @pytest.fixture
    def sample_config(self, tmp_path):
        """Create sample SyncConfig."""
        return SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="123456",
                    local_path=str(tmp_path / "docs"),
                    exclude_page_ids=[],
                )
            ],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=str(tmp_path / ".confluence-sync/temp"),
        )

    @pytest.fixture
    def sample_state(self):
        """Create sample SyncState."""
        return SyncState(last_synced="2024-01-15T10:30:00Z")

    def test_dry_run_displays_preview(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Dry run displays preview of changes without applying them."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                exit_code = sync_cmd.run(dry_run=True)

                # Assert
                assert exit_code == ExitCode.SUCCESS
                mock_dependencies['output_handler'].info.assert_any_call(
                    "Dry run mode - previewing changes..."
                )
                mock_dependencies['output_handler'].print_dryrun_summary.assert_called_once()

    def test_dry_run_does_not_update_state(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Dry run does not update sync state."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                sync_cmd.run(dry_run=True)

                # Assert - state.save should NOT be called in dry run
                mock_dependencies['state_manager'].save.assert_not_called()

    def test_dry_run_returns_success_on_no_conflicts(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Dry run returns SUCCESS when no conflicts detected."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                exit_code = sync_cmd.run(dry_run=True)

                # Assert
                assert exit_code == ExitCode.SUCCESS

    def test_dry_run_calls_display_summary_with_counts(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Dry run calls display_dry_run_summary with correct counts."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                sync_cmd.run(dry_run=True)

                # Assert
                mock_dependencies['output_handler'].print_dryrun_summary.assert_called_once_with(
                    to_push=[],
                    to_pull=[],
                    conflicts=[],
                )

    def test_get_remote_pages_excludes_parent_when_configured(self, tmp_path, mock_dependencies):
        """When exclude_parent=True, _get_remote_pages excludes parent page and its directory from paths.

        This tests the fix for the bug where dry-run preview showed parent folder
        in paths (e.g., docs/Parent-Page/Child.md) when exclude_parent=True.
        The correct behavior is to show docs/Child.md (children at root level).
        """
        # Arrange
        from src.file_mapper.models import PageNode

        config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="parent123",
                    local_path=str(tmp_path / "docs"),
                    exclude_page_ids=[],
                    exclude_parent=True,  # THIS IS THE KEY SETTING
                )
            ],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=str(tmp_path / ".confluence-sync/temp"),
        )

        # Create a mock hierarchy with parent and children
        parent_node = PageNode(
            page_id="parent123",
            title="Parent Page",
            space_key="TEST",
            version=1,
            last_modified="2024-01-15T10:30:00Z",
            parent_id=None,
            children=[
                PageNode(
                    page_id="child1",
                    title="Child One",
                    space_key="TEST",
                    version=1,
                    last_modified="2024-01-15T10:30:00Z",
                    parent_id="parent123",
                    children=[],
                ),
                PageNode(
                    page_id="child2",
                    title="Child Two",
                    space_key="TEST",
                    version=1,
                    last_modified="2024-01-15T10:30:00Z",
                    parent_id="parent123",
                    children=[],
                ),
            ],
        )

        # Mock hierarchy builder to return our test hierarchy
        mock_hierarchy_builder = Mock()
        mock_hierarchy_builder.build_hierarchy.return_value = parent_node

        sync_cmd = SyncCommand(
            config_path=str(tmp_path / "config.yaml"),
            state_path=str(tmp_path / "state.yaml"),
            **mock_dependencies
        )

        with patch('src.file_mapper.hierarchy_builder.HierarchyBuilder') as mock_hb_class:
            mock_hb_class.return_value = mock_hierarchy_builder
            # Act
            result = sync_cmd._get_remote_pages(config)

        # Assert
        # Parent page should NOT be in the results when exclude_parent=True
        assert "parent123" not in result, "Parent page should be excluded"

        # Children SHOULD be in the results
        assert "child1" in result, "Child pages should be included"
        assert "child2" in result, "Child pages should be included"

        # Paths should NOT contain the parent folder "Parent-Page"
        child1_path = result["child1"]["relative_path"]
        child2_path = result["child2"]["relative_path"]

        assert "Parent-Page" not in child1_path, \
            f"Child path should not contain parent folder: {child1_path}"
        assert "Parent-Page" not in child2_path, \
            f"Child path should not contain parent folder: {child2_path}"

        # Paths should be at root level: docs/Child-One.md, docs/Child-Two.md
        assert child1_path.endswith("Child-One.md"), f"Unexpected path: {child1_path}"
        assert child2_path.endswith("Child-Two.md"), f"Unexpected path: {child2_path}"

    def test_get_remote_pages_includes_parent_when_not_excluded(self, tmp_path, mock_dependencies):
        """When exclude_parent=False (default), _get_remote_pages includes parent page."""
        # Arrange
        from src.file_mapper.models import PageNode

        config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="parent123",
                    local_path=str(tmp_path / "docs"),
                    exclude_page_ids=[],
                    exclude_parent=False,  # Default behavior
                )
            ],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=str(tmp_path / ".confluence-sync/temp"),
        )

        # Create a mock hierarchy with parent and children
        parent_node = PageNode(
            page_id="parent123",
            title="Parent Page",
            space_key="TEST",
            version=1,
            last_modified="2024-01-15T10:30:00Z",
            parent_id=None,
            children=[
                PageNode(
                    page_id="child1",
                    title="Child One",
                    space_key="TEST",
                    version=1,
                    last_modified="2024-01-15T10:30:00Z",
                    parent_id="parent123",
                    children=[],
                ),
            ],
        )

        mock_hierarchy_builder = Mock()
        mock_hierarchy_builder.build_hierarchy.return_value = parent_node

        sync_cmd = SyncCommand(
            config_path=str(tmp_path / "config.yaml"),
            state_path=str(tmp_path / "state.yaml"),
            **mock_dependencies
        )

        with patch('src.file_mapper.hierarchy_builder.HierarchyBuilder') as mock_hb_class:
            mock_hb_class.return_value = mock_hierarchy_builder
            # Act
            result = sync_cmd._get_remote_pages(config)

        # Assert
        # Parent page SHOULD be included when exclude_parent=False
        assert "parent123" in result, "Parent page should be included"
        assert "child1" in result, "Child page should be included"

        # Child path SHOULD contain the parent folder
        child1_path = result["child1"]["relative_path"]
        assert "Parent-Page" in child1_path, \
            f"Child path should contain parent folder: {child1_path}"


class TestSyncCommandForceModes:
    """Test cases for SyncCommand force push/pull modes (UT-SC-03)."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mocked dependencies for SyncCommand."""
        mock_change_detector = Mock()
        # Mock deletion and move detection to return proper objects
        mock_change_detector.detect_deletions.return_value = DeletionResult(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        mock_change_detector.detect_moves.return_value = MoveResult(
            moved_in_confluence=[],
            moved_locally=[]
        )

        # Mock file_mapper to return proper SyncResult
        mock_file_mapper = Mock()
        mock_file_mapper.sync_spaces.return_value = SyncResult(
            pushed_count=0,
            pulled_count=0,
            conflict_page_ids=[],
        )

        return {
            'output_handler': Mock(),
            'state_manager': Mock(),
            'file_mapper': mock_file_mapper,
            'change_detector': mock_change_detector,
            'merge_orchestrator': Mock(),
            'authenticator': Mock(),
        }

    @pytest.fixture
    def sample_config(self, tmp_path):
        """Create sample SyncConfig."""
        return SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="123456",
                    local_path=str(tmp_path / "docs"),
                    exclude_page_ids=[],
                )
            ],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=str(tmp_path / ".confluence-sync/temp"),
        )

    @pytest.fixture
    def sample_state(self):
        """Create sample SyncState."""
        return SyncState(last_synced="2024-01-15T10:30:00Z")

    def test_force_push_mode_executes(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Force push mode executes and updates state."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                exit_code = sync_cmd.run(force_push=True)

                # Assert
                assert exit_code == ExitCode.SUCCESS
                mock_dependencies['output_handler'].info.assert_any_call(
                    "Force pushing local changes to Confluence..."
                )
                mock_dependencies['state_manager'].save.assert_called_once()

    def test_force_pull_mode_executes(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Force pull mode executes and updates state."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                exit_code = sync_cmd.run(force_pull=True)

                # Assert
                assert exit_code == ExitCode.SUCCESS
                mock_dependencies['output_handler'].info.assert_any_call(
                    "Force pulling Confluence changes to local..."
                )
                mock_dependencies['state_manager'].save.assert_called_once()

    def test_force_push_displays_summary(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Force push displays summary with push count."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                sync_cmd.run(force_push=True)

                # Assert
                mock_dependencies['output_handler'].print_force_summary.assert_called_once_with(
                    count=0,
                    direction="push",
                )

    def test_force_pull_displays_summary(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Force pull displays summary with pull count."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                sync_cmd.run(force_pull=True)

                # Assert
                mock_dependencies['output_handler'].print_force_summary.assert_called_once_with(
                    count=0,
                    direction="pull",
                )

    def test_force_push_displays_actual_count_from_sync_result(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Force push summary should reflect actual pushed count from SyncResult.

        This test verifies that the sync summary uses actual sync results
        instead of hardcoded zeros (regression test for bug fix).
        """
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        # Mock sync_spaces to return a result with 5 pushed pages
        mock_dependencies['file_mapper'].sync_spaces.return_value = SyncResult(
            pushed_count=5,
            pulled_count=0,
            conflict_page_ids=[],
        )

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                sync_cmd.run(force_push=True)

                # Assert - summary should show 5, not 0
                mock_dependencies['output_handler'].print_force_summary.assert_called_once_with(
                    count=5,
                    direction="push",
                )

    def test_force_push_updates_last_synced(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Force push updates last_synced timestamp in state."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                sync_cmd.run(force_push=True)

                # Assert
                mock_dependencies['state_manager'].save.assert_called_once()
                saved_state = mock_dependencies['state_manager'].save.call_args[0][1]
                assert saved_state.last_synced is not None

    def test_force_pull_updates_last_synced(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Force pull updates last_synced timestamp in state."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                sync_cmd.run(force_pull=True)

                # Assert
                mock_dependencies['state_manager'].save.assert_called_once()
                saved_state = mock_dependencies['state_manager'].save.call_args[0][1]
                assert saved_state.last_synced is not None

    def test_force_push_sets_get_baseline_callback(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Force push should set config.get_baseline for surgical updates.

        This was a bug where force_push didn't set the baseline callback,
        causing all updates to use full replacement instead of surgical updates.
        """
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Track config passed to file_mapper.sync_spaces
        captured_config = None

        def capture_config(config):
            nonlocal captured_config
            captured_config = config
            return Mock(pushed_count=0)

        mock_dependencies['file_mapper'].sync_spaces.side_effect = capture_config

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                sync_cmd.run(force_push=True)

                # Assert - config.get_baseline should be set (not None)
                assert captured_config is not None, "sync_spaces should be called"
                assert captured_config.get_baseline is not None, \
                    "force_push should set get_baseline callback for surgical updates"

    def test_force_pull_sets_get_baseline_callback(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Force pull should set config.get_baseline.

        Ensures baseline callback is available for consistency.
        """
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Track config passed to file_mapper.sync_spaces
        captured_config = None

        def capture_config(config):
            nonlocal captured_config
            captured_config = config
            return Mock(pulled_count=0)

        mock_dependencies['file_mapper'].sync_spaces.side_effect = capture_config

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                sync_cmd.run(force_pull=True)

                # Assert - config.get_baseline should be set (not None)
                assert captured_config is not None, "sync_spaces should be called"
                assert captured_config.get_baseline is not None, \
                    "force_pull should set get_baseline callback"


class TestSyncCommandBidirectionalMode:
    """Test cases for SyncCommand bidirectional sync mode."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mocked dependencies for SyncCommand."""
        mock_change_detector = Mock()
        # Mock deletion and move detection to return proper objects
        mock_change_detector.detect_deletions.return_value = DeletionResult(
            deleted_in_confluence=[],
            deleted_locally=[]
        )
        mock_change_detector.detect_moves.return_value = MoveResult(
            moved_in_confluence=[],
            moved_locally=[]
        )

        return {
            'output_handler': Mock(),
            'state_manager': Mock(),
            'file_mapper': Mock(),
            'change_detector': mock_change_detector,
            'merge_orchestrator': Mock(),
            'authenticator': Mock(),
        }

    @pytest.fixture
    def sample_config(self, tmp_path):
        """Create sample SyncConfig."""
        return SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="123456",
                    local_path=str(tmp_path / "docs"),
                    exclude_page_ids=[],
                )
            ],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=str(tmp_path / ".confluence-sync/temp"),
        )

    @pytest.fixture
    def sample_state(self):
        """Create sample SyncState."""
        return SyncState(last_synced="2024-01-15T10:30:00Z")

    def test_bidirectional_sync_executes(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Bidirectional sync executes and updates state."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                exit_code = sync_cmd.run()

                # Assert
                assert exit_code == ExitCode.SUCCESS
                mock_dependencies['output_handler'].info.assert_any_call(
                    "Starting bidirectional sync..."
                )
                mock_dependencies['state_manager'].save.assert_called_once()

    def test_bidirectional_sync_displays_summary(
        self, tmp_path, mock_dependencies, sample_config, sample_state
    ):
        """Bidirectional sync displays summary with counts."""
        # Arrange
        config_path = tmp_path / "config.yaml"
        state_path = tmp_path / "state.yaml"

        sync_cmd = SyncCommand(
            config_path=str(config_path),
            state_path=str(state_path),
            **mock_dependencies
        )

        # Mock config loading
        with patch('src.cli.sync_command.ConfigLoader.load') as mock_load:
            with patch('src.cli.sync_command.Path') as mock_path_cls:
                mock_load.return_value = sample_config
                mock_dependencies['state_manager'].load.return_value = sample_state

                # Mock Path.exists to return True
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path_cls.return_value = mock_path

                # Act
                sync_cmd.run()

                # Assert
                mock_dependencies['output_handler'].print_summary.assert_called_once()


class TestSyncCommandValidation:
    """Test cases for SyncCommand input validation."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mocked dependencies for SyncCommand."""
        return {
            'output_handler': Mock(),
            'state_manager': Mock(),
        }

    def test_cannot_use_both_force_push_and_force_pull(self, mock_dependencies):
        """Cannot use both --forcePush and --forcePull flags."""
        # Arrange
        sync_cmd = SyncCommand(**mock_dependencies)

        # Act
        exit_code = sync_cmd.run(force_push=True, force_pull=True)

        # Assert
        assert exit_code == ExitCode.GENERAL_ERROR
        mock_dependencies['output_handler'].error.assert_called_with(
            "Cannot use both --forcePush and --forcePull"
        )

    def test_config_file_not_found_shows_helpful_message(
        self, tmp_path, mock_dependencies
    ):
        """Show helpful message when config file not found."""
        # Arrange
        config_path = tmp_path / "nonexistent.yaml"
        sync_cmd = SyncCommand(
            config_path=str(config_path),
            **mock_dependencies
        )

        # Act
        exit_code = sync_cmd.run()

        # Assert
        assert exit_code == ExitCode.GENERAL_ERROR
        # Should print helpful guidance (multiple print calls)
        mock_dependencies['output_handler'].print.assert_called()
        # Verify key message was shown
        print_calls = [str(call) for call in mock_dependencies['output_handler'].print.call_args_list]
        assert any("confluence-sync --init" in str(call) for call in print_calls)

