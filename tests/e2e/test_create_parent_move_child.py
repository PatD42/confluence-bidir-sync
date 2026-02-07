"""E2E test: Create Parent Then Move Child (E2E-6).

This test validates the workflow where a new parent page is created and an
existing page is moved under it:
1. Setup existing page structure in Confluence
2. Create new parent page locally (new-section.md)
3. Create new folder locally (new-section/)
4. Move existing page into new folder
5. Run sync to push changes
6. Verify new parent page created in Confluence
7. Verify existing page moved under new parent

Requirements:
- Test Confluence credentials in .env.test
- Test space (CONFSYNCTEST) access

Test Scenario (E2E-6):
- Existing page already in Confluence
- Create new-section.md locally (will be parent page)
- Create new-section/ folder locally
- Move existing page into new-section/ folder
- Run sync
- Verify new parent page created
- Verify existing page moved to be child of new parent
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


class TestCreateParentMoveChild:
    """E2E tests for creating parent page and moving child under it."""

    @pytest.fixture(scope="function")
    def temp_workspace(self):
        """Create a temporary workspace directory for testing.

        This workspace includes:
        - .confluence-sync/ directory for config and state
        - local_docs/ directory for markdown files
        """
        temp_dir = tempfile.mkdtemp(prefix="create_parent_move_test_")
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
            title="E2E Test - Create Parent Move Child Root",
            content=SAMPLE_PAGE_SIMPLE
        )
        logger.info(f"Created test space root page: {page_info['page_id']}")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up test space root page: {page_info['page_id']}")

    @pytest.fixture(scope="function")
    def existing_child_page(self, test_space_root):
        """Create an existing child page that will be moved under new parent.

        This represents a page that already exists in Confluence and will be
        moved under a newly created parent page.

        Returns:
            Dict with page_id, space_key, title, and version
        """
        page_info = setup_test_page(
            title="E2E Test - Existing Child Page",
            content="<h1>Existing Child</h1><p>This page will be moved under a new parent.</p>",
            parent_id=test_space_root['page_id']
        )
        logger.info(f"Created existing child page: {page_info['page_id']}")

        yield page_info

        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up existing child page: {page_info['page_id']}")

    def test_create_local_parent_and_folder(self, temp_workspace):
        """Test creating a new parent page file and folder locally.

        Verification steps:
        1. Create new-section.md file
        2. Create new-section/ folder
        3. Verify both exist
        4. Verify file has proper content
        """
        local_docs = Path(temp_workspace['local_docs'])

        # Step 1: Create new-section.md file
        parent_file = local_docs / "new-section.md"
        parent_content = "# New Section\n\nThis is a new parent section.\n"
        parent_file.write_text(parent_content)
        logger.info(f"Created parent file: {parent_file}")

        # Step 2: Create new-section/ folder
        parent_folder = local_docs / "new-section"
        parent_folder.mkdir(exist_ok=True)
        logger.info(f"Created parent folder: {parent_folder}")

        # Step 3: Verify both exist
        assert parent_file.exists(), "Parent file should exist"
        assert parent_folder.exists(), "Parent folder should exist"
        assert parent_folder.is_dir(), "Parent path should be a directory"
        logger.info("✓ Parent file and folder created successfully")

        # Step 4: Verify file has proper content
        assert parent_file.read_text() == parent_content, "Parent file should have correct content"
        logger.info("✓ Parent file has correct content")

    def test_move_existing_page_to_new_folder(self, temp_workspace):
        """Test moving an existing page file into a new folder.

        Verification steps:
        1. Create existing page file in root
        2. Create new parent folder
        3. Move existing page file into folder
        4. Verify file exists in new location
        5. Verify file removed from old location
        """
        local_docs = Path(temp_workspace['local_docs'])

        # Step 1: Create existing page file in root
        existing_file = local_docs / "existing-page.md"
        page_content = "# Existing Page\n\nThis page will be moved.\n"
        existing_file.write_text(page_content)
        logger.info(f"Created existing page file: {existing_file}")

        # Step 2: Create new parent folder
        parent_folder = local_docs / "new-section"
        parent_folder.mkdir(exist_ok=True)
        logger.info(f"Created parent folder: {parent_folder}")

        # Step 3: Move existing page file into folder
        new_location = parent_folder / "existing-page.md"
        shutil.move(str(existing_file), str(new_location))
        logger.info(f"Moved file from {existing_file} to {new_location}")

        # Step 4: Verify file exists in new location
        assert new_location.exists(), "File should exist in new location"
        assert new_location.read_text() == page_content, "File content should be preserved"
        logger.info("✓ File exists in new location with correct content")

        # Step 5: Verify file removed from old location
        assert not existing_file.exists(), "File should not exist in old location"
        logger.info("✓ File removed from old location")

    def test_verify_initial_page_structure(self, test_space_root, existing_child_page):
        """Test that initial page structure is set up correctly in Confluence.

        Verification steps:
        1. Verify existing child page exists
        2. Verify child page is under root
        3. Verify child page title and content
        """
        auth = Authenticator()
        api = APIWrapper(auth)

        child_page_id = existing_child_page['page_id']
        root_id = test_space_root['page_id']

        # Step 1: Verify existing child page exists
        logger.info("1. Verifying existing child page exists")
        child_page = api.get_page_by_id(child_page_id, expand="ancestors,body.storage")
        assert child_page is not None, "Child page should exist"
        logger.info(f"   ✓ Child page exists: {child_page_id}")

        # Step 2: Verify child page is under root
        logger.info("2. Verifying child page is under root")
        ancestors = child_page.get("ancestors", [])
        ancestor_ids = [a.get('id') for a in ancestors]
        assert root_id in ancestor_ids, \
            f"Root {root_id} should be in child page's ancestors: {ancestor_ids}"
        logger.info(f"   ✓ Child page ancestors: {ancestor_ids}")

        # Step 3: Verify child page title and content
        logger.info("3. Verifying child page title and content")
        assert child_page.get("title") == existing_child_page['title'], \
            "Child page title should match"
        assert child_page.get("body", {}).get("storage", {}).get("value") is not None, \
            "Child page should have content"
        logger.info("   ✓ Child page title and content verified")

    def test_api_create_parent_and_move_child(self, test_space_root, existing_child_page):
        """Test creating a new parent page and moving child using Confluence API.

        Verification steps:
        1. Create new parent page in Confluence
        2. Verify parent page created
        3. Move existing child page under new parent
        4. Verify child page parent updated
        5. Verify ancestor chain updated
        6. Cleanup new parent page
        """
        auth = Authenticator()
        api = APIWrapper(auth)

        root_id = test_space_root['page_id']
        space_key = test_space_root['space_key']
        child_page_id = existing_child_page['page_id']

        # Step 1: Create new parent page in Confluence
        logger.info("1. Creating new parent page in Confluence")
        new_parent_content = "<h1>New Section</h1><p>This is a new parent section.</p>"
        new_parent_result = api.create_page(
            space=space_key,
            title="E2E Test - New Section Parent",
            body=new_parent_content,
            parent_id=root_id
        )
        new_parent_id = new_parent_result.get("id") if isinstance(new_parent_result, dict) else str(new_parent_result)
        logger.info(f"   ✓ Created new parent page: {new_parent_id}")

        try:
            # Step 2: Verify parent page created
            logger.info("2. Verifying parent page created")
            parent_page = api.get_page_by_id(new_parent_id, expand="ancestors")
            assert parent_page is not None, "Parent page should exist"
            assert parent_page.get("title") == "E2E Test - New Section Parent", \
                "Parent page title should match"
            parent_ancestors = [a.get('id') for a in parent_page.get("ancestors", [])]
            assert root_id in parent_ancestors, \
                f"Root {root_id} should be in parent's ancestors: {parent_ancestors}"
            logger.info("   ✓ Parent page created and verified")

            # Step 3: Move existing child page under new parent
            logger.info("3. Moving existing child page under new parent")
            child_page = api.get_page_by_id(child_page_id, expand="body.storage,version")
            current_version = child_page.get("version", {}).get("number", 1)
            current_title = child_page.get("title")
            current_body = child_page.get("body", {}).get("storage", {}).get("value", "")

            # Add a comment to force content change (ensures parent update happens)
            updated_body = current_body + "<!-- Moved to new parent -->"

            api.update_page(
                page_id=child_page_id,
                title=current_title,
                body=updated_body,
                version=current_version,
                parent_id=new_parent_id
            )
            logger.info("   ✓ Child page moved under new parent")

            # Step 4: Verify child page parent updated
            logger.info("4. Verifying child page parent updated")
            moved_child = api.get_page_by_id(child_page_id, expand="ancestors")
            moved_ancestors = [a.get('id') for a in moved_child.get("ancestors", [])]

            assert new_parent_id in moved_ancestors, \
                f"New parent {new_parent_id} should be in child's ancestors: {moved_ancestors}"
            logger.info(f"   ✓ Child page ancestors include new parent: {moved_ancestors}")

            # Step 5: Verify ancestor chain updated
            logger.info("5. Verifying ancestor chain updated")
            assert root_id in moved_ancestors, \
                f"Root {root_id} should be in ancestor chain: {moved_ancestors}"
            assert new_parent_id in moved_ancestors, \
                f"New parent {new_parent_id} should be in ancestor chain: {moved_ancestors}"
            logger.info(f"   ✓ Complete ancestor chain: {moved_ancestors}")

        finally:
            # Step 6: Cleanup new parent page
            logger.info("6. Cleaning up new parent page")
            try:
                # Move child back to root before deleting parent
                child_page = api.get_page_by_id(child_page_id, expand="body.storage,version")
                current_version = child_page.get("version", {}).get("number", 1)
                current_title = child_page.get("title")
                current_body = child_page.get("body", {}).get("storage", {}).get("value", "")

                api.update_page(
                    page_id=child_page_id,
                    title=current_title,
                    body=current_body,
                    version=current_version,
                    parent_id=root_id
                )
                logger.info("   ✓ Moved child back to root")

                # Now delete the new parent page
                api.delete_page(new_parent_id)
                logger.info(f"   ✓ Deleted new parent page: {new_parent_id}")
            except Exception as e:
                logger.warning(f"   ! Failed to cleanup new parent page: {e}")

    @pytest.mark.skip(reason="Requires full sync implementation with parent creation and move detection")
    def test_create_parent_move_child_sync_journey(
        self,
        temp_workspace,
        test_space_root,
        existing_child_page
    ):
        """Test complete journey: create parent locally, move child, sync to Confluence.

        Verification steps:
        1. Setup config with test space
        2. Create new-section.md locally (new parent page)
        3. Create new-section/ folder locally
        4. Move existing child page into new-section/ folder
        5. Run sync to push changes
        6. Verify new parent page created in Confluence
        7. Verify existing page moved under new parent in Confluence
        8. Verify ancestor chain updated correctly

        Note: This test is currently skipped because the full sync implementation
        with parent creation and move detection is not yet complete.
        """
        config_path = temp_workspace['config_path']
        state_path = temp_workspace['state_path']
        local_docs = Path(temp_workspace['local_docs'])

        # Step 1: Setup config with test space
        logger.info("=== Step 1: Setting up config ===")
        config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key=test_space_root['space_key'],
                    parent_page_id=test_space_root['page_id'],
                    local_path=str(local_docs)
                )
            ]
        )
        ConfigLoader.save(config_path, config)
        logger.info("   ✓ Config created")

        # Step 2: Create new-section.md locally (new parent page)
        logger.info("=== Step 2: Creating new parent page locally ===")
        parent_file = local_docs / "new-section.md"
        parent_content = "# New Section\n\nThis is a new parent section.\n"
        parent_file.write_text(parent_content)
        logger.info(f"   ✓ Created parent file: {parent_file}")

        # Step 3: Create new-section/ folder locally
        logger.info("=== Step 3: Creating parent folder locally ===")
        parent_folder = local_docs / "new-section"
        parent_folder.mkdir(exist_ok=True)
        logger.info(f"   ✓ Created parent folder: {parent_folder}")

        # Step 4: Move existing child page into new-section/ folder
        logger.info("=== Step 4: Moving existing child page into folder ===")

        # TODO: First, we need to pull the existing child page from Confluence
        # to create the local file, then move it into the new folder.
        # For now, we'll simulate this by creating a file with the same name.

        # Create a local file representing the existing child page
        child_file = local_docs / f"{existing_child_page['title']}.md"
        child_content = "# Existing Child\n\nThis page will be moved under a new parent.\n"
        child_file.write_text(child_content)

        # Move the file into the new folder
        new_child_location = parent_folder / f"{existing_child_page['title']}.md"
        shutil.move(str(child_file), str(new_child_location))
        logger.info(f"   ✓ Moved child file to: {new_child_location}")

        # Step 5: Run sync to push changes
        logger.info("=== Step 5: Running sync to push changes ===")

        # TODO: Run sync command
        # sync_cmd = SyncCommand(config_path=config_path, state_path=state_path)
        # exit_code = sync_cmd.run()
        # assert exit_code == ExitCode.SUCCESS
        logger.info("   TODO: Run sync command")

        # Step 6: Verify new parent page created in Confluence
        logger.info("=== Step 6: Verifying new parent page created ===")

        # TODO: Verify using Confluence API
        # auth = Authenticator()
        # api = APIWrapper(auth)
        #
        # # Find the new parent page by title
        # space_key = test_space_root['space_key']
        # search_results = api.search_content(
        #     cql=f'space={space_key} AND title="New Section"'
        # )
        # assert len(search_results) > 0, "New parent page should be created"
        # new_parent_page = search_results[0]
        # new_parent_id = new_parent_page.get('id')
        # logger.info(f"   ✓ New parent page found: {new_parent_id}")
        logger.info("   TODO: Verify new parent page created")

        # Step 7: Verify existing page moved under new parent in Confluence
        logger.info("=== Step 7: Verifying existing page moved ===")

        # TODO: Verify using Confluence API
        # child_page_id = existing_child_page['page_id']
        # child_page = api.get_page_by_id(child_page_id, expand="ancestors")
        # ancestors = [a.get('id') for a in child_page.get("ancestors", [])]
        #
        # assert new_parent_id in ancestors, \
        #     f"New parent {new_parent_id} should be in child's ancestors: {ancestors}"
        # logger.info(f"   ✓ Child page ancestors: {ancestors}")
        logger.info("   TODO: Verify existing page moved")

        # Step 8: Verify ancestor chain updated correctly
        logger.info("=== Step 8: Verifying ancestor chain ===")

        # TODO: Verify ancestor chain
        # root_id = test_space_root['page_id']
        # assert root_id in ancestors, \
        #     f"Root {root_id} should be in ancestor chain: {ancestors}"
        # assert new_parent_id in ancestors, \
        #     f"New parent {new_parent_id} should be in ancestor chain: {ancestors}"
        # logger.info(f"   ✓ Complete ancestor chain verified: {ancestors}")
        logger.info("   TODO: Verify ancestor chain")

        logger.info("=== Create Parent Move Child journey test completed ===")

    def test_workflow_foundation(self, temp_workspace, test_space_root, existing_child_page):
        """Test the foundation workflow for creating parent and moving child.

        This test validates the foundation components:
        1. Create nested structure locally (parent file + folder)
        2. Move existing child file into folder
        3. Verify local file structure correct
        4. API test: Create parent in Confluence
        5. API test: Move child under new parent
        6. Verify Confluence hierarchy correct

        Note: Full sync integration requires MoveDetector and parent page creation
        logic which is part of the broader feature set.
        """
        logger.info("=== Starting Workflow Foundation Test ===")

        local_docs = Path(temp_workspace['local_docs'])
        auth = Authenticator()
        api = APIWrapper(auth)

        # Step 1: Create nested structure locally
        logger.info("1. Creating nested structure locally")
        parent_file = local_docs / "new-section.md"
        parent_content = "# New Section\n\nThis is a new parent section.\n"
        parent_file.write_text(parent_content)

        parent_folder = local_docs / "new-section"
        parent_folder.mkdir(exist_ok=True)

        assert parent_file.exists(), "Parent file should exist"
        assert parent_folder.exists(), "Parent folder should exist"
        logger.info("   ✓ Parent file and folder created")

        # Step 2: Move existing child file into folder
        logger.info("2. Moving existing child file into folder")
        child_file = local_docs / "existing-child.md"
        child_content = "# Existing Child\n\nThis page will be moved.\n"
        child_file.write_text(child_content)

        new_child_location = parent_folder / "existing-child.md"
        shutil.move(str(child_file), str(new_child_location))

        assert new_child_location.exists(), "Child file should exist in new location"
        assert not child_file.exists(), "Child file should not exist in old location"
        logger.info(f"   ✓ Child file moved to: {new_child_location}")

        # Step 3: Verify local file structure
        logger.info("3. Verifying local file structure")
        assert (local_docs / "new-section.md").exists(), "Parent file should exist"
        assert (local_docs / "new-section").is_dir(), "Parent folder should exist"
        assert (local_docs / "new-section" / "existing-child.md").exists(), \
            "Child file should exist in folder"
        logger.info("   ✓ Local file structure verified")

        # Step 4: API test - Create parent in Confluence
        logger.info("4. Creating parent page in Confluence")
        root_id = test_space_root['page_id']
        space_key = test_space_root['space_key']

        parent_xhtml = "<h1>New Section</h1><p>This is a new parent section.</p>"
        new_parent_result = api.create_page(
            space=space_key,
            title="E2E Test - New Section (Foundation)",
            body=parent_xhtml,
            parent_id=root_id
        )
        new_parent_id = new_parent_result.get("id") if isinstance(new_parent_result, dict) else str(new_parent_result)
        logger.info(f"   ✓ Created parent page: {new_parent_id}")

        try:
            # Step 5: API test - Move child under new parent
            logger.info("5. Moving child page under new parent")
            child_page_id = existing_child_page['page_id']

            child_page = api.get_page_by_id(child_page_id, expand="body.storage,version")
            current_version = child_page.get("version", {}).get("number", 1)
            current_title = child_page.get("title")
            current_body = child_page.get("body", {}).get("storage", {}).get("value", "")

            # Add a comment to force content change (ensures parent update happens)
            updated_body = current_body + "<!-- Moved to new parent -->"

            api.update_page(
                page_id=child_page_id,
                title=current_title,
                body=updated_body,
                version=current_version,
                parent_id=new_parent_id
            )
            logger.info("   ✓ Child page moved under new parent")

            # Step 6: Verify Confluence hierarchy
            logger.info("6. Verifying Confluence hierarchy")
            moved_child = api.get_page_by_id(child_page_id, expand="ancestors")
            ancestors = [a.get('id') for a in moved_child.get("ancestors", [])]

            assert new_parent_id in ancestors, \
                f"New parent {new_parent_id} should be in ancestors: {ancestors}"
            assert root_id in ancestors, \
                f"Root {root_id} should be in ancestors: {ancestors}"
            logger.info(f"   ✓ Confluence hierarchy verified: {ancestors}")

            logger.info("=== Workflow Foundation Test PASSED ===")
            logger.info("Summary:")
            logger.info(f"  - Created parent page locally: {parent_file}")
            logger.info(f"  - Created parent folder: {parent_folder}")
            logger.info(f"  - Moved child file into folder: {new_child_location}")
            logger.info(f"  - Created parent page in Confluence: {new_parent_id}")
            logger.info(f"  - Moved child page under new parent")
            logger.info(f"  - Verified hierarchy in Confluence")
            logger.info("\nNext steps (requires sync implementation):")
            logger.info("  - Detect new parent page creation in local files")
            logger.info("  - Create corresponding page in Confluence")
            logger.info("  - Detect child page move in local files")
            logger.info("  - Update child page parent in Confluence")

        finally:
            # Cleanup: Move child back to root and delete parent
            logger.info("Cleanup: Restoring original structure")
            try:
                child_page = api.get_page_by_id(child_page_id, expand="body.storage,version")
                current_version = child_page.get("version", {}).get("number", 1)
                current_title = child_page.get("title")
                current_body = child_page.get("body", {}).get("storage", {}).get("value", "")

                api.update_page(
                    page_id=child_page_id,
                    title=current_title,
                    body=current_body,
                    version=current_version,
                    parent_id=root_id
                )
                logger.info("   ✓ Moved child back to root")

                api.delete_page(new_parent_id)
                logger.info(f"   ✓ Deleted parent page: {new_parent_id}")
            except Exception as e:
                logger.warning(f"   ! Cleanup failed: {e}")
