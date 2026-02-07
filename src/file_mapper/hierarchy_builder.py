"""Hierarchy builder for discovering Confluence page hierarchies using CQL.

This module implements CQL-based page discovery to build a tree structure
representing the Confluence page hierarchy. It enforces the 100 page limit
per level (ADR-013) and uses recursive tree building to represent parent-child
relationships.
"""

import logging
from typing import List, Dict, Any, Optional

from ..confluence_client.api_wrapper import APIWrapper
from ..confluence_client.auth import Authenticator
from ..confluence_client.errors import (
    PageNotFoundError,
    APIUnreachableError,
    APIAccessError,
    InvalidCredentialsError,
)
from ..content_converter.markdown_converter import MarkdownConverter
from .models import PageNode
from .errors import PageLimitExceededError

logger = logging.getLogger(__name__)


class HierarchyBuilder:
    """Builds page hierarchy trees using CQL queries.

    This class uses CQL (Confluence Query Language) to discover pages
    under a parent page and builds a recursive tree structure. It enforces
    the page limit per level (ADR-013) and provides clear error messages
    when limits are exceeded.

    The CQL query pattern is: `parent = {page_id}`
    This returns all direct children of the specified page.

    Example:
        >>> auth = Authenticator()
        >>> builder = HierarchyBuilder(auth)
        >>> tree = builder.build_hierarchy("123456", "TEAM", page_limit=100)
        >>> print(f"Root page has {len(tree.children)} children")
    """

    def __init__(self, authenticator: Authenticator):
        """Initialize the hierarchy builder with authentication.

        Args:
            authenticator: Authenticator instance for Confluence API access
        """
        self._api = APIWrapper(authenticator)
        self._converter = MarkdownConverter()

    def build_hierarchy(
        self,
        parent_page_id: str,
        space_key: str,
        page_limit: int = 100,
        exclude_page_ids: Optional[List[str]] = None
    ) -> PageNode:
        """Build a complete page hierarchy starting from a parent page.

        This method fetches the parent page, then recursively discovers
        all descendant pages using CQL queries. It enforces the page_limit
        at each level and excludes pages in the exclude_page_ids list.

        Args:
            parent_page_id: The page ID to use as the root of the hierarchy
            space_key: The space key where the page resides
            page_limit: Maximum number of child pages allowed per level (default 100)
            exclude_page_ids: Optional list of page IDs to exclude from the tree

        Returns:
            PageNode: Root node of the page hierarchy tree with all children

        Raises:
            PageNotFoundError: If parent_page_id doesn't exist
            PageLimitExceededError: If any level exceeds the page_limit
            APIUnreachableError: If API is unreachable
            APIAccessError: If API access fails after retries
            InvalidCredentialsError: If credentials are invalid
        """
        exclude_set = set(exclude_page_ids or [])

        # Check if parent page is in exclude list
        if parent_page_id in exclude_set:
            logger.warning(
                f"Parent page {parent_page_id} is in exclude list - "
                f"building minimal tree without children"
            )

        # Fetch the parent page to get its metadata and content
        logger.info(f"Confluence API: GET /content/{parent_page_id}?expand=version,space,ancestors,body.storage")
        parent_data = self._api.get_page_by_id(
            page_id=parent_page_id,
            expand="version,space,ancestors,body.storage"
        )

        # Validate the page is in the expected space (case-insensitive comparison)
        page_space = parent_data.get('space', {}).get('key', '')
        if page_space.lower() != space_key.lower():
            logger.warning(
                f"Page {parent_page_id} is in space '{page_space}', "
                f"not '{space_key}' as expected"
            )

        # Create the root node
        root = self._create_page_node(parent_data, parent_id=None)

        # Build the tree recursively if parent is not excluded
        if parent_page_id not in exclude_set:
            self._build_children_recursive(
                node=root,
                space_key=space_key,
                page_limit=page_limit,
                exclude_page_ids=exclude_set
            )

        return root

    def _build_children_recursive(
        self,
        node: PageNode,
        space_key: str,
        page_limit: int,
        exclude_page_ids: set
    ) -> None:
        """Recursively build child nodes for a given page.

        This method uses CQL to find all children of the current node,
        creates PageNode objects for each child, and recursively builds
        their children.

        Args:
            node: The parent PageNode to add children to
            space_key: The space key for CQL queries
            page_limit: Maximum number of children allowed
            exclude_page_ids: Set of page IDs to exclude

        Raises:
            PageLimitExceededError: If children count exceeds page_limit
        """
        # Query for children using CQL
        logger.debug(f"Querying children of page {node.page_id}")
        children_data = self._query_children_cql(node.page_id, space_key)

        # Filter out excluded pages
        filtered_children = [
            child for child in children_data
            if child.get('id') and child['id'] not in exclude_page_ids
        ]

        # Check page limit
        if len(filtered_children) > page_limit:
            logger.error(
                f"Page {node.page_id} ('{node.title}') has {len(filtered_children)} "
                f"children, exceeding limit of {page_limit}"
            )
            raise PageLimitExceededError(
                current_count=len(filtered_children),
                limit=page_limit
            )

        # Create child nodes
        for child_data in filtered_children:
            child_node = self._create_page_node(child_data, parent_id=node.page_id)
            node.children.append(child_node)

            # Recursively build grandchildren
            self._build_children_recursive(
                node=child_node,
                space_key=space_key,
                page_limit=page_limit,
                exclude_page_ids=exclude_page_ids
            )

    def _query_children_cql(
        self,
        parent_page_id: str,
        space_key: str
    ) -> List[Dict[str, Any]]:
        """Get child pages of a parent page.

        Uses the get_page_child_by_type API to fetch direct children
        of the specified page. This is more reliable than CQL queries
        for parent-child relationships.

        Args:
            parent_page_id: The parent page ID
            space_key: The space key (unused, kept for interface compatibility)

        Returns:
            List of page data dictionaries from the API results

        Raises:
            APIAccessError: If API query fails
        """
        logger.debug(f"Fetching children of page {parent_page_id} in space {space_key}")

        try:
            expand = "version,space,body.storage"

            # Use get_page_child_by_type for reliable child fetching
            response = self._api.get_page_child_by_type(
                page_id=parent_page_id,
                child_type='page',
                expand=expand
            )

            # Handle both dict with 'results' key and direct list
            if isinstance(response, dict):
                all_results = response.get('results', [])
            else:
                # If response is iterable, convert to list
                all_results = list(response)

            logger.debug(f"Found {len(all_results)} children for page {parent_page_id}")
            return all_results

        except Exception as e:
            logger.error(f"Failed to fetch children for page {parent_page_id}: {e}")
            raise APIAccessError(f"Failed to fetch child pages: {str(e)}")

    def _create_page_node(
        self,
        page_data: Dict[str, Any],
        parent_id: Optional[str]
    ) -> PageNode:
        """Create a PageNode from Confluence API response data.

        Extracts the necessary fields from the API response and creates
        a PageNode with empty children list.

        Args:
            page_data: Page data from Confluence API
            parent_id: Parent page ID (None for root)

        Returns:
            PageNode: New page node with metadata populated
        """
        # Extract version info for last_modified timestamp
        version_info = page_data.get('version', {})
        last_modified = version_info.get('when', '')
        version_number = version_info.get('number', 1)

        # Extract space key
        space_info = page_data.get('space', {})
        space_key = space_info.get('key', '')

        # Extract required fields with error handling
        page_id = page_data.get('id')
        if not page_id:
            logger.error(f"Page data missing 'id' field: {page_data}")
            raise ValueError("Page data missing required 'id' field")

        title = page_data.get('title', 'Untitled Page')

        # Extract and convert content
        body_storage = page_data.get('body', {}).get('storage', {})
        xhtml_content = body_storage.get('value', '')
        markdown_content = ""
        if xhtml_content:
            try:
                markdown_content = self._converter.xhtml_to_markdown(xhtml_content)
            except Exception as e:
                logger.warning(f"Failed to convert content for page {page_id}: {e}")
                markdown_content = ""

        # Create the node
        node = PageNode(
            page_id=page_id,
            title=title,
            parent_id=parent_id,
            children=[],
            last_modified=last_modified,
            space_key=space_key,
            markdown_content=markdown_content,
            version=version_number
        )

        logger.debug(
            f"Created PageNode: id={node.page_id}, "
            f"title='{node.title}', parent={parent_id}, version={version_number}"
        )

        return node
