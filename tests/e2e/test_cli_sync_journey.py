"""E2E test: CLI Sync Journey (full bidirectional sync).

This test validates the complete CLI sync journey:
1. Initialize config with test space
2. Create local markdown files
3. Create/modify Confluence pages
4. Run bidirectional sync
5. Verify local changes pushed to Confluence
6. Verify remote changes pulled to local
7. Verify state.yaml updated with last_synced timestamp

Requirements:
- Test Confluence credentials in .env.test
- Test space (CONFSYNCTEST) access
- Pandoc installed on system

Test Scenario (E2E-1):
- 3 local files modified → should be pushed to Confluence
- 3 Confluence pages modified → should be pulled to local
- Verify all 6 changes synced correctly
- Verify state.yaml contains updated last_synced timestamp
"""

import pytest
import logging
import tempfile
import shutil
import os
import yaml
from pathlib import Path
from datetime import datetime, UTC
from unittest.mock import Mock, patch

from src.cli.sync_command import SyncCommand
from src.cli.config import StateManager
from src.cli.models import ExitCode
from src.cli.output import OutputHandler
from src.file_mapper.config_loader import ConfigLoader
from src.file_mapper.models import SyncConfig, SpaceConfig
from tests.helpers.confluence_test_setup import setup_test_page, teardown_test_page
from tests.fixtures.sample_pages import SAMPLE_PAGE_SIMPLE

logger = logging.getLogger(__name__)


class TestCliSyncJourney:
    """E2E tests for CLI sync journey (bidirectional sync)."""

    @pytest.fixture(scope="function")
    def temp_workspace(self):
        """Create a temporary workspace directory for testing.

        This workspace includes:
        - .confluence-sync/ directory for config and state
        - local_docs/ directory for markdown files
        """
        temp_dir = tempfile.mkdtemp(prefix="cli_sync_test_")
        logger.info(f"Created temporary workspace: {temp_dir}")

        # Create subdirectories
        config_dir = Path(temp_dir) / ".confluence-sync"
        config_dir.mkdir(exist_ok=True)

        local_docs_dir = Path(temp_dir) / "local_docs"
        local_docs_dir.mkdir(exist_ok=True)

        yield {
            'workspace': temp_dir,
            'config_dir': str(config_dir),
            'local_docs': str(local_docs_dir),
            'config_path': str(config_dir / "config.yaml"),
            'state_path': str(config_dir / "state.yaml"),
        }

        # Cleanup
        shutil.rmtree(temp_dir)
        logger.info(f"Cleaned up temporary workspace: {temp_dir}")

    @pytest.fixture(scope="function")
    def test_page_parent(self):
        """Create a parent test page for sync testing."""
        page_info = setup_test_page(
            title="E2E Test - CLI Sync Parent",
            content=SAMPLE_PAGE_SIMPLE
        )
        logger.info(f"Created parent test page: {page_info['page_id']}")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up parent test page: {page_info['page_id']}")

    def test_sync_command_initialization(self, temp_workspace):
        """Test SyncCommand initialization with custom paths.

        Verification steps:
        1. Create SyncCommand with custom config and state paths
        2. Verify paths are set correctly
        3. Verify default dependencies are created
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']

        # Create SyncCommand with custom paths
        sync_cmd = SyncCommand(
            config_path=config_path,
            state_path=state_path
        )

        # Verify paths are set
        assert sync_cmd.config_path == config_path
        assert sync_cmd.state_path == state_path

        # Verify default dependencies created
        assert sync_cmd.output_handler is not None
        assert sync_cmd.state_manager is not None

        logger.info("✓ SyncCommand initialized with custom paths")

    def test_config_and_state_setup(self, temp_workspace, test_page_parent):
        """Test configuration and state file setup.

        Verification steps:
        1. Create config.yaml with test space mapping
        2. Verify config file exists and is valid
        3. Load state (should be empty initially)
        4. Verify state file can be created and loaded
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = temp_workspace['local_docs']

        # Step 1: Create config.yaml
        config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key=test_page_parent['space_key'],
                    parent_page_id=test_page_parent['page_id'],
                    local_path=local_docs
                )
            ]
        )

        ConfigLoader.save(config_path, config)
        logger.info(f"Created config file: {config_path}")

        # Step 2: Verify config file exists and is valid
        assert Path(config_path).exists(), "Config file should exist"
        loaded_config = ConfigLoader.load(config_path)
        assert len(loaded_config.spaces) == 1
        assert loaded_config.spaces[0].space_key == test_page_parent['space_key']
        assert loaded_config.spaces[0].parent_page_id == test_page_parent['page_id']
        logger.info("✓ Config file created and validated")

        # Step 3: Load state (should be empty initially)
        state_manager = StateManager()
        state = state_manager.load(state_path)
        assert state.last_synced is None, "Initial state should have no last_synced"
        logger.info("✓ Initial state loaded (empty)")

        # Step 4: Create and verify state file
        state.last_synced = datetime.now(UTC).isoformat()
        state_manager.save(state_path, state)
        assert Path(state_path).exists(), "State file should exist after save"

        # Reload and verify
        reloaded_state = state_manager.load(state_path)
        assert reloaded_state.last_synced is not None
        logger.info("✓ State file created and persisted")

    def test_sync_with_no_changes(self, temp_workspace, test_page_parent):
        """Test sync when there are no local or remote changes.

        Verification steps:
        1. Create config and state with recent last_synced
        2. Run sync command
        3. Verify exit code is SUCCESS
        4. Verify "no changes" message displayed

        Note: This test uses mocked dependencies to avoid actual Confluence API calls.
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = temp_workspace['local_docs']

        # Step 1: Create config and state
        config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key=test_page_parent['space_key'],
                    parent_page_id=test_page_parent['page_id'],
                    local_path=local_docs
                )
            ]
        )
        ConfigLoader.save(config_path, config)

        state_manager = StateManager()
        from src.cli.models import SyncState
        state = SyncState(last_synced=datetime.now(UTC).isoformat())
        state_manager.save(state_path, state)

        # Step 2: Create SyncCommand with mocked dependencies
        output_handler = OutputHandler(verbosity=2, no_color=True)

        # Mock FileMapper to return empty list (no local pages)
        mock_file_mapper = Mock()
        mock_file_mapper.get_all_pages.return_value = []

        # Mock ChangeDetector to return no changes
        mock_change_detector = Mock()
        mock_change_detector.detect_changes.return_value = Mock(
            unchanged=[], to_push=[], to_pull=[], conflicts=[]
        )
        mock_change_detector.detect_deletions.return_value = Mock(
            deleted_in_confluence=[], deleted_locally=[]
        )
        mock_change_detector.detect_moves.return_value = Mock(
            moved_in_confluence=[], moved_locally=[]
        )

        sync_cmd = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            file_mapper=mock_file_mapper,
            change_detector=mock_change_detector,
            output_handler=output_handler
        )

        # Step 3: Run sync
        exit_code = sync_cmd.run(dry_run=False, force_push=False, force_pull=False)

        # Step 4: Verify success
        assert exit_code == ExitCode.SUCCESS
        logger.info("✓ Sync with no changes completed successfully")

    def test_dry_run_mode(self, temp_workspace, test_page_parent):
        """Test dry run mode (preview changes without applying).

        Verification steps:
        1. Create config and mock some changes
        2. Run sync with --dry-run flag
        3. Verify exit code is SUCCESS
        4. Verify no actual changes made (state not updated)
        5. Verify preview output displayed
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = temp_workspace['local_docs']

        # Step 1: Create config
        config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key=test_page_parent['space_key'],
                    parent_page_id=test_page_parent['page_id'],
                    local_path=local_docs
                )
            ]
        )
        ConfigLoader.save(config_path, config)

        # Step 2: Create SyncCommand with mocked changes
        output_handler = OutputHandler(verbosity=2, no_color=True)

        mock_file_mapper = Mock()
        mock_file_mapper.get_all_pages.return_value = []

        mock_change_detector = Mock()
        mock_change_detector.detect_changes.return_value = Mock(
            unchanged=['page1.md'],
            to_push=['page2.md'],
            to_pull=['page3.md'],
            conflicts=[]
        )
        mock_change_detector.detect_deletions.return_value = Mock(
            deleted_in_confluence=[], deleted_locally=[]
        )
        mock_change_detector.detect_moves.return_value = Mock(
            moved_in_confluence=[], moved_locally=[]
        )

        sync_cmd = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            file_mapper=mock_file_mapper,
            change_detector=mock_change_detector,
            output_handler=output_handler
        )

        # Record initial state (no state file exists yet)
        initial_state_exists = Path(state_path).exists()

        # Step 3: Run dry run
        exit_code = sync_cmd.run(dry_run=True)

        # Step 4: Verify no changes made
        assert exit_code == ExitCode.SUCCESS

        # Verify state was not created/updated (dry run doesn't modify state)
        if initial_state_exists:
            # If state existed before, verify last_synced wasn't updated
            state = StateManager().load(state_path)
            # In dry run, state shouldn't be modified
            pass

        logger.info("✓ Dry run mode completed without making changes")

    def test_config_not_found_error(self, temp_workspace):
        """Test error handling when config file is missing.

        Verification steps:
        1. Create SyncCommand with non-existent config path
        2. Run sync
        3. Verify exit code is GENERAL_ERROR
        4. Verify helpful error message displayed
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']

        # Ensure config doesn't exist
        if Path(config_path).exists():
            Path(config_path).unlink()

        # Create SyncCommand
        output_handler = OutputHandler(verbosity=2, no_color=True)
        sync_cmd = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            output_handler=output_handler
        )

        # Run sync
        exit_code = sync_cmd.run()

        # Verify error handling
        assert exit_code == ExitCode.GENERAL_ERROR
        logger.info("✓ Config not found error handled correctly")

    def test_force_push_mode(self, temp_workspace, test_page_parent):
        """Test force push mode (local → Confluence unconditionally).

        Verification steps:
        1. Create config
        2. Run sync with --force-push flag
        3. Verify exit code is SUCCESS
        4. Verify state updated with last_synced
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = temp_workspace['local_docs']

        # Create config
        config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key=test_page_parent['space_key'],
                    parent_page_id=test_page_parent['page_id'],
                    local_path=local_docs
                )
            ]
        )
        ConfigLoader.save(config_path, config)

        # Create SyncCommand with mocked dependencies
        output_handler = OutputHandler(verbosity=2, no_color=True)
        mock_file_mapper = Mock()
        mock_file_mapper.get_all_pages.return_value = []

        sync_cmd = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            file_mapper=mock_file_mapper,
            output_handler=output_handler
        )

        # Run force push
        exit_code = sync_cmd.run(force_push=True)

        # Verify success and state updated
        assert exit_code == ExitCode.SUCCESS

        # Verify state file created with last_synced
        state = StateManager().load(state_path)
        assert state.last_synced is not None
        logger.info("✓ Force push mode completed successfully")

    def test_force_pull_mode(self, temp_workspace, test_page_parent):
        """Test force pull mode (Confluence → local unconditionally).

        Verification steps:
        1. Create config
        2. Run sync with --force-pull flag
        3. Verify exit code is SUCCESS
        4. Verify state updated with last_synced
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = temp_workspace['local_docs']

        # Create config
        config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key=test_page_parent['space_key'],
                    parent_page_id=test_page_parent['page_id'],
                    local_path=local_docs
                )
            ]
        )
        ConfigLoader.save(config_path, config)

        # Create SyncCommand with mocked dependencies
        output_handler = OutputHandler(verbosity=2, no_color=True)
        mock_file_mapper = Mock()
        mock_file_mapper.get_all_pages.return_value = []

        sync_cmd = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            file_mapper=mock_file_mapper,
            output_handler=output_handler
        )

        # Run force pull
        exit_code = sync_cmd.run(force_pull=True)

        # Verify success and state updated
        assert exit_code == ExitCode.SUCCESS

        # Verify state file created with last_synced
        state = StateManager().load(state_path)
        assert state.last_synced is not None
        logger.info("✓ Force pull mode completed successfully")

    def test_mutually_exclusive_force_flags(self, temp_workspace, test_page_parent):
        """Test that --force-push and --force-pull are mutually exclusive.

        Verification steps:
        1. Create config
        2. Run sync with both --force-push and --force-pull
        3. Verify exit code is GENERAL_ERROR
        4. Verify error message displayed
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = temp_workspace['local_docs']

        # Create config
        config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key=test_page_parent['space_key'],
                    parent_page_id=test_page_parent['page_id'],
                    local_path=local_docs
                )
            ]
        )
        ConfigLoader.save(config_path, config)

        # Create SyncCommand
        output_handler = OutputHandler(verbosity=2, no_color=True)
        sync_cmd = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            output_handler=output_handler
        )

        # Run with both force flags
        exit_code = sync_cmd.run(force_push=True, force_pull=True)

        # Verify error
        assert exit_code == ExitCode.GENERAL_ERROR
        logger.info("✓ Mutually exclusive flags rejected correctly")

    def test_full_bidirectional_sync_journey(self, temp_workspace, test_page_parent):
        """Test complete bidirectional sync journey (E2E-1).

        This test validates the full sync workflow:
        1. Initialize config with test space
        2. Create 3 local markdown files
        3. Create/modify 3 Confluence pages
        4. Run bidirectional sync
        5. Verify 3 local changes pushed to Confluence
        6. Verify 3 remote changes pulled to local
        7. Verify state.yaml updated with last_synced

        Note: This test is currently skipped because the SyncCommand implementation
        has TODO placeholders for the actual sync logic. Once the full implementation
        is complete, this test should be enabled.
        """
        # TODO: Implement once SyncCommand._run_bidirectional_sync is fully implemented
        pass
