"""Unit tests for MacroPreserver test helper.

NOTE: MacroPreserver is a TEST HELPER, not production code. It tests the
OLD approach from Epic 01 (converting macros to HTML comments). Production
code uses surgical updates that never touch ac: elements.
"""

from bs4 import BeautifulSoup
from tests.helpers.macro_test_utils import MacroPreserver


class TestMacroPreserver:
    """Test cases for MacroPreserver test helper."""

    def test_detect_macros_finds_ac_elements(self):
        """detect_macros should find all ac: namespace elements."""
        preserver = MacroPreserver()
        xhtml = '''
            <p>Regular content</p>
            <ac:structured-macro ac:name="info">
                <ac:rich-text-body>Info content</ac:rich-text-body>
            </ac:structured-macro>
        '''
        soup = BeautifulSoup(xhtml, 'lxml')

        macros = preserver.detect_macros(soup)

        assert len(macros) == 2  # structured-macro + rich-text-body
        assert all(tag.name.startswith('ac:') for tag in macros)

    def test_detect_macros_returns_empty_when_no_macros(self):
        """detect_macros should return empty list when no macros present."""
        preserver = MacroPreserver()
        xhtml = '<p>Just regular HTML</p>'
        soup = BeautifulSoup(xhtml, 'lxml')

        macros = preserver.detect_macros(soup)

        assert macros == []

    def test_preserve_as_comments_converts_macros(self):
        """preserve_as_comments should convert ac: elements to HTML comments."""
        preserver = MacroPreserver()
        xhtml = '<p>Text <ac:structured-macro ac:name="info"><ac:rich-text-body>Note</ac:rich-text-body></ac:structured-macro> more text</p>'
        soup = BeautifulSoup(xhtml, 'lxml')

        result = preserver.preserve_as_comments(soup)

        result_str = str(result)
        assert '<!-- CONFLUENCE_MACRO:' in result_str
        assert 'ac:structured-macro' in result_str
        assert '-->' in result_str

    def test_preserve_as_comments_removes_ac_elements(self):
        """preserve_as_comments should remove ac: elements from the tree."""
        preserver = MacroPreserver()
        xhtml = '<p><ac:structured-macro ac:name="info"><ac:rich-text-body>Note</ac:rich-text-body></ac:structured-macro></p>'
        soup = BeautifulSoup(xhtml, 'lxml')

        result = preserver.preserve_as_comments(soup)

        # No ac: elements should remain in the tree
        remaining_macros = result.find_all(lambda tag: tag.name.startswith('ac:'))
        assert remaining_macros == []

    def test_preserve_as_comments_preserves_macro_attributes(self):
        """preserve_as_comments should preserve macro attributes in comments."""
        preserver = MacroPreserver()
        xhtml = '<p><ac:structured-macro ac:name="code" ac:schema-version="1"><ac:parameter ac:name="language">python</ac:parameter></ac:structured-macro></p>'
        soup = BeautifulSoup(xhtml, 'lxml')

        result = preserver.preserve_as_comments(soup)

        result_str = str(result)
        assert 'ac:name="code"' in result_str
        assert 'ac:schema-version="1"' in result_str
        assert 'ac:name="language"' in result_str

    def test_restore_from_comments_restores_macros(self):
        """restore_from_comments should restore macros from HTML comments."""
        preserver = MacroPreserver()
        # First create a macro, preserve it, then restore it
        xhtml = '<p><ac:structured-macro ac:name="info"><ac:rich-text-body>Note</ac:rich-text-body></ac:structured-macro></p>'
        soup = BeautifulSoup(xhtml, 'lxml')
        preserved = preserver.preserve_as_comments(soup)
        html_with_comments = str(preserved)

        result = preserver.restore_from_comments(html_with_comments)

        assert '<ac:structured-macro' in result or 'ac:structured-macro' in result
        assert 'ac:name="info"' in result

    def test_restore_from_comments_ignores_regular_comments(self):
        """restore_from_comments should ignore regular HTML comments."""
        preserver = MacroPreserver()
        html_with_comments = '<p>Text <!-- This is a regular comment --> more text</p>'

        result = preserver.restore_from_comments(html_with_comments)

        # Regular comments should remain
        assert 'regular comment' in result or '<!--' in result

    def test_round_trip_preservation(self):
        """Macros should survive preserve_as_comments -> restore_from_comments round trip."""
        preserver = MacroPreserver()
        original_xhtml = '<p>Text <ac:structured-macro ac:name="info"><ac:parameter ac:name="title">Important</ac:parameter><ac:rich-text-body>Note content</ac:rich-text-body></ac:structured-macro> more text</p>'
        soup = BeautifulSoup(original_xhtml, 'lxml')

        # Preserve as comments
        preserved_soup = preserver.preserve_as_comments(soup)
        preserved_html = str(preserved_soup)

        # Restore from comments
        restored_html = preserver.restore_from_comments(preserved_html)

        # Verify macro elements are back
        assert '<ac:structured-macro' in restored_html
        assert 'ac:name="info"' in restored_html
        assert '<ac:parameter' in restored_html
        assert 'ac:name="title"' in restored_html
        assert '<ac:rich-text-body>' in restored_html

    def test_get_macro_types_counts_macros(self):
        """get_macro_types should count occurrences of each macro type."""
        preserver = MacroPreserver()
        xhtml = '''
            <p>Content</p>
            <ac:structured-macro ac:name="info">
                <ac:rich-text-body>Info 1</ac:rich-text-body>
            </ac:structured-macro>
            <ac:structured-macro ac:name="warning">
                <ac:rich-text-body>Warning</ac:rich-text-body>
            </ac:structured-macro>
            <ac:structured-macro ac:name="info">
                <ac:rich-text-body>Info 2</ac:rich-text-body>
            </ac:structured-macro>
        '''
        soup = BeautifulSoup(xhtml, 'lxml')

        counts = preserver.get_macro_types(soup)

        assert counts['ac:structured-macro'] == 3
        assert counts['ac:rich-text-body'] == 3

    def test_get_macro_types_returns_empty_dict_when_no_macros(self):
        """get_macro_types should return empty dict when no macros present."""
        preserver = MacroPreserver()
        xhtml = '<p>Just regular HTML</p>'
        soup = BeautifulSoup(xhtml, 'lxml')

        counts = preserver.get_macro_types(soup)

        assert counts == {}

    def test_preserve_as_comments_handles_nested_macros(self):
        """preserve_as_comments should handle nested macro structures."""
        preserver = MacroPreserver()
        xhtml = '''
            <ac:structured-macro ac:name="panel">
                <ac:rich-text-body>
                    <p>Text with nested <ac:link><ri:page ri:content-title="Other Page"/></ac:link></p>
                </ac:rich-text-body>
            </ac:structured-macro>
        '''
        soup = BeautifulSoup(xhtml, 'lxml')

        result = preserver.preserve_as_comments(soup)

        # All ac: elements should be converted to comments
        remaining_macros = result.find_all(lambda tag: tag.name.startswith('ac:'))
        assert remaining_macros == []

        # Result should contain comments with preserved macros
        result_str = str(result)
        assert '<!-- CONFLUENCE_MACRO:' in result_str
