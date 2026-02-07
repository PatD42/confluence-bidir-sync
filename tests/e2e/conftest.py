"""Pytest configuration and fixtures for E2E tests.

Provides shared fixtures for E2E tests that validate complete workflows
using real Confluence API and filesystem operations.
"""

import shutil
import tempfile
import time
import uuid
import logging
from pathlib import Path
from typing import Dict, Generator, List, Any

import pytest

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator
from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.hierarchy_builder import HierarchyBuilder
from src.page_operations.page_operations import PageOperations
from tests.fixtures.confluence_credentials import get_test_credentials
from tests.helpers.confluence_test_setup import setup_test_page, teardown_test_page

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def test_credentials() -> Dict[str, str]:
    """Load test Confluence credentials from .env.test file.

    Returns:
        Dict containing:
            - confluence_url: Confluence instance URL
            - confluence_user: User email
            - confluence_api_token: API token
            - test_space: Test space key (from CONFLUENCE_TEST_SPACE)

    Raises:
        FileNotFoundError: If .env.test file not found
        ValueError: If required credentials are missing
    """
    return get_test_credentials()


@pytest.fixture(scope="session")
def api_wrapper(test_credentials: Dict[str, str]) -> APIWrapper:
    """Create authenticated API wrapper for Confluence E2E tests.

    Uses test credentials from .env.test to authenticate with Confluence API.
    This fixture has session scope for performance (reuses authentication).

    Args:
        test_credentials: Test credentials fixture

    Returns:
        Authenticated APIWrapper instance
    """
    auth = Authenticator()
    return APIWrapper(auth)


@pytest.fixture(scope="session")
def page_operations(api_wrapper: APIWrapper) -> PageOperations:
    """Create PageOperations instance for E2E tests.

    Args:
        api_wrapper: Authenticated API wrapper fixture

    Returns:
        PageOperations instance
    """
    return PageOperations(api_wrapper)


@pytest.fixture(scope="function")
def temp_test_dir() -> Generator[Path, None, None]:
    """Create temporary directory for file operation tests.

    Creates a unique temporary directory for each test function, ensuring
    isolation between tests. The directory is automatically cleaned up after
    the test completes (even if the test fails).

    Yields:
        Path to temporary directory
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="e2e_test_"))

    try:
        yield temp_dir
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


@pytest.fixture(scope="function")
def test_config_dir(temp_test_dir: Path) -> Path:
    """Create .confluence-sync directory structure for E2E tests.

    Creates the expected configuration directory structure inside a temporary
    test directory. This mirrors the real configuration layout.

    Args:
        temp_test_dir: Temporary test directory fixture

    Returns:
        Path to .confluence-sync directory
    """
    config_dir = temp_test_dir / ".confluence-sync"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Create temp subdirectory for atomic operations
    temp_subdir = config_dir / "temp"
    temp_subdir.mkdir(parents=True, exist_ok=True)

    # Create baseline directory
    baseline_dir = config_dir / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)

    return config_dir


@pytest.fixture(scope="function")
def cleanup_test_pages() -> Generator[List[str], None, None]:
    """Track test pages for cleanup after E2E tests complete.

    Provides a list that tests can append page IDs to. All pages in the list
    are automatically deleted after the test completes (even if test fails).
    This prevents test data from accumulating in Confluence.

    Yields:
        List to append page IDs that should be cleaned up
    """
    page_ids = []

    try:
        yield page_ids
    finally:
        if page_ids:
            for page_id in reversed(page_ids):
                try:
                    teardown_test_page(page_id)
                    logger.info(f"Cleaned up test page: {page_id}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup page {page_id}: {e}")


@pytest.fixture(scope="function")
def synced_test_page(
    test_credentials: Dict[str, str],
    cleanup_test_pages: List[str],
    temp_test_dir: Path,
    api_wrapper: APIWrapper,
    test_config_dir: Path,
) -> Generator[Dict[str, Any], None, None]:
    """Create a Confluence page with table content and sync to local markdown.

    This fixture creates a test page in Confluence with a table and paragraph,
    then sets up a local markdown file representing the synced state.

    Args:
        test_credentials: Test credentials fixture
        cleanup_test_pages: Cleanup fixture for automatic page deletion
        temp_test_dir: Temporary directory for local files
        api_wrapper: Authenticated API wrapper
        test_config_dir: Config directory with baseline

    Yields:
        Dict containing:
            - page_id: Confluence page ID
            - page_title: Page title
            - local_path: Path to local markdown file
            - api_wrapper: API wrapper instance
            - temp_dir: Temporary directory path
            - config_dir: Config directory path
            - space_key: Confluence space key
    """
    space_key = test_credentials['test_space']
    unique_id = uuid.uuid4().hex[:8]
    title = f"E2E-SyncTest-{unique_id}"

    # Create page with table and paragraph content
    content = """
<h1>Test Page</h1>
<table>
    <tr><th>Column A</th><th>Column B</th></tr>
    <tr><td>Cell A1</td><td>Cell B1</td></tr>
    <tr><td>Cell A2</td><td>Cell B2</td></tr>
</table>
<p>This is a test paragraph for sync testing.</p>
"""

    page_info = setup_test_page(
        title=title,
        content=content,
        space_key=space_key
    )
    cleanup_test_pages.append(page_info['page_id'])

    # Wait for Confluence to settle after page creation
    time.sleep(2)

    # Create corresponding local markdown file
    local_path = temp_test_dir / f"{title}.md"
    markdown_content = f"""---
page_id: {page_info['page_id']}
space_key: {space_key}
version: 1
---

# Test Page

| Column A | Column B |
|----------|----------|
| Cell A1 | Cell B1 |
| Cell A2 | Cell B2 |

This is a test paragraph for sync testing.
"""
    local_path.write_text(markdown_content)

    # Create baseline file
    baseline_dir = test_config_dir / "baseline"
    baseline_file = baseline_dir / f"{page_info['page_id']}.md"
    baseline_file.write_text(markdown_content)

    logger.info(f"Created synced test page: {page_info['page_id']} -> {local_path}")

    yield {
        'page_id': page_info['page_id'],
        'page_title': title,
        'local_path': local_path,
        'api_wrapper': api_wrapper,
        'temp_dir': temp_test_dir,
        'config_dir': test_config_dir,
        'space_key': space_key,
        'version': page_info['version'],
    }


@pytest.fixture(scope="function")
def page_with_macros(
    test_credentials: Dict[str, str],
    cleanup_test_pages: List[str],
    api_wrapper: APIWrapper,
) -> Generator[Dict[str, Any], None, None]:
    """Create a Confluence page with TOC, code, and status macros.

    This fixture creates a test page containing various Confluence macros
    to test macro preservation through sync cycles.

    Args:
        test_credentials: Test credentials fixture
        cleanup_test_pages: Cleanup fixture for automatic page deletion
        api_wrapper: Authenticated API wrapper

    Yields:
        Dict containing:
            - page_id: Confluence page ID
            - page_title: Page title
            - space_key: Confluence space key
            - api_wrapper: API wrapper instance
    """
    space_key = test_credentials['test_space']
    unique_id = uuid.uuid4().hex[:8]
    title = f"E2E-MacroTest-{unique_id}"

    # Create page with various macros
    content = """
<h1>Macro Test Page</h1>
<ac:structured-macro ac:name="toc">
    <ac:parameter ac:name="printable">true</ac:parameter>
    <ac:parameter ac:name="style">square</ac:parameter>
</ac:structured-macro>
<h2>Introduction</h2>
<p>This page contains macros for testing preservation.</p>
<h2>Code Example</h2>
<ac:structured-macro ac:name="code">
    <ac:parameter ac:name="language">python</ac:parameter>
    <ac:plain-text-body><![CDATA[def hello():
    print("Hello, World!")
]]></ac:plain-text-body>
</ac:structured-macro>
<h2>Status</h2>
<p>Current status: <ac:structured-macro ac:name="status"><ac:parameter ac:name="colour">Green</ac:parameter><ac:parameter ac:name="title">Active</ac:parameter></ac:structured-macro></p>
<h2>Warning</h2>
<ac:structured-macro ac:name="warning">
    <ac:rich-text-body><p>This is a warning message.</p></ac:rich-text-body>
</ac:structured-macro>
<h2>Conclusion</h2>
<p>End of macro test page.</p>
"""

    page_info = setup_test_page(
        title=title,
        content=content,
        space_key=space_key
    )
    cleanup_test_pages.append(page_info['page_id'])

    # Wait for Confluence to settle after page creation
    time.sleep(2)

    logger.info(f"Created macro test page: {page_info['page_id']}")

    yield {
        'page_id': page_info['page_id'],
        'page_title': title,
        'space_key': space_key,
        'api_wrapper': api_wrapper,
        'version': page_info['version'],
    }


@pytest.fixture(scope="function")
def page_with_multiline_cells(
    test_credentials: Dict[str, str],
    cleanup_test_pages: List[str],
    api_wrapper: APIWrapper,
) -> Generator[Dict[str, Any], None, None]:
    """Create a Confluence page with table cells containing multiple lines.

    This fixture creates a test page with table cells using <p> tags
    for multi-line content, testing line break conversion.

    Args:
        test_credentials: Test credentials fixture
        cleanup_test_pages: Cleanup fixture for automatic page deletion
        api_wrapper: Authenticated API wrapper

    Yields:
        Dict containing page info
    """
    space_key = test_credentials['test_space']
    unique_id = uuid.uuid4().hex[:8]
    title = f"E2E-MultilineTest-{unique_id}"

    # Create page with multi-line table cells using <p> tags
    content = """
<h1>Multi-line Cell Test</h1>
<table>
    <tr>
        <th>Feature</th>
        <th>Description</th>
    </tr>
    <tr>
        <td><p>Login</p><p>Authentication</p></td>
        <td><p>Users can</p><p>authenticate</p><p>securely</p></td>
    </tr>
    <tr>
        <td><p>Dashboard</p></td>
        <td><p>View</p><p>metrics</p></td>
    </tr>
</table>
"""

    page_info = setup_test_page(
        title=title,
        content=content,
        space_key=space_key
    )
    cleanup_test_pages.append(page_info['page_id'])

    # Wait for Confluence to settle after page creation
    time.sleep(2)

    logger.info(f"Created multiline cell test page: {page_info['page_id']}")

    yield {
        'page_id': page_info['page_id'],
        'page_title': title,
        'space_key': space_key,
        'api_wrapper': api_wrapper,
        'version': page_info['version'],
    }


@pytest.fixture(scope="function")
def file_mapper_instance(api_wrapper: APIWrapper) -> FileMapper:
    """Create a configured FileMapper instance for E2E tests.

    Args:
        api_wrapper: Authenticated API wrapper fixture

    Returns:
        Configured FileMapper instance
    """
    hierarchy_builder = HierarchyBuilder(api_wrapper)
    file_mapper = FileMapper(hierarchy_builder=hierarchy_builder)
    logger.info("Created FileMapper instance for E2E tests")
    return file_mapper
