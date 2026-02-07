"""Unit tests for BeautifulSoup parser security in SurgicalEditor.

Tests M3: BeautifulSoup XXE risk - switching to html.parser to prevent
XML External Entity (XXE) attacks.
"""

import pytest
from bs4 import BeautifulSoup

from src.page_operations.surgical_editor import SurgicalEditor
from src.page_operations.models import SurgicalOperation, OperationType


class TestParserSecurity:
    """Test cases for parser security (M3)."""

    @pytest.fixture
    def editor(self):
        """Create a SurgicalEditor instance."""
        return SurgicalEditor()

    def test_parser_is_html_parser(self, editor):
        """Verify editor uses html.parser instead of lxml (CRITICAL TEST)."""
        assert editor.parser == "html.parser"
        assert editor.parser != "lxml"

    def test_xxe_attack_prevented(self, editor):
        """Verify XXE attacks are prevented with html.parser."""
        # Attempt XXE attack with external entity
        xxe_payload = """<?xml version="1.0"?>
<!DOCTYPE foo [
<!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<p>&xxe;</p>
"""
        # html.parser should treat this as text, not execute the entity
        soup = BeautifulSoup(xxe_payload, editor.parser)

        # The payload should be treated as text, not executed
        content = str(soup)

        # Should NOT contain actual file contents (would appear if XXE succeeded)
        assert "root:" not in content
        assert "/bin/bash" not in content
        assert "/bin/sh" not in content

        # Entity should be escaped, not expanded
        # html.parser will escape & to &amp; preventing entity expansion
        assert "&amp;xxe" in content or "xxe" not in content

    def test_billion_laughs_attack_prevented(self, editor):
        """Verify billion laughs (entity expansion bomb) is prevented."""
        # Billion laughs attack - recursive entity expansion
        billion_laughs = """<?xml version="1.0"?>
<!DOCTYPE lolz [
<!ENTITY lol "lol">
<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<p>&lol3;</p>
"""
        # Should not cause exponential memory usage
        soup = BeautifulSoup(billion_laughs, editor.parser)
        content = str(soup)

        # Entity expansion should not occur with html.parser
        assert len(content) < 10000  # Should not expand to huge size

    def test_basic_html_parsing_works(self, editor):
        """Verify basic HTML parsing still works correctly."""
        html = "<div><p>Hello <strong>world</strong></p></div>"
        soup = BeautifulSoup(html, editor.parser)

        # Should parse correctly
        assert soup.find('p') is not None
        assert soup.find('strong') is not None
        assert "Hello" in soup.get_text()
        assert "world" in soup.get_text()

    def test_confluence_macros_parsed_correctly(self, editor):
        """Verify Confluence macros (ac: namespace) are parsed correctly."""
        xhtml = """<ac:structured-macro ac:name="info">
  <ac:rich-text-body>
    <p>This is an info macro</p>
  </ac:rich-text-body>
</ac:structured-macro>"""

        soup = BeautifulSoup(xhtml, editor.parser)

        # Should find the macro
        macro = soup.find('ac:structured-macro')
        assert macro is not None
        assert macro.get('ac:name') == 'info'

    def test_surgical_operations_work_with_new_parser(self, editor):
        """Verify surgical operations work correctly with html.parser."""
        xhtml = "<p>Original text</p>"
        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Original text",
                new_content="Updated text"
            )
        ]

        result, success, failure = editor.apply_operations(xhtml, operations)

        # Should successfully update text
        assert success == 1
        assert failure == 0
        assert "Updated text" in result
        assert "Original text" not in result

    def test_table_operations_work_with_new_parser(self, editor):
        """Verify table operations work with html.parser."""
        xhtml = """<table>
  <tr><th>Header</th></tr>
  <tr><td>Data</td></tr>
</table>"""

        soup = BeautifulSoup(xhtml, editor.parser)

        # Should parse table correctly
        table = soup.find('table')
        assert table is not None
        rows = table.find_all('tr')
        assert len(rows) == 2

    def test_nested_elements_parsed_correctly(self, editor):
        """Verify deeply nested elements are parsed correctly."""
        xhtml = "<div><div><div><p>Nested <em>content</em></p></div></div></div>"
        soup = BeautifulSoup(xhtml, editor.parser)

        # Should parse nested structure correctly
        p = soup.find('p')
        assert p is not None
        em = p.find('em')
        assert em is not None
        assert em.get_text() == 'content'

    def test_malformed_html_handled_gracefully(self, editor):
        """Verify malformed HTML is handled gracefully."""
        # Unclosed tags and other malformations
        malformed = "<p>Unclosed paragraph<div>Mismatched</p></div>"

        # Should not raise exception
        soup = BeautifulSoup(malformed, editor.parser)
        assert soup is not None

    def test_special_characters_preserved(self, editor):
        """Verify special characters are preserved correctly."""
        xhtml = "<p>Special: &lt; &gt; &amp; &quot; &#39;</p>"
        soup = BeautifulSoup(xhtml, editor.parser)

        # Should preserve entity encoding
        content = str(soup)
        assert "&lt;" in content or "<" in soup.get_text()
        assert "&gt;" in content or ">" in soup.get_text()

    def test_no_external_resource_loading(self, editor):
        """Verify parser doesn't attempt to load external resources."""
        # HTML with external resource references
        xhtml = """<p>Test</p>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">"""

        # Should parse without attempting network access
        # html.parser won't try to fetch the DTD
        soup = BeautifulSoup(xhtml, editor.parser)
        assert soup.find('p') is not None
        assert "Test" in soup.get_text()

    def test_parser_performance_acceptable(self, editor):
        """Verify html.parser performance is acceptable for typical content."""
        # Create moderately large HTML
        large_html = "<div>" + "<p>Paragraph</p>" * 1000 + "</div>"

        # Should parse in reasonable time (< 1 second typically)
        import time
        start = time.time()
        soup = BeautifulSoup(large_html, editor.parser)
        duration = time.time() - start

        # Should complete quickly
        assert duration < 5.0  # Very generous timeout
        assert soup.find('p') is not None
