"""Unit tests for YAML depth validation in FrontmatterHandler.

Tests H1: YAML depth validation to prevent DoS attacks.
"""

import pytest

from src.file_mapper.frontmatter_handler import FrontmatterHandler
from src.file_mapper.errors import FrontmatterError


class TestYAMLDepthValidation:
    """Test cases for YAML depth validation (H1)."""

    def test_shallow_yaml_accepted(self):
        """Verify shallow YAML (depth 3) is accepted."""
        content = """---
level1:
  level2:
    level3: value
---
# Content
"""
        result = FrontmatterHandler.parse("/path/to/file.md", content)
        assert result.content == "# Content\n"

    def test_max_depth_yaml_accepted(self):
        """Verify YAML at exactly max depth (10) is accepted."""
        # Build a YAML structure with exactly 10 levels of nesting
        # depth 0: root dict
        # depth 1-9: nested dicts (level1 through level9)
        # depth 10: final value
        yaml_content = "level1:\n"
        indent = "  "
        for i in range(2, 10):  # Creates level2 through level9
            yaml_content += f"{indent * (i-1)}level{i}:\n"
        yaml_content += f"{indent * 9}value: final\n"

        content = f"---\n{yaml_content}---\n# Content\n"

        result = FrontmatterHandler.parse("/path/to/file.md", content)
        assert result.content == "# Content\n"

    def test_deep_yaml_rejected(self):
        """Verify deeply nested YAML (15 levels) is rejected (CRITICAL TEST)."""
        # Build a YAML structure with 15 levels of nesting (exceeds MAX_YAML_DEPTH=10)
        yaml_content = "level1:\n"
        indent = "  "
        for i in range(2, 16):
            yaml_content += f"{indent * (i-1)}level{i}:\n"
        yaml_content += f"{indent * 15}value: too_deep\n"

        content = f"---\n{yaml_content}---\n# Content\n"

        with pytest.raises(FrontmatterError) as exc_info:
            FrontmatterHandler.parse("/path/to/file.md", content)

        assert "exceeds maximum depth" in str(exc_info.value)
        assert "10" in str(exc_info.value)

    def test_yaml_bomb_list_nested_rejected(self):
        """Verify YAML bomb with nested lists is rejected."""
        # Build a list-based deeply nested structure
        yaml_content = "data:\n"
        indent = "  "
        for i in range(15):
            yaml_content += f"{indent * (i+1)}- item:\n"

        content = f"---\n{yaml_content}---\n# Content\n"

        with pytest.raises(FrontmatterError) as exc_info:
            FrontmatterHandler.parse("/path/to/file.md", content)

        assert "exceeds maximum depth" in str(exc_info.value)

    def test_yaml_bomb_mixed_dict_list_rejected(self):
        """Verify YAML bomb with mixed dicts and lists is rejected."""
        # Build a structure alternating dicts and lists
        yaml_content = "root:\n"
        indent = "  "
        for i in range(15):
            if i % 2 == 0:
                yaml_content += f"{indent * (i+1)}dict{i}:\n"
            else:
                yaml_content += f"{indent * (i+1)}- item:\n"

        content = f"---\n{yaml_content}---\n# Content\n"

        with pytest.raises(FrontmatterError) as exc_info:
            FrontmatterHandler.parse("/path/to/file.md", content)

        assert "exceeds maximum depth" in str(exc_info.value)

    def test_extract_frontmatter_validates_depth(self):
        """Verify extract_frontmatter_and_content also validates depth."""
        # Build deep YAML
        yaml_content = "level1:\n"
        indent = "  "
        for i in range(2, 16):
            yaml_content += f"{indent * (i-1)}level{i}:\n"
        yaml_content += f"{indent * 15}value: too_deep\n"

        content = f"---\n{yaml_content}---\n# Content\n"

        with pytest.raises(FrontmatterError) as exc_info:
            FrontmatterHandler.extract_frontmatter_and_content(content)

        assert "exceeds maximum depth" in str(exc_info.value)

    def test_complex_valid_structure_accepted(self):
        """Verify complex but valid structure (depth 8) is accepted."""
        content = """---
confluence_url: https://example.atlassian.net/wiki/spaces/TEAM/pages/123456
metadata:
  author:
    name: John Doe
    contact:
      email: john@example.com
      social:
        twitter: "@johndoe"
        links:
          github: "https://github.com/johndoe"
tags:
  - engineering
  - documentation
  - testing
---
# Content
"""
        result = FrontmatterHandler.parse("/path/to/file.md", content)
        assert result.content == "# Content\n"
        assert result.page_id == "123456"

    def test_depth_validation_with_empty_dicts(self):
        """Verify depth validation works with empty nested dicts."""
        # Build structure with empty dicts at each level
        yaml_content = "level1:\n"
        indent = "  "
        for i in range(2, 16):
            yaml_content += f"{indent * (i-1)}level{i}:\n"

        content = f"---\n{yaml_content}---\n# Content\n"

        with pytest.raises(FrontmatterError) as exc_info:
            FrontmatterHandler.parse("/path/to/file.md", content)

        assert "exceeds maximum depth" in str(exc_info.value)

    def test_wide_but_shallow_structure_accepted(self):
        """Verify wide but shallow structure is accepted."""
        # 100 keys at depth 1
        yaml_content = "\n".join([f"key{i}: value{i}" for i in range(100)])

        content = f"---\n{yaml_content}\n---\n# Content\n"

        result = FrontmatterHandler.parse("/path/to/file.md", content)
        assert result.content == "# Content\n"

    def test_generate_silently_handles_deep_existing_frontmatter(self):
        """Verify generate() silently ignores deeply nested existing frontmatter."""
        from src.file_mapper.models import LocalPage

        # Build deep YAML in content
        yaml_content = "level1:\n"
        indent = "  "
        for i in range(2, 16):
            yaml_content += f"{indent * (i-1)}level{i}:\n"
        yaml_content += f"{indent * 15}value: too_deep\n"

        content_with_deep_yaml = f"---\n{yaml_content}---\n# Test Content\n"

        local_page = LocalPage(
            file_path="/path/to/file.md",
            page_id="123456",
            content=content_with_deep_yaml,
            space_key="TEAM",
            confluence_base_url="https://example.atlassian.net/wiki"
        )

        # Should not raise - existing frontmatter is ignored if invalid
        result = FrontmatterHandler.generate(local_page)

        # Should still generate valid frontmatter with confluence_url
        assert "confluence_url: https://example.atlassian.net/wiki/spaces/TEAM/pages/123456" in result
        assert "# Test Content" in result
