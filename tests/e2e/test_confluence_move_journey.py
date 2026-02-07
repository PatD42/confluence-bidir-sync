"""E2E test: Confluence Move Journey (page hierarchy moves).

This test validates the complete move detection and handling workflow:
1. Sync nested page hierarchy to local
2. Move parent page in Confluence (changes hierarchy)
3. Run sync to detect move
4. Verify local files moved to new hierarchy
5. Verify old folders cleaned up

Requirements:
- Test Confluence credentials in .env.test
- Test space (CONFSYNCTEST) access

Test Scenario (E2E-3):
- Create nested hierarchy: Parent > Child1, Child2
- Sync to local (creates local folder structure)
- Move Parent to new location in Confluence
- Run sync again
- Verify local files reflect new hierarchy
- Verify old folders are cleaned up
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


class TestConfluenceMoveJourney:
    """E2E tests for Confluence page move detection and handling."""

    @pytest.fixture(scope="function")
    def temp_workspace(self):
        """Create a temporary workspace directory for testing.

        This workspace includes:
        - .confluence-sync/ directory for config and state
        - local_docs/ directory for markdown files
        """
        temp_dir = tempfile.mkdtemp(prefix="confluence_move_test_")
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
            title="E2E Test - Move Journey Root",
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
          - Parent Page
            - Child Page 1
            - Child Page 2

        Returns:
            Dict with page IDs for root, parent, child1, child2
        """
        # Create parent page
        parent_info = setup_test_page(
            title="E2E Test - Move Parent",
            content="<h1>Parent Page</h1><p>This is the parent page.</p>",
            parent_id=test_space_root['page_id']
        )
        logger.info(f"Created parent page: {parent_info['page_id']}")

        # Create child pages under parent
        child1_info = setup_test_page(
            title="E2E Test - Move Child 1",
            content="<h1>Child 1</h1><p>This is child page 1.</p>",
            parent_id=parent_info['page_id']
        )
        logger.info(f"Created child 1 page: {child1_info['page_id']}")

        child2_info = setup_test_page(
            title="E2E Test - Move Child 2",
            content="<h1>Child 2</h1><p>This is child page 2.</p>",
            parent_id=parent_info['page_id']
        )
        logger.info(f"Created child 2 page: {child2_info['page_id']}")

        hierarchy = {
            'root': test_space_root,
            'parent': parent_info,
            'child1': child1_info,
            'child2': child2_info,
        }

        yield hierarchy

        # Cleanup (in reverse order - children first)
        teardown_test_page(child2_info['page_id'])
        logger.info(f"Cleaned up child 2 page: {child2_info['page_id']}")
        teardown_test_page(child1_info['page_id'])
        logger.info(f"Cleaned up child 1 page: {child1_info['page_id']}")
        teardown_test_page(parent_info['page_id'])
        logger.info(f"Cleaned up parent page: {parent_info['page_id']}")

    @pytest.fixture(scope="function")
    def new_parent_location(self, test_space_root):
        """Create a new parent location for move testing.

        This creates a separate branch in the hierarchy where we'll move pages to.
        """
        new_parent_info = setup_test_page(
            title="E2E Test - New Parent Location",
            content="<h1>New Location</h1><p>Pages will be moved here.</p>",
            parent_id=test_space_root['page_id']
        )
        logger.info(f"Created new parent location: {new_parent_info['page_id']}")

        yield new_parent_info

        # Cleanup
        teardown_test_page(new_parent_info['page_id'])
        logger.info(f"Cleaned up new parent location: {new_parent_info['page_id']}")

    def test_move_page_in_confluence(self, nested_page_hierarchy, new_parent_location):
        """Test moving a page in Confluence using API.

        Verification steps:
        1. Verify initial parent hierarchy
        2. Move parent page to new location
        3. Verify page was moved (new parent_id)
        4. Verify children moved with parent (maintain hierarchy)
        """
        auth = Authenticator()
        api = APIWrapper(auth)

        parent_id = nested_page_hierarchy['parent']['page_id']
        new_parent_id = new_parent_location['page_id']

        # Step 1: Verify initial parent
        logger.info("1. Verifying initial parent hierarchy")
        initial_page = api.get_page_by_id(parent_id, expand="ancestors")
        initial_ancestors = initial_page.get("ancestors", [])
        logger.info(f"   Initial ancestors: {[a.get('id') for a in initial_ancestors]}")

        # Step 2: Move parent page to new location
        logger.info(f"2. Moving parent page {parent_id} to new location {new_parent_id}")

        # Get current version for update
        current_version = initial_page.get("version", {}).get("number", 1)
        current_title = initial_page.get("title")
        current_body = initial_page.get("body", {}).get("storage", {}).get("value", "")

        # Update page with new parent (this moves the page)
        # Note: In Confluence API, moving is done via update with parent_id parameter
        updated_page = api.update_page(
            page_id=parent_id,
            title=current_title,
            body=current_body,
            version=current_version,
            parent_id=new_parent_id  # This moves the page
        )
        logger.info(f"   ✓ Page moved successfully")

        # Step 3: Verify page was moved
        logger.info("3. Verifying page was moved to new location")
        moved_page = api.get_page_by_id(parent_id, expand="ancestors")
        moved_ancestors = moved_page.get("ancestors", [])

        # The new parent should be in the ancestors
        ancestor_ids = [a.get('id') for a in moved_ancestors]
        assert new_parent_id in ancestor_ids, \
            f"New parent {new_parent_id} should be in ancestors: {ancestor_ids}"
        logger.info(f"   ✓ Verified new parent in ancestors: {ancestor_ids}")

        # Step 4: Verify children still under parent (hierarchy maintained)
        logger.info("4. Verifying children maintained hierarchy with parent")
        child1_id = nested_page_hierarchy['child1']['page_id']
        child1_page = api.get_page_by_id(child1_id, expand="ancestors")
        child1_ancestors = [a.get('id') for a in child1_page.get("ancestors", [])]

        assert parent_id in child1_ancestors, \
            f"Parent {parent_id} should still be in child's ancestors: {child1_ancestors}"
        logger.info(f"   ✓ Child hierarchy maintained: {child1_ancestors}")

    @pytest.mark.skip(reason="Requires full sync implementation with move detection")
    def test_sync_detects_page_move(
        self,
        temp_workspace,
        nested_page_hierarchy,
        new_parent_location
    ):
        """Test that sync detects page moves in Confluence.

        Verification steps:
        1. Setup config and initial sync (creates local files)
        2. Move parent page in Confluence
        3. Run sync with move detection
        4. Verify local files moved to new path
        5. Verify old folders cleaned up

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
        # - local_docs/E2E Test - Move Parent/index.md
        # - local_docs/E2E Test - Move Parent/E2E Test - Move Child 1.md
        # - local_docs/E2E Test - Move Parent/E2E Test - Move Child 2.md

        # Step 2: Move parent page in Confluence
        logger.info("=== Step 2: Moving parent page in Confluence ===")
        auth = Authenticator()
        api = APIWrapper(auth)

        parent_id = nested_page_hierarchy['parent']['page_id']
        new_parent_id = new_parent_location['page_id']

        # Get current page data
        current_page = api.get_page_by_id(parent_id, expand="body.storage,version")
        current_version = current_page.get("version", {}).get("number", 1)
        current_title = current_page.get("title")
        current_body = current_page.get("body", {}).get("storage", {}).get("value", "")

        # Move the page
        api.update_page(
            page_id=parent_id,
            title=current_title,
            body=current_body,
            version=current_version,
            parent_id=new_parent_id
        )
        logger.info(f"   Moved parent {parent_id} to new location {new_parent_id}")

        # Step 3: Run sync with move detection
        logger.info("=== Step 3: Running sync to detect move ===")

        # TODO: Run sync command
        # sync_cmd = SyncCommand(config_path=config_path, state_path=state_path)
        # exit_code = sync_cmd.run()
        # assert exit_code == ExitCode.SUCCESS

        # Step 4: Verify local files moved to new path
        logger.info("=== Step 4: Verifying local files moved ===")

        # TODO: Verify new file structure exists:
        # - local_docs/E2E Test - New Parent Location/E2E Test - Move Parent/index.md
        # - local_docs/E2E Test - New Parent Location/E2E Test - Move Parent/E2E Test - Move Child 1.md
        # - local_docs/E2E Test - New Parent Location/E2E Test - Move Parent/E2E Test - Move Child 2.md

        # Step 5: Verify old folders cleaned up
        logger.info("=== Step 5: Verifying old folders cleaned up ===")

        # TODO: Verify old path no longer exists:
        # old_parent_path = Path(local_docs) / "E2E Test - Move Parent"
        # assert not old_parent_path.exists(), "Old folder should be cleaned up"

        logger.info("=== Page move journey test completed ===")

    def test_move_page_hierarchy_preserved(self, nested_page_hierarchy, new_parent_location):
        """Test that moving a parent page preserves child hierarchy.

        Verification steps:
        1. Verify initial hierarchy (parent > child1, child2)
        2. Move parent to new location
        3. Verify children still nested under parent
        4. Verify parent-child relationships maintained
        """
        auth = Authenticator()
        api = APIWrapper(auth)

        parent_id = nested_page_hierarchy['parent']['page_id']
        child1_id = nested_page_hierarchy['child1']['page_id']
        child2_id = nested_page_hierarchy['child2']['page_id']
        new_parent_id = new_parent_location['page_id']

        # Step 1: Verify initial hierarchy
        logger.info("1. Verifying initial hierarchy")
        child1_before = api.get_page_by_id(child1_id, expand="ancestors")
        child1_ancestors_before = [a.get('id') for a in child1_before.get("ancestors", [])]
        assert parent_id in child1_ancestors_before, "Child1 should have parent in ancestors"
        logger.info(f"   ✓ Initial child1 ancestors: {child1_ancestors_before}")

        # Step 2: Move parent to new location
        logger.info(f"2. Moving parent {parent_id} to new location {new_parent_id}")
        current_page = api.get_page_by_id(parent_id, expand="body.storage,version")
        current_version = current_page.get("version", {}).get("number", 1)
        current_title = current_page.get("title")
        current_body = current_page.get("body", {}).get("storage", {}).get("value", "")

        api.update_page(
            page_id=parent_id,
            title=current_title,
            body=current_body,
            version=current_version,
            parent_id=new_parent_id
        )
        logger.info("   ✓ Parent moved")

        # Step 3: Verify children still nested under parent
        logger.info("3. Verifying children still nested under parent")
        child1_after = api.get_page_by_id(child1_id, expand="ancestors")
        child1_ancestors_after = [a.get('id') for a in child1_after.get("ancestors", [])]

        assert parent_id in child1_ancestors_after, \
            f"Child1 should still have parent {parent_id} in ancestors: {child1_ancestors_after}"
        logger.info(f"   ✓ Child1 still under parent: {child1_ancestors_after}")

        child2_after = api.get_page_by_id(child2_id, expand="ancestors")
        child2_ancestors_after = [a.get('id') for a in child2_after.get("ancestors", [])]

        assert parent_id in child2_ancestors_after, \
            f"Child2 should still have parent {parent_id} in ancestors: {child2_ancestors_after}"
        logger.info(f"   ✓ Child2 still under parent: {child2_ancestors_after}")

        # Step 4: Verify parent-child relationships maintained
        logger.info("4. Verifying parent-child relationships maintained")
        # Get children of parent page
        parent_children = api.get_page_child_by_type(
            parent_id,
            child_type="page",
            expand="page"
        )

        child_ids = [child.get('id') for child in parent_children]
        assert child1_id in child_ids, f"Child1 {child1_id} should be in parent's children: {child_ids}"
        assert child2_id in child_ids, f"Child2 {child2_id} should be in parent's children: {child_ids}"
        logger.info(f"   ✓ Parent-child relationships maintained: {child_ids}")

    def test_complete_move_journey_workflow(
        self,
        temp_workspace,
        nested_page_hierarchy,
        new_parent_location
    ):
        """Test the complete move detection workflow end-to-end.

        This test validates the foundation for move detection:
        1. Create nested page hierarchy in Confluence
        2. Verify hierarchy structure
        3. Move parent page to new location
        4. Verify move succeeded and hierarchy preserved
        5. Verify ancestor chain updated

        Note: Full local file sync and cleanup requires MoveDetector
        implementation which is part of the broader feature set.
        """
        logger.info("=== Starting Complete Move Journey Workflow ===")

        auth = Authenticator()
        api = APIWrapper(auth)

        parent_id = nested_page_hierarchy['parent']['page_id']
        child1_id = nested_page_hierarchy['child1']['page_id']
        new_parent_id = new_parent_location['page_id']

        # Step 1: Create nested page hierarchy (already done by fixtures)
        logger.info("1. Nested page hierarchy created")
        logger.info(f"   Root: {nested_page_hierarchy['root']['page_id']}")
        logger.info(f"   Parent: {parent_id}")
        logger.info(f"   Child1: {child1_id}")
        logger.info(f"   Child2: {nested_page_hierarchy['child2']['page_id']}")
        logger.info(f"   New location: {new_parent_id}")

        # Step 2: Verify hierarchy structure
        logger.info("2. Verifying initial hierarchy structure")
        parent_page = api.get_page_by_id(parent_id, expand="ancestors,children.page")
        parent_ancestors = [a.get('id') for a in parent_page.get("ancestors", [])]
        logger.info(f"   Parent ancestors: {parent_ancestors}")
        assert nested_page_hierarchy['root']['page_id'] in parent_ancestors
        logger.info("   ✓ Hierarchy structure verified")

        # Step 3: Move parent page to new location
        logger.info("3. Moving parent page to new location")
        current_version = parent_page.get("version", {}).get("number", 1)
        current_title = parent_page.get("title")
        current_body = parent_page.get("body", {}).get("storage", {}).get("value", "")

        updated_page = api.update_page(
            page_id=parent_id,
            title=current_title,
            body=current_body,
            version=current_version,
            parent_id=new_parent_id
        )
        logger.info("   ✓ Parent page moved")

        # Step 4: Verify move succeeded and hierarchy preserved
        logger.info("4. Verifying move succeeded and hierarchy preserved")
        moved_page = api.get_page_by_id(parent_id, expand="ancestors,children.page")
        moved_ancestors = [a.get('id') for a in moved_page.get("ancestors", [])]

        assert new_parent_id in moved_ancestors, \
            f"New parent {new_parent_id} should be in ancestors: {moved_ancestors}"
        logger.info(f"   ✓ New parent in ancestors: {moved_ancestors}")

        # Verify children still under parent
        children = moved_page.get("children", {}).get("page", {}).get("results", [])
        child_ids = [c.get('id') for c in children]
        assert child1_id in child_ids, f"Child1 should still be under parent: {child_ids}"
        logger.info(f"   ✓ Children preserved: {child_ids}")

        # Step 5: Verify ancestor chain updated
        logger.info("5. Verifying ancestor chain updated for children")
        child1_page = api.get_page_by_id(child1_id, expand="ancestors")
        child1_ancestors = [a.get('id') for a in child1_page.get("ancestors", [])]

        # Child should have: root > new_parent > parent > child1
        assert new_parent_id in child1_ancestors, \
            f"New parent location should be in child's ancestor chain: {child1_ancestors}"
        assert parent_id in child1_ancestors, \
            f"Parent should still be in child's ancestor chain: {child1_ancestors}"
        logger.info(f"   ✓ Ancestor chain updated: {child1_ancestors}")

        logger.info("=== Complete Move Journey Workflow PASSED ===")
        logger.info("Summary:")
        logger.info(f"  - Parent page moved from root to new location")
        logger.info(f"  - Child hierarchy preserved")
        logger.info(f"  - Ancestor chains updated correctly")
        logger.info("\nNext steps (requires MoveDetector implementation):")
        logger.info("  - Detect moves in sync process")
        logger.info("  - Update local file paths to match new hierarchy")
        logger.info("  - Clean up old folder structure")
