"""Pytest configuration and fixtures for integration tests.

Provides shared fixtures for integration tests that interact with real
Confluence API and filesystem operations, plus mock fixtures for
isolated component testing.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Dict, Generator, Any
from unittest.mock import Mock, patch, MagicMock
import pytest

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator
from src.cli.baseline_manager import BaselineManager
from tests.fixtures.confluence_credentials import get_test_credentials
from tests.fixtures.adf_fixtures import ADF_MINIMAL, ADF_WITH_TABLE


@pytest.fixture(scope="session")
def test_credentials() -> Dict[str, str]:
    """Load test Confluence credentials from .env.test file.

    Returns:
        Dict containing:
            - confluence_url: Confluence instance URL
            - confluence_user: User email
            - confluence_api_token: API token
            - test_space: Test space key

    Raises:
        FileNotFoundError: If .env.test file not found
        ValueError: If required credentials are missing
    """
    return get_test_credentials()


@pytest.fixture(scope="session")
def api_wrapper(test_credentials: Dict[str, str]) -> APIWrapper:
    """Create authenticated API wrapper for Confluence integration tests.

    Uses test credentials from .env.test to authenticate with Confluence API.
    This fixture has session scope for performance (reuses authentication).

    Args:
        test_credentials: Test credentials fixture

    Returns:
        Authenticated APIWrapper instance
    """
    auth = Authenticator()
    return APIWrapper(auth)


# =============================================================================
# Mock Fixtures for Integration Tests
# =============================================================================

@pytest.fixture
def mock_api_wrapper() -> Generator[Mock, None, None]:
    """Create a mock APIWrapper for integration tests.

    Provides a mock with pre-configured return values for common operations.
    Tests can customize the mock's behavior as needed.

    Yields:
        Mock APIWrapper instance with default responses
    """
    mock = Mock(spec=APIWrapper)

    # Default page response
    mock.get_page_by_id.return_value = {
        'id': '12345',
        'title': 'Test Page',
        'version': {'number': 1},
        'body': {
            'storage': {'value': '<p>Test content</p>'},
        },
        'space': {'key': 'TEST'},
    }

    # Default ADF response
    mock.get_page_adf.return_value = ADF_MINIMAL

    # Default update responses
    mock.update_page.return_value = {
        'id': '12345',
        'version': {'number': 2},
    }
    mock.update_page_adf.return_value = {
        'id': '12345',
        'version': {'number': 2},
    }

    # Default create response
    mock.create_page.return_value = {
        'id': '67890',
        'version': {'number': 1},
    }

    # Default delete (no return)
    mock.delete_page.return_value = None

    yield mock


@pytest.fixture
def mock_api_wrapper_with_table() -> Generator[Mock, None, None]:
    """Create a mock APIWrapper that returns a page with table content.

    Yields:
        Mock APIWrapper with table content responses
    """
    mock = Mock(spec=APIWrapper)

    mock.get_page_by_id.return_value = {
        'id': '12345',
        'title': 'Table Page',
        'version': {'number': 1},
        'body': {
            'storage': {
                'value': '''
<table>
    <tr><th>Col1</th><th>Col2</th></tr>
    <tr><td>A</td><td>B</td></tr>
</table>
'''
            },
        },
        'space': {'key': 'TEST'},
    }

    mock.get_page_adf.return_value = ADF_WITH_TABLE

    mock.update_page_adf.return_value = {
        'id': '12345',
        'version': {'number': 2},
    }

    yield mock


@pytest.fixture
def mock_api_wrapper_version_conflict() -> Generator[Mock, None, None]:
    """Create a mock APIWrapper that simulates version conflicts.

    The mock will fail on first update attempt with version mismatch,
    then succeed on retry.

    Yields:
        Mock APIWrapper that simulates version conflict
    """
    mock = Mock(spec=APIWrapper)

    # Initial page state
    mock.get_page_by_id.return_value = {
        'id': '12345',
        'title': 'Test Page',
        'version': {'number': 1},
        'body': {'storage': {'value': '<p>Original</p>'}},
        'space': {'key': 'TEST'},
    }

    # First update fails with version conflict
    call_count = [0]

    def update_with_conflict(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("Version conflict: expected 1, got 2")
        return {'id': '12345', 'version': {'number': 3}}

    mock.update_page.side_effect = update_with_conflict
    mock.update_page_adf.side_effect = update_with_conflict

    # After first call, return updated version
    def get_page_after_conflict(*args, **kwargs):
        if call_count[0] > 0:
            return {
                'id': '12345',
                'title': 'Test Page',
                'version': {'number': 2},
                'body': {'storage': {'value': '<p>Updated by other</p>'}},
                'space': {'key': 'TEST'},
            }
        return mock.get_page_by_id.return_value

    mock.get_page_by_id.side_effect = get_page_after_conflict

    yield mock


@pytest.fixture
def mock_baseline_manager(temp_test_dir: Path) -> Generator[BaselineManager, None, None]:
    """Create a BaselineManager with a temporary directory.

    Args:
        temp_test_dir: Temporary directory fixture

    Yields:
        BaselineManager instance using temp directory
    """
    config_dir = temp_test_dir / '.confluence-sync'
    config_dir.mkdir(parents=True, exist_ok=True)

    baseline_dir = config_dir / 'baseline'
    baseline_dir.mkdir(parents=True, exist_ok=True)

    manager = BaselineManager(config_dir)
    manager.initialize()
    yield manager


@pytest.fixture
def mock_baseline_with_content(mock_baseline_manager: BaselineManager) -> Generator[BaselineManager, None, None]:
    """Create a BaselineManager with pre-populated baseline content.

    Args:
        mock_baseline_manager: BaselineManager fixture

    Yields:
        BaselineManager with baseline content for page '12345'
    """
    # Write baseline content for test page
    baseline_content = """| Col1 | Col2 |
|------|------|
| A | B |
| C | D |
"""
    mock_baseline_manager.update_baseline('12345', baseline_content)

    yield mock_baseline_manager


@pytest.fixture
def mock_adf_api() -> Generator[Dict[str, Mock], None, None]:
    """Create mocks for ADF-specific API calls.

    Yields:
        Dict with 'get' and 'update' mocks for ADF operations
    """
    with patch.object(APIWrapper, 'get_page_adf') as mock_get:
        with patch.object(APIWrapper, 'update_page_adf') as mock_update:
            mock_get.return_value = ADF_MINIMAL
            mock_update.return_value = {'id': '12345', 'version': {'number': 2}}

            yield {
                'get': mock_get,
                'update': mock_update,
            }


@pytest.fixture
def mock_network_error() -> Generator[Mock, None, None]:
    """Create a mock that simulates transient network errors.

    First call raises network error, subsequent calls succeed.

    Yields:
        Mock that fails once then succeeds
    """
    mock = Mock()
    call_count = [0]

    def network_error_then_success(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ConnectionError("Network unreachable")
        return {'id': '12345', 'version': {'number': 2}}

    mock.side_effect = network_error_then_success
    yield mock


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
    temp_dir = Path(tempfile.mkdtemp(prefix="confluence_sync_test_"))

    try:
        yield temp_dir
    finally:
        # Cleanup: Remove directory and all contents
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


@pytest.fixture(scope="function")
def test_config_dir(temp_test_dir: Path) -> Path:
    """Create .confluence-sync directory structure for config tests.

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
def cleanup_test_pages() -> Generator[list, None, None]:
    """Track test pages for cleanup after tests complete.

    Provides a list that tests can append page IDs to. All pages in the list
    are automatically deleted after the test completes (even if test fails).
    This prevents test data from accumulating in Confluence.

    Yields:
        List to append page IDs that should be cleaned up

    Example:
        >>> def test_page_creation(api_wrapper, cleanup_test_pages):
        ...     page_id = api_wrapper.create_page(...)
        ...     cleanup_test_pages.append(page_id)
        ...     # Page will be deleted automatically after test
    """
    page_ids = []

    try:
        yield page_ids
    finally:
        # Cleanup: Delete all tracked pages
        if page_ids:
            auth = Authenticator()
            api = APIWrapper(auth)

            for page_id in page_ids:
                try:
                    api.delete_page(page_id)
                except Exception:
                    # Ignore errors during cleanup (page might not exist)
                    pass
