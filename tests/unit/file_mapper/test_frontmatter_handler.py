"""Unit tests for file_mapper.frontmatter_handler module.

Note: LocalPage uses model with:
- file_path: path to the markdown file
- page_id: Confluence page ID (None for new files)
- content: markdown content (without frontmatter)
- space_key: Confluence space key
- confluence_base_url: Base Confluence URL

Frontmatter uses page_id format only.
"""

import pytest
import yaml

from src.file_mapper.frontmatter_handler import FrontmatterHandler
from src.file_mapper.errors import FrontmatterError
from src.file_mapper.models import LocalPage


class TestFrontmatterHandlerParse:
    """Test cases for FrontmatterHandler.parse() method."""

    def test_parse_valid_frontmatter_with_page_id(self):
        """Parse valid markdown with frontmatter including confluence_url."""
        content = """---
confluence_url: https://example.atlassian.net/wiki/spaces/TEAM/pages/123456
---
# Test Page

This is the content.
"""
        result = FrontmatterHandler.parse("/path/to/file.md", content)

        assert result.file_path == "/path/to/file.md"
        assert result.page_id == "123456"
        assert result.space_key == "TEAM"
        assert result.confluence_base_url == "https://example.atlassian.net/wiki"
        assert result.content == "# Test Page\n\nThis is the content.\n"

    def test_parse_valid_frontmatter_without_confluence_url(self):
        """Parse valid markdown with frontmatter but no confluence_url."""
        content = """---
some_field: value
---
This is new content.
"""
        result = FrontmatterHandler.parse("/path/to/new.md", content)

        assert result.page_id is None
        assert result.space_key is None
        assert result.content == "This is new content.\n"

    def test_parse_empty_content_after_frontmatter(self):
        """Parse markdown with valid frontmatter but no content."""
        content = """---
confluence_url: https://example.atlassian.net/wiki/spaces/TEST/pages/123
---
"""
        result = FrontmatterHandler.parse("/path/to/empty.md", content)

        assert result.page_id == "123"
        assert result.space_key == "TEST"
        assert result.content == ""

    def test_parse_multiline_content(self):
        """Parse markdown with multiline content."""
        content = """---
page_id: '123'
---
# Heading

Paragraph 1.

Paragraph 2.

- List item 1
- List item 2
"""
        result = FrontmatterHandler.parse("/path/to/file.md", content)

        expected_content = """# Heading

Paragraph 1.

Paragraph 2.

- List item 1
- List item 2
"""
        assert result.content == expected_content

    def test_parse_content_with_code_blocks(self):
        """Parse markdown with code blocks in content."""
        content = """---
page_id: '123'
---
Here is some code:

```python
def hello():
    print("world")
```
"""
        result = FrontmatterHandler.parse("/path/to/code.md", content)

        assert "```python" in result.content
        assert 'def hello():' in result.content

    def test_parse_no_frontmatter_returns_new_file(self):
        """Parse markdown without frontmatter returns LocalPage with page_id=None (new file)."""
        content = "# Just a heading\n\nNo frontmatter here."

        result = FrontmatterHandler.parse("/path/to/file.md", content)

        assert result.file_path == "/path/to/file.md"
        assert result.page_id is None
        assert result.content == content

    def test_parse_invalid_yaml_syntax_raises_error(self):
        """Parse markdown with invalid YAML syntax raises FrontmatterError."""
        content = """---
confluence_url: "https://example.atlassian.net/wiki/spaces/TEST/pages/123"
invalid yaml: [unclosed bracket
---
Content
"""
        with pytest.raises(FrontmatterError) as exc_info:
            FrontmatterHandler.parse("/path/to/file.md", content)

        assert exc_info.value.file_path == "/path/to/file.md"
        assert "Invalid YAML syntax" in str(exc_info.value)

    def test_parse_frontmatter_not_dict_raises_error(self):
        """Parse markdown with non-dict frontmatter raises error."""
        content = """---
- item1
- item2
- item3
---
Content
"""
        with pytest.raises(FrontmatterError) as exc_info:
            FrontmatterHandler.parse("/path/to/file.md", content)

        assert "Frontmatter must be a YAML dictionary, got list" in str(exc_info.value)

    def test_parse_frontmatter_string_raises_error(self):
        """Parse markdown with string frontmatter raises error."""
        content = """---
just a string
---
Content
"""
        with pytest.raises(FrontmatterError) as exc_info:
            FrontmatterHandler.parse("/path/to/file.md", content)

        assert "Frontmatter must be a YAML dictionary, got str" in str(exc_info.value)

    def test_parse_with_extra_fields_ignored(self):
        """Parse markdown with extra fields - extra fields are ignored."""
        content = """---
confluence_url: https://example.atlassian.net/wiki/spaces/TEST/pages/123
extra_field: "This is extra"
another_field: 42
---
Content
"""
        result = FrontmatterHandler.parse("/path/to/file.md", content)

        assert result.page_id == "123"
        assert result.space_key == "TEST"
        assert result.content == "Content\n"

class TestFrontmatterHandlerGenerate:
    """Test cases for FrontmatterHandler.generate() method."""

    def test_generate_with_confluence_url(self):
        """Generate markdown with confluence_url in frontmatter."""
        local_page = LocalPage(
            file_path="/path/to/file.md",
            page_id="123456",
            content="# Test Page\n\nContent here.",
            space_key="TEAM",
            confluence_base_url="https://example.atlassian.net/wiki"
        )

        result = FrontmatterHandler.generate(local_page)

        assert result.startswith("---\n")
        assert "confluence_url: https://example.atlassian.net/wiki/spaces/TEAM/pages/123456" in result
        assert result.endswith("# Test Page\n\nContent here.")

    def test_generate_with_null_page_id(self):
        """Generate markdown with page_id set to null."""
        local_page = LocalPage(
            file_path="/path/to/new.md",
            page_id=None,
            content="New content."
        )

        result = FrontmatterHandler.generate(local_page)

        # New files without page_id have no frontmatter (cleaner)
        assert result == "New content."
        assert "---" not in result

    def test_generate_with_empty_content(self):
        """Generate markdown with empty content."""
        local_page = LocalPage(
            file_path="/path/to/empty.md",
            page_id="123",
            content="",
            space_key="TEST",
            confluence_base_url="https://example.atlassian.net/wiki"
        )

        result = FrontmatterHandler.generate(local_page)

        assert result.startswith("---\n")
        assert "confluence_url:" in result
        assert result.endswith("---\n")

    def test_generate_with_multiline_content(self):
        """Generate markdown preserves multiline content."""
        content = """# Heading 1

Paragraph 1.

## Heading 2

Paragraph 2.
"""
        local_page = LocalPage(
            file_path="/path/to/file.md",
            page_id="123",
            content=content,
            space_key="TEST",
            confluence_base_url="https://example.atlassian.net/wiki"
        )

        result = FrontmatterHandler.generate(local_page)

        assert content in result
        assert result.count("---") == 2

    def test_generate_parseable_output(self):
        """Generate output that can be parsed back."""
        original_page = LocalPage(
            file_path="/path/to/file.md",
            page_id="123456",
            content="# Test\n\nContent here.",
            space_key="TEAM",
            confluence_base_url="https://example.atlassian.net/wiki"
        )

        generated = FrontmatterHandler.generate(original_page)
        parsed = FrontmatterHandler.parse("/path/to/file.md", generated)

        assert parsed.page_id == original_page.page_id
        assert parsed.space_key == original_page.space_key
        assert parsed.content == original_page.content

    def test_generate_with_unicode_content(self):
        """Generate markdown with unicode characters."""
        local_page = LocalPage(
            file_path="/path/to/file.md",
            page_id="123",
            content="Content with unicode: 你好世界 🎉",
            space_key="TEST",
            confluence_base_url="https://example.atlassian.net/wiki"
        )

        result = FrontmatterHandler.generate(local_page)

        assert "你好" in result
        assert "🎉" in result

    def test_generate_format_has_correct_structure(self):
        """Generate output has correct frontmatter structure."""
        local_page = LocalPage(
            file_path="/path/to/file.md",
            page_id="123",
            content="Content",
            space_key="TEST",
            confluence_base_url="https://example.atlassian.net/wiki"
        )

        result = FrontmatterHandler.generate(local_page)

        lines = result.split('\n')
        assert lines[0] == "---"

        # Find the closing delimiter
        closing_index = None
        for i in range(1, len(lines)):
            if lines[i] == "---":
                closing_index = i
                break

        assert closing_index is not None
        assert closing_index > 1  # Should have content between delimiters

    def test_generate_raises_error_without_context(self):
        """Generate raises ValueError when space_key or base_url is missing."""
        local_page = LocalPage(
            file_path="/path/to/file.md",
            page_id="12345678",
            content="# Test\n\nContent."
            # No space_key or confluence_base_url
        )

        with pytest.raises(ValueError) as exc_info:
            FrontmatterHandler.generate(local_page)

        assert "space_key and confluence_base_url are required" in str(exc_info.value)

    def test_generate_preserves_user_fields(self):
        """Generate preserves user-added frontmatter fields."""
        # Content already has frontmatter with custom fields
        local_page = LocalPage(
            file_path="/path/to/file.md",
            page_id="12345678",
            content="---\nauthor: John Doe\ntags: [test, example]\n---\n# Test\n\nContent.",
            space_key="TEAM",
            confluence_base_url="https://example.atlassian.net/wiki"
        )

        result = FrontmatterHandler.generate(local_page)

        # confluence_url should be first
        assert result.startswith("---\nconfluence_url:")
        # User fields should be preserved
        assert "author: John Doe" in result
        assert "tags:" in result


class TestFrontmatterHandlerExtractFrontmatterAndContent:
    """Test cases for FrontmatterHandler.extract_frontmatter_and_content() method."""

    def test_extract_valid_frontmatter(self):
        """Extract frontmatter and content from valid markdown."""
        content = """---
confluence_url: https://example.atlassian.net/wiki/spaces/TEST/pages/123456
---
# Content Here
"""
        frontmatter, markdown = FrontmatterHandler.extract_frontmatter_and_content(content)

        assert isinstance(frontmatter, dict)
        assert "confluence_url" in frontmatter
        assert frontmatter["confluence_url"] == "https://example.atlassian.net/wiki/spaces/TEST/pages/123456"
        assert markdown == "# Content Here\n"

    def test_extract_no_frontmatter_returns_empty_dict(self):
        """Extract from content without frontmatter returns empty dict and full content."""
        content = "Just plain markdown content."

        frontmatter, markdown = FrontmatterHandler.extract_frontmatter_and_content(content)

        assert frontmatter == {}
        assert markdown == content

    def test_extract_invalid_yaml_raises_error(self):
        """Extract with invalid YAML syntax raises error."""
        content = """---
invalid: [unclosed
---
Content
"""
        with pytest.raises(FrontmatterError) as exc_info:
            FrontmatterHandler.extract_frontmatter_and_content(content)

        assert "Invalid YAML syntax" in str(exc_info.value)

    def test_extract_non_dict_frontmatter_raises_error(self):
        """Extract with non-dict frontmatter raises error."""
        content = """---
- list item
---
Content
"""
        with pytest.raises(FrontmatterError) as exc_info:
            FrontmatterHandler.extract_frontmatter_and_content(content)

        assert "Frontmatter must be a YAML dictionary" in str(exc_info.value)

    def test_extract_empty_content(self):
        """Extract with empty content after frontmatter."""
        content = """---
page_id: '123'
---
"""
        frontmatter, markdown = FrontmatterHandler.extract_frontmatter_and_content(content)

        assert markdown == ""

    def test_extract_preserves_content_structure(self):
        """Extract preserves content structure including whitespace."""
        content = """---
field: value
---
Line 1

Line 3 (skipped line 2)

  Indented line
"""
        frontmatter, markdown = FrontmatterHandler.extract_frontmatter_and_content(content)

        expected = """Line 1

Line 3 (skipped line 2)

  Indented line
"""
        assert markdown == expected


class TestFrontmatterHandlerConstants:
    """Test cases for FrontmatterHandler class constants."""

    def test_required_fields_constant(self):
        """Required fields constant is empty (no required fields for minimal frontmatter)."""
        assert FrontmatterHandler.REQUIRED_FIELDS == set()

    def test_frontmatter_pattern_matches_valid_frontmatter(self):
        """Frontmatter pattern regex matches valid frontmatter."""
        content = """---
field: value
---
Content"""
        match = FrontmatterHandler.FRONTMATTER_PATTERN.match(content)

        assert match is not None
        assert match.group(1) == "field: value"

    def test_frontmatter_pattern_does_not_match_invalid(self):
        """Frontmatter pattern does not match invalid format."""
        content = "No frontmatter here"
        match = FrontmatterHandler.FRONTMATTER_PATTERN.match(content)

        assert match is None


