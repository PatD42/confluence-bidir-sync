"""Unit tests for page_operations.content_parser module."""

import pytest

from src.page_operations.content_parser import ContentParser
from src.page_operations.models import BlockType


class TestContentParser:
    """Test cases for ContentParser class."""

    @pytest.fixture
    def parser(self):
        """Create ContentParser instance."""
        return ContentParser()

    # ===== XHTML Parsing Tests =====

    def test_extract_xhtml_blocks_finds_headings(self, parser):
        """extract_xhtml_blocks should find all headings."""
        xhtml = """
        <h1>Title</h1>
        <p>Content</p>
        <h2>Section</h2>
        <h3>Subsection</h3>
        """

        blocks = parser.extract_xhtml_blocks(xhtml)

        headings = [b for b in blocks if b.block_type == BlockType.HEADING]
        assert len(headings) == 3
        assert headings[0].content == "Title"
        assert headings[0].level == 1
        assert headings[1].content == "Section"
        assert headings[1].level == 2
        assert headings[2].content == "Subsection"
        assert headings[2].level == 3

    def test_extract_xhtml_blocks_finds_paragraphs(self, parser):
        """extract_xhtml_blocks should find all paragraphs."""
        xhtml = """
        <p>First paragraph</p>
        <p>Second paragraph</p>
        <p></p>
        <p>Third paragraph</p>
        """

        blocks = parser.extract_xhtml_blocks(xhtml)

        paragraphs = [b for b in blocks if b.block_type == BlockType.PARAGRAPH]
        # Empty paragraph should be skipped
        assert len(paragraphs) == 3

    def test_extract_xhtml_blocks_finds_tables(self, parser):
        """extract_xhtml_blocks should extract table structure."""
        xhtml = """
        <table>
            <tbody>
                <tr><th>A</th><th>B</th></tr>
                <tr><td>1</td><td>2</td></tr>
                <tr><td>3</td><td>4</td></tr>
            </tbody>
        </table>
        """

        blocks = parser.extract_xhtml_blocks(xhtml)

        tables = [b for b in blocks if b.block_type == BlockType.TABLE]
        assert len(tables) == 1
        assert tables[0].rows == [['A', 'B'], ['1', '2'], ['3', '4']]

    def test_extract_xhtml_blocks_finds_lists(self, parser):
        """extract_xhtml_blocks should find individual list items."""
        xhtml = """
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
        <ol>
            <li>First</li>
            <li>Second</li>
        </ol>
        """

        blocks = parser.extract_xhtml_blocks(xhtml)

        lists = [b for b in blocks if b.block_type == BlockType.LIST]
        # Each list item is now extracted as a separate block
        assert len(lists) == 4
        contents = [b.content for b in lists]
        assert "Item 1" in contents
        assert "Item 2" in contents
        assert "First" in contents
        assert "Second" in contents

    def test_extract_xhtml_blocks_finds_nested_lists(self, parser):
        """extract_xhtml_blocks should find lists nested inside containers like divs."""
        xhtml = """
        <div class="content">
            <ol>
                <li><strong>Bold Item</strong>: Description one</li>
                <li><strong>Another Item</strong>: Description two</li>
            </ol>
        </div>
        """

        blocks = parser.extract_xhtml_blocks(xhtml)

        lists = [b for b in blocks if b.block_type == BlockType.LIST]
        # Should find both list items even though nested in div
        assert len(lists) == 2
        contents = [b.content for b in lists]
        assert "Bold Item: Description one" in contents
        assert "Another Item: Description two" in contents

    def test_extract_xhtml_blocks_finds_macros(self, parser):
        """extract_xhtml_blocks should find Confluence macros."""
        xhtml = """
        <p>Text</p>
        <ac:structured-macro ac:name="toc">
            <ac:parameter ac:name="style">none</ac:parameter>
        </ac:structured-macro>
        <p>More text</p>
        """

        blocks = parser.extract_xhtml_blocks(xhtml)

        macros = [b for b in blocks if b.block_type == BlockType.MACRO]
        assert len(macros) == 1
        assert 'ac:name="toc"' in macros[0].content

    def test_extract_xhtml_blocks_preserves_element_reference(self, parser):
        """extract_xhtml_blocks should preserve element reference."""
        xhtml = '<p local-id="abc">Test paragraph</p>'

        blocks = parser.extract_xhtml_blocks(xhtml)

        assert len(blocks) == 1
        assert blocks[0].element is not None
        assert blocks[0].element.get('local-id') == 'abc'

    def test_extract_xhtml_blocks_assigns_indices(self, parser):
        """extract_xhtml_blocks should assign sequential indices."""
        xhtml = """
        <h1>One</h1>
        <p>Two</p>
        <h2>Three</h2>
        """

        blocks = parser.extract_xhtml_blocks(xhtml)

        indices = [b.index for b in blocks]
        assert indices == [0, 1, 2]

    # ===== Markdown Parsing Tests =====

    def test_extract_markdown_blocks_finds_headings(self, parser):
        """extract_markdown_blocks should find ATX headings."""
        markdown = """# Title

## Section

### Subsection

Regular text
"""

        blocks = parser.extract_markdown_blocks(markdown)

        headings = [b for b in blocks if b.block_type == BlockType.HEADING]
        assert len(headings) == 3
        assert headings[0].content == "Title"
        assert headings[0].level == 1
        assert headings[1].content == "Section"
        assert headings[1].level == 2

    def test_extract_markdown_blocks_finds_headings_with_attributes(self, parser):
        """extract_markdown_blocks should strip pandoc attributes from headings."""
        markdown = '# Title {#title local-id="abc"}\n\nContent'

        blocks = parser.extract_markdown_blocks(markdown)

        headings = [b for b in blocks if b.block_type == BlockType.HEADING]
        assert len(headings) == 1
        assert headings[0].content == "Title"
        assert "{" not in headings[0].content

    def test_extract_markdown_blocks_finds_paragraphs(self, parser):
        """extract_markdown_blocks should find paragraphs."""
        markdown = """First paragraph.

Second paragraph
that spans multiple lines.

Third paragraph.
"""

        blocks = parser.extract_markdown_blocks(markdown)

        paragraphs = [b for b in blocks if b.block_type == BlockType.PARAGRAPH]
        assert len(paragraphs) == 3
        # Multi-line paragraph should be joined
        assert "spans multiple lines" in paragraphs[1].content

    def test_extract_markdown_blocks_finds_pipe_tables(self, parser):
        """extract_markdown_blocks should find pipe-delimited tables."""
        markdown = """| Col1 | Col2 |
|------|------|
| A    | B    |
| C    | D    |
"""

        blocks = parser.extract_markdown_blocks(markdown)

        tables = [b for b in blocks if b.block_type == BlockType.TABLE]
        assert len(tables) == 1
        assert tables[0].rows[0] == ['Col1', 'Col2']

    def test_extract_markdown_blocks_finds_simple_tables(self, parser):
        """extract_markdown_blocks should find pandoc simple tables."""
        markdown = """  --------- ---------
  **ABC**   **DEF**
  1         2
  --------- ---------
"""

        blocks = parser.extract_markdown_blocks(markdown)

        tables = [b for b in blocks if b.block_type == BlockType.TABLE]
        assert len(tables) == 1
        # Should extract rows (may have formatting artifacts)
        assert len(tables[0].rows) >= 2

    def test_extract_markdown_blocks_finds_simple_tables_header_first(self, parser):
        """extract_markdown_blocks should find simple tables when header comes before separator."""
        # Pandoc simple table format: header row, then separator, then data
        markdown = """Role         Name        Expectations
-----------  ----------  -------------
Developer    John        Build features
Tester       Jane        Write tests
"""

        blocks = parser.extract_markdown_blocks(markdown)

        tables = [b for b in blocks if b.block_type == BlockType.TABLE]
        assert len(tables) == 1
        # Should correctly parse columns
        assert tables[0].rows[0] == ['Role', 'Name', 'Expectations']
        assert tables[0].rows[1] == ['Developer', 'John', 'Build features']
        assert tables[0].rows[2] == ['Tester', 'Jane', 'Write tests']

    def test_extract_markdown_blocks_finds_lists(self, parser):
        """extract_markdown_blocks should find individual list items."""
        markdown = """- Item 1
- Item 2
- Item 3

1. First
2. Second
"""

        blocks = parser.extract_markdown_blocks(markdown)

        lists = [b for b in blocks if b.block_type == BlockType.LIST]
        # Each list item is now extracted as a separate block
        assert len(lists) == 5
        contents = [b.content for b in lists]
        assert "Item 1" in contents
        assert "Item 2" in contents
        assert "Item 3" in contents
        assert "First" in contents
        assert "Second" in contents

    def test_extract_markdown_blocks_finds_code_blocks(self, parser):
        """extract_markdown_blocks should find fenced code blocks."""
        markdown = """```python
def hello():
    print("world")
```

Some text
"""

        blocks = parser.extract_markdown_blocks(markdown)

        code = [b for b in blocks if b.block_type == BlockType.CODE]
        assert len(code) == 1
        assert "def hello" in code[0].content

    def test_extract_markdown_blocks_finds_macro_placeholders(self, parser):
        """extract_markdown_blocks should find macro placeholders."""
        markdown = """CONFLUENCE_MACRO_PLACEHOLDER_0

# Title

CONFLUENCE_MACRO_PLACEHOLDER_1
"""

        blocks = parser.extract_markdown_blocks(markdown)

        macros = [b for b in blocks if b.block_type == BlockType.MACRO]
        assert len(macros) == 2

    def test_extract_markdown_blocks_assigns_indices(self, parser):
        """extract_markdown_blocks should assign sequential indices."""
        markdown = """# One

Two

# Three
"""

        blocks = parser.extract_markdown_blocks(markdown)

        indices = [b.index for b in blocks]
        assert indices == sorted(indices)

    # ===== Table Parsing Edge Cases =====

    def test_parse_markdown_table_handles_empty_cells(self, parser):
        """_parse_markdown_table should handle empty cells."""
        lines = [
            "| A |   | C |",
            "|---|---|---|",
            "| 1 |   | 3 |",
        ]

        rows = parser._parse_markdown_table(lines)

        assert len(rows) == 2
        # Empty cells should be preserved
        assert rows[0] == ['A', 'C'] or rows[0] == ['A', '', 'C']

    def test_parse_simple_table_handles_varied_widths(self, parser):
        """_parse_simple_table should handle varied column widths."""
        lines = [
            "  -------- ----------",
            "  Short    Longer text",
            "  A        B",
            "  -------- ----------",
        ]

        rows = parser._parse_simple_table(lines)

        assert len(rows) >= 2

    # ===== Block Type Detection Tests =====

    def test_xhtml_code_block_detection(self, parser):
        """Should detect pre and code tags as code blocks."""
        xhtml = """
        <pre><code>function foo() {}</code></pre>
        <code>inline code</code>
        """

        blocks = parser.extract_xhtml_blocks(xhtml)

        code_blocks = [b for b in blocks if b.block_type == BlockType.CODE]
        assert len(code_blocks) >= 1

    def test_empty_content_handling(self, parser):
        """Should handle empty or whitespace-only content."""
        xhtml = "<p>   </p><p></p>"
        markdown = "\n\n   \n\n"

        xhtml_blocks = parser.extract_xhtml_blocks(xhtml)
        md_blocks = parser.extract_markdown_blocks(markdown)

        # Empty content should be skipped
        assert len(xhtml_blocks) == 0
        assert len(md_blocks) == 0
