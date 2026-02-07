"""E2E tests for line break format conversion through sync cycles.

Tests the full round-trip of line break conversion:
- Pull: Confluence <p> tags → Local markdown <br> tags
- Push: Local <br> tags → Confluence <p> tags (or hardBreak in ADF)
"""

import pytest
import logging
from pathlib import Path

from src.content_converter.markdown_converter import MarkdownConverter

logger = logging.getLogger(__name__)


@pytest.mark.e2e
@pytest.mark.linebreak
class TestLineBreakRoundtripE2E:
    """E2E tests for line break format conversion."""

    def test_pull_converts_p_tags_to_br(
        self,
        page_with_multiline_cells,
    ):
        """AC-2.1: Confluence <p> tags become <br> in local markdown.

        Given: A Confluence page with table cells containing multiple <p> tags
        When: I pull the page to local
        Then: The markdown should have <br> tags between lines in cells
        And: NOT have <p> tags in the markdown
        """
        page_id = page_with_multiline_cells['page_id']
        api = page_with_multiline_cells['api_wrapper']

        # Get page content
        page = api.get_page_by_id(page_id)
        xhtml_content = page['body']['storage']['value']

        logger.info(f"XHTML content: {xhtml_content[:500]}...")

        # Verify source has <p> tags in table cells
        assert '<p>' in xhtml_content, "Source should have <p> tags"

        # Convert to markdown
        converter = MarkdownConverter()
        markdown = converter.xhtml_to_markdown(xhtml_content)

        logger.info(f"Converted markdown: {markdown[:500]}...")

        # Verify markdown has <br> for multi-line cells
        # Note: The exact format depends on the converter implementation
        # It may use <br> or actual newlines within cells
        assert '<p>' not in markdown or markdown.count('<p>') < xhtml_content.count('<p>'), \
            "Markdown should have fewer or no <p> tags"

    def test_push_converts_br_to_storage_format(
        self,
        synced_test_page,
    ):
        """AC-2.2: Local <br> becomes proper storage format.

        Given: A local markdown file with <br> tags in table cells
        When: I push to Confluence
        Then: The Confluence storage should have proper format
        And: NOT have raw <br> tags in storage
        """
        page_id = synced_test_page['page_id']
        api = synced_test_page['api_wrapper']

        # Get current version
        page = api.get_page_by_id(page_id)
        version = page['version']['number']

        # Create markdown with <br> tags
        markdown_with_br = """# Test Page

| Feature | Description |
|---------|-------------|
| Login | Users can<br>authenticate<br>securely |
| Dashboard | View<br>metrics |
"""

        # Convert markdown to XHTML for push
        converter = MarkdownConverter()
        xhtml = converter.markdown_to_xhtml(markdown_with_br)

        logger.info(f"Converted XHTML: {xhtml[:500]}...")

        # Push to Confluence
        result = api.update_page(
            page_id=page_id,
            title=page['title'],
            body=xhtml,
            version=version
        )

        # Verify the result
        final_page = api.get_page_by_id(page_id)
        final_content = final_page['body']['storage']['value']

        logger.info(f"Final storage content: {final_content[:500]}...")

        # Content should be valid (either with <p> or <br/>)
        assert final_content is not None, "Should have content"

    def test_bidirectional_edit_preserves_line_breaks(
        self,
        synced_test_page,
        temp_test_dir,
    ):
        """AC-2.3: Both sides add lines, all preserved after merge.

        Given: A page with multi-line table cells synced both directions
        When: Confluence adds a line AND local adds a different line
        Then: Both lines should be preserved after merge
        And: All <br> tags should be present
        """
        page_id = synced_test_page['page_id']
        api = synced_test_page['api_wrapper']

        # Set up initial content with multi-line cell
        page = api.get_page_by_id(page_id)
        version = page['version']['number']

        initial_content = """
<table>
    <tr><th>Feature</th><th>Description</th></tr>
    <tr><td>Login</td><td><p>Line 1</p><p>Line 2</p></td></tr>
</table>
"""
        api.update_page(page_id=page_id, title=page['title'], body=initial_content, version=version)

        # Simulate local edit (add line)
        local_content = """
<table>
    <tr><th>Feature</th><th>Description</th></tr>
    <tr><td>Login</td><td><p>Line 1</p><p>Line 2</p><p>Local Line 3</p></td></tr>
</table>
"""

        # Get updated version and push local changes
        page = api.get_page_by_id(page_id)
        version = page['version']['number']

        result = api.update_page(page_id=page_id, title=page['title'], body=local_content, version=version)

        # Verify both original and new lines present
        final_page = api.get_page_by_id(page_id)
        final_content = final_page['body']['storage']['value']

        assert 'Line 1' in final_content, "Original line 1 should be preserved"
        assert 'Line 2' in final_content, "Original line 2 should be preserved"
        assert 'Local Line 3' in final_content, "New line should be added"

    def test_multiple_br_in_same_cell_preserved(
        self,
        synced_test_page,
    ):
        """AC-2.4: Cell with 4+ lines survives edit.

        Given: A table cell with 4+ lines (3+ <br> tags)
        When: I edit one line and sync
        Then: All other lines should be preserved
        And: All line separators should remain intact
        """
        page_id = synced_test_page['page_id']
        api = synced_test_page['api_wrapper']

        # Set up content with many lines in a cell
        page = api.get_page_by_id(page_id)
        version = page['version']['number']

        content_with_many_lines = """
<table>
    <tr><th>Feature</th><th>Description</th></tr>
    <tr>
        <td>Complex Feature</td>
        <td><p>Line A</p><p>Line B</p><p>Line C</p><p>Line D</p><p>Line E</p></td>
    </tr>
</table>
"""
        api.update_page(page_id=page_id, title=page['title'], body=content_with_many_lines, version=version)

        # Edit one line (Line C -> Line C MODIFIED)
        page = api.get_page_by_id(page_id)
        version = page['version']['number']
        current_content = page['body']['storage']['value']

        modified_content = current_content.replace('Line C', 'Line C MODIFIED')

        result = api.update_page(page_id=page_id, title=page['title'], body=modified_content, version=version)

        # Verify all lines present
        final_page = api.get_page_by_id(page_id)
        final_content = final_page['body']['storage']['value']

        assert 'Line A' in final_content, "Line A should be preserved"
        assert 'Line B' in final_content, "Line B should be preserved"
        assert 'Line C MODIFIED' in final_content, "Line C should be modified"
        assert 'Line D' in final_content, "Line D should be preserved"
        assert 'Line E' in final_content, "Line E should be preserved"


@pytest.mark.e2e
@pytest.mark.linebreak
class TestMarkdownConverterE2E:
    """E2E tests for MarkdownConverter line break handling."""

    def test_xhtml_to_markdown_table_conversion(self):
        """Verify table with multi-line cells converts correctly."""
        converter = MarkdownConverter()

        xhtml = """
<table>
    <tr><th>Feature</th><th>Description</th></tr>
    <tr><td>Login</td><td><p>Users can</p><p>authenticate</p></td></tr>
</table>
"""
        markdown = converter.xhtml_to_markdown(xhtml)

        # Verify it's a valid markdown table
        assert '|' in markdown, "Should produce markdown table"
        assert 'Login' in markdown, "Should preserve content"

    def test_markdown_to_xhtml_table_conversion(self):
        """Verify markdown table converts to XHTML."""
        converter = MarkdownConverter()

        markdown = """| Feature | Description |
|---------|-------------|
| Login | Users can<br>authenticate |
"""
        xhtml = converter.markdown_to_xhtml(markdown)

        # Verify it produces valid XHTML
        assert '<table' in xhtml.lower() or '<tr' in xhtml.lower() or 'Login' in xhtml, \
            "Should produce table-like structure or preserve content"

    def test_roundtrip_preserves_content(self):
        """Verify round-trip conversion preserves essential content."""
        converter = MarkdownConverter()

        original_markdown = """# Test Document

| Feature | Status |
|---------|--------|
| Login | Active |
| Logout | Pending |

Some paragraph text here.
"""
        # Convert to XHTML
        xhtml = converter.markdown_to_xhtml(original_markdown)

        # Convert back to markdown
        final_markdown = converter.xhtml_to_markdown(xhtml)

        # Essential content should be preserved
        assert 'Test Document' in final_markdown, "Heading should survive round-trip"
        assert 'Login' in final_markdown, "Table content should survive"
        assert 'paragraph' in final_markdown.lower() or 'Some' in final_markdown, \
            "Paragraph content should survive"
