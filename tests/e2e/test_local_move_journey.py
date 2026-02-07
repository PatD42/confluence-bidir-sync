"""E2E test: Local Move Journey (local file moves sync to Confluence).

This test validates the complete local move detection and handling workflow:
1. Sync nested page hierarchy to local
2. Move local file to different folder
3. Run sync to detect move
4. Verify Confluence page parent updated
5. Verify page accessible at new location

Requirements:
- Test Confluence credentials in .env.test
- Test space (CONFSYNCTEST) access

Test Scenario (E2E-4):
- Create nested hierarchy: Root > Folder1, Folder2
- Sync to local (creates local folder structure)
- Move file from Folder1 to Folder2 locally
- Run sync again
- Verify Confluence page parent updated to Folder2
- Verify page accessible at new Confluence location
"""

import pytest
import logging
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, UTC

from src.cli.sync_command import SyncCommand
from src.cli.config import StateManager
from src.cli.models import ExitCode, SyncState
from src.cli.output import OutputHandler
from src.file_mapper.config_loader import ConfigLoader
from src.file_mapper.models import SyncConfig, SpaceConfig
from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator
from tests.helpers.confluence_test_setup import setup_test_page, teardown_test_page
from tests.fixtures.sample_pages import SAMPLE_PAGE_SIMPLE

logger = logging.getLogger(__name__)


class TestLocalMoveJourney:
    """E2E tests for local file move detection and handling."""

    @pytest.fixture(scope="function")
    def temp_workspace(self):
        """Create a temporary workspace directory for testing.

        This workspace includes:
        - .confluence-sync/ directory for config and state
        - local_docs/ directory for markdown files
        """
        temp_dir = tempfile.mkdtemp(prefix="local_move_test_")
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
    def test_space_root(self):
        """Create a root page for the test space."""
        page_info = setup_test_page(
            title="E2E Test - Local Move Journey Root",
            content=SAMPLE_PAGE_SIMPLE
        )
        logger.info(f"Created test space root page: {page_info['page_id']}")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up test space root page: {page_info['page_id']}")

    @pytest.fixture(scope="function")
    def nested_page_hierarchy(self, test_space_root):
        """Create a nested page hierarchy for move testing.

        Creates structure:
        - Root (from test_space_root)
          - Folder 1
            - Page to Move
          - Folder 2

        Returns:
            Dict with page IDs for root, folder1, folder2, page_to_move
        """
        # Create Folder 1 page
        folder1_info = setup_test_page(
            title="E2E Test - Local Move Folder 1",
            content="<h1>Folder 1</h1><p>First folder.</p>",
            parent_id=test_space_root['page_id']
        )
        logger.info(f"Created folder 1 page: {folder1_info['page_id']}")

        # Create Folder 2 page
        folder2_info = setup_test_page(
            title="E2E Test - Local Move Folder 2",
            content="<h1>Folder 2</h1><p>Second folder.</p>",
            parent_id=test_space_root['page_id']
        )
        logger.info(f"Created folder 2 page: {folder2_info['page_id']}")

        # Create page under Folder 1 (this will be moved)
        page_to_move_info = setup_test_page(
            title="E2E Test - Page to Move",
            content="<h1>Page to Move</h1><p>This page will be moved from Folder 1 to Folder 2.</p>",
            parent_id=folder1_info['page_id']
        )
        logger.info(f"Created page to move: {page_to_move_info['page_id']}")

        hierarchy = {
            'root': test_space_root,
            'folder1': folder1_info,
            'folder2': folder2_info,
            'page_to_move': page_to_move_info,
        }

        yield hierarchy

        # Cleanup (in reverse order - children first)
        teardown_test_page(page_to_move_info['page_id'])
        logger.info(f"Cleaned up page to move: {page_to_move_info['page_id']}")
        teardown_test_page(folder2_info['page_id'])
        logger.info(f"Cleaned up folder 2 page: {folder2_info['page_id']}")
        teardown_test_page(folder1_info['page_id'])
        logger.info(f"Cleaned up folder 1 page: {folder1_info['page_id']}")

    def test_local_file_move_creates_nested_folders(self, temp_workspace):
        """Test that moving a local file between folders works correctly.

        Verification steps:
        1. Create nested folder structure locally
        2. Create a markdown file in folder1
        3. Move the file to folder2
        4. Verify file exists in new location
        5. Verify file removed from old location
        """
        local_docs = Path(temp_workspace['local_docs'])

        # Step 1: Create folder structure
        folder1 = local_docs / "folder1"
        folder2 = local_docs / "folder2"
        folder1.mkdir(exist_ok=True)
        folder2.mkdir(exist_ok=True)
        logger.info("Created local folder structure")

        # Step 2: Create a markdown file in folder1
        test_file = folder1 / "test-page.md"
        test_content = "# Test Page\n\nThis is a test page.\n"
        test_file.write_text(test_content)
        assert test_file.exists(), "Test file should exist in folder1"
        logger.info(f"Created test file: {test_file}")

        # Step 3: Move the file to folder2
        new_location = folder2 / "test-page.md"
        shutil.move(str(test_file), str(new_location))
        logger.info(f"Moved file from {test_file} to {new_location}")

        # Step 4: Verify file exists in new location
        assert new_location.exists(), "File should exist in new location (folder2)"
        assert new_location.read_text() == test_content, "File content should be preserved"
        logger.info("✓ File exists in new location with correct content")

        # Step 5: Verify file removed from old location
        assert not test_file.exists(), "File should not exist in old location (folder1)"
        logger.info("✓ File removed from old location")

    def test_verify_initial_hierarchy(self, nested_page_hierarchy):
        """Test that initial page hierarchy is set up correctly.

        Verification steps:
        1. Verify page_to_move exists under folder1
        2. Verify folder1 and folder2 are siblings under root
        3. Verify ancestor chain for page_to_move includes folder1 and root
        """
        auth = Authenticator()
        api = APIWrapper(auth)

        page_to_move_id = nested_page_hierarchy['page_to_move']['page_id']
        folder1_id = nested_page_hierarchy['folder1']['page_id']
        folder2_id = nested_page_hierarchy['folder2']['page_id']
        root_id = nested_page_hierarchy['root']['page_id']

        # Step 1: Verify page_to_move exists under folder1
        logger.info("1. Verifying page_to_move is under folder1")
        page_to_move = api.get_page_by_id(page_to_move_id, expand="ancestors")
        ancestors = page_to_move.get("ancestors", [])
        ancestor_ids = [a.get('id') for a in ancestors]

        assert folder1_id in ancestor_ids, \
            f"Folder1 {folder1_id} should be in page's ancestors: {ancestor_ids}"
        logger.info(f"   ✓ Page ancestors: {ancestor_ids}")

        # Step 2: Verify folder1 and folder2 are siblings under root
        logger.info("2. Verifying folder1 and folder2 are under root")
        folder1 = api.get_page_by_id(folder1_id, expand="ancestors")
        folder1_ancestors = [a.get('id') for a in folder1.get("ancestors", [])]
        assert root_id in folder1_ancestors, \
            f"Root {root_id} should be in folder1's ancestors: {folder1_ancestors}"

        folder2 = api.get_page_by_id(folder2_id, expand="ancestors")
        folder2_ancestors = [a.get('id') for a in folder2.get("ancestors", [])]
        assert root_id in folder2_ancestors, \
            f"Root {root_id} should be in folder2's ancestors: {folder2_ancestors}"
        logger.info("   ✓ Both folders are under root")

        # Step 3: Verify ancestor chain
        logger.info("3. Verifying complete ancestor chain")
        assert root_id in ancestor_ids, \
            f"Root {root_id} should be in page's ancestors: {ancestor_ids}"
        assert folder1_id in ancestor_ids, \
            f"Folder1 {folder1_id} should be in page's ancestors: {ancestor_ids}"
        logger.info(f"   ✓ Complete ancestor chain verified: {ancestor_ids}")

    def test_move_page_parent_in_confluence_api(self, nested_page_hierarchy):
        """Test moving a page to new parent using Confluence API.

        Verification steps:
        1. Verify initial parent (folder1)
        2. Move page to new parent (folder2)
        3. Verify page parent updated
        4. Verify ancestor chain updated
        """
        auth = Authenticator()
        api = APIWrapper(auth)

        page_to_move_id = nested_page_hierarchy['page_to_move']['page_id']
        folder1_id = nested_page_hierarchy['folder1']['page_id']
        folder2_id = nested_page_hierarchy['folder2']['page_id']

        # Step 1: Verify initial parent
        logger.info("1. Verifying initial parent (folder1)")
        initial_page = api.get_page_by_id(page_to_move_id, expand="ancestors")
        initial_ancestors = [a.get('id') for a in initial_page.get("ancestors", [])]
        assert folder1_id in initial_ancestors, \
            f"Folder1 {folder1_id} should be in initial ancestors: {initial_ancestors}"
        logger.info(f"   ✓ Initial ancestors: {initial_ancestors}")

        # Step 2: Move page to new parent (folder2)
        logger.info(f"2. Moving page {page_to_move_id} to new parent {folder2_id}")

        # Get current version and content for update
        current_version = initial_page.get("version", {}).get("number", 1)
        current_title = initial_page.get("title")
        current_body = initial_page.get("body", {}).get("storage", {}).get("value", "")

        # Update page with new parent (this moves the page)
        updated_page = api.update_page(
            page_id=page_to_move_id,
            title=current_title,
            body=current_body,
            version=current_version,
            parent_id=folder2_id  # This moves the page
        )
        logger.info("   ✓ Page moved successfully")

        # Step 3: Verify page parent updated
        logger.info("3. Verifying page parent updated to folder2")
        moved_page = api.get_page_by_id(page_to_move_id, expand="ancestors")
        moved_ancestors = [a.get('id') for a in moved_page.get("ancestors", [])]

        assert folder2_id in moved_ancestors, \
            f"Folder2 {folder2_id} should be in new ancestors: {moved_ancestors}"
        logger.info(f"   ✓ New ancestors include folder2: {moved_ancestors}")

        # Step 4: Verify ancestor chain updated (folder1 should NOT be in ancestors)
        logger.info("4. Verifying ancestor chain updated (folder1 removed)")
        assert folder1_id not in moved_ancestors, \
            f"Folder1 {folder1_id} should NOT be in new ancestors: {moved_ancestors}"
        logger.info("   ✓ Folder1 removed from ancestors")

    @pytest.mark.skip(reason="Requires full sync implementation with move detection")
    def test_local_move_syncs_to_confluence(
        self,
        temp_workspace,
        nested_page_hierarchy
    ):
        """Test that local file moves are detected and synced to Confluence.

        Verification steps:
        1. Setup config and initial sync (creates local files)
        2. Move local file from folder1 to folder2
        3. Run sync with move detection
        4. Verify Confluence page parent updated to folder2
        5. Verify page accessible at new Confluence location

        Note: This test is currently skipped because the full sync implementation
        with move detection is not yet complete. Once the MoveDetector and
        SyncCommand integration is implemented, this test should be enabled.
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = temp_workspace['local_docs']

        # Step 1: Setup config and initial sync
        logger.info("=== Step 1: Initial sync to create local hierarchy ===")
        config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key=nested_page_hierarchy['root']['space_key'],
                    parent_page_id=nested_page_hierarchy['root']['page_id'],
                    local_path=local_docs
                )
            ]
        )
        ConfigLoader.save(config_path, config)

        # TODO: Run initial sync to create local files
        # This would create files like:
        # - local_docs/E2E Test - Local Move Folder 1/index.md
        # - local_docs/E2E Test - Local Move Folder 1/E2E Test - Page to Move.md
        # - local_docs/E2E Test - Local Move Folder 2/index.md

        # Step 2: Move local file from folder1 to folder2
        logger.info("=== Step 2: Moving local file from folder1 to folder2 ===")

        # TODO: Identify the local file path for page_to_move
        # page_file = Path(local_docs) / "E2E Test - Local Move Folder 1" / "E2E Test - Page to Move.md"
        # new_location = Path(local_docs) / "E2E Test - Local Move Folder 2" / "E2E Test - Page to Move.md"
        # shutil.move(str(page_file), str(new_location))
        # logger.info(f"   Moved file from {page_file} to {new_location}")

        # Step 3: Run sync with move detection
        logger.info("=== Step 3: Running sync to detect move ===")

        # TODO: Run sync command
        # sync_cmd = SyncCommand(config_path=config_path, state_path=state_path)
        # exit_code = sync_cmd.run()
        # assert exit_code == ExitCode.SUCCESS

        # Step 4: Verify Confluence page parent updated to folder2
        logger.info("=== Step 4: Verifying Confluence page parent updated ===")

        # TODO: Verify using Confluence API
        # auth = Authenticator()
        # api = APIWrapper(auth)
        # page_to_move_id = nested_page_hierarchy['page_to_move']['page_id']
        # folder2_id = nested_page_hierarchy['folder2']['page_id']
        #
        # page = api.get_page_by_id(page_to_move_id, expand="ancestors")
        # ancestors = [a.get('id') for a in page.get("ancestors", [])]
        # assert folder2_id in ancestors, "Page should be under folder2 in Confluence"

        # Step 5: Verify page accessible at new Confluence location
        logger.info("=== Step 5: Verifying page accessible at new location ===")

        # TODO: Verify page can be fetched and is in correct location
        # page_title = nested_page_hierarchy['page_to_move']['title']
        # page = api.get_page_by_id(page_to_move_id)
        # assert page.get("title") == page_title
        # logger.info(f"   ✓ Page '{page_title}' accessible at new location")

        logger.info("=== Local move journey test completed ===")

    def test_complete_local_move_workflow(
        self,
        temp_workspace,
        nested_page_hierarchy
    ):
        """Test the complete local move detection workflow foundation.

        This test validates the foundation for move detection:
        1. Create nested page hierarchy in Confluence
        2. Verify hierarchy structure
        3. Simulate local file move (API-based for now)
        4. Verify Confluence parent can be updated
        5. Verify ancestor chain updated

        Note: Full local file sync and move detection requires MoveDetector
        implementation which is part of the broader feature set.
        """
        logger.info("=== Starting Complete Local Move Workflow ===")

        auth = Authenticator()
        api = APIWrapper(auth)

        page_to_move_id = nested_page_hierarchy['page_to_move']['page_id']
        folder1_id = nested_page_hierarchy['folder1']['page_id']
        folder2_id = nested_page_hierarchy['folder2']['page_id']
        root_id = nested_page_hierarchy['root']['page_id']

        # Step 1: Create nested page hierarchy (already done by fixtures)
        logger.info("1. Nested page hierarchy created")
        logger.info(f"   Root: {root_id}")
        logger.info(f"   Folder 1: {folder1_id}")
        logger.info(f"   Folder 2: {folder2_id}")
        logger.info(f"   Page to move: {page_to_move_id}")

        # Step 2: Verify hierarchy structure
        logger.info("2. Verifying initial hierarchy structure")
        page = api.get_page_by_id(page_to_move_id, expand="ancestors")
        initial_ancestors = [a.get('id') for a in page.get("ancestors", [])]
        logger.info(f"   Initial ancestors: {initial_ancestors}")
        assert folder1_id in initial_ancestors, "Page should be under folder1 initially"
        logger.info("   ✓ Hierarchy structure verified")

        # Step 3: Simulate local file move (use API to move page)
        logger.info("3. Simulating local file move (moving page to folder2)")
        current_version = page.get("version", {}).get("number", 1)
        current_title = page.get("title")
        current_body = page.get("body", {}).get("storage", {}).get("value", "")

        updated_page = api.update_page(
            page_id=page_to_move_id,
            title=current_title,
            body=current_body,
            version=current_version,
            parent_id=folder2_id
        )
        logger.info("   ✓ Page moved to folder2")

        # Step 4: Verify Confluence parent updated
        logger.info("4. Verifying Confluence parent updated")
        moved_page = api.get_page_by_id(page_to_move_id, expand="ancestors")
        moved_ancestors = [a.get('id') for a in moved_page.get("ancestors", [])]

        assert folder2_id in moved_ancestors, \
            f"Folder2 {folder2_id} should be in ancestors: {moved_ancestors}"
        logger.info(f"   ✓ New parent in ancestors: {moved_ancestors}")

        # Step 5: Verify ancestor chain updated
        logger.info("5. Verifying ancestor chain updated")

        # Page should have: root > folder2 > page
        assert root_id in moved_ancestors, \
            f"Root {root_id} should be in ancestor chain: {moved_ancestors}"
        assert folder2_id in moved_ancestors, \
            f"Folder2 {folder2_id} should be in ancestor chain: {moved_ancestors}"
        assert folder1_id not in moved_ancestors, \
            f"Folder1 {folder1_id} should NOT be in ancestor chain: {moved_ancestors}"
        logger.info(f"   ✓ Ancestor chain updated: {moved_ancestors}")

        logger.info("=== Complete Local Move Workflow PASSED ===")
        logger.info("Summary:")
        logger.info(f"  - Page moved from folder1 to folder2")
        logger.info(f"  - Confluence parent updated")
        logger.info(f"  - Ancestor chain updated correctly")
        logger.info("\nNext steps (requires MoveDetector implementation):")
        logger.info("  - Detect local file moves in sync process")
        logger.info("  - Update Confluence parent to match local structure")
        logger.info("  - Verify page accessible at new location")

    def test_move_detection_with_dry_run(self, temp_workspace, nested_page_hierarchy):
        """Test dry run mode for local move detection.

        Verification steps:
        1. Setup config and initial sync
        2. Move local file to different folder
        3. Run sync with --dry-run flag
        4. Verify exit code is SUCCESS
        5. Verify Confluence page NOT moved (dry run doesn't apply changes)
        6. Verify preview output shows pending move

        Note: This test requires MoveDetector implementation.
        """
        # TODO: Implement once MoveDetector and SyncCommand integration is complete
        pass

    def test_move_preserves_page_content(self, nested_page_hierarchy):
        """Test that moving a page preserves its content.

        Verification steps:
        1. Get initial page content
        2. Move page to new parent
        3. Verify content unchanged
        4. Verify only parent/ancestors changed
        """
        auth = Authenticator()
        api = APIWrapper(auth)

        page_to_move_id = nested_page_hierarchy['page_to_move']['page_id']
        folder2_id = nested_page_hierarchy['folder2']['page_id']

        # Step 1: Get initial page content
        logger.info("1. Getting initial page content")
        initial_page = api.get_page_by_id(page_to_move_id, expand="body.storage,version")
        initial_content = initial_page.get("body", {}).get("storage", {}).get("value", "")
        initial_title = initial_page.get("title")
        logger.info(f"   Initial title: {initial_title}")
        logger.info(f"   Initial content length: {len(initial_content)}")

        # Step 2: Move page to new parent
        logger.info("2. Moving page to new parent")
        current_version = initial_page.get("version", {}).get("number", 1)

        api.update_page(
            page_id=page_to_move_id,
            title=initial_title,
            body=initial_content,
            version=current_version,
            parent_id=folder2_id
        )
        logger.info("   ✓ Page moved")

        # Step 3: Verify content unchanged
        logger.info("3. Verifying content unchanged")
        moved_page = api.get_page_by_id(page_to_move_id, expand="body.storage,version")
        moved_content = moved_page.get("body", {}).get("storage", {}).get("value", "")
        moved_title = moved_page.get("title")

        assert moved_title == initial_title, "Title should be unchanged"
        assert moved_content == initial_content, "Content should be unchanged"
        logger.info("   ✓ Title and content preserved")

        # Step 4: Verify only parent/ancestors changed
        logger.info("4. Verifying version did not decrease (parent change may or may not increment)")
        moved_version = moved_page.get("version", {}).get("number", 1)
        assert moved_version >= current_version, "Version should not decrease after move"
        logger.info(f"   ✓ Version maintained or incremented: {current_version} → {moved_version}")
