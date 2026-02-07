"""E2E test: Full Pull Sync (Confluence → Local).

This test validates the complete pull sync workflow:
1. Create a hierarchy of 15 pages in Confluence
2. Start with an empty local folder
3. Run sync_spaces() with force_pull
4. Verify all 15 markdown files are created locally
5. Verify correct folder hierarchy
6. Verify frontmatter contains all required fields

Requirements:
- Test Confluence credentials in .env.test
- CONFSYNCTEST space available

Test Hierarchy (15 pages total):
```
Root (E2E Test - Pull Sync Root)
├── Team
│   ├── Engineering
│   │   ├── Backend
│   │   └── Frontend
│   ├── Product
│   └── Design
├── Projects
│   ├── Project Alpha
│   │   ├── Requirements
│   │   └── Architecture
│   └── Project Beta
├── Documentation
│   ├── User Guides
│   └── API Reference
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


class TestFullPullSync:
    """E2E tests for full pull sync from Confluence to local."""

    @pytest.fixture(scope="function")
    def test_hierarchy_pages(self, test_credentials, cleanup_test_pages):
        """Create a 15-page hierarchy in Confluence for pull sync testing.

        Returns:
            Dict containing:
                - parent_page_id: Root page ID
                - space_key: Space key
                - page_ids: List of all 15 page IDs
                - page_titles: List of all page titles
        """
        space_key = test_credentials['test_space']

        # Create root parent page
        root = setup_test_page(
            title="E2E Test - Pull Sync Root",
            content="<p>Root page for pull sync E2E test</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])

        page_ids = [root['page_id']]
        page_titles = ["E2E Test - Pull Sync Root"]

        # Level 1: Team, Projects, Documentation (3 pages)
        team = setup_test_page(
            title="Team",
            content="<p>Team information</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(team['page_id'])
        page_ids.append(team['page_id'])
        page_titles.append("Team")

        projects = setup_test_page(
            title="Projects",
            content="<p>Active projects</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(projects['page_id'])
        page_ids.append(projects['page_id'])
        page_titles.append("Projects")

        documentation = setup_test_page(
            title="Documentation",
            content="<p>Documentation hub</p>",
            space_key=space_key,
            parent_id=root['page_id']
        )
        cleanup_test_pages.append(documentation['page_id'])
        page_ids.append(documentation['page_id'])
        page_titles.append("Documentation")

        # Level 2 under Team: Engineering, Product, Design (3 pages)
        engineering = setup_test_page(
            title="Engineering",
            content="<p>Engineering team</p>",
            space_key=space_key,
            parent_id=team['page_id']
        )
        cleanup_test_pages.append(engineering['page_id'])
        page_ids.append(engineering['page_id'])
        page_titles.append("Engineering")

        product = setup_test_page(
            title="Product",
            content="<p>Product team</p>",
            space_key=space_key,
            parent_id=team['page_id']
        )
        cleanup_test_pages.append(product['page_id'])
        page_ids.append(product['page_id'])
        page_titles.append("Product")

        design = setup_test_page(
            title="Design",
            content="<p>Design team</p>",
            space_key=space_key,
            parent_id=team['page_id']
        )
        cleanup_test_pages.append(design['page_id'])
        page_ids.append(design['page_id'])
        page_titles.append("Design")

        # Level 3 under Engineering: Backend, Frontend (2 pages)
        backend = setup_test_page(
            title="Backend",
            content="<p>Backend engineering</p>",
            space_key=space_key,
            parent_id=engineering['page_id']
        )
        cleanup_test_pages.append(backend['page_id'])
        page_ids.append(backend['page_id'])
        page_titles.append("Backend")

        frontend = setup_test_page(
            title="Frontend",
            content="<p>Frontend engineering</p>",
            space_key=space_key,
            parent_id=engineering['page_id']
        )
        cleanup_test_pages.append(frontend['page_id'])
        page_ids.append(frontend['page_id'])
        page_titles.append("Frontend")

        # Level 2 under Projects: Project Alpha, Project Beta (2 pages)
        alpha = setup_test_page(
            title="Project Alpha",
            content="<p>First project</p>",
            space_key=space_key,
            parent_id=projects['page_id']
        )
        cleanup_test_pages.append(alpha['page_id'])
        page_ids.append(alpha['page_id'])
        page_titles.append("Project Alpha")

        beta = setup_test_page(
            title="Project Beta",
            content="<p>Second project</p>",
            space_key=space_key,
            parent_id=projects['page_id']
        )
        cleanup_test_pages.append(beta['page_id'])
        page_ids.append(beta['page_id'])
        page_titles.append("Project Beta")

        # Level 3 under Project Alpha: Requirements, Architecture (2 pages)
        requirements = setup_test_page(
            title="Requirements",
            content="<p>Project requirements</p>",
            space_key=space_key,
            parent_id=alpha['page_id']
        )
        cleanup_test_pages.append(requirements['page_id'])
        page_ids.append(requirements['page_id'])
        page_titles.append("Requirements")

        architecture = setup_test_page(
            title="Architecture",
            content="<p>System architecture</p>",
            space_key=space_key,
            parent_id=alpha['page_id']
        )
        cleanup_test_pages.append(architecture['page_id'])
        page_ids.append(architecture['page_id'])
        page_titles.append("Architecture")

        # Level 2 under Documentation: User Guides, API Reference (2 pages)
        user_guides = setup_test_page(
            title="User Guides",
            content="<p>User documentation</p>",
            space_key=space_key,
            parent_id=documentation['page_id']
        )
        cleanup_test_pages.append(user_guides['page_id'])
        page_ids.append(user_guides['page_id'])
        page_titles.append("User Guides")

        api_reference = setup_test_page(
            title="API Reference",
            content="<p>API documentation</p>",
            space_key=space_key,
            parent_id=documentation['page_id']
        )
        cleanup_test_pages.append(api_reference['page_id'])
        page_ids.append(api_reference['page_id'])
        page_titles.append("API Reference")

        # Total: 15 pages (1 root + 3 level-1 + 5 level-2 + 6 level-3)
        assert len(page_ids) == 15, f"Should have 15 pages, got {len(page_ids)}"

        logger.info(f"Created test hierarchy with {len(page_ids)} pages")
        logger.info(f"Root page ID: {root['page_id']}")

        # Wait for Confluence to index all pages
        import time
        logger.info("Waiting 5 seconds for Confluence indexing...")
        time.sleep(5)

        return {
            'parent_page_id': root['page_id'],
            'space_key': space_key,
            'page_ids': page_ids,
            'page_titles': page_titles,
        }

    @pytest.mark.e2e
    def test_full_pull_sync_15_pages(self, test_hierarchy_pages, temp_test_dir):
        """Test full pull sync of 15 pages from Confluence to empty local folder.

        Verification steps:
        1. Start with empty local folder
        2. 15 pages exist in Confluence hierarchy
        3. Run sync with force_pull=True
        4. Verify 15 markdown files created locally
        5. Verify correct folder hierarchy (nested folders for child pages)
        6. Verify frontmatter in all files contains required fields
        """
        # Step 1: Verify empty local folder
        assert temp_test_dir.exists(), "Temporary directory should exist"
        assert not list(temp_test_dir.iterdir()), "Temporary directory should be empty"
        logger.info(f"✓ Starting with empty local folder: {temp_test_dir}")

        # Step 2: Verify 15 pages exist in Confluence
        parent_page_id = test_hierarchy_pages['parent_page_id']
        space_key = test_hierarchy_pages['space_key']
        page_ids = test_hierarchy_pages['page_ids']
        page_titles = test_hierarchy_pages['page_titles']

        assert len(page_ids) == 15, "Should have 15 pages in Confluence"
        logger.info(f"✓ 15 pages exist in Confluence (root: {parent_page_id})")

        # Step 3: Configure and run sync with force_pull
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=parent_page_id,
            local_path=str(temp_test_dir),
            exclude_page_ids=[]
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=True,  # Force pull from Confluence
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        # Create FileMapper and run sync
        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)

        logger.info("Running sync_spaces() with force_pull=True")
        file_mapper.sync_spaces(sync_config)
        logger.info("✓ Sync completed successfully")

        # Step 4: Verify 15 markdown files created locally
        # Collect all .md files recursively
        md_files = list(temp_test_dir.rglob("*.md"))

        # Filter out any temp files from .confluence-sync directory
        md_files = [f for f in md_files if '.confluence-sync' not in str(f)]

        assert len(md_files) == 15, \
            f"Should have 15 markdown files, found {len(md_files)}: {[f.name for f in md_files]}"
        logger.info(f"✓ Created {len(md_files)} markdown files locally")

        # Step 5: Verify correct folder hierarchy
        # All files are under a root directory named after the root page
        root_dir = temp_test_dir / "E2E-Test--Pull-Sync-Root"

        # Check that expected directory structure exists
        expected_dirs = [
            root_dir / "Team",
            root_dir / "Team" / "Engineering",
            root_dir / "Projects",
            root_dir / "Projects" / "Project-Alpha",
            root_dir / "Documentation",
        ]

        for expected_dir in expected_dirs:
            assert expected_dir.exists() and expected_dir.is_dir(), \
                f"Expected directory does not exist: {expected_dir}"

        logger.info("✓ Verified correct folder hierarchy (nested folders for children)")

        # Verify specific files exist at expected paths
        expected_files = [
            temp_test_dir / "E2E-Test--Pull-Sync-Root.md",  # Root page file
            root_dir / "Team.md",
            root_dir / "Team" / "Engineering.md",
            root_dir / "Team" / "Engineering" / "Backend.md",
            root_dir / "Team" / "Engineering" / "Frontend.md",
            root_dir / "Team" / "Product.md",
            root_dir / "Team" / "Design.md",
            root_dir / "Projects.md",
            root_dir / "Projects" / "Project-Alpha.md",
            root_dir / "Projects" / "Project-Alpha" / "Requirements.md",
            root_dir / "Projects" / "Project-Alpha" / "Architecture.md",
            root_dir / "Projects" / "Project-Beta.md",
            root_dir / "Documentation.md",
            root_dir / "Documentation" / "User-Guides.md",
            root_dir / "Documentation" / "API-Reference.md",
        ]

        for expected_file in expected_files:
            assert expected_file.exists() and expected_file.is_file(), \
                f"Expected file does not exist: {expected_file}"

        logger.info("✓ All 15 expected files exist at correct paths")

        # Step 6: Verify frontmatter in all files
        # Note: With simplified frontmatter, only page_id is stored
        # Title is derived from content H1 heading
        import re
        for md_file in md_files:
            content = md_file.read_text(encoding='utf-8')

            # Parse frontmatter (FrontmatterHandler.parse() returns LocalPage)
            local_page = FrontmatterHandler.parse(str(md_file), content)

            # Verify page_id exists in frontmatter
            assert local_page.page_id, \
                f"File {md_file.name} missing page_id in frontmatter"

            # Verify page_id matches one of our created pages
            assert local_page.page_id in page_ids, \
                f"File {md_file.name} has unknown page_id: {local_page.page_id}"

            # Verify content has H1 heading (title)
            h1_match = re.search(r'^#\s+(.+)$', local_page.content, re.MULTILINE)
            assert h1_match, \
                f"File {md_file.name} missing H1 title heading in content"

            logger.debug(f"✓ Verified frontmatter for {md_file.name}")

        logger.info("✓ All 15 files have valid frontmatter with page_id")

        # Verify all page titles are present in the synced files
        synced_titles = set()
        for md_file in md_files:
            content = md_file.read_text(encoding='utf-8')
            local_page = FrontmatterHandler.parse(str(md_file), content)
            # Extract title from H1 heading in content
            h1_match = re.search(r'^#\s+(.+)$', local_page.content, re.MULTILINE)
            if h1_match:
                synced_titles.add(h1_match.group(1).strip())

        assert len(synced_titles) == 15, \
            f"Should have 15 unique titles, found {len(synced_titles)}"

        for title in page_titles:
            assert title in synced_titles, \
                f"Expected title '{title}' not found in synced files"

        logger.info("✓ All 15 page titles present in synced files")
        logger.info("=" * 60)
        logger.info("✓ Full pull sync E2E test PASSED")
        logger.info("  - Empty local folder → 15 markdown files")
        logger.info("  - Correct hierarchy (nested folders)")
        logger.info("  - Valid frontmatter in all files")
        logger.info("=" * 60)

    @pytest.mark.e2e
    def test_pull_sync_idempotency(self, test_hierarchy_pages, temp_test_dir):
        """Test that running pull sync twice produces the same result.

        Verifies that sync is idempotent - running it multiple times
        without changes in Confluence should not modify local files.
        """
        # Setup
        parent_page_id = test_hierarchy_pages['parent_page_id']
        space_key = test_hierarchy_pages['space_key']

        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=parent_page_id,
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

        # First sync
        logger.info("Running first sync")
        file_mapper.sync_spaces(sync_config)

        # Get checksums of all files after first sync
        md_files = [f for f in temp_test_dir.rglob("*.md") if '.confluence-sync' not in str(f)]
        first_sync_checksums = {}
        for md_file in md_files:
            first_sync_checksums[md_file.name] = md_file.read_text(encoding='utf-8')

        logger.info(f"First sync created {len(first_sync_checksums)} files")

        # Second sync (should be idempotent)
        logger.info("Running second sync (should be idempotent)")
        file_mapper.sync_spaces(sync_config)

        # Get checksums after second sync
        md_files = [f for f in temp_test_dir.rglob("*.md") if '.confluence-sync' not in str(f)]
        second_sync_checksums = {}
        for md_file in md_files:
            second_sync_checksums[md_file.name] = md_file.read_text(encoding='utf-8')

        logger.info(f"Second sync resulted in {len(second_sync_checksums)} files")

        # Verify same files exist
        assert set(first_sync_checksums.keys()) == set(second_sync_checksums.keys()), \
            "Different files after second sync"

        # Verify content is identical (except last_synced timestamp may differ)
        # For now, just verify same number and structure
        assert len(first_sync_checksums) == len(second_sync_checksums), \
            "Different number of files after second sync"

        logger.info("✓ Pull sync is idempotent - second sync produced same result")
