"""API wrapper for Confluence Cloud REST API v2.

This module wraps the atlassian-python-api Confluence client and provides
error translation from HTTP exceptions to our typed exception hierarchy.
It integrates with the retry logic for handling rate limits.
"""

import logging
import re
from typing import Dict, Any, Optional, List

from atlassian import Confluence
from requests.exceptions import Timeout, ConnectTimeout, ReadTimeout, ConnectionError

from .auth import Authenticator
from .errors import (
    InvalidCredentialsError,
    PageNotFoundError,
    APIUnreachableError,
    APIAccessError,
)
from .retry_logic import retry_on_rate_limit

logger = logging.getLogger(__name__)


class APIWrapper:
    """Wrapper around atlassian-python-api Confluence client with error translation.

    This class provides a thin wrapper over the Confluence API client that:
    1. Handles authentication using the Authenticator
    2. Translates HTTP errors to typed exceptions
    3. Integrates retry logic for 429 rate limits
    4. Provides a clean interface for Confluence operations

    Example:
        >>> auth = Authenticator()
        >>> api = APIWrapper(auth)
        >>> page = api.get_page_by_id("123456")
    """

    def __init__(self, authenticator: Authenticator):
        """Initialize the API wrapper with authentication credentials.

        Args:
            authenticator: Authenticator instance for loading credentials

        Raises:
            InvalidCredentialsError: If credentials are missing or invalid
        """
        self._authenticator = authenticator
        self._client: Optional[Confluence] = None

    def _get_client(self) -> Confluence:
        """Get or create the Confluence API client.

        This method lazily initializes the Confluence client on first use
        and validates credentials.

        Returns:
            Confluence: Initialized atlassian-python-api Confluence client

        Raises:
            InvalidCredentialsError: If credentials are missing
        """
        if self._client is None:
            creds = self._authenticator.get_credentials()
            self._client = Confluence(
                url=creds.url,
                username=creds.user,
                password=creds.api_token,
                cloud=True,  # Use Confluence Cloud API
                timeout=30,  # 30 second timeout to prevent hanging (H2)
            )
        return self._client

    def _validate_page_id(self, page_id: str) -> None:
        """Validate that a page ID is in the correct format.

        Prevents injection attacks by ensuring page IDs contain only
        numeric characters. Confluence page IDs are always numeric.

        Args:
            page_id: The page ID to validate

        Raises:
            ValueError: If page_id is not a valid numeric string
        """
        if not page_id or not str(page_id).strip():
            raise ValueError("page_id cannot be empty")

        # Page IDs must be numeric only (Confluence uses numeric IDs)
        page_id_str = str(page_id).strip()
        if not re.match(r'^\d+$', page_id_str):
            raise ValueError(
                f"Invalid page_id format: '{page_id}'. "
                f"Page IDs must contain only numeric characters."
            )

    def _sanitize_credentials(self, text: str) -> str:
        """Sanitize error messages to prevent credential leakage.

        Masks API tokens, passwords, and shows only domains for URLs
        and email addresses to prevent information disclosure (H5).

        Args:
            text: The error message or log text to sanitize

        Returns:
            str: Sanitized text with credentials masked

        Example:
            >>> api._sanitize_credentials("Error: token sk-abc123xyz failed")
            "Error: token ***REDACTED*** failed"
            >>> api._sanitize_credentials("https://user:pass@example.com/wiki")
            "https://***:***@example.com/***"
        """
        if not text:
            return text

        sanitized = text

        # Apply sanitization rules in order from most specific to least specific

        # 1. Mask passwords in URLs (user:pass@host) - do this first
        sanitized = re.sub(
            r'://([\w.-]+):([\w.-]+)@',
            r'://***:***@',
            sanitized
        )

        # 2. Mask Authorization headers (match everything after Authorization: until end or newline)
        sanitized = re.sub(
            r'Authorization:\s*[^\n\r]+',
            'Authorization: ***REDACTED***',
            sanitized,
            flags=re.IGNORECASE
        )

        # 3. Mask Bearer tokens
        sanitized = re.sub(
            r'Bearer\s+[^\s\n\r]+',
            'Bearer ***REDACTED***',
            sanitized,
            flags=re.IGNORECASE
        )

        # 4. Mask password field values (password=xyz or password: "xyz")
        sanitized = re.sub(
            r'password["\']?\s*[:=]\s*["\']?([^"\'\s&]+)',
            r'password=***REDACTED***',
            sanitized,
            flags=re.IGNORECASE
        )

        # 5. Mask API token field values (api_token=xyz, token=xyz, etc.)
        sanitized = re.sub(
            r'(api_?token|token)["\']?\s*[:=]\s*["\']?([^"\'\s&]+)',
            r'\1=***REDACTED***',
            sanitized,
            flags=re.IGNORECASE
        )

        # 6. Mask email addresses (show domain only)
        sanitized = re.sub(
            r'\b[\w.-]+@([\w.-]+\.[a-z]{2,})\b',
            r'***@\1',
            sanitized,
            flags=re.IGNORECASE
        )

        # 7. Mask token-like patterns (prefixed tokens like sk-*, xoxb-*)
        # Only match if there's a clear prefix followed by dash
        sanitized = re.sub(
            r'\b[a-zA-Z]{2,4}-[a-zA-Z0-9]{8,}\b',
            '***REDACTED***',
            sanitized
        )

        # 8. Mask long alphanumeric strings in token context (after "with token", "token:", etc.)
        sanitized = re.sub(
            r'(with\s+token|token[:\s]+)["\']?([a-zA-Z0-9-]{8,})',
            r'\1***REDACTED***',
            sanitized,
            flags=re.IGNORECASE
        )

        return sanitized

    def _translate_error(self, exception: Exception, operation: str) -> Exception:
        """Translate HTTP exceptions to typed Confluence exceptions.

        Args:
            exception: The original exception from the API client
            operation: Description of the operation that failed (for logging)

        Returns:
            Exception: Translated exception (one of our typed exceptions)
        """
        # Check for timeout exceptions first (H2: prevent hangs)
        if isinstance(exception, (Timeout, ConnectTimeout, ReadTimeout, ConnectionError)):
            creds = self._authenticator.get_credentials()
            return APIUnreachableError(endpoint=creds.url)

        error_msg = str(exception).lower()

        # Check for 401 Unauthorized - invalid credentials
        if '401' in error_msg or 'unauthorized' in error_msg:
            creds = self._authenticator.get_credentials()
            return InvalidCredentialsError(
                user=creds.user,
                endpoint=creds.url
            )

        # Check for 404 Not Found - page doesn't exist
        if '404' in error_msg or 'not found' in error_msg or 'no content' in error_msg:
            # Extract page ID from operation string (e.g., "get_page_by_id(123456)")
            page_id = "unknown"
            import re
            match = re.search(r'\(([^)]+)\)', operation)
            if match:
                page_id = match.group(1)
            return PageNotFoundError(page_id=page_id)

        # Check for network/connection errors
        if any(keyword in error_msg for keyword in [
            'connection',
            'timeout',
            'unreachable',
            'network',
            'failed to connect',
        ]):
            creds = self._authenticator.get_credentials()
            return APIUnreachableError(endpoint=creds.url)

        # Check status_code attribute (common in HTTP libraries)
        if hasattr(exception, 'status_code'):
            status_code = exception.status_code
            if status_code == 401:
                creds = self._authenticator.get_credentials()
                return InvalidCredentialsError(
                    user=creds.user,
                    endpoint=creds.url
                )
            elif status_code == 404:
                return PageNotFoundError(page_id="unknown")

        # Check response.status_code (requests library pattern)
        if hasattr(exception, 'response') and hasattr(exception.response, 'status_code'):
            status_code = exception.response.status_code
            if status_code == 401:
                creds = self._authenticator.get_credentials()
                return InvalidCredentialsError(
                    user=creds.user,
                    endpoint=creds.url
                )
            elif status_code == 404:
                return PageNotFoundError(page_id="unknown")

        # Default to generic API access error
        # Sanitize error message to prevent credential leakage (H5)
        safe_error_msg = self._sanitize_credentials(str(exception))
        logger.error(f"API operation failed: {operation} - {safe_error_msg}")
        return APIAccessError(f"Confluence API failure during {operation}")

    def get_page_by_id(
        self,
        page_id: str,
        expand: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch a page by its ID.

        Args:
            page_id: The Confluence page ID
            expand: Optional comma-separated list of properties to expand
                   (e.g., "body.storage,version")

        Returns:
            Dict containing page data from Confluence API

        Raises:
            InvalidCredentialsError: If credentials are invalid
            PageNotFoundError: If page doesn't exist
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails after retries
        """
        # Validate input to prevent injection attacks
        self._validate_page_id(page_id)

        def _fetch():
            try:
                client = self._get_client()
                return client.get_page_by_id(
                    page_id=page_id,
                    expand=expand or "space,body.storage,version"
                )
            except Exception as e:
                # Translate the error
                raise self._translate_error(e, f"get_page_by_id({page_id})") from e

        # Use retry logic for rate limits
        return retry_on_rate_limit(_fetch)

    def get_page_by_title(
        self,
        space: str,
        title: str,
        expand: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch a page by space and title.

        Args:
            space: The space key
            title: The page title
            expand: Optional comma-separated list of properties to expand

        Returns:
            Dict containing page data, or None if not found

        Raises:
            InvalidCredentialsError: If credentials are invalid
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails after retries
        """
        def _fetch():
            try:
                client = self._get_client()
                return client.get_page_by_title(
                    space=space,
                    title=title,
                    expand=expand or "space,body.storage,version"
                )
            except Exception as e:
                # For get_page_by_title, 404 means page doesn't exist (not an error)
                error_msg = str(e).lower()
                if '404' in error_msg or 'not found' in error_msg:
                    return None
                # Translate other errors
                raise self._translate_error(e, f"get_page_by_title({space}, {title})") from e

        # Use retry logic for rate limits
        return retry_on_rate_limit(_fetch)  # type: ignore[no-any-return]

    def get_page_version(
        self,
        page_id: str,
        version: int,
        expand: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch a specific version of a page.

        Args:
            page_id: The Confluence page ID
            version: The version number to fetch
            expand: Optional comma-separated list of properties to expand

        Returns:
            Dict containing page data from the specified version

        Raises:
            InvalidCredentialsError: If credentials are invalid
            PageNotFoundError: If page or version doesn't exist
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails after retries
        """
        # Validate input to prevent injection attacks
        self._validate_page_id(page_id)

        def _fetch():
            try:
                client = self._get_client()
                # Use the history API to get a specific version
                # The status=historical parameter is needed for old versions
                result = client.get(
                    f"rest/api/content/{page_id}",
                    params={
                        "status": "historical",
                        "version": version,
                        "expand": expand or "body.storage,version"
                    }
                )
                return result
            except Exception as e:
                raise self._translate_error(e, f"get_page_version({page_id}, v{version})") from e

        return retry_on_rate_limit(_fetch)

    def update_page(
        self,
        page_id: str,
        title: str,
        body: str,
        version: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Update a page's content.

        Args:
            page_id: The Confluence page ID
            title: The page title
            body: The page content in storage format (XHTML)
            version: The current version number (will be incremented)
            **kwargs: Additional parameters to pass to the API

        Returns:
            Dict containing updated page data

        Raises:
            InvalidCredentialsError: If credentials are invalid
            PageNotFoundError: If page doesn't exist
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails after retries or version conflict
        """
        # Validate input to prevent injection attacks
        self._validate_page_id(page_id)

        def _update():
            try:
                client = self._get_client()
                # Note: atlassian-python-api auto-increments version internally
                return client.update_page(
                    page_id=page_id,
                    title=title,
                    body=body,
                    **kwargs
                )
            except Exception as e:
                # Check for 409 version conflict
                error_msg = str(e).lower()
                if '409' in error_msg or 'conflict' in error_msg:
                    raise APIAccessError(
                        f"Version conflict updating page {page_id} "
                        f"(version {version} is stale)"
                    )
                # Translate other errors
                raise self._translate_error(e, f"update_page({page_id})") from e

        # Use retry logic for rate limits
        return retry_on_rate_limit(_update)

    def create_page(
        self,
        space: str,
        title: str,
        body: str,
        parent_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a new page.

        Args:
            space: The space key where page will be created
            title: The page title
            body: The page content in storage format (XHTML)
            parent_id: Optional parent page ID
            **kwargs: Additional parameters to pass to the API

        Returns:
            Dict containing created page data

        Raises:
            InvalidCredentialsError: If credentials are invalid
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails after retries
        """
        def _create():
            try:
                client = self._get_client()
                return client.create_page(
                    space=space,
                    title=title,
                    body=body,
                    parent_id=parent_id,
                    **kwargs
                )
            except Exception as e:
                # Translate errors
                raise self._translate_error(e, f"create_page({space}, {title})") from e

        # Use retry logic for rate limits
        return retry_on_rate_limit(_create)

    def get_page_child_by_type(
        self,
        page_id: str,
        child_type: str = "page",
        expand: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get child pages of a given page.

        Args:
            page_id: The parent page ID
            child_type: The type of children to fetch (default: "page")
            expand: Optional comma-separated list of properties to expand

        Returns:
            Dict containing list of child pages

        Raises:
            InvalidCredentialsError: If credentials are invalid
            PageNotFoundError: If page doesn't exist
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails after retries
        """
        # Validate input to prevent injection attacks
        self._validate_page_id(page_id)

        def _fetch():
            try:
                client = self._get_client()
                return client.get_page_child_by_type(
                    page_id=page_id,
                    type=child_type,
                    expand=expand
                )
            except Exception as e:
                # Translate errors
                raise self._translate_error(e, f"get_page_child_by_type({page_id})") from e

        # Use retry logic for rate limits
        return retry_on_rate_limit(_fetch)

    def delete_page(self, page_id: str) -> None:
        """Delete a page by its ID.

        Args:
            page_id: The Confluence page ID to delete

        Raises:
            InvalidCredentialsError: If credentials are invalid
            PageNotFoundError: If page doesn't exist
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails after retries
        """
        # Validate input to prevent injection attacks
        self._validate_page_id(page_id)

        def _delete():
            try:
                client = self._get_client()
                # atlassian-python-api uses remove_page method
                client.remove_page(page_id)
            except Exception as e:
                # Translate errors
                raise self._translate_error(e, f"delete_page({page_id})") from e

        # Use retry logic for rate limits
        retry_on_rate_limit(_delete)

    def get_space(
        self,
        space_key: str,
        expand: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get space information including homepage.

        Args:
            space_key: The space key (e.g., "TEAM")
            expand: Optional comma-separated list of properties to expand
                   (default: "homepage" to get the space's homepage ID)

        Returns:
            Dict containing space data including homepage if expanded:
            - key: Space key
            - name: Space name
            - homepage: Dict with 'id' and 'title' (if expanded)

        Raises:
            InvalidCredentialsError: If credentials are invalid
            PageNotFoundError: If space doesn't exist
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails after retries
        """
        def _fetch():
            try:
                client = self._get_client()
                return client.get_space(
                    space_key=space_key,
                    expand=expand or "homepage"
                )
            except Exception as e:
                # Translate errors
                raise self._translate_error(e, f"get_space({space_key})") from e

        # Use retry logic for rate limits
        return retry_on_rate_limit(_fetch)

    def search_by_cql(
        self,
        cql: str,
        start: int = 0,
        limit: int = 25,
        expand: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for content using Confluence Query Language (CQL).

        Args:
            cql: The CQL query string (e.g., "type=page AND space=DEV")
            start: Starting index for pagination (default: 0)
            limit: Maximum number of results to return (default: 25)
            expand: Optional comma-separated list of properties to expand

        Returns:
            Dict containing search results with pagination metadata:
            - results: List of matching content items
            - start: Starting index of results
            - limit: Maximum results per page
            - size: Number of results in this response
            - totalSize: Total number of matching results (if available)

        Raises:
            InvalidCredentialsError: If credentials are invalid
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails after retries
        """
        def _search():
            try:
                client = self._get_client()
                return client.cql(
                    cql=cql,
                    start=start,
                    limit=limit,
                    expand=expand
                )
            except Exception as e:
                # Translate errors
                raise self._translate_error(e, f"search_by_cql({cql[:50]}...)") from e

        # Use retry logic for rate limits
        return retry_on_rate_limit(_search)

    def get_page_adf(
        self,
        page_id: str,
    ) -> Dict[str, Any]:
        """Fetch a page's content in ADF (Atlassian Document Format).

        ADF is Confluence's JSON-based document format. Each node in ADF
        has a localId that can be used for surgical updates.

        Args:
            page_id: The Confluence page ID

        Returns:
            Dict containing:
            - id: Page ID
            - title: Page title
            - version: Version info
            - body: Dict with 'atlas_doc_format' containing ADF JSON

        Raises:
            InvalidCredentialsError: If credentials are invalid
            PageNotFoundError: If page doesn't exist
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails after retries
        """
        # Validate input to prevent injection attacks
        self._validate_page_id(page_id)

        def _fetch():
            try:
                client = self._get_client()
                # Use body.atlas_doc_format to get ADF instead of storage format
                return client.get_page_by_id(
                    page_id=page_id,
                    expand="body.atlas_doc_format,version"
                )
            except Exception as e:
                raise self._translate_error(e, f"get_page_adf({page_id})") from e

        return retry_on_rate_limit(_fetch)

    def update_page_adf(
        self,
        page_id: str,
        title: str,
        adf_content: Dict[str, Any],
        version: int,
    ) -> Dict[str, Any]:
        """Update a page using ADF (Atlassian Document Format).

        This method updates page content using ADF JSON rather than XHTML.
        ADF updates preserve localIds and allow surgical modifications.

        Args:
            page_id: The Confluence page ID
            title: The page title
            adf_content: The ADF document as a dictionary
            version: The current version number (for optimistic locking)

        Returns:
            Dict containing updated page data

        Raises:
            InvalidCredentialsError: If credentials are invalid
            PageNotFoundError: If page doesn't exist
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails (including version conflict)
        """
        # Validate input to prevent injection attacks
        self._validate_page_id(page_id)

        def _update():
            try:
                client = self._get_client()
                import json

                # Prepare the update payload for ADF format
                # Confluence API requires specific structure for atlas_doc_format
                payload = {
                    "version": {"number": version + 1},
                    "title": title,
                    "type": "page",
                    "body": {
                        "atlas_doc_format": {
                            "value": json.dumps(adf_content),
                            "representation": "atlas_doc_format"
                        }
                    }
                }

                # Use the underlying requests session for direct API call
                # The atlassian-python-api doesn't have native ADF support
                # client.url already includes /wiki, so just append the API path
                response = client._session.put(
                    f"{client.url}/rest/api/content/{page_id}",
                    json=payload
                )

                if response.status_code == 409:
                    raise APIAccessError(
                        f"Version conflict updating page {page_id} "
                        f"(version {version} is stale)"
                    )

                response.raise_for_status()
                return response.json()

            except APIAccessError:
                raise
            except Exception as e:
                error_msg = str(e).lower()
                if '409' in error_msg or 'conflict' in error_msg:
                    raise APIAccessError(
                        f"Version conflict updating page {page_id} "
                        f"(version {version} is stale)"
                    )
                raise self._translate_error(e, f"update_page_adf({page_id})") from e

        return retry_on_rate_limit(_update)
