"""Unit tests for recursion limits in FileMapper.

Tests M2: Unbounded recursion - depth limits to prevent stack overflow.
"""

import pytest
from unittest.mock import Mock, MagicMock

from src.file_mapper.file_mapper import FileMapper, MAX_RECURSION_DEPTH
from src.file_mapper.models import PageNode, SpaceConfig
from src.file_mapper.errors import FilesystemError


class TestRecursionLimits:
    """Test cases for recursion depth limits (M2)."""

    @pytest.fixture
    def file_mapper(self):
        """Create a FileMapper instance."""
        return FileMapper()

    @pytest.fixture
    def space_config(self):
        """Create a mock SpaceConfig."""
        config = Mock(spec=SpaceConfig)
        config.space_key = "TEST"
        config.local_path = "/test"
        return config

    def create_deep_hierarchy(self, depth: int) -> PageNode:
        """Create a deeply nested PageNode hierarchy.

        Args:
            depth: Number of levels to create

        Returns:
            Root PageNode with nested children
        """
        root = PageNode(
            page_id="root",
            title="Root Page",
            parent_id=None,
            markdown_content="Root content"
        )

        current = root
        for i in range(depth):
            child = PageNode(
                page_id=f"child_{i}",
                title=f"Child {i}",
                parent_id=current.page_id,
                markdown_content=f"Child {i} content"
            )
            current.children = [child]
            current = child

        return root

    def test_shallow_hierarchy_succeeds(self, file_mapper, space_config):
        """Verify shallow hierarchies process without issues."""
        # Create 5-level hierarchy
        root = self.create_deep_hierarchy(5)

        # Should not raise exception
        page_ids = file_mapper._collect_page_ids_from_hierarchy(root)
        assert len(page_ids) == 6  # root + 5 children

    def test_max_depth_hierarchy_succeeds(self, file_mapper, space_config):
        """Verify hierarchies at exactly max depth succeed."""
        # Create hierarchy at exactly MAX_RECURSION_DEPTH
        root = self.create_deep_hierarchy(MAX_RECURSION_DEPTH)

        # Should not raise exception
        page_ids = file_mapper._collect_page_ids_from_hierarchy(root)
        assert len(page_ids) == MAX_RECURSION_DEPTH + 1

    def test_exceeds_max_depth_raises_error(self, file_mapper, space_config):
        """Verify hierarchies exceeding max depth raise error (CRITICAL TEST)."""
        # Create hierarchy deeper than MAX_RECURSION_DEPTH
        root = self.create_deep_hierarchy(MAX_RECURSION_DEPTH + 1)

        # Should raise FilesystemError
        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._collect_page_ids_from_hierarchy(root)

        error = exc_info.value
        assert "exceeds maximum depth" in str(error)
        assert str(MAX_RECURSION_DEPTH) in str(error)

    def test_very_deep_hierarchy_rejected(self, file_mapper):
        """Verify very deep hierarchies (100+ levels) are rejected."""
        # Create 100-level hierarchy
        root = self.create_deep_hierarchy(100)

        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._collect_page_ids_from_hierarchy(root)

        assert "exceeds maximum depth" in str(exc_info.value)

    def test_build_file_list_depth_limit(self, file_mapper, space_config):
        """Verify _build_file_list_from_hierarchy respects depth limit."""
        # Create deep hierarchy
        root = self.create_deep_hierarchy(MAX_RECURSION_DEPTH + 1)
        files_to_write = []
        page_ids_filter = {f"child_{i}" for i in range(MAX_RECURSION_DEPTH + 2)}
        page_ids_filter.add("root")

        # Should raise FilesystemError
        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._build_file_list_from_hierarchy(
                node=root,
                parent_path="/test",
                files_to_write=files_to_write,
                space_config=space_config,
                page_ids_filter=page_ids_filter
            )

        assert "exceeds maximum depth" in str(exc_info.value)

    def test_max_recursion_depth_constant_is_50(self):
        """Verify MAX_RECURSION_DEPTH constant is set correctly."""
        assert MAX_RECURSION_DEPTH == 50

    def test_error_message_includes_depth_info(self, file_mapper):
        """Verify error message includes helpful depth information."""
        # Create overly deep hierarchy
        root = self.create_deep_hierarchy(MAX_RECURSION_DEPTH + 1)

        with pytest.raises(FilesystemError) as exc_info:
            file_mapper._collect_page_ids_from_hierarchy(root)

        error_msg = str(exc_info.value)
        # Should mention max depth (50)
        assert "50" in error_msg
        # Should mention the issue
        assert "circular reference" in error_msg.lower() or "deep nesting" in error_msg.lower()

    def test_boundary_case_depth_check(self, file_mapper):
        """Test hierarchies around the depth boundary."""
        # Just under max depth (should pass)
        root_under = self.create_deep_hierarchy(MAX_RECURSION_DEPTH - 1)
        page_ids = file_mapper._collect_page_ids_from_hierarchy(root_under)
        assert len(page_ids) == MAX_RECURSION_DEPTH

        # At max depth (should pass)
        root_at = self.create_deep_hierarchy(MAX_RECURSION_DEPTH)
        page_ids = file_mapper._collect_page_ids_from_hierarchy(root_at)
        assert len(page_ids) == MAX_RECURSION_DEPTH + 1

        # Just over max depth (should fail)
        root_over = self.create_deep_hierarchy(MAX_RECURSION_DEPTH + 1)
        with pytest.raises(FilesystemError):
            file_mapper._collect_page_ids_from_hierarchy(root_over)

    def test_wide_hierarchy_succeeds(self, file_mapper):
        """Verify wide (many siblings) hierarchies work within depth limit."""
        # Create a wide hierarchy (50 siblings at depth 1, each with 10 children at depth 2)
        root = PageNode(
            page_id="root",
            title="Root",
            parent_id=None,
            markdown_content="Root"
        )

        for i in range(50):
            parent = PageNode(
                page_id=f"parent_{i}",
                title=f"Parent {i}",
                parent_id="root",
                markdown_content=f"Parent {i}"
            )
            root.children.append(parent)

            for j in range(10):
                child = PageNode(
                    page_id=f"child_{i}_{j}",
                    title=f"Child {i}.{j}",
                    parent_id=f"parent_{i}",
                    markdown_content=f"Child {i}.{j}"
                )
                parent.children.append(child)

        # Should succeed (depth is only 2)
        page_ids = file_mapper._collect_page_ids_from_hierarchy(root)
        assert len(page_ids) == 1 + 50 + (50 * 10)  # root + 50 parents + 500 children

    def test_depth_parameter_increments_correctly(self, file_mapper):
        """Verify depth parameter increments properly through recursion."""
        # Create hierarchy with exactly MAX_RECURSION_DEPTH + 1 levels
        # This should fail at depth MAX_RECURSION_DEPTH + 1
        root = self.create_deep_hierarchy(MAX_RECURSION_DEPTH + 1)

        with pytest.raises(FilesystemError):
            file_mapper._collect_page_ids_from_hierarchy(root, depth=0)

        # But starting at depth 1 should fail earlier
        with pytest.raises(FilesystemError):
            file_mapper._collect_page_ids_from_hierarchy(root, depth=1)
