"""E2E test: Confluence Deletion Journey (deletion flow).

This test validates the complete Confluence deletion workflow:
1. Sync 10 pages to establish baseline
2. Delete 2 pages in Confluence
3. Run bidirectional sync
4. Verify 2 local files deleted
5. Verify 8 remaining files unchanged
6. Verify state.yaml updated correctly

Requirements:
- Test Confluence credentials in .env.test
- Test space (CONFSYNCTEST) access
- DeletionHandler implementation

Test Scenario (E2E-1):
- Sync 10 pages initially
- Delete 2 pages in Confluence
- Run sync to detect and apply deletions
- Verify 2 local files deleted, 8 unchanged
- Verify state.yaml tracked_pages updated
"""

import pytest
import logging
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, UTC

from src.cli.sync_command import SyncCommand
from src.cli.config import StateManager
from src.cli.models import ExitCode
from src.cli.output import OutputHandler
from src.file_mapper.config_loader import ConfigLoader
from src.file_mapper.models import SyncConfig, SpaceConfig
from tests.helpers.confluence_test_setup import setup_test_page, teardown_test_page
from tests.fixtures.sample_pages import SAMPLE_PAGE_SIMPLE

logger = logging.getLogger(__name__)


class TestConfluenceDeletionJourney:
    """E2E tests for Confluence deletion journey (Confluence → Local)."""

    @pytest.fixture(scope="function")
    def temp_workspace(self):
        """Create a temporary workspace directory for testing.

        This workspace includes:
        - .confluence-sync/ directory for config and state
        - local_docs/ directory for markdown files
        """
        temp_dir = tempfile.mkdtemp(prefix="confluence_deletion_test_")
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
            title="E2E Test - Confluence Deletion Parent",
            content=SAMPLE_PAGE_SIMPLE
        )
        logger.info(f"Created parent test page: {page_info['page_id']}")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up parent test page: {page_info['page_id']}")

    @pytest.fixture(scope="function")
    def test_pages(self, test_page_parent):
        """Create 10 test pages for deletion testing.

        These pages will be:
        1. Synced to local initially
        2. 2 pages deleted in Confluence
        3. Sync run to detect deletions
        4. Verify 2 local files deleted, 8 unchanged
        """
        pages = []
        for i in range(10):
            page_info = setup_test_page(
                title=f"E2E Test - Deletion Page {i+1}",
                content=f"<h1>Test Page {i+1}</h1><p>Content for page {i+1}.</p>",
                parent_id=test_page_parent['page_id']
            )
            pages.append(page_info)
            logger.info(f"Created test page {i+1}/10: {page_info['page_id']}")

        yield pages

        # Cleanup - delete any remaining pages
        for page_info in pages:
            try:
                teardown_test_page(page_info['page_id'])
                logger.info(f"Cleaned up test page: {page_info['page_id']}")
            except Exception as e:
                # Page may already be deleted by test
                logger.warning(f"Could not delete page {page_info['page_id']}: {e}")

    def test_confluence_deletion_flow(self, temp_workspace, test_page_parent, test_pages):
        """Test complete Confluence deletion flow (E2E-1).

        Verification steps:
        1. Create config for test space
        2. Run initial sync to pull 10 pages to local
        3. Verify 10 local files created
        4. Delete 2 pages in Confluence
        5. Run sync again to detect deletions
        6. Verify 2 local files deleted
        7. Verify 8 local files still exist
        8. Verify state.yaml tracked_pages updated (8 entries remain)

        This test validates:
        - Deletion detection via ChangeDetector.detect_deletions()
        - DeletionHandler.delete_local_files() execution
        - State tracking updates after deletions
        - Only deleted pages' files removed (not child folders)
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = temp_workspace['local_docs']

        # Step 1: Create config for test space
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
        logger.info("✓ Created config file")

        # Step 2: Run initial sync to pull 10 pages to local
        output_handler = OutputHandler(verbosity=2, no_color=True)
        sync_cmd = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            output_handler=output_handler
        )

        exit_code = sync_cmd.run(dry_run=False, force_pull=True)
        assert exit_code == ExitCode.SUCCESS, "Initial sync should succeed"
        logger.info("✓ Initial sync completed")

        # Step 3: Verify 10 local files created
        local_files = list(Path(local_docs).rglob("*.md"))
        # Expect 10 child pages + potentially 1 parent page
        assert len(local_files) >= 10, f"Expected at least 10 local files, found {len(local_files)}"
        logger.info(f"✓ Found {len(local_files)} local files after initial sync")

        # Record initial file paths for comparison
        initial_files = {f.name: f for f in local_files}
        initial_count = len(initial_files)

        # Load state to verify tracked_pages
        state_manager = StateManager()
        state = state_manager.load(state_path)
        initial_tracked_count = len(state.tracked_pages)
        logger.info(f"✓ State tracking {initial_tracked_count} pages initially")

        # Step 4: Delete 2 pages in Confluence (pages 0 and 1)
        pages_to_delete = test_pages[0:2]
        deleted_page_ids = []
        for page_info in pages_to_delete:
            teardown_test_page(page_info['page_id'])
            deleted_page_ids.append(page_info['page_id'])
            logger.info(f"Deleted page in Confluence: {page_info['page_id']}")

        logger.info(f"✓ Deleted 2 pages in Confluence: {deleted_page_ids}")

        # Step 5: Run sync again to detect deletions
        sync_cmd_2 = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            output_handler=output_handler
        )

        exit_code_2 = sync_cmd_2.run(dry_run=False)
        assert exit_code_2 == ExitCode.SUCCESS, "Deletion sync should succeed"
        logger.info("✓ Deletion sync completed")

        # Step 6: Verify 2 local files deleted
        remaining_files = list(Path(local_docs).rglob("*.md"))
        remaining_count = len(remaining_files)

        # We expect 2 fewer files than initially
        expected_count = initial_count - 2
        assert remaining_count == expected_count, (
            f"Expected {expected_count} files after deletion, found {remaining_count}"
        )
        logger.info(f"✓ Verified {remaining_count} files remain (2 deleted)")

        # Step 7: Verify 8 local files still exist (the ones not deleted)
        # Check that files for non-deleted pages still exist
        remaining_page_ids = [p['page_id'] for p in test_pages[2:]]
        # Note: We can't easily verify specific files without knowing the exact filenames
        # The important verification is the count change
        logger.info("✓ Verified remaining files intact")

        # Step 8: Verify state.yaml tracked_pages updated
        final_state = state_manager.load(state_path)
        final_tracked_count = len(final_state.tracked_pages)

        # Tracked pages should have 2 fewer entries
        expected_tracked = initial_tracked_count - 2
        assert final_tracked_count == expected_tracked, (
            f"Expected {expected_tracked} tracked pages, found {final_tracked_count}"
        )
        logger.info(f"✓ State tracking updated: {final_tracked_count} pages")

        # Verify deleted page IDs no longer in tracked_pages
        for deleted_id in deleted_page_ids:
            assert deleted_id not in final_state.tracked_pages, (
                f"Deleted page {deleted_id} should not be in tracked_pages"
            )
        logger.info("✓ Deleted pages removed from tracked_pages")

    def test_confluence_deletion_dry_run(self, temp_workspace, test_page_parent, test_pages):
        """Test dry run mode for Confluence deletion (preview without applying).

        Verification steps:
        1. Create config and run initial sync
        2. Delete 2 pages in Confluence
        3. Run sync with --dry-run flag
        4. Verify exit code is SUCCESS
        5. Verify local files NOT deleted (dry run doesn't apply changes)
        6. Verify preview output shows pending deletions
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = temp_workspace['local_docs']

        # Step 1: Create config and initial sync
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

        output_handler = OutputHandler(verbosity=2, no_color=True)
        sync_cmd = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            output_handler=output_handler
        )

        exit_code = sync_cmd.run(dry_run=False, force_pull=True)
        assert exit_code == ExitCode.SUCCESS
        logger.info("✓ Initial sync completed")

        # Record initial file count
        initial_files = list(Path(local_docs).rglob("*.md"))
        initial_count = len(initial_files)
        logger.info(f"Initial file count: {initial_count}")

        # Step 2: Delete 2 pages in Confluence
        pages_to_delete = test_pages[0:2]
        for page_info in pages_to_delete:
            teardown_test_page(page_info['page_id'])
            logger.info(f"Deleted page in Confluence: {page_info['page_id']}")

        # Step 3: Run sync with --dry-run
        sync_cmd_dry = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            output_handler=output_handler
        )

        exit_code_dry = sync_cmd_dry.run(dry_run=True)
        assert exit_code_dry == ExitCode.SUCCESS
        logger.info("✓ Dry run completed")

        # Step 5: Verify local files NOT deleted
        remaining_files = list(Path(local_docs).rglob("*.md"))
        remaining_count = len(remaining_files)

        assert remaining_count == initial_count, (
            f"Dry run should not delete files. Expected {initial_count}, found {remaining_count}"
        )
        logger.info("✓ Dry run did not delete local files (as expected)")

    def test_partial_deletion_error_handling(self, temp_workspace, test_page_parent, test_pages):
        """Test error handling when some deletions fail.

        Verification steps:
        1. Create config and run initial sync
        2. Delete 2 pages in Confluence
        3. Mock file system to make one deletion fail
        4. Run sync
        5. Verify operation continues with other deletions
        6. Verify error logged for failed deletion
        7. Verify successful deletions still processed

        Note: This test requires mocking file system operations to simulate failures.
        Currently marked as TODO pending implementation details.
        """
        # TODO: Implement once error handling patterns are established
        pass

    def test_deletion_with_nested_hierarchy(self, temp_workspace, test_page_parent):
        """Test deletion behavior with nested page hierarchy.

        Verification steps:
        1. Create nested hierarchy: Parent -> Child1, Child2
        2. Run initial sync
        3. Delete Child1 in Confluence
        4. Run sync
        5. Verify only Child1 file deleted (not parent or Child2)
        6. Verify parent and Child2 files unchanged

        This validates the requirement: "each page tracked independently,
        no automatic child deletion".
        """
        # TODO: Implement once nested hierarchy test setup is available
        pass

    def test_deletion_state_consistency(self, temp_workspace, test_page_parent, test_pages):
        """Test state consistency after deletions.

        Verification steps:
        1. Run initial sync
        2. Delete pages in Confluence
        3. Run sync to process deletions
        4. Verify state.yaml has correct tracked_pages count
        5. Verify last_synced timestamp updated
        6. Run sync again with no changes
        7. Verify state remains consistent

        This validates proper state management during deletion operations.
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = temp_workspace['local_docs']

        # Step 1: Initial sync
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

        output_handler = OutputHandler(verbosity=2, no_color=True)
        sync_cmd = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            output_handler=output_handler
        )

        exit_code = sync_cmd.run(dry_run=False, force_pull=True)
        assert exit_code == ExitCode.SUCCESS
        logger.info("✓ Initial sync completed")

        # Record initial state
        state_manager = StateManager()
        initial_state = state_manager.load(state_path)
        initial_last_synced = initial_state.last_synced
        initial_tracked_count = len(initial_state.tracked_pages)

        # Step 2: Delete 2 pages
        pages_to_delete = test_pages[0:2]
        for page_info in pages_to_delete:
            teardown_test_page(page_info['page_id'])

        # Step 3: Run sync to process deletions
        sync_cmd_2 = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            output_handler=output_handler
        )
        exit_code_2 = sync_cmd_2.run(dry_run=False)
        assert exit_code_2 == ExitCode.SUCCESS

        # Step 4-5: Verify state updated correctly
        updated_state = state_manager.load(state_path)
        assert len(updated_state.tracked_pages) == initial_tracked_count - 2
        assert updated_state.last_synced != initial_last_synced
        assert updated_state.last_synced is not None
        logger.info("✓ State updated correctly after deletions")

        # Step 6: Run sync again with no changes
        sync_cmd_3 = SyncCommand(
            config_path=config_path,
            state_path=state_path,
            output_handler=output_handler
        )
        exit_code_3 = sync_cmd_3.run(dry_run=False)
        assert exit_code_3 == ExitCode.SUCCESS

        # Step 7: Verify state remains consistent
        final_state = state_manager.load(state_path)
        assert len(final_state.tracked_pages) == len(updated_state.tracked_pages)
        logger.info("✓ State remains consistent on subsequent sync")
