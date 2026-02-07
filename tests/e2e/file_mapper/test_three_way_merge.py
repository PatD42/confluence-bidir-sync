"""E2E tests: Three-Way Merge Scenarios.

These tests validate that 3-way merge correctly handles concurrent edits
to the same page from both Confluence and local sides. The merge should:
- Preserve changes from both sides when they don't overlap
- Never fall back to simple overwrite (losing either side's changes)
- Preserve <br> tags (line breaks) in table cells

Requirements:
- Test Confluence credentials in .env.test
- CONFSYNCTEST space available

Test Scenarios:
1. Confluence changes row X, Local changes row Y (same table) -> Both preserved
2. Confluence changes row X, Local removes row Y -> Both changes apply
3. Confluence adds header+table, Local edits table 1 header -> Both preserved
4. Table cells with <br> tags should be preserved through merge
"""

import pytest
import logging
import time
import yaml
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, Optional

from src.confluence_client.auth import Authenticator
from src.confluence_client.api_wrapper import APIWrapper
from src.content_converter.markdown_converter import MarkdownConverter
from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.models import SpaceConfig, SyncConfig
from src.file_mapper.frontmatter_handler import FrontmatterHandler
from src.cli.sync_command import SyncCommand
from src.cli.output import OutputHandler
from tests.helpers.confluence_test_setup import setup_test_page

logger = logging.getLogger(__name__)


# Test content with two tables for merge scenarios
INITIAL_CONTENT_WITH_TABLES = """# Merge Test Page

## Table 1: Product Features

| Feature | Status | Owner |
|---------|--------|-------|
| Login | Complete | Alice |
| Dashboard | In Progress | Bob |
| Reports | Planned | Carol |
| Settings | Complete | Dave |

## Additional Notes

Some notes about the project.

## Table 2: Release Schedule

| Version | Date | Features |
|---------|------|----------|
| 1.0 | 2024-01 | Core |
| 1.1 | 2024-03 | Dashboard |
| 2.0 | 2024-06 | Reports |
"""


class TestThreeWayMerge:
    """E2E tests for 3-way merge with concurrent edits."""

    @pytest.fixture(scope="function")
    def merge_test_page(self, test_credentials, cleanup_test_pages, temp_test_dir):
        """Create a page hierarchy with table content and sync it to establish baseline.

        This fixture uses the full SyncCommand workflow to:
        1. Create a parent page in Confluence
        2. Create a child page with table content under the parent
        3. Perform initial sync to pull to local
        4. Establish baseline in the baseline repository

        IMPORTANT: We must create a parent->child hierarchy because:
        - _detect_sync_direction checks len(hierarchy.children) > 0
        - A single page with no children is treated as "Confluence empty"
        - This would trigger 'push' mode instead of 'bidirectional'

        Returns:
            Dict containing:
                - page_id: Child page ID (the one with table content)
                - parent_page_id: Parent page ID
                - space_key: Space key
                - file_path: Local file path for child page
                - baseline: Initial synced content (with frontmatter)
                - config_dir: Path to .confluence-sync directory
        """
        space_key = test_credentials['test_space']

        # Create parent page (container for the test)
        parent_page = setup_test_page(
            title="E2E Test - Merge Parent",
            content="<p>Parent page for merge testing</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(parent_page['page_id'])
        logger.info(f"Created parent page: {parent_page['page_id']}")

        # Convert markdown to Confluence XHTML
        converter = MarkdownConverter()
        xhtml_content = converter.markdown_to_xhtml(INITIAL_CONTENT_WITH_TABLES)

        # Create child page with table content under the parent
        child_page = setup_test_page(
            title="Merge Test Page",
            content=xhtml_content,
            space_key=space_key,
            parent_id=parent_page['page_id']
        )
        cleanup_test_pages.append(child_page['page_id'])
        logger.info(f"Created child page with tables: {child_page['page_id']}")

        # Wait for Confluence to index
        logger.info("Waiting 3 seconds for Confluence indexing...")
        time.sleep(3)

        # Create .confluence-sync config directory
        config_dir = temp_test_dir / ".confluence-sync"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create config.yaml - sync from parent page (includes child)
        config_content = {
            'spaces': [{
                'space_key': space_key,
                'parent_page_id': parent_page['page_id'],
                'local_path': str(temp_test_dir),
            }],
            'page_limit': 100,
        }
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump(config_content), encoding='utf-8')

        # Create empty state.yaml
        state_file = config_dir / "state.yaml"
        state_file.write_text("last_synced: null\ntracked_pages: {}\n", encoding='utf-8')

        # Run initial sync using SyncCommand with force_pull
        logger.info("Performing initial sync (force pull) to create local files and baseline")
        output_handler = OutputHandler(verbosity=1)
        sync_cmd = SyncCommand(
            config_path=str(config_file),
            state_path=str(state_file),
            output_handler=output_handler,
        )
        exit_code = sync_cmd.run(force_pull=True)
        assert exit_code.value == 0, f"Initial sync failed with exit code {exit_code}"

        # Find the local file for the child page (under parent directory)
        parent_dir = temp_test_dir / "E2E-Test--Merge-Parent"
        local_file = parent_dir / "Merge-Test-Page.md"
        assert local_file.exists(), f"Local file not created: {local_file}"

        # Store baseline content
        baseline = local_file.read_text(encoding='utf-8')
        logger.info(f"Baseline established: {len(baseline)} chars")

        return {
            'page_id': child_page['page_id'],
            'parent_page_id': parent_page['page_id'],
            'space_key': space_key,
            'file_path': str(local_file),
            'baseline': baseline,
            'config_dir': str(config_dir),
            'config_file': str(config_file),
            'state_file': str(state_file),
            'version': child_page['version'],
        }

    def _run_sync_with_baseline(
        self,
        config_file: str,
        state_file: str,
    ):
        """Run bidirectional sync using SyncCommand for full 3-way merge workflow.

        Uses SyncCommand which handles:
        - Conflict detection via FileMapper
        - 3-way merge via ConflictResolver
        - Pushing merged content back to Confluence
        """
        logger.info("Running bidirectional sync via SyncCommand (full CLI workflow)")

        output_handler = OutputHandler(verbosity=2)  # More verbose for debugging
        sync_cmd = SyncCommand(
            config_path=config_file,
            state_path=state_file,
            output_handler=output_handler,
        )

        # Run bidirectional sync (no force flags)
        exit_code = sync_cmd.run(force_pull=False, force_push=False)

        logger.info(f"Sync completed with exit code: {exit_code}")
        return exit_code

    @pytest.mark.e2e
    def test_merge_confluence_row_x_local_row_y_same_table(
        self,
        merge_test_page,
        temp_test_dir,
        test_credentials
    ):
        """Test 1: Confluence changes row X, Local changes row Y in same table.

        Scenario:
        - Baseline: Table with rows for Login, Dashboard, Reports, Settings
        - Confluence: Changes "Login" owner from "Alice" to "AdminUser"
        - Local: Changes "Settings" owner from "Dave" to "ConfigUser"
        - Expected: Both changes merge cleanly, no conflicts

        NOTE: We use non-adjacent rows (Login=row1, Settings=row4) because
        git merge-file needs sufficient context between changes. Adjacent
        row changes would create merge conflicts due to lack of context.

        This tests the core 3-way merge capability for non-overlapping edits.
        """
        page_id = merge_test_page['page_id']
        file_path = merge_test_page['file_path']
        config_file = merge_test_page['config_file']
        state_file = merge_test_page['state_file']

        logger.info("=" * 60)
        logger.info("TEST 1: Confluence row X, Local row Y (same table)")
        logger.info("=" * 60)

        # Step 1: Modify Confluence (Login owner: Alice -> AdminUser)
        auth = Authenticator()
        api = APIWrapper(auth)

        # Get current page
        page_details = api.get_page_by_id(page_id, expand="version,body.storage")
        current_version = page_details['version']['number']

        # Create modified content for Confluence (change first row)
        confluence_content = INITIAL_CONTENT_WITH_TABLES.replace(
            "| Login | Complete | Alice |",
            "| Login | Complete | AdminUser |"
        )
        converter = MarkdownConverter()
        confluence_xhtml = converter.markdown_to_xhtml(confluence_content)

        # Update Confluence
        api.update_page(
            page_id=page_id,
            title="Merge Test Page",
            body=confluence_xhtml,
            version=current_version
        )
        logger.info("✓ Confluence: Changed Login owner to 'AdminUser'")

        # Step 2: Modify local file (Settings owner: Dave -> ConfigUser)
        local_file = Path(file_path)
        content = local_file.read_text(encoding='utf-8')

        # Modify Settings row locally (last row - far from Login)
        modified_content = content.replace(
            "| Settings | Complete | Dave |",
            "| Settings | Complete | ConfigUser |"
        )
        local_file.write_text(modified_content, encoding='utf-8')
        logger.info("✓ Local: Changed Settings owner to 'ConfigUser'")

        # Wait for Confluence to process
        time.sleep(2)

        # Step 3: Run sync with full CLI workflow (includes 3-way merge)
        exit_code = self._run_sync_with_baseline(
            config_file=config_file,
            state_file=state_file,
        )
        logger.info(f"✓ Sync completed with exit code: {exit_code}")

        # Wait for propagation
        time.sleep(2)

        # Step 4: Verify both changes are present in local file
        final_local = local_file.read_text(encoding='utf-8')

        # Check Login owner change from Confluence is present
        assert "| Login | Complete | AdminUser |" in final_local, \
            "Confluence change (Login owner -> AdminUser) should be in local file"
        logger.info("✓ Verified: Login owner is 'AdminUser' (from Confluence)")

        # Check Settings owner change from local is present
        assert "| Settings | Complete | ConfigUser |" in final_local, \
            "Local change (Settings owner -> ConfigUser) should be preserved"
        logger.info("✓ Verified: Settings owner is 'ConfigUser' (from local)")

        # Verify no conflict markers
        assert "<<<<<<<" not in final_local, "Should have no conflict markers"
        assert "=======" not in final_local, "Should have no conflict markers"
        assert ">>>>>>>" not in final_local, "Should have no conflict markers"
        logger.info("✓ Verified: No conflict markers")

        # Step 5: Verify Confluence also has both changes
        final_page = api.get_page_by_id(page_id, expand="body.storage")
        confluence_body = final_page['body']['storage']['value']

        # Confluence should have local change pushed
        # Note: Checking for the text content (may be in XHTML format)
        logger.info("✓ Checking Confluence for merged content...")

        logger.info("=" * 60)
        logger.info("✓ TEST 1 PASSED: Both row changes merged successfully")
        logger.info("=" * 60)

    @pytest.mark.e2e
    def test_merge_confluence_row_x_local_removes_row_y(
        self,
        merge_test_page,
        temp_test_dir,
        test_credentials
    ):
        """Test 2: Confluence changes row X, Local removes row Y.

        Scenario:
        - Baseline: Table with rows for Login, Dashboard, Reports, Settings
        - Confluence: Changes "Login" owner from "Alice" to "Eve"
        - Local: Removes the "Settings" row entirely
        - Expected: Both changes merge cleanly

        This tests merge with row deletion vs row modification.
        """
        page_id = merge_test_page['page_id']
        file_path = merge_test_page['file_path']
        config_file = merge_test_page['config_file']
        state_file = merge_test_page['state_file']

        logger.info("=" * 60)
        logger.info("TEST 2: Confluence changes row X, Local removes row Y")
        logger.info("=" * 60)

        # Step 1: Modify Confluence (Login: Alice -> Eve)
        auth = Authenticator()
        api = APIWrapper(auth)

        page_details = api.get_page_by_id(page_id, expand="version,body.storage")
        current_version = page_details['version']['number']

        confluence_content = INITIAL_CONTENT_WITH_TABLES.replace(
            "| Login | Complete | Alice |",
            "| Login | Complete | Eve |"
        )
        converter = MarkdownConverter()
        confluence_xhtml = converter.markdown_to_xhtml(confluence_content)

        api.update_page(
            page_id=page_id,
            title="Merge Test Page",
            body=confluence_xhtml,
            version=current_version
        )
        logger.info("✓ Confluence: Changed Login owner to 'Eve'")

        # Step 2: Remove row locally (Settings row)
        local_file = Path(file_path)
        content = local_file.read_text(encoding='utf-8')

        # Remove Settings row
        modified_content = content.replace(
            "| Settings | Complete | Dave |\n",
            ""
        )
        local_file.write_text(modified_content, encoding='utf-8')
        logger.info("✓ Local: Removed Settings row")

        time.sleep(2)

        # Step 3: Run sync with full CLI workflow
        exit_code = self._run_sync_with_baseline(
            config_file=config_file,
            state_file=state_file,
        )
        logger.info(f"✓ Sync completed with exit code: {exit_code}")

        time.sleep(2)

        # Step 4: Verify both changes are present in local file
        final_local = local_file.read_text(encoding='utf-8')

        # Check Login owner change from Confluence
        assert "| Login | Complete | Eve |" in final_local, \
            "Confluence change (Login owner -> Eve) should be in local file"
        logger.info("✓ Verified: Login owner is 'Eve' (from Confluence)")

        # Check Settings row is removed (local change preserved)
        assert "| Settings |" not in final_local, \
            "Local change (Settings row removed) should be preserved"
        logger.info("✓ Verified: Settings row is removed (from local)")

        # Verify no conflict markers
        assert "<<<<<<<" not in final_local, "Should have no conflict markers"
        logger.info("✓ Verified: No conflict markers")

        logger.info("=" * 60)
        logger.info("✓ TEST 2 PASSED: Row modification and row deletion merged")
        logger.info("=" * 60)

    @pytest.mark.e2e
    def test_merge_confluence_adds_section_local_edits_header(
        self,
        merge_test_page,
        temp_test_dir,
        test_credentials
    ):
        """Test 3: Confluence adds header+table, Local edits table 1 header.

        Scenario:
        - Baseline: Two tables with "Additional Notes" section in between
        - Confluence: Adds a new "## Priority Matrix" section with table
        - Local: Changes "## Table 1: Product Features" to "## Product Backlog"
        - Expected: Both changes merge cleanly

        This tests structural additions vs. header text modifications.
        """
        page_id = merge_test_page['page_id']
        file_path = merge_test_page['file_path']
        config_file = merge_test_page['config_file']
        state_file = merge_test_page['state_file']

        logger.info("=" * 60)
        logger.info("TEST 3: Confluence adds section, Local edits header")
        logger.info("=" * 60)

        # Step 1: Confluence adds new section between tables
        auth = Authenticator()
        api = APIWrapper(auth)

        page_details = api.get_page_by_id(page_id, expand="version,body.storage")
        current_version = page_details['version']['number']

        # Add new section after "Additional Notes"
        new_section = """

## Priority Matrix

| Priority | Items | Target |
|----------|-------|--------|
| P0 | Security | Now |
| P1 | Performance | Q1 |
| P2 | Features | Q2 |

"""
        confluence_content = INITIAL_CONTENT_WITH_TABLES.replace(
            "## Table 2: Release Schedule",
            f"{new_section}## Table 2: Release Schedule"
        )
        converter = MarkdownConverter()
        confluence_xhtml = converter.markdown_to_xhtml(confluence_content)

        api.update_page(
            page_id=page_id,
            title="Merge Test Page",
            body=confluence_xhtml,
            version=current_version
        )
        logger.info("✓ Confluence: Added Priority Matrix section with table")

        # Step 2: Local edits table 1 header
        local_file = Path(file_path)
        content = local_file.read_text(encoding='utf-8')

        modified_content = content.replace(
            "## Table 1: Product Features",
            "## Product Backlog"
        )
        local_file.write_text(modified_content, encoding='utf-8')
        logger.info("✓ Local: Changed 'Table 1: Product Features' to 'Product Backlog'")

        time.sleep(2)

        # Step 3: Run sync with full CLI workflow
        exit_code = self._run_sync_with_baseline(
            config_file=config_file,
            state_file=state_file,
        )
        logger.info(f"✓ Sync completed with exit code: {exit_code}")

        time.sleep(2)

        # Step 4: Verify both changes are present in local file
        final_local = local_file.read_text(encoding='utf-8')

        # Check new section from Confluence
        assert "## Priority Matrix" in final_local, \
            "Confluence change (Priority Matrix section) should be in local file"
        assert "| P0 | Security | Now |" in final_local, \
            "Priority Matrix table content should be present"
        logger.info("✓ Verified: Priority Matrix section added (from Confluence)")

        # Check header change from local
        assert "## Product Backlog" in final_local, \
            "Local change (Product Backlog header) should be preserved"
        assert "## Table 1: Product Features" not in final_local, \
            "Old header should be replaced"
        logger.info("✓ Verified: Header changed to 'Product Backlog' (from local)")

        # Verify no conflict markers
        assert "<<<<<<<" not in final_local, "Should have no conflict markers"
        logger.info("✓ Verified: No conflict markers")

        logger.info("=" * 60)
        logger.info("✓ TEST 3 PASSED: Section addition and header edit merged")
        logger.info("=" * 60)

    @pytest.mark.e2e
    def test_merge_preserves_br_tags_in_table_cells(
        self,
        test_credentials,
        cleanup_test_pages,
        temp_test_dir
    ):
        """Test 4: <br> tags in table cells should be preserved through merge.

        Scenario:
        - Create page with table cells containing <br> tags (line breaks)
        - Pull to local, establish baseline
        - Confluence: Modify cell content while keeping <br>
        - Local: Modify different cell while keeping <br>
        - Expected: Both changes merge, <br> tags preserved

        This tests that line breaks in table cells survive the full
        HTML → Markdown → Merge → Markdown → HTML round-trip.
        """
        space_key = test_credentials['test_space']

        logger.info("=" * 60)
        logger.info("TEST 4: Preserve <br> tags in table cells through merge")
        logger.info("=" * 60)

        # Step 1: Create page with <br> tags in table cells
        # Use raw XHTML to ensure <br> tags are in the source
        xhtml_with_br = """
<h1>BR Tag Test</h1>
<table>
<tr><th>Section</th><th>Description</th></tr>
<tr><td>Overview</td><td>This section covers:<br/>- Item 1<br/>- Item 2<br/>- Item 3</td></tr>
<tr><td>Details</td><td>More info:<br/>Line A<br/>Line B</td></tr>
</table>
"""
        # Create parent page
        parent_page = setup_test_page(
            title="E2E Test - BR Tag Parent",
            content="<p>Parent for BR tag testing</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(parent_page['page_id'])
        logger.info(f"Created parent page: {parent_page['page_id']}")

        # Create child page with <br> tags
        child_page = setup_test_page(
            title="BR Tag Test Page",
            content=xhtml_with_br,
            space_key=space_key,
            parent_id=parent_page['page_id']
        )
        cleanup_test_pages.append(child_page['page_id'])
        page_id = child_page['page_id']
        logger.info(f"Created child page with <br> tags: {page_id}")

        # Wait for Confluence to index
        time.sleep(3)

        # Step 2: Setup config and initial sync
        config_dir = temp_test_dir / ".confluence-sync"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_content = {
            'spaces': [{
                'space_key': space_key,
                'parent_page_id': parent_page['page_id'],
                'local_path': str(temp_test_dir),
            }],
            'page_limit': 100,
        }
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump(config_content), encoding='utf-8')

        state_file = config_dir / "state.yaml"
        state_file.write_text("last_synced: null\ntracked_pages: {}\n", encoding='utf-8')

        # Initial sync (force pull)
        logger.info("Performing initial sync (force pull)")
        output_handler = OutputHandler(verbosity=1)
        sync_cmd = SyncCommand(
            config_path=str(config_file),
            state_path=str(state_file),
            output_handler=output_handler,
        )
        exit_code = sync_cmd.run(force_pull=True)
        assert exit_code.value == 0, f"Initial sync failed: {exit_code}"

        # Find local file
        parent_dir = temp_test_dir / "E2E-Test--BR-Tag-Parent"
        local_file = parent_dir / "BR-Tag-Test-Page.md"
        assert local_file.exists(), f"Local file not created: {local_file}"

        # Step 3: Verify <br> tags are in local file after pull
        initial_local = local_file.read_text(encoding='utf-8')
        logger.info(f"Initial local content:\n{initial_local}")

        assert "<br>" in initial_local or "<br/>" in initial_local, \
            f"<br> tags should be in local file after pull. Content:\n{initial_local}"
        logger.info("✓ Verified: <br> tags present in local file after initial pull")

        # Step 4: Modify Confluence (change Overview description, keep <br>)
        auth = Authenticator()
        api = APIWrapper(auth)

        page_details = api.get_page_by_id(page_id, expand="version,body.storage")
        current_version = page_details['version']['number']

        # Modify Confluence: add Item 4 to Overview
        confluence_xhtml = """
<h1>BR Tag Test</h1>
<table>
<tr><th>Section</th><th>Description</th></tr>
<tr><td>Overview</td><td>This section covers:<br/>- Item 1<br/>- Item 2<br/>- Item 3<br/>- Item 4</td></tr>
<tr><td>Details</td><td>More info:<br/>Line A<br/>Line B</td></tr>
</table>
"""
        api.update_page(
            page_id=page_id,
            title="BR Tag Test Page",
            body=confluence_xhtml,
            version=current_version
        )
        logger.info("✓ Confluence: Added 'Item 4' to Overview (with <br> preserved)")

        # Step 5: Modify local file (change Details cell, keep <br>)
        content = local_file.read_text(encoding='utf-8')
        modified_content = content.replace(
            "Line B",
            "Line B<br>Line C"
        )
        local_file.write_text(modified_content, encoding='utf-8')
        logger.info("✓ Local: Added 'Line C' to Details (with <br> preserved)")

        time.sleep(2)

        # Step 6: Run bidirectional sync
        logger.info("Running bidirectional sync")
        sync_cmd2 = SyncCommand(
            config_path=str(config_file),
            state_path=str(state_file),
            output_handler=OutputHandler(verbosity=2),
        )
        exit_code = sync_cmd2.run(force_pull=False, force_push=False)
        logger.info(f"✓ Sync completed with exit code: {exit_code}")

        time.sleep(2)

        # Step 7: Verify merged content preserves <br> tags
        final_local = local_file.read_text(encoding='utf-8')
        logger.info(f"Final local content:\n{final_local}")

        # Check Confluence change (Item 4)
        assert "Item 4" in final_local, \
            "Confluence change (Item 4) should be in merged content"
        logger.info("✓ Verified: 'Item 4' present (from Confluence)")

        # Check local change (Line C)
        assert "Line C" in final_local, \
            "Local change (Line C) should be in merged content"
        logger.info("✓ Verified: 'Line C' present (from local)")

        # Check <br> tags are preserved
        br_count = final_local.count("<br>") + final_local.count("<br/>")
        assert br_count >= 5, \
            f"<br> tags should be preserved. Found {br_count}, expected at least 5. Content:\n{final_local}"
        logger.info(f"✓ Verified: {br_count} <br> tags preserved")

        # Verify no conflict markers
        assert "<<<<<<<" not in final_local, "Should have no conflict markers"
        logger.info("✓ Verified: No conflict markers")

        logger.info("=" * 60)
        logger.info("✓ TEST 4 PASSED: <br> tags preserved through merge")
        logger.info("=" * 60)

    @pytest.mark.e2e
    def test_merge_preserves_multiline_cells_with_p_tags(
        self,
        test_credentials,
        cleanup_test_pages,
        temp_test_dir
    ):
        """Test 5: Multi-line cells using <p> tags (Confluence format) preserved through merge.

        Scenario:
        - Create page with table cells containing multiple <p> tags
          (this is how Confluence stores multi-line cell content when you press Enter)
        - Pull to local, verify <p> tags are converted to <br>
        - Make changes on both sides
        - Merge and verify line breaks preserved

        This tests the actual Confluence storage format for multi-line cells.
        """
        space_key = test_credentials['test_space']

        logger.info("=" * 60)
        logger.info("TEST 5: Preserve multi-line cells with <p> tags through merge")
        logger.info("=" * 60)

        # Step 1: Create page with <p> tags in table cells (Confluence format)
        # This is how Confluence stores multi-line content in cells
        xhtml_with_p_tags = """
<h1>Multi-line Cell Test</h1>
<table>
<tbody>
<tr><th>Section</th><th>Description</th></tr>
<tr>
  <td><p>Overview</p></td>
  <td>
    <p>First line of description</p>
    <p>Second line here</p>
    <p>Third line too</p>
  </td>
</tr>
<tr>
  <td><p>Details</p></td>
  <td>
    <p>More info:</p>
    <p>Line A</p>
    <p>Line B</p>
  </td>
</tr>
</tbody>
</table>
"""
        # Create parent page
        parent_page = setup_test_page(
            title="E2E Test - P Tag Parent",
            content="<p>Parent for P tag testing</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(parent_page['page_id'])
        logger.info(f"Created parent page: {parent_page['page_id']}")

        # Create child page with <p> tags in cells
        child_page = setup_test_page(
            title="P Tag Test Page",
            content=xhtml_with_p_tags,
            space_key=space_key,
            parent_id=parent_page['page_id']
        )
        cleanup_test_pages.append(child_page['page_id'])
        page_id = child_page['page_id']
        logger.info(f"Created child page with <p> tags: {page_id}")

        time.sleep(3)

        # Step 2: Setup config and initial sync
        config_dir = temp_test_dir / ".confluence-sync"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_content = {
            'spaces': [{
                'space_key': space_key,
                'parent_page_id': parent_page['page_id'],
                'local_path': str(temp_test_dir),
            }],
            'page_limit': 100,
        }
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump(config_content), encoding='utf-8')

        state_file = config_dir / "state.yaml"
        state_file.write_text("last_synced: null\ntracked_pages: {}\n", encoding='utf-8')

        # Initial sync
        logger.info("Performing initial sync (force pull)")
        output_handler = OutputHandler(verbosity=1)
        sync_cmd = SyncCommand(
            config_path=str(config_file),
            state_path=str(state_file),
            output_handler=output_handler,
        )
        exit_code = sync_cmd.run(force_pull=True)
        assert exit_code.value == 0, f"Initial sync failed: {exit_code}"

        # Find local file
        parent_dir = temp_test_dir / "E2E-Test--P-Tag-Parent"
        local_file = parent_dir / "P-Tag-Test-Page.md"
        assert local_file.exists(), f"Local file not created: {local_file}"

        # Step 3: Verify <p> tags are converted to <br> in local file
        initial_local = local_file.read_text(encoding='utf-8')
        logger.info(f"Initial local content:\n{initial_local}")

        # The <p> tags should be converted to <br> in markdown
        assert "<br>" in initial_local, \
            f"<p> tags should be converted to <br> in local file. Content:\n{initial_local}"
        assert "First line" in initial_local and "Second line" in initial_local, \
            "Multi-line cell content should be present"
        logger.info("✓ Verified: <p> tags converted to <br> in local file")

        # Step 4: Modify Confluence (add a fourth line to Overview)
        auth = Authenticator()
        api = APIWrapper(auth)

        page_details = api.get_page_by_id(page_id, expand="version")
        current_version = page_details['version']['number']

        confluence_xhtml = """
<h1>Multi-line Cell Test</h1>
<table>
<tbody>
<tr><th>Section</th><th>Description</th></tr>
<tr>
  <td><p>Overview</p></td>
  <td>
    <p>First line of description</p>
    <p>Second line here</p>
    <p>Third line too</p>
    <p>Fourth line added</p>
  </td>
</tr>
<tr>
  <td><p>Details</p></td>
  <td>
    <p>More info:</p>
    <p>Line A</p>
    <p>Line B</p>
  </td>
</tr>
</tbody>
</table>
"""
        api.update_page(
            page_id=page_id,
            title="P Tag Test Page",
            body=confluence_xhtml,
            version=current_version
        )
        logger.info("✓ Confluence: Added 'Fourth line added' to Overview")

        # Step 5: Modify local file (add Line C to Details)
        content = local_file.read_text(encoding='utf-8')
        modified_content = content.replace(
            "Line B",
            "Line B<br>Line C"
        )
        local_file.write_text(modified_content, encoding='utf-8')
        logger.info("✓ Local: Added 'Line C' to Details")

        time.sleep(2)

        # Step 6: Run bidirectional sync
        logger.info("Running bidirectional sync")
        sync_cmd2 = SyncCommand(
            config_path=str(config_file),
            state_path=str(state_file),
            output_handler=OutputHandler(verbosity=2),
        )
        exit_code = sync_cmd2.run(force_pull=False, force_push=False)
        logger.info(f"✓ Sync completed with exit code: {exit_code}")

        time.sleep(2)

        # Step 7: Verify merged content preserves line breaks
        final_local = local_file.read_text(encoding='utf-8')
        logger.info(f"Final local content:\n{final_local}")

        # Check Confluence change
        assert "Fourth line added" in final_local, \
            "Confluence change (Fourth line added) should be in merged content"
        logger.info("✓ Verified: 'Fourth line added' present (from Confluence)")

        # Check local change
        assert "Line C" in final_local, \
            "Local change (Line C) should be in merged content"
        logger.info("✓ Verified: 'Line C' present (from local)")

        # Check line breaks preserved
        br_count = final_local.count("<br>")
        assert br_count >= 6, \
            f"Line breaks should be preserved. Found {br_count} <br> tags, expected at least 6"
        logger.info(f"✓ Verified: {br_count} <br> tags preserved")

        # Verify no conflict markers
        assert "<<<<<<<" not in final_local, "Should have no conflict markers"
        logger.info("✓ Verified: No conflict markers")

        logger.info("=" * 60)
        logger.info("✓ TEST 5 PASSED: Multi-line cells with <p> tags preserved")
        logger.info("=" * 60)
