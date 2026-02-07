"""Test Confluence credentials fixture.

Loads test account credentials from .env.test file.
Used by integration and E2E tests.
"""

import os
from typing import Dict
from pathlib import Path
from dotenv import load_dotenv


def get_test_credentials() -> Dict[str, str]:
    """Load test Confluence credentials from .env.test file.

    Returns:
        Dict containing:
            - confluence_url: Confluence instance URL
            - confluence_user: User email
            - confluence_api_token: API token
            - test_space: Test space key

    Raises:
        FileNotFoundError: If .env.test file not found
        ValueError: If required credentials are missing (including CONFLUENCE_TEST_SPACE)

    Example:
        >>> creds = get_test_credentials()
        >>> print(creds['confluence_url'])
        https://yourinstance.atlassian.net/wiki
    """
    # Find .env.test in repository root
    # Working directory is the repository root
    env_test_path = Path('.env.test')

    if not env_test_path.exists():
        raise FileNotFoundError(
            ".env.test file not found. "
            "Create it from .env.test.example with test Confluence credentials."
        )

    # Load from .env.test
    load_dotenv(env_test_path)

    # Extract required credentials
    confluence_url = os.getenv('CONFLUENCE_URL')
    confluence_user = os.getenv('CONFLUENCE_USER')
    confluence_api_token = os.getenv('CONFLUENCE_API_TOKEN')
    test_space = os.getenv('CONFLUENCE_TEST_SPACE')  # Optional

    # Validate required credentials
    missing = []
    if not confluence_url:
        missing.append('CONFLUENCE_URL')
    if not confluence_user:
        missing.append('CONFLUENCE_USER')
    if not confluence_api_token:
        missing.append('CONFLUENCE_API_TOKEN')
    if not test_space:
        missing.append('CONFLUENCE_TEST_SPACE')

    if missing:
        raise ValueError(
            f"Missing required credentials in .env.test: {', '.join(missing)}. "
            "CONFLUENCE_TEST_SPACE must be set to a valid Confluence space key for E2E tests."
        )

    return {
        'confluence_url': confluence_url,
        'confluence_user': confluence_user,
        'confluence_api_token': confluence_api_token,
        'test_space': test_space,
    }
