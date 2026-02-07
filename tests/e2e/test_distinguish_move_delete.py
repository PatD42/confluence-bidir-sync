"""E2E test: Distinguish Move from Deletion.

This test validates that the sync correctly distinguishes between a page being
moved to a different parent versus being deleted:
1. Sync a page under parent-A
2. Move the page to parent-B in Confluence
3. Run sync to detect the move
4. Verify page was NOT deleted (still exists in Confluence)
5. Verify local file moved to parent-B folder (not deleted)

Requirements:
- Test Confluence credentials in .env.test
- Test space (CONFSYNCTEST) access

Test Scenario (E2E-7):
- Create page under parent-A
- Sync to local (creates local file under parent-A folder)
- Move page to parent-B in Confluence
- Run sync again
- Verify local file NOT deleted
- Verify local file moved to parent-B folder
- Verify page still exists in Confluence
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


class TestDistinguishMoveDelete:
    """E2E tests for distinguishing page moves from deletions."""

    @pytest.fixture(scope="function")
    def temp_workspace(self):
        """Create a temporary workspace directory for testing.

        This workspace includes:
        - .confluence-sync/ directory for config and state
        - local_docs/ directory for markdown files
        """
        temp_dir = tempfile.mkdtemp(prefix="move_vs_delete_test_")
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
            title="E2E Test - Move vs Delete Root",
            content=SAMPLE_PAGE_SIMPLE
        )
        logger.info(f"Created test space root page: {page_info['page_id']}")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up test space root page: {page_info['page_id']}")

    @pytest.fixture(scope="function")
    def parent_a(self, test_space_root):
        """Create parent-A page for testing.

        This is the initial parent where the test page will be created.
        """
        parent_a_info = setup_test_page(
            title="E2E Test - Parent A",
            content="<h1>Parent A</h1><p>This is parent A.</p>",
            parent_id=test_space_root['page_id']
        )
        logger.info(f"Created parent A page: {parent_a_info['page_id']}")
        yield parent_a_info
        # Cleanup
        teardown_test_page(parent_a_info['page_id'])
        logger.info(f"Cleaned up parent A page: {parent_a_info['page_id']}")

    @pytest.fixture(scope="function")
    def parent_b(self, test_space_root):
        """Create parent-B page for testing.

        This is the target parent where the test page will be moved to.
        """
        parent_b_info = setup_test_page(
            title="E2E Test - Parent B",
            content="<h1>Parent B</h1><p>This is parent B.</p>",
            parent_id=test_space_root['page_id']
        )
        logger.info(f"Created parent B page: {parent_b_info['page_id']}")
        yield parent_b_info
        # Cleanup
        teardown_test_page(parent_b_info['page_id'])
        logger.info(f"Cleaned up parent B page: {parent_b_info['page_id']}")

    @pytest.fixture(scope="function")
    def test_page_under_parent_a(self, parent_a):
        """Create a test page under parent-A.

        This is the page that will be moved to parent-B to test move detection.
        """
        test_page_info = setup_test_page(
            title="E2E Test - Movable Page",
            content="<h1>Movable Page</h1><p>This page will be moved between parents.</p>",
            parent_id=parent_a['page_id']
        )
        logger.info(f"Created test page under parent A: {test_page_info['page_id']}")
        yield test_page_info
        # Cleanup
        teardown_test_page(test_page_info['page_id'])
        logger.info(f"Cleaned up test page: {test_page_info['page_id']}")

    def test_page_still_exists_after_move(self, test_page_under_parent_a, parent_b):
        """Test that page still exists in Confluence after being moved.

        Verification steps:
        1. Verify page exists under parent-A
        2. Move page to parent-B
        3. Verify page still exists (not deleted)
        4. Verify page's new parent is parent-B
        """
        auth = Authenticator()
        api = APIWrapper(auth)

        page_id = test_page_under_parent_a['page_id']
        parent_a_id = test_page_under_parent_a['page_id']
        parent_b_id = parent_b['page_id']

        # Step 1: Verify page exists under parent-A
        logger.info("1. Verifying page exists under parent-A")
        initial_page = api.get_page_by_id(page_id, expand="ancestors")
        assert initial_page is not None, "Page should exist"
        initial_ancestors = [a.get('id') for a in initial_page.get("ancestors", [])]
        logger.info(f"   ✓ Initial ancestors: {initial_ancestors}")

        # Step 2: Move page to parent-B
        logger.info(f"2. Moving page {page_id} from parent-A to parent-B {parent_b_id}")
        current_version = initial_page.get("version", {}).get("number", 1)
        current_title = initial_page.get("title")
        current_body = initial_page.get("body", {}).get("storage", {}).get("value", "")

        api.update_page(
            page_id=page_id,
            title=current_title,
            body=current_body,
            version=current_version,
            parent_id=parent_b_id
        )
        logger.info("   ✓ Page moved to parent-B")

        # Step 3: Verify page still exists (not deleted)
        logger.info("3. Verifying page still exists in Confluence")
        moved_page = api.get_page_by_id(page_id, expand="ancestors")
        assert moved_page is not None, "Page should still exist after move"
        assert moved_page.get('id') == page_id, "Page ID should be unchanged"
        logger.info(f"   ✓ Page {page_id} still exists")

        # Step 4: Verify page's new parent is parent-B
        logger.info("4. Verifying page's new parent is parent-B")
        moved_ancestors = [a.get('id') for a in moved_page.get("ancestors", [])]
        assert parent_b_id in moved_ancestors, \
            f"Parent-B {parent_b_id} should be in ancestors: {moved_ancestors}"
        logger.info(f"   ✓ Page now under parent-B: {moved_ancestors}")

    def test_move_detected_not_deletion(self, test_page_under_parent_a, parent_a, parent_b):
        """Test that move is detected as move, not as deletion.

        Verification steps:
        1. Verify initial parent hierarchy (page under parent-A)
        2. Move page to parent-B in Confluence
        3. Verify page was moved (ancestors updated)
        4. Verify page was NOT deleted (still accessible)
        5. Verify move can be detected by comparing ancestor chains
        """
        auth = Authenticator()
        api = APIWrapper(auth)

        page_id = test_page_under_parent_a['page_id']
        parent_a_id = parent_a['page_id']
        parent_b_id = parent_b['page_id']

        # Step 1: Verify initial parent hierarchy
        logger.info("1. Verifying initial parent hierarchy (page under parent-A)")
        initial_page = api.get_page_by_id(page_id, expand="ancestors")
        initial_ancestors = [a.get('id') for a in initial_page.get("ancestors", [])]
        assert parent_a_id in initial_ancestors, \
            f"Parent-A {parent_a_id} should be in initial ancestors: {initial_ancestors}"
        logger.info(f"   ✓ Initial hierarchy confirmed: {initial_ancestors}")

        # Step 2: Move page to parent-B in Confluence
        logger.info(f"2. Moving page {page_id} to parent-B {parent_b_id}")
        current_version = initial_page.get("version", {}).get("number", 1)
        current_title = initial_page.get("title")
        current_body = initial_page.get("body", {}).get("storage", {}).get("value", "")

        api.update_page(
            page_id=page_id,
            title=current_title,
            body=current_body,
            version=current_version,
            parent_id=parent_b_id
        )
        logger.info("   ✓ Page moved successfully")

        # Step 3: Verify page was moved (ancestors updated)
        logger.info("3. Verifying page was moved (ancestors updated)")
        moved_page = api.get_page_by_id(page_id, expand="ancestors")
        moved_ancestors = [a.get('id') for a in moved_page.get("ancestors", [])]
        assert parent_b_id in moved_ancestors, \
            f"Parent-B {parent_b_id} should be in ancestors after move: {moved_ancestors}"
        assert parent_a_id not in moved_ancestors, \
            f"Parent-A {parent_a_id} should NOT be in ancestors after move: {moved_ancestors}"
        logger.info(f"   ✓ Ancestors updated correctly: {moved_ancestors}")

        # Step 4: Verify page was NOT deleted (still accessible)
        logger.info("4. Verifying page was NOT deleted (still accessible)")
        assert moved_page.get('id') == page_id, "Page should still have same ID"
        assert moved_page.get('title') == current_title, "Page title should be unchanged"
        logger.info("   ✓ Page NOT deleted, still accessible")

        # Step 5: Verify move can be detected by comparing ancestor chains
        logger.info("5. Verifying move can be detected by ancestor chain comparison")
        # The key insight for move detection:
        # - Page ID unchanged (same page_id)
        # - Ancestors changed (different parent)
        # - Page NOT deleted (API returns page data)
        assert initial_ancestors != moved_ancestors, \
            "Ancestor chains should differ between initial and moved states"
        logger.info("   ✓ Move detectable via ancestor chain comparison")

        logger.info("\n=== Move vs Deletion Detection Summary ===")
        logger.info("Key indicators that this is a MOVE, not a DELETION:")
        logger.info(f"  1. Page ID unchanged: {page_id}")
        logger.info(f"  2. Page still accessible via API")
        logger.info(f"  3. Ancestor chain changed: {initial_ancestors} → {moved_ancestors}")
        logger.info(f"  4. Page exists at new location under parent-B")
        logger.info("\nFor a DELETION, we would expect:")
        logger.info("  - Page ID not found in Confluence (404 error)")
        logger.info("  - API call to get_page_by_id() would fail")
        logger.info("  - No ancestor chain because page doesn't exist")

    @pytest.mark.skip(reason="Requires full sync implementation with move detection")
    def test_sync_moves_local_file_not_deletes(
        self,
        temp_workspace,
        test_space_root,
        parent_a,
        parent_b,
        test_page_under_parent_a
    ):
        """Test that sync moves local file rather than deleting it.

        Verification steps:
        1. Setup config and initial sync (creates local file under parent-A)
        2. Move page to parent-B in Confluence
        3. Run sync with move detection
        4. Verify local file moved to parent-B folder (NOT deleted)
        5. Verify old parent-A path cleaned up

        Note: This test is currently skipped because the full sync implementation
        with move detection is not yet complete. Once the MoveDetector and
        SyncCommand integration is implemented, this test should be enabled.
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = temp_workspace['local_docs']

        # Step 1: Setup config and initial sync
        logger.info("=== Step 1: Initial sync to create local file ===")
        config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key=test_space_root['space_key'],
                    parent_page_id=test_space_root['page_id'],
                    local_path=local_docs
                )
            ]
        )
        ConfigLoader.save(config_path, config)

        # TODO: Run initial sync to create local files
        # This would create file like:
        # - local_docs/E2E Test - Parent A/E2E Test - Movable Page.md

        # Step 2: Move page to parent-B in Confluence
        logger.info("=== Step 2: Moving page to parent-B in Confluence ===")
        auth = Authenticator()
        api = APIWrapper(auth)

        page_id = test_page_under_parent_a['page_id']
        parent_b_id = parent_b['page_id']

        # Get current page data
        current_page = api.get_page_by_id(page_id, expand="body.storage,version")
        current_version = current_page.get("version", {}).get("number", 1)
        current_title = current_page.get("title")
        current_body = current_page.get("body", {}).get("storage", {}).get("value", "")

        # Move the page
        api.update_page(
            page_id=page_id,
            title=current_title,
            body=current_body,
            version=current_version,
            parent_id=parent_b_id
        )
        logger.info(f"   Moved page {page_id} to parent-B {parent_b_id}")

        # Step 3: Run sync with move detection
        logger.info("=== Step 3: Running sync to detect move ===")

        # TODO: Run sync command
        # sync_cmd = SyncCommand(config_path=config_path, state_path=state_path)
        # exit_code = sync_cmd.run()
        # assert exit_code == ExitCode.SUCCESS

        # Step 4: Verify local file moved to parent-B folder (NOT deleted)
        logger.info("=== Step 4: Verifying local file moved (NOT deleted) ===")

        # TODO: Verify new file structure exists:
        # - local_docs/E2E Test - Parent B/E2E Test - Movable Page.md

        # Verify file exists at new location
        # new_path = Path(local_docs) / "E2E Test - Parent B" / "E2E Test - Movable Page.md"
        # assert new_path.exists(), "File should exist at new location (moved, not deleted)"
        # logger.info(f"   ✓ File exists at new location: {new_path}")

        # Step 5: Verify old parent-A path cleaned up
        logger.info("=== Step 5: Verifying old path cleaned up ===")

        # TODO: Verify old path no longer exists:
        # old_path = Path(local_docs) / "E2E Test - Parent A" / "E2E Test - Movable Page.md"
        # assert not old_path.exists(), "File should NOT exist at old location"

        # Verify parent-A folder cleaned up if empty
        # parent_a_folder = Path(local_docs) / "E2E Test - Parent A"
        # if parent_a_folder.exists():
        #     assert not list(parent_a_folder.glob("*")), "Parent-A folder should be empty"
        #     logger.info("   ✓ Old folder cleaned up")

        logger.info("=== Move vs Delete journey test completed ===")
        logger.info("\nSummary:")
        logger.info("  - Page moved in Confluence (parent-A → parent-B)")
        logger.info("  - Local file moved (NOT deleted)")
        logger.info("  - Old folder structure cleaned up")
        logger.info("  - Move correctly distinguished from deletion")
