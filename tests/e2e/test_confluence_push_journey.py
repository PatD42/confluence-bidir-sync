"""E2E test: Push Journey (convert → update/create page).

This test validates the complete push journey:
1. Convert markdown to XHTML
2. Verify valid Confluence storage format
3. Update existing page
4. Verify new version number returned
5. Create new page
6. Verify page_id returned
7. Test version conflict handling

Requirements:
- Test Confluence credentials in .env.test
- Pandoc installed on system

Future Epic Extensions:
- Epic 02: Add step to read markdown from local file
- Epic 05: Add step to perform surgical section update
"""

import pytest
import logging

from bs4 import BeautifulSoup

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator
from src.confluence_client.errors import APIAccessError
from src.content_converter.markdown_converter import MarkdownConverter

from tests.fixtures.sample_markdown import (
    SAMPLE_MARKDOWN_SIMPLE,
    SAMPLE_MARKDOWN_WITH_TABLES,
    SAMPLE_MARKDOWN_WITH_CODE_BLOCKS,
)
from tests.helpers.confluence_test_setup import setup_test_page, teardown_test_page

logger = logging.getLogger(__name__)


class TestPushJourney:
    """E2E tests for Confluence push journey."""

    @pytest.fixture(scope="function")
    def existing_test_page(self):
        """Create an existing test page for update tests."""
        page_info = setup_test_page(
            title="E2E Test - Push Journey Update Target",
            content="<p>Original content to be updated</p>"
        )
        logger.info(f"Created existing test page for updates: {page_info['page_id']}")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up existing test page: {page_info['page_id']}")

    def test_convert_markdown_to_xhtml(self):
        """Test converting markdown to XHTML and verify storage format.

        Verification steps:
        1. Convert markdown to XHTML
        2. Verify valid Confluence storage format (parseable HTML)
        3. Verify content structure preserved
        """
        # Step 1: Convert markdown to XHTML
        converter = MarkdownConverter()
        logger.info("Converting markdown to XHTML")
        xhtml = converter.markdown_to_xhtml(SAMPLE_MARKDOWN_SIMPLE)

        # Step 2: Verify valid Confluence storage format
        assert xhtml, "XHTML output should not be empty"

        # Parse the XHTML to verify it's valid
        soup = BeautifulSoup(xhtml, 'lxml')
        assert soup, "XHTML should be parseable"
        logger.info("✓ Verified XHTML is valid and parseable")

        # Step 3: Verify content structure preserved
        # Check for headings
        h1_tags = soup.find_all('h1')
        h2_tags = soup.find_all('h2')
        assert len(h1_tags) > 0 or len(h2_tags) > 0, "Should have heading tags"

        # Check for lists
        ul_tags = soup.find_all('ul')
        ol_tags = soup.find_all('ol')
        assert len(ul_tags) > 0 or len(ol_tags) > 0, "Should have list tags"

        # Check content preservation
        text_content = soup.get_text()
        assert 'Test Page' in text_content, "Should contain page title"
        assert 'Section 1' in text_content, "Should contain section 1"
        assert 'Section 2' in text_content, "Should contain section 2"

        logger.info("✓ Verified content structure preserved in XHTML")
        logger.info(f"XHTML preview:\n{xhtml[:300]}...")

    def test_update_existing_page(self, existing_test_page):
        """Test updating an existing page with converted markdown.

        Verification steps:
        1. Convert markdown to XHTML
        2. Update existing page
        3. Verify new version number returned
        4. Fetch updated page and verify content
        """
        # Step 1: Convert markdown to XHTML
        converter = MarkdownConverter()
        logger.info("Converting markdown to XHTML for update")
        new_content = converter.markdown_to_xhtml(SAMPLE_MARKDOWN_SIMPLE)
        assert new_content, "Should have XHTML content"
        logger.info("✓ Converted markdown to XHTML")

        # Step 2: Update existing page
        auth = Authenticator()
        api = APIWrapper(auth)

        page_id = existing_test_page['page_id']
        original_version = existing_test_page['version']
        logger.info(f"Updating page {page_id} (current version: {original_version})")

        result = api.update_page(
            page_id=page_id,
            title="E2E Test - Push Journey Update Target",
            body=new_content,
            version=original_version
        )
        new_version = result.get("version", {}).get("number")

        # Step 3: Verify new version number returned
        assert isinstance(new_version, int), "Should return version number as int"
        assert new_version == original_version + 1, \
            f"Version should increment from {original_version} to {original_version + 1}"
        logger.info(f"✓ Verified version incremented: {original_version} → {new_version}")

        # Step 4: Fetch updated page and verify content
        updated_page = api.get_page_by_id(page_id, expand="body.storage,version")

        assert updated_page, "Should return page data"
        fetched_version = updated_page.get("version", {}).get("number")
        assert fetched_version == new_version, "Fetched page should have new version"
        content_storage = updated_page.get("body", {}).get("storage", {}).get("value", "")
        assert content_storage, "Should have updated content"

        # Verify the content was actually updated
        assert 'Original content to be updated' not in content_storage, \
            "Should not contain original content"
        assert 'Test Page' in content_storage or \
               'Section 1' in content_storage, \
            "Should contain new content"

        logger.info("✓ Verified page updated successfully with new content")
        logger.info(f"Updated page: version {fetched_version}")

    def test_create_new_page(self):
        """Test creating a new page with converted markdown.

        Verification steps:
        1. Convert markdown to XHTML
        2. Create new page
        3. Verify page_id returned
        4. Fetch created page and verify content
        """
        page_id = None
        try:
            # Step 1: Convert markdown to XHTML
            converter = MarkdownConverter()
            logger.info("Converting markdown to XHTML for new page")
            content = converter.markdown_to_xhtml(SAMPLE_MARKDOWN_WITH_TABLES)
            assert content, "Should have XHTML content"
            logger.info("✓ Converted markdown to XHTML")

            # Step 2: Create new page
            auth = Authenticator()
            api = APIWrapper(auth)

            from tests.fixtures.confluence_credentials import get_test_credentials
            creds = get_test_credentials()
            space_key = creds['test_space']

            title = "E2E Test - Push Journey New Page"
            logger.info(f"Creating new page '{title}' in space {space_key}")

            result = api.create_page(
                space=space_key,
                title=title,
                body=content,
                parent_id=None
            )
            page_id = result.get("id") if isinstance(result, dict) else str(result)

            # Step 3: Verify page_id returned
            assert page_id, "Should return page_id"
            assert isinstance(page_id, str), "page_id should be a string"
            logger.info(f"✓ Verified page_id returned: {page_id}")

            # Step 4: Fetch created page and verify content
            created_page = api.get_page_by_id(page_id, expand="body.storage,version")

            assert created_page, "Should return page data"
            assert created_page.get("id") == page_id, "Page ID should match"
            assert created_page.get("title") == title, "Title should match"
            assert created_page.get("version", {}).get("number") == 1, "New page should be version 1"
            content_storage = created_page.get("body", {}).get("storage", {}).get("value", "")
            assert content_storage, "Should have content"

            # Verify the content matches what we uploaded
            assert 'Page with Tables' in content_storage or \
                   'table' in content_storage.lower(), \
                "Should contain table content"

            logger.info("✓ Verified new page created successfully")
            logger.info(f"Created page: {created_page.get('title')} (ID: {created_page.get('id')}, version: {created_page.get('version', {}).get('number')})")

        finally:
            # Cleanup
            if page_id:
                teardown_test_page(page_id)
                logger.info(f"Cleaned up created test page: {page_id}")

    @pytest.mark.skip(reason="Version conflict testing requires direct REST API access - atlassian-python-api auto-manages versions")
    def test_version_conflict_handling(self, existing_test_page):
        """Test version conflict handling when page is updated concurrently.

        NOTE: This test is skipped because the atlassian-python-api library
        automatically fetches and increments versions internally, making it
        impossible to trigger version conflicts through the library's interface.
        Version conflict handling IS implemented in APIWrapper (lines 251-257)
        but requires direct REST API calls to test, which is beyond the scope
        of this E2E test suite.

        Verification steps:
        1. Convert markdown to XHTML
        2. Update page with correct version (should succeed)
        3. Attempt to update with old version (should fail with conflict)
        4. Verify descriptive error for version conflict
        """
        # Step 1: Convert markdown to XHTML
        converter = MarkdownConverter()
        logger.info("Converting markdown to XHTML for version conflict test")
        content = converter.markdown_to_xhtml(SAMPLE_MARKDOWN_SIMPLE)
        assert content, "Should have XHTML content"
        logger.info("✓ Converted markdown to XHTML")

        # Step 2: Update page with correct version (should succeed)
        auth = Authenticator()
        api = APIWrapper(auth)

        page_id = existing_test_page['page_id']
        original_version = existing_test_page['version']

        logger.info(f"First update with version {original_version}")
        result = api.update_page(
            page_id=page_id,
            title="E2E Test - Push Journey Update Target",
            body=content,
            version=original_version
        )
        new_version = result.get("version", {}).get("number")
        assert new_version == original_version + 1, "Should increment version"
        logger.info(f"✓ First update succeeded: version {original_version} → {new_version}")

        # Step 3: Attempt to update with old version (should fail with conflict)
        logger.info(f"Attempting second update with old version {original_version} (should fail)")

        with pytest.raises(APIAccessError) as exc_info:
            api.update_page(
                page_id=page_id,
                title="E2E Test - Push Journey Update Target",
                body=content,
                version=original_version  # Using old version - should conflict
            )

        # Step 4: Verify descriptive error for version conflict
        error = exc_info.value
        assert error, "Should raise APIAccessError for version conflict"
        logger.info(f"✓ Version conflict detected as expected: {error}")

    def test_duplicate_page_creation_handling(self):
        """Test duplicate page creation detection.

        Verification steps:
        1. Create page with markdown content
        2. Attempt to create page with same title (should fail)
        3. Verify duplicate is detected and error returned
        """
        from src.page_operations import PageOperations

        page_id = None
        try:
            from tests.fixtures.confluence_credentials import get_test_credentials
            creds = get_test_credentials()
            space_key = creds['test_space']

            title = "E2E Test - Push Journey Duplicate Test"
            markdown = "# Duplicate Test\n\nTest content"

            # Step 1: Create page with unique title
            ops = PageOperations()
            logger.info(f"Creating first page '{title}'")

            result = ops.create_page(
                space_key=space_key,
                title=title,
                markdown_content=markdown,
                parent_id=None
            )
            assert result.success, f"First page should be created: {result.error}"
            page_id = result.page_id
            logger.info(f"✓ First page created: {page_id}")

            # Step 2: Attempt to create page with same title (should fail)
            logger.info(f"Attempting to create duplicate page with title '{title}' (should fail)")

            duplicate_result = ops.create_page(
                space_key=space_key,
                title=title,
                markdown_content=markdown,
                parent_id=None
            )

            # Step 3: Verify duplicate is detected
            assert not duplicate_result.success, "Should fail for duplicate"
            assert "already exists" in duplicate_result.error.lower(), \
                "Error should mention page already exists"
            logger.info(f"✓ Duplicate page creation prevented: {duplicate_result.error}")

        finally:
            # Cleanup
            if page_id:
                teardown_test_page(page_id)
                logger.info(f"Cleaned up test page: {page_id}")

    def test_complete_push_journey_workflow(self, existing_test_page):
        """Test the complete push journey workflow end-to-end.

        This test simulates a real-world scenario:
        1. Start with markdown content
        2. Convert to XHTML storage format
        3. Validate XHTML structure
        4. Update existing page
        5. Verify update succeeded
        6. Fetch and validate updated content

        This is the foundation for Epic 02 which will add:
        - Read markdown from local file system
        - Map files to pages

        And Epic 05 which will add:
        - Surgical section updates (update only changed sections)
        """
        logger.info("=== Starting Complete Push Journey Workflow ===")

        # Initialize all components
        auth = Authenticator()
        api = APIWrapper(auth)
        converter = MarkdownConverter()

        # Step 1: Start with markdown content
        markdown = SAMPLE_MARKDOWN_WITH_CODE_BLOCKS
        logger.info("1. Starting with markdown content")
        logger.info(f"   Markdown length: {len(markdown)} characters")
        assert markdown, "Should have markdown content"
        logger.info("   ✓ Markdown content ready")

        # Step 2: Convert to XHTML storage format
        logger.info("2. Converting markdown to XHTML storage format")
        xhtml = converter.markdown_to_xhtml(markdown)
        assert xhtml, "Should produce XHTML output"
        logger.info(f"   ✓ Converted to XHTML ({len(xhtml)} characters)")

        # Step 3: Validate XHTML structure
        logger.info("3. Validating XHTML structure")
        soup = BeautifulSoup(xhtml, 'lxml')
        assert soup, "XHTML should be parseable"

        # Verify code blocks are present
        pre_tags = soup.find_all('pre')
        code_tags = soup.find_all('code')
        assert len(pre_tags) > 0 or len(code_tags) > 0, "Should have code blocks"
        logger.info(f"   ✓ XHTML structure valid (found {len(pre_tags)} <pre> tags, {len(code_tags)} <code> tags)")

        # Step 4: Update existing page
        page_id = existing_test_page['page_id']
        original_version = existing_test_page['version']
        logger.info(f"4. Updating existing page {page_id} (version {original_version})")

        result = api.update_page(
            page_id=page_id,
            title="E2E Test - Push Journey Update Target",
            body=xhtml,
            version=original_version
        )
        new_version = result.get("version", {}).get("number")
        logger.info(f"   ✓ Page updated: version {original_version} → {new_version}")

        # Step 5: Verify update succeeded
        logger.info("5. Verifying update succeeded")
        assert isinstance(new_version, int), "Should return version number"
        assert new_version == original_version + 1, "Version should increment"
        logger.info(f"   ✓ Update verified (new version: {new_version})")

        # Step 6: Fetch and validate updated content
        logger.info("6. Fetching and validating updated content")
        updated_page = api.get_page_by_id(page_id, expand="body.storage,version")

        assert updated_page, "Should return page data"
        fetched_version = updated_page.get("version", {}).get("number")
        assert fetched_version == new_version, "Fetched page should have new version"
        content_storage = updated_page.get("body", {}).get("storage", {}).get("value", "")
        assert content_storage, "Should have content"

        # Verify content contains code blocks
        assert 'Page with Code Blocks' in content_storage or \
               'code' in content_storage.lower(), \
            "Should contain code block content"

        logger.info("   ✓ Updated content validated")

        logger.info("=== Complete Push Journey Workflow PASSED ===")
        logger.info("Summary:")
        logger.info(f"  - Page ID: {updated_page.get('id')}")
        logger.info(f"  - Title: {updated_page.get('title')}")
        logger.info(f"  - Version: {original_version} → {new_version}")
        logger.info(f"  - Markdown: {len(markdown)} characters")
        logger.info(f"  - XHTML: {len(xhtml)} characters")
        logger.info(f"  - Storage content: {len(content_storage)} characters")
        logger.info("\nNext steps (future epics):")
        logger.info("  - Epic 02: Read markdown from local file system")
        logger.info("  - Epic 05: Implement surgical section updates")
        logger.info("  - Epic 06: Create CLI tool for sync orchestration")
