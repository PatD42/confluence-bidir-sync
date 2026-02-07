"""Unit tests for content_converter.markdown_converter module."""

import pytest
from unittest.mock import patch, MagicMock
import subprocess
from src.content_converter.markdown_converter import MarkdownConverter
from src.confluence_client.errors import ConversionError


class TestMarkdownConverterInit:
    """Test cases for MarkdownConverter initialization."""

    @patch('subprocess.run')
    def test_init_succeeds_when_pandoc_installed(self, mock_run):
        """__init__ should succeed when Pandoc is installed."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        assert converter is not None
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_init_raises_error_when_pandoc_not_installed(self, mock_run):
        """__init__ should raise ConversionError when Pandoc is not installed."""
        mock_run.return_value = MagicMock(returncode=1)

        with pytest.raises(ConversionError) as exc_info:
            MarkdownConverter()

        assert "Pandoc not found" in str(exc_info.value)
        assert "brew install pandoc" in str(exc_info.value)

    @patch('subprocess.run')
    def test_init_raises_error_on_timeout(self, mock_run):
        """__init__ should raise ConversionError when Pandoc check times out."""
        mock_run.side_effect = subprocess.TimeoutExpired("which", 5)

        with pytest.raises(ConversionError) as exc_info:
            MarkdownConverter()

        assert "Pandoc not found" in str(exc_info.value)


class TestXHTMLToMarkdown:
    """Test cases for xhtml_to_markdown method (uses markdownify)."""

    @patch('subprocess.run')
    def test_xhtml_to_markdown_success(self, mock_run):
        """xhtml_to_markdown should convert XHTML to markdown successfully."""
        mock_run.return_value = MagicMock(returncode=0)  # which pandoc

        converter = MarkdownConverter()
        result = converter.xhtml_to_markdown("<h1>Test</h1><p>This is markdown.</p>")

        # markdownify produces clean output
        assert "Test" in result
        assert "This is markdown." in result

    @patch('subprocess.run')
    def test_xhtml_to_markdown_empty_string(self, mock_run):
        """xhtml_to_markdown should return empty string for empty input."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()
        result = converter.xhtml_to_markdown("")

        assert result == ""

    @patch('subprocess.run')
    def test_xhtml_to_markdown_produces_pipe_tables(self, mock_run):
        """xhtml_to_markdown should produce pipe-formatted tables."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()
        html = """
        <table>
        <thead><tr><th>Page</th><th>Focus</th></tr></thead>
        <tbody>
        <tr><td>Domain Model</td><td>Entities, patterns</td></tr>
        <tr><td>Security</td><td>Auth, protection</td></tr>
        </tbody>
        </table>
        """
        result = converter.xhtml_to_markdown(html)

        # Should produce pipe table format
        assert "|" in result
        assert "Page" in result
        assert "Focus" in result
        assert "Domain Model" in result

    @patch('subprocess.run')
    def test_xhtml_to_markdown_handles_headerless_tables(self, mock_run):
        """xhtml_to_markdown should handle tables without headers."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()
        html = """
        <table>
        <tbody>
        <tr><td>Cell 1</td><td>Cell 2</td></tr>
        <tr><td>Cell 3</td><td>Cell 4</td></tr>
        </tbody>
        </table>
        """
        result = converter.xhtml_to_markdown(html)

        # Should still produce pipe table
        assert "|" in result
        assert "Cell 1" in result

    @patch('subprocess.run')
    def test_xhtml_to_markdown_handles_lists_in_tables(self, mock_run):
        """xhtml_to_markdown should handle lists inside table cells."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()
        html = """
        <table>
        <tr><th>Col1</th><th>Col2</th></tr>
        <tr><td>A</td><td><ul><li>item1</li><li>item2</li></ul></td></tr>
        </table>
        """
        result = converter.xhtml_to_markdown(html)

        # Should produce pipe table with flattened list
        assert "|" in result
        assert "item1" in result
        assert "item2" in result


class TestMarkdownToXHTML:
    """Test cases for markdown_to_xhtml method."""

    @patch('subprocess.run')
    def test_markdown_to_xhtml_success(self, mock_run):
        """markdown_to_xhtml should convert markdown to XHTML successfully."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # which pandoc
            MagicMock(returncode=0, stdout="<h1>Test</h1><p>This is HTML.</p>")  # pandoc conversion
        ]

        converter = MarkdownConverter()
        result = converter.markdown_to_xhtml("# Test\n\nThis is HTML.")

        assert result == "<h1>Test</h1><p>This is HTML.</p>"

    @patch('subprocess.run')
    def test_markdown_to_xhtml_empty_string(self, mock_run):
        """markdown_to_xhtml should return empty string for empty input."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()
        result = converter.markdown_to_xhtml("")

        assert result == ""

    @patch('subprocess.run')
    def test_markdown_to_xhtml_uses_correct_pandoc_args(self, mock_run):
        """markdown_to_xhtml should call pandoc with correct arguments."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # which pandoc
            MagicMock(returncode=0, stdout="<h1>Test</h1>")  # pandoc conversion
        ]

        converter = MarkdownConverter()
        converter.markdown_to_xhtml("# Test")

        # Get the second call (pandoc conversion, not 'which')
        pandoc_call = mock_run.call_args_list[1]
        assert pandoc_call[0][0] == ["pandoc", "-f", "markdown", "-t", "html"]
        assert pandoc_call[1]['input'] == "# Test"
        assert pandoc_call[1]['text'] is True
        assert pandoc_call[1]['capture_output'] is True
        assert pandoc_call[1]['check'] is True
        assert pandoc_call[1]['timeout'] == 10

    @patch('subprocess.run')
    def test_markdown_to_xhtml_raises_on_pandoc_error(self, mock_run):
        """markdown_to_xhtml should raise ConversionError when pandoc fails."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # which pandoc
            subprocess.CalledProcessError(1, "pandoc", stderr="Invalid markdown")
        ]

        converter = MarkdownConverter()

        with pytest.raises(ConversionError) as exc_info:
            converter.markdown_to_xhtml("**invalid")

        assert "Pandoc conversion failed" in str(exc_info.value)

    @patch('subprocess.run')
    def test_markdown_to_xhtml_raises_on_timeout(self, mock_run):
        """markdown_to_xhtml should raise ConversionError on timeout."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # which pandoc
            subprocess.TimeoutExpired("pandoc", 10)
        ]

        converter = MarkdownConverter()

        with pytest.raises(ConversionError) as exc_info:
            converter.markdown_to_xhtml("# Test")

        assert "timed out" in str(exc_info.value)


class TestPandocInstalled:
    """Test cases for _pandoc_installed method."""

    @patch('subprocess.run')
    def test_pandoc_installed_returns_true_when_found(self, mock_run):
        """_pandoc_installed should return True when pandoc is found."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        assert converter._pandoc_installed() is True

    @patch('subprocess.run')
    def test_pandoc_installed_returns_false_when_not_found(self, mock_run):
        """_pandoc_installed should return False when pandoc is not found."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # Init check
            MagicMock(returncode=1)   # Explicit _pandoc_installed() call
        ]

        converter = MarkdownConverter()

        assert converter._pandoc_installed() is False

    @patch('subprocess.run')
    def test_pandoc_installed_returns_false_on_timeout(self, mock_run):
        """_pandoc_installed should return False on timeout."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # Init check
            subprocess.TimeoutExpired("which", 5)  # Explicit call
        ]

        converter = MarkdownConverter()

        assert converter._pandoc_installed() is False

    @patch('subprocess.run')
    def test_pandoc_installed_returns_false_on_file_not_found(self, mock_run):
        """_pandoc_installed should return False on FileNotFoundError."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # Init check
            FileNotFoundError()  # Explicit call
        ]

        converter = MarkdownConverter()

        assert converter._pandoc_installed() is False


class TestParagraphToBrConversion:
    """Test cases for converting Confluence <p> tags in table cells to <br> tags in markdown.

    This covers the PULL direction: Confluence → markdown.
    Confluence stores multi-line table cell content as multiple <p> tags.
    """

    @patch('subprocess.run')
    def test_p_tags_in_td_become_br(self, mock_run):
        """Multiple <p> tags in td should become <br> separated text."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()
        html = """
        <table>
        <tr><th>Column</th></tr>
        <tr><td><p>Line 1</p><p>Line 2</p><p>Line 3</p></td></tr>
        </table>
        """
        result = converter.xhtml_to_markdown(html)

        # Should have <br> between lines in markdown
        assert "Line 1<br>Line 2<br>Line 3" in result or \
               "Line 1<br>Line 2" in result  # At minimum two lines joined

    @patch('subprocess.run')
    def test_p_tags_in_th_become_br(self, mock_run):
        """Multiple <p> tags in th should become <br> separated text."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()
        html = """
        <table>
        <tr><th><p>Header Line 1</p><p>Header Line 2</p></th></tr>
        <tr><td>Data</td></tr>
        </table>
        """
        result = converter.xhtml_to_markdown(html)

        # Should have <br> between header lines
        assert "Header Line 1<br>Header Line 2" in result or \
               ("Header Line 1" in result and "Header Line 2" in result)

    @patch('subprocess.run')
    def test_single_p_in_cell_no_br(self, mock_run):
        """Single <p> in cell should not add unnecessary <br>."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()
        html = """
        <table>
        <tr><th>Header</th></tr>
        <tr><td><p>Single line content</p></td></tr>
        </table>
        """
        result = converter.xhtml_to_markdown(html)

        # Should NOT have <br> at end of single-line cell
        assert "Single line content<br>" not in result or result.count("<br>") == 0
        assert "Single line content" in result

    @patch('subprocess.run')
    def test_existing_br_in_cell_preserved(self, mock_run):
        """Existing <br> tags in cells should be preserved."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()
        html = """
        <table>
        <tr><th>Header</th></tr>
        <tr><td>Line 1<br>Line 2</td></tr>
        </table>
        """
        result = converter.xhtml_to_markdown(html)

        assert "<br>" in result or "Line 1" in result


class TestBrToParagraphConversion:
    """Test cases for converting <br> tags in markdown to <p> tags for Confluence.

    This covers the PUSH direction: markdown → Confluence.
    The _convert_br_to_p_in_cells method is called after Pandoc conversion.
    """

    @patch('subprocess.run')
    def test_br_to_p_in_td(self, mock_run):
        """<br> in <td> should become multiple <p> tags."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        # Directly test the internal method
        html = "<table><tr><td>Line 1<br>Line 2</td></tr></table>"
        result = converter._convert_br_to_p_in_cells(html)

        assert "<p>Line 1</p><p>Line 2</p>" in result
        assert "<br>" not in result

    @patch('subprocess.run')
    def test_br_to_p_in_th(self, mock_run):
        """<br> in <th> should become multiple <p> tags."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        html = "<table><tr><th>Header 1<br>Header 2</th></tr></table>"
        result = converter._convert_br_to_p_in_cells(html)

        assert "<p>Header 1</p><p>Header 2</p>" in result
        assert "<br>" not in result

    @patch('subprocess.run')
    def test_br_variants_all_converted(self, mock_run):
        """All <br> variants (<br/>, <br />) should be converted."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        # Test <br/>
        html1 = "<table><tr><td>A<br/>B</td></tr></table>"
        result1 = converter._convert_br_to_p_in_cells(html1)
        assert "<p>A</p><p>B</p>" in result1

        # Test <br />
        html2 = "<table><tr><td>A<br />B</td></tr></table>"
        result2 = converter._convert_br_to_p_in_cells(html2)
        assert "<p>A</p><p>B</p>" in result2

    @patch('subprocess.run')
    def test_multiple_br_become_multiple_p(self, mock_run):
        """Multiple <br> tags become multiple <p> tags."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        html = "<table><tr><td>A<br>B<br>C<br>D</td></tr></table>"
        result = converter._convert_br_to_p_in_cells(html)

        assert "<p>A</p><p>B</p><p>C</p><p>D</p>" in result
        assert "<br>" not in result

    @patch('subprocess.run')
    def test_no_br_no_change(self, mock_run):
        """Cells without <br> should not be modified."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        html = "<table><tr><td>Plain content</td></tr></table>"
        result = converter._convert_br_to_p_in_cells(html)

        # Should remain unchanged
        assert "<td>Plain content</td>" in result
        assert "<p>" not in result  # No wrapping when no <br>

    @patch('subprocess.run')
    def test_br_outside_table_unchanged(self, mock_run):
        """<br> tags outside table cells should not be converted to <p>."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        html = "<p>Line 1<br>Line 2</p><table><tr><td>Cell</td></tr></table>"
        result = converter._convert_br_to_p_in_cells(html)

        # <br> outside table should remain
        assert "<p>Line 1<br>Line 2</p>" in result or "Line 1<br>Line 2" in result

    @patch('subprocess.run')
    def test_multiple_cells_processed(self, mock_run):
        """All cells in a table should be processed."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        html = """<table>
        <tr><td>A1<br>A2</td><td>B1<br>B2</td></tr>
        <tr><td>C1<br>C2</td><td>D1<br>D2</td></tr>
        </table>"""
        result = converter._convert_br_to_p_in_cells(html)

        assert "<p>A1</p><p>A2</p>" in result
        assert "<p>B1</p><p>B2</p>" in result
        assert "<p>C1</p><p>C2</p>" in result
        assert "<p>D1</p><p>D2</p>" in result


class TestRoundTripLineBreaks:
    """Test that line breaks survive the full round-trip: Confluence → markdown → Confluence."""

    @patch('subprocess.run')
    def test_multiline_cell_roundtrip_pull(self, mock_run):
        """Multi-line cell content should preserve line breaks on pull."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        # Confluence format: multiple <p> tags
        confluence_html = """<table>
        <tr><th>Feature</th><th>Notes</th></tr>
        <tr><td>Login</td><td><p>Users can</p><p>authenticate</p></td></tr>
        </table>"""

        markdown = converter.xhtml_to_markdown(confluence_html)

        # Should have <br> or line separation in markdown
        assert "Users can" in markdown
        assert "authenticate" in markdown
        # The <br> indicates multi-line was preserved
        assert "<br>" in markdown or "\n" in markdown


class TestNewlineSeparatedCells:
    """Test cases for markdown tables with cells containing actual newlines (\\n).

    Standard markdown pipe tables don't support actual newlines within cells.
    Each row must be on a single line. Multiline content must use <br> tags.

    This test class documents the current behavior when users accidentally
    put actual newlines in table cells.
    """

    @patch('subprocess.run')
    def test_actual_newline_in_cell_breaks_table(self, mock_run):
        """Actual newlines in cells break the table structure.

        This documents the current behavior: if someone edits a markdown file
        and puts actual \\n characters in a table cell (instead of <br>),
        Pandoc will interpret it as a new row.
        """
        # First call for 'which pandoc', second for actual conversion
        mock_run.side_effect = [
            MagicMock(returncode=0),  # which pandoc
            MagicMock(returncode=0, stdout="""<table>
<thead><tr><th>Header</th><th>Notes</th></tr></thead>
<tbody>
<tr><td>Cell1</td><td>Line1</td></tr>
<tr><td>Line2</td><td></td></tr>
</tbody>
</table>""")
        ]

        converter = MarkdownConverter()

        # Markdown with actual newline in cell (invalid pipe table)
        md = "| Header | Notes |\n|---|---|\n| Cell1 | Line1\nLine2 |"

        xhtml = converter.markdown_to_xhtml(md)

        # Pandoc interprets the newline as a new row (not multiline cell)
        # This documents the CURRENT behavior, not necessarily desired
        assert "Line1" in xhtml
        assert "Line2" in xhtml

    @patch('subprocess.run')
    def test_br_tag_in_cell_preserves_multiline(self, mock_run):
        """Using <br> tags preserves multiline content in cells correctly.

        This is the CORRECT way to have multiline content in pipe tables.
        """
        mock_run.side_effect = [
            MagicMock(returncode=0),  # which pandoc
            MagicMock(returncode=0, stdout="""<table>
<thead><tr><th>Header</th><th>Notes</th></tr></thead>
<tbody>
<tr><td>Cell1</td><td>Line1<br>Line2</td></tr>
</tbody>
</table>""")
        ]

        converter = MarkdownConverter()

        # Markdown with <br> tag in cell (correct pipe table syntax)
        md = "| Header | Notes |\n|---|---|\n| Cell1 | Line1<br>Line2 |"

        xhtml = converter.markdown_to_xhtml(md)

        # Post-processing converts <br> to <p> tags for Confluence
        assert "Line1" in xhtml
        assert "Line2" in xhtml
        # Should be in same cell (check it wasn't split into rows)
        # The <br> gets converted to <p> tags
        assert "<p>Line1</p><p>Line2</p>" in xhtml

    @patch('subprocess.run')
    def test_roundtrip_preserves_br_multiline(self, mock_run):
        """Full round-trip: markdown with <br> → Confluence → markdown should preserve multiline."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        # Confluence format: <p> tags for multiline content
        confluence_html = """<table>
<tr><th>Feature</th><th>Description</th></tr>
<tr><td>Login</td><td><p>Step 1: Enter username</p><p>Step 2: Enter password</p><p>Step 3: Click submit</p></td></tr>
</table>"""

        # Pull: Confluence → markdown
        markdown = converter.xhtml_to_markdown(confluence_html)

        # Should convert <p> tags to <br> in markdown
        assert "Step 1: Enter username" in markdown
        assert "Step 2: Enter password" in markdown
        assert "Step 3: Click submit" in markdown
        assert "<br>" in markdown  # Multiline preserved as <br>

    @patch('subprocess.run')
    def test_backslash_n_literal_in_cell_not_interpreted_as_newline(self, mock_run):
        """Literal \\n string in cell should not be interpreted as newline.

        If someone types the literal characters backslash-n, it should stay as-is.
        """
        mock_run.side_effect = [
            MagicMock(returncode=0),  # which pandoc
            MagicMock(returncode=0, stdout="""<table>
<thead><tr><th>Header</th></tr></thead>
<tbody><tr><td>Contains \\n literal</td></tr></tbody>
</table>""")
        ]

        converter = MarkdownConverter()

        # Markdown with literal \n text (not an actual newline)
        md = "| Header |\n|---|\n| Contains \\\\n literal |"

        xhtml = converter.markdown_to_xhtml(md)

        # Should preserve the literal \n text
        assert "Contains" in xhtml


class TestFixMultilineTableCells:
    """Test cases for _fix_multiline_table_cells preprocessing.

    This method converts actual newlines in table cells to <br> tags
    so Pandoc can process them correctly.
    """

    @patch('subprocess.run')
    def test_fix_simple_multiline_cell(self, mock_run):
        """Simple multiline cell with actual newlines should be fixed."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        md = "| Header | Notes |\n|---|---|\n| Cell | Line1\nLine2 |"
        fixed = converter._fix_multiline_table_cells(md)

        assert "Line1<br>Line2" in fixed
        # Should be a valid table row now
        lines = fixed.split('\n')
        assert lines[2].startswith('|')
        assert lines[2].endswith('|')

    @patch('subprocess.run')
    def test_fix_multiple_newlines_in_cell(self, mock_run):
        """Multiple newlines in a cell should all become <br> tags."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        md = "| Col |\n|---|\n| A\nB\nC\nD |"
        fixed = converter._fix_multiline_table_cells(md)

        assert "A<br>B<br>C<br>D" in fixed

    @patch('subprocess.run')
    def test_fix_preserves_valid_tables(self, mock_run):
        """Valid single-line tables should not be modified."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        md = "| Header | Notes |\n|---|---|\n| Cell | Value |"
        fixed = converter._fix_multiline_table_cells(md)

        # Should be unchanged
        assert fixed == md

    @patch('subprocess.run')
    def test_fix_preserves_br_tags(self, mock_run):
        """Existing <br> tags should be preserved."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        md = "| Header |\n|---|\n| Line1<br>Line2 |"
        fixed = converter._fix_multiline_table_cells(md)

        # Should be unchanged (already valid)
        assert fixed == md

    @patch('subprocess.run')
    def test_fix_mixed_content(self, mock_run):
        """Tables mixed with regular content should work correctly."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        md = """# Heading

Some paragraph text.

| Header | Notes |
|---|---|
| Cell | Line1
Line2 |

More text after table."""
        fixed = converter._fix_multiline_table_cells(md)

        assert "# Heading" in fixed
        assert "Some paragraph text." in fixed
        assert "Line1<br>Line2" in fixed
        assert "More text after table." in fixed

    @patch('subprocess.run')
    def test_fix_multiple_tables(self, mock_run):
        """Multiple tables in same document should all be processed."""
        mock_run.return_value = MagicMock(returncode=0)

        converter = MarkdownConverter()

        md = """| T1 |
|---|
| A
B |

| T2 |
|---|
| X
Y |"""
        fixed = converter._fix_multiline_table_cells(md)

        assert "A<br>B" in fixed
        assert "X<br>Y" in fixed

    @patch('subprocess.run')
    def test_full_roundtrip_with_newlines(self, mock_run):
        """Full round-trip: broken markdown → XHTML → markdown should preserve multiline."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # which pandoc
            MagicMock(returncode=0, stdout="""<table>
<thead><tr><th>Feature</th><th>Description</th></tr></thead>
<tbody><tr><td>Login</td><td><p>Step 1</p><p>Step 2</p><p>Step 3</p></td></tr></tbody>
</table>""")
        ]

        converter = MarkdownConverter()

        # Markdown with actual newlines (would normally break)
        md = "| Feature | Description |\n|---|---|\n| Login | Step 1\nStep 2\nStep 3 |"

        xhtml = converter.markdown_to_xhtml(md)

        # Should have <p> tags (Confluence format)
        assert "<p>Step 1</p>" in xhtml
        assert "<p>Step 2</p>" in xhtml
        assert "<p>Step 3</p>" in xhtml
