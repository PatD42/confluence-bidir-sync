"""Integration tests for CQL-based page discovery.

This module tests the HierarchyBuilder's CQL query functionality against
a real Confluence instance. Tests verify:
- CQL query execution and result parsing
- Recursive hierarchy building
- Page limit enforcement
- Page exclusion by pageID
- Error handling for various API scenarios

Requirements:
- Test Confluence credentials in .env.test
- Test space with known page hierarchy structure
"""

import pytest
import logging
from typing import Dict

from src.file_mapper.hierarchy_builder import HierarchyBuilder
from src.file_mapper.models import PageNode
from src.file_mapper.errors import PageLimitExceededError
from src.confluence_client.auth import Authenticator
from src.confluence_client.errors import PageNotFoundError, APIAccessError
from tests.helpers.confluence_test_setup import setup_test_page, teardown_test_page

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestCQLQueries:
    """Integration tests for CQL-based hierarchy discovery."""

    @pytest.fixture(scope="function")
    def auth(self) -> Authenticator:
        """Create authenticator for Confluence API access.

        Returns:
            Authenticated Authenticator instance
        """
        return Authenticator()

    @pytest.fixture(scope="function")
    def hierarchy_builder(self, auth: Authenticator) -> HierarchyBuilder:
        """Create HierarchyBuilder instance.

        Args:
            auth: Authenticator fixture

        Returns:
            HierarchyBuilder instance
        """
        return HierarchyBuilder(auth)

    @pytest.fixture(scope="function")
    def test_parent_page(self, test_credentials: Dict[str, str]):
        """Create a parent test page without children.

        Args:
            test_credentials: Test credentials fixture

        Yields:
            Dict with page_id, title, space_key
        """
        page_info = setup_test_page(
            title="INT Test - CQL Parent Page",
            content="<p>Test parent page for CQL queries</p>"
        )
        logger.info(f"Created parent test page: {page_info['page_id']}")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up parent test page: {page_info['page_id']}")

    @pytest.fixture(scope="function")
    def test_parent_with_single_child(self, test_credentials: Dict[str, str]):
        """Create a parent page with a single child.

        Args:
            test_credentials: Test credentials fixture

        Yields:
            Dict with parent and child page info
        """
        # Create parent page
        parent_info = setup_test_page(
            title="INT Test - Parent with Single Child",
            content="<p>Parent page</p>"
        )
        logger.info(f"Created parent page: {parent_info['page_id']}")

        # Create child page
        child_info = setup_test_page(
            title="INT Test - Child Page",
            content="<p>Child page</p>",
            parent_id=parent_info['page_id']
        )
        logger.info(f"Created child page: {child_info['page_id']}")

        yield {
            'parent': parent_info,
            'child': child_info
        }

        # Cleanup (child first, then parent)
        teardown_test_page(child_info['page_id'])
        teardown_test_page(parent_info['page_id'])
        logger.info(f"Cleaned up test pages")

    @pytest.fixture(scope="function")
    def test_parent_with_multiple_children(self, test_credentials: Dict[str, str]):
        """Create a parent page with multiple children.

        Args:
            test_credentials: Test credentials fixture

        Yields:
            Dict with parent and children page info
        """
        # Create parent page
        parent_info = setup_test_page(
            title="INT Test - Parent with Multiple Children",
            content="<p>Parent page with multiple children</p>"
        )
        logger.info(f"Created parent page: {parent_info['page_id']}")

        # Create three child pages
        children = []
        for i in range(3):
            child_info = setup_test_page(
                title=f"INT Test - Child {i+1}",
                content=f"<p>Child page {i+1}</p>",
                parent_id=parent_info['page_id']
            )
            children.append(child_info)
            logger.info(f"Created child page {i+1}: {child_info['page_id']}")

        yield {
            'parent': parent_info,
            'children': children
        }

        # Cleanup (children first, then parent)
        for child_info in children:
            teardown_test_page(child_info['page_id'])
        teardown_test_page(parent_info['page_id'])
        logger.info(f"Cleaned up test pages")

    @pytest.fixture(scope="function")
    def test_nested_hierarchy(self, test_credentials: Dict[str, str]):
        """Create a nested page hierarchy (parent -> child -> grandchild).

        Args:
            test_credentials: Test credentials fixture

        Yields:
            Dict with parent, child, and grandchild page info
        """
        # Create parent page
        parent_info = setup_test_page(
            title="INT Test - Nested Parent",
            content="<p>Root parent page</p>"
        )
        logger.info(f"Created parent page: {parent_info['page_id']}")

        # Create child page
        child_info = setup_test_page(
            title="INT Test - Nested Child",
            content="<p>Child page</p>",
            parent_id=parent_info['page_id']
        )
        logger.info(f"Created child page: {child_info['page_id']}")

        # Create grandchild page
        grandchild_info = setup_test_page(
            title="INT Test - Nested Grandchild",
            content="<p>Grandchild page</p>",
            parent_id=child_info['page_id']
        )
        logger.info(f"Created grandchild page: {grandchild_info['page_id']}")

        yield {
            'parent': parent_info,
            'child': child_info,
            'grandchild': grandchild_info
        }

        # Cleanup (deepest first)
        teardown_test_page(grandchild_info['page_id'])
        teardown_test_page(child_info['page_id'])
        teardown_test_page(parent_info['page_id'])
        logger.info(f"Cleaned up nested test pages")

    def test_build_hierarchy_no_children(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_parent_page: Dict[str, str]
    ):
        """Test building hierarchy for a page with no children.

        Verifies:
        - CQL query executes successfully
        - Parent node is created with correct metadata
        - Children list is empty

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_parent_page: Test parent page fixture
        """
        page_id = test_parent_page['page_id']
        space_key = test_parent_page['space_key']

        logger.info(f"Building hierarchy for page {page_id}")
        root = hierarchy_builder.build_hierarchy(
            parent_page_id=page_id,
            space_key=space_key
        )

        # Verify root node
        assert isinstance(root, PageNode), "Should return PageNode"
        assert root.page_id == page_id, "Page ID should match"
        assert root.title == test_parent_page['title'], "Title should match"
        assert root.parent_id is None, "Root should have no parent"
        assert root.space_key == space_key, "Space key should match"
        assert len(root.children) == 0, "Should have no children"
        assert root.last_modified, "Should have last_modified timestamp"

        logger.info("✓ Verified hierarchy with no children")

    def test_build_hierarchy_single_child(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_parent_with_single_child: Dict
    ):
        """Test building hierarchy for a page with one child.

        Verifies:
        - CQL query discovers child page
        - Parent node has exactly one child
        - Child node has correct metadata and parent reference

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_parent_with_single_child: Test parent/child fixture
        """
        parent_info = test_parent_with_single_child['parent']
        child_info = test_parent_with_single_child['child']

        logger.info(f"Building hierarchy for page {parent_info['page_id']}")
        root = hierarchy_builder.build_hierarchy(
            parent_page_id=parent_info['page_id'],
            space_key=parent_info['space_key']
        )

        # Verify root node
        assert root.page_id == parent_info['page_id']
        assert root.title == parent_info['title']
        assert len(root.children) == 1, "Should have exactly one child"

        # Verify child node
        child_node = root.children[0]
        assert child_node.page_id == child_info['page_id']
        assert child_node.title == child_info['title']
        assert child_node.parent_id == parent_info['page_id']
        assert child_node.space_key == parent_info['space_key']
        assert len(child_node.children) == 0, "Child should have no children"

        logger.info("✓ Verified hierarchy with single child")

    def test_build_hierarchy_multiple_children(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_parent_with_multiple_children: Dict
    ):
        """Test building hierarchy for a page with multiple children.

        Verifies:
        - CQL query discovers all children
        - Parent node has correct number of children
        - All child nodes have correct metadata

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_parent_with_multiple_children: Test parent/children fixture
        """
        parent_info = test_parent_with_multiple_children['parent']
        children_info = test_parent_with_multiple_children['children']

        logger.info(f"Building hierarchy for page {parent_info['page_id']}")
        root = hierarchy_builder.build_hierarchy(
            parent_page_id=parent_info['page_id'],
            space_key=parent_info['space_key']
        )

        # Verify root node
        assert root.page_id == parent_info['page_id']
        assert len(root.children) == len(children_info), \
            f"Should have {len(children_info)} children"

        # Verify all children are present
        child_ids = {child.page_id for child in root.children}
        expected_ids = {child['page_id'] for child in children_info}
        assert child_ids == expected_ids, "All children should be discovered"

        # Verify each child has correct parent reference
        for child_node in root.children:
            assert child_node.parent_id == parent_info['page_id']
            assert child_node.space_key == parent_info['space_key']
            assert len(child_node.children) == 0

        logger.info(f"✓ Verified hierarchy with {len(children_info)} children")

    def test_build_hierarchy_nested_levels(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_nested_hierarchy: Dict
    ):
        """Test building hierarchy with nested levels.

        Verifies:
        - CQL queries execute recursively for all levels
        - Three-level hierarchy is built correctly
        - Parent-child relationships are correct at all levels

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_nested_hierarchy: Test nested pages fixture
        """
        parent_info = test_nested_hierarchy['parent']
        child_info = test_nested_hierarchy['child']
        grandchild_info = test_nested_hierarchy['grandchild']

        logger.info(f"Building nested hierarchy for page {parent_info['page_id']}")
        root = hierarchy_builder.build_hierarchy(
            parent_page_id=parent_info['page_id'],
            space_key=parent_info['space_key']
        )

        # Verify root (parent) level
        assert root.page_id == parent_info['page_id']
        assert len(root.children) == 1, "Parent should have 1 child"

        # Verify child level
        child_node = root.children[0]
        assert child_node.page_id == child_info['page_id']
        assert child_node.parent_id == parent_info['page_id']
        assert len(child_node.children) == 1, "Child should have 1 grandchild"

        # Verify grandchild level
        grandchild_node = child_node.children[0]
        assert grandchild_node.page_id == grandchild_info['page_id']
        assert grandchild_node.parent_id == child_info['page_id']
        assert len(grandchild_node.children) == 0, "Grandchild should have no children"

        logger.info("✓ Verified nested 3-level hierarchy")

    def test_build_hierarchy_with_exclusion(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_parent_with_multiple_children: Dict
    ):
        """Test building hierarchy with page exclusion.

        Verifies:
        - Excluded pages are not included in the tree
        - Non-excluded siblings are still discovered

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_parent_with_multiple_children: Test parent/children fixture
        """
        parent_info = test_parent_with_multiple_children['parent']
        children_info = test_parent_with_multiple_children['children']

        # Exclude the first child
        excluded_id = children_info[0]['page_id']
        logger.info(f"Building hierarchy with excluded page: {excluded_id}")

        root = hierarchy_builder.build_hierarchy(
            parent_page_id=parent_info['page_id'],
            space_key=parent_info['space_key'],
            exclude_page_ids=[excluded_id]
        )

        # Verify excluded page is not in tree
        child_ids = {child.page_id for child in root.children}
        assert excluded_id not in child_ids, "Excluded page should not be in tree"

        # Verify non-excluded children are present
        expected_count = len(children_info) - 1
        assert len(root.children) == expected_count, \
            f"Should have {expected_count} non-excluded children"

        logger.info(f"✓ Verified exclusion (excluded 1, found {len(root.children)})")

    def test_build_hierarchy_exclude_parent(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_parent_with_single_child: Dict
    ):
        """Test building hierarchy when parent itself is excluded.

        Verifies:
        - Parent node is created but has no children
        - Exclusion applies to entire subtree

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_parent_with_single_child: Test parent/child fixture
        """
        parent_info = test_parent_with_single_child['parent']

        logger.info(f"Building hierarchy with excluded parent: {parent_info['page_id']}")
        root = hierarchy_builder.build_hierarchy(
            parent_page_id=parent_info['page_id'],
            space_key=parent_info['space_key'],
            exclude_page_ids=[parent_info['page_id']]
        )

        # Verify parent node exists but has no children
        assert root.page_id == parent_info['page_id']
        assert len(root.children) == 0, \
            "Excluded parent should have no children in tree"

        logger.info("✓ Verified exclusion of parent page")

    def test_page_limit_enforcement(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_parent_with_multiple_children: Dict
    ):
        """Test that page limit is enforced correctly.

        Verifies:
        - PageLimitExceededError is raised when limit is exceeded
        - Error message includes useful context

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_parent_with_multiple_children: Test parent/children fixture
        """
        parent_info = test_parent_with_multiple_children['parent']
        children_count = len(test_parent_with_multiple_children['children'])

        # Set limit below actual child count
        page_limit = children_count - 1
        logger.info(f"Testing limit of {page_limit} with {children_count} children")

        with pytest.raises(PageLimitExceededError) as exc_info:
            hierarchy_builder.build_hierarchy(
                parent_page_id=parent_info['page_id'],
                space_key=parent_info['space_key'],
                page_limit=page_limit
            )

        # Verify error details
        error = exc_info.value
        assert error.current_count == children_count
        assert error.limit == page_limit
        assert str(children_count) in str(error)
        assert str(page_limit) in str(error)

        logger.info("✓ Verified page limit enforcement")

    def test_page_limit_at_boundary(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_parent_with_multiple_children: Dict
    ):
        """Test that page limit allows exact match.

        Verifies:
        - No error when child count equals limit exactly
        - All children are discovered

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_parent_with_multiple_children: Test parent/children fixture
        """
        parent_info = test_parent_with_multiple_children['parent']
        children_count = len(test_parent_with_multiple_children['children'])

        # Set limit exactly equal to child count
        logger.info(f"Testing limit of {children_count} with {children_count} children")

        root = hierarchy_builder.build_hierarchy(
            parent_page_id=parent_info['page_id'],
            space_key=parent_info['space_key'],
            page_limit=children_count
        )

        # Should succeed and include all children
        assert len(root.children) == children_count

        logger.info("✓ Verified page limit boundary condition")

    def test_invalid_parent_page_id(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_credentials: Dict[str, str]
    ):
        """Test error handling for non-existent parent page.

        Verifies:
        - PageNotFoundError is raised for invalid page ID

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_credentials: Test credentials fixture
        """
        invalid_page_id = "999999999"
        space_key = test_credentials['test_space']

        logger.info(f"Testing with invalid page ID: {invalid_page_id}")

        with pytest.raises(PageNotFoundError) as exc_info:
            hierarchy_builder.build_hierarchy(
                parent_page_id=invalid_page_id,
                space_key=space_key
            )

        # Verify error includes page ID
        error = exc_info.value
        assert invalid_page_id in str(error)

        logger.info("✓ Verified error handling for invalid page ID")

    def test_wrong_space_key(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_parent_page: Dict[str, str]
    ):
        """Test behavior when querying with wrong space key.

        Verifies:
        - Hierarchy is built but a warning is logged
        - Root node is created with actual space key

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_parent_page: Test parent page fixture
        """
        page_id = test_parent_page['page_id']
        wrong_space_key = "WRONGSPACE"

        logger.info(f"Testing with wrong space key: {wrong_space_key}")

        # Should succeed but log warning
        root = hierarchy_builder.build_hierarchy(
            parent_page_id=page_id,
            space_key=wrong_space_key
        )

        # Verify root node uses actual space key from API
        assert root.page_id == page_id
        assert root.space_key == test_parent_page['space_key'], \
            "Should use actual space key from API"

        logger.info("✓ Verified handling of wrong space key")

    def test_cql_metadata_extraction(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_parent_page: Dict[str, str]
    ):
        """Test that CQL results include required metadata.

        Verifies:
        - last_modified timestamp is populated
        - space_key is populated
        - All fields in PageNode are set correctly

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_parent_page: Test parent page fixture
        """
        page_id = test_parent_page['page_id']
        space_key = test_parent_page['space_key']

        logger.info(f"Testing metadata extraction for page {page_id}")
        root = hierarchy_builder.build_hierarchy(
            parent_page_id=page_id,
            space_key=space_key
        )

        # Verify all metadata fields are populated
        assert root.page_id, "page_id should be populated"
        assert root.title, "title should be populated"
        assert root.space_key, "space_key should be populated"
        assert root.last_modified, "last_modified should be populated"

        # Verify last_modified is ISO 8601 format (contains 'T' separator)
        assert 'T' in root.last_modified or 'Z' in root.last_modified, \
            "last_modified should be ISO 8601 format"

        logger.info("✓ Verified CQL metadata extraction")

    def test_empty_hierarchy_construction(
        self,
        hierarchy_builder: HierarchyBuilder,
        test_parent_page: Dict[str, str]
    ):
        """Test that empty hierarchy (no children) is valid.

        Verifies:
        - Single-node tree is valid
        - Children list is initialized to empty list (not None)

        Args:
            hierarchy_builder: HierarchyBuilder fixture
            test_parent_page: Test parent page fixture
        """
        page_id = test_parent_page['page_id']
        space_key = test_parent_page['space_key']

        logger.info(f"Testing empty hierarchy construction")
        root = hierarchy_builder.build_hierarchy(
            parent_page_id=page_id,
            space_key=space_key
        )

        # Verify single-node tree structure
        assert root is not None
        assert isinstance(root.children, list), "children should be a list"
        assert len(root.children) == 0, "children should be empty"
        assert root.children == [], "children should be empty list, not None"

        logger.info("✓ Verified empty hierarchy construction")
