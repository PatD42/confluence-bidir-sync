"""Pytest configuration and fixtures for file_mapper E2E tests.

Provides shared fixtures for E2E tests that validate complete file_mapper
workflows using real Confluence API and filesystem operations.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Dict, Generator, List
import pytest
import logging

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator
from src.file_mapper.file_mapper import FileMapper
from src.file_mapper.hierarchy_builder import HierarchyBuilder
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
        ValueError: If required credentials are missing (including CONFLUENCE_TEST_SPACE)

    Example:
        >>> def test_something(test_credentials):
        ...     space_key = test_credentials['test_space']
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

    Example:
        >>> def test_api_call(api_wrapper):
        ...     page = api_wrapper.get_page_by_id('123456')
        ...     assert page is not None
    """
    auth = Authenticator()
    return APIWrapper(auth)


@pytest.fixture(scope="function")
def temp_test_dir() -> Generator[Path, None, None]:
    """Create temporary directory for file operation tests.

    Creates a unique temporary directory for each test function, ensuring
    isolation between tests. The directory is automatically cleaned up after
    the test completes (even if the test fails).

    Yields:
        Path to temporary directory

    Example:
        >>> def test_file_operations(temp_test_dir):
        ...     test_file = temp_test_dir / "test.md"
        ...     test_file.write_text("# Test")
        ...     assert test_file.exists()
    """
    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix="file_mapper_e2e_"))

    try:
        yield temp_dir
    finally:
        # Cleanup: Remove directory and all contents
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

    Example:
        >>> def test_config_loading(test_config_dir):
        ...     config_file = test_config_dir / "config.yaml"
        ...     config_file.write_text("key: value")
        ...     assert config_file.exists()
    """
    config_dir = temp_test_dir / ".confluence-sync"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Create temp subdirectory for atomic operations
    temp_subdir = config_dir / "temp"
    temp_subdir.mkdir(parents=True, exist_ok=True)

    return config_dir


@pytest.fixture(scope="function")
def cleanup_test_pages() -> Generator[List[str], None, None]:
    """Track test pages for cleanup after E2E tests complete.

    Provides a list that tests can append page IDs to. All pages in the list
    are automatically deleted after the test completes (even if test fails).
    This prevents test data from accumulating in Confluence.

    Yields:
        List to append page IDs that should be cleaned up

    Example:
        >>> def test_page_creation(api_wrapper, cleanup_test_pages):
        ...     page_id = setup_test_page("Test", "<p>Content</p>")['page_id']
        ...     cleanup_test_pages.append(page_id)
        ...     # Page will be deleted automatically after test
    """
    page_ids = []

    try:
        yield page_ids
    finally:
        # Cleanup: Delete all tracked pages in reverse order
        # (children first to avoid dependency issues)
        if page_ids:
            for page_id in reversed(page_ids):
                try:
                    teardown_test_page(page_id)
                    logger.info(f"Cleaned up test page: {page_id}")
                except Exception as e:
                    # Log but don't fail cleanup
                    logger.warning(f"Failed to cleanup page {page_id}: {e}")


@pytest.fixture(scope="function")
def test_parent_page(test_credentials: Dict[str, str], cleanup_test_pages: List[str]) -> Dict[str, str]:
    """Create a parent page for E2E test hierarchies.

    Creates a parent page in CONFSYNCTEST space that serves as the root for
    test page hierarchies. The page is automatically cleaned up after the test.

    Args:
        test_credentials: Test credentials fixture
        cleanup_test_pages: Cleanup fixture for automatic page deletion

    Returns:
        Dict containing:
            - page_id: Parent page ID
            - space_key: Space key (CONFSYNCTEST)
            - title: Page title
            - version: Version number

    Example:
        >>> def test_hierarchy(test_parent_page):
        ...     parent_id = test_parent_page['page_id']
        ...     # Create child pages under parent_id
    """
    space_key = test_credentials['test_space']

    # Create parent page
    page_info = setup_test_page(
        title="E2E Test - File Mapper Parent",
        content="<p>Parent page for file_mapper E2E tests</p>",
        space_key=space_key
    )

    # Register for cleanup
    cleanup_test_pages.append(page_info['page_id'])

    logger.info(f"Created test parent page: {page_info['page_id']} in space {space_key}")

    return page_info


@pytest.fixture(scope="function")
def file_mapper_instance(api_wrapper: APIWrapper) -> FileMapper:
    """Create a configured FileMapper instance for E2E tests.

    Creates a FileMapper instance with all required dependencies configured
    for testing against real Confluence API.

    Args:
        api_wrapper: Authenticated API wrapper fixture

    Returns:
        Configured FileMapper instance

    Example:
        >>> def test_sync(file_mapper_instance, test_parent_page):
        ...     result = file_mapper_instance.sync_spaces(config)
        ...     assert result is not None
    """
    # Create HierarchyBuilder with API wrapper
    hierarchy_builder = HierarchyBuilder(api_wrapper)

    # Create FileMapper instance
    file_mapper = FileMapper(hierarchy_builder=hierarchy_builder)

    logger.info("Created FileMapper instance for E2E tests")

    return file_mapper
