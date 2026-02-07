"""Unit tests for ADF editor module."""

import pytest
from src.page_operations.adf_editor import AdfEditor
from src.page_operations.adf_parser import AdfParser
from src.page_operations.adf_models import AdfDocument, AdfNode, AdfNodeType
from src.page_operations.models import OperationType, SurgicalOperation


class TestAdfEditor:
    """Test suite for AdfEditor class."""

    @pytest.fixture
    def editor(self):
        """Create editor instance."""
        return AdfEditor()

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return AdfParser()

    @pytest.fixture
    def simple_doc(self, parser):
        """Simple document with a paragraph."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-1"},
                    "content": [
                        {"type": "text", "text": "Original text"}
                    ]
                }
            ]
        }
        return parser.parse_document(adf)

    @pytest.fixture
    def multi_para_doc(self, parser):
        """Document with multiple paragraphs."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-1"},
                    "content": [
                        {"type": "text", "text": "First paragraph"}
                    ]
                },
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-2"},
                    "content": [
                        {"type": "text", "text": "Second paragraph"}
                    ]
                },
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-3"},
                    "content": [
                        {"type": "text", "text": "Third paragraph"}
                    ]
                }
            ]
        }
        return parser.parse_document(adf)

    @pytest.fixture
    def heading_doc(self, parser):
        """Document with headings."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1, "localId": "head-1"},
                    "content": [
                        {"type": "text", "text": "Main Title"}
                    ]
                },
                {
                    "type": "heading",
                    "attrs": {"level": 2, "localId": "head-2"},
                    "content": [
                        {"type": "text", "text": "Subtitle"}
                    ]
                }
            ]
        }
        return parser.parse_document(adf)

    @pytest.fixture
    def doc_with_macro(self, parser):
        """Document with a macro."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-1"},
                    "content": [
                        {"type": "text", "text": "Before macro"}
                    ]
                },
                {
                    "type": "extension",
                    "attrs": {
                        "layout": "default",
                        "extensionType": "com.atlassian.confluence.macro.core",
                        "extensionKey": "toc",
                        "localId": "macro-1"
                    }
                },
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-2"},
                    "content": [
                        {"type": "text", "text": "After macro"}
                    ]
                }
            ]
        }
        return parser.parse_document(adf)

    @pytest.fixture
    def table_doc(self, parser):
        """Document with a table."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "table",
                    "attrs": {"localId": "table-1"},
                    "content": [
                        {
                            "type": "tableRow",
                            "attrs": {"localId": "row-1"},
                            "content": [
                                {
                                    "type": "tableCell",
                                    "attrs": {"localId": "cell-1"},
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {"type": "text", "text": "Cell content"}
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        return parser.parse_document(adf)

    # --- UPDATE_TEXT Tests ---

    def test_update_text_by_local_id(self, editor, simple_doc):
        """Test updating text content using localId matching."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Original text",
                new_content="Updated text",
            )
        ]

        modified, success, failure = editor.apply_operations(
            simple_doc, operations, {"Original text": "para-1"}
        )

        assert success == 1
        assert failure == 0
        assert modified.content[0].get_text_content() == "Updated text"

    def test_update_text_partial_match(self, editor, multi_para_doc):
        """Test updating text with partial content matching."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Second paragraph",
                new_content="Modified second",
            )
        ]

        modified, success, failure = editor.apply_operations(
            multi_para_doc, operations, {"Second paragraph": "para-2"}
        )

        assert success == 1
        assert modified.content[1].get_text_content() == "Modified second"

    def test_update_text_no_match_fails(self, editor, simple_doc):
        """Test that updating non-existent content fails."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Non-existent text",
                new_content="Updated",
            )
        ]

        modified, success, failure = editor.apply_operations(
            simple_doc, operations, {}
        )

        assert success == 0
        assert failure == 1

    # --- DELETE_BLOCK Tests ---

    def test_delete_block(self, editor, multi_para_doc):
        """Test deleting a block by localId."""
        original_count = len(multi_para_doc.content)

        operations = [
            SurgicalOperation(
                op_type=OperationType.DELETE_BLOCK,
                target_content="Second paragraph",
            )
        ]

        modified, success, failure = editor.apply_operations(
            multi_para_doc, operations, {"Second paragraph": "para-2"}
        )

        assert success == 1
        assert len(modified.content) == original_count - 1
        # Verify second paragraph is gone
        contents = [n.get_text_content() for n in modified.content]
        assert "Second paragraph" not in contents

    def test_delete_macro_refused(self, editor, doc_with_macro):
        """Test that deleting macros is refused."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.DELETE_BLOCK,
                target_content="[MACRO:toc]",
            )
        ]

        modified, success, failure = editor.apply_operations(
            doc_with_macro, operations, {"[MACRO:toc]": "macro-1"}
        )

        # Should fail - macros should not be deleted
        assert success == 0
        assert failure == 1
        # Macro should still be there
        assert len(modified.content) == 3

    # --- INSERT_BLOCK Tests ---

    def test_insert_block_after(self, editor, multi_para_doc):
        """Test inserting a new block after an anchor."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.INSERT_BLOCK,
                new_content="Inserted paragraph",
                after_content="First paragraph",
            )
        ]

        modified, success, failure = editor.apply_operations(
            multi_para_doc, operations, {"First paragraph": "para-1"}
        )

        assert success == 1
        assert len(modified.content) == 4
        # Check insertion position
        assert modified.content[1].get_text_content() == "Inserted paragraph"

    def test_insert_block_at_end(self, editor, simple_doc):
        """Test inserting at end when no anchor found."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.INSERT_BLOCK,
                new_content="New at end",
                after_content="Non-existent anchor",
            )
        ]

        modified, success, failure = editor.apply_operations(
            simple_doc, operations, {}
        )

        assert success == 1
        assert len(modified.content) == 2
        assert modified.content[-1].get_text_content() == "New at end"

    # --- CHANGE_HEADING_LEVEL Tests ---

    def test_change_heading_level(self, editor, heading_doc):
        """Test changing a heading level."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.CHANGE_HEADING_LEVEL,
                target_content="Subtitle",
                new_level=3,
            )
        ]

        modified, success, failure = editor.apply_operations(
            heading_doc, operations, {"Subtitle": "head-2"}
        )

        assert success == 1
        assert modified.content[1].attrs["level"] == 3

    def test_change_heading_level_non_heading_fails(self, editor, simple_doc):
        """Test that changing level on non-heading fails."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.CHANGE_HEADING_LEVEL,
                target_content="Original text",
                new_level=2,
            )
        ]

        modified, success, failure = editor.apply_operations(
            simple_doc, operations, {"Original text": "para-1"}
        )

        assert success == 0
        assert failure == 1

    # --- TABLE_UPDATE_CELL Tests ---

    def test_table_update_cell(self, editor, table_doc):
        """Test updating a table cell."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.TABLE_UPDATE_CELL,
                target_content="Cell content",
                new_content="New cell content",
                row_index=0,
                cell_index=0,
            )
        ]

        modified, success, failure = editor.apply_operations(
            table_doc, operations, {}
        )

        assert success == 1
        cell = modified.content[0].content[0].content[0]
        assert cell.get_text_content() == "New cell content"

    # --- Macro Preservation Tests ---

    def test_macro_count_unchanged(self, editor, doc_with_macro):
        """Test that macro count is preserved after operations."""
        macros_before = editor.count_macros(doc_with_macro)

        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Before macro",
                new_content="Modified before macro",
            )
        ]

        modified, _, _ = editor.apply_operations(
            doc_with_macro, operations, {"Before macro": "para-1"}
        )

        macros_after = editor.count_macros(modified)
        assert macros_after == macros_before

    def test_update_text_near_macro(self, editor, doc_with_macro):
        """Test updating text adjacent to macros preserves macro."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="After macro",
                new_content="Still after macro",
            )
        ]

        modified, success, _ = editor.apply_operations(
            doc_with_macro, operations, {"After macro": "para-2"}
        )

        assert success == 1
        # Verify macro is still in position 1
        assert modified.content[1].type == "extension"

    # --- Edge Cases ---

    def test_empty_operations_list(self, editor, simple_doc):
        """Test applying empty operations list."""
        modified, success, failure = editor.apply_operations(
            simple_doc, [], {}
        )

        assert success == 0
        assert failure == 0
        assert modified.content[0].get_text_content() == "Original text"

    def test_document_not_mutated(self, editor, simple_doc):
        """Test that original document is not mutated."""
        original_text = simple_doc.content[0].get_text_content()

        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Original text",
                new_content="Updated",
            )
        ]

        editor.apply_operations(simple_doc, operations, {"Original text": "para-1"})

        # Original should be unchanged
        assert simple_doc.content[0].get_text_content() == original_text

    def test_multiple_operations(self, editor, multi_para_doc):
        """Test applying multiple operations in sequence."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="First paragraph",
                new_content="Modified first",
            ),
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Third paragraph",
                new_content="Modified third",
            ),
        ]

        local_id_map = {
            "First paragraph": "para-1",
            "Third paragraph": "para-3",
        }

        modified, success, failure = editor.apply_operations(
            multi_para_doc, operations, local_id_map
        )

        assert success == 2
        assert failure == 0
        assert modified.content[0].get_text_content() == "Modified first"
        assert modified.content[2].get_text_content() == "Modified third"


class TestAdfEditorCountMacros:
    """Test macro counting functionality."""

    @pytest.fixture
    def editor(self):
        return AdfEditor()

    @pytest.fixture
    def parser(self):
        return AdfParser()

    def test_count_macros_none(self, editor, parser):
        """Test counting macros when there are none."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "No macros"}]
                }
            ]
        }
        doc = parser.parse_document(adf)
        assert editor.count_macros(doc) == 0

    def test_count_macros_one(self, editor, parser):
        """Test counting single macro."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "extension",
                    "attrs": {"extensionKey": "toc"}
                }
            ]
        }
        doc = parser.parse_document(adf)
        assert editor.count_macros(doc) == 1

    def test_count_macros_multiple(self, editor, parser):
        """Test counting multiple macros."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "extension", "attrs": {"extensionKey": "toc"}},
                {"type": "paragraph", "content": []},
                {"type": "extension", "attrs": {"extensionKey": "code"}},
                {"type": "inlineExtension", "attrs": {"extensionKey": "emoji"}},
            ]
        }
        doc = parser.parse_document(adf)
        assert editor.count_macros(doc) == 3  # extension + extension + inlineExtension


class TestAdfEditorBrToHardBreak:
    """Test <br> to hardBreak conversion in ADF editor."""

    @pytest.fixture
    def editor(self):
        return AdfEditor()

    @pytest.fixture
    def parser(self):
        return AdfParser()

    def test_text_to_adf_nodes_no_br(self, editor):
        """Convert plain text without <br> tags."""
        nodes = editor._text_to_adf_nodes("Hello world")

        assert len(nodes) == 1
        assert nodes[0].type == "text"
        assert nodes[0].text == "Hello world"

    def test_text_to_adf_nodes_single_br(self, editor):
        """Convert text with single <br> tag to hardBreak."""
        nodes = editor._text_to_adf_nodes("Line 1<br>Line 2")

        assert len(nodes) == 3
        assert nodes[0].type == "text"
        assert nodes[0].text == "Line 1"
        assert nodes[1].type == "hardBreak"
        assert nodes[2].type == "text"
        assert nodes[2].text == "Line 2"

    def test_text_to_adf_nodes_multiple_br(self, editor):
        """Convert text with multiple <br> tags."""
        nodes = editor._text_to_adf_nodes("A<br>B<br>C")

        assert len(nodes) == 5
        assert nodes[0].type == "text"
        assert nodes[0].text == "A"
        assert nodes[1].type == "hardBreak"
        assert nodes[2].type == "text"
        assert nodes[2].text == "B"
        assert nodes[3].type == "hardBreak"
        assert nodes[4].type == "text"
        assert nodes[4].text == "C"

    def test_text_to_adf_nodes_br_variants(self, editor):
        """Handle <br/> and <br /> variants."""
        nodes_slash = editor._text_to_adf_nodes("A<br/>B")
        nodes_space_slash = editor._text_to_adf_nodes("A<br />B")

        # Both should produce same result
        assert len(nodes_slash) == 3
        assert nodes_slash[1].type == "hardBreak"

        assert len(nodes_space_slash) == 3
        assert nodes_space_slash[1].type == "hardBreak"

    def test_text_to_adf_nodes_empty(self, editor):
        """Handle empty text."""
        nodes = editor._text_to_adf_nodes("")

        assert len(nodes) == 1
        assert nodes[0].type == "text"
        assert nodes[0].text == ""

    def test_text_to_adf_nodes_leading_br(self, editor):
        """Handle <br> at start of text."""
        nodes = editor._text_to_adf_nodes("<br>Line after")

        # <br> at start means empty part before it
        assert len(nodes) == 2
        assert nodes[0].type == "hardBreak"
        assert nodes[1].type == "text"
        assert nodes[1].text == "Line after"

    def test_text_to_adf_nodes_trailing_br(self, editor):
        """Handle <br> at end of text."""
        nodes = editor._text_to_adf_nodes("Line before<br>")

        assert len(nodes) == 2
        assert nodes[0].type == "text"
        assert nodes[0].text == "Line before"
        assert nodes[1].type == "hardBreak"


class TestAdfEditorReplaceExistingHardBreaks:
    """Test replacing content that already contains hardBreak nodes."""

    @pytest.fixture
    def editor(self):
        return AdfEditor()

    @pytest.fixture
    def parser(self):
        return AdfParser()

    @pytest.fixture
    def doc_with_hardbreaks(self, parser):
        """Document with paragraph containing hardBreak nodes."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-1"},
                    "content": [
                        {"type": "text", "text": "Highest in"},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "the world"},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "for now."}
                    ]
                }
            ]
        }
        return parser.parse_document(adf)

    def test_replace_hardbreak_content_with_new_br(self, editor, doc_with_hardbreaks):
        """Replace content that has hardBreaks with new content containing <br>.

        This is the critical fix for the duplication bug where old hardBreak nodes
        were not being removed.
        """
        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Highest in the world for now.",
                new_content="Highest 1 in<br>this world<br>for now.",
            )
        ]

        local_id_map = {"Highest in the world for now.": "para-1"}

        modified, success, failure = editor.apply_operations(
            doc_with_hardbreaks, operations, local_id_map
        )

        assert success == 1
        assert failure == 0

        # Check resulting content structure
        para = modified.content[0]
        assert para.type == "paragraph"

        # Should have exactly 5 nodes: text, hardBreak, text, hardBreak, text
        assert len(para.content) == 5

        assert para.content[0].type == "text"
        assert para.content[0].text == "Highest 1 in"
        assert para.content[1].type == "hardBreak"
        assert para.content[2].type == "text"
        assert para.content[2].text == "this world"
        assert para.content[3].type == "hardBreak"
        assert para.content[4].type == "text"
        assert para.content[4].text == "for now."

    def test_replace_hardbreak_content_with_plain_text(self, editor, doc_with_hardbreaks):
        """Replace multi-line content with single line (no <br>)."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Highest in the world for now.",
                new_content="Just a single line.",
            )
        ]

        local_id_map = {"Highest in the world for now.": "para-1"}

        modified, success, failure = editor.apply_operations(
            doc_with_hardbreaks, operations, local_id_map
        )

        assert success == 1

        # Should have exactly 1 text node - all hardBreaks removed
        para = modified.content[0]
        assert len(para.content) == 1
        assert para.content[0].type == "text"
        assert para.content[0].text == "Just a single line."

    def test_replace_hardbreak_content_with_more_br(self, editor, doc_with_hardbreaks):
        """Replace 2-line content with 4-line content."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Highest in the world for now.",
                new_content="Line 1<br>Line 2<br>Line 3<br>Line 4",
            )
        ]

        local_id_map = {"Highest in the world for now.": "para-1"}

        modified, success, failure = editor.apply_operations(
            doc_with_hardbreaks, operations, local_id_map
        )

        assert success == 1

        # Should have 7 nodes: 4 text + 3 hardBreak
        para = modified.content[0]
        assert len(para.content) == 7

        # Verify structure
        text_nodes = [n for n in para.content if n.type == "text"]
        hardbreak_nodes = [n for n in para.content if n.type == "hardBreak"]

        assert len(text_nodes) == 4
        assert len(hardbreak_nodes) == 3
        assert [n.text for n in text_nodes] == ["Line 1", "Line 2", "Line 3", "Line 4"]

    def test_replace_preserves_marks(self, editor, parser):
        """Replacing content should preserve formatting marks."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-1"},
                    "content": [
                        {
                            "type": "text",
                            "text": "Bold text",
                            "marks": [{"type": "strong"}]
                        },
                        {"type": "hardBreak"},
                        {"type": "text", "text": "Normal text"}
                    ]
                }
            ]
        }
        doc = parser.parse_document(adf)

        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Bold text Normal text",
                new_content="New bold<br>New normal",
            )
        ]

        local_id_map = {"Bold text Normal text": "para-1"}

        modified, success, _ = editor.apply_operations(doc, operations, local_id_map)

        assert success == 1

        para = modified.content[0]
        # First text node should have strong mark preserved
        assert para.content[0].type == "text"
        assert para.content[0].text == "New bold"
        # Check that marks exist and first mark is "strong" type
        assert para.content[0].marks is not None
        assert len(para.content[0].marks) == 1
        assert para.content[0].marks[0].type == "strong"


class TestAdfEditorTableOperations:
    """Tests for table row insert and delete operations."""

    @pytest.fixture
    def editor(self):
        return AdfEditor()

    @pytest.fixture
    def parser(self):
        return AdfParser()

    @pytest.fixture
    def multi_row_table_doc(self, parser):
        """Document with a table having multiple rows."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "table",
                    "attrs": {"localId": "table-1"},
                    "content": [
                        {
                            "type": "tableRow",
                            "attrs": {"localId": "row-header"},
                            "content": [
                                {
                                    "type": "tableHeader",
                                    "attrs": {"localId": "cell-h1"},
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "Name"}]
                                        }
                                    ]
                                },
                                {
                                    "type": "tableHeader",
                                    "attrs": {"localId": "cell-h2"},
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "Value"}]
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            "type": "tableRow",
                            "attrs": {"localId": "row-1"},
                            "content": [
                                {
                                    "type": "tableCell",
                                    "attrs": {"localId": "cell-1a"},
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "Alice"}]
                                        }
                                    ]
                                },
                                {
                                    "type": "tableCell",
                                    "attrs": {"localId": "cell-1b"},
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "100"}]
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            "type": "tableRow",
                            "attrs": {"localId": "row-2"},
                            "content": [
                                {
                                    "type": "tableCell",
                                    "attrs": {"localId": "cell-2a"},
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "Bob"}]
                                        }
                                    ]
                                },
                                {
                                    "type": "tableCell",
                                    "attrs": {"localId": "cell-2b"},
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "200"}]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        return parser.parse_document(adf)

    def test_table_insert_row_basic(self, editor, multi_row_table_doc):
        """Test inserting a row into a table."""
        original_row_count = len(multi_row_table_doc.content[0].content)

        operations = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="",  # Will match first table
                new_content="Charlie|300",  # Pipe-delimited cell values
                row_index=2,
            )
        ]

        modified, success, failure = editor.apply_operations(
            multi_row_table_doc, operations, {}
        )

        assert success == 1
        assert failure == 0
        assert len(modified.content[0].content) == original_row_count + 1

    def test_table_insert_row_with_after_content(self, editor, multi_row_table_doc):
        """Test inserting a row after a specific row by content."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="",
                new_content="Charlie|300",
                after_content="Alice|100",
                row_index=0,  # Should be overridden by after_content
            )
        ]

        modified, success, failure = editor.apply_operations(
            multi_row_table_doc, operations, {}
        )

        assert success == 1
        # New row should be after Alice (index 1), so at index 2
        new_row = modified.content[0].content[2]
        cell_text = new_row.content[0].get_text_content()
        assert "Charlie" in cell_text

    def test_table_delete_row_by_content(self, editor, multi_row_table_doc):
        """Test deleting a row by its content."""
        original_row_count = len(multi_row_table_doc.content[0].content)

        operations = [
            SurgicalOperation(
                op_type=OperationType.TABLE_DELETE_ROW,
                target_content="",
                new_content="Bob|200",  # Content to match
                row_index=0,
            )
        ]

        modified, success, failure = editor.apply_operations(
            multi_row_table_doc, operations, {}
        )

        assert success == 1
        assert len(modified.content[0].content) == original_row_count - 1
        # Verify Bob's row is gone
        all_text = " ".join([
            row.get_text_content() for row in modified.content[0].content
        ])
        assert "Bob" not in all_text

    def test_table_delete_row_by_index(self, editor, multi_row_table_doc):
        """Test deleting a row by index when content doesn't match."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.TABLE_DELETE_ROW,
                target_content="",
                new_content="",  # No content match
                row_index=1,  # Delete second row (Alice)
            )
        ]

        modified, success, failure = editor.apply_operations(
            multi_row_table_doc, operations, {}
        )

        assert success == 1
        # Verify first data row is gone
        remaining_rows = modified.content[0].content
        assert len(remaining_rows) == 2  # Header + Bob

    def test_table_insert_row_pads_cells(self, editor, multi_row_table_doc):
        """Test that inserted row pads to match column count."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="",
                new_content="OnlyOneValue",  # Single value for 2-column table
                row_index=3,
            )
        ]

        modified, success, failure = editor.apply_operations(
            multi_row_table_doc, operations, {}
        )

        assert success == 1
        new_row = modified.content[0].content[3]
        assert len(new_row.content) == 2  # Should have 2 cells

    def test_table_insert_row_table_not_found(self, editor, parser):
        """Test insert fails gracefully when no table exists."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "No table here"}]
                }
            ]
        }
        doc = parser.parse_document(adf)

        operations = [
            SurgicalOperation(
                op_type=OperationType.TABLE_INSERT_ROW,
                target_content="",
                new_content="A|B",
                row_index=0,
            )
        ]

        modified, success, failure = editor.apply_operations(doc, operations, {})

        assert success == 0
        assert failure == 1

    def test_table_delete_row_not_found(self, editor, multi_row_table_doc):
        """Test delete fails when row content not found."""
        operations = [
            SurgicalOperation(
                op_type=OperationType.TABLE_DELETE_ROW,
                target_content="",
                new_content="NonExistent|Row",
                row_index=999,  # Also invalid index
            )
        ]

        modified, success, failure = editor.apply_operations(
            multi_row_table_doc, operations, {}
        )

        assert success == 0
        assert failure == 1


class TestAdfEditorHelperMethods:
    """Tests for internal helper methods."""

    @pytest.fixture
    def editor(self):
        return AdfEditor()

    @pytest.fixture
    def parser(self):
        return AdfParser()

    def test_build_content_to_id_map(self, editor, parser):
        """Test building content-to-localId mapping."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-1"},
                    "content": [{"type": "text", "text": "First paragraph"}]
                },
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-2"},
                    "content": [{"type": "text", "text": "Second paragraph"}]
                }
            ]
        }
        doc = parser.parse_document(adf)

        content_map = editor._build_content_to_id_map(doc)

        assert "First paragraph" in content_map
        assert content_map["First paragraph"] == "para-1"
        assert "Second paragraph" in content_map
        assert content_map["Second paragraph"] == "para-2"

    def test_find_id_by_partial_content(self, editor, parser):
        """Test finding localId by partial content match."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-1"},
                    "content": [{"type": "text", "text": "This is a long paragraph"}]
                }
            ]
        }
        doc = parser.parse_document(adf)
        content_map = editor._build_content_to_id_map(doc)

        # Should find by partial match
        local_id = editor._find_id_by_partial_content(content_map, "long paragraph")

        assert local_id == "para-1"

    def test_remove_node_by_id(self, editor, parser):
        """Test removing a node by its localId."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-1"},
                    "content": [{"type": "text", "text": "Keep this"}]
                },
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-2"},
                    "content": [{"type": "text", "text": "Delete this"}]
                }
            ]
        }
        doc = parser.parse_document(adf)

        result = editor._remove_node_by_id(doc, "para-2")

        assert result is True
        assert len(doc.content) == 1
        assert doc.content[0].local_id == "para-1"

    def test_create_paragraph_node(self, editor):
        """Test creating a paragraph node with text."""
        node = editor._create_paragraph_node("Test content")

        assert node.type == "paragraph"
        assert len(node.content) == 1
        assert node.content[0].type == "text"
        assert node.content[0].text == "Test content"
