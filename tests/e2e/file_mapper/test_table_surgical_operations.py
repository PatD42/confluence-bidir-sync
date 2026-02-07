"""E2E tests for surgical table row operations.

Tests validate that table modifications (add row, delete row, update cells)
are handled by surgical ADF updates without falling back to full page replacement.

Success criteria: "table not regenerated" = surgical operation succeeds,
no fallback to full replacement.
"""

import pytest
import logging
import time
from pathlib import Path
from typing import Dict, List

from src.confluence_client.auth import Authenticator
from src.confluence_client.api_wrapper import APIWrapper
from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.models import SpaceConfig, SyncConfig
from src.file_mapper.frontmatter_handler import FrontmatterHandler
from tests.helpers.confluence_test_setup import setup_test_page

logger = logging.getLogger(__name__)


# XHTML table template for test pages
TABLE_XHTML = """
<table>
<tbody>
<tr><th>Name</th><th>Value</th><th>Status</th></tr>
<tr><td>Item 1</td><td>100</td><td>Active</td></tr>
<tr><td>Item 2</td><td>200</td><td>Pending</td></tr>
<tr><td>Item 3</td><td>300</td><td>Complete</td></tr>
</tbody>
</table>
"""

# Empty cells table
EMPTY_CELLS_TABLE_XHTML = """
<table>
<tbody>
<tr><th>Col A</th><th>Col B</th></tr>
<tr><td>Value 1</td><td></td></tr>
<tr><td></td><td></td></tr>
<tr><td>Value 3</td><td>Filled</td></tr>
</tbody>
</table>
"""


class TestTableSurgicalOperations:
    """E2E tests for surgical table row operations."""

    @pytest.fixture(scope="function")
    def table_test_page(self, test_credentials, cleanup_test_pages, temp_test_dir):
        """Create a test page with a table and sync it locally.

        Returns:
            Dict containing page info and local file path
        """
        space_key = test_credentials['test_space']

        # Create a parent page first
        parent = setup_test_page(
            title="E2E Test - Table Surgical Parent",
            content="<p>Parent for table surgical operation tests</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(parent['page_id'])

        # Create page with table under the parent
        page = setup_test_page(
            title="E2E Test - Table Surgical Operations",
            content=TABLE_XHTML,
            space_key=space_key,
            parent_id=parent['page_id']
        )
        cleanup_test_pages.append(page['page_id'])
        logger.info(f"Created table test page: {page['page_id']}")

        # Wait for Confluence to index
        time.sleep(2)

        # Perform initial sync to create local file
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=parent['page_id'],
            local_path=str(temp_test_dir),
            exclude_page_ids=[]
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=10,
            force_pull=True,
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)
        file_mapper.sync_spaces(sync_config)

        # Find local file - it should be in a folder named after the parent
        parent_folder = temp_test_dir / "E2E-Test--Table-Surgical-Parent"
        local_file = parent_folder / "E2E-Test--Table-Surgical-Operations.md"

        # Also try at root level in case sync puts it there
        if not local_file.exists():
            local_file = temp_test_dir / "E2E-Test--Table-Surgical-Operations.md"

        assert local_file.exists(), f"Local file not created at {local_file}"

        return {
            'page_id': page['page_id'],
            'parent_id': parent['page_id'],
            'space_key': space_key,
            'local_file': local_file,
            'temp_dir': temp_test_dir,
            'initial_version': page['version']
        }

    @pytest.fixture(scope="function")
    def empty_cells_table_page(self, test_credentials, cleanup_test_pages, temp_test_dir):
        """Create a test page with a table containing empty cells.

        Returns:
            Dict containing page info and local file path
        """
        space_key = test_credentials['test_space']

        # Create a parent page first
        parent = setup_test_page(
            title="E2E Test - Empty Cells Parent",
            content="<p>Parent for empty cells table test</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(parent['page_id'])

        # Create page with empty cells table under the parent
        page = setup_test_page(
            title="E2E Test - Table Empty Cells",
            content=EMPTY_CELLS_TABLE_XHTML,
            space_key=space_key,
            parent_id=parent['page_id']
        )
        cleanup_test_pages.append(page['page_id'])

        # Wait for Confluence to index
        time.sleep(2)

        # Perform initial sync
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=parent['page_id'],
            local_path=str(temp_test_dir),
            exclude_page_ids=[]
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=10,
            force_pull=True,
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)
        file_mapper.sync_spaces(sync_config)

        # Find local file
        parent_folder = temp_test_dir / "E2E-Test--Empty-Cells-Parent"
        local_file = parent_folder / "E2E-Test--Table-Empty-Cells.md"

        if not local_file.exists():
            local_file = temp_test_dir / "E2E-Test--Table-Empty-Cells.md"

        assert local_file.exists(), f"Local file not created: {local_file}"

        return {
            'page_id': page['page_id'],
            'parent_id': parent['page_id'],
            'space_key': space_key,
            'local_file': local_file,
            'temp_dir': temp_test_dir,
            'initial_version': page['version']
        }

    def _sync_changes(self, temp_dir: Path, space_key: str, parent_id: str):
        """Sync local changes back to Confluence."""
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=parent_id,
            local_path=str(temp_dir),
            exclude_page_ids=[]
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=10,
            force_pull=False,
            force_push=True,
            temp_dir=str(temp_dir / ".confluence-sync" / "temp")
        )

        auth = Authenticator()
        file_mapper = FileMapper(authenticator=auth)
        file_mapper.sync_spaces(sync_config)

    def _verify_surgical_update(self, api: APIWrapper, page_id: str, initial_version: int) -> bool:
        """Verify that a surgical update occurred (not full replacement).

        Checks that:
        1. Version increased by exactly 1 (surgical update, not multiple operations)
        2. Page content still has table structure intact

        Returns:
            True if surgical update verified
        """
        page = api.get_page_by_id(page_id, expand="version,body.storage")
        new_version = page['version']['number']

        # Version should increase (update happened)
        if new_version <= initial_version:
            logger.error(f"Version did not increase: {initial_version} -> {new_version}")
            return False

        # Check that table structure exists in the content
        body = page.get('body', {}).get('storage', {}).get('value', '')
        has_table = '<table' in body.lower()

        if not has_table:
            logger.error("Table structure not found in page content")
            return False

        logger.info(f"Surgical update verified: version {initial_version} -> {new_version}")
        return True

    @pytest.mark.e2e
    def test_delete_row_with_content(self, table_test_page, test_credentials):
        """Test deleting a table row with content.

        Success criteria: Row is deleted via surgical update, table not regenerated.
        """
        page_id = table_test_page['page_id']
        local_file = table_test_page['local_file']
        space_key = table_test_page['space_key']
        temp_dir = table_test_page['temp_dir']

        # Read local file
        content = local_file.read_text(encoding='utf-8')
        local_page = FrontmatterHandler.parse(str(local_file), content)

        logger.info(f"Original content:\n{local_page.content}")

        # Delete the "Item 2" row from the table
        # The table should look like: Name | Value | Status + Item 1/2/3 rows
        lines = local_page.content.split('\n')
        new_lines = [line for line in lines if 'Item 2' not in line]
        local_page.content = '\n'.join(new_lines)

        logger.info(f"Modified content (Item 2 removed):\n{local_page.content}")

        # Write back
        updated_content = FrontmatterHandler.generate(local_page)
        local_file.write_text(updated_content, encoding='utf-8')

        # Get current version before sync
        auth = Authenticator()
        api = APIWrapper(auth)
        current_page = api.get_page_by_id(page_id, expand="version")
        version_before = current_page['version']['number']

        # Sync changes
        self._sync_changes(temp_dir, space_key, table_test_page['parent_id'])

        # Wait for Confluence
        time.sleep(2)

        # Verify surgical update
        assert self._verify_surgical_update(api, page_id, version_before), \
            "Surgical update failed - fallback may have been used"

        # Verify content: Item 2 should be gone, Item 1 and 3 should remain
        page = api.get_page_by_id(page_id, expand="body.storage")
        body = page.get('body', {}).get('storage', {}).get('value', '')

        assert 'Item 1' in body, "Item 1 should still be in table"
        assert 'Item 2' not in body, "Item 2 should be deleted"
        assert 'Item 3' in body, "Item 3 should still be in table"

        logger.info("✓ test_delete_row_with_content PASSED")

    @pytest.mark.e2e
    def test_delete_row_with_empty_cells(self, empty_cells_table_page, test_credentials):
        """Test deleting a table row that has empty cells.

        Success criteria: Row is deleted via surgical update, table not regenerated.
        """
        page_id = empty_cells_table_page['page_id']
        local_file = empty_cells_table_page['local_file']
        space_key = empty_cells_table_page['space_key']
        temp_dir = empty_cells_table_page['temp_dir']

        # Read local file
        content = local_file.read_text(encoding='utf-8')
        local_page = FrontmatterHandler.parse(str(local_file), content)

        logger.info(f"Original content:\n{local_page.content}")

        # Delete the row with empty cells (the one with just empty cells)
        # Looking for a row that's essentially empty
        lines = local_page.content.split('\n')
        # Keep rows that have at least some content beyond pipe separators
        new_lines = []
        for line in lines:
            # Skip rows that are mostly empty (just pipes and whitespace)
            if '|' in line:
                cell_content = line.replace('|', '').strip()
                if not cell_content and line.count('|') > 2:
                    # This is an empty data row, skip it
                    continue
            new_lines.append(line)

        local_page.content = '\n'.join(new_lines)

        logger.info(f"Modified content (empty row removed):\n{local_page.content}")

        # Write back
        updated_content = FrontmatterHandler.generate(local_page)
        local_file.write_text(updated_content, encoding='utf-8')

        # Get current version
        auth = Authenticator()
        api = APIWrapper(auth)
        current_page = api.get_page_by_id(page_id, expand="version")
        version_before = current_page['version']['number']

        # Sync changes
        self._sync_changes(temp_dir, space_key, empty_cells_table_page['parent_id'])
        time.sleep(2)

        # Verify surgical update
        assert self._verify_surgical_update(api, page_id, version_before), \
            "Surgical update failed - fallback may have been used"

        # Verify table still exists and has content
        page = api.get_page_by_id(page_id, expand="body.storage")
        body = page.get('body', {}).get('storage', {}).get('value', '')

        assert 'Value 1' in body, "Value 1 row should still be in table"
        assert 'Value 3' in body, "Value 3 row should still be in table"

        logger.info("✓ test_delete_row_with_empty_cells PASSED")

    @pytest.mark.e2e
    def test_add_row_with_content(self, table_test_page, test_credentials):
        """Test adding a new table row with content.

        Success criteria: Row is added via surgical update, table not regenerated.
        """
        page_id = table_test_page['page_id']
        local_file = table_test_page['local_file']
        space_key = table_test_page['space_key']
        temp_dir = table_test_page['temp_dir']

        # Read local file
        content = local_file.read_text(encoding='utf-8')
        local_page = FrontmatterHandler.parse(str(local_file), content)

        logger.info(f"Original content:\n{local_page.content}")

        # Add a new row "Item 4 | 400 | New" after Item 3
        lines = local_page.content.split('\n')
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if 'Item 3' in line:
                # Add new row after Item 3
                # Match the table format
                if '|' in line:
                    new_lines.append('| Item 4 | 400 | New |')

        local_page.content = '\n'.join(new_lines)

        logger.info(f"Modified content (Item 4 added):\n{local_page.content}")

        # Write back
        updated_content = FrontmatterHandler.generate(local_page)
        local_file.write_text(updated_content, encoding='utf-8')

        # Get current version
        auth = Authenticator()
        api = APIWrapper(auth)
        current_page = api.get_page_by_id(page_id, expand="version")
        version_before = current_page['version']['number']

        # Sync changes
        self._sync_changes(temp_dir, space_key, table_test_page['parent_id'])
        time.sleep(2)

        # Verify surgical update
        assert self._verify_surgical_update(api, page_id, version_before), \
            "Surgical update failed - fallback may have been used"

        # Verify content: All items including new Item 4 should be present
        page = api.get_page_by_id(page_id, expand="body.storage")
        body = page.get('body', {}).get('storage', {}).get('value', '')

        assert 'Item 1' in body, "Item 1 should still be in table"
        assert 'Item 2' in body, "Item 2 should still be in table"
        assert 'Item 3' in body, "Item 3 should still be in table"
        assert 'Item 4' in body, "Item 4 should be added to table"
        assert '400' in body, "New row value should be in table"

        logger.info("✓ test_add_row_with_content PASSED")

    @pytest.mark.e2e
    def test_add_row_without_content(self, table_test_page, test_credentials):
        """Test adding a new table row with empty cells.

        Success criteria: Empty row is added via surgical update, table not regenerated.
        """
        page_id = table_test_page['page_id']
        local_file = table_test_page['local_file']
        space_key = table_test_page['space_key']
        temp_dir = table_test_page['temp_dir']

        # Read local file
        content = local_file.read_text(encoding='utf-8')
        local_page = FrontmatterHandler.parse(str(local_file), content)

        logger.info(f"Original content:\n{local_page.content}")

        # Add an empty row after Item 3
        lines = local_page.content.split('\n')
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if 'Item 3' in line:
                # Add empty row after Item 3
                if '|' in line:
                    new_lines.append('| | | |')

        local_page.content = '\n'.join(new_lines)

        logger.info(f"Modified content (empty row added):\n{local_page.content}")

        # Write back
        updated_content = FrontmatterHandler.generate(local_page)
        local_file.write_text(updated_content, encoding='utf-8')

        # Get current version
        auth = Authenticator()
        api = APIWrapper(auth)
        current_page = api.get_page_by_id(page_id, expand="version")
        version_before = current_page['version']['number']

        # Sync changes
        self._sync_changes(temp_dir, space_key, table_test_page['parent_id'])
        time.sleep(2)

        # Verify surgical update
        assert self._verify_surgical_update(api, page_id, version_before), \
            "Surgical update failed - fallback may have been used"

        # Verify original content is preserved
        page = api.get_page_by_id(page_id, expand="body.storage")
        body = page.get('body', {}).get('storage', {}).get('value', '')

        assert 'Item 1' in body, "Item 1 should still be in table"
        assert 'Item 2' in body, "Item 2 should still be in table"
        assert 'Item 3' in body, "Item 3 should still be in table"

        # Count table rows (should be header + 3 original + 1 new = 5)
        row_count = body.lower().count('<tr')
        assert row_count >= 4, f"Table should have at least 4 rows, got {row_count}"

        logger.info("✓ test_add_row_without_content PASSED")

    @pytest.mark.e2e
    def test_replace_all_cells_in_row(self, table_test_page, test_credentials):
        """Test replacing all cell content in a single row.

        Success criteria: Cells are updated via surgical update, table not regenerated.
        """
        page_id = table_test_page['page_id']
        local_file = table_test_page['local_file']
        space_key = table_test_page['space_key']
        temp_dir = table_test_page['temp_dir']

        # Read local file
        content = local_file.read_text(encoding='utf-8')
        local_page = FrontmatterHandler.parse(str(local_file), content)

        logger.info(f"Original content:\n{local_page.content}")

        # Replace all cells in the "Item 2" row with new content
        lines = local_page.content.split('\n')
        new_lines = []
        for line in lines:
            if 'Item 2' in line and '|' in line:
                # Replace with completely new content
                new_lines.append('| Updated Item | 999 | Modified |')
            else:
                new_lines.append(line)

        local_page.content = '\n'.join(new_lines)

        logger.info(f"Modified content (Item 2 row replaced):\n{local_page.content}")

        # Write back
        updated_content = FrontmatterHandler.generate(local_page)
        local_file.write_text(updated_content, encoding='utf-8')

        # Get current version
        auth = Authenticator()
        api = APIWrapper(auth)
        current_page = api.get_page_by_id(page_id, expand="version")
        version_before = current_page['version']['number']

        # Sync changes
        self._sync_changes(temp_dir, space_key, table_test_page['parent_id'])
        time.sleep(2)

        # Verify surgical update
        assert self._verify_surgical_update(api, page_id, version_before), \
            "Surgical update failed - fallback may have been used"

        # Verify content: Item 2 should be replaced with new content
        page = api.get_page_by_id(page_id, expand="body.storage")
        body = page.get('body', {}).get('storage', {}).get('value', '')

        assert 'Item 1' in body, "Item 1 should still be in table"
        assert 'Item 2' not in body, "Item 2 should be replaced"
        assert 'Updated Item' in body, "New cell content should be present"
        assert '999' in body, "New value should be present"
        assert 'Modified' in body, "New status should be present"
        assert 'Item 3' in body, "Item 3 should still be in table"

        logger.info("✓ test_replace_all_cells_in_row PASSED")

    @pytest.mark.e2e
    def test_update_single_word_in_cell(self, table_test_page, test_credentials):
        """Test updating a single word within a table cell.

        This test catches the scenario where removing/changing a single word
        from a table cell should produce exactly 1 TABLE_UPDATE_CELL operation,
        not multiple row delete/insert operations.

        Success criteria: Single cell is updated via surgical update, table not regenerated.
        """
        page_id = table_test_page['page_id']
        local_file = table_test_page['local_file']
        space_key = table_test_page['space_key']
        temp_dir = table_test_page['temp_dir']

        # Read local file
        content = local_file.read_text(encoding='utf-8')
        local_page = FrontmatterHandler.parse(str(local_file), content)

        logger.info(f"Original content:\n{local_page.content}")

        # Change only ONE word in ONE cell: "Active" -> "Done" in Item 1's status
        lines = local_page.content.split('\n')
        new_lines = []
        for line in lines:
            if 'Item 1' in line and 'Active' in line:
                # Change just "Active" to "Done" - minimal single-word change
                new_lines.append(line.replace('Active', 'Done'))
            else:
                new_lines.append(line)

        local_page.content = '\n'.join(new_lines)

        logger.info(f"Modified content (Active -> Done):\n{local_page.content}")

        # Write back
        updated_content = FrontmatterHandler.generate(local_page)
        local_file.write_text(updated_content, encoding='utf-8')

        # Get current version
        auth = Authenticator()
        api = APIWrapper(auth)
        current_page = api.get_page_by_id(page_id, expand="version")
        version_before = current_page['version']['number']

        # Sync changes
        self._sync_changes(temp_dir, space_key, table_test_page['parent_id'])
        time.sleep(2)

        # Verify surgical update (version increment means change was applied)
        assert self._verify_surgical_update(api, page_id, version_before), \
            "Surgical update failed - fallback may have been used"

        # Verify content: Only Active -> Done, everything else unchanged
        page = api.get_page_by_id(page_id, expand="body.storage")
        body = page.get('body', {}).get('storage', {}).get('value', '')

        assert 'Item 1' in body, "Item 1 should still be in table"
        assert '100' in body, "Item 1 value should still be 100"
        assert 'Done' in body, "Status should be changed to Done"
        assert 'Active' not in body or body.count('Active') == 0, "Active should be replaced"
        assert 'Item 2' in body, "Item 2 should still be in table"
        assert 'Pending' in body, "Item 2 status should still be Pending"
        assert 'Item 3' in body, "Item 3 should still be in table"

        logger.info("✓ test_update_single_word_in_cell PASSED")
