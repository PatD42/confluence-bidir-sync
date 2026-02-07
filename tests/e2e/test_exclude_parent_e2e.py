"""E2E test: --excludeParent option.

This test validates the --excludeParent CLI option:
1. Create a parent page with children in Confluence
2. Initialize with --excludeParent option
3. Verify config has exclude_parent: true
4. Run sync
5. Verify parent page is NOT synced locally
6. Verify child pages ARE synced

Requirements:
- Test Confluence credentials in .env.test
- CONFSYNCTEST space available

Test Hierarchy:
```
Parent (E2E Test - Exclude Parent Root) <- EXCLUDED by --excludeParent
├── Child A (synced)
├── Child B (synced)
└── Child C (synced)
```
"""

import os
import pytest
import logging
import yaml
from pathlib import Path

from src.confluence_client.auth import Authenticator
from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.config_loader import ConfigLoader
from src.file_mapper.models import SpaceConfig, SyncConfig
from tests.helpers.confluence_test_setup import setup_test_page

logger = logging.getLogger(__name__)


class TestExcludeParent:
    """E2E tests for --excludeParent CLI option."""

    @pytest.fixture(scope="function")
    def parent_with_children(self, test_credentials, cleanup_test_pages):
        """Create a parent page with children for testing --excludeParent.

        Returns:
            Dict containing:
                - parent_page_id: Parent page ID (to be excluded)
                - space_key: Space key
                - confluence_base_url: Base Confluence URL
                - child_page_ids: List of child page IDs (to be synced)
        """
        space_key = test_credentials['test_space']
        confluence_base_url = test_credentials['confluence_url']

        # Create parent page
        parent = setup_test_page(
            title="E2E Test - Exclude Parent Root",
            content="<p>This is the parent page that should be excluded.</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(parent['page_id'])
        logger.info(f"Created parent page: {parent['page_id']}")

        child_page_ids = []

        # Create Child A
        child_a = setup_test_page(
            title="Child A",
            content="<p>Child A content - should be synced.</p>",
            space_key=space_key,
            parent_id=parent['page_id']
        )
        cleanup_test_pages.append(child_a['page_id'])
        child_page_ids.append(child_a['page_id'])
        logger.info(f"Created Child A: {child_a['page_id']}")

        # Create Child B
        child_b = setup_test_page(
            title="Child B",
            content="<p>Child B content - should be synced.</p>",
            space_key=space_key,
            parent_id=parent['page_id']
        )
        cleanup_test_pages.append(child_b['page_id'])
        child_page_ids.append(child_b['page_id'])
        logger.info(f"Created Child B: {child_b['page_id']}")

        # Create Child C
        child_c = setup_test_page(
            title="Child C",
            content="<p>Child C content - should be synced.</p>",
            space_key=space_key,
            parent_id=parent['page_id']
        )
        cleanup_test_pages.append(child_c['page_id'])
        child_page_ids.append(child_c['page_id'])
        logger.info(f"Created Child C: {child_c['page_id']}")

        # Wait for Confluence to index
        import time
        logger.info("Waiting 3 seconds for Confluence indexing...")
        time.sleep(3)

        return {
            'parent_page_id': parent['page_id'],
            'space_key': space_key,
            'confluence_base_url': confluence_base_url,
            'child_page_ids': child_page_ids,
        }

    @pytest.mark.e2e
    def test_exclude_parent_sync_behavior(self, parent_with_children, temp_test_dir):
        """Test that exclude_parent=True excludes the parent page from sync.

        This tests the sync behavior directly using SpaceConfig.exclude_parent=True.

        Verification steps:
        1. Start with empty local folder
        2. Configure sync with exclude_parent=True
        3. Run sync
        4. Verify parent page is NOT synced (no root .md file)
        5. Verify all 3 child pages ARE synced
        """
        # Step 1: Verify empty local folder
        assert temp_test_dir.exists(), "Temporary directory should exist"
        logger.info(f"✓ Starting with empty local folder: {temp_test_dir}")

        # Step 2: Get test hierarchy info
        parent_page_id = parent_with_children['parent_page_id']
        space_key = parent_with_children['space_key']
        confluence_base_url = parent_with_children['confluence_base_url']
        child_page_ids = parent_with_children['child_page_ids']

        logger.info(f"Parent page ID (to be excluded): {parent_page_id}")
        logger.info(f"Child page IDs (to be synced): {child_page_ids}")

        # Step 3: Configure sync with exclude_parent=True
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=parent_page_id,
            local_path=str(temp_test_dir),
            exclude_page_ids=[],
            exclude_parent=True,  # THIS IS WHAT WE'RE TESTING
            confluence_base_url=confluence_base_url
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=True,
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        logger.info("✓ Configured sync with exclude_parent=True")

        # Step 4: Run sync
        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)

        logger.info("Running sync with exclude_parent=True")
        file_mapper.sync_spaces(sync_config)
        logger.info("✓ Sync completed")

        # Step 5: Verify parent page is NOT synced
        # When exclude_parent=True, there should be no root .md file
        # Only child pages should exist
        md_files = [f for f in temp_test_dir.rglob("*.md") if '.confluence-sync' not in str(f)]
        logger.info(f"Found {len(md_files)} markdown files: {[f.name for f in md_files]}")

        # There should be exactly 3 files (the children)
        assert len(md_files) == 3, \
            f"Should have 3 markdown files (children only), found {len(md_files)}: {[f.name for f in md_files]}"
        logger.info("✓ Correct number of files (3 children, parent excluded)")

        # Verify the parent .md file does NOT exist
        parent_file = temp_test_dir / "E2E-Test--Exclude-Parent-Root.md"
        assert not parent_file.exists(), \
            f"Parent page file should NOT exist when exclude_parent=True: {parent_file}"
        logger.info("✓ Parent page file does NOT exist (correctly excluded)")

        # Step 6: Verify all 3 child pages ARE synced
        # Children should be at top level when parent is excluded
        expected_child_files = [
            temp_test_dir / "Child-A.md",
            temp_test_dir / "Child-B.md",
            temp_test_dir / "Child-C.md",
        ]

        for expected_file in expected_child_files:
            assert expected_file.exists(), \
                f"Child file should exist: {expected_file}"
            logger.info(f"✓ Child file exists: {expected_file.name}")

        logger.info("=" * 60)
        logger.info("✓ Exclude Parent E2E test PASSED")
        logger.info(f"  - Parent page excluded: {parent_page_id}")
        logger.info(f"  - 3 child pages synced")
        logger.info("  - Parent .md file does NOT exist")
        logger.info("  - All child .md files exist at top level")
        logger.info("=" * 60)

    @pytest.mark.e2e
    def test_exclude_parent_config_generation(self, parent_with_children, temp_test_dir):
        """Test that exclude_parent is correctly saved and loaded from config.

        This tests the config file generation and loading with exclude_parent=True.

        Verification steps:
        1. Create a SpaceConfig with exclude_parent=True
        2. Save to YAML
        3. Load from YAML
        4. Verify exclude_parent is preserved
        """
        parent_page_id = parent_with_children['parent_page_id']
        space_key = parent_with_children['space_key']
        confluence_base_url = parent_with_children['confluence_base_url']

        # Create config with exclude_parent=True
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=parent_page_id,
            local_path=str(temp_test_dir),
            exclude_page_ids=[],
            exclude_parent=True,
            confluence_base_url=confluence_base_url
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=".confluence-sync/temp"
        )

        # Save config
        config_path = temp_test_dir / ".confluence-sync" / "config.yaml"
        ConfigLoader.save(str(config_path), sync_config)
        logger.info(f"✓ Saved config to {config_path}")

        # Verify raw YAML content
        with open(config_path, 'r') as f:
            raw_yaml = yaml.safe_load(f)

        assert raw_yaml['spaces'][0]['exclude_parent'] is True, \
            "exclude_parent should be True in raw YAML"
        logger.info("✓ Raw YAML has exclude_parent: true")

        # Load config back
        loaded_config = ConfigLoader.load(str(config_path))
        logger.info("✓ Loaded config from file")

        # Verify exclude_parent is preserved
        assert loaded_config.spaces[0].exclude_parent is True, \
            "exclude_parent should be True after loading from YAML"
        logger.info("✓ exclude_parent is True after load")

        # Verify confluence_base_url is preserved
        assert loaded_config.spaces[0].confluence_base_url == confluence_base_url, \
            f"confluence_base_url should be {confluence_base_url}"
        logger.info("✓ confluence_base_url is preserved")

        logger.info("=" * 60)
        logger.info("✓ Config generation E2E test PASSED")
        logger.info("  - exclude_parent saved correctly to YAML")
        logger.info("  - exclude_parent loaded correctly from YAML")
        logger.info("  - confluence_base_url preserved")
        logger.info("=" * 60)
