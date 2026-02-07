"""Unit tests for page_operations.page_operations module.

Tests cover:
- get_page_snapshot (basic, with version, with labels)
- apply_operations (UPDATE_TEXT, DELETE_BLOCK, TABLE operations)
- update_page_surgical (success, version conflict)
- update_page_surgical_adf (success path)
- create_page (with/without parent_id, duplicate handling)
- update_page_content
- update_page_parent
- delete_page
- Helper methods (_preserve_macros_for_markdown, _filter_title_heading)
"""

import json
import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from src.page_operations.page_operations import PageOperations
from src.page_operations.models import (
    SurgicalOperation,
    OperationType,
    BlockType,
    ContentBlock,
)
from src.confluence_client.errors import (
    PageNotFoundError,
    APIAccessError,
)


class TestGetPageSnapshot:
    """Tests for get_page_snapshot method."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API wrapper."""
        api = Mock()
        return api

    @pytest.fixture
    def ops(self, mock_api):
        """Create PageOperations with mocked API."""
        return PageOperations(api=mock_api)

    @pytest.fixture
    def sample_page_data(self):
        """Sample page data from API."""
        return {
            "id": "12345",
            "title": "Test Page",
            "spaceKey": "TEST",
            "body": {
                "storage": {
                    "value": "<p>Hello World</p>"
                }
            },
            "version": {
                "number": 5,
                "when": "2024-01-15T10:30:00.000Z"
            },
            "metadata": {
                "labels": {
                    "results": [
                        {"name": "label1"},
                        {"name": "label2"}
                    ]
                }
            },
            "ancestors": [
                {"id": "parent123"}
            ]
        }

    def test_get_page_snapshot_basic(self, ops, mock_api, sample_page_data):
        """get_page_snapshot should return snapshot with all fields."""
        mock_api.get_page_by_id.return_value = sample_page_data

        snapshot = ops.get_page_snapshot("12345")

        assert snapshot.page_id == "12345"
        assert snapshot.title == "Test Page"
        assert snapshot.space_key == "TEST"
        assert snapshot.version == 5
        assert "<p>Hello World</p>" in snapshot.xhtml
        mock_api.get_page_by_id.assert_called_once()

    def test_get_page_snapshot_with_version(self, ops, mock_api, sample_page_data):
        """get_page_snapshot with version should use version history API."""
        mock_api.get_page_version.return_value = sample_page_data

        snapshot = ops.get_page_snapshot("12345", version=3)

        mock_api.get_page_version.assert_called_once_with("12345", 3)
        assert snapshot.version == 5  # From the returned data

    def test_get_page_snapshot_extracts_labels(self, ops, mock_api, sample_page_data):
        """get_page_snapshot should extract labels from metadata."""
        mock_api.get_page_by_id.return_value = sample_page_data

        snapshot = ops.get_page_snapshot("12345")

        assert snapshot.labels == ["label1", "label2"]

    def test_get_page_snapshot_extracts_parent_id(self, ops, mock_api, sample_page_data):
        """get_page_snapshot should extract parent_id from ancestors."""
        mock_api.get_page_by_id.return_value = sample_page_data

        snapshot = ops.get_page_snapshot("12345")

        assert snapshot.parent_id == "parent123"

    def test_get_page_snapshot_no_parent(self, ops, mock_api, sample_page_data):
        """get_page_snapshot should handle pages at space root."""
        sample_page_data["ancestors"] = []
        mock_api.get_page_by_id.return_value = sample_page_data

        snapshot = ops.get_page_snapshot("12345")

        assert snapshot.parent_id is None

    def test_get_page_snapshot_empty_page_id_raises(self, ops):
        """get_page_snapshot should raise ValueError for empty page_id."""
        with pytest.raises(ValueError, match="page_id cannot be empty"):
            ops.get_page_snapshot("")

        with pytest.raises(ValueError, match="page_id cannot be empty"):
            ops.get_page_snapshot("   ")

    def test_get_page_snapshot_space_key_from_space_object(self, ops, mock_api):
        """get_page_snapshot should get space_key from space object if not at root."""
        page_data = {
            "id": "12345",
            "title": "Test Page",
            "space": {"key": "FROMSPACE"},
            "body": {"storage": {"value": "<p>Test</p>"}},
            "version": {"number": 1, "when": "2024-01-15T10:30:00.000Z"},
            "metadata": {"labels": {"results": []}},
            "ancestors": []
        }
        mock_api.get_page_by_id.return_value = page_data

        snapshot = ops.get_page_snapshot("12345")

        assert snapshot.space_key == "FROMSPACE"

    def test_get_page_snapshot_parses_timestamp(self, ops, mock_api, sample_page_data):
        """get_page_snapshot should parse last_modified timestamp."""
        mock_api.get_page_by_id.return_value = sample_page_data

        snapshot = ops.get_page_snapshot("12345")

        assert isinstance(snapshot.last_modified, datetime)


class TestApplyOperations:
    """Tests for apply_operations method."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API wrapper."""
        api = Mock()
        return api

    @pytest.fixture
    def ops(self, mock_api):
        """Create PageOperations with mocked API."""
        return PageOperations(api=mock_api)

    def test_apply_operations_update_text(self, ops, mock_api):
        """apply_operations with UPDATE_TEXT should update page content."""
        mock_api.get_page_by_id.return_value = {
            "title": "Test",
            "version": {"number": 1}
        }
        mock_api.update_page.return_value = {
            "version": {"number": 2}
        }

        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Hello",
                new_content="Goodbye"
            )
        ]

        result = ops.apply_operations(
            page_id="12345",
            base_xhtml="<p>Hello World</p>",
            base_version=1,
            operations=operations
        )

        assert result.success is True
        assert result.new_version == 2
        assert result.operations_applied == 1

    def test_apply_operations_version_conflict(self, ops, mock_api):
        """apply_operations should detect version conflicts and retry successfully."""
        # Simulate version conflict on first attempt, then success on retry
        # First call: version check (conflict: 5 != 1)
        # Second call: refetch after conflict
        # Third call: version check on retry (success: 5 == 5)
        mock_api.get_page_by_id.side_effect = [
            {"title": "Test", "version": {"number": 5}, "body": {"storage": {"value": "<p>Hello</p>"}}},
            {"title": "Test", "version": {"number": 5}, "body": {"storage": {"value": "<p>Hello</p>"}}},
            {"title": "Test", "version": {"number": 5}, "body": {"storage": {"value": "<p>Hello</p>"}}},
        ]
        mock_api.update_page.return_value = {"id": "12345", "version": {"number": 6}}

        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Hello",
                new_content="Goodbye"
            )
        ]

        result = ops.apply_operations(
            page_id="12345",
            base_xhtml="<p>Hello</p>",
            base_version=1,
            operations=operations
        )

        # With H3 retry logic, version conflicts are automatically resolved
        assert result.success is True
        assert result.new_version == 6

    def test_apply_operations_api_error(self, ops, mock_api):
        """apply_operations should handle API errors gracefully."""
        mock_api.get_page_by_id.return_value = {
            "title": "Test",
            "version": {"number": 1}
        }
        mock_api.update_page.side_effect = APIAccessError("Connection failed")

        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Hello",
                new_content="Goodbye"
            )
        ]

        result = ops.apply_operations(
            page_id="12345",
            base_xhtml="<p>Hello</p>",
            base_version=1,
            operations=operations
        )

        assert result.success is False
        assert "Connection failed" in result.error

    def test_apply_operations_preserves_macros(self, ops, mock_api):
        """apply_operations should preserve Confluence macros."""
        xhtml = '''<p>Hello</p>
        <ac:structured-macro ac:name="toc">
            <ac:parameter ac:name="style">none</ac:parameter>
        </ac:structured-macro>
        <p>World</p>'''

        mock_api.get_page_by_id.return_value = {
            "title": "Test",
            "version": {"number": 1}
        }
        mock_api.update_page.return_value = {
            "version": {"number": 2}
        }

        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Hello",
                new_content="Goodbye"
            )
        ]

        result = ops.apply_operations(
            page_id="12345",
            base_xhtml=xhtml,
            base_version=1,
            operations=operations
        )

        assert result.success is True
        # Verify macro is in the modified XHTML
        assert "ac:structured-macro" in result.modified_xhtml
        assert 'ac:name="toc"' in result.modified_xhtml

    def test_apply_operations_delete_block(self, ops, mock_api):
        """apply_operations with DELETE_BLOCK should remove content."""
        mock_api.get_page_by_id.return_value = {
            "title": "Test",
            "version": {"number": 1}
        }
        mock_api.update_page.return_value = {
            "version": {"number": 2}
        }

        operations = [
            SurgicalOperation(
                op_type=OperationType.DELETE_BLOCK,
                target_content="Delete me"
            )
        ]

        result = ops.apply_operations(
            page_id="12345",
            base_xhtml="<p>Keep</p><p>Delete me</p>",
            base_version=1,
            operations=operations
        )

        assert result.success is True
        assert "Delete me" not in result.modified_xhtml
        assert "Keep" in result.modified_xhtml


class TestUpdatePageSurgical:
    """Tests for update_page_surgical method."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API wrapper."""
        api = Mock()
        return api

    @pytest.fixture
    def ops(self, mock_api):
        """Create PageOperations with mocked API."""
        return PageOperations(api=mock_api)

    def test_update_page_surgical_success(self, ops, mock_api):
        """update_page_surgical should apply surgical changes."""
        # Setup: page fetch returns XHTML
        mock_api.get_page_by_id.return_value = {
            "id": "12345",
            "title": "Test Page",
            "spaceKey": "TEST",
            "body": {"storage": {"value": "<p>Original text</p>"}},
            "version": {"number": 1, "when": "2024-01-15T10:30:00Z"},
            "metadata": {"labels": {"results": []}},
            "ancestors": []
        }
        mock_api.update_page.return_value = {"version": {"number": 2}}

        result = ops.update_page_surgical(
            page_id="12345",
            new_markdown_content="Modified text"
        )

        assert result.success is True
        assert result.new_version == 2

    def test_update_page_surgical_no_changes(self, ops, mock_api):
        """update_page_surgical should detect when no changes needed."""
        mock_api.get_page_by_id.return_value = {
            "id": "12345",
            "title": "Test Page",
            "spaceKey": "TEST",
            "body": {"storage": {"value": "<p>Same content</p>"}},
            "version": {"number": 1, "when": "2024-01-15T10:30:00Z"},
            "metadata": {"labels": {"results": []}},
            "ancestors": []
        }

        result = ops.update_page_surgical(
            page_id="12345",
            new_markdown_content="Same content"
        )

        assert result.success is True
        assert result.operations_applied == 0

    def test_update_page_surgical_page_not_found(self, ops, mock_api):
        """update_page_surgical should handle page not found."""
        mock_api.get_page_by_id.side_effect = PageNotFoundError("Not found")

        result = ops.update_page_surgical(
            page_id="99999",
            new_markdown_content="New content"
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_update_page_surgical_version_conflict(self, ops, mock_api):
        """update_page_surgical should detect version conflict before upload."""
        # First call returns version 1
        # Second call (pre-upload check) returns version 5
        mock_api.get_page_by_id.side_effect = [
            {
                "id": "12345",
                "title": "Test Page",
                "spaceKey": "TEST",
                "body": {"storage": {"value": "<p>Original</p>"}},
                "version": {"number": 1, "when": "2024-01-15T10:30:00Z"},
                "metadata": {"labels": {"results": []}},
                "ancestors": []
            },
            {
                "version": {"number": 5}  # Changed since we fetched
            }
        ]

        result = ops.update_page_surgical(
            page_id="12345",
            new_markdown_content="Different content entirely"
        )

        assert result.success is False
        assert "conflict" in result.error.lower()


class TestUpdatePageSurgicalAdf:
    """Tests for update_page_surgical_adf method."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API wrapper."""
        api = Mock()
        return api

    @pytest.fixture
    def ops(self, mock_api):
        """Create PageOperations with mocked API."""
        return PageOperations(api=mock_api)

    @pytest.fixture
    def sample_adf(self):
        """Sample ADF document."""
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello World"}
                    ],
                    "attrs": {"localId": "p1"}
                }
            ]
        }

    def test_update_page_surgical_adf_success(self, ops, mock_api, sample_adf):
        """update_page_surgical_adf should apply ADF surgical changes."""
        mock_api.get_page_adf.return_value = {
            "title": "Test Page",
            "version": {"number": 1},
            "body": {
                "atlas_doc_format": {
                    "value": json.dumps(sample_adf)
                }
            }
        }
        mock_api.get_page_by_id.return_value = {"version": {"number": 1}}
        mock_api.update_page_adf.return_value = {"version": {"number": 2}}

        result = ops.update_page_surgical_adf(
            page_id="12345",
            new_markdown_content="Modified World",
            baseline_markdown="Hello World"
        )

        assert result.success is True

    def test_update_page_surgical_adf_no_baseline_uses_fallback(self, ops, mock_api, sample_adf):
        """update_page_surgical_adf without baseline should use full replacement."""
        mock_api.get_page_adf.return_value = {
            "title": "Test Page",
            "version": {"number": 1},
            "body": {
                "atlas_doc_format": {
                    "value": json.dumps(sample_adf)
                }
            }
        }
        mock_api.update_page.return_value = {"version": {"number": 2}}

        result = ops.update_page_surgical_adf(
            page_id="12345",
            new_markdown_content="New content",
            baseline_markdown=None  # No baseline
        )

        assert result.success is True
        assert result.fallback_used is True

    def test_update_page_surgical_adf_page_not_found(self, ops, mock_api):
        """update_page_surgical_adf should handle page not found."""
        mock_api.get_page_adf.side_effect = PageNotFoundError("Not found")

        result = ops.update_page_surgical_adf(
            page_id="99999",
            new_markdown_content="Content",
            baseline_markdown="Old"
        )

        assert result.success is False
        assert "not found" in result.error.lower()


class TestCreatePage:
    """Tests for create_page method."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API wrapper."""
        api = Mock()
        return api

    @pytest.fixture
    def ops(self, mock_api):
        """Create PageOperations with mocked API."""
        return PageOperations(api=mock_api)

    def test_create_page_with_parent_id(self, ops, mock_api):
        """create_page with parent_id should create under parent."""
        mock_api.get_page_by_title.return_value = None  # No duplicate
        mock_api.create_page.return_value = {"id": "new123"}

        result = ops.create_page(
            space_key="TEST",
            title="New Page",
            markdown_content="# Hello\n\nWorld",
            parent_id="parent456"
        )

        assert result.success is True
        assert result.page_id == "new123"
        mock_api.create_page.assert_called_once()
        call_kwargs = mock_api.create_page.call_args[1]
        assert call_kwargs["parent_id"] == "parent456"

    def test_create_page_without_parent_id(self, ops, mock_api):
        """create_page without parent_id should create at space root."""
        mock_api.get_page_by_title.return_value = None
        mock_api.create_page.return_value = {"id": "new123"}

        result = ops.create_page(
            space_key="TEST",
            title="Root Page",
            markdown_content="Content",
            parent_id=None
        )

        assert result.success is True
        call_kwargs = mock_api.create_page.call_args[1]
        assert call_kwargs["parent_id"] is None

    def test_create_page_duplicate_same_parent(self, ops, mock_api):
        """create_page should detect duplicate under same parent."""
        mock_api.get_page_by_title.return_value = {
            "id": "existing123",
            "ancestors": [{"id": "parent456"}]
        }

        result = ops.create_page(
            space_key="TEST",
            title="Duplicate",
            markdown_content="Content",
            parent_id="parent456"
        )

        assert result.success is False
        assert "already exists" in result.error

    def test_create_page_same_title_different_parent_allowed(self, ops, mock_api):
        """create_page should allow same title under different parent."""
        mock_api.get_page_by_title.return_value = {
            "id": "existing123",
            "ancestors": [{"id": "other_parent"}]
        }
        mock_api.create_page.return_value = {"id": "new123"}

        result = ops.create_page(
            space_key="TEST",
            title="Same Title",
            markdown_content="Content",
            parent_id="different_parent"
        )

        assert result.success is True

    def test_create_page_skip_duplicate_check(self, ops, mock_api):
        """create_page with check_duplicate=False should skip check."""
        mock_api.create_page.return_value = {"id": "new123"}

        result = ops.create_page(
            space_key="TEST",
            title="Title",
            markdown_content="Content",
            check_duplicate=False
        )

        assert result.success is True
        mock_api.get_page_by_title.assert_not_called()

    def test_create_page_api_error(self, ops, mock_api):
        """create_page should handle API errors."""
        mock_api.get_page_by_title.return_value = None
        mock_api.create_page.side_effect = Exception("Network error")

        result = ops.create_page(
            space_key="TEST",
            title="Page",
            markdown_content="Content"
        )

        assert result.success is False
        assert "Network error" in result.error


class TestUpdatePageContent:
    """Tests for update_page_content method."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API wrapper."""
        api = Mock()
        return api

    @pytest.fixture
    def ops(self, mock_api):
        """Create PageOperations with mocked API."""
        return PageOperations(api=mock_api)

    def test_update_page_content_success(self, ops, mock_api):
        """update_page_content should replace entire page."""
        mock_api.get_page_by_id.return_value = {
            "title": "Test",
            "version": {"number": 1}
        }
        mock_api.update_page.return_value = {"version": {"number": 2}}

        result = ops.update_page_content(
            page_id="12345",
            markdown_content="# New Content"
        )

        assert result.success is True
        assert result.new_version == 2

    def test_update_page_content_page_not_found(self, ops, mock_api):
        """update_page_content should handle page not found."""
        mock_api.get_page_by_id.side_effect = PageNotFoundError("Not found")

        result = ops.update_page_content(
            page_id="99999",
            markdown_content="Content"
        )

        assert result.success is False
        assert "not found" in result.error.lower()


class TestUpdatePageParent:
    """Tests for update_page_parent method."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API wrapper."""
        api = Mock()
        return api

    @pytest.fixture
    def ops(self, mock_api):
        """Create PageOperations with mocked API."""
        return PageOperations(api=mock_api)

    def test_update_page_parent_success(self, ops, mock_api):
        """update_page_parent should move page to new parent."""
        mock_api.get_page_by_id.return_value = {
            "title": "Page",
            "body": {"storage": {"value": "<p>Content</p>"}},
            "version": {"number": 1}
        }
        mock_api.update_page.return_value = {"version": {"number": 2}}

        result = ops.update_page_parent(
            page_id="12345",
            parent_id="new_parent"
        )

        assert result.success is True
        # Verify ancestors were passed
        call_kwargs = mock_api.update_page.call_args[1]
        assert call_kwargs["ancestors"] == [{"id": "new_parent"}]

    def test_update_page_parent_move_to_root(self, ops, mock_api):
        """update_page_parent with None should move to space root."""
        mock_api.get_page_by_id.return_value = {
            "title": "Page",
            "body": {"storage": {"value": "<p>Content</p>"}},
            "version": {"number": 1}
        }
        mock_api.update_page.return_value = {"version": {"number": 2}}

        result = ops.update_page_parent(
            page_id="12345",
            parent_id=None
        )

        assert result.success is True
        call_kwargs = mock_api.update_page.call_args[1]
        assert call_kwargs["ancestors"] == []


class TestDeletePage:
    """Tests for delete_page method."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API wrapper."""
        api = Mock()
        return api

    @pytest.fixture
    def ops(self, mock_api):
        """Create PageOperations with mocked API."""
        return PageOperations(api=mock_api)

    def test_delete_page_success(self, ops, mock_api):
        """delete_page should call API to delete."""
        mock_api.delete_page.return_value = None

        ops.delete_page("12345")

        mock_api.delete_page.assert_called_once_with("12345")

    def test_delete_page_raises_on_error(self, ops, mock_api):
        """delete_page should propagate errors."""
        mock_api.delete_page.side_effect = PageNotFoundError("Not found")

        with pytest.raises(PageNotFoundError):
            ops.delete_page("99999")


class TestPreserveMacrosForMarkdown:
    """Tests for _preserve_macros_for_markdown helper."""

    @pytest.fixture
    def ops(self):
        """Create PageOperations with mocked API."""
        return PageOperations(api=Mock())

    def test_preserve_macros_replaces_with_placeholders(self, ops):
        """_preserve_macros_for_markdown should replace macros with placeholders."""
        xhtml = '''<p>Before</p>
        <ac:structured-macro ac:name="info">
            <ac:rich-text-body>Info text</ac:rich-text-body>
        </ac:structured-macro>
        <p>After</p>'''

        result, macros = ops._preserve_macros_for_markdown(xhtml)

        assert len(macros) == 1
        assert "CONFLUENCE_MACRO_PLACEHOLDER_0" in macros[0]["placeholder"]
        assert "ac:structured-macro" in macros[0]["html"]

    def test_preserve_macros_handles_multiple_macros(self, ops):
        """_preserve_macros_for_markdown should handle multiple macros."""
        xhtml = '''<ac:structured-macro ac:name="toc"/>
        <p>Content</p>
        <ac:structured-macro ac:name="info">Text</ac:structured-macro>'''

        result, macros = ops._preserve_macros_for_markdown(xhtml)

        assert len(macros) == 2

    def test_preserve_macros_no_macros(self, ops):
        """_preserve_macros_for_markdown should handle content without macros."""
        xhtml = "<p>Simple content</p>"

        result, macros = ops._preserve_macros_for_markdown(xhtml)

        assert len(macros) == 0
        assert "Simple content" in result


class TestFilterTitleHeading:
    """Tests for _filter_title_heading helper."""

    @pytest.fixture
    def ops(self):
        """Create PageOperations with mocked API."""
        return PageOperations(api=Mock())

    def test_filter_title_heading_removes_matching_h1(self, ops):
        """_filter_title_heading should remove H1 matching page title."""
        blocks = [
            ContentBlock(block_type=BlockType.HEADING, content="My Page Title", level=1, index=0),
            ContentBlock(block_type=BlockType.PARAGRAPH, content="Content here", index=1),
        ]

        result = ops._filter_title_heading(blocks, "My Page Title")

        assert len(result) == 1
        assert result[0].content == "Content here"

    def test_filter_title_heading_keeps_non_matching_h1(self, ops):
        """_filter_title_heading should keep H1 not matching title."""
        blocks = [
            ContentBlock(block_type=BlockType.HEADING, content="Different Heading", level=1, index=0),
            ContentBlock(block_type=BlockType.PARAGRAPH, content="Content", index=1),
        ]

        result = ops._filter_title_heading(blocks, "My Page Title")

        assert len(result) == 2

    def test_filter_title_heading_ignores_h2(self, ops):
        """_filter_title_heading should not filter H2 headings."""
        blocks = [
            ContentBlock(block_type=BlockType.HEADING, content="My Page Title", level=2, index=0),
            ContentBlock(block_type=BlockType.PARAGRAPH, content="Content", index=1),
        ]

        result = ops._filter_title_heading(blocks, "My Page Title")

        assert len(result) == 2

    def test_filter_title_heading_empty_blocks(self, ops):
        """_filter_title_heading should handle empty block list."""
        result = ops._filter_title_heading([], "Title")

        assert result == []

    def test_filter_title_heading_normalizes_whitespace(self, ops):
        """_filter_title_heading should normalize whitespace for comparison."""
        blocks = [
            ContentBlock(block_type=BlockType.HEADING, content="My  Page   Title", level=1, index=0),
            ContentBlock(block_type=BlockType.PARAGRAPH, content="Content", index=1),
        ]

        result = ops._filter_title_heading(blocks, "My Page Title")

        assert len(result) == 1


class TestUpdateOrCreate:
    """Tests for update_or_create method."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API wrapper."""
        api = Mock()
        return api

    @pytest.fixture
    def ops(self, mock_api):
        """Create PageOperations with mocked API."""
        return PageOperations(api=mock_api)

    def test_update_or_create_with_page_id_updates(self, ops, mock_api):
        """update_or_create with page_id should update existing page."""
        mock_api.get_page_by_id.return_value = {
            "id": "12345",
            "title": "Test",
            "spaceKey": "TEST",
            "body": {"storage": {"value": "<p>Old</p>"}},
            "version": {"number": 1, "when": "2024-01-15T10:30:00Z"},
            "metadata": {"labels": {"results": []}},
            "ancestors": []
        }
        mock_api.update_page.return_value = {"version": {"number": 2}}

        operations = [
            SurgicalOperation(
                op_type=OperationType.UPDATE_TEXT,
                target_content="Old",
                new_content="New"
            )
        ]

        result = ops.update_or_create(
            space_key="TEST",
            page_id="12345",
            parent_id=None,
            title="Test",
            operations=operations
        )

        assert result.success is True

    def test_update_or_create_without_page_id_returns_error(self, ops, mock_api):
        """update_or_create without page_id should return error."""
        result = ops.update_or_create(
            space_key="TEST",
            page_id=None,
            parent_id="parent123",
            title="New Page",
            operations=[]
        )

        assert result.success is False
        assert "create_page()" in result.error

    def test_update_or_create_page_not_found(self, ops, mock_api):
        """update_or_create with non-existent page_id should return error."""
        mock_api.get_page_by_id.side_effect = PageNotFoundError("Not found")

        result = ops.update_or_create(
            space_key="TEST",
            page_id="nonexistent",
            parent_id=None,
            title="Title",
            operations=[]
        )

        assert result.success is False
        assert "not found" in result.error.lower()


class TestGetPageVersions:
    """Tests for get_page_versions method."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API wrapper."""
        api = Mock()
        return api

    @pytest.fixture
    def ops(self, mock_api):
        """Create PageOperations with mocked API."""
        return PageOperations(api=mock_api)

    def test_get_page_versions_returns_list(self, ops, mock_api):
        """get_page_versions should return list of PageVersion objects."""
        mock_api.get_page_versions.return_value = [
            {
                "number": 1,
                "when": "2024-01-01T10:00:00Z",
                "by": {"displayName": "Alice"},
                "message": "Initial"
            },
            {
                "number": 2,
                "when": "2024-01-02T11:00:00Z",
                "by": {"displayName": "Bob"},
                "message": None
            }
        ]

        versions = ops.get_page_versions("12345")

        assert len(versions) == 2
        assert versions[0].version == 1
        assert versions[0].modified_by == "Alice"
        assert versions[0].message == "Initial"
        assert versions[1].version == 2
        assert versions[1].message is None
