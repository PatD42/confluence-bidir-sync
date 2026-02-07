"""Unit tests for production MacroPreserver.

Tests the MacroPreserver class in src/page_operations/macro_preserver.py
which handles preservation of Confluence macros during content conversion,
with special handling for inline comment markers.
"""

import pytest

from src.page_operations.macro_preserver import MacroPreserver, MacroInfo


class TestMacroPreserverInlineComments:
    """Test cases for inline comment handling."""

    @pytest.fixture
    def preserver(self):
        """Create a MacroPreserver instance."""
        return MacroPreserver()

    def test_preserve_inline_comment_extracts_text(self, preserver):
        """Inline comment markers should have their text preserved, not replaced with placeholder."""
        xhtml = '<p>Some <ac:inline-comment-marker ac:ref="abc123">commented text</ac:inline-comment-marker> here</p>'

        result, macros = preserver.preserve_macros(xhtml)

        # Text should be preserved in output
        assert "commented text" in result
        # Should NOT have placeholder in output
        assert "INLINE_COMMENT" not in result
        # Marker should be stored for reference
        assert len(macros) == 1
        assert macros[0].macro_type == "inline-comment"
        assert macros[0].text == "commented text"
        assert macros[0].ref == "abc123"

    def test_preserve_multiple_inline_comments(self, preserver):
        """Multiple inline comments should all have their text preserved."""
        xhtml = '''<p>
            <ac:inline-comment-marker ac:ref="ref1">first comment</ac:inline-comment-marker>
            and
            <ac:inline-comment-marker ac:ref="ref2">second comment</ac:inline-comment-marker>
        </p>'''

        result, macros = preserver.preserve_macros(xhtml)

        assert "first comment" in result
        assert "second comment" in result
        assert len(macros) == 2
        assert all(m.macro_type == "inline-comment" for m in macros)

    def test_count_inline_comments(self, preserver):
        """count_inline_comments should count ac:inline-comment-marker elements."""
        xhtml = '''<p>
            <ac:inline-comment-marker ac:ref="ref1">text1</ac:inline-comment-marker>
            <ac:inline-comment-marker ac:ref="ref2">text2</ac:inline-comment-marker>
        </p>'''

        count = preserver.count_inline_comments(xhtml)

        assert count == 2

    def test_count_inline_comments_returns_zero_when_none(self, preserver):
        """count_inline_comments should return 0 when no markers present."""
        xhtml = "<p>Regular paragraph without comments</p>"

        count = preserver.count_inline_comments(xhtml)

        assert count == 0

    def test_extract_inline_comments(self, preserver):
        """extract_inline_comments should return ref and text for each marker."""
        xhtml = '''<p>
            <ac:inline-comment-marker ac:ref="abc">first</ac:inline-comment-marker>
            <ac:inline-comment-marker ac:ref="def">second</ac:inline-comment-marker>
        </p>'''

        comments = preserver.extract_inline_comments(xhtml)

        assert len(comments) == 2
        assert comments[0]["ref"] == "abc"
        assert comments[0]["text"] == "first"
        assert comments[1]["ref"] == "def"
        assert comments[1]["text"] == "second"


class TestMacroPreserverBlockMacros:
    """Test cases for block macro handling."""

    @pytest.fixture
    def preserver(self):
        """Create a MacroPreserver instance."""
        return MacroPreserver()

    def test_preserve_block_macro_as_placeholder(self, preserver):
        """Block macros should be replaced with HTML comment placeholders."""
        xhtml = '''<p>Text</p>
            <ac:structured-macro ac:name="info">
                <ac:rich-text-body>Info content</ac:rich-text-body>
            </ac:structured-macro>'''

        result, macros = preserver.preserve_macros(xhtml)

        # Should have placeholder in output
        assert "CONFLUENCE_MACRO_PLACEHOLDER" in result
        # Should NOT have ac: elements in output
        assert "<ac:structured-macro" not in result
        # Macro info should be stored
        block_macros = [m for m in macros if m.macro_type == "block-macro"]
        assert len(block_macros) == 1
        assert "ac:structured-macro" in block_macros[0].html

    def test_restore_block_macro_from_placeholder(self, preserver):
        """Block macros should be restored from placeholders."""
        xhtml = '<p>Text</p><ac:structured-macro ac:name="info"><ac:rich-text-body>Content</ac:rich-text-body></ac:structured-macro>'

        # Preserve
        preserved, macros = preserver.preserve_macros(xhtml)

        # Restore
        restored = preserver.restore_macros(preserved, macros)

        assert "<ac:structured-macro" in restored
        assert 'ac:name="info"' in restored
        assert "<ac:rich-text-body>" in restored

    def test_restore_skips_inline_comments(self, preserver):
        """Inline comment markers should NOT be restored (text may have been edited)."""
        xhtml = '<p><ac:inline-comment-marker ac:ref="abc">text</ac:inline-comment-marker></p>'

        # Preserve
        preserved, macros = preserver.preserve_macros(xhtml)

        # Modify the text (simulating user edit)
        modified = preserved.replace("text", "modified text")

        # Restore
        restored = preserver.restore_macros(modified, macros)

        # Should NOT have the original marker restored
        assert "ac:inline-comment-marker" not in restored
        # Should have the modified text
        assert "modified text" in restored


class TestMacroPreserverMixedContent:
    """Test cases for mixed content with both inline comments and block macros."""

    @pytest.fixture
    def preserver(self):
        """Create a MacroPreserver instance."""
        return MacroPreserver()

    def test_preserve_mixed_content(self, preserver):
        """Should handle both inline comments and block macros in same content."""
        xhtml = '''<p>Text with <ac:inline-comment-marker ac:ref="ref1">inline comment</ac:inline-comment-marker></p>
            <ac:structured-macro ac:name="info">
                <ac:rich-text-body>Info content</ac:rich-text-body>
            </ac:structured-macro>'''

        result, macros = preserver.preserve_macros(xhtml)

        # Inline comment text preserved
        assert "inline comment" in result
        # Block macro replaced with placeholder
        assert "CONFLUENCE_MACRO_PLACEHOLDER" in result
        # Two macros stored
        assert len(macros) == 2
        inline_macros = [m for m in macros if m.macro_type == "inline-comment"]
        block_macros = [m for m in macros if m.macro_type == "block-macro"]
        assert len(inline_macros) == 1
        assert len(block_macros) == 1

    def test_restore_mixed_content(self, preserver):
        """Should restore block macros but not inline comments in mixed content."""
        xhtml = '''<p>Text with <ac:inline-comment-marker ac:ref="ref1">inline</ac:inline-comment-marker></p>
            <ac:structured-macro ac:name="panel">
                <ac:rich-text-body>Panel content</ac:rich-text-body>
            </ac:structured-macro>'''

        preserved, macros = preserver.preserve_macros(xhtml)
        restored = preserver.restore_macros(preserved, macros)

        # Block macro restored
        assert "<ac:structured-macro" in restored
        assert 'ac:name="panel"' in restored
        # Inline comment NOT restored (text preserved but no marker)
        assert "inline" in restored
        assert "ac:inline-comment-marker" not in restored


class TestMacroPreserverEdgeCases:
    """Test edge cases for MacroPreserver."""

    @pytest.fixture
    def preserver(self):
        """Create a MacroPreserver instance."""
        return MacroPreserver()

    def test_preserve_nested_macros(self, preserver):
        """Nested macros should be handled (only top-level replaced)."""
        xhtml = '''<ac:structured-macro ac:name="panel">
            <ac:rich-text-body>
                <ac:structured-macro ac:name="code">
                    <ac:plain-text-body>print("hello")</ac:plain-text-body>
                </ac:structured-macro>
            </ac:rich-text-body>
        </ac:structured-macro>'''

        result, macros = preserver.preserve_macros(xhtml)

        # Should only have one top-level macro stored
        block_macros = [m for m in macros if m.macro_type == "block-macro"]
        assert len(block_macros) == 1
        # The nested structure should be in the stored HTML
        assert "ac:plain-text-body" in block_macros[0].html

    def test_preserve_empty_inline_comment(self, preserver):
        """Empty inline comment marker should be handled."""
        xhtml = '<p>Before<ac:inline-comment-marker ac:ref="empty"></ac:inline-comment-marker>After</p>'

        result, macros = preserver.preserve_macros(xhtml)

        assert "Before" in result
        assert "After" in result
        assert len(macros) == 1
        assert macros[0].text == ""

    def test_preserve_no_macros(self, preserver):
        """Content without macros should pass through unchanged."""
        xhtml = "<p>Regular paragraph</p><h1>Heading</h1>"

        result, macros = preserver.preserve_macros(xhtml)

        assert "Regular paragraph" in result
        assert "Heading" in result
        assert len(macros) == 0

    def test_macro_info_dataclass(self):
        """MacroInfo dataclass should store all fields correctly."""
        info = MacroInfo(
            placeholder="TEST_PLACEHOLDER",
            html="<ac:test>content</ac:test>",
            name="test-macro",
            macro_type="block-macro",
            ref="ref123",
            text="some text",
        )

        assert info.placeholder == "TEST_PLACEHOLDER"
        assert info.html == "<ac:test>content</ac:test>"
        assert info.name == "test-macro"
        assert info.macro_type == "block-macro"
        assert info.ref == "ref123"
        assert info.text == "some text"
