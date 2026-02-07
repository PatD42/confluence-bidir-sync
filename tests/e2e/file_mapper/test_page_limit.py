"""E2E test: Page Limit Enforcement.

This test validates the 100 page limit per level:
1. Create a parent page with 101 child pages
2. Run sync
3. Verify PageLimitExceededError is raised
4. Verify no local files are created (atomic rollback)
5. Verify error message explains the MVP limitation

Requirements:
- Test Confluence credentials in .env.test
- CONFSYNCTEST space available

Note: This test creates 101 pages which may take some time (~30 seconds).
"""

import pytest
import logging
from pathlib import Path

from src.confluence_client.auth import Authenticator
from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.models import SpaceConfig, SyncConfig
from src.file_mapper.errors import PageLimitExceededError
from tests.helpers.confluence_test_setup import setup_test_page

logger = logging.getLogger(__name__)


class TestPageLimit:
    """E2E tests for page limit enforcement (ADR-013)."""

    @pytest.fixture(scope="function")
    def test_parent_with_101_children(self, test_credentials, cleanup_test_pages):
        """Create a parent page with 101 child pages to exceed the limit.

        This fixture creates a hierarchy that exceeds the MVP limit of 100
        pages per level. It may take ~30 seconds to create all pages.

        Returns:
            Dict containing:
                - parent_page_id: Root page ID
                - space_key: Space key
                - child_count: Number of child pages (101)
        """
        space_key = test_credentials['test_space']

        # Create root parent page
        root = setup_test_page(
            title="E2E Test - Page Limit Root",
            content="<p>Root page for page limit E2E test (101 children)</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])
        logger.info(f"Created root page: {root['page_id']}")

        # Create 101 child pages (exceeds limit of 100)
        child_count = 101
        logger.info(f"Creating {child_count} child pages (this may take ~30 seconds)...")

        created_children = []
        for i in range(1, child_count + 1):
            child = setup_test_page(
                title=f"Child Page {i:03d}",
                content=f"<p>Child page number {i}</p>",
                space_key=space_key,
                parent_id=root['page_id']
            )
            cleanup_test_pages.append(child['page_id'])
            created_children.append(child['page_id'])

            # Log progress every 10 pages
            if i % 10 == 0:
                logger.info(f"  Created {i}/{child_count} child pages...")

        logger.info(f"✓ Created {len(created_children)} child pages under root")

        # Wait for Confluence to index all pages
        import time
        logger.info("Waiting 10 seconds for Confluence indexing...")
        time.sleep(10)

        return {
            'parent_page_id': root['page_id'],
            'space_key': space_key,
            'child_count': child_count,
        }

    @pytest.mark.e2e
    @pytest.mark.slow  # Mark as slow test due to 101 page creation
    def test_page_limit_exceeded_error(
        self,
        test_parent_with_101_children,
        temp_test_dir
    ):
        """Test that sync fails when page limit is exceeded.

        Verification steps:
        1. Start with empty local folder
        2. Create parent with 101 child pages (exceeds limit of 100)
        3. Run sync with page_limit=100
        4. Verify PageLimitExceededError is raised
        5. Verify error message includes count (101) and limit (100)
        6. Verify no local files are created (atomic rollback)
        """
        # Step 1: Verify empty local folder
        assert temp_test_dir.exists(), "Temporary directory should exist"
        assert not list(temp_test_dir.iterdir()), "Temporary directory should be empty"
        logger.info(f"✓ Starting with empty local folder: {temp_test_dir}")

        # Step 2: Get test hierarchy info
        parent_page_id = test_parent_with_101_children['parent_page_id']
        space_key = test_parent_with_101_children['space_key']
        child_count = test_parent_with_101_children['child_count']

        logger.info(f"✓ Parent page has {child_count} children (exceeds limit of 100)")

        # Step 3: Configure sync with page_limit=100
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=parent_page_id,
            local_path=str(temp_test_dir),
            exclude_page_ids=[]
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=100,  # MVP limit per ADR-013
            force_pull=True,
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)

        # Step 4: Verify PageLimitExceededError is raised
        logger.info("Running sync_spaces() expecting PageLimitExceededError")
        with pytest.raises(PageLimitExceededError) as exc_info:
            file_mapper.sync_spaces(sync_config)

        error = exc_info.value
        logger.info(f"✓ PageLimitExceededError raised as expected: {error}")

        # Step 5: Verify error message includes count and limit
        assert error.current_count == child_count, \
            f"Error should report {child_count} pages, got {error.current_count}"
        assert error.limit == 100, \
            f"Error should report limit of 100, got {error.limit}"

        error_message = str(error)
        assert str(child_count) in error_message, \
            f"Error message should include count {child_count}: {error_message}"
        assert "100" in error_message, \
            f"Error message should include limit 100: {error_message}"

        logger.info("✓ Error message includes count and limit")
        logger.info(f"  Error message: {error_message}")

        # Step 6: Verify no local files are created (atomic rollback)
        md_files = list(temp_test_dir.rglob("*.md"))
        md_files = [f for f in md_files if '.confluence-sync' not in str(f)]

        assert len(md_files) == 0, \
            f"No markdown files should be created after error, found {len(md_files)}: {[f.name for f in md_files]}"
        logger.info("✓ No markdown files created (atomic rollback)")

        # Verify temp directory is cleaned up
        temp_sync_dir = temp_test_dir / ".confluence-sync" / "temp"
        if temp_sync_dir.exists():
            temp_files = list(temp_sync_dir.iterdir())
            assert len(temp_files) == 0, \
                f"Temp directory should be empty after rollback, found {len(temp_files)} files"
        logger.info("✓ Temp directory cleaned up")

        logger.info("=" * 60)
        logger.info("✓ Page limit E2E test PASSED")
        logger.info(f"  - Created {child_count} child pages (exceeds limit of 100)")
        logger.info("  - PageLimitExceededError raised with correct details")
        logger.info("  - No files created (atomic rollback)")
        logger.info("  - MVP limitation correctly enforced (ADR-013)")
        logger.info("=" * 60)

    @pytest.mark.e2e
    def test_page_limit_boundary_success(
        self,
        test_credentials,
        cleanup_test_pages,
        temp_test_dir
    ):
        """Test that sync succeeds when exactly at the page limit.

        Verifies that having exactly 100 child pages (at the boundary)
        does NOT raise an error and all pages are synced successfully.
        """
        space_key = test_credentials['test_space']

        # Create root parent page
        root = setup_test_page(
            title="E2E Test - Page Limit Boundary",
            content="<p>Root page for boundary test (exactly 100 children)</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])
        logger.info(f"Created root page: {root['page_id']}")

        # Create exactly 100 child pages (at the boundary)
        child_count = 100
        logger.info(f"Creating {child_count} child pages (this may take ~25 seconds)...")

        for i in range(1, child_count + 1):
            child = setup_test_page(
                title=f"Boundary Child {i:03d}",
                content=f"<p>Boundary test child {i}</p>",
                space_key=space_key,
                parent_id=root['page_id']
            )
            cleanup_test_pages.append(child['page_id'])

            if i % 10 == 0:
                logger.info(f"  Created {i}/{child_count} child pages...")

        logger.info(f"✓ Created {child_count} child pages")

        # Wait for Confluence
        import time
        logger.info("Waiting 10 seconds for Confluence indexing...")
        time.sleep(10)

        # Configure sync with page_limit=100
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

        # Sync should succeed (exactly at boundary)
        logger.info("Running sync with exactly 100 child pages (at boundary)")
        file_mapper.sync_spaces(sync_config)
        logger.info("✓ Sync completed successfully")

        # Verify all 101 files created (root + 100 children)
        md_files = [f for f in temp_test_dir.rglob("*.md") if '.confluence-sync' not in str(f)]
        expected_file_count = child_count + 1  # root + children

        assert len(md_files) == expected_file_count, \
            f"Should have {expected_file_count} files, found {len(md_files)}"

        logger.info(f"✓ All {expected_file_count} files created successfully")
        logger.info("=" * 60)
        logger.info("✓ Page limit boundary test PASSED")
        logger.info(f"  - Created exactly {child_count} child pages")
        logger.info("  - Sync succeeded (at boundary, not exceeding)")
        logger.info(f"  - All {expected_file_count} files synced correctly")
        logger.info("=" * 60)

    @pytest.mark.e2e
    def test_page_limit_custom_value(
        self,
        test_credentials,
        cleanup_test_pages,
        temp_test_dir
    ):
        """Test page limit with custom value (not default 100).

        Verifies that page_limit configuration is respected and can be
        set to values other than the default 100.
        """
        space_key = test_credentials['test_space']

        # Create root
        root = setup_test_page(
            title="E2E Test - Custom Limit",
            content="<p>Root page for custom limit test</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])

        # Create 6 child pages
        child_count = 6
        for i in range(1, child_count + 1):
            child = setup_test_page(
                title=f"Custom Limit Child {i}",
                content=f"<p>Child {i}</p>",
                space_key=space_key,
                parent_id=root['page_id']
            )
            cleanup_test_pages.append(child['page_id'])

        logger.info(f"Created {child_count} child pages")

        # Wait for Confluence
        import time
        time.sleep(3)

        # Configure sync with custom page_limit=5 (less than child_count)
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=root['page_id'],
            local_path=str(temp_test_dir),
            exclude_page_ids=[]
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=5,  # Custom limit less than child_count
            force_pull=True,
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)

        # Sync should fail with custom limit
        logger.info("Running sync with custom page_limit=5 (6 children exist)")
        with pytest.raises(PageLimitExceededError) as exc_info:
            file_mapper.sync_spaces(sync_config)

        error = exc_info.value
        assert error.current_count == child_count
        assert error.limit == 5

        logger.info("✓ Custom page limit test PASSED")
        logger.info("  - Custom limit of 5 enforced")
        logger.info(f"  - Error raised for {child_count} children")
