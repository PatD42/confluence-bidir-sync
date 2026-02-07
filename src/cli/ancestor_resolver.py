"""Ancestor resolver for CQL ancestors parsing and hierarchy resolution.

This module implements CQL-based ancestor fetching to detect page moves
by comparing ancestor chains. It uses the Confluence API with expand=ancestors
to retrieve full parent hierarchies and builds local paths from the ancestor chain.
"""

import logging
import os
from typing import Dict, List, Optional

from ..confluence_client.api_wrapper import APIWrapper
from ..confluence_client.auth import Authenticator
from ..confluence_client.errors import (
    APIAccessError,
    PageNotFoundError,
)
from .errors import CLIError

logger = logging.getLogger(__name__)


class AncestorResolver:
    """Resolves page ancestors for move detection.

    This class fetches pages from Confluence with their complete ancestor chains
    using the expand=ancestors parameter. It provides methods to:
    - Fetch pages with full ancestor data via CQL
    - Extract parent chains from ancestor data
    - Build local file paths from ancestor hierarchies

    The ancestor data is used for move detection (ADR-014) by comparing
    current ancestor chains against expected paths from the local file system.

    Example:
        >>> auth = Authenticator()
        >>> resolver = AncestorResolver()
        >>> pages = resolver.fetch_with_ancestors(
        ...     space_key="TEAM",
        ...     page_ids=["123", "456"]
        ... )
        >>> for page_id, data in pages.items():
        ...     print(f"Page {page_id} ancestors: {data.get('ancestors', [])}")
    """

    def __init__(self, api: Optional[APIWrapper] = None):
        """Initialize AncestorResolver with optional API wrapper.

        Args:
            api: APIWrapper instance. If None, creates one with
                 default authentication.
        """
        if api is None:
            auth = Authenticator()
            api = APIWrapper(auth)
        self.api = api

    def fetch_with_ancestors(
        self,
        space_key: str,
        page_ids: List[str]
    ) -> Dict[str, Dict]:
        """Fetch pages with their ancestor chains using CQL.

        This method fetches multiple pages by ID and includes their complete
        ancestor chains using the expand=ancestors parameter. This is used
        for move detection by comparing the current ancestor chain against
        the expected parent hierarchy from the local file structure.

        Args:
            space_key: Confluence space key (for validation/logging)
            page_ids: List of page IDs to fetch with ancestors

        Returns:
            Dict mapping page_id to page data (including 'ancestors' field)
            The ancestors field is a list ordered from root to immediate parent.

        Raises:
            CLIError: If API access fails or pages cannot be fetched
            PageNotFoundError: If a page doesn't exist (logged and skipped)

        Example:
            >>> pages = resolver.fetch_with_ancestors("TEAM", ["123", "456"])
            >>> page_data = pages["123"]
            >>> ancestors = page_data.get("ancestors", [])
            >>> for ancestor in ancestors:
            ...     print(f"Parent: {ancestor['title']}")
        """
        logger.info(
            f"Fetching {len(page_ids)} pages with ancestors from space {space_key}"
        )

        result = {}

        for page_id in page_ids:
            try:
                # Fetch page with ancestors expanded
                page_data = self.api.get_page_by_id(
                    page_id=page_id,
                    expand="ancestors,version,space"
                )

                # Validate space matches (case-insensitive comparison)
                page_space = page_data.get("space", {}).get("key", "")
                if page_space and page_space.lower() != space_key.lower():
                    logger.warning(
                        f"Page {page_id} is in space '{page_space}', "
                        f"not '{space_key}' as expected"
                    )

                # Add to results
                result[page_id] = page_data
                logger.debug(
                    f"Fetched page {page_id}: '{page_data.get('title', 'unknown')}' "
                    f"with {len(page_data.get('ancestors', []))} ancestors"
                )

            except PageNotFoundError as e:
                # Log and skip missing pages - they may have been deleted
                logger.warning(f"Page {page_id} not found (may be deleted): {e}")
                continue

            except Exception as e:
                # Log error and skip this page, but continue with others
                logger.error(f"Error fetching page {page_id} with ancestors: {e}")
                # Don't raise - continue processing other pages
                continue

        logger.info(f"Successfully fetched {len(result)} pages with ancestors")

        if not result and page_ids:
            # All pages failed to fetch - this is an error condition
            raise CLIError(
                f"Failed to fetch any pages from {len(page_ids)} requested "
                f"page IDs in space {space_key}"
            )

        return result

    def get_parent_chain(self, page_data: Dict) -> List[str]:
        """Extract parent chain from page data.

        This method extracts the ancestor chain from the page data returned
        by the Confluence API (with expand=ancestors). The ancestors are
        already ordered from root to immediate parent.

        Args:
            page_data: Page data dictionary from Confluence API including
                      'ancestors' field

        Returns:
            List of page IDs ordered from root to immediate parent.
            Returns empty list if page has no ancestors.

        Example:
            >>> page_data = {
            ...     "id": "123",
            ...     "title": "Child Page",
            ...     "ancestors": [
            ...         {"id": "100", "title": "Root"},
            ...         {"id": "110", "title": "Parent"}
            ...     ]
            ... }
            >>> resolver.get_parent_chain(page_data)
            ['100', '110']
        """
        ancestors = page_data.get("ancestors", [])

        # Extract page IDs from ancestors list
        parent_ids = [ancestor.get("id") for ancestor in ancestors if ancestor.get("id")]

        logger.debug(
            f"Extracted parent chain for page {page_data.get('id', 'unknown')}: "
            f"{len(parent_ids)} ancestors"
        )

        return parent_ids

    def build_path_from_ancestors(
        self,
        page_data: Dict,
        space_key: str,
        base_path: Optional[str] = None
    ) -> str:
        """Build local file path from ancestor hierarchy.

        This method constructs a local file path from the ancestor chain
        by converting ancestor titles to filesafe directory names and
        joining them with the page's own title as the filename.

        Args:
            page_data: Page data dictionary from Confluence API including
                      'ancestors' and 'title' fields
            space_key: Confluence space key (for logging/validation)
            base_path: Optional base directory path. If not provided,
                      uses space_key as base.

        Returns:
            Local file path constructed from ancestor hierarchy and page title.
            Format: "base_path/ancestor1/ancestor2/page-title.md"

        Example:
            >>> page_data = {
            ...     "id": "123",
            ...     "title": "Child Page",
            ...     "ancestors": [
            ...         {"id": "100", "title": "Section A"},
            ...         {"id": "110", "title": "Subsection B"}
            ...     ]
            ... }
            >>> resolver.build_path_from_ancestors(page_data, "TEAM", "/docs")
            '/docs/Section-A/Subsection-B/Child-Page.md'
        """
        from ..file_mapper.filesafe_converter import FilesafeConverter

        # Start with base path (use space_key if not provided)
        if base_path is None:
            base_path = space_key

        path_parts = [base_path]

        # Add ancestor directories
        ancestors = page_data.get("ancestors", [])
        for ancestor in ancestors:
            ancestor_title = ancestor.get("title", "")
            if ancestor_title:
                # Convert title to filesafe directory name (without .md extension)
                # We'll strip the .md extension since this is a directory
                filesafe_name = FilesafeConverter.title_to_filename(ancestor_title)
                if filesafe_name.endswith(".md"):
                    filesafe_name = filesafe_name[:-3]
                path_parts.append(filesafe_name)

        # Add page filename
        page_title = page_data.get("title", "untitled")
        page_filename = FilesafeConverter.title_to_filename(page_title)
        path_parts.append(page_filename)

        # Join all parts
        full_path = os.path.join(*path_parts)

        logger.debug(
            f"Built path for page {page_data.get('id', 'unknown')} "
            f"('{page_title}'): {full_path}"
        )

        return full_path
