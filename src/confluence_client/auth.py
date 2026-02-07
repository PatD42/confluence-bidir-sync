"""Authentication module for loading Confluence credentials.

This module handles loading Confluence Cloud credentials from environment variables
using python-dotenv. It validates that all required credentials are present and
raises appropriate errors if any are missing.
"""

import os
from typing import NamedTuple

from dotenv import load_dotenv

from .errors import InvalidCredentialsError


class Credentials(NamedTuple):
    """Confluence API credentials."""
    url: str
    user: str
    api_token: str


class Authenticator:
    """Loads and validates Confluence credentials from environment variables.

    Credentials are loaded from a .env file using python-dotenv and are never
    cached or logged to prevent security risks.

    Required environment variables:
        CONFLUENCE_URL: Confluence instance URL (e.g., https://yourinstance.atlassian.net/wiki)
        CONFLUENCE_USER: Confluence user email address
        CONFLUENCE_API_TOKEN: Confluence API token

    Raises:
        InvalidCredentialsError: If any required credential is missing

    Example:
        >>> auth = Authenticator()
        >>> creds = auth.get_credentials()
        >>> print(f"Connecting to {creds.url}")
    """

    def __init__(self):
        """Initialize the authenticator by loading environment variables from .env file."""
        # Load environment variables from .env file
        load_dotenv()

    def get_credentials(self) -> Credentials:
        """Get Confluence credentials from environment variables.

        Returns:
            Credentials: A named tuple containing url, user, and api_token

        Raises:
            InvalidCredentialsError: If any required credential is missing
        """
        url = os.getenv('CONFLUENCE_URL')
        user = os.getenv('CONFLUENCE_USER')
        api_token = os.getenv('CONFLUENCE_API_TOKEN')

        # Validate that all credentials are present
        missing = []
        if not url:
            missing.append('CONFLUENCE_URL')
        if not user:
            missing.append('CONFLUENCE_USER')
        if not api_token:
            missing.append('CONFLUENCE_API_TOKEN')

        if missing:
            # Raise InvalidCredentialsError with the first missing credential
            # Use a generic endpoint since we don't have the URL yet
            endpoint = url if url else "unknown"
            raise InvalidCredentialsError(
                user=user if user else "unknown",
                endpoint=endpoint
            )

        # Type checker: these are guaranteed to be str due to validation above
        return Credentials(url=url, user=user, api_token=api_token)  # type: ignore[arg-type]
