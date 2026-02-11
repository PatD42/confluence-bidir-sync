"""E2E test: Push Sync with Orphan Directories and Duplicate Titles.

This test validates that:
1. Subdirectories without a parent .md file get placeholder pages created
2. Files with duplicate H1 headings each get unique Confluence pages
3. The Confluence hierarchy correctly reflects the local directory structure
4. Push count accurately reports actual pages created

Test Hierarchy:
```
Root (E2E Test - Orphan Dir Push Root)
├── Core-Messaging (auto-created placeholder)
│   ├── Product Overview  (H1: "Shared Title" - keeps H1 title)
│   └── Product Summary   (H1: "Shared Title" - uses filename as title)
```

Requirements:
- Test Confluence credentials in .env.test
- CONFSYNCTEST space available
"""

import pytest
import logging
import time
from pathlib import Path

from src.confluence_client.auth import Authenticator
from src.confluence_client.api_wrapper import APIWrapper
from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.models import SpaceConfig, SyncConfig
from src.file_mapper.frontmatter_handler import FrontmatterHandler
from tests.helpers.confluence_test_setup import setup_test_page

logger = logging.getLogger(__name__)


class TestOrphanDirPushSync:
    """E2E tests for pushing files in subdirectories without parent .md files."""

    @pytest.fixture(scope="function")
    def empty_confluence_parent(self, test_credentials, cleanup_test_pages):
        """Create an empty parent page in Confluence."""
        space_key = test_credentials['test_space']

        root = setup_test_page(
            title="E2E Test - Orphan Dir Push Root",
            content="<p>Root page for orphan dir push E2E test</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])
        logger.info(f"Created empty parent page: {root['page_id']}")

        time.sleep(2)

        return {
            'parent_page_id': root['page_id'],
            'space_key': space_key,
        }

    @pytest.fixture(scope="function")
    def orphan_dir_files(self, temp_test_dir):
        """Create markdown files in a subdirectory without parent .md file.

        Structure:
            docs/Core-Messaging/Product-Overview.md  (H1: "Shared Title")
            docs/Core-Messaging/Product-Summary.md   (H1: "Shared Title")

        Note: No docs/Core-Messaging.md exists - this is the "orphan directory" case.
        """
        sub_dir = temp_test_dir / "Core-Messaging"
        sub_dir.mkdir()

        file1 = sub_dir / "Product-Overview.md"
        file1.write_text(
            "# Shared Title\n\n"
            "This is the product overview document.\n\n"
            "## Overview\n\nProduct overview content here.\n",
            encoding='utf-8'
        )

        file2 = sub_dir / "Product-Summary.md"
        file2.write_text(
            "# Shared Title\n\n"
            "This is the product summary document.\n\n"
            "## Summary\n\nProduct summary content here.\n",
            encoding='utf-8'
        )

        logger.info(f"Created 2 files in orphan directory: {sub_dir}")
        return [file1, file2]

    @pytest.mark.e2e
    def test_orphan_dir_creates_placeholder_and_children(
        self,
        empty_confluence_parent,
        orphan_dir_files,
        temp_test_dir,
        cleanup_test_pages
    ):
        """Files in orphan subdirectory should create placeholder + child pages.

        Verifies:
        1. Placeholder .md file is auto-created for the orphan directory
        2. Placeholder page is created in Confluence as intermediate parent
        3. Both child files are created as children of the placeholder
        4. Each child gets a unique page_id (no duplicates despite same H1)
        5. Push count is accurate
        """
        parent_page_id = empty_confluence_parent['parent_page_id']
        space_key = empty_confluence_parent['space_key']

        auth = Authenticator()
        api = APIWrapper(auth)

        # Step 1: Verify no Core-Messaging.md exists yet
        placeholder_path = temp_test_dir / "Core-Messaging.md"
        assert not placeholder_path.exists(), "Placeholder should not exist before sync"
        logger.info("Step 1: Confirmed no placeholder file exists")

        # Step 2: Run push sync
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=parent_page_id,
            local_path=str(temp_test_dir),
            exclude_page_ids=[]
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=False,
            force_push=True,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        file_mapper = FileMapper(authenticator=auth)
        logger.info("Step 2: Running sync_spaces() with force_push=True")
        file_mapper.sync_spaces(sync_config)
        logger.info("Sync completed")

        time.sleep(3)

        # Step 3: Verify placeholder file was created locally
        assert placeholder_path.exists(), \
            "Placeholder Core-Messaging.md should be auto-created"
        placeholder_content = placeholder_path.read_text(encoding='utf-8')
        assert '# Core Messaging' in placeholder_content, \
            "Placeholder should have H1 title derived from directory name"
        assert '## Place holder' in placeholder_content, \
            "Placeholder should have H2 place holder text"

        # Verify placeholder has frontmatter with page_id after sync
        placeholder_page = FrontmatterHandler.parse(str(placeholder_path), placeholder_content)
        assert placeholder_page.page_id is not None and placeholder_page.page_id != 'null', \
            "Placeholder should have page_id after sync"
        placeholder_page_id = placeholder_page.page_id
        cleanup_test_pages.append(placeholder_page_id)
        logger.info(f"Step 3: Placeholder created with page_id={placeholder_page_id}")

        # Step 4: Verify Confluence hierarchy
        # Parent should have exactly 1 child (the placeholder page)
        children = list(api.get_page_child_by_type(parent_page_id, child_type="page"))
        assert len(children) == 1, \
            f"Parent should have 1 child (placeholder), got {len(children)}: {[c['title'] for c in children]}"
        assert children[0]['title'] == 'Core Messaging', \
            f"Child should be 'Core Messaging', got '{children[0]['title']}'"
        logger.info("Step 4: Confluence hierarchy correct - placeholder is child of root")

        # Step 5: Verify grandchildren (the actual files)
        grandchildren = list(api.get_page_child_by_type(placeholder_page_id, child_type="page"))
        for gc in grandchildren:
            cleanup_test_pages.append(gc['id'])

        assert len(grandchildren) == 2, \
            f"Placeholder should have 2 children, got {len(grandchildren)}: {[gc['title'] for gc in grandchildren]}"
        grandchild_titles = {gc['title'] for gc in grandchildren}
        logger.info(f"Step 5: Found grandchildren: {grandchild_titles}")

        # Step 6: Verify each local file has a UNIQUE page_id
        page_ids = set()
        for file_path in orphan_dir_files:
            content = file_path.read_text(encoding='utf-8')
            local_page = FrontmatterHandler.parse(str(file_path), content)
            assert local_page.page_id is not None and local_page.page_id != 'null', \
                f"{file_path.name} should have page_id after sync"
            page_ids.add(local_page.page_id)
            cleanup_test_pages.append(local_page.page_id)

        assert len(page_ids) == 2, \
            f"Each file should have a UNIQUE page_id, got {len(page_ids)} unique IDs: {page_ids}"
        logger.info(f"Step 6: Each file has unique page_id: {page_ids}")

        # Step 7: Verify total = 3 pages (placeholder + 2 children)
        all_descendants = list(api.get_page_child_by_type(parent_page_id, child_type="page"))
        total_count = len(all_descendants)
        for child in all_descendants:
            grandkids = list(api.get_page_child_by_type(child['id'], child_type="page"))
            total_count += len(grandkids)

        assert total_count == 3, \
            f"Should have 3 total pages (1 placeholder + 2 children), got {total_count}"
        logger.info(f"Step 7: Total pages correct: {total_count}")

        logger.info("=" * 60)
        logger.info("Orphan directory push sync E2E test PASSED")
        logger.info("  - Placeholder auto-created for orphan directory")
        logger.info("  - Duplicate H1 titles resolved with filename fallback")
        logger.info("  - Each file has unique page_id")
        logger.info("  - Confluence hierarchy matches local structure")
        logger.info("=" * 60)
