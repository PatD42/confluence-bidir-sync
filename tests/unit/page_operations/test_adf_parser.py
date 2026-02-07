"""Unit tests for ADF parser module."""

import pytest
from src.page_operations.adf_parser import AdfParser, adf_block_type_to_content_block_type
from src.page_operations.adf_models import AdfNodeType, AdfDocument
from src.page_operations.models import BlockType


class TestAdfParser:
    """Test suite for AdfParser class."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return AdfParser()

    @pytest.fixture
    def simple_adf(self):
        """Simple ADF document with paragraph."""
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"localId": "para-1"},
                    "content": [
                        {"type": "text", "text": "Hello world"}
                    ]
                }
            ]
        }

    @pytest.fixture
    def complex_adf(self):
        """Complex ADF document with multiple node types."""
        return {
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
                    "type": "paragraph",
                    "attrs": {"localId": "para-1"},
                    "content": [
                        {"type": "text", "text": "Introduction text"}
                    ]
                },
                {
                    "type": "bulletList",
                    "attrs": {"localId": "list-1"},
                    "content": [
                        {
                            "type": "listItem",
                            "attrs": {"localId": "item-1"},
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": "Item 1"}
                                    ]
                                }
                            ]
                        },
                        {
                            "type": "listItem",
                            "attrs": {"localId": "item-2"},
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": "Item 2"}
                                    ]
                                }
                            ]
                        }
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
                }
            ]
        }

    @pytest.fixture
    def table_adf(self):
        """ADF document with a table."""
        return {
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
                                    "type": "tableHeader",
                                    "attrs": {"localId": "cell-1a"},
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "Header 1"}]
                                        }
                                    ]
                                },
                                {
                                    "type": "tableHeader",
                                    "attrs": {"localId": "cell-1b"},
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "Header 2"}]
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
                                            "content": [{"type": "text", "text": "Cell 1"}]
                                        }
                                    ]
                                },
                                {
                                    "type": "tableCell",
                                    "attrs": {"localId": "cell-2b"},
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "Cell 2"}]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

    def test_parse_simple_document(self, parser, simple_adf):
        """Test parsing a simple ADF document."""
        doc = parser.parse_document(simple_adf)

        assert isinstance(doc, AdfDocument)
        assert doc.version == 1
        assert len(doc.content) == 1
        assert doc.content[0].type == "paragraph"
        assert doc.content[0].local_id == "para-1"

    def test_parse_document_extracts_text(self, parser, simple_adf):
        """Test that text content is properly extracted."""
        doc = parser.parse_document(simple_adf)

        para = doc.content[0]
        assert para.get_text_content() == "Hello world"

    def test_parse_complex_document(self, parser, complex_adf):
        """Test parsing a complex document with multiple node types."""
        doc = parser.parse_document(complex_adf)

        assert len(doc.content) == 4

        # Check heading
        heading = doc.content[0]
        assert heading.type == "heading"
        assert heading.attrs.get("level") == 1
        assert heading.get_text_content() == "Main Title"

        # Check macro is preserved
        macro = doc.content[3]
        assert macro.type == "extension"
        assert macro.attrs.get("extensionKey") == "toc"

    def test_find_by_local_id(self, parser, complex_adf):
        """Test finding nodes by localId."""
        doc = parser.parse_document(complex_adf)

        # Find heading
        node = doc.find_by_local_id("head-1")
        assert node is not None
        assert node.type == "heading"

        # Find nested list item
        node = doc.find_by_local_id("item-2")
        assert node is not None
        assert node.type == "listItem"

        # Non-existent ID
        node = doc.find_by_local_id("does-not-exist")
        assert node is None

    def test_extract_blocks_paragraph(self, parser, simple_adf):
        """Test extracting blocks from simple document."""
        doc = parser.parse_document(simple_adf)
        blocks = parser.extract_blocks(doc)

        assert len(blocks) == 1
        assert blocks[0].node_type == AdfNodeType.PARAGRAPH
        assert blocks[0].content == "Hello world"
        assert blocks[0].local_id == "para-1"

    def test_extract_blocks_heading(self, parser, complex_adf):
        """Test extracting heading blocks."""
        doc = parser.parse_document(complex_adf)
        blocks = parser.extract_blocks(doc)

        heading_block = blocks[0]
        assert heading_block.node_type == AdfNodeType.HEADING
        assert heading_block.level == 1
        assert heading_block.content == "Main Title"

    def test_extract_blocks_list(self, parser, complex_adf):
        """Test extracting list items as individual blocks."""
        doc = parser.parse_document(complex_adf)
        blocks = parser.extract_blocks(doc)

        # List items are now extracted individually (not as single list block)
        # Index 0: heading, Index 1: paragraph, Index 2-3: list items
        assert len(blocks) == 5  # heading + para + 2 list items + macro

        item1_block = blocks[2]
        assert item1_block.node_type == AdfNodeType.LIST_ITEM
        assert item1_block.content == "Item 1"
        assert item1_block.local_id == "item-1"

        item2_block = blocks[3]
        assert item2_block.node_type == AdfNodeType.LIST_ITEM
        assert item2_block.content == "Item 2"
        assert item2_block.local_id == "item-2"

    def test_extract_blocks_macro(self, parser, complex_adf):
        """Test extracting macro blocks."""
        doc = parser.parse_document(complex_adf)
        blocks = parser.extract_blocks(doc)

        # Macro is at index 4 (after 2 individual list items)
        macro_block = blocks[4]
        assert macro_block.node_type == AdfNodeType.EXTENSION
        assert macro_block.is_macro
        assert "toc" in macro_block.content

    def test_extract_blocks_table(self, parser, table_adf):
        """Test extracting table blocks with rows."""
        doc = parser.parse_document(table_adf)
        blocks = parser.extract_blocks(doc)

        assert len(blocks) == 1
        table_block = blocks[0]

        assert table_block.node_type == AdfNodeType.TABLE
        assert table_block.local_id == "table-1"
        assert len(table_block.rows) == 2
        assert table_block.rows[0] == ["Header 1", "Header 2"]
        assert table_block.rows[1] == ["Cell 1", "Cell 2"]

    def test_parse_invalid_document_raises(self, parser):
        """Test that invalid ADF raises ValueError."""
        with pytest.raises(ValueError):
            parser.parse_document({"type": "not-a-doc"})

        with pytest.raises(ValueError):
            parser.parse_document("not a dict")

    def test_parse_from_string(self, parser):
        """Test parsing from JSON string."""
        json_str = '{"type": "doc", "version": 1, "content": []}'
        doc = parser.parse_from_string(json_str)

        assert isinstance(doc, AdfDocument)
        assert doc.version == 1

    def test_document_to_dict(self, parser, simple_adf):
        """Test converting document back to dictionary."""
        doc = parser.parse_document(simple_adf)
        result = doc.to_dict()

        assert result["type"] == "doc"
        assert result["version"] == 1
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "paragraph"


class TestAdfBlockTypeMapping:
    """Test ADF to ContentBlock type mapping."""

    def test_paragraph_mapping(self):
        """Test paragraph type mapping."""
        result = adf_block_type_to_content_block_type(AdfNodeType.PARAGRAPH)
        assert result == BlockType.PARAGRAPH

    def test_heading_mapping(self):
        """Test heading type mapping."""
        result = adf_block_type_to_content_block_type(AdfNodeType.HEADING)
        assert result == BlockType.HEADING

    def test_table_mapping(self):
        """Test table type mapping."""
        result = adf_block_type_to_content_block_type(AdfNodeType.TABLE)
        assert result == BlockType.TABLE

    def test_list_mapping(self):
        """Test list type mapping."""
        result = adf_block_type_to_content_block_type(AdfNodeType.BULLET_LIST)
        assert result == BlockType.LIST

        result = adf_block_type_to_content_block_type(AdfNodeType.ORDERED_LIST)
        assert result == BlockType.LIST

        result = adf_block_type_to_content_block_type(AdfNodeType.LIST_ITEM)
        assert result == BlockType.LIST

    def test_code_mapping(self):
        """Test code block type mapping."""
        result = adf_block_type_to_content_block_type(AdfNodeType.CODE_BLOCK)
        assert result == BlockType.CODE

    def test_extension_mapping(self):
        """Test macro/extension type mapping."""
        result = adf_block_type_to_content_block_type(AdfNodeType.EXTENSION)
        assert result == BlockType.MACRO

    def test_unknown_mapping(self):
        """Test unknown type mapping."""
        result = adf_block_type_to_content_block_type(AdfNodeType.RULE)
        assert result == BlockType.OTHER
