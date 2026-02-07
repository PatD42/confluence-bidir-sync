"""Unit tests for cli.ancestor_resolver module."""

from unittest.mock import Mock, patch

import pytest

from src.cli.ancestor_resolver import AncestorResolver
from src.cli.errors import CLIError
from src.confluence_client.errors import PageNotFoundError, APIAccessError


class TestAncestorResolver:
    """Test cases for AncestorResolver."""

    @pytest.fixture
    def mock_api(self):
        """Create mock API wrapper."""
        return Mock()

    @pytest.fixture
    def resolver(self, mock_api):
        """Create AncestorResolver instance with mock API."""
        return AncestorResolver(api=mock_api)


class TestFetchWithAncestors(TestAncestorResolver):
    """Test fetch_with_ancestors method."""

    def test_fetch_single_page_with_ancestors(self, resolver, mock_api):
        """Fetch single page with ancestors successfully."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Child Page",
            "space": {"key": "TEAM"},
            "ancestors": [
                {"id": "100", "title": "Root"},
                {"id": "110", "title": "Parent"}
            ]
        }
        mock_api.get_page_by_id.return_value = page_data

        # Act
        result = resolver.fetch_with_ancestors("TEAM", ["123"])

        # Assert
        assert len(result) == 1
        assert "123" in result
        assert result["123"]["title"] == "Child Page"
        assert len(result["123"]["ancestors"]) == 2
        mock_api.get_page_by_id.assert_called_once_with(
            page_id="123",
            expand="ancestors,version,space"
        )

    def test_fetch_multiple_pages_with_ancestors(self, resolver, mock_api):
        """Fetch multiple pages with ancestors successfully."""
        # Arrange
        page1_data = {
            "id": "123",
            "title": "Page 1",
            "space": {"key": "TEAM"},
            "ancestors": [{"id": "100", "title": "Root"}]
        }
        page2_data = {
            "id": "456",
            "title": "Page 2",
            "space": {"key": "TEAM"},
            "ancestors": [{"id": "100", "title": "Root"}, {"id": "200", "title": "Parent"}]
        }
        mock_api.get_page_by_id.side_effect = [page1_data, page2_data]

        # Act
        result = resolver.fetch_with_ancestors("TEAM", ["123", "456"])

        # Assert
        assert len(result) == 2
        assert "123" in result
        assert "456" in result
        assert result["123"]["title"] == "Page 1"
        assert result["456"]["title"] == "Page 2"
        assert mock_api.get_page_by_id.call_count == 2

    def test_fetch_page_not_found_skips_and_continues(self, resolver, mock_api):
        """PageNotFoundError should skip page and continue with others."""
        # Arrange
        page2_data = {
            "id": "456",
            "title": "Page 2",
            "space": {"key": "TEAM"},
            "ancestors": []
        }
        mock_api.get_page_by_id.side_effect = [
            PageNotFoundError("Page 123 not found"),
            page2_data
        ]

        # Act
        result = resolver.fetch_with_ancestors("TEAM", ["123", "456"])

        # Assert
        assert len(result) == 1
        assert "123" not in result
        assert "456" in result
        assert result["456"]["title"] == "Page 2"

    def test_fetch_space_mismatch_logs_warning(self, resolver, mock_api, caplog):
        """Space key mismatch should log warning but still return page."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Page",
            "space": {"key": "OTHER"},  # Different space
            "ancestors": []
        }
        mock_api.get_page_by_id.return_value = page_data

        # Act
        with caplog.at_level("WARNING"):
            result = resolver.fetch_with_ancestors("TEAM", ["123"])

        # Assert
        assert len(result) == 1
        assert "123" in result
        assert "is in space 'OTHER'" in caplog.text
        assert "not 'TEAM'" in caplog.text

    def test_fetch_all_pages_fail_raises_error(self, resolver, mock_api):
        """All pages failing to fetch should raise CLIError."""
        # Arrange
        mock_api.get_page_by_id.side_effect = PageNotFoundError("Not found")

        # Act & Assert
        with pytest.raises(CLIError) as exc_info:
            resolver.fetch_with_ancestors("TEAM", ["123", "456"])

        assert "Failed to fetch any pages" in str(exc_info.value)
        assert "2 requested page IDs" in str(exc_info.value)

    def test_fetch_generic_error_skips_and_continues(self, resolver, mock_api):
        """Generic error should skip page and continue with others."""
        # Arrange
        page2_data = {
            "id": "456",
            "title": "Page 2",
            "space": {"key": "TEAM"},
            "ancestors": []
        }
        mock_api.get_page_by_id.side_effect = [
            Exception("Network error"),
            page2_data
        ]

        # Act
        result = resolver.fetch_with_ancestors("TEAM", ["123", "456"])

        # Assert
        assert len(result) == 1
        assert "123" not in result
        assert "456" in result

    def test_fetch_empty_page_list(self, resolver, mock_api):
        """Empty page list should return empty dict."""
        # Arrange
        page_ids = []

        # Act
        result = resolver.fetch_with_ancestors("TEAM", page_ids)

        # Assert
        assert result == {}
        assert len(result) == 0

    def test_fetch_page_without_space_field(self, resolver, mock_api):
        """Page without space field should still be returned."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Page",
            # No space field
            "ancestors": []
        }
        mock_api.get_page_by_id.return_value = page_data

        # Act
        result = resolver.fetch_with_ancestors("TEAM", ["123"])

        # Assert
        assert len(result) == 1
        assert "123" in result


class TestGetParentChain(TestAncestorResolver):
    """Test get_parent_chain method."""

    def test_get_parent_chain_with_ancestors(self, resolver):
        """Extract parent chain from page with ancestors."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Child Page",
            "ancestors": [
                {"id": "100", "title": "Root"},
                {"id": "110", "title": "Parent"}
            ]
        }

        # Act
        result = resolver.get_parent_chain(page_data)

        # Assert
        assert result == ["100", "110"]

    def test_get_parent_chain_no_ancestors(self, resolver):
        """Extract parent chain from root page (no ancestors)."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Root Page",
            "ancestors": []
        }

        # Act
        result = resolver.get_parent_chain(page_data)

        # Assert
        assert result == []

    def test_get_parent_chain_missing_ancestors_field(self, resolver):
        """Page without ancestors field should return empty list."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Page"
            # No ancestors field
        }

        # Act
        result = resolver.get_parent_chain(page_data)

        # Assert
        assert result == []

    def test_get_parent_chain_single_ancestor(self, resolver):
        """Extract parent chain with single ancestor."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Child Page",
            "ancestors": [
                {"id": "100", "title": "Parent"}
            ]
        }

        # Act
        result = resolver.get_parent_chain(page_data)

        # Assert
        assert result == ["100"]

    def test_get_parent_chain_with_missing_id(self, resolver):
        """Ancestors without id field should be skipped."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Child Page",
            "ancestors": [
                {"id": "100", "title": "Root"},
                {"title": "Missing ID"},  # No id field
                {"id": "110", "title": "Parent"}
            ]
        }

        # Act
        result = resolver.get_parent_chain(page_data)

        # Assert
        assert result == ["100", "110"]  # Middle one skipped

    def test_get_parent_chain_preserves_order(self, resolver):
        """Parent chain should preserve order from root to immediate parent."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Deep Child",
            "ancestors": [
                {"id": "100", "title": "Root"},
                {"id": "110", "title": "Level 1"},
                {"id": "120", "title": "Level 2"},
                {"id": "130", "title": "Immediate Parent"}
            ]
        }

        # Act
        result = resolver.get_parent_chain(page_data)

        # Assert
        assert result == ["100", "110", "120", "130"]


class TestBuildPathFromAncestors(TestAncestorResolver):
    """Test build_path_from_ancestors method."""

    def test_build_path_with_ancestors(self, resolver):
        """Build path from page with ancestor hierarchy."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Child Page",
            "ancestors": [
                {"id": "100", "title": "Section A"},
                {"id": "110", "title": "Subsection B"}
            ]
        }

        # Act
        result = resolver.build_path_from_ancestors(
            page_data,
            space_key="TEAM",
            base_path="/docs"
        )

        # Assert
        assert result == "/docs/Section-A/Subsection-B/Child-Page.md"

    def test_build_path_no_ancestors(self, resolver):
        """Build path for root page (no ancestors)."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Root Page",
            "ancestors": []
        }

        # Act
        result = resolver.build_path_from_ancestors(
            page_data,
            space_key="TEAM",
            base_path="/docs"
        )

        # Assert
        assert result == "/docs/Root-Page.md"

    def test_build_path_uses_space_key_when_no_base_path(self, resolver):
        """Use space_key as base_path when base_path is None."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Page",
            "ancestors": []
        }

        # Act
        result = resolver.build_path_from_ancestors(
            page_data,
            space_key="TEAM",
            base_path=None
        )

        # Assert
        assert result == "TEAM/Page.md"

    def test_build_path_strips_md_from_ancestor_directories(self, resolver):
        """Ancestor titles should not have .md extension in path."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Child",
            "ancestors": [
                {"id": "100", "title": "Parent Folder"}
            ]
        }

        # Act
        result = resolver.build_path_from_ancestors(
            page_data,
            space_key="TEAM",
            base_path="base"
        )

        # Assert
        # Parent should be a directory (no .md), child should have .md
        assert result == "base/Parent-Folder/Child.md"
        assert "/Parent-Folder.md/" not in result

    def test_build_path_with_special_characters(self, resolver):
        """Build path with special characters in titles."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Q&A Session",
            "ancestors": [
                {"id": "100", "title": "API Reference: Getting Started"}
            ]
        }

        # Act
        result = resolver.build_path_from_ancestors(
            page_data,
            space_key="TEAM",
            base_path="base"
        )

        # Assert
        # Special chars converted per FilesafeConverter rules
        assert "API-Reference--Getting-Started" in result
        assert "Q-A-Session.md" in result

    def test_build_path_missing_title_uses_untitled(self, resolver):
        """Page without title should use 'untitled'."""
        # Arrange
        page_data = {
            "id": "123",
            # No title field
            "ancestors": []
        }

        # Act
        result = resolver.build_path_from_ancestors(
            page_data,
            space_key="TEAM",
            base_path="base"
        )

        # Assert
        assert result == "base/untitled.md"

    def test_build_path_empty_ancestor_title_skipped(self, resolver):
        """Ancestors with empty titles should be skipped."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Child",
            "ancestors": [
                {"id": "100", "title": "Parent"},
                {"id": "110", "title": ""},  # Empty title
                {"id": "120", "title": "Grandparent"}
            ]
        }

        # Act
        result = resolver.build_path_from_ancestors(
            page_data,
            space_key="TEAM",
            base_path="base"
        )

        # Assert
        # Only Parent and Grandparent should be in path (empty one skipped)
        assert "Parent" in result
        assert "Grandparent" in result
        # Should have 2 ancestor directories
        parts = result.split("/")
        assert len(parts) == 4  # base + Parent + Grandparent + Child.md

    def test_build_path_with_multiple_ancestors(self, resolver):
        """Build path with deep hierarchy."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Deep Page",
            "ancestors": [
                {"id": "100", "title": "Level 1"},
                {"id": "110", "title": "Level 2"},
                {"id": "120", "title": "Level 3"}
            ]
        }

        # Act
        result = resolver.build_path_from_ancestors(
            page_data,
            space_key="TEAM",
            base_path="base"
        )

        # Assert
        assert result == "base/Level-1/Level-2/Level-3/Deep-Page.md"


class TestLogging(TestAncestorResolver):
    """Test logging behavior."""

    def test_fetch_logs_progress(self, resolver, mock_api, caplog):
        """Fetch should log progress information."""
        # Arrange
        page_data = {
            "id": "123",
            "title": "Page",
            "space": {"key": "TEAM"},
            "ancestors": [{"id": "100", "title": "Parent"}]
        }
        mock_api.get_page_by_id.return_value = page_data

        # Act
        with caplog.at_level("INFO"):
            result = resolver.fetch_with_ancestors("TEAM", ["123"])

        # Assert
        assert "Fetching 1 pages with ancestors" in caplog.text
        assert "Successfully fetched 1 pages" in caplog.text

    def test_fetch_logs_page_not_found_warning(self, resolver, mock_api, caplog):
        """PageNotFoundError should be logged as warning."""
        # Arrange
        page2_data = {
            "id": "456",
            "title": "Page 2",
            "space": {"key": "TEAM"},
            "ancestors": []
        }
        mock_api.get_page_by_id.side_effect = [
            PageNotFoundError("Page 123 not found"),
            page2_data
        ]

        # Act
        with caplog.at_level("WARNING"):
            result = resolver.fetch_with_ancestors("TEAM", ["123", "456"])

        # Assert
        assert "Page 123 not found" in caplog.text
        assert "may be deleted" in caplog.text

    def test_fetch_logs_generic_error(self, resolver, mock_api, caplog):
        """Generic errors should be logged."""
        # Arrange
        page2_data = {
            "id": "456",
            "title": "Page 2",
            "space": {"key": "TEAM"},
            "ancestors": []
        }
        mock_api.get_page_by_id.side_effect = [
            Exception("Network error"),
            page2_data
        ]

        # Act
        with caplog.at_level("ERROR"):
            result = resolver.fetch_with_ancestors("TEAM", ["123", "456"])

        # Assert
        assert "Error fetching page 123" in caplog.text


class TestInitialization(TestAncestorResolver):
    """Test AncestorResolver initialization."""

    def test_init_with_api_wrapper(self, mock_api):
        """Initialize with provided API wrapper."""
        # Act
        resolver = AncestorResolver(api=mock_api)

        # Assert
        assert resolver.api is mock_api

    @patch('src.cli.ancestor_resolver.Authenticator')
    @patch('src.cli.ancestor_resolver.APIWrapper')
    def test_init_without_api_wrapper_creates_default(
        self, mock_api_wrapper_class, mock_auth_class
    ):
        """Initialize without API wrapper should create default one."""
        # Arrange
        mock_auth_instance = Mock()
        mock_api_instance = Mock()
        mock_auth_class.return_value = mock_auth_instance
        mock_api_wrapper_class.return_value = mock_api_instance

        # Act
        resolver = AncestorResolver()

        # Assert
        mock_auth_class.assert_called_once()
        mock_api_wrapper_class.assert_called_once_with(mock_auth_instance)
        assert resolver.api is mock_api_instance
