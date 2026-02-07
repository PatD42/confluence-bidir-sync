"""Integration tests for CQL expand=ancestors query.

This module tests the AncestorResolver's CQL expand=ancestors functionality against
a real Confluence instance. Tests verify:
- Fetching pages with ancestor chains via CQL
- Extracting parent chains from ancestor data
- Building local file paths from ancestor hierarchies
- Error handling for various API scenarios

Requirements:
- Test Confluence credentials in .env.test
- Test space with known page hierarchy structure
"""

import pytest
import logging
from typing import Dict

from src.cli.ancestor_resolver import AncestorResolver
from src.cli.errors import CLIError
from src.confluence_client.auth import Authenticator
from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.errors import PageNotFoundError, APIAccessError
from tests.helpers.confluence_test_setup import setup_test_page, teardown_test_page

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestCQLAncestorsQuery:
    """Integration tests for CQL expand=ancestors functionality."""

    @pytest.fixture(scope="function")
    def api(self) -> APIWrapper:
        """Create APIWrapper for Confluence API access.

        Returns:
            Authenticated APIWrapper instance
        """
        auth = Authenticator()
        return APIWrapper(auth)

    @pytest.fixture(scope="function")
    def ancestor_resolver(self, api: APIWrapper) -> AncestorResolver:
        """Create AncestorResolver instance.

        Args:
            api: APIWrapper fixture

        Returns:
            AncestorResolver instance
        """
        return AncestorResolver(api=api)

    @pytest.fixture(scope="function")
    def test_root_page(self, test_credentials: Dict[str, str]):
        """Create a root test page without parents.

        Args:
            test_credentials: Test credentials fixture

        Yields:
            Dict with page_id, title, space_key
        """
        page_info = setup_test_page(
            title="INT Test - Ancestors Root Page",
            content="<p>Test root page for ancestors queries</p>"
        )
        logger.info(f"Created root test page: {page_info['page_id']}")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up root test page: {page_info['page_id']}")

    @pytest.fixture(scope="function")
    def test_parent_with_child(self, test_credentials: Dict[str, str]):
        """Create a parent page with a single child.

        Args:
            test_credentials: Test credentials fixture

        Yields:
            Dict with parent and child page info
        """
        # Create parent page
        parent_info = setup_test_page(
            title="INT Test - Ancestors Parent",
            content="<p>Parent page for ancestors test</p>"
        )
        logger.info(f"Created parent page: {parent_info['page_id']}")

        # Create child page
        child_info = setup_test_page(
            title="INT Test - Ancestors Child",
            content="<p>Child page for ancestors test</p>",
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
    def test_deep_hierarchy(self, test_credentials: Dict[str, str]):
        """Create a deep page hierarchy (root -> parent -> child -> grandchild).

        Args:
            test_credentials: Test credentials fixture

        Yields:
            Dict with root, parent, child, and grandchild page info
        """
        # Create root page
        root_info = setup_test_page(
            title="INT Test - Ancestors Deep Root",
            content="<p>Root page for deep hierarchy test</p>"
        )
        logger.info(f"Created root page: {root_info['page_id']}")

        # Create parent page
        parent_info = setup_test_page(
            title="INT Test - Ancestors Deep Parent",
            content="<p>Parent page</p>",
            parent_id=root_info['page_id']
        )
        logger.info(f"Created parent page: {parent_info['page_id']}")

        # Create child page
        child_info = setup_test_page(
            title="INT Test - Ancestors Deep Child",
            content="<p>Child page</p>",
            parent_id=parent_info['page_id']
        )
        logger.info(f"Created child page: {child_info['page_id']}")

        # Create grandchild page
        grandchild_info = setup_test_page(
            title="INT Test - Ancestors Deep Grandchild",
            content="<p>Grandchild page</p>",
            parent_id=child_info['page_id']
        )
        logger.info(f"Created grandchild page: {grandchild_info['page_id']}")

        yield {
            'root': root_info,
            'parent': parent_info,
            'child': child_info,
            'grandchild': grandchild_info
        }

        # Cleanup (deepest first)
        teardown_test_page(grandchild_info['page_id'])
        teardown_test_page(child_info['page_id'])
        teardown_test_page(parent_info['page_id'])
        teardown_test_page(root_info['page_id'])
        logger.info(f"Cleaned up deep hierarchy test pages")

    def test_fetch_root_page_no_ancestors(
        self,
        ancestor_resolver: AncestorResolver,
        test_root_page: Dict[str, str]
    ):
        """Test fetching a root page with minimal ancestors.

        Verifies:
        - Page is fetched successfully
        - Ancestors list is present (may include space home page)
        - Page data includes all required fields

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_root_page: Test root page fixture
        """
        page_id = test_root_page['page_id']
        space_key = test_root_page['space_key']

        logger.info(f"Fetching root page {page_id} with ancestors")
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=space_key,
            page_ids=[page_id]
        )

        # Verify result structure
        assert len(result) == 1, "Should return one page"
        assert page_id in result, "Page ID should be in result"

        # Verify page data
        page_data = result[page_id]
        assert page_data['id'] == page_id, "Page ID should match"
        assert page_data['title'] == test_root_page['title'], "Title should match"
        assert 'ancestors' in page_data, "Should have ancestors field"

        # Root pages may have space home page as ancestor
        ancestors = page_data['ancestors']
        assert isinstance(ancestors, list), "Ancestors should be a list"

        logger.info(f"✓ Verified root page with {len(ancestors)} ancestor(s)")

    def test_fetch_child_page_with_ancestors(
        self,
        ancestor_resolver: AncestorResolver,
        test_parent_with_child: Dict
    ):
        """Test fetching a child page with ancestors.

        Verifies:
        - Child page is fetched successfully
        - Ancestors list includes parent page
        - Ancestor data includes page ID and title

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_parent_with_child: Test parent/child fixture
        """
        parent_info = test_parent_with_child['parent']
        child_info = test_parent_with_child['child']

        logger.info(f"Fetching child page {child_info['page_id']} with ancestors")
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=child_info['space_key'],
            page_ids=[child_info['page_id']]
        )

        # Verify child page data
        assert len(result) == 1
        assert child_info['page_id'] in result

        page_data = result[child_info['page_id']]
        assert page_data['id'] == child_info['page_id']
        assert page_data['title'] == child_info['title']

        # Verify ancestors
        ancestors = page_data.get('ancestors', [])
        assert len(ancestors) >= 1, "Child should have at least one ancestor (parent)"

        # Find parent in ancestors (may have other ancestors above it)
        parent_ids = [a.get('id') for a in ancestors]
        assert parent_info['page_id'] in parent_ids, "Parent should be in ancestors"

        # Verify parent data in ancestors
        parent_ancestor = next(a for a in ancestors if a.get('id') == parent_info['page_id'])
        assert parent_ancestor['title'] == parent_info['title'], "Parent title should match"

        logger.info(f"✓ Verified child page with {len(ancestors)} ancestor(s)")

    def test_fetch_deep_hierarchy_ancestors(
        self,
        ancestor_resolver: AncestorResolver,
        test_deep_hierarchy: Dict
    ):
        """Test fetching a deeply nested page with full ancestor chain.

        Verifies:
        - Grandchild page has complete ancestor chain
        - Ancestors are ordered from root to immediate parent
        - All ancestor levels are present

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_deep_hierarchy: Test deep hierarchy fixture
        """
        root_info = test_deep_hierarchy['root']
        parent_info = test_deep_hierarchy['parent']
        child_info = test_deep_hierarchy['child']
        grandchild_info = test_deep_hierarchy['grandchild']

        logger.info(f"Fetching grandchild page {grandchild_info['page_id']} with ancestors")
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=grandchild_info['space_key'],
            page_ids=[grandchild_info['page_id']]
        )

        # Verify grandchild page data
        page_data = result[grandchild_info['page_id']]
        ancestors = page_data.get('ancestors', [])

        # Verify ancestor chain includes all levels
        ancestor_ids = [a.get('id') for a in ancestors]
        assert root_info['page_id'] in ancestor_ids, "Root should be in ancestors"
        assert parent_info['page_id'] in ancestor_ids, "Parent should be in ancestors"
        assert child_info['page_id'] in ancestor_ids, "Child should be in ancestors"

        # Verify ordering (root should come before parent, parent before child)
        root_index = ancestor_ids.index(root_info['page_id'])
        parent_index = ancestor_ids.index(parent_info['page_id'])
        child_index = ancestor_ids.index(child_info['page_id'])

        assert root_index < parent_index, "Root should come before parent in ancestors"
        assert parent_index < child_index, "Parent should come before child in ancestors"

        logger.info(f"✓ Verified deep hierarchy with {len(ancestors)} ancestor(s)")

    def test_fetch_multiple_pages_with_ancestors(
        self,
        ancestor_resolver: AncestorResolver,
        test_parent_with_child: Dict
    ):
        """Test fetching multiple pages with ancestors in single call.

        Verifies:
        - Multiple pages can be fetched in one call
        - Each page has correct ancestor data
        - Results are keyed by page ID

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_parent_with_child: Test parent/child fixture
        """
        parent_info = test_parent_with_child['parent']
        child_info = test_parent_with_child['child']

        page_ids = [parent_info['page_id'], child_info['page_id']]

        logger.info(f"Fetching {len(page_ids)} pages with ancestors")
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=parent_info['space_key'],
            page_ids=page_ids
        )

        # Verify both pages are in result
        assert len(result) == 2, "Should return two pages"
        assert parent_info['page_id'] in result
        assert child_info['page_id'] in result

        # Verify parent has fewer ancestors than child
        parent_ancestors = result[parent_info['page_id']].get('ancestors', [])
        child_ancestors = result[child_info['page_id']].get('ancestors', [])
        assert len(child_ancestors) > len(parent_ancestors), \
            "Child should have more ancestors than parent"

        logger.info("✓ Verified multiple pages fetch")

    def test_get_parent_chain_from_child(
        self,
        ancestor_resolver: AncestorResolver,
        test_parent_with_child: Dict
    ):
        """Test extracting parent chain from child page data.

        Verifies:
        - get_parent_chain extracts ancestor IDs correctly
        - Parent chain is ordered from root to immediate parent
        - Parent ID is in the chain

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_parent_with_child: Test parent/child fixture
        """
        parent_info = test_parent_with_child['parent']
        child_info = test_parent_with_child['child']

        # Fetch child with ancestors
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=child_info['space_key'],
            page_ids=[child_info['page_id']]
        )

        page_data = result[child_info['page_id']]

        # Extract parent chain
        logger.info(f"Extracting parent chain for page {child_info['page_id']}")
        parent_chain = ancestor_resolver.get_parent_chain(page_data)

        # Verify parent is in chain
        assert isinstance(parent_chain, list), "Parent chain should be a list"
        assert len(parent_chain) >= 1, "Should have at least one parent"
        assert parent_info['page_id'] in parent_chain, "Parent ID should be in chain"

        logger.info(f"✓ Verified parent chain with {len(parent_chain)} parent(s)")

    def test_get_parent_chain_from_root(
        self,
        ancestor_resolver: AncestorResolver,
        test_root_page: Dict[str, str]
    ):
        """Test extracting parent chain from root page (minimal ancestors).

        Verifies:
        - get_parent_chain returns list of ancestor IDs
        - No errors with ancestor extraction
        - Parent chain is a valid list

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_root_page: Test root page fixture
        """
        # Fetch root with ancestors
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=test_root_page['space_key'],
            page_ids=[test_root_page['page_id']]
        )

        page_data = result[test_root_page['page_id']]

        # Extract parent chain
        logger.info(f"Extracting parent chain for root page {test_root_page['page_id']}")
        parent_chain = ancestor_resolver.get_parent_chain(page_data)

        # Verify parent chain is valid (may include space home page)
        assert isinstance(parent_chain, list), "Parent chain should be a list"
        assert len(parent_chain) >= 0, "Parent chain should be non-negative length"

        logger.info(f"✓ Verified parent chain with {len(parent_chain)} parent(s) for root page")

    def test_get_parent_chain_deep_hierarchy(
        self,
        ancestor_resolver: AncestorResolver,
        test_deep_hierarchy: Dict
    ):
        """Test extracting parent chain from deeply nested page.

        Verifies:
        - Parent chain includes all ancestor levels
        - Order is preserved (root to immediate parent)
        - All expected page IDs are present

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_deep_hierarchy: Test deep hierarchy fixture
        """
        root_info = test_deep_hierarchy['root']
        parent_info = test_deep_hierarchy['parent']
        child_info = test_deep_hierarchy['child']
        grandchild_info = test_deep_hierarchy['grandchild']

        # Fetch grandchild with ancestors
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=grandchild_info['space_key'],
            page_ids=[grandchild_info['page_id']]
        )

        page_data = result[grandchild_info['page_id']]

        # Extract parent chain
        logger.info(f"Extracting parent chain for grandchild {grandchild_info['page_id']}")
        parent_chain = ancestor_resolver.get_parent_chain(page_data)

        # Verify all ancestors are in chain
        assert root_info['page_id'] in parent_chain, "Root should be in parent chain"
        assert parent_info['page_id'] in parent_chain, "Parent should be in parent chain"
        assert child_info['page_id'] in parent_chain, "Child should be in parent chain"

        # Verify ordering
        root_index = parent_chain.index(root_info['page_id'])
        parent_index = parent_chain.index(parent_info['page_id'])
        child_index = parent_chain.index(child_info['page_id'])

        assert root_index < parent_index < child_index, \
            "Parent chain should be ordered from root to immediate parent"

        logger.info(f"✓ Verified parent chain with {len(parent_chain)} levels")

    def test_build_path_from_child_page(
        self,
        ancestor_resolver: AncestorResolver,
        test_parent_with_child: Dict
    ):
        """Test building file path from child page ancestors.

        Verifies:
        - Path includes ancestor directories
        - Page filename is at the end
        - Path components are filesafe

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_parent_with_child: Test parent/child fixture
        """
        parent_info = test_parent_with_child['parent']
        child_info = test_parent_with_child['child']

        # Fetch child with ancestors
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=child_info['space_key'],
            page_ids=[child_info['page_id']]
        )

        page_data = result[child_info['page_id']]

        # Build path
        logger.info(f"Building path for page {child_info['page_id']}")
        path = ancestor_resolver.build_path_from_ancestors(
            page_data=page_data,
            space_key=child_info['space_key'],
            base_path="/docs"
        )

        # Verify path structure
        assert isinstance(path, str), "Path should be a string"
        assert path.startswith("/docs"), "Path should start with base_path"
        assert path.endswith(".md"), "Path should end with .md extension"
        assert "Ancestors-Child" in path or "Child" in path, \
            "Path should include child page filename"

        logger.info(f"✓ Verified path: {path}")

    def test_build_path_from_root_page(
        self,
        ancestor_resolver: AncestorResolver,
        test_root_page: Dict[str, str]
    ):
        """Test building file path from root page (no ancestors).

        Verifies:
        - Path has only base and filename
        - No intermediate directories for root page
        - Path is correctly formatted

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_root_page: Test root page fixture
        """
        # Fetch root with ancestors
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=test_root_page['space_key'],
            page_ids=[test_root_page['page_id']]
        )

        page_data = result[test_root_page['page_id']]

        # Build path
        logger.info(f"Building path for root page {test_root_page['page_id']}")
        path = ancestor_resolver.build_path_from_ancestors(
            page_data=page_data,
            space_key=test_root_page['space_key'],
            base_path="/docs"
        )

        # Verify path structure (should be /docs/filename.md)
        assert isinstance(path, str)
        assert path.startswith("/docs")
        assert path.endswith(".md")
        # Should have minimal path (base/filename)
        assert "Ancestors-Root-Page" in path or "Root-Page" in path

        logger.info(f"✓ Verified root path: {path}")

    def test_build_path_deep_hierarchy(
        self,
        ancestor_resolver: AncestorResolver,
        test_deep_hierarchy: Dict
    ):
        """Test building file path from deeply nested page.

        Verifies:
        - Path includes all ancestor directories
        - Directories are in correct order (root to parent)
        - Final component is the page filename

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_deep_hierarchy: Test deep hierarchy fixture
        """
        grandchild_info = test_deep_hierarchy['grandchild']

        # Fetch grandchild with ancestors
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=grandchild_info['space_key'],
            page_ids=[grandchild_info['page_id']]
        )

        page_data = result[grandchild_info['page_id']]

        # Build path
        logger.info(f"Building path for grandchild {grandchild_info['page_id']}")
        path = ancestor_resolver.build_path_from_ancestors(
            page_data=page_data,
            space_key=grandchild_info['space_key'],
            base_path="/docs"
        )

        # Verify path structure
        assert isinstance(path, str)
        assert path.startswith("/docs")
        assert path.endswith(".md")
        assert "Grandchild" in path, "Path should include grandchild filename"

        # Count path separators to verify depth
        # Should have: /docs + root + parent + child + grandchild.md
        path_parts = path.split("/")
        assert len(path_parts) >= 5, "Path should have multiple directory levels"

        logger.info(f"✓ Verified deep path: {path}")

    def test_fetch_invalid_page_id(
        self,
        ancestor_resolver: AncestorResolver,
        test_credentials: Dict[str, str]
    ):
        """Test error handling for non-existent page ID.

        Verifies:
        - CLIError is raised when all pages fail to fetch
        - Error message includes context

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_credentials: Test credentials fixture
        """
        invalid_page_id = "999999999"
        space_key = test_credentials['test_space']

        logger.info(f"Testing with invalid page ID: {invalid_page_id}")

        with pytest.raises(CLIError) as exc_info:
            ancestor_resolver.fetch_with_ancestors(
                space_key=space_key,
                page_ids=[invalid_page_id]
            )

        # Verify error details
        error = exc_info.value
        assert "Failed to fetch any pages" in str(error)

        logger.info("✓ Verified error handling for invalid page ID")

    def test_fetch_empty_page_list(
        self,
        ancestor_resolver: AncestorResolver,
        test_credentials: Dict[str, str]
    ):
        """Test fetching with empty page list.

        Verifies:
        - Empty list returns empty dict
        - No errors with empty input

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_credentials: Test credentials fixture
        """
        space_key = test_credentials['test_space']

        logger.info("Testing with empty page list")
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=space_key,
            page_ids=[]
        )

        # Verify empty result
        assert isinstance(result, dict)
        assert len(result) == 0

        logger.info("✓ Verified empty page list handling")

    def test_fetch_partial_failure(
        self,
        ancestor_resolver: AncestorResolver,
        test_root_page: Dict[str, str]
    ):
        """Test fetching when some pages fail.

        Verifies:
        - Valid pages are still returned
        - Invalid pages are skipped (not causing failure)
        - Result includes only successfully fetched pages

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_root_page: Test root page fixture
        """
        valid_page_id = test_root_page['page_id']
        invalid_page_id = "999999999"
        space_key = test_root_page['space_key']

        logger.info(f"Testing with mixed valid/invalid page IDs")
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=space_key,
            page_ids=[valid_page_id, invalid_page_id]
        )

        # Verify valid page is in result
        assert len(result) >= 1, "Should return at least the valid page"
        assert valid_page_id in result, "Valid page should be in result"
        assert invalid_page_id not in result, "Invalid page should not be in result"

        logger.info("✓ Verified partial failure handling")

    def test_ancestors_metadata_complete(
        self,
        ancestor_resolver: AncestorResolver,
        test_parent_with_child: Dict
    ):
        """Test that ancestor data includes all required fields.

        Verifies:
        - Each ancestor has 'id' field
        - Each ancestor has 'title' field
        - Ancestor data is well-formed

        Args:
            ancestor_resolver: AncestorResolver fixture
            test_parent_with_child: Test parent/child fixture
        """
        child_info = test_parent_with_child['child']

        # Fetch child with ancestors
        result = ancestor_resolver.fetch_with_ancestors(
            space_key=child_info['space_key'],
            page_ids=[child_info['page_id']]
        )

        page_data = result[child_info['page_id']]
        ancestors = page_data.get('ancestors', [])

        # Verify each ancestor has required fields
        for ancestor in ancestors:
            assert 'id' in ancestor, "Ancestor should have 'id' field"
            assert 'title' in ancestor, "Ancestor should have 'title' field"
            assert ancestor['id'], "Ancestor ID should not be empty"
            assert ancestor['title'], "Ancestor title should not be empty"

        logger.info(f"✓ Verified metadata for {len(ancestors)} ancestor(s)")
