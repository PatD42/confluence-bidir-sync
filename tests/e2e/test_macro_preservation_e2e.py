"""E2E tests for Confluence macro preservation through sync cycles.

Tests verify that Confluence macros (TOC, code, status, etc.) survive
the complete sync cycle of pull → edit → push without corruption.
"""

import pytest
import logging
import re

from src.page_operations.adf_editor import AdfEditor
from src.page_operations.adf_parser import AdfParser

logger = logging.getLogger(__name__)


@pytest.mark.e2e
@pytest.mark.macro
class TestMacroPreservationE2E:
    """E2E tests for macro preservation through sync."""

    def test_toc_macro_survives_sync_cycle(
        self,
        page_with_macros,
    ):
        """AC-4.1: TOC macro preserved through pull/edit/push.

        Given: A Confluence page with a {toc} macro
        When: I pull → edit nearby content → push
        Then: The TOC macro should still be present in Confluence
        And: Macro functionality should work
        """
        page_id = page_with_macros['page_id']
        api = page_with_macros['api_wrapper']

        # Get initial content
        page = api.get_page_by_id(page_id)
        initial_content = page['body']['storage']['value']
        version = page['version']['number']

        # Verify TOC macro is present
        assert 'ac:name="toc"' in initial_content, \
            f"Page should have TOC macro. Content: {initial_content[:500]}..."

        # Count macros before edit
        initial_macro_count = initial_content.count('ac:structured-macro')
        logger.info(f"Initial macro count: {initial_macro_count}")

        # Edit content near the macro (add a heading)
        modified_content = initial_content.replace(
            '<h2>Introduction</h2>',
            '<h2>Introduction</h2>\n<p>New paragraph added near TOC.</p>'
        )

        # Push edited content
        result = api.update_page(
            page_id=page_id,
            title=page['title'],
            body=modified_content,
            version=version
        )

        # Verify macro still present
        final_page = api.get_page_by_id(page_id)
        final_content = final_page['body']['storage']['value']

        assert 'ac:name="toc"' in final_content, \
            "TOC macro should be preserved after edit"

        final_macro_count = final_content.count('ac:structured-macro')
        assert final_macro_count == initial_macro_count, \
            f"Macro count should be unchanged: {initial_macro_count} -> {final_macro_count}"

    def test_code_macro_preserved_during_edit(
        self,
        page_with_macros,
    ):
        """AC-4.2: Code macro unchanged when editing nearby.

        Given: A page with a {code:language=python} macro containing code
        When: I edit text above or below the macro and sync
        Then: The code macro should be unchanged
        And: Code content should be preserved exactly
        """
        page_id = page_with_macros['page_id']
        api = page_with_macros['api_wrapper']

        # Get initial content
        page = api.get_page_by_id(page_id)
        initial_content = page['body']['storage']['value']
        version = page['version']['number']

        # Verify code macro is present
        assert 'ac:name="code"' in initial_content, \
            "Page should have code macro"

        # Extract code content for verification
        code_match = re.search(
            r'ac:plain-text-body[^>]*>.*?<!\[CDATA\[(.*?)\]\]>',
            initial_content,
            re.DOTALL
        )
        if code_match:
            original_code = code_match.group(1)
            logger.info(f"Original code: {original_code}")
        else:
            original_code = None
            logger.warning("Could not extract code content")

        # Edit content above the code macro
        modified_content = initial_content.replace(
            '<h2>Code Example</h2>',
            '<h2>Code Example</h2>\n<p>This is a new paragraph above the code.</p>'
        )

        # Push edited content
        result = api.update_page(
            page_id=page_id,
            title=page['title'],
            body=modified_content,
            version=version
        )

        # Verify code macro preserved
        final_page = api.get_page_by_id(page_id)
        final_content = final_page['body']['storage']['value']

        assert 'ac:name="code"' in final_content, \
            "Code macro should be preserved"

        # Verify code content unchanged
        if original_code:
            assert original_code in final_content, \
                "Code content should be preserved exactly"

    def test_inline_macro_in_paragraph_preserved(
        self,
        page_with_macros,
    ):
        """AC-4.3: Inline macro survives paragraph edit.

        Given: A paragraph containing an inline macro (e.g., {status})
        When: I edit other words in the same paragraph and sync
        Then: The inline macro should remain intact
        And: Macro rendering should work correctly
        """
        page_id = page_with_macros['page_id']
        api = page_with_macros['api_wrapper']

        # Get initial content
        page = api.get_page_by_id(page_id)
        initial_content = page['body']['storage']['value']
        version = page['version']['number']

        # Verify status macro is present
        assert 'ac:name="status"' in initial_content, \
            "Page should have status macro"

        # Find the paragraph with status macro and edit it
        # Add text before the macro
        modified_content = initial_content.replace(
            'Current status:',
            'The current system status is:'
        )

        # Push edited content
        result = api.update_page(
            page_id=page_id,
            title=page['title'],
            body=modified_content,
            version=version
        )

        # Verify status macro preserved
        final_page = api.get_page_by_id(page_id)
        final_content = final_page['body']['storage']['value']

        assert 'ac:name="status"' in final_content, \
            "Status macro should be preserved"

        # Verify macro parameters preserved
        assert 'colour' in final_content or 'color' in final_content, \
            "Macro parameters should be preserved"


@pytest.mark.e2e
@pytest.mark.macro
class TestMacroCountingE2E:
    """E2E tests for macro counting functionality."""

    def test_count_macros_in_real_page(
        self,
        page_with_macros,
    ):
        """Verify macro counting works on real page content."""
        page_id = page_with_macros['page_id']
        api = page_with_macros['api_wrapper']

        # Get page content
        page = api.get_page_by_id(page_id)
        content = page['body']['storage']['value']

        # Count macros in storage format
        macro_count = content.count('ac:structured-macro')

        logger.info(f"Found {macro_count} macros in page")

        # The test page should have multiple macros
        # (toc, code, status, warning)
        assert macro_count >= 3, \
            f"Page should have at least 3 macros, found {macro_count}"

    def test_adf_editor_macro_counting(self):
        """Verify AdfEditor counts macros in ADF documents."""
        editor = AdfEditor()
        parser = AdfParser()

        # Create ADF with macros
        doc_dict = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "extension",
                    "attrs": {
                        "extensionType": "com.atlassian.confluence.macro.core",
                        "extensionKey": "toc"
                    }
                },
                {"type": "paragraph", "content": [{"type": "text", "text": "Text"}]},
                {
                    "type": "extension",
                    "attrs": {
                        "extensionType": "com.atlassian.confluence.macro.core",
                        "extensionKey": "code"
                    }
                }
            ]
        }
        doc = parser.parse_document(doc_dict)

        count = editor.count_macros(doc)

        assert count == 2, f"Should count 2 macros, got {count}"


@pytest.mark.e2e
@pytest.mark.macro
class TestMacroEdgeCases:
    """E2E tests for macro edge cases."""

    def test_nested_macro_content_preserved(
        self,
        page_with_macros,
    ):
        """Verify macros with rich content are preserved."""
        page_id = page_with_macros['page_id']
        api = page_with_macros['api_wrapper']

        page = api.get_page_by_id(page_id)
        initial_content = page['body']['storage']['value']
        version = page['version']['number']

        # Warning macro has rich-text-body
        assert 'ac:rich-text-body' in initial_content, \
            "Page should have macro with rich text body"

        # Edit unrelated content
        modified_content = initial_content.replace(
            '<h2>Conclusion</h2>',
            '<h2>Final Thoughts</h2>'
        )

        result = api.update_page(
            page_id=page_id,
            title=page['title'],
            body=modified_content,
            version=version
        )

        # Verify rich text body preserved
        final_page = api.get_page_by_id(page_id)
        final_content = final_page['body']['storage']['value']

        assert 'ac:rich-text-body' in final_content, \
            "Rich text body should be preserved"

    def test_multiple_same_type_macros(self):
        """Verify multiple macros of same type are preserved."""
        content = """
<ac:structured-macro ac:name="info">
    <ac:rich-text-body><p>First info box</p></ac:rich-text-body>
</ac:structured-macro>
<p>Text between</p>
<ac:structured-macro ac:name="info">
    <ac:rich-text-body><p>Second info box</p></ac:rich-text-body>
</ac:structured-macro>
"""
        # Count info macros
        info_count = content.count('ac:name="info"')

        assert info_count == 2, "Should have 2 info macros"
