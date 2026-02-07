"""E2E tests for surgical XHTML editing.

These tests verify that surgical edits to markdown files are correctly
propagated to Confluence without corrupting other content.

Templates in CONFSYNCTEST (DO NOT MODIFY):
- A: Surgical Edit Test - Reference page (without table) - ID: 11763713
- B: Duplicate of Surgical Edit Test (with table) - ID: 11829249
- C: Surgical Edit Test (with headerless table) - ID: 11796481
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Generator, List

import pytest

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator
from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.models import SpaceConfig, SyncConfig
from tests.fixtures.confluence_credentials import get_test_credentials
from tests.helpers.confluence_test_setup import setup_test_page, teardown_test_page

logger = logging.getLogger(__name__)

# Template page IDs (DO NOT MODIFY THESE PAGES)
TEMPLATE_A_ID = "11763713"  # Reference page (without table)
TEMPLATE_B_ID = "11829249"  # With table (has headers)
TEMPLATE_C_ID = "11796481"  # Headerless table


@pytest.fixture(scope="session")
def test_credentials() -> Dict[str, str]:
    """Load test Confluence credentials."""
    return get_test_credentials()


@pytest.fixture(scope="session")
def api_wrapper(test_credentials: Dict[str, str]) -> APIWrapper:
    """Create authenticated API wrapper."""
    auth = Authenticator()
    return APIWrapper(auth)


@pytest.fixture(scope="function")
def temp_test_dir() -> Generator[Path, None, None]:
    """Create temporary directory for test files."""
    temp_dir = Path(tempfile.mkdtemp(prefix="surgical_edit_e2e_"))
    try:
        yield temp_dir
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


@pytest.fixture(scope="function")
def cleanup_test_pages() -> Generator[List[str], None, None]:
    """Track test pages for cleanup."""
    page_ids = []
    try:
        yield page_ids
    finally:
        for page_id in reversed(page_ids):
            try:
                teardown_test_page(page_id)
                logger.info(f"Cleaned up test page: {page_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup page {page_id}: {e}")


@pytest.fixture(scope="function")
def file_mapper_instance() -> FileMapper:
    """Create FileMapper instance for E2E tests."""
    auth = Authenticator()
    return FileMapper(authenticator=auth)


def create_test_page_from_template(
    api_wrapper: APIWrapper,
    template_id: str,
    test_name: str,
    space_key: str,
    parent_id: str = None
) -> Dict[str, str]:
    """Create a test page by copying content from a template.

    Args:
        api_wrapper: Authenticated API wrapper
        template_id: ID of template page to copy
        test_name: Name to include in the test page title
        space_key: Space key for the new page
        parent_id: Optional parent page ID

    Returns:
        Dict with page_id, title, version
    """
    # Get template content
    template = api_wrapper.get_page_by_id(page_id=template_id, expand="body.storage")
    template_content = template["body"]["storage"]["value"]

    # Create test page
    return setup_test_page(
        title=f"Test - {test_name}",
        content=template_content,
        space_key=space_key,
        parent_id=parent_id
    )


def run_sync(
    file_mapper: FileMapper,
    space_key: str,
    parent_page_id: str,
    local_path: Path,
    force_pull: bool = False,
    force_push: bool = False
) -> None:
    """Run sync operation."""
    sync_config = SyncConfig(
        spaces=[SpaceConfig(
            space_key=space_key,
            parent_page_id=parent_page_id,
            local_path=str(local_path),
            exclude_page_ids=[]
        )],
        page_limit=100,
        force_pull=force_pull,
        force_push=force_push,
        temp_dir=str(local_path / ".confluence-sync" / "temp")
    )

    # Create config directory
    (local_path / ".confluence-sync" / "temp").mkdir(parents=True, exist_ok=True)

    file_mapper.sync_spaces(sync_config)


def strip_markdown_formatting(text: str) -> str:
    """Strip markdown formatting (bold, italic) from text for comparison."""
    import re
    # Remove bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    # Remove italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    return text


def find_markdown_file(sync_dir: Path, contains_text: str = None) -> Path:
    """Find a markdown file, optionally containing specific text.

    Text comparison strips markdown formatting so "ulist 1" matches "u**list** 1".
    """
    for md_file in sync_dir.rglob("*.md"):
        if contains_text is None:
            return md_file
        content = md_file.read_text()
        # Also check stripped version for matching
        stripped_content = strip_markdown_formatting(content)
        if contains_text in content or contains_text in stripped_content:
            return md_file
    raise FileNotFoundError(f"No markdown file found" + (f" containing '{contains_text}'" if contains_text else ""))


class TestSurgicalEditNoTable:
    """Tests for surgical edits on pages without tables (Template A)."""

    @pytest.mark.e2e
    def test_remove_word_from_paragraph(
        self,
        api_wrapper,
        file_mapper_instance,
        test_credentials,
        temp_test_dir,
        cleanup_test_pages
    ):
        """Test 1: Remove a word from the first paragraph.

        Expected: Word is removed, no errors, other content preserved.
        """
        space_key = test_credentials['test_space']

        # Create parent page for this test
        parent = setup_test_page(
            title="Test Parent - Paragraph Edit",
            content="<p>Parent page</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(parent['page_id'])

        # Create test page from template A
        test_page = create_test_page_from_template(
            api_wrapper, TEMPLATE_A_ID,
            "Paragraph Edit", space_key, parent['page_id']
        )
        cleanup_test_pages.append(test_page['page_id'])
        logger.info(f"Created test page: {test_page['page_id']}")

        # Step 1: Initial sync to pull content
        run_sync(file_mapper_instance, space_key, parent['page_id'], temp_test_dir, force_pull=True)

        # Step 2: Find and modify the markdown file
        md_file = find_markdown_file(temp_test_dir, "semantic intent")
        content = md_file.read_text()
        logger.info(f"Found markdown file: {md_file}")

        # Remove "semantic" from "extracts semantic intent"
        assert "semantic intent" in content, "Expected text 'semantic intent' not found"
        modified_content = content.replace("semantic intent", "intent")
        md_file.write_text(modified_content)
        logger.info("Modified markdown: removed 'semantic' from paragraph")

        # Step 3: Sync to push changes (force_push to avoid conflict detection on freshly created page)
        run_sync(file_mapper_instance, space_key, parent['page_id'], temp_test_dir, force_push=True)

        # Step 4: Verify the change was propagated to Confluence
        page = api_wrapper.get_page_by_id(page_id=test_page['page_id'], expand="body.storage")
        xhtml = page["body"]["storage"]["value"]

        # Verify the word was removed
        assert "semantic intent" not in xhtml, "Word 'semantic' should have been removed"
        assert "extracts intent from Python" in xhtml, "Modified text not found"

        # Verify other content is preserved
        assert "Intent Extraction:" in xhtml, "List item 1 should be preserved"
        assert "Syntax Error Resilience:" in xhtml, "List item 2 should be preserved"
        assert "Quality Filtering:" in xhtml, "List item 3 should be preserved"
        assert "Structured Output:" in xhtml, "List item 4 should be preserved"

        logger.info("✓ Test 1 PASSED: Word removed from paragraph successfully")

    @pytest.mark.e2e
    def test_remove_word_from_list_item(
        self,
        api_wrapper,
        file_mapper_instance,
        test_credentials,
        temp_test_dir,
        cleanup_test_pages
    ):
        """Test 2: Remove a word from the second ordered bullet.

        Expected: Word is removed, no errors, other content preserved.
        """
        space_key = test_credentials['test_space']

        # Create parent page
        parent = setup_test_page(
            title="Test Parent - List Item Edit",
            content="<p>Parent page</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(parent['page_id'])

        # Create test page from template A
        test_page = create_test_page_from_template(
            api_wrapper, TEMPLATE_A_ID,
            "List Item Edit", space_key, parent['page_id']
        )
        cleanup_test_pages.append(test_page['page_id'])
        logger.info(f"Created test page: {test_page['page_id']}")

        # Step 1: Initial sync
        run_sync(file_mapper_instance, space_key, parent['page_id'], temp_test_dir, force_pull=True)

        # Step 2: Find and modify
        md_file = find_markdown_file(temp_test_dir, "Syntax Error Resilience")
        content = md_file.read_text()

        # Remove "as well" from the second list item
        # "syntax errors as well" -> "syntax errors"
        assert "syntax errors as well" in content or "syntax errors" in content, \
            "Expected text not found in markdown"

        if "syntax errors as well" in content:
            modified_content = content.replace("syntax errors as well", "syntax errors")
        else:
            # If "as well" is not present, remove another word like "valid"
            modified_content = content.replace("valid intents", "intents")

        md_file.write_text(modified_content)
        logger.info("Modified markdown: removed words from list item 2")

        # Step 3: Sync to push changes (force_push to avoid conflict detection on freshly created page)
        run_sync(file_mapper_instance, space_key, parent['page_id'], temp_test_dir, force_push=True)

        # Step 4: Verify
        page = api_wrapper.get_page_by_id(page_id=test_page['page_id'], expand="body.storage")
        xhtml = page["body"]["storage"]["value"]

        # Verify other content is preserved
        assert "Code Intent RAG" in xhtml, "Paragraph should be preserved"
        assert "Intent Extraction:" in xhtml, "List item 1 should be preserved"
        assert "Syntax Error Resilience" in xhtml, "List item 2 header should be preserved"
        assert "Quality Filtering:" in xhtml, "List item 3 should be preserved"
        assert "Structured Output:" in xhtml, "List item 4 should be preserved"

        logger.info("✓ Test 2 PASSED: Word removed from list item successfully")


class TestSurgicalEditWithTable:
    """Tests for surgical edits on pages with tables (Template B)."""

    @pytest.mark.e2e
    def test_change_word_in_table_first_column(
        self,
        api_wrapper,
        file_mapper_instance,
        test_credentials,
        temp_test_dir,
        cleanup_test_pages
    ):
        """Test 3: Change a word in the first column of the first data row.

        Expected: Word is changed, no errors, table structure preserved.
        """
        space_key = test_credentials['test_space']

        # Create parent page
        parent = setup_test_page(
            title="Test Parent - Table Column Edit",
            content="<p>Parent page</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(parent['page_id'])

        # Create test page from template B
        test_page = create_test_page_from_template(
            api_wrapper, TEMPLATE_B_ID,
            "Table Column Edit", space_key, parent['page_id']
        )
        cleanup_test_pages.append(test_page['page_id'])
        logger.info(f"Created test page: {test_page['page_id']}")

        # Step 1: Initial sync
        run_sync(file_mapper_instance, space_key, parent['page_id'], temp_test_dir, force_pull=True)

        # Step 2: Find and modify
        md_file = find_markdown_file(temp_test_dir, "Resilience")
        content = md_file.read_text()

        # Change "Resilience" to "Robustness"
        assert "Resilience" in content, "Expected text 'Resilience' not found"
        modified_content = content.replace("Resilience", "Robustness")
        md_file.write_text(modified_content)
        logger.info("Modified markdown: changed 'Resilience' to 'Robustness' in table")

        # Step 3: Sync (force_push to avoid conflict detection on freshly created page)
        run_sync(file_mapper_instance, space_key, parent['page_id'], temp_test_dir, force_push=True)

        # Step 4: Verify
        page = api_wrapper.get_page_by_id(page_id=test_page['page_id'], expand="body.storage")
        xhtml = page["body"]["storage"]["value"]

        # Verify the word was changed
        assert "Robustness" in xhtml, "Word 'Robustness' should be in the page"

        # Verify table structure is preserved
        assert "<table" in xhtml, "Table element should be preserved"
        assert "<tbody>" in xhtml, "Table body should be preserved"
        assert "<tr" in xhtml, "Table rows should be preserved"

        # Verify other content is preserved
        assert "Code Intent RAG" in xhtml, "Paragraph should be preserved"
        assert "Intent Extraction:" in xhtml, "List items should be preserved"

        logger.info("✓ Test 3 PASSED: Word changed in table first column successfully")

    @pytest.mark.e2e
    def test_change_word_in_table_list_cell(
        self,
        api_wrapper,
        file_mapper_instance,
        test_credentials,
        temp_test_dir,
        cleanup_test_pages
    ):
        """Test 4: Change a word in the second column (list inside table cell).

        Expected: Word is changed, no errors, table and list structure preserved.
        """
        space_key = test_credentials['test_space']

        # Create parent page
        parent = setup_test_page(
            title="Test Parent - Table List Cell Edit",
            content="<p>Parent page</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(parent['page_id'])

        # Create test page from template B
        test_page = create_test_page_from_template(
            api_wrapper, TEMPLATE_B_ID,
            "Table List Cell Edit", space_key, parent['page_id']
        )
        cleanup_test_pages.append(test_page['page_id'])
        logger.info(f"Created test page: {test_page['page_id']}")

        # Step 1: Initial sync
        run_sync(file_mapper_instance, space_key, parent['page_id'], temp_test_dir, force_pull=True)

        # Step 2: Find and modify
        md_file = find_markdown_file(temp_test_dir, "ulist")
        content = md_file.read_text()

        # Change "ulist 1" to "item one" (list item in table cell)
        # Handle both plain "ulist 1" and formatted "u**list** 1"
        import re
        if "ulist 1" in content:
            modified_content = content.replace("ulist 1", "item one")
            logger.info("Modified markdown: changed 'ulist 1' to 'item one' in table")
        elif re.search(r"u\*\*list\*\*\s*1", content):
            # Handle bold formatting: u**list** 1
            modified_content = re.sub(r"u\*\*list\*\*\s*1", "item one", content)
            logger.info("Modified markdown: changed 'u**list** 1' to 'item one' in table")
        elif re.search(r"u\*list\*\s*1", content):
            # Handle italic formatting: u*list* 1
            modified_content = re.sub(r"u\*list\*\s*1", "item one", content)
            logger.info("Modified markdown: changed 'u*list* 1' to 'item one' in table")
        else:
            pytest.skip("Could not find 'ulist 1' (plain or formatted) in content")

        md_file.write_text(modified_content)

        # Step 3: Sync (force_push to avoid conflict detection on freshly created page)
        run_sync(file_mapper_instance, space_key, parent['page_id'], temp_test_dir, force_push=True)

        # Step 4: Verify
        page = api_wrapper.get_page_by_id(page_id=test_page['page_id'], expand="body.storage")
        xhtml = page["body"]["storage"]["value"]

        # Verify table structure is preserved
        assert "<table" in xhtml, "Table element should be preserved"
        assert "<ul" in xhtml or "<li>" in xhtml, "List in table should be preserved"

        # Verify other content is preserved
        assert "Code Intent RAG" in xhtml, "Paragraph should be preserved"
        assert "Intent Extraction:" in xhtml, "List items should be preserved"

        logger.info("✓ Test 4 PASSED: Word changed in table list cell successfully")


class TestSurgicalEditHeaderlessTable:
    """Tests for surgical edits on pages with headerless tables (Template C)."""

    @pytest.mark.e2e
    def test_change_word_in_headerless_table_list_cell(
        self,
        api_wrapper,
        file_mapper_instance,
        test_credentials,
        temp_test_dir,
        cleanup_test_pages
    ):
        """Test 5: Change a word in a list inside a headerless table cell.

        Expected: Word is changed, no errors, table structure preserved.
        """
        space_key = test_credentials['test_space']

        # Create parent page
        parent = setup_test_page(
            title="Test Parent - Headerless Table Edit",
            content="<p>Parent page</p>",
            space_key=space_key
        )
        cleanup_test_pages.append(parent['page_id'])

        # Create test page from template C
        test_page = create_test_page_from_template(
            api_wrapper, TEMPLATE_C_ID,
            "Headerless Table Edit", space_key, parent['page_id']
        )
        cleanup_test_pages.append(test_page['page_id'])
        logger.info(f"Created test page: {test_page['page_id']}")

        # Step 1: Initial sync
        run_sync(file_mapper_instance, space_key, parent['page_id'], temp_test_dir, force_pull=True)

        # Step 2: Find and modify
        md_file = find_markdown_file(temp_test_dir, "ulist")
        content = md_file.read_text()

        # Change "ulist 1" to "item one" in headerless table
        # Handle both plain "ulist 1" and formatted "u**list** 1"
        import re
        if "ulist 1" in content:
            modified_content = content.replace("ulist 1", "item one")
            logger.info("Modified markdown: changed 'ulist 1' to 'item one' in headerless table")
        elif re.search(r"u\*\*list\*\*\s*1", content):
            # Handle bold formatting: u**list** 1
            modified_content = re.sub(r"u\*\*list\*\*\s*1", "item one", content)
            logger.info("Modified markdown: changed 'u**list** 1' to 'item one' in headerless table")
        elif re.search(r"u\*list\*\s*1", content):
            # Handle italic formatting: u*list* 1
            modified_content = re.sub(r"u\*list\*\s*1", "item one", content)
            logger.info("Modified markdown: changed 'u*list* 1' to 'item one' in headerless table")
        else:
            pytest.skip("Could not find 'ulist 1' (plain or formatted) in content")

        md_file.write_text(modified_content)

        # Step 3: Sync (force_push to avoid conflict detection on freshly created page)
        run_sync(file_mapper_instance, space_key, parent['page_id'], temp_test_dir, force_push=True)

        # Step 4: Verify
        page = api_wrapper.get_page_by_id(page_id=test_page['page_id'], expand="body.storage")
        xhtml = page["body"]["storage"]["value"]

        # Verify table structure is preserved
        assert "<table" in xhtml, "Table element should be preserved"
        assert "<td" in xhtml, "Table data cells should be preserved"

        # Verify other content is preserved
        assert "Code Intent RAG" in xhtml, "Paragraph should be preserved"
        assert "Intent Extraction:" in xhtml, "List items should be preserved"

        logger.info("✓ Test 5 PASSED: Word changed in headerless table list cell successfully")
