"""InitCommand for configuration initialization.

This module implements the --init command that creates sync configuration
by parsing a Confluence URL and setting up the local directory structure.
"""

import os
import re
import logging
from typing import Optional, Tuple
from urllib.parse import urlparse

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator
from src.file_mapper.config_loader import ConfigLoader
from src.file_mapper.models import SpaceConfig, SyncConfig
from .errors import InitError

logger = logging.getLogger(__name__)


class InitCommand:
    """Handles initialization of sync configuration.

    The InitCommand parses a Confluence page URL to extract space key and
    page ID, validates that the page exists, and creates the
    .confluence-sync/config.yaml file with the proper structure.

    Example:
        >>> init = InitCommand()
        >>> init.run(
        ...     local_path="./docs",
        ...     confluence_url="https://example.atlassian.net/wiki/spaces/TEAM/pages/123456",
        ...     exclude_parent=False
        ... )
    """

    # Default config file path
    DEFAULT_CONFIG_PATH = ".confluence-sync/config.yaml"

    # Regex patterns for different Confluence URL formats
    # Pattern 1: URL with page ID - /spaces/SPACE/pages/PAGE_ID[/title]
    URL_WITH_PAGE_ID = re.compile(
        r'^(https?://[^/]+)(/wiki)?/spaces/([^/]+)/pages/(\d+)(?:/.*)?$'
    )
    # Pattern 2: Space overview or space root - /spaces/SPACE[/overview]
    URL_SPACE_ONLY = re.compile(
        r'^(https?://[^/]+)(/wiki)?/spaces/([^/]+)(?:/overview)?/?$'
    )

    def __init__(
        self,
        api_wrapper: Optional[APIWrapper] = None,
        config_path: Optional[str] = None
    ):
        """Initialize the init command.

        Args:
            api_wrapper: Optional APIWrapper instance for testing
            config_path: Optional config file path (defaults to .confluence-sync/config.yaml)
        """
        self.api_wrapper = api_wrapper
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH

    def _get_api_wrapper(self) -> APIWrapper:
        """Get or create the API wrapper.

        Returns:
            APIWrapper instance

        Raises:
            InitError: If credentials are not configured
        """
        if self.api_wrapper is None:
            try:
                auth = Authenticator()
                self.api_wrapper = APIWrapper(auth)
            except Exception as e:
                raise InitError(
                    f"Failed to initialize Confluence API client: {str(e)}\n"
                    "Please ensure CONFLUENCE_URL, CONFLUENCE_USER, and "
                    "CONFLUENCE_API_TOKEN environment variables are set."
                )
        return self.api_wrapper

    def _validate_url(self, url: str) -> None:
        """Validate that a URL has proper structure.

        Uses urlparse() to ensure URL has valid scheme and netloc
        to prevent malformed URLs from causing crashes (M4).

        Args:
            url: URL to validate

        Raises:
            InitError: If URL is malformed or missing required components
        """
        if not url or not url.strip():
            raise InitError("URL cannot be empty")

        try:
            parsed = urlparse(url)

            # Check for valid scheme (http or https)
            if not parsed.scheme or parsed.scheme not in ('http', 'https'):
                raise InitError(
                    f"Invalid URL scheme: '{parsed.scheme or '(missing)'}'\n"
                    f"URL must start with http:// or https://"
                )

            # Check for valid netloc (domain)
            if not parsed.netloc or not parsed.netloc.strip():
                raise InitError(
                    f"Invalid URL: missing domain name\n"
                    f"URL must include a domain (e.g., example.atlassian.net)"
                )

        except Exception as e:
            raise InitError(f"Malformed URL: {e}")

    def _parse_confluence_url(self, url: str) -> Tuple[str, str, Optional[str]]:
        """Parse a Confluence page URL to extract components.

        Supports multiple URL formats:
        1. With page ID: https://domain.atlassian.net/wiki/spaces/TEAM/pages/123456
        2. With page ID and title: https://domain.atlassian.net/wiki/spaces/TEAM/pages/123456/Page-Title
        3. Space overview: https://domain.atlassian.net/wiki/spaces/TEAM/overview
        4. Space root: https://domain.atlassian.net/wiki/spaces/TEAM

        Args:
            url: Full Confluence URL from browser

        Returns:
            Tuple of (base_url, space_key, page_id)
            - base_url: https://example.atlassian.net/wiki
            - space_key: TEAM
            - page_id: 123456 or None (if not in URL)

        Raises:
            InitError: If URL format is invalid
        """
        # Validate URL structure first (M4: URL validation)
        self._validate_url(url)
        # Try URL with page ID first
        match = self.URL_WITH_PAGE_ID.match(url)
        if match:
            domain = match.group(1)
            wiki_path = match.group(2) or ""
            space_key = match.group(3)
            page_id = match.group(4)
            base_url = f"{domain}{wiki_path}" if wiki_path else f"{domain}/wiki"
            return base_url, space_key, page_id

        # Try space-only URL
        match = self.URL_SPACE_ONLY.match(url)
        if match:
            domain = match.group(1)
            wiki_path = match.group(2) or ""
            space_key = match.group(3)
            base_url = f"{domain}{wiki_path}" if wiki_path else f"{domain}/wiki"
            # page_id is None - will be resolved via API
            return base_url, space_key, None

        # URL didn't match any known pattern
        raise InitError(
            f"Invalid Confluence URL format: '{url}'\n"
            "Supported formats:\n"
            "  - https://domain.atlassian.net/wiki/spaces/SPACE/pages/PAGE_ID\n"
            "  - https://domain.atlassian.net/wiki/spaces/SPACE/overview\n"
            "  - https://domain.atlassian.net/wiki/spaces/SPACE\n"
            "You can copy this URL directly from your browser."
        )

    def _get_space_homepage(self, space_key: str) -> Tuple[str, str]:
        """Get the homepage of a Confluence space.

        Args:
            space_key: Confluence space key

        Returns:
            Tuple of (page_id, page_title)

        Raises:
            InitError: If space not found or has no homepage
        """
        api = self._get_api_wrapper()

        try:
            # Get space info with homepage expansion
            space_data = api.get_space(space_key, expand="homepage")

            if space_data is None:
                raise InitError(
                    f"Space not found: '{space_key}'\n"
                    "Please verify the space key in your URL."
                )

            # Get homepage from space data
            homepage = space_data.get('homepage')
            if homepage is None:
                # Try to get homepage ID directly
                homepage_id = space_data.get('homepageId')
                if homepage_id:
                    page_data = api.get_page_by_id(str(homepage_id))
                    if page_data:
                        return str(homepage_id), page_data.get('title', 'Unknown')

                raise InitError(
                    f"Space '{space_key}' has no homepage.\n"
                    "Please provide a URL with a specific page ID."
                )

            page_id = str(homepage.get('id'))
            page_title = homepage.get('title', 'Unknown')

            logger.info(f"Resolved space homepage: '{page_title}' (ID: {page_id})")
            return page_id, page_title

        except InitError:
            raise
        except Exception as e:
            raise InitError(
                f"Failed to get space homepage for '{space_key}': {str(e)}"
            )

    def _validate_page_exists(self, page_id: str, space_key: str) -> str:
        """Validate that the page exists and return its title.

        Args:
            page_id: Confluence page ID
            space_key: Confluence space key

        Returns:
            Page title

        Raises:
            InitError: If page not found or API error occurs
        """
        api = self._get_api_wrapper()

        try:
            page_data = api.get_page_by_id(page_id)

            if page_data is None:
                raise InitError(
                    f"Page not found: ID '{page_id}' in space '{space_key}'\n"
                    "Please verify the URL points to an existing Confluence page."
                )

            title = page_data.get('title', 'Unknown')
            logger.info(f"Validated page '{title}' (ID: {page_id}) in space {space_key}")
            return title

        except InitError:
            raise
        except Exception as e:
            raise InitError(
                f"Failed to validate page '{page_id}': {str(e)}"
            )

    def _check_config_exists(self) -> None:
        """Check if config file already exists.

        Raises:
            InitError: If config file already exists
        """
        if os.path.exists(self.config_path):
            raise InitError(
                f"Configuration file already exists at {self.config_path}\n"
                "Please delete it first if you want to reinitialize."
            )

    def _create_directories(self, local_path: str) -> None:
        """Create necessary directories.

        Creates both the .confluence-sync directory and the local sync directory.

        Args:
            local_path: Local directory path for synced files

        Raises:
            InitError: If directory creation fails
        """
        # Normalize path (remove trailing slash, etc.)
        local_path = os.path.normpath(local_path)

        # Create .confluence-sync directory
        config_dir = os.path.dirname(self.config_path)
        if config_dir:
            try:
                os.makedirs(config_dir, exist_ok=True)
                logger.info(f"Created config directory: {config_dir}")
            except Exception as e:
                raise InitError(
                    f"Failed to create config directory {config_dir}: {str(e)}"
                )

        # Create local sync directory
        try:
            os.makedirs(local_path, exist_ok=True)
            logger.info(f"Created local sync directory: {local_path}")
        except Exception as e:
            raise InitError(
                f"Failed to create local directory {local_path}: {str(e)}"
            )

    def run(
        self,
        local_path: str,
        confluence_url: str,
        exclude_parent: bool = False
    ) -> None:
        """Run the init command to create sync configuration.

        Args:
            local_path: Local directory path for synced files
            confluence_url: Full Confluence page URL (copy from browser)
            exclude_parent: If True, exclude the parent page from sync

        Raises:
            InitError: If initialization fails at any step
        """
        # Check if config already exists
        self._check_config_exists()

        # Parse Confluence URL
        base_url, space_key, page_id = self._parse_confluence_url(confluence_url)
        logger.info(f"Parsed URL: base={base_url}, space={space_key}, page_id={page_id or '(none - will resolve)'}")

        # Resolve page ID if not in URL (get space homepage)
        if page_id is None:
            logger.info(f"No page ID in URL, getting homepage for space '{space_key}'")
            page_id, page_title = self._get_space_homepage(space_key)
        else:
            # Validate page exists
            page_title = self._validate_page_exists(page_id, space_key)

        # Normalize local path
        local_path = os.path.normpath(local_path)

        # Create directories
        self._create_directories(local_path)

        # Create sync configuration
        space_config = SpaceConfig(
            space_key=space_key,
            parent_page_id=page_id,
            local_path=local_path,
            exclude_page_ids=[],
            exclude_parent=exclude_parent,
            confluence_base_url=base_url
        )

        sync_config = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=".confluence-sync/temp"
        )

        # Save configuration
        try:
            ConfigLoader.save(self.config_path, sync_config)
            logger.info(f"Configuration saved to {self.config_path}")
        except Exception as e:
            raise InitError(
                f"Failed to save configuration: {str(e)}"
            )

        # Log summary
        logger.info(f"Initialized sync for '{page_title}' (ID: {page_id})")
        if exclude_parent:
            logger.info("  Parent page excluded - only children will be synced")
