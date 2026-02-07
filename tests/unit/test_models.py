"""Unit tests for models module."""

from src.models.confluence_page import ConfluencePage
from src.models.conversion_result import ConversionResult


class TestConfluencePage:
    """Test cases for ConfluencePage dataclass."""

    def test_confluence_page_creation(self):
        """ConfluencePage can be created with all required fields."""
        page = ConfluencePage(
            page_id="123456",
            space_key="TEST",
            title="Test Page",
            content_storage="<p>Test content</p>",
            version=1,
            labels=["test", "example"],
            parent_id="789",
            children=["111", "222"]
        )

        assert page.page_id == "123456"
        assert page.space_key == "TEST"
        assert page.title == "Test Page"
        assert page.content_storage == "<p>Test content</p>"
        assert page.version == 1
        assert page.labels == ["test", "example"]
        assert page.parent_id == "789"
        assert page.children == ["111", "222"]

    def test_confluence_page_with_optional_none(self):
        """ConfluencePage can have None for parent_id."""
        page = ConfluencePage(
            page_id="123456",
            space_key="TEST",
            title="Root Page",
            content_storage="<p>Content</p>",
            version=1,
            labels=[],
            parent_id=None,
            children=[]
        )

        assert page.parent_id is None

    def test_confluence_page_with_empty_lists(self):
        """ConfluencePage can have empty lists for labels and children."""
        page = ConfluencePage(
            page_id="123456",
            space_key="TEST",
            title="Test Page",
            content_storage="<p>Content</p>",
            version=1,
            labels=[],
            parent_id=None,
            children=[]
        )

        assert page.labels == []
        assert page.children == []

    def test_confluence_page_equality(self):
        """Two ConfluencePage instances with same data should be equal."""
        page1 = ConfluencePage(
            page_id="123",
            space_key="TEST",
            title="Page",
            content_storage="<p>Content</p>",
            version=1,
            labels=[],
            parent_id=None,
            children=[]
        )

        page2 = ConfluencePage(
            page_id="123",
            space_key="TEST",
            title="Page",
            content_storage="<p>Content</p>",
            version=1,
            labels=[],
            parent_id=None,
            children=[]
        )

        assert page1 == page2

    def test_confluence_page_inequality(self):
        """Two ConfluencePage instances with different data should not be equal."""
        page1 = ConfluencePage(
            page_id="123",
            space_key="TEST",
            title="Page 1",
            content_storage="<p>Content</p>",
            version=1,
            labels=[],
            parent_id=None,
            children=[]
        )

        page2 = ConfluencePage(
            page_id="456",
            space_key="TEST",
            title="Page 2",
            content_storage="<p>Content</p>",
            version=1,
            labels=[],
            parent_id=None,
            children=[]
        )

        assert page1 != page2


class TestConversionResult:
    """Test cases for ConversionResult dataclass."""

    def test_conversion_result_with_all_fields(self):
        """ConversionResult can be created with all fields."""
        result = ConversionResult(
            markdown="# Test\n\nThis is a test.",
            metadata={"page_id": "123", "title": "Test Page"},
            warnings=["Unsupported macro: jira", "Unsupported macro: status"]
        )

        assert result.markdown == "# Test\n\nThis is a test."
        assert result.metadata == {"page_id": "123", "title": "Test Page"}
        assert result.warnings == ["Unsupported macro: jira", "Unsupported macro: status"]

    def test_conversion_result_with_defaults(self):
        """ConversionResult uses empty dict/list as defaults for metadata/warnings."""
        result = ConversionResult(markdown="# Test")

        assert result.markdown == "# Test"
        assert result.metadata == {}
        assert result.warnings == []

    def test_conversion_result_metadata_is_mutable(self):
        """ConversionResult metadata can be modified after creation."""
        result = ConversionResult(markdown="# Test")
        result.metadata["key"] = "value"

        assert result.metadata == {"key": "value"}

    def test_conversion_result_warnings_is_mutable(self):
        """ConversionResult warnings can be modified after creation."""
        result = ConversionResult(markdown="# Test")
        result.warnings.append("Warning 1")
        result.warnings.append("Warning 2")

        assert result.warnings == ["Warning 1", "Warning 2"]

    def test_conversion_result_equality(self):
        """Two ConversionResult instances with same data should be equal."""
        result1 = ConversionResult(
            markdown="# Test",
            metadata={"key": "value"},
            warnings=["warning"]
        )

        result2 = ConversionResult(
            markdown="# Test",
            metadata={"key": "value"},
            warnings=["warning"]
        )

        assert result1 == result2

    def test_conversion_result_inequality(self):
        """Two ConversionResult instances with different data should not be equal."""
        result1 = ConversionResult(markdown="# Test 1")
        result2 = ConversionResult(markdown="# Test 2")

        assert result1 != result2

    def test_conversion_result_default_factories_create_separate_instances(self):
        """Each ConversionResult should get its own metadata and warnings instances."""
        result1 = ConversionResult(markdown="# Test 1")
        result2 = ConversionResult(markdown="# Test 2")

        result1.metadata["key"] = "value1"
        result1.warnings.append("warning1")

        result2.metadata["key"] = "value2"
        result2.warnings.append("warning2")

        # Ensure they don't share the same dict/list instances
        assert result1.metadata != result2.metadata
        assert result1.warnings != result2.warnings
