"""E2E test: Title Change Detection and File Rename.

This test validates the title change detection and file rename workflow:
1. Create and sync a page with title "Old Name"
2. Rename the page in Confluence to "New Name"
3. Run sync
4. Verify local file is renamed to match new title
5. Verify frontmatter is updated with new title
6. Verify old file is deleted

Requirements:
- Test Confluence credentials in .env.test
- CONFSYNCTEST space available

Test Scenario:
```
Root (E2E Test - Title Change Root)
└── Old Name → New Name (renamed in Confluence)
```
"""

import pytest
import logging
from pathlib import Path
from datetime import datetime

from src.confluence_client.auth import Authenticator
from src.confluence_client.api_wrapper import APIWrapper
from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.models import SpaceConfig, SyncConfig
from src.file_mapper.frontmatter_handler import FrontmatterHandler
from src.file_mapper.filesafe_converter import FilesafeConverter
from tests.helpers.confluence_test_setup import setup_test_page
import re

logger = logging.getLogger(__name__)


def extract_title_from_content(content: str) -> str:
    """Extract title from H1 heading in markdown content."""
    match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


class TestTitleChange:
    """E2E tests for title change detection and file renaming."""

    @pytest.fixture(scope="function")
    def synced_page_with_old_name(self, test_credentials, cleanup_test_pages, temp_test_dir):
        """Create a page with title "Old Name" and sync it locally.

        Returns:
            Dict containing:
                - parent_page_id: Root page ID
                - space_key: Space key
                - page_id: Page ID of the test page
                - old_title: Original title ("Old Name")
                - old_file_path: Path to the local file with old name
        """
        space_key = test_credentials['test_space']

        # Create root parent page
        root = setup_test_page(
            title="E2E Test - Title Change Root",
            content="<p>Root page for title change E2E test</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])

        # Create test page with "Old Name"
        old_title = "Old Name"
        test_page = setup_test_page(
            title=old_title,
            content="<p>This page will be renamed</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(test_page['page_id'])
        logger.info(f"Created page: {old_title} (ID: {test_page['page_id']})")

        # Wait for Confluence to index
        import time
        logger.info("Waiting 3 seconds for Confluence indexing...")
        time.sleep(3)

        # Perform initial sync to create local file
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=root['page_id'],
            local_path=str(temp_test_dir),
            exclude_page_ids=[]
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=True,
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)

        logger.info("Performing initial sync to create local file")
        file_mapper.sync_spaces(sync_config)

        # Verify local file was created with old name
        root_dir = temp_test_dir / "E2E-Test--Title-Change-Root"
        old_filename = FilesafeConverter.title_to_filename(old_title)
        old_file_path = root_dir / old_filename

        assert old_file_path.exists(), f"Local file not created: {old_file_path}"
        logger.info(f"Verified local file created: {old_file_path}")

        # Verify content has title as H1 heading
        content = old_file_path.read_text(encoding='utf-8')
        local_page = FrontmatterHandler.parse(str(old_file_path), content)
        extracted_title = extract_title_from_content(local_page.content)
        assert extracted_title == old_title, f"Content H1 title should be '{old_title}', got '{extracted_title}'"
        logger.info(f"Verified content has title: {old_title}")

        return {
            'parent_page_id': root['page_id'],
            'space_key': space_key,
            'page_id': test_page['page_id'],
            'old_title': old_title,
            'old_file_path': str(old_file_path),
            'version': test_page['version']
        }

    @pytest.mark.e2e
    def test_title_change_renames_local_file(
        self,
        synced_page_with_old_name,
        temp_test_dir
    ):
        """Test that renaming a page in Confluence renames the local file.

        Verification steps:
        1. Start with synced page "Old Name"
        2. Rename page to "New Name" in Confluence
        3. Run sync
        4. Verify local file is renamed to "New-Name.md"
        5. Verify frontmatter is updated with new title
        6. Verify old file "Old-Name.md" is deleted
        """
        page_id = synced_page_with_old_name['page_id']
        space_key = synced_page_with_old_name['space_key']
        parent_page_id = synced_page_with_old_name['parent_page_id']
        old_title = synced_page_with_old_name['old_title']
        old_file_path = Path(synced_page_with_old_name['old_file_path'])
        version = synced_page_with_old_name['version']

        # Step 1: Verify we start with old file
        assert old_file_path.exists(), f"Old file should exist: {old_file_path}"
        logger.info(f"✓ Starting with file: {old_file_path.name}")

        # Step 2: Rename page in Confluence
        new_title = "New Name"
        auth = Authenticator()
        api = APIWrapper(auth)

        # Get current page details
        page_details = api.get_page_by_id(page_id)
        current_version = page_details['version']['number']

        # Update page with new title (keeping same content)
        result = api.update_page(
            page_id=page_id,
            title=new_title,
            body="<p>This page has been renamed</p>",
            version=current_version
        )
        new_version = result.get('version', {}).get('number', 'unknown')
        logger.info(f"✓ Renamed page in Confluence: '{old_title}' → '{new_title}' (version {new_version})")

        # Wait for Confluence to process the update
        import time
        logger.info("Waiting 3 seconds for Confluence to process title change...")
        time.sleep(3)

        # Step 3: Run sync
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=parent_page_id,
            local_path=str(temp_test_dir),
            exclude_page_ids=[]
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=True,  # Force pull to get the title change
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        file_mapper = FileMapper(authenticator=auth)

        logger.info("Running sync to detect title change")
        file_mapper.sync_spaces(sync_config)
        logger.info("✓ Sync completed")

        # Wait for file system operations to complete
        time.sleep(1)

        # Step 4: Verify local file is renamed
        root_dir = temp_test_dir / "E2E-Test--Title-Change-Root"
        new_filename = FilesafeConverter.title_to_filename(new_title)
        new_file_path = root_dir / new_filename

        assert new_file_path.exists(), \
            f"New file should exist: {new_file_path}"
        logger.info(f"✓ New file created: {new_file_path.name}")

        # Step 5: Verify frontmatter is updated with new title
        content = new_file_path.read_text(encoding='utf-8')
        local_page = FrontmatterHandler.parse(str(new_file_path), content)

        extracted_title = extract_title_from_content(local_page.content)
        assert extracted_title == new_title, \
            f"Content H1 title should be '{new_title}', got '{extracted_title}'"
        assert local_page.page_id == page_id, \
            f"Page ID should remain the same: {page_id}"
        logger.info(f"✓ Content updated with new title: {new_title}")

        # Step 6: Verify old file is deleted
        assert not old_file_path.exists(), \
            f"Old file should be deleted: {old_file_path}"
        logger.info(f"✓ Old file deleted: {old_file_path.name}")

        logger.info("=" * 60)
        logger.info("✓ Title change E2E test PASSED")
        logger.info(f"  - Page renamed in Confluence: '{old_title}' → '{new_title}'")
        logger.info(f"  - Local file renamed: {old_file_path.name} → {new_file_path.name}")
        logger.info(f"  - Frontmatter updated with new title")
        logger.info(f"  - Old file deleted")
        logger.info("=" * 60)

    @pytest.mark.e2e
    def test_title_change_with_special_characters(
        self,
        test_credentials,
        cleanup_test_pages,
        temp_test_dir
    ):
        """Test title change with special characters in the new title.

        This verifies that filesafe conversion works correctly when renaming
        files after a title change that includes special characters.
        """
        space_key = test_credentials['test_space']

        # Create root parent page
        root = setup_test_page(
            title="E2E Test - Title Change Special Chars",
            content="<p>Root page for special character title change test</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])

        # Create test page with simple title
        old_title = "Simple Title"
        test_page = setup_test_page(
            title=old_title,
            content="<p>This page will be renamed with special characters</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(test_page['page_id'])
        logger.info(f"Created page: {old_title} (ID: {test_page['page_id']})")

        # Wait for Confluence
        import time
        time.sleep(3)

        # Initial sync
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=root['page_id'],
            local_path=str(temp_test_dir),
            exclude_page_ids=[]
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=True,
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)

        logger.info("Performing initial sync")
        file_mapper.sync_spaces(sync_config)

        # Verify old file exists
        root_dir = temp_test_dir / "E2E-Test--Title-Change-Special-Chars"
        old_filename = FilesafeConverter.title_to_filename(old_title)
        old_file_path = root_dir / old_filename
        assert old_file_path.exists(), f"Old file should exist: {old_file_path}"

        # Rename page with special characters
        new_title = "API Reference: Getting Started & FAQ's"
        api = APIWrapper(auth)

        page_details = api.get_page_by_id(test_page['page_id'])
        result = api.update_page(
            page_id=test_page['page_id'],
            title=new_title,
            body="<p>Renamed with special characters</p>",
            version=page_details['version']['number']
        )
        new_version = result.get('version', {}).get('number', 'unknown')
        logger.info(f"✓ Renamed to: '{new_title}' (version {new_version})")

        time.sleep(3)

        # Sync again
        logger.info("Running sync after title change with special characters")
        file_mapper.sync_spaces(sync_config)

        # Verify new file with filesafe name
        # Expected: "API-Reference--Getting-Started---FAQ-s.md"
        new_filename = FilesafeConverter.title_to_filename(new_title)
        new_file_path = root_dir / new_filename

        assert new_file_path.exists(), \
            f"New file should exist: {new_file_path}"
        logger.info(f"✓ New file created with filesafe name: {new_file_path.name}")

        # Verify content has new title as H1
        content = new_file_path.read_text(encoding='utf-8')
        local_page = FrontmatterHandler.parse(str(new_file_path), content)
        extracted_title = extract_title_from_content(local_page.content)
        assert extracted_title == new_title, \
            f"Content H1 should have new title: {new_title}, got '{extracted_title}'"

        # Verify old file is deleted
        assert not old_file_path.exists(), \
            f"Old file should be deleted: {old_file_path}"

        logger.info("✓ Title change with special characters test PASSED")
        logger.info(f"  - Title: '{old_title}' → '{new_title}'")
        logger.info(f"  - File: {old_filename} → {new_filename}")

    @pytest.mark.e2e
    def test_title_change_with_nested_pages(
        self,
        test_credentials,
        cleanup_test_pages,
        temp_test_dir
    ):
        """Test title change for a parent page with children.

        Verifies that renaming a parent page also renames its directory,
        and that child pages remain accessible in the new directory structure.
        """
        space_key = test_credentials['test_space']

        # Create root parent page
        root = setup_test_page(
            title="E2E Test - Title Change Nested",
            content="<p>Root page for nested title change test</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])

        # Create parent page that will be renamed
        old_parent_title = "Old Parent"
        parent_page = setup_test_page(
            title=old_parent_title,
            content="<p>Parent page that will be renamed</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(parent_page['page_id'])

        # Create child page under the parent
        child_page = setup_test_page(
            title="Child Page",
            content="<p>Child page under parent</p>",
            space_key=space_key,
            parent_id=parent_page['page_id']
        )
        cleanup_test_pages.append(child_page['page_id'])
        logger.info(f"Created hierarchy: {old_parent_title} → Child Page")

        # Wait for Confluence
        import time
        time.sleep(3)

        # Initial sync
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=root['page_id'],
            local_path=str(temp_test_dir),
            exclude_page_ids=[]
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=True,
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)

        logger.info("Performing initial sync")
        file_mapper.sync_spaces(sync_config)

        # Verify old directory structure exists
        root_dir = temp_test_dir / "E2E-Test--Title-Change-Nested"
        old_parent_dir = root_dir / "Old-Parent"
        old_child_file = old_parent_dir / "Child-Page.md"
        assert old_parent_dir.exists(), f"Old parent directory should exist"
        assert old_child_file.exists(), f"Child file should exist in old directory"

        # Rename parent page
        new_parent_title = "New Parent"
        api = APIWrapper(auth)

        parent_details = api.get_page_by_id(parent_page['page_id'])
        result = api.update_page(
            page_id=parent_page['page_id'],
            title=new_parent_title,
            body="<p>Renamed parent page</p>",
            version=parent_details['version']['number']
        )
        new_version = result.get('version', {}).get('number', 'unknown')
        logger.info(f"✓ Renamed parent: '{old_parent_title}' → '{new_parent_title}'")

        time.sleep(3)

        # Sync again
        logger.info("Running sync after parent rename")
        file_mapper.sync_spaces(sync_config)

        # Verify new directory structure
        new_parent_dir = root_dir / "New-Parent"
        new_child_file = new_parent_dir / "Child-Page.md"

        assert new_parent_dir.exists(), \
            f"New parent directory should exist: {new_parent_dir}"
        assert new_child_file.exists(), \
            f"Child file should exist in new directory: {new_child_file}"
        logger.info(f"✓ New directory structure created")

        # Verify old directory is deleted
        assert not old_parent_dir.exists(), \
            f"Old parent directory should be deleted: {old_parent_dir}"
        logger.info(f"✓ Old directory deleted")

        # Verify child page content is still valid
        content = new_child_file.read_text(encoding='utf-8')
        local_page = FrontmatterHandler.parse(str(new_child_file), content)
        extracted_title = extract_title_from_content(local_page.content)
        assert extracted_title == "Child Page", \
            f"Child page title should remain 'Child Page', got '{extracted_title}'"
        assert local_page.page_id == child_page['page_id'], \
            f"Child page ID should remain the same"

        logger.info("✓ Title change with nested pages test PASSED")
        logger.info(f"  - Parent renamed: '{old_parent_title}' → '{new_parent_title}'")
        logger.info(f"  - Directory renamed: Old-Parent/ → New-Parent/")
        logger.info(f"  - Child page preserved in new directory")
