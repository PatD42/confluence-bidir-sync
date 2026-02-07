"""Test helpers for creating and deleting test pages on Confluence.

These helpers are used by integration and E2E tests to set up and tear down
test pages on a real Confluence instance. They ensure proper cleanup even
if tests fail.
"""

import logging
from typing import Optional, Dict, Any

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator
from tests.fixtures.confluence_credentials import get_test_credentials

logger = logging.getLogger(__name__)


def setup_test_page(
    title: str,
    content: str,
    space_key: Optional[str] = None,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a test page on Confluence for testing purposes.

    This helper creates a page with the given title and content in the
    test space. The page should be deleted after the test using
    teardown_test_page().

    Pre-cleanup: If a page with the same title already exists in the space
    (from a previous interrupted test run), it will be deleted first to
    avoid "page already exists" errors.

    Args:
        title: The page title (should be unique to avoid conflicts)
        content: The page content in storage format (XHTML)
        space_key: Optional space key (defaults to test space from credentials)
        parent_id: Optional parent page ID (creates at root if None)

    Returns:
        Dict containing:
            - page_id: Created page ID (str)
            - space_key: Space key where page was created (str)
            - title: Page title (str)
            - version: Initial version number (int, always 1)

    Raises:
        InvalidCredentialsError: If test credentials are invalid
        PageAlreadyExistsError: If page with same title already exists
        APIUnreachableError: If API is unreachable
        APIAccessError: If API access fails

    Example:
        >>> page_info = setup_test_page(
        ...     "Test Page 123",
        ...     "<p>Test content</p>"
        ... )
        >>> print(page_info['page_id'])
        >>> teardown_test_page(page_info['page_id'])
    """
    # Get test credentials
    creds = get_test_credentials()
    if space_key is None:
        space_key = creds['test_space']

    # Initialize API
    auth = Authenticator()
    api = APIWrapper(auth)

    # PRE-CLEANUP: Check if page with same title already exists
    # If it does, delete it first to avoid "page already exists" errors
    # This handles interrupted test runs that didn't clean up properly
    try:
        existing_page = api.get_page_by_title(space=space_key, title=title)
        if existing_page:
            existing_id = existing_page.get('id')
            logger.warning(
                f"Pre-cleanup: Found existing page '{title}' (ID {existing_id}) from previous test run. "
                f"Deleting before creating new page..."
            )
            api.delete_page(existing_id)
            logger.info(f"Pre-cleanup: Deleted existing page '{title}' (ID {existing_id})")
    except Exception as e:
        # If get_page_by_title fails (e.g., page not found), that's fine - we'll create a new one
        logger.debug(f"Pre-cleanup check for '{title}': {e}")

    # Create the page
    result = api.create_page(
        space=space_key,
        title=title,
        body=content,
        parent_id=parent_id
    )
    page_id = result.get("id") if isinstance(result, dict) else str(result)

    logger.info(f"Created test page '{title}' with ID {page_id} in space {space_key}")

    return {
        'page_id': page_id,
        'space_key': space_key,
        'title': title,
        'version': 1,
    }


def teardown_test_page(page_id: str) -> None:
    """Delete a test page from Confluence.

    This helper deletes a page created by setup_test_page(). It should be
    called in test cleanup/teardown to ensure test pages don't accumulate.

    Args:
        page_id: The page ID to delete

    Raises:
        InvalidCredentialsError: If test credentials are invalid
        PageNotFoundError: If page doesn't exist (ignored - already deleted)
        APIUnreachableError: If API is unreachable
        APIAccessError: If API access fails

    Example:
        >>> page_info = setup_test_page("Test Page", "<p>Content</p>")
        >>> # ... run tests ...
        >>> teardown_test_page(page_info['page_id'])
    """
    auth = Authenticator()
    api = APIWrapper(auth)

    try:
        # Delete the page using the API wrapper
        api.delete_page(page_id)
        logger.info(f"Deleted test page with ID {page_id}")
    except Exception as e:
        # If page not found, it's already deleted (not an error)
        error_msg = str(e).lower()
        if '404' in error_msg or 'not found' in error_msg:
            logger.warning(f"Page {page_id} not found (already deleted)")
            return

        # Re-raise other errors
        logger.error(f"Failed to delete test page {page_id}: {e}")
        raise
