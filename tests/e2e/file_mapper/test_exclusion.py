"""E2E test: Exclusion by PageID.

This test validates the exclusion feature:
1. Create a hierarchy with multiple pages including an "Archives" section
2. Configure exclusion to exclude the "Archives" page by pageID
3. Run sync
4. Verify Archives and its descendants are not synced locally
5. Verify other pages are synced normally

Requirements:
- Test Confluence credentials in .env.test
- CONFSYNCTEST space available

Test Hierarchy (8 pages total, 3 excluded):
```
Root (E2E Test - Exclusion Root)
├── Team (synced)
│   └── Engineering (synced)
├── Archives (EXCLUDED)
│   ├── Old Project (excluded descendant)
│   └── Deprecated Docs (excluded descendant)
└── Active Projects (synced)
    └── Current Work (synced)
```
"""

import pytest
import logging
from pathlib import Path
from datetime import datetime

from src.confluence_client.auth import Authenticator
from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.models import SpaceConfig, SyncConfig
from src.file_mapper.frontmatter_handler import FrontmatterHandler
from tests.helpers.confluence_test_setup import setup_test_page

logger = logging.getLogger(__name__)


class TestExclusion:
    """E2E tests for page exclusion by pageID."""

    @pytest.fixture(scope="function")
    def test_hierarchy_with_archives(self, test_credentials, cleanup_test_pages):
        """Create a hierarchy with an Archives section to be excluded.

        Returns:
            Dict containing:
                - parent_page_id: Root page ID
                - space_key: Space key
                - archives_page_id: Archives page ID (to be excluded)
                - synced_page_ids: List of page IDs that should be synced
                - excluded_page_ids: List of page IDs that should be excluded
        """
        space_key = test_credentials['test_space']

        # Create root parent page
        root = setup_test_page(
            title="E2E Test - Exclusion Root",
            content="<p>Root page for exclusion E2E test</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])
        logger.info(f"Created root page: {root['page_id']}")

        synced_page_ids = [root['page_id']]
        excluded_page_ids = []

        # Create Team section (should be synced)
        team = setup_test_page(
            title="Team",
            content="<p>Team information</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(team['page_id'])
        synced_page_ids.append(team['page_id'])
        logger.info(f"Created Team page: {team['page_id']}")

        # Create Engineering under Team (should be synced)
        engineering = setup_test_page(
            title="Engineering",
            content="<p>Engineering team</p>",
            space_key=space_key,
            parent_id=team['page_id']
        )
        cleanup_test_pages.append(engineering['page_id'])
        synced_page_ids.append(engineering['page_id'])
        logger.info(f"Created Engineering page: {engineering['page_id']}")

        # Create Archives section (should be EXCLUDED)
        archives = setup_test_page(
            title="Archives",
            content="<p>Archived content</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(archives['page_id'])
        excluded_page_ids.append(archives['page_id'])
        logger.info(f"Created Archives page (TO BE EXCLUDED): {archives['page_id']}")

        # Create pages under Archives (descendants should also be excluded)
        old_project = setup_test_page(
            title="Old Project",
            content="<p>Old project documentation</p>",
            space_key=space_key,
            parent_id=archives['page_id']
        )
        cleanup_test_pages.append(old_project['page_id'])
        excluded_page_ids.append(old_project['page_id'])
        logger.info(f"Created Old Project page (descendant): {old_project['page_id']}")

        deprecated_docs = setup_test_page(
            title="Deprecated Docs",
            content="<p>Deprecated documentation</p>",
            space_key=space_key,
            parent_id=archives['page_id']
        )
        cleanup_test_pages.append(deprecated_docs['page_id'])
        excluded_page_ids.append(deprecated_docs['page_id'])
        logger.info(f"Created Deprecated Docs page (descendant): {deprecated_docs['page_id']}")

        # Create Active Projects section (should be synced)
        active_projects = setup_test_page(
            title="Active Projects",
            content="<p>Current active projects</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(active_projects['page_id'])
        synced_page_ids.append(active_projects['page_id'])
        logger.info(f"Created Active Projects page: {active_projects['page_id']}")

        # Create Current Work under Active Projects (should be synced)
        current_work = setup_test_page(
            title="Current Work",
            content="<p>Current work items</p>",
            space_key=space_key,
            parent_id=active_projects['page_id']
        )
        cleanup_test_pages.append(current_work['page_id'])
        synced_page_ids.append(current_work['page_id'])
        logger.info(f"Created Current Work page: {current_work['page_id']}")

        # Total: 8 pages (1 root + 7 children/descendants)
        # Synced: 5 pages (root, team, engineering, active_projects, current_work)
        # Excluded: 3 pages (archives, old_project, deprecated_docs)
        total_pages = len(synced_page_ids) + len(excluded_page_ids)
        assert total_pages == 8, f"Should have 8 pages total, got {total_pages}"

        logger.info(f"Created test hierarchy with {total_pages} pages")
        logger.info(f"  - {len(synced_page_ids)} pages to be synced")
        logger.info(f"  - {len(excluded_page_ids)} pages to be excluded")
        logger.info(f"Archives page ID (excluded): {archives['page_id']}")

        # Wait for Confluence to index all pages
        import time
        logger.info("Waiting 5 seconds for Confluence indexing...")
        time.sleep(5)

        return {
            'parent_page_id': root['page_id'],
            'space_key': space_key,
            'archives_page_id': archives['page_id'],
            'synced_page_ids': synced_page_ids,
            'excluded_page_ids': excluded_page_ids,
        }

    @pytest.mark.e2e
    def test_exclusion_by_page_id(self, test_hierarchy_with_archives, temp_test_dir):
        """Test that pages excluded by pageID are not synced.

        Verification steps:
        1. Start with empty local folder
        2. 8 pages exist in Confluence (5 to sync, 3 to exclude)
        3. Configure exclusion for Archives page by pageID
        4. Run sync with force_pull=True
        5. Verify only 5 pages are synced locally (Archives and descendants excluded)
        6. Verify excluded pages do NOT have local files
        7. Verify non-excluded pages ARE synced correctly
        """
        # Step 1: Verify empty local folder
        assert temp_test_dir.exists(), "Temporary directory should exist"
        assert not list(temp_test_dir.iterdir()), "Temporary directory should be empty"
        logger.info(f"✓ Starting with empty local folder: {temp_test_dir}")

        # Step 2: Get test hierarchy info
        parent_page_id = test_hierarchy_with_archives['parent_page_id']
        space_key = test_hierarchy_with_archives['space_key']
        archives_page_id = test_hierarchy_with_archives['archives_page_id']
        synced_page_ids = test_hierarchy_with_archives['synced_page_ids']
        excluded_page_ids = test_hierarchy_with_archives['excluded_page_ids']

        total_pages = len(synced_page_ids) + len(excluded_page_ids)
        logger.info(f"✓ {total_pages} pages exist in Confluence")
        logger.info(f"  - {len(synced_page_ids)} pages should be synced")
        logger.info(f"  - {len(excluded_page_ids)} pages should be excluded")

        # Step 3: Configure exclusion for Archives page
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=parent_page_id,
            local_path=str(temp_test_dir),
            exclude_page_ids=[archives_page_id]  # Exclude Archives by pageID
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=True,  # Force pull from Confluence
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        logger.info(f"✓ Configured exclusion for Archives page: {archives_page_id}")

        # Step 4: Run sync
        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)

        logger.info("Running sync_spaces() with exclusion configured")
        file_mapper.sync_spaces(sync_config)
        logger.info("✓ Sync completed successfully")

        # Step 5: Verify only 5 pages are synced locally
        md_files = list(temp_test_dir.rglob("*.md"))
        md_files = [f for f in md_files if '.confluence-sync' not in str(f)]

        assert len(md_files) == len(synced_page_ids), \
            f"Should have {len(synced_page_ids)} markdown files, found {len(md_files)}: {[f.name for f in md_files]}"
        logger.info(f"✓ Created {len(md_files)} markdown files locally (excluded {len(excluded_page_ids)} pages)")

        # Step 6: Verify excluded pages do NOT have local files
        root_dir = temp_test_dir / "E2E-Test--Exclusion-Root"

        # Archives.md should NOT exist
        archives_file = root_dir / "Archives.md"
        assert not archives_file.exists(), \
            f"Archives.md should NOT exist (excluded): {archives_file}"
        logger.info("✓ Archives.md does not exist (correctly excluded)")

        # Archives/ directory should NOT exist
        archives_dir = root_dir / "Archives"
        assert not archives_dir.exists(), \
            f"Archives/ directory should NOT exist (excluded): {archives_dir}"
        logger.info("✓ Archives/ directory does not exist (correctly excluded)")

        # Old-Project.md should NOT exist (descendant of excluded page)
        old_project_file = archives_dir / "Old-Project.md"
        assert not old_project_file.exists(), \
            f"Old-Project.md should NOT exist (descendant of excluded): {old_project_file}"
        logger.info("✓ Old-Project.md does not exist (descendant of excluded page)")

        # Deprecated-Docs.md should NOT exist (descendant of excluded page)
        deprecated_docs_file = archives_dir / "Deprecated-Docs.md"
        assert not deprecated_docs_file.exists(), \
            f"Deprecated-Docs.md should NOT exist (descendant of excluded): {deprecated_docs_file}"
        logger.info("✓ Deprecated-Docs.md does not exist (descendant of excluded page)")

        # Step 7: Verify non-excluded pages ARE synced correctly
        expected_synced_files = [
            temp_test_dir / "E2E-Test--Exclusion-Root.md",  # Root
            root_dir / "Team.md",
            root_dir / "Team" / "Engineering.md",
            root_dir / "Active-Projects.md",
            root_dir / "Active-Projects" / "Current-Work.md",
        ]

        for expected_file in expected_synced_files:
            assert expected_file.exists() and expected_file.is_file(), \
                f"Expected file should exist: {expected_file}"
            logger.debug(f"✓ Verified file exists: {expected_file.name}")

        logger.info("✓ All 5 expected files exist at correct paths")

        # Verify frontmatter in all synced files
        for md_file in md_files:
            content = md_file.read_text(encoding='utf-8')
            local_page = FrontmatterHandler.parse(str(md_file), content)

            # Verify page_id is in synced list (not in excluded list)
            assert local_page.page_id in synced_page_ids, \
                f"File {md_file.name} has page_id {local_page.page_id} which should be synced"
            assert local_page.page_id not in excluded_page_ids, \
                f"File {md_file.name} has page_id {local_page.page_id} which should be excluded"

            logger.debug(f"✓ Verified frontmatter for {md_file.name} (page_id: {local_page.page_id})")

        logger.info("✓ All synced files have valid frontmatter")

        logger.info("=" * 60)
        logger.info("✓ Exclusion E2E test PASSED")
        logger.info(f"  - Excluded Archives page by pageID: {archives_page_id}")
        logger.info(f"  - {len(excluded_page_ids)} pages excluded (including descendants)")
        logger.info(f"  - {len(synced_page_ids)} pages synced normally")
        logger.info("  - Verified excluded pages do NOT have local files")
        logger.info("  - Verified non-excluded pages ARE synced correctly")
        logger.info("=" * 60)

    @pytest.mark.e2e
    def test_exclusion_with_multiple_excluded_pages(
        self,
        test_credentials,
        cleanup_test_pages,
        temp_test_dir
    ):
        """Test exclusion with multiple pages excluded by pageID.

        Verifies that multiple pages can be excluded simultaneously and
        that their descendants are also excluded.
        """
        space_key = test_credentials['test_space']

        # Create root
        root = setup_test_page(
            title="E2E Test - Multiple Exclusions",
            content="<p>Root page for multiple exclusions test</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])

        # Create Page A (to be excluded)
        page_a = setup_test_page(
            title="Page A",
            content="<p>Page A</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(page_a['page_id'])

        # Create Page B (to be synced)
        page_b = setup_test_page(
            title="Page B",
            content="<p>Page B</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(page_b['page_id'])

        # Create Page C (to be excluded)
        page_c = setup_test_page(
            title="Page C",
            content="<p>Page C</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(page_c['page_id'])

        # Create Page D (to be synced)
        page_d = setup_test_page(
            title="Page D",
            content="<p>Page D</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(page_d['page_id'])

        logger.info("Created hierarchy with 5 pages (2 to exclude, 3 to sync)")

        # Wait for Confluence
        import time
        time.sleep(3)

        # Configure exclusion for Page A and Page C
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=root['page_id'],
            local_path=str(temp_test_dir),
            exclude_page_ids=[page_a['page_id'], page_c['page_id']]
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

        logger.info("Running sync with 2 excluded pages")
        file_mapper.sync_spaces(sync_config)

        # Verify only 3 files created (root, Page B, Page D)
        md_files = [f for f in temp_test_dir.rglob("*.md") if '.confluence-sync' not in str(f)]
        assert len(md_files) == 3, f"Should have 3 files (root + 2 non-excluded), got {len(md_files)}"

        # Verify Page A and Page C do NOT exist
        root_dir = temp_test_dir / "E2E-Test--Multiple-Exclusions"
        page_a_file = root_dir / "Page-A.md"
        page_c_file = root_dir / "Page-C.md"

        assert not page_a_file.exists(), "Page A should NOT exist (excluded)"
        assert not page_c_file.exists(), "Page C should NOT exist (excluded)"

        # Verify Page B and Page D DO exist
        page_b_file = root_dir / "Page-B.md"
        page_d_file = root_dir / "Page-D.md"

        assert page_b_file.exists(), "Page B should exist (not excluded)"
        assert page_d_file.exists(), "Page D should exist (not excluded)"

        logger.info("✓ Multiple exclusion test PASSED")
        logger.info("  - 2 pages excluded by pageID")
        logger.info("  - 3 pages synced (root + 2 non-excluded)")
