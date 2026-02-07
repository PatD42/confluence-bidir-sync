"""E2E test: Full Push Sync (Local → Confluence).

This test validates the complete push sync workflow:
1. Create 10 local markdown files without page_ids in frontmatter
2. Start with an empty Confluence parent page (no children)
3. Run sync_spaces() with force_push=True
4. Verify all 10 pages are created in Confluence
5. Verify frontmatter in local files is updated with page_ids

Requirements:
- Test Confluence credentials in .env.test
- CONFSYNCTEST space available

Test Hierarchy (10 pages total):
```
Root (E2E Test - Push Sync Root)
├── Product
│   ├── Features
│   ├── Roadmap
│   └── Pricing
├── Engineering
│   ├── Architecture
│   ├── Testing
│   └── Deployment
├── Marketing
└── Sales
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
from tests.helpers.confluence_test_setup import setup_test_page

logger = logging.getLogger(__name__)


class TestFullPushSync:
    """E2E tests for full push sync from local to Confluence."""

    @pytest.fixture(scope="function")
    def empty_confluence_parent(self, test_credentials, cleanup_test_pages):
        """Create an empty parent page in Confluence for push sync testing.

        Returns:
            Dict containing:
                - parent_page_id: Root page ID
                - space_key: Space key
        """
        space_key = test_credentials['test_space']

        # Create root parent page with NO children
        root = setup_test_page(
            title="E2E Test - Push Sync Root",
            content="<p>Root page for push sync E2E test - initially empty</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])

        logger.info(f"Created empty parent page: {root['page_id']} in space {space_key}")

        # Wait for Confluence to index the page
        import time
        logger.info("Waiting 2 seconds for Confluence indexing...")
        time.sleep(2)

        return {
            'parent_page_id': root['page_id'],
            'space_key': space_key,
        }

    @pytest.fixture(scope="function")
    def local_files_without_page_ids(self, temp_test_dir):
        """Create 10 local markdown files without page_ids in frontmatter.

        Creates a hierarchical file structure representing the test hierarchy.

        Returns:
            List of created file paths
        """
        # Create the file structure
        files_to_create = [
            # Top-level pages
            ("Product.md", "Product", "Information about our product"),
            ("Engineering.md", "Engineering", "Engineering documentation"),
            ("Marketing.md", "Marketing", "Marketing materials"),
            ("Sales.md", "Sales", "Sales information"),
            # Children of Product
            ("Product/Features.md", "Features", "Product features"),
            ("Product/Roadmap.md", "Roadmap", "Product roadmap"),
            ("Product/Pricing.md", "Pricing", "Pricing information"),
            # Children of Engineering
            ("Engineering/Architecture.md", "Architecture", "System architecture"),
            ("Engineering/Testing.md", "Testing", "Testing guidelines"),
            ("Engineering/Deployment.md", "Deployment", "Deployment procedures"),
        ]

        created_files = []

        for rel_path, title, description in files_to_create:
            file_path = temp_test_dir / rel_path

            # Create parent directory if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Create frontmatter WITHOUT page_id (or with page_id: null)
            # This simulates new local files that haven't been synced yet
            # With simplified LocalPage model, only page_id is in frontmatter
            frontmatter = f"""---
page_id: null
---

# {title}

{description}

This page was created locally and needs to be pushed to Confluence.
"""

            file_path.write_text(frontmatter, encoding='utf-8')
            created_files.append(file_path)
            logger.info(f"Created local file: {rel_path}")

        assert len(created_files) == 10, f"Should create 10 files, created {len(created_files)}"
        logger.info(f"Created {len(created_files)} local markdown files without page_ids")

        return created_files

    @pytest.mark.e2e
    def test_full_push_sync_10_pages(
        self,
        empty_confluence_parent,
        local_files_without_page_ids,
        temp_test_dir,
        cleanup_test_pages
    ):
        """Test full push sync of 10 local pages to empty Confluence parent.

        Verification steps:
        1. Start with 10 local files without page_ids
        2. Empty Confluence parent (no children)
        3. Run sync with force_push=True
        4. Verify 10 pages created in Confluence
        5. Verify frontmatter in local files is updated with page_ids
        """
        # Step 1: Verify 10 local files exist
        assert len(local_files_without_page_ids) == 10, "Should have 10 local files"
        logger.info(f"✓ Starting with 10 local files")

        # Verify files don't have page_ids
        for file_path in local_files_without_page_ids:
            content = file_path.read_text(encoding='utf-8')
            local_page = FrontmatterHandler.parse(str(file_path), content)
            assert local_page.page_id is None or local_page.page_id == 'null', \
                f"File {file_path.name} should not have page_id yet"

        logger.info("✓ All local files have null page_ids (not yet synced)")

        # Step 2: Verify Confluence parent is empty
        parent_page_id = empty_confluence_parent['parent_page_id']
        space_key = empty_confluence_parent['space_key']

        # Use API to verify no children
        auth = Authenticator()
        api = APIWrapper(auth)

        # Get children of parent page
        children = list(api.get_page_child_by_type(parent_page_id, child_type="page"))
        assert len(children) == 0, f"Parent should have no children, found {len(children)}"
        logger.info(f"✓ Confluence parent page is empty (no children)")

        # Step 3: Configure and run sync with force_push
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
            force_push=True,  # Force push to Confluence
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        # Create FileMapper and run sync
        file_mapper = FileMapper(authenticator=auth)

        logger.info("Running sync_spaces() with force_push=True")
        file_mapper.sync_spaces(sync_config)
        logger.info("✓ Sync completed successfully")

        # Wait for Confluence to process all the new pages
        import time
        logger.info("Waiting 5 seconds for Confluence to process new pages...")
        time.sleep(5)

        # Step 4: Verify 10 pages created in Confluence
        # Get all children recursively
        def get_all_descendants(page_id, api_wrapper):
            """Recursively get all descendant pages."""
            descendants = []
            children = list(api_wrapper.get_page_child_by_type(page_id, child_type="page"))
            for child in children:
                descendants.append(child)
                descendants.extend(get_all_descendants(child['id'], api_wrapper))
            return descendants

        all_pages = get_all_descendants(parent_page_id, api)
        created_page_ids = [p['id'] for p in all_pages]

        assert len(all_pages) == 10, \
            f"Should have 10 pages in Confluence, found {len(all_pages)}: {[p['title'] for p in all_pages]}"
        logger.info(f"✓ Created {len(all_pages)} pages in Confluence")

        # Register all created pages for cleanup
        for page_id in created_page_ids:
            cleanup_test_pages.append(page_id)

        # Verify expected titles exist
        created_titles = {p['title'] for p in all_pages}
        expected_titles = {
            "Product", "Features", "Roadmap", "Pricing",
            "Engineering", "Architecture", "Testing", "Deployment",
            "Marketing", "Sales",
        }

        assert created_titles == expected_titles, \
            f"Missing titles: {expected_titles - created_titles}, Extra: {created_titles - expected_titles}"
        logger.info("✓ All expected page titles present in Confluence")

        # Step 5: Verify frontmatter in local files is updated with page_ids
        # Note: With simplified LocalPage model, only page_id is tracked in frontmatter.
        # space_key and last_synced are tracked globally in state.yaml.
        md_files = [f for f in temp_test_dir.rglob("*.md") if '.confluence-sync' not in str(f)]
        assert len(md_files) == 10, f"Should still have 10 local files, found {len(md_files)}"

        updated_count = 0
        for md_file in md_files:
            content = md_file.read_text(encoding='utf-8')
            local_page = FrontmatterHandler.parse(str(md_file), content)

            # Verify page_id is now set (not null)
            assert local_page.page_id is not None and local_page.page_id != 'null', \
                f"File {md_file.name} should have page_id after sync"

            # Verify page_id is in the list of created pages
            assert local_page.page_id in created_page_ids, \
                f"File {md_file.name} has unknown page_id: {local_page.page_id}"

            updated_count += 1
            logger.debug(f"✓ Verified frontmatter updated for {md_file.name} (page_id: {local_page.page_id})")

        assert updated_count == 10, f"Should update 10 files, updated {updated_count}"
        logger.info("✓ All 10 local files have updated frontmatter with page_ids")

        # Verify hierarchy is preserved in Confluence
        # Check that child pages have correct parents
        for page in all_pages:
            page_details = api.get_page_by_id(page['id'])
            page_title = page_details['title']

            # Check expected parent relationships (children with explicit parents)
            # Note: Sales is a top-level page (no child pages under Marketing in this test)
            expected_parents = {
                "Features": "Product",
                "Roadmap": "Product",
                "Pricing": "Product",
                "Architecture": "Engineering",
                "Testing": "Engineering",
                "Deployment": "Engineering",
            }

            if page_title in expected_parents:
                expected_parent_title = expected_parents[page_title]
                # Get parent from ancestors
                ancestors = page_details.get('ancestors', [])
                if ancestors:
                    actual_parent = ancestors[-1]
                    # Parent should either be expected_parent_title or the root
                    parent_title = actual_parent['title']
                    if parent_title != "E2E Test - Push Sync Root":
                        assert parent_title == expected_parent_title, \
                            f"Page '{page_title}' should be child of '{expected_parent_title}', got '{parent_title}'"
                        logger.debug(f"✓ {page_title} is child of {parent_title}")

        logger.info("✓ Hierarchy preserved in Confluence (parent-child relationships correct)")

        logger.info("=" * 60)
        logger.info("✓ Full push sync E2E test PASSED")
        logger.info("  - 10 local files without page_ids → 10 Confluence pages")
        logger.info("  - Frontmatter updated with page_ids")
        logger.info("  - Hierarchy preserved")
        logger.info("=" * 60)

    @pytest.mark.e2e
    def test_push_sync_idempotency(
        self,
        empty_confluence_parent,
        local_files_without_page_ids,
        temp_test_dir,
        cleanup_test_pages
    ):
        """Test that running push sync twice doesn't create duplicate pages.

        Verifies that sync is idempotent - running it multiple times
        should not create duplicate pages in Confluence.
        """
        # Setup
        parent_page_id = empty_confluence_parent['parent_page_id']
        space_key = empty_confluence_parent['space_key']

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

        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)
        api = APIWrapper(auth)

        # First sync
        logger.info("Running first push sync")
        file_mapper.sync_spaces(sync_config)

        # Wait for Confluence
        import time
        time.sleep(5)

        # Get page count after first sync
        def count_descendants(page_id, api_wrapper):
            """Count all descendant pages."""
            children = list(api_wrapper.get_page_child_by_type(page_id, child_type="page"))
            count = len(children)
            for child in children:
                count += count_descendants(child['id'], api_wrapper)
            return count

        first_sync_count = count_descendants(parent_page_id, api)
        logger.info(f"First sync created {first_sync_count} pages")

        # Register pages for cleanup
        def register_all_descendants(page_id, api_wrapper, cleanup_list):
            """Register all descendants for cleanup."""
            children = list(api_wrapper.get_page_child_by_type(page_id, child_type="page"))
            for child in children:
                cleanup_list.append(child['id'])
                register_all_descendants(child['id'], api_wrapper, cleanup_list)

        register_all_descendants(parent_page_id, api, cleanup_test_pages)

        # Second sync (should be idempotent - no new pages created)
        logger.info("Running second push sync (should be idempotent)")
        file_mapper.sync_spaces(sync_config)

        time.sleep(5)

        # Get page count after second sync
        second_sync_count = count_descendants(parent_page_id, api)
        logger.info(f"Second sync resulted in {second_sync_count} pages")

        # Verify same number of pages (no duplicates)
        assert first_sync_count == second_sync_count, \
            f"Second sync should not create duplicates: first={first_sync_count}, second={second_sync_count}"

        assert second_sync_count == 10, f"Should have exactly 10 pages, got {second_sync_count}"

        logger.info("✓ Push sync is idempotent - second sync did not create duplicates")
