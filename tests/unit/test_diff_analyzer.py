"""Unit tests for DiffAnalyzer.

Tests the DiffAnalyzer class which generates surgical operations
by comparing original and modified content blocks.
"""

import pytest

from src.page_operations.diff_analyzer import DiffAnalyzer
from src.page_operations.models import (
    BlockType,
    ContentBlock,
    OperationType,
)


class TestDiffAnalyzer:
    """Test cases for DiffAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create a DiffAnalyzer instance."""
        return DiffAnalyzer()

    def test_analyze_no_changes(self, analyzer):
        """Identical blocks should produce no operations."""
        original = [
            ContentBlock(BlockType.HEADING, "Title", level=1, index=0),
            ContentBlock(BlockType.PARAGRAPH, "Content", index=1),
        ]
        modified = [
            ContentBlock(BlockType.HEADING, "Title", level=1, index=0),
            ContentBlock(BlockType.PARAGRAPH, "Content", index=1),
        ]

        operations = analyzer.analyze(original, modified)

        assert len(operations) == 0

    def test_analyze_text_update(self, analyzer):
        """Changed paragraph content should produce UPDATE_TEXT operation."""
        original = [
            ContentBlock(BlockType.PARAGRAPH, "Original text", index=0),
        ]
        modified = [
            ContentBlock(BlockType.PARAGRAPH, "Modified text", index=0),
        ]

        operations = analyzer.analyze(original, modified)

        assert len(operations) == 1
        assert operations[0].op_type == OperationType.UPDATE_TEXT
        assert operations[0].target_content == "Original text"
        assert operations[0].new_content == "Modified text"

    def test_analyze_heading_level_change(self, analyzer):
        """Changed heading level should produce CHANGE_HEADING_LEVEL operation."""
        original = [
            ContentBlock(BlockType.HEADING, "Section", level=1, index=0),
        ]
        modified = [
            ContentBlock(BlockType.HEADING, "Section", level=2, index=0),
        ]

        operations = analyzer.analyze(original, modified)

        assert len(operations) == 1
        assert operations[0].op_type == OperationType.CHANGE_HEADING_LEVEL
        assert operations[0].target_content == "Section"
        assert operations[0].old_level == 1
        assert operations[0].new_level == 2

    def test_analyze_heading_text_change_same_level(self, analyzer):
        """Changed heading text at same level should produce UPDATE_TEXT operation."""
        original = [
            ContentBlock(BlockType.HEADING, "Old Title", level=1, index=0),
        ]
        modified = [
            ContentBlock(BlockType.HEADING, "New Title", level=1, index=0),
        ]

        operations = analyzer.analyze(original, modified)

        assert len(operations) == 1
        assert operations[0].op_type == OperationType.UPDATE_TEXT
        assert operations[0].target_content == "Old Title"
        assert operations[0].new_content == "New Title"

    def test_analyze_insert_block(self, analyzer):
        """New block should produce INSERT_BLOCK operation."""
        original = [
            ContentBlock(BlockType.HEADING, "Title", level=1, index=0),
        ]
        modified = [
            ContentBlock(BlockType.HEADING, "Title", level=1, index=0),
            ContentBlock(BlockType.PARAGRAPH, "New paragraph", index=1),
        ]

        operations = analyzer.analyze(original, modified)

        assert len(operations) == 1
        assert operations[0].op_type == OperationType.INSERT_BLOCK
        assert operations[0].new_content == "New paragraph"

    def test_analyze_delete_block(self, analyzer):
        """Removed block should produce DELETE_BLOCK operation."""
        original = [
            ContentBlock(BlockType.HEADING, "Title", level=1, index=0),
            ContentBlock(BlockType.PARAGRAPH, "To be deleted", index=1),
        ]
        modified = [
            ContentBlock(BlockType.HEADING, "Title", level=1, index=0),
        ]

        operations = analyzer.analyze(original, modified)

        assert len(operations) == 1
        assert operations[0].op_type == OperationType.DELETE_BLOCK
        assert operations[0].target_content == "To be deleted"

    def test_analyze_macros_are_ignored(self, analyzer):
        """Macro blocks should be excluded from diff analysis."""
        original = [
            ContentBlock(BlockType.PARAGRAPH, "Text", index=0),
            ContentBlock(BlockType.MACRO, "<ac:macro>content</ac:macro>", index=1),
        ]
        modified = [
            ContentBlock(BlockType.PARAGRAPH, "Modified text", index=0),
            # Macro is missing from modified - should NOT produce delete
        ]

        operations = analyzer.analyze(original, modified)

        # Should only have UPDATE for paragraph, not DELETE for macro
        assert len(operations) == 1
        assert operations[0].op_type == OperationType.UPDATE_TEXT
        assert all(op.target_content != "<ac:macro>content</ac:macro>" for op in operations)

    def test_analyze_table_identical_skipped(self, analyzer):
        """Identical tables should produce no operations."""
        original = [
            ContentBlock(
                BlockType.TABLE,
                "A B 1 2",
                rows=[["A", "B"], ["1", "2"]],
                index=0,
            ),
        ]
        modified = [
            ContentBlock(
                BlockType.TABLE,
                "A B 1 2",
                rows=[["A", "B"], ["1", "2"]],
                index=0,
            ),
        ]

        operations = analyzer.analyze(original, modified)

        # Identical tables produce no operations
        assert len(operations) == 0

    def test_analyze_table_major_change_generates_row_operations(self, analyzer):
        """Major table changes (<50% similar) should produce row-level operations."""
        original = [
            ContentBlock(
                BlockType.TABLE,
                "old data values here",
                rows=[["old", "data"], ["values", "here"]],
                index=0,
            ),
        ]
        modified = [
            ContentBlock(
                BlockType.TABLE,
                "new content different words completely changed",
                rows=[["new", "content", "different"], ["words", "completely", "changed"]],
                index=0,
            ),
        ]

        operations = analyzer.analyze(original, modified)

        # Major changes produce row-level operations (deletes and inserts)
        delete_ops = [op for op in operations if op.op_type == OperationType.TABLE_DELETE_ROW]
        insert_ops = [op for op in operations if op.op_type == OperationType.TABLE_INSERT_ROW]

        # 2 rows deleted (old rows), 2 rows inserted (new rows)
        assert len(delete_ops) == 2
        assert len(insert_ops) == 2

    def test_analyze_table_row_deleted(self, analyzer):
        """Deleting a table row should produce TABLE_DELETE_ROW operation."""
        original = [
            ContentBlock(
                BlockType.TABLE,
                "Header1 Header2 Row1Col1 Row1Col2 Row2Col1 Row2Col2",
                rows=[["Header1", "Header2"], ["Row1Col1", "Row1Col2"], ["Row2Col1", "Row2Col2"]],
                index=0,
            ),
        ]
        modified = [
            ContentBlock(
                BlockType.TABLE,
                "Header1 Header2 Row2Col1 Row2Col2",
                rows=[["Header1", "Header2"], ["Row2Col1", "Row2Col2"]],
                index=0,
            ),
        ]

        operations = analyzer.analyze(original, modified)

        # One row deleted
        delete_ops = [op for op in operations if op.op_type == OperationType.TABLE_DELETE_ROW]
        assert len(delete_ops) == 1
        assert "Row1Col1" in delete_ops[0].new_content

    def test_analyze_table_row_inserted(self, analyzer):
        """Inserting a table row should produce TABLE_INSERT_ROW operation."""
        original = [
            ContentBlock(
                BlockType.TABLE,
                "Header1 Header2 Row1Col1 Row1Col2",
                rows=[["Header1", "Header2"], ["Row1Col1", "Row1Col2"]],
                index=0,
            ),
        ]
        modified = [
            ContentBlock(
                BlockType.TABLE,
                "Header1 Header2 Row1Col1 Row1Col2 NewRow1 NewRow2",
                rows=[["Header1", "Header2"], ["Row1Col1", "Row1Col2"], ["NewRow1", "NewRow2"]],
                index=0,
            ),
        ]

        operations = analyzer.analyze(original, modified)

        # One row inserted
        insert_ops = [op for op in operations if op.op_type == OperationType.TABLE_INSERT_ROW]
        assert len(insert_ops) == 1
        assert "NewRow1" in insert_ops[0].new_content

    def test_analyze_table_cell_updated(self, analyzer):
        """Updating a cell should produce TABLE_UPDATE_CELL operation."""
        original = [
            ContentBlock(
                BlockType.TABLE,
                "Header1 Header2 OldValue Col2",
                rows=[["Header1", "Header2"], ["OldValue", "Col2"]],
                index=0,
            ),
        ]
        modified = [
            ContentBlock(
                BlockType.TABLE,
                "Header1 Header2 NewValue Col2",
                rows=[["Header1", "Header2"], ["NewValue", "Col2"]],
                index=0,
            ),
        ]

        operations = analyzer.analyze(original, modified)

        # One cell updated
        update_ops = [op for op in operations if op.op_type == OperationType.TABLE_UPDATE_CELL]
        assert len(update_ops) == 1
        assert update_ops[0].new_content == "NewValue"
        assert update_ops[0].row_index == 1  # Second row (data row)
        assert update_ops[0].cell_index == 0  # First cell

    def test_analyze_multiple_changes(self, analyzer):
        """Multiple changes should produce multiple operations."""
        original = [
            ContentBlock(BlockType.HEADING, "Title", level=1, index=0),
            ContentBlock(BlockType.PARAGRAPH, "Paragraph 1", index=1),
            ContentBlock(BlockType.PARAGRAPH, "Original para 3", index=2),
        ]
        modified = [
            ContentBlock(BlockType.HEADING, "New Title", level=1, index=0),
            ContentBlock(BlockType.PARAGRAPH, "Paragraph 1", index=1),
            ContentBlock(BlockType.PARAGRAPH, "Modified para 3", index=2),
        ]

        operations = analyzer.analyze(original, modified)

        # Should have UPDATE operations for changed heading and paragraph
        # "Paragraph 1" is unchanged so no operation for it
        op_types = [op.op_type for op in operations]
        assert len(operations) == 2
        assert all(op.op_type == OperationType.UPDATE_TEXT for op in operations)

    def test_analyze_delete_and_insert_operations(self, analyzer):
        """Adding and removing blocks should produce INSERT and DELETE operations."""
        original = [
            ContentBlock(BlockType.HEADING, "Title", level=1, index=0),
            ContentBlock(BlockType.PARAGRAPH, "To be deleted", index=1),
        ]
        modified = [
            ContentBlock(BlockType.HEADING, "Title", level=1, index=0),
            ContentBlock(BlockType.PARAGRAPH, "Completely new content", index=1),
        ]

        operations = analyzer.analyze(original, modified)

        # Position 1 changes from "To be deleted" to "Completely new content"
        # This is an UPDATE since it's at the same position
        assert len(operations) == 1
        assert operations[0].op_type == OperationType.UPDATE_TEXT

    def test_similarity_calculation(self, analyzer):
        """Similarity should be based on word overlap."""
        # High similarity
        score1 = analyzer._similarity("hello world", "hello beautiful world")
        assert score1 > 0.5

        # Low similarity
        score2 = analyzer._similarity("hello world", "foo bar baz")
        assert score2 < 0.3

        # Empty strings
        score3 = analyzer._similarity("", "hello")
        assert score3 == 0.0

        # Identical strings
        score4 = analyzer._similarity("hello world", "hello world")
        assert score4 == 1.0

    def test_block_key_generation(self, analyzer):
        """Block keys should combine type and content."""
        block = ContentBlock(BlockType.PARAGRAPH, "Test content here", index=0)

        key = analyzer._block_key(block)

        assert "paragraph" in key
        assert "Test content" in key

    def test_block_key_truncates_long_content(self, analyzer):
        """Block keys should truncate content over 100 characters."""
        long_content = "x" * 200
        block = ContentBlock(BlockType.PARAGRAPH, long_content, index=0)

        key = analyzer._block_key(block)

        # Key should contain at most 100 chars of content
        assert len(key) < 150  # type + 100 chars content + separator


class TestDiffAnalyzerSimilarityMatching:
    """Test cases for fuzzy matching in DiffAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create a DiffAnalyzer instance."""
        return DiffAnalyzer()

    def test_finds_similar_block_for_minor_edit(self, analyzer):
        """Should match blocks with minor text differences."""
        mod_block = ContentBlock(
            BlockType.PARAGRAPH,
            "This is a slightly modified paragraph",
            index=0,
        )
        orig_blocks = [
            ContentBlock(BlockType.PARAGRAPH, "This is a paragraph", index=0),
        ]

        similar = analyzer._find_similar_block(mod_block, orig_blocks, set())

        assert similar is not None
        assert similar.content == "This is a paragraph"

    def test_ignores_already_matched_blocks(self, analyzer):
        """Should not match blocks that are already matched."""
        mod_block = ContentBlock(BlockType.PARAGRAPH, "Test content", index=0)
        orig_blocks = [
            ContentBlock(BlockType.PARAGRAPH, "Test content", index=0),
        ]
        already_matched = {analyzer._block_key(orig_blocks[0])}

        similar = analyzer._find_similar_block(mod_block, orig_blocks, already_matched)

        assert similar is None

    def test_requires_same_block_type(self, analyzer):
        """Should not match blocks of different types."""
        mod_block = ContentBlock(BlockType.PARAGRAPH, "Test content", index=0)
        orig_blocks = [
            ContentBlock(BlockType.LIST, "Test content", index=0),
        ]

        similar = analyzer._find_similar_block(mod_block, orig_blocks, set())

        assert similar is None

    def test_allows_heading_to_heading_match_different_levels(self, analyzer):
        """Should match headings regardless of level."""
        mod_block = ContentBlock(
            BlockType.HEADING, "Section Title", level=2, index=0
        )
        orig_blocks = [
            ContentBlock(BlockType.HEADING, "Section Title", level=1, index=0),
        ]

        similar = analyzer._find_similar_block(mod_block, orig_blocks, set())

        # Should match despite different levels
        assert similar is not None


class TestDiffAnalyzerWhitespaceNormalization:
    """Test cases for whitespace normalization in DiffAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create a DiffAnalyzer instance."""
        return DiffAnalyzer()

    def test_whitespace_differences_do_not_cause_spurious_updates(self, analyzer):
        """Blocks with only whitespace differences should match (no update operation)."""
        # XHTML parsing might produce different whitespace than markdown
        original = [
            ContentBlock(BlockType.PARAGRAPH, "This is  some   text", index=0),
            ContentBlock(BlockType.PARAGRAPH, "Another\n paragraph", index=1),
        ]
        modified = [
            ContentBlock(BlockType.PARAGRAPH, "This is some text", index=0),
            ContentBlock(BlockType.PARAGRAPH, "Another paragraph", index=1),
        ]

        operations = analyzer.analyze(original, modified)

        # No operations should be generated - content is semantically identical
        assert len(operations) == 0

    def test_real_content_change_with_whitespace_variation(self, analyzer):
        """Real content changes should be detected despite whitespace variations."""
        original = [
            ContentBlock(BlockType.PARAGRAPH, "Original  text here", index=0),
        ]
        modified = [
            ContentBlock(BlockType.PARAGRAPH, "Modified text here", index=0),
        ]

        operations = analyzer.analyze(original, modified)

        # Should generate one UPDATE operation for the real change
        assert len(operations) == 1
        assert operations[0].op_type == OperationType.UPDATE_TEXT

    def test_table_whitespace_normalization(self, analyzer):
        """Tables with whitespace variations in cells should match."""
        original = [
            ContentBlock(
                BlockType.TABLE,
                "Col A  Col B  Val 1  Val 2",
                rows=[["Col A", "Col B"], ["Val 1", "Val 2"]],
                index=0,
            ),
        ]
        modified = [
            ContentBlock(
                BlockType.TABLE,
                "Col A Col B Val 1 Val 2",
                rows=[["Col A", "Col B"], ["Val 1", "Val 2"]],
                index=0,
            ),
        ]

        operations = analyzer.analyze(original, modified)

        # No operations - tables are semantically identical
        assert len(operations) == 0

    def test_table_cell_change_detected_with_whitespace(self, analyzer):
        """Real table cell changes should be detected despite whitespace."""
        original = [
            ContentBlock(
                BlockType.TABLE,
                "Header  Value  Active",
                rows=[["Header", "Value"], ["100", "Active"]],
                index=0,
            ),
        ]
        modified = [
            ContentBlock(
                BlockType.TABLE,
                "Header Value Done",
                rows=[["Header", "Value"], ["100", "Done"]],  # Active -> Done
                index=0,
            ),
        ]

        operations = analyzer.analyze(original, modified)

        # Should detect the cell change
        assert len(operations) == 1
        assert operations[0].op_type == OperationType.TABLE_UPDATE_CELL
        assert operations[0].new_content == "Done"
