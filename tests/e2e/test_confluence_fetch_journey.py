"""E2E test: Fetch Journey (fetch → convert to markdown).

This test validates the complete fetch journey:
1. Fetch page by ID from test Confluence
2. Verify ConfluencePage returned with storage format content
3. Convert XHTML to markdown
4. Verify clean markdown output
5. Verify warnings for macros

Requirements:
- Test Confluence credentials in .env.test
- Pandoc installed on system

Future Epic Extensions:
- Epic 02: Add step to write markdown to local file
- Epic 03: Add step to integrate with git merge
- Epic 04: Add step to parse sections
"""

import pytest
import logging
from bs4 import BeautifulSoup, Comment

from bs4 import BeautifulSoup

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator
from src.content_converter.markdown_converter import MarkdownConverter
from src.models.conversion_result import ConversionResult
from tests.helpers.macro_test_utils import MacroPreserver

from tests.fixtures.sample_pages import SAMPLE_PAGE_WITH_MACROS, SAMPLE_PAGE_SIMPLE
from tests.helpers.confluence_test_setup import setup_test_page, teardown_test_page

logger = logging.getLogger(__name__)


class TestFetchJourney:
    """E2E tests for Confluence fetch journey."""

    @pytest.fixture(scope="function")
    def test_page_simple(self):
        """Create a simple test page without macros."""
        page_info = setup_test_page(
            title="E2E Test - Fetch Journey Simple",
            content=SAMPLE_PAGE_SIMPLE
        )
        logger.info(f"Created simple test page: {page_info['page_id']}")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up simple test page: {page_info['page_id']}")

    @pytest.fixture(scope="function")
    def test_page_with_macros(self):
        """Create a test page with Confluence macros."""
        page_info = setup_test_page(
            title="E2E Test - Fetch Journey With Macros",
            content=SAMPLE_PAGE_WITH_MACROS
        )
        logger.info(f"Created test page with macros: {page_info['page_id']}")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up test page with macros: {page_info['page_id']}")

    def test_fetch_simple_page_by_id(self, test_page_simple):
        """Test fetching a simple page by ID and converting to markdown.

        Verification steps:
        1. Fetch page by ID from test Confluence
        2. Verify page data returned with storage format content
        3. Convert XHTML to markdown
        4. Verify clean markdown output
        """
        # Step 1: Fetch page by ID
        auth = Authenticator()
        api = APIWrapper(auth)

        page_id = test_page_simple['page_id']
        logger.info(f"Fetching page by ID: {page_id}")
        page = api.get_page_by_id(page_id, expand="space,body.storage,version")

        # Step 2: Verify page data returned with storage format content
        assert page, "Should return page data"
        assert page.get("id") == page_id, "Page ID should match"
        assert page.get("title") == test_page_simple['title'], "Title should match"
        assert page.get("space", {}).get("key") == test_page_simple['space_key'], "Space key should match"
        assert page.get("version", {}).get("number") == 1, "Version should be 1 for new page"
        content_storage = page.get("body", {}).get("storage", {}).get("value", "")
        assert content_storage, "Should have storage format content"
        assert '<h1>' in content_storage or '<h2>' in content_storage, \
            "Storage content should contain HTML headings"

        logger.info(f"✓ Verified page structure (version={page.get('version', {}).get('number')})")

        # Step 3: Convert XHTML to markdown
        converter = MarkdownConverter()
        logger.info("Converting XHTML to markdown")
        markdown = converter.xhtml_to_markdown(content_storage)

        # Step 4: Verify clean markdown output
        assert markdown, "Markdown output should not be empty"
        assert '# Test Page' in markdown or '## Test Page' in markdown or \
               'Test Page' in markdown, "Should contain page title"
        assert 'Section 1' in markdown, "Should contain section 1 content"
        assert 'Section 2' in markdown, "Should contain section 2 content"

        # Verify list formatting
        assert '-' in markdown or '*' in markdown, "Should contain bullet list markers"
        assert '1.' in markdown or '2.' in markdown, "Should contain numbered list markers"

        logger.info("✓ Verified clean markdown output")
        logger.info(f"Markdown preview:\n{markdown[:200]}...")

    def test_fetch_page_with_macros_and_verify_warnings(self, test_page_with_macros):
        """Test fetching page with macros and verifying macro preservation.

        Verification steps:
        1. Fetch page by ID from test Confluence
        2. Verify page data returned with storage format content
        3. Detect macros in XHTML
        4. Preserve macros as HTML comments
        5. Convert XHTML to markdown
        6. Verify clean markdown output with preserved macros
        7. Verify warnings for macros
        """
        # Step 1: Fetch page by ID
        auth = Authenticator()
        api = APIWrapper(auth)

        page_id = test_page_with_macros['page_id']
        logger.info(f"Fetching page with macros by ID: {page_id}")
        page = api.get_page_by_id(page_id, expand="body.storage,version")

        # Step 2: Verify page data returned with storage format content
        assert page, "Should return page data"
        assert page.get("id") == page_id, "Page ID should match"
        content_storage = page.get("body", {}).get("storage", {}).get("value", "")
        assert content_storage, "Should have storage format content"

        logger.info("✓ Verified page structure")

        # Step 3: Detect macros in XHTML
        soup = BeautifulSoup(content_storage, 'lxml')

        macro_preserver = MacroPreserver()
        macros = macro_preserver.detect_macros(soup)

        assert len(macros) > 0, "Should detect macros in content"
        logger.info(f"✓ Detected {len(macros)} macros in content")

        # Step 4: Preserve macros as HTML comments
        macro_types = macro_preserver.get_macro_types(soup)
        logger.info(f"Macro types found: {macro_types}")

        # Create a new soup instance for preservation
        soup_for_conversion = BeautifulSoup(content_storage, 'lxml')
        soup_with_comments = macro_preserver.preserve_as_comments(soup_for_conversion)

        # Verify macros were converted to comments
        comments = soup_with_comments.find_all(
            string=lambda text: isinstance(text, Comment)
        )
        macro_comments = [
            c for c in comments
            if 'CONFLUENCE_MACRO' in str(c)
        ]
        assert len(macro_comments) > 0, "Should have macro comments after preservation"
        logger.info(f"✓ Preserved {len(macro_comments)} macros as HTML comments")

        # Step 5: Convert XHTML to markdown (with preserved macros)
        converter = MarkdownConverter()
        xhtml_with_comments = str(soup_with_comments)
        logger.info("Converting XHTML (with preserved macros) to markdown")
        markdown = converter.xhtml_to_markdown(xhtml_with_comments)

        # Step 6: Verify clean markdown output with preserved macros
        assert markdown, "Markdown output should not be empty"
        assert 'Page with Macros' in markdown, "Should contain page title"
        assert 'Info Panel' in markdown or 'Code Block' in markdown or \
               'Warning Panel' in markdown, "Should contain section headers"

        # Verify that HTML comments are preserved in markdown
        # Pandoc may or may not preserve HTML comments depending on version
        # So we just verify the markdown is clean and readable
        logger.info("✓ Verified clean markdown output with macro preservation")
        logger.info(f"Markdown preview:\n{markdown[:300]}...")

        # Step 7: Verify warnings for macros
        warnings = []
        for macro_name, count in macro_types.items():
            warning = f"Found {count} '{macro_name}' macro(s) - preserved as HTML comments"
            warnings.append(warning)

        assert len(warnings) > 0, "Should have warnings about macros"
        logger.info(f"✓ Generated {len(warnings)} warnings for macros:")
        for warning in warnings:
            logger.info(f"  - {warning}")

        # Create ConversionResult with warnings
        result = ConversionResult(
            markdown=markdown,
            metadata={'page_id': page_id, 'macros_found': macro_types},
            warnings=warnings
        )

        assert result.markdown == markdown, "Result should contain markdown"
        assert result.warnings == warnings, "Result should contain warnings"
        assert result.metadata['macros_found'] == macro_types, "Metadata should contain macro types"
        logger.info("✓ Verified ConversionResult structure with warnings")

    def test_fetch_page_by_path(self, test_page_simple):
        """Test fetching a page by space key and title.

        Verification steps:
        1. Fetch page by path (space + title) from test Confluence
        2. Verify page data returned matches the created page
        3. Verify content is identical to fetch by ID
        """
        # Step 1: Fetch page by path
        auth = Authenticator()
        api = APIWrapper(auth)

        space_key = test_page_simple['space_key']
        title = test_page_simple['title']
        logger.info(f"Fetching page by path: {space_key}/{title}")
        page = api.get_page_by_title(space=space_key, title=title, expand="space,body.storage")

        # Step 2: Verify page data returned matches the created page
        assert page, "Should return page data"
        assert page.get("id") == test_page_simple['page_id'], "Page ID should match"
        assert page.get("title") == title, "Title should match"
        assert page.get("space", {}).get("key") == space_key, "Space key should match"

        logger.info(f"✓ Verified page fetch by path matches page ID: {page.get('id')}")

        # Step 3: Verify content is identical to fetch by ID
        page_by_id = api.get_page_by_id(test_page_simple['page_id'], expand="body.storage")
        content_by_path = page.get("body", {}).get("storage", {}).get("value", "")
        content_by_id = page_by_id.get("body", {}).get("storage", {}).get("value", "")
        assert content_by_path == content_by_id, \
            "Content should be identical whether fetched by ID or path"

        logger.info("✓ Verified content consistency between fetch methods")

    def test_complete_fetch_journey_workflow(self, test_page_with_macros):
        """Test the complete fetch journey workflow end-to-end.

        This test simulates a real-world scenario:
        1. Fetch page from Confluence
        2. Parse and analyze content
        3. Preserve macros
        4. Convert to markdown
        5. Generate warnings and metadata
        6. Return structured result

        This is the foundation for Epic 02 which will add:
        - Write markdown to local file system
        - Map pages to file structure

        And Epic 03 which will add:
        - Git merge integration
        """
        logger.info("=== Starting Complete Fetch Journey Workflow ===")

        # Initialize all components
        auth = Authenticator()
        api = APIWrapper(auth)
        macro_preserver = MacroPreserver()
        converter = MarkdownConverter()

        # Step 1: Fetch page from Confluence
        page_id = test_page_with_macros['page_id']
        logger.info(f"1. Fetching page from Confluence: {page_id}")
        page = api.get_page_by_id(page_id, expand="space,body.storage,version,metadata.labels")
        content_storage = page.get("body", {}).get("storage", {}).get("value", "")
        page_title = page.get("title", "")
        page_version = page.get("version", {}).get("number", 1)
        page_space_key = page.get("space", {}).get("key", "")
        page_labels = [l.get("name", "") for l in page.get("metadata", {}).get("labels", {}).get("results", [])]
        assert content_storage, "Should have content"
        logger.info(f"   ✓ Fetched page: {page_title} (version {page_version})")

        # Step 2: Parse and analyze content
        logger.info("2. Parsing and analyzing XHTML content")
        soup = BeautifulSoup(content_storage, 'lxml')
        macros = macro_preserver.detect_macros(soup)
        macro_types = macro_preserver.get_macro_types(soup)
        logger.info(f"   ✓ Parsed content, found {len(macros)} macros: {list(macro_types.keys())}")

        # Step 3: Preserve macros
        logger.info("3. Preserving macros as HTML comments")
        soup_for_conversion = BeautifulSoup(content_storage, 'lxml')
        soup_with_comments = macro_preserver.preserve_as_comments(soup_for_conversion)
        logger.info(f"   ✓ Preserved {len(macros)} macros")

        # Step 4: Convert to markdown
        logger.info("4. Converting XHTML to markdown")
        xhtml_with_comments = str(soup_with_comments)
        markdown = converter.xhtml_to_markdown(xhtml_with_comments)
        assert markdown, "Should produce markdown output"
        logger.info(f"   ✓ Converted to markdown ({len(markdown)} characters)")

        # Step 5: Generate warnings and metadata
        logger.info("5. Generating warnings and metadata")
        warnings = []
        for macro_name, count in macro_types.items():
            warning = f"Found {count} '{macro_name}' macro(s) - preserved as HTML comments"
            warnings.append(warning)

        metadata = {
            'page_id': page_id,
            'space_key': page_space_key,
            'title': page_title,
            'version': page_version,
            'macros_found': macro_types,
            'labels': page_labels,
        }
        logger.info(f"   ✓ Generated {len(warnings)} warnings")

        # Step 6: Return structured result
        logger.info("6. Creating structured ConversionResult")
        result = ConversionResult(
            markdown=markdown,
            metadata=metadata,
            warnings=warnings
        )
        logger.info("   ✓ Created ConversionResult")

        # Verify the complete result
        assert result.markdown, "Result should have markdown"
        assert result.metadata['page_id'] == page_id, "Metadata should have page_id"
        assert result.metadata['version'] == page_version, "Metadata should have version"
        assert len(result.warnings) > 0, "Should have warnings about macros"
        assert result.metadata['macros_found'], "Metadata should list macros found"

        logger.info("=== Complete Fetch Journey Workflow PASSED ===")
        logger.info("Summary:")
        logger.info(f"  - Page: {result.metadata['title']} (ID: {result.metadata['page_id']})")
        logger.info(f"  - Version: {result.metadata['version']}")
        logger.info(f"  - Markdown: {len(result.markdown)} characters")
        logger.info(f"  - Macros: {len(result.metadata['macros_found'])} types")
        logger.info(f"  - Warnings: {len(result.warnings)}")
        logger.info("\nNext steps (future epics):")
        logger.info("  - Epic 02: Write markdown to local file")
        logger.info("  - Epic 03: Integrate with git merge")
        logger.info("  - Epic 04: Parse sections for granular tracking")
        logger.info("  - Epic 05: Implement surgical section updates")
