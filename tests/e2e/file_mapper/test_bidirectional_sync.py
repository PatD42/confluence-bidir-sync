"""E2E test: Bidirectional Sync.

This test validates the bidirectional sync workflow:
1. Create and sync 5 pages initially
2. Edit 2 pages locally (update markdown content)
3. Edit 2 different pages remotely (update via Confluence API)
4. Run sync again
5. Verify all changes are synced correctly in both directions

Requirements:
- Test Confluence credentials in .env.test
- CONFSYNCTEST space available

Test Hierarchy (5 pages total):
```
Root (E2E Test - Bidirectional Sync Root)
├── Page A (will be edited locally)
├── Page B (will be edited locally)
├── Page C (will be edited remotely)
├── Page D (will be edited remotely)
└── Page E (unchanged control)
```
"""

import pytest
import logging
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, Optional

from src.confluence_client.auth import Authenticator
from src.confluence_client.api_wrapper import APIWrapper
from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.models import SpaceConfig, SyncConfig
from src.file_mapper.frontmatter_handler import FrontmatterHandler
from src.file_mapper.filesafe_converter import FilesafeConverter
from tests.helpers.confluence_test_setup import setup_test_page

logger = logging.getLogger(__name__)


class TestBidirectionalSync:
    """E2E tests for bidirectional sync between Confluence and local files."""

    @pytest.fixture(scope="function")
    def synced_test_pages(self, test_credentials, cleanup_test_pages, temp_test_dir):
        """Create 5 pages in Confluence and sync them locally.

        This creates the initial state: 5 pages that are fully synced
        between Confluence and local filesystem.

        Returns:
            Dict containing:
                - parent_page_id: Root page ID
                - space_key: Space key
                - pages: List of page info dicts with page_id, title, file_path
        """
        space_key = test_credentials['test_space']

        # Create root parent page
        root = setup_test_page(
            title="E2E Test - Bidirectional Sync Root",
            content="<p>Root page for bidirectional sync E2E test</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(root['page_id'])

        # Create 5 child pages
        page_titles = ["Page A", "Page B", "Page C", "Page D", "Page E"]
        pages = []

        for title in page_titles:
            page = setup_test_page(
                title=title,
                content=f"<p>Initial content for {title}</p>",
                space_key=space_key,
                parent_id=root['page_id']
            )
            cleanup_test_pages.append(page['page_id'])
            pages.append({
                'page_id': page['page_id'],
                'title': title,
                'version': page['version']
            })
            logger.info(f"Created page: {title} (ID: {page['page_id']})")

        # Wait for Confluence to index all pages
        import time
        logger.info("Waiting 3 seconds for Confluence indexing...")
        time.sleep(3)

        # Perform initial sync to create local files
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

        logger.info("Performing initial sync to create local files")
        file_mapper.sync_spaces(sync_config)

        # Verify local files were created and build baseline dictionary
        root_dir = temp_test_dir / "E2E-Test--Bidirectional-Sync-Root"
        baselines: Dict[str, str] = {}

        # Store baseline for root page
        root_file = temp_test_dir / "E2E-Test--Bidirectional-Sync-Root.md"
        if root_file.exists():
            baselines[root['page_id']] = root_file.read_text(encoding='utf-8')
            logger.info(f"Stored baseline for root page: {root['page_id']}")

        for page in pages:
            filename = FilesafeConverter.title_to_filename(page['title'])
            file_path = root_dir / filename
            assert file_path.exists(), f"Local file not created: {file_path}"
            page['file_path'] = str(file_path)
            # Store baseline content for each page
            baselines[page['page_id']] = file_path.read_text(encoding='utf-8')
            logger.info(f"Verified local file and stored baseline: {file_path}")

        # Record timestamp after initial sync
        last_synced = datetime.now(UTC).isoformat()
        logger.info(f"Initial sync complete: {len(pages)} pages synced, last_synced={last_synced}")

        return {
            'parent_page_id': root['page_id'],
            'space_key': space_key,
            'pages': pages,
            'baselines': baselines,
            'last_synced': last_synced,
        }

    @pytest.mark.e2e
    def test_bidirectional_sync_no_conflicts(
        self,
        synced_test_pages,
        temp_test_dir,
        test_credentials
    ):
        """Test bidirectional sync with changes on both sides (no conflicts).

        Verification steps:
        1. Start with 5 synced pages
        2. Edit 2 pages locally (Page A, Page B)
        3. Edit 2 different pages remotely (Page C, Page D)
        4. Run sync
        5. Verify all 4 changes are synced correctly
        6. Verify Page E (unchanged) remains unchanged
        """
        parent_page_id = synced_test_pages['parent_page_id']
        space_key = synced_test_pages['space_key']
        pages = synced_test_pages['pages']
        baselines = synced_test_pages['baselines']
        last_synced = synced_test_pages['last_synced']

        # Create baseline lookup function
        def get_baseline(page_id: str) -> Optional[str]:
            return baselines.get(page_id)

        # Step 1: Verify we have 5 synced pages
        assert len(pages) == 5, f"Should have 5 pages, got {len(pages)}"
        logger.info(f"✓ Starting with {len(pages)} synced pages")

        # Step 2: Edit 2 pages locally (Page A and Page B)
        page_a = next(p for p in pages if p['title'] == "Page A")
        page_b = next(p for p in pages if p['title'] == "Page B")

        # Read and modify Page A locally
        page_a_path = Path(page_a['file_path'])
        content_a = page_a_path.read_text(encoding='utf-8')
        local_page_a = FrontmatterHandler.parse(str(page_a_path), content_a)
        local_page_a.content = "# Page A\n\nLocally edited content for Page A"
        updated_content_a = FrontmatterHandler.generate(local_page_a)
        page_a_path.write_text(updated_content_a, encoding='utf-8')
        logger.info(f"✓ Edited Page A locally")

        # Read and modify Page B locally
        page_b_path = Path(page_b['file_path'])
        content_b = page_b_path.read_text(encoding='utf-8')
        local_page_b = FrontmatterHandler.parse(str(page_b_path), content_b)
        local_page_b.content = "# Page B\n\nLocally edited content for Page B"
        updated_content_b = FrontmatterHandler.generate(local_page_b)
        page_b_path.write_text(updated_content_b, encoding='utf-8')
        logger.info(f"✓ Edited Page B locally")

        # Step 3: Edit 2 different pages remotely (Page C and Page D)
        page_c = next(p for p in pages if p['title'] == "Page C")
        page_d = next(p for p in pages if p['title'] == "Page D")

        auth = Authenticator()
        api = APIWrapper(auth)

        # Update Page C remotely
        page_c_details = api.get_page_by_id(page_c['page_id'])
        result_c = api.update_page(
            page_id=page_c['page_id'],
            title="Page C",
            body="<p>Remotely edited content for Page C</p>",
            version=page_c_details['version']['number']
        )
        new_version_c = result_c.get('version', {}).get('number', 'unknown')
        logger.info(f"✓ Edited Page C remotely (version {new_version_c})")

        # Update Page D remotely
        page_d_details = api.get_page_by_id(page_d['page_id'])
        result_d = api.update_page(
            page_id=page_d['page_id'],
            title="Page D",
            body="<p>Remotely edited content for Page D</p>",
            version=page_d_details['version']['number']
        )
        new_version_d = result_d.get('version', {}).get('number', 'unknown')
        logger.info(f"✓ Edited Page D remotely (version {new_version_d})")

        # Wait for Confluence to process updates
        import time
        logger.info("Waiting 3 seconds for Confluence to process updates...")
        time.sleep(3)

        # Step 4: Run bidirectional sync with hybrid change detection
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
            force_push=False,  # No force flags - bidirectional sync
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp"),
            last_synced=last_synced,  # For mtime comparison
            get_baseline=get_baseline,  # For content comparison
        )

        file_mapper = FileMapper(authenticator=auth)

        logger.info(f"Running bidirectional sync with change detection (last_synced={last_synced})")
        file_mapper.sync_spaces(sync_config)
        logger.info("✓ Sync completed")

        # Wait for changes to propagate
        time.sleep(2)

        # Step 5: Verify all 4 changes are synced correctly

        # Verify Page A changes pushed to Confluence
        page_a_remote = api.get_page_by_id(page_a['page_id'])
        # Note: Content comparison might need HTML parsing, for now just verify it was updated
        # We'll check that the version number increased as a proxy for update
        assert page_a_remote['version']['number'] > page_a['version'], \
            f"Page A should be updated in Confluence (version {page_a_remote['version']['number']})"
        logger.info(f"✓ Page A changes pushed to Confluence (version {page_a_remote['version']['number']})")

        # Verify Page B changes pushed to Confluence
        page_b_remote = api.get_page_by_id(page_b['page_id'])
        assert page_b_remote['version']['number'] > page_b['version'], \
            f"Page B should be updated in Confluence (version {page_b_remote['version']['number']})"
        logger.info(f"✓ Page B changes pushed to Confluence (version {page_b_remote['version']['number']})")

        # Verify Page C changes pulled to local
        page_c_path = Path(page_c['file_path'])
        content_c = page_c_path.read_text(encoding='utf-8')
        local_page_c = FrontmatterHandler.parse(str(page_c_path), content_c)
        assert "Remotely edited content for Page C" in local_page_c.content, \
            f"Page C should have remote changes locally"
        logger.info(f"✓ Page C changes pulled to local")

        # Verify Page D changes pulled to local
        page_d_path = Path(page_d['file_path'])
        content_d = page_d_path.read_text(encoding='utf-8')
        local_page_d = FrontmatterHandler.parse(str(page_d_path), content_d)
        assert "Remotely edited content for Page D" in local_page_d.content, \
            f"Page D should have remote changes locally"
        logger.info(f"✓ Page D changes pulled to local")

        # Step 6: Verify Page E (unchanged) remains unchanged
        page_e = next(p for p in pages if p['title'] == "Page E")
        page_e_remote = api.get_page_by_id(page_e['page_id'])
        assert page_e_remote['version']['number'] == page_e['version'], \
            f"Page E should not be modified (version {page_e_remote['version']['number']})"

        page_e_path = Path(page_e['file_path'])
        content_e = page_e_path.read_text(encoding='utf-8')
        local_page_e = FrontmatterHandler.parse(str(page_e_path), content_e)
        assert "Initial content for Page E" in local_page_e.content, \
            f"Page E should have original content locally"
        logger.info(f"✓ Page E remains unchanged")

        logger.info("=" * 60)
        logger.info("✓ Bidirectional sync E2E test PASSED")
        logger.info("  - 2 local edits pushed to Confluence (Page A, B)")
        logger.info("  - 2 remote edits pulled to local (Page C, D)")
        logger.info("  - 1 unchanged page remains unchanged (Page E)")
        logger.info("=" * 60)

    @pytest.mark.e2e
    @pytest.mark.skip(reason="Bidirectional sync not fully implemented in MVP")
    def test_bidirectional_sync_with_conflict_detection(
        self,
        synced_test_pages,
        temp_test_dir
    ):
        """Test bidirectional sync with conflicting changes (same page edited both sides).

        This test verifies that the system can detect and handle conflicts when
        the same page is modified on both sides. This is a future enhancement
        beyond the MVP scope.

        NOTE: This test is skipped in MVP as conflict detection is not implemented.
        """
        # TODO: Implement conflict detection test when bidirectional sync is fully implemented
        pass
