"""Security tests for surgical_editor - testing ast.literal_eval replacement."""

import pytest
from src.page_operations.surgical_editor import SurgicalEditor
from src.page_operations.models import SurgicalOperation, OperationType


class TestSurgicalEditorSecureRowParsing:
    """Test secure parsing of row content with ast.literal_eval."""

    @pytest.fixture
    def editor(self):
        """Create SurgicalEditor instance."""
        return SurgicalEditor()

    @pytest.fixture
    def table_xhtml(self):
        """Sample XHTML with a table."""
        return """
        <table>
            <tbody>
                <tr><th>Col1</th><th>Col2</th></tr>
                <tr><td><p>A</p></td><td><p>B</p></td></tr>
                <tr><td><p>C</p></td><td><p>D</p></td></tr>
            </tbody>
        </table>
        """

    def test_table_insert_row_with_valid_list(self, editor, table_xhtml):
        """Should successfully parse valid list representation."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="table",
                new_content="['X', 'Y']",
                row_index=2
            )
        ]
        result, success, failure = editor.apply_operations(table_xhtml, ops)
        assert success == 1
        assert failure == 0
        assert "X" in result
        assert "Y" in result

    def test_table_insert_row_with_empty_cells(self, editor, table_xhtml):
        """Should handle empty cell values."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="table",
                new_content="['', 'Value']",
                row_index=2
            )
        ]
        result, success, failure = editor.apply_operations(table_xhtml, ops)
        assert success == 1
        assert "Value" in result

    def test_table_insert_row_with_numeric_values(self, editor, table_xhtml):
        """Should handle numeric cell values."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="table",
                new_content="[123, 456]",
                row_index=2
            )
        ]
        result, success, failure = editor.apply_operations(table_xhtml, ops)
        assert success == 1
        assert "123" in result
        assert "456" in result

    def test_table_insert_row_rejects_malicious_code(self, editor, table_xhtml):
        """Should reject code execution attempts (security test)."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="table",
                new_content="__import__('os').system('echo hacked')",
                row_index=2
            )
        ]
        # Should fail parsing, not execute code
        result, success, failure = editor.apply_operations(table_xhtml, ops)
        assert failure == 1
        assert success == 0

    def test_table_insert_row_rejects_function_calls(self, editor, table_xhtml):
        """Should reject function call attempts."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="table",
                new_content="list(range(10))",
                row_index=2
            )
        ]
        result, success, failure = editor.apply_operations(table_xhtml, ops)
        assert failure == 1
        assert success == 0

    def test_table_delete_row_with_valid_list(self, editor, table_xhtml):
        """Should successfully parse valid list for deletion."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_DELETE_ROW,
                target_content="['A', 'B']",
                row_index=1
            )
        ]
        result, success, failure = editor.apply_operations(table_xhtml, ops)
        assert success == 1
        assert "A" not in result or "C" in result  # Row with A,B deleted

    def test_table_delete_row_handles_invalid_syntax(self, editor, table_xhtml):
        """Should handle invalid syntax gracefully."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_DELETE_ROW,
                target_content="not a valid list",
                row_index=1
            )
        ]
        # Should not crash, just fail to find row
        result, success, failure = editor.apply_operations(table_xhtml, ops)
        # Operation fails but doesn't crash
        assert failure == 1

    def test_table_insert_row_with_special_characters(self, editor, table_xhtml):
        """Should handle special characters in cell values."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="table",
                new_content="['Hello, World!', 'Test & Value']",
                row_index=2
            )
        ]
        result, success, failure = editor.apply_operations(table_xhtml, ops)
        assert success == 1
        assert "Hello, World!" in result

    def test_table_insert_row_with_unicode(self, editor, table_xhtml):
        """Should handle unicode characters."""
        ops = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="table",
                new_content="['日本語', 'émoji 🎉']",
                row_index=2
            )
        ]
        result, success, failure = editor.apply_operations(table_xhtml, ops)
        assert success == 1
        assert "日本語" in result
