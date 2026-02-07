"""Unit tests for page_operations.surgical_editor module."""

import pytest
from bs4 import BeautifulSoup

from src.page_operations.surgical_editor import SurgicalEditor
from src.page_operations.models import SurgicalOperation, OperationType


class TestSurgicalEditor:
    """Test cases for SurgicalEditor class."""

    @pytest.fixture
    def editor(self):
        """Create SurgicalEditor instance."""
        return SurgicalEditor()

    @pytest.fixture
    def sample_xhtml(self):
        """Sample XHTML with various elements."""
        return """
        <h1 local-id="h1">Header One</h1>
        <p local-id="p1">First paragraph with some text.</p>
        <h2 local-id="h2">Sub Header</h2>
        <p local-id="p2">Second paragraph to update.</p>
        <table ac:local-id="t1">
            <tbody>
                <tr><th>Col1</th><th>Col2</th></tr>
                <tr><td><p>A</p></td><td><p>B</p></td></tr>
                <tr><td><p>C</p></td><td><p>D</p></td></tr>
            </tbody>
        </table>
        <ac:structured-macro ac:name="toc"><ac:parameter ac:name="style">none</ac:parameter></ac:structured-macro>
        <h3 local-id="h3">Section to Delete</h3>
        <p local-id="p3">This paragraph should be deleted.</p>
        """

    # ===== UPDATE_TEXT Tests =====

    def test_update_text_replaces_content(self, editor, sample_xhtml):
        """update_text should replace text in matching element."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Second paragraph to update",
                new_content="Updated second paragraph"
            )
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        assert "Updated second paragraph" in result
        assert "Second paragraph to update" not in result

    def test_update_text_preserves_element_attributes(self, editor, sample_xhtml):
        """update_text should preserve element attributes like local-id."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="First paragraph",
                new_content="Modified first paragraph"
            )
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        assert 'local-id="p1"' in result
        assert "Modified first paragraph" in result

    def test_update_text_skips_macros(self, editor):
        """update_text should not modify macro content."""
        # Test that macro content is not modified even when it contains matching text
        xhtml = '<ac:structured-macro ac:name="info">Some info text</ac:structured-macro><p>Regular paragraph text</p>'

        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Regular paragraph text",
                new_content="Changed paragraph"
            )
        ]

        result, _, _ = editor.apply_operations(xhtml, ops)

        # Macro content should be unchanged
        assert 'ac:name="info"' in result
        assert 'Some info text' in result  # Macro content preserved
        # Paragraph should be updated
        soup = BeautifulSoup(result, 'lxml')
        p = soup.find('p')
        assert "Changed paragraph" in p.get_text()

    def test_update_text_not_found_logs_warning(self, editor, caplog):
        """update_text should log warning when target not found."""
        xhtml = "<p>Some content</p>"

        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Nonexistent text",
                new_content="New text"
            )
        ]

        result, _, _ = editor.apply_operations(xhtml, ops)

        # Content unchanged
        assert "Some content" in result
        assert "Target text not found" in caplog.text

    # ===== DELETE_BLOCK Tests =====

    def test_delete_block_removes_paragraph(self, editor, sample_xhtml):
        """delete_block should remove paragraph with matching content."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.DELETE_BLOCK,
                target_content="This paragraph should be deleted"
            )
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        assert "This paragraph should be deleted" not in result

    def test_delete_block_removes_heading(self, editor, sample_xhtml):
        """delete_block should remove heading with matching content."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.DELETE_BLOCK,
                target_content="Section to Delete"
            )
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        assert "Section to Delete" not in result

    def test_delete_block_only_deletes_leaf_elements(self, editor):
        """delete_block should only delete leaf elements, not containers."""
        xhtml = """
        <div class="container">
            <p>Paragraph inside div</p>
            <p>Another paragraph</p>
        </div>
        """

        ops = [
            SurgicalOperation(
                op_type=OperationType.DELETE_BLOCK,
                target_content="Paragraph inside div"
            )
        ]

        result, _, _ = editor.apply_operations(xhtml, ops)

        # Paragraph removed, div container remains
        assert "Paragraph inside div" not in result
        assert "Another paragraph" in result

    def test_delete_block_preserves_macros(self, editor, sample_xhtml):
        """delete_block should preserve macros."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.DELETE_BLOCK,
                target_content="This paragraph should be deleted"
            )
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        assert 'ac:structured-macro' in result
        assert 'ac:name="toc"' in result

    # ===== CHANGE_HEADING_LEVEL Tests =====

    def test_change_heading_level_h2_to_h3(self, editor, sample_xhtml):
        """change_heading_level should change h2 to h3."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.CHANGE_HEADING_LEVEL,
                target_content="Sub Header",
                new_content="Sub Header",
                old_level=2,
                new_level=3
            )
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        soup = BeautifulSoup(result, 'lxml')
        h3s = soup.find_all('h3')
        h3_texts = [h.get_text(strip=True) for h in h3s]
        assert "Sub Header" in h3_texts

    def test_change_heading_level_updates_text(self, editor, sample_xhtml):
        """change_heading_level should update heading text if changed."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.CHANGE_HEADING_LEVEL,
                target_content="Sub Header",
                new_content="New Sub Header Title",
                old_level=2,
                new_level=2
            )
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        assert "New Sub Header Title" in result
        # Original text should be replaced
        soup = BeautifulSoup(result, 'lxml')
        h2s = soup.find_all('h2')
        h2_texts = [h.get_text(strip=True) for h in h2s]
        assert "New Sub Header Title" in h2_texts

    def test_change_heading_level_preserves_local_id(self, editor, sample_xhtml):
        """change_heading_level should preserve element attributes."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.CHANGE_HEADING_LEVEL,
                target_content="Sub Header",
                new_content="Sub Header",
                old_level=2,
                new_level=3
            )
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        assert 'local-id="h2"' in result

    # ===== TABLE_INSERT_ROW Tests =====

    def test_table_insert_row_adds_row(self, editor, sample_xhtml):
        """table_insert_row should add a new row to table."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="",
                new_content="['X', 'Y']",
                row_index=2
            )
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        soup = BeautifulSoup(result, 'lxml')
        rows = soup.find('table').find_all('tr')
        row_texts = [[td.get_text(strip=True) for td in row.find_all(['td', 'th'])] for row in rows]

        # Should have new row with X, Y
        assert any('X' in row and 'Y' in row for row in row_texts)

    def test_table_insert_row_at_end(self, editor, sample_xhtml):
        """table_insert_row should append row if index exceeds current rows."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="",
                new_content="['End', 'Row']",
                row_index=100  # Beyond current rows
            )
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        soup = BeautifulSoup(result, 'lxml')
        rows = soup.find('table').find_all('tr')
        last_row = [td.get_text(strip=True) for td in rows[-1].find_all(['td', 'th'])]

        assert 'End' in last_row
        assert 'Row' in last_row

    # ===== TABLE_DELETE_ROW Tests =====

    def test_table_delete_row_removes_row(self, editor, sample_xhtml):
        """table_delete_row should remove row with matching content."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_DELETE_ROW,
                target_content="['A', 'B']",
                row_index=1
            )
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        soup = BeautifulSoup(result, 'lxml')
        table_text = soup.find('table').get_text()

        # A, B should be removed
        # Note: need to check row doesn't exist, not just text
        rows = soup.find('table').find_all('tr')
        row_texts = [[td.get_text(strip=True) for td in row.find_all(['td', 'th'])] for row in rows]
        assert ['A', 'B'] not in row_texts

    # ===== Macro Preservation Tests =====

    def test_count_macros_finds_ac_elements(self, editor, sample_xhtml):
        """count_macros should count all ac: namespace elements."""
        count = editor.count_macros(sample_xhtml)

        # structured-macro + parameter = 2
        assert count >= 2

    def test_operations_preserve_macro_count(self, editor, sample_xhtml):
        """All operations should preserve macro count."""
        macros_before = editor.count_macros(sample_xhtml)

        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="First paragraph",
                new_content="Modified"
            ),
            SurgicalOperation(
                op_type=OperationType.DELETE_BLOCK,
                target_content="This paragraph should be deleted"
            ),
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)
        macros_after = editor.count_macros(result)

        assert macros_after == macros_before

    # ===== Multiple Operations Tests =====

    def test_multiple_operations_applied_in_order(self, editor, sample_xhtml):
        """Multiple operations should be applied in order."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="First paragraph",
                new_content="Updated first"
            ),
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Second paragraph",
                new_content="Updated second"
            ),
        ]

        result, _, _ = editor.apply_operations(sample_xhtml, ops)

        assert "Updated first" in result
        assert "Updated second" in result

    def test_empty_operations_returns_unchanged(self, editor, sample_xhtml):
        """Empty operations list should return unchanged content."""
        result, _, _ = editor.apply_operations(sample_xhtml, [])

        # Should contain original content
        assert "Header One" in result
        assert "First paragraph" in result

    def test_update_text_with_inline_formatting(self, editor):
        """update_text should find text in elements with inline formatting like <strong>."""
        # This tests the case where <strong>Text</strong>: more text
        # should be searchable as "Text: more text" (no extra space before colon)
        xhtml = '<li><strong>Bold Label</strong>: Description with details</li>'

        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Bold Label: Description with details",
                new_content="Bold Label: MODIFIED description"
            )
        ]

        result, success, failure = editor.apply_operations(xhtml, ops)

        assert success == 1
        assert failure == 0
        assert "MODIFIED description" in result

    def test_update_text_selects_most_specific_element(self, editor):
        """update_text should modify <li> not parent <div> when both contain target text."""
        # This tests a critical bug where modifying a parent <div> destroyed
        # the child <li> structure
        xhtml = '''<div class="content">
<ol>
<li>Target text to modify here</li>
<li>Other item</li>
</ol>
</div>'''

        ops = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Target text to modify here",
                new_content="MODIFIED target text"
            )
        ]

        result, success, failure = editor.apply_operations(xhtml, ops)

        assert success == 1
        assert failure == 0
        # Verify the <li> structure is preserved
        soup = BeautifulSoup(result, 'lxml')
        lis = soup.find_all('li')
        assert len(lis) == 2  # Both list items should still exist
        assert "MODIFIED target text" in lis[0].get_text()
        assert "Other item" in lis[1].get_text()
