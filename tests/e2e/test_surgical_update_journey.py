"""E2E test: Surgical Update Journey.

This test validates the complete surgical update journey:
1. Fetch page as snapshot (XHTML + markdown)
2. Apply surgical operations to XHTML
3. Verify macros/labels/local-ids preserved
4. Upload modified content
5. Verify changes in Confluence

Requirements:
- Test Confluence credentials in .env
- Test page in CONFSYNCTEST space

Test Page: Conf Sync Test Page (ID: 10158081)
"""

import pytest
import logging
import uuid
from datetime import datetime

from src.page_operations import (
    PageOperations,
    SurgicalEditor,
    SurgicalOperation,
    OperationType,
)
from src.confluence_client.auth import Authenticator
from src.confluence_client.api_wrapper import APIWrapper

from tests.helpers.confluence_test_setup import setup_test_page, teardown_test_page

logger = logging.getLogger(__name__)

# Test page configuration
TEST_PAGE_ID = "10158081"
TEST_SPACE_KEY = "CONFSYNCTEST"


class TestSurgicalUpdateJourney:
    """E2E tests for surgical update workflow."""

    @pytest.fixture(scope="class")
    def page_ops(self):
        """Create PageOperations instance."""
        return PageOperations()

    @pytest.fixture(scope="function")
    def surgical_test_page(self):
        """Create a test page for surgical update tests."""
        # Create page with known content structure
        xhtml = """
        <ac:structured-macro ac:name="toc" ac:schema-version="1">
            <ac:parameter ac:name="style">none</ac:parameter>
        </ac:structured-macro>
        <h1 local-id="h1-test">E2E Test Page</h1>
        <p local-id="p1-test">This is the original paragraph text.</p>
        <h2 local-id="h2-test">Section to Modify</h2>
        <p local-id="p2-test">This paragraph will be updated surgically.</p>
        <h3 local-id="h3-test">Subsection to Change Level</h3>
        <p local-id="p3-test">This paragraph may be deleted.</p>
        <table ac:local-id="table-test">
            <tbody>
                <tr><th>Col A</th><th>Col B</th></tr>
                <tr><td><p>A1</p></td><td><p>B1</p></td></tr>
                <tr><td><p>A2</p></td><td><p>B2</p></td></tr>
            </tbody>
        </table>
        <ac:structured-macro ac:name="children" ac:schema-version="2">
            <ac:parameter ac:name="allChildren">true</ac:parameter>
        </ac:structured-macro>
        """

        page_info = setup_test_page(
            title=f"E2E Surgical Test - {uuid.uuid4().hex[:8]}",
            content=xhtml
        )
        logger.info(f"Created surgical test page: {page_info['page_id']}")

        yield page_info

        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up surgical test page: {page_info['page_id']}")

    # ===== Basic Snapshot Tests =====

    def test_get_page_snapshot_returns_xhtml_and_markdown(self, page_ops, surgical_test_page):
        """get_page_snapshot should return both XHTML and markdown."""
        page_id = surgical_test_page['page_id']

        snapshot = page_ops.get_page_snapshot(page_id)

        assert snapshot.page_id == page_id
        assert snapshot.xhtml, "Should have XHTML content"
        assert snapshot.markdown, "Should have markdown content"
        assert snapshot.version > 0, "Should have version number"
        assert snapshot.title, "Should have title"

        # XHTML should contain macros
        assert 'ac:structured-macro' in snapshot.xhtml
        assert 'ac:name="toc"' in snapshot.xhtml

        # Markdown should be human-readable
        assert 'E2E Test Page' in snapshot.markdown

        logger.info(f"✓ Snapshot retrieved: {len(snapshot.xhtml)} chars XHTML, {len(snapshot.markdown)} chars markdown")

    def test_snapshot_preserves_local_ids_in_xhtml(self, page_ops, surgical_test_page):
        """Snapshot XHTML should preserve local-id attributes."""
        page_id = surgical_test_page['page_id']

        snapshot = page_ops.get_page_snapshot(page_id)

        # Check local-ids are preserved
        assert 'local-id="h1-test"' in snapshot.xhtml
        assert 'local-id="p1-test"' in snapshot.xhtml
        assert 'ac:local-id="table-test"' in snapshot.xhtml

        logger.info("✓ Local IDs preserved in snapshot XHTML")

    # ===== Surgical Update Tests =====

    def test_apply_update_text_operation(self, page_ops, surgical_test_page):
        """apply_operations should update text content."""
        page_id = surgical_test_page['page_id']

        # Get snapshot
        snapshot = page_ops.get_page_snapshot(page_id)
        original_version = snapshot.version

        # Create update operation
        unique_marker = f"UPDATED-{uuid.uuid4().hex[:8]}"
        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="This paragraph will be updated surgically",
                new_content=f"This paragraph was {unique_marker}"
            )
        ]

        # Apply operations
        result = page_ops.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,
            base_version=snapshot.version,
            operations=ops
        )

        assert result.success, f"Operation should succeed: {result.error}"
        assert result.new_version == original_version + 1

        # Verify by fetching again
        updated = page_ops.get_page_snapshot(page_id)
        assert unique_marker in updated.xhtml
        assert "This paragraph will be updated surgically" not in updated.xhtml

        logger.info(f"✓ Text update applied: v{original_version} → v{result.new_version}")

    def test_apply_delete_block_operation(self, page_ops, surgical_test_page):
        """apply_operations should delete block content."""
        page_id = surgical_test_page['page_id']

        snapshot = page_ops.get_page_snapshot(page_id)
        original_version = snapshot.version

        # Delete the paragraph
        ops = [
            SurgicalOperation(
                op_type=OperationType.DELETE_BLOCK,
                target_content="This paragraph may be deleted"
            )
        ]

        result = page_ops.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,
            base_version=snapshot.version,
            operations=ops
        )

        assert result.success, f"Operation should succeed: {result.error}"

        # Verify deletion
        updated = page_ops.get_page_snapshot(page_id)
        assert "This paragraph may be deleted" not in updated.xhtml

        logger.info(f"✓ Block deleted: v{original_version} → v{result.new_version}")

    def test_apply_change_heading_level(self, page_ops, surgical_test_page):
        """apply_operations should change heading level."""
        page_id = surgical_test_page['page_id']

        snapshot = page_ops.get_page_snapshot(page_id)

        # Change h3 to h2
        ops = [
            SurgicalOperation(
                op_type=OperationType.CHANGE_HEADING_LEVEL,
                target_content="Subsection to Change Level",
                new_content="Subsection Changed to H2",
                old_level=3,
                new_level=2
            )
        ]

        result = page_ops.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,
            base_version=snapshot.version,
            operations=ops
        )

        assert result.success, f"Operation should succeed: {result.error}"

        # Verify heading change
        updated = page_ops.get_page_snapshot(page_id)
        assert '<h2' in updated.xhtml and 'Subsection Changed to H2' in updated.xhtml

        logger.info(f"✓ Heading level changed: h3 → h2")

    def test_apply_table_insert_row(self, page_ops, surgical_test_page):
        """apply_operations should insert table row."""
        page_id = surgical_test_page['page_id']

        snapshot = page_ops.get_page_snapshot(page_id)

        # Insert row
        unique_marker = f"NEW-{uuid.uuid4().hex[:4]}"
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="",
                new_content=f"['{unique_marker}', 'NEW-B']",
                row_index=2
            )
        ]

        result = page_ops.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,
            base_version=snapshot.version,
            operations=ops
        )

        assert result.success, f"Operation should succeed: {result.error}"

        # Verify row added
        updated = page_ops.get_page_snapshot(page_id)
        assert unique_marker in updated.xhtml

        logger.info(f"✓ Table row inserted with marker: {unique_marker}")

    # ===== Preservation Tests =====

    def test_surgical_update_preserves_macros(self, page_ops, surgical_test_page):
        """Surgical updates should preserve Confluence macros."""
        page_id = surgical_test_page['page_id']

        snapshot = page_ops.get_page_snapshot(page_id)
        editor = SurgicalEditor()

        # Count macros before
        macros_before = editor.count_macros(snapshot.xhtml)
        assert macros_before >= 2, "Should have at least 2 macros (toc + children)"

        # Apply operation
        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="original paragraph text",
                new_content="modified paragraph text"
            )
        ]

        result = page_ops.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,
            base_version=snapshot.version,
            operations=ops
        )

        assert result.success

        # Count macros after
        updated = page_ops.get_page_snapshot(page_id)
        macros_after = editor.count_macros(updated.xhtml)

        assert macros_after == macros_before, \
            f"Macro count should be preserved: {macros_before} → {macros_after}"

        logger.info(f"✓ Macros preserved: {macros_before} macros")

    def test_surgical_update_preserves_local_ids(self, page_ops, surgical_test_page):
        """Surgical updates should preserve local-id attributes."""
        page_id = surgical_test_page['page_id']

        snapshot = page_ops.get_page_snapshot(page_id)

        # Collect local-ids before
        import re
        local_ids_before = set(re.findall(r'local-id="([^"]+)"', snapshot.xhtml))

        # Apply operation
        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="original paragraph text",
                new_content="updated text"
            )
        ]

        result = page_ops.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,
            base_version=snapshot.version,
            operations=ops
        )

        assert result.success

        # Check local-ids after
        updated = page_ops.get_page_snapshot(page_id)
        local_ids_after = set(re.findall(r'local-id="([^"]+)"', updated.xhtml))

        # IDs from non-deleted elements should be preserved
        assert 'h1-test' in local_ids_after
        assert 'h2-test' in local_ids_after

        logger.info(f"✓ Local IDs preserved: {len(local_ids_after)} IDs")

    # ===== Version Conflict Tests =====

    def test_version_conflict_detection(self, page_ops, surgical_test_page):
        """apply_operations should detect version conflicts."""
        page_id = surgical_test_page['page_id']

        snapshot = page_ops.get_page_snapshot(page_id)

        # First update (should succeed)
        ops1 = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="original paragraph text",
                new_content="first update"
            )
        ]

        result1 = page_ops.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,
            base_version=snapshot.version,
            operations=ops1
        )
        assert result1.success

        # Second update with OLD version (should detect conflict)
        ops2 = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="first update",
                new_content="second update"
            )
        ]

        result2 = page_ops.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,  # Using old XHTML
            base_version=snapshot.version,  # Using old version
            operations=ops2
        )

        # Should fail due to version conflict
        assert not result2.success
        assert "conflict" in result2.error.lower() or "version" in result2.error.lower()

        logger.info("✓ Version conflict detected as expected")

    # ===== Multiple Operations Test =====

    def test_multiple_operations_in_single_update(self, page_ops, surgical_test_page):
        """Multiple operations should be applied in single update."""
        page_id = surgical_test_page['page_id']

        snapshot = page_ops.get_page_snapshot(page_id)
        original_version = snapshot.version

        unique_marker = uuid.uuid4().hex[:8]

        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="original paragraph text",
                new_content=f"updated-{unique_marker}"
            ),
            SurgicalOperation(
                op_type=OperationType.CHANGE_HEADING_LEVEL,
                target_content="Section to Modify",
                new_content="Section Modified",
                old_level=2,
                new_level=3
            ),
        ]

        result = page_ops.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,
            base_version=snapshot.version,
            operations=ops
        )

        assert result.success, f"Operations should succeed: {result.error}"
        assert result.operations_applied == 2

        # Verify both changes
        updated = page_ops.get_page_snapshot(page_id)
        assert f"updated-{unique_marker}" in updated.xhtml
        assert '<h3' in updated.xhtml and 'Section Modified' in updated.xhtml

        logger.info(f"✓ Multiple operations applied: {result.operations_applied} ops, v{original_version} → v{result.new_version}")

    # ===== Create Page Test =====

    def test_create_page_from_markdown(self, page_ops):
        """create_page should create new page from markdown."""
        unique_title = f"E2E Create Test - {uuid.uuid4().hex[:8]}"
        markdown_content = f"""# {unique_title}

This is a test page created from markdown.

## Section 1

Some content here.

- List item 1
- List item 2
"""

        result = page_ops.create_page(
            space_key=TEST_SPACE_KEY,
            title=unique_title,
            markdown_content=markdown_content,
            parent_id=None
        )

        try:
            assert result.success, f"Create should succeed: {result.error}"
            assert result.page_id, "Should return page_id"

            # Verify page exists
            snapshot = page_ops.get_page_snapshot(result.page_id)
            assert snapshot.title == unique_title
            assert "Section 1" in snapshot.markdown

            logger.info(f"✓ Page created: {result.page_id}")

        finally:
            # Cleanup
            if result.page_id:
                teardown_test_page(result.page_id)

    # ===== Complete Journey Test =====

    def test_complete_surgical_journey(self, page_ops, surgical_test_page):
        """Test complete surgical update journey end-to-end."""
        logger.info("=== Starting Complete Surgical Journey ===")

        page_id = surgical_test_page['page_id']

        # Step 1: Get snapshot
        logger.info("1. Getting page snapshot...")
        snapshot = page_ops.get_page_snapshot(page_id)
        assert snapshot.xhtml and snapshot.markdown
        logger.info(f"   ✓ Snapshot: v{snapshot.version}, {len(snapshot.xhtml)} chars XHTML")

        # Step 2: Count initial macros/local-ids
        editor = SurgicalEditor()
        macros_before = editor.count_macros(snapshot.xhtml)
        logger.info(f"   ✓ Initial macros: {macros_before}")

        # Step 3: Prepare operations
        unique_marker = f"JOURNEY-{datetime.now().strftime('%H%M%S')}"
        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="original paragraph text",
                new_content=f"Text updated at {unique_marker}"
            ),
        ]
        logger.info(f"2. Prepared {len(ops)} surgical operations")

        # Step 4: Apply operations
        logger.info("3. Applying surgical operations...")
        result = page_ops.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,
            base_version=snapshot.version,
            operations=ops
        )
        assert result.success, f"Operations failed: {result.error}"
        logger.info(f"   ✓ Applied: v{snapshot.version} → v{result.new_version}")

        # Step 5: Verify changes
        logger.info("4. Verifying changes...")
        updated = page_ops.get_page_snapshot(page_id)

        # Content updated
        assert unique_marker in updated.xhtml
        logger.info("   ✓ Content updated correctly")

        # Macros preserved
        macros_after = editor.count_macros(updated.xhtml)
        assert macros_after == macros_before
        logger.info(f"   ✓ Macros preserved: {macros_after}")

        # Version incremented
        assert updated.version == result.new_version
        logger.info(f"   ✓ Version correct: {updated.version}")

        logger.info("=== Complete Surgical Journey PASSED ===")
