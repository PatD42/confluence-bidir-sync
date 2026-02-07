"""YAML frontmatter parsing and generation for markdown files.

This module handles reading and writing YAML frontmatter in markdown files.
Frontmatter contains a confluence_url linking local files to Confluence pages.

The confluence_url format provides:
- Direct link to the Confluence page
- Space key (extractable from URL)
- Page ID (extractable from URL)

Other metadata (title) is derived from config and file path.
Sync timestamps are tracked globally in state.yaml, not per-file.
"""

import re
from typing import Optional, Tuple
import yaml

from .errors import FrontmatterError
from .models import LocalPage


class FrontmatterHandler:
    """Handles YAML frontmatter operations for markdown files.

    Provides methods to parse frontmatter from markdown content and
    generate markdown content with frontmatter containing confluence_url.

    Frontmatter format:
        - confluence_url: Full Confluence page URL (contains space key and page ID)
        - No frontmatter: Treated as new file (not yet synced)

    When updating files with existing frontmatter, additional user fields
    are preserved and confluence_url is added/updated as the first field.
    """

    # Regex pattern to match YAML frontmatter (between --- delimiters)
    FRONTMATTER_PATTERN = re.compile(
        r'^---\s*\n(.*?)\n---\s*\n',
        re.DOTALL
    )

    # Regex to extract space_key and page_id from confluence_url
    # Format: https://domain.atlassian.net/wiki/spaces/{space-key}/pages/{page-id}
    # Also supports: https://domain.atlassian.net/wiki/spaces/{space-key}/pages/{page-id}/{title}
    CONFLUENCE_URL_PATTERN = re.compile(
        r'https?://[^/]+/wiki/spaces/([^/]+)/pages/(\d+)(?:/.*)?$'
    )

    # No required fields - confluence_url is optional for new files
    REQUIRED_FIELDS: set = set()

    # Maximum allowed depth for YAML structures to prevent DoS attacks
    MAX_YAML_DEPTH = 10

    @classmethod
    def _validate_yaml_depth(cls, obj, current_depth: int = 0, max_depth: int = MAX_YAML_DEPTH) -> None:
        """Validate that YAML structure depth doesn't exceed maximum.

        Prevents YAML bomb DoS attacks from deeply nested structures.

        Args:
            obj: YAML object (dict, list, or primitive)
            current_depth: Current nesting depth
            max_depth: Maximum allowed depth

        Raises:
            FrontmatterError: If depth exceeds maximum
        """
        if current_depth > max_depth:
            raise FrontmatterError(
                "<yaml>",
                f"YAML structure exceeds maximum depth of {max_depth}. "
                f"This may indicate a YAML bomb attack or overly complex frontmatter."
            )

        if isinstance(obj, dict):
            for value in obj.values():
                cls._validate_yaml_depth(value, current_depth + 1, max_depth)
        elif isinstance(obj, list):
            for item in obj:
                cls._validate_yaml_depth(item, current_depth + 1, max_depth)

    @classmethod
    def build_confluence_url(
        cls,
        base_url: str,
        space_key: str,
        page_id: str
    ) -> str:
        """Build a Confluence page URL from components.

        Args:
            base_url: Confluence base URL (e.g., https://domain.atlassian.net or
                     https://domain.atlassian.net/wiki)
            space_key: Space key (e.g., "TEAM")
            page_id: Page ID (e.g., "12345678")

        Returns:
            Full Confluence URL: https://domain.atlassian.net/wiki/spaces/TEAM/pages/12345678
        """
        # Ensure base_url doesn't end with /
        base_url = base_url.rstrip('/')
        # Ensure /wiki is present for Confluence Cloud URLs
        if not base_url.endswith('/wiki'):
            base_url = f"{base_url}/wiki"
        return f"{base_url}/spaces/{space_key}/pages/{page_id}"

    @classmethod
    def parse_confluence_url(cls, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract space_key and page_id from a Confluence URL.

        Args:
            url: Confluence page URL

        Returns:
            Tuple of (space_key, page_id), or (None, None) if URL doesn't match pattern
        """
        match = cls.CONFLUENCE_URL_PATTERN.match(url)
        if match:
            return match.group(1), match.group(2)
        return None, None

    @classmethod
    def parse(cls, file_path: str, content: str) -> LocalPage:
        """Parse YAML frontmatter from markdown content.

        Files without frontmatter are treated as new files (not yet synced).

        Args:
            file_path: Path to the file (for error messages)
            content: Full markdown content including frontmatter

        Returns:
            LocalPage object with page_id, space_key, confluence_base_url, and content

        Raises:
            FrontmatterError: If frontmatter is malformed or has invalid YAML
        """
        # Extract frontmatter
        match = cls.FRONTMATTER_PATTERN.match(content)
        if not match:
            # No frontmatter - treat as new file
            return LocalPage(
                file_path=file_path,
                page_id=None,
                content=content
            )

        frontmatter_str = match.group(1)
        markdown_content = content[match.end():]

        # Parse YAML
        try:
            frontmatter = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError as e:
            raise FrontmatterError(
                file_path,
                f"Invalid YAML syntax: {str(e)}"
            )

        if not isinstance(frontmatter, dict):
            raise FrontmatterError(
                file_path,
                f"Frontmatter must be a YAML dictionary, got {type(frontmatter).__name__}"
            )

        # Validate YAML depth to prevent DoS attacks
        try:
            cls._validate_yaml_depth(frontmatter)
        except FrontmatterError as e:
            # Re-raise with correct file path
            raise FrontmatterError(file_path, str(e).split(": ", 1)[-1])

        # Extract page_id and space_key from confluence_url
        page_id = None
        space_key = None
        confluence_base_url = None

        if 'confluence_url' in frontmatter and frontmatter['confluence_url']:
            url = str(frontmatter['confluence_url'])
            space_key, page_id = cls.parse_confluence_url(url)
            # Extract base URL from the full URL
            if page_id:
                # URL format: https://domain.atlassian.net/wiki/spaces/KEY/pages/ID
                # Base URL is everything before /spaces/
                parts = url.split('/spaces/')
                if len(parts) == 2:
                    confluence_base_url = parts[0]

        return LocalPage(
            file_path=file_path,
            page_id=page_id,
            content=markdown_content,
            space_key=space_key,
            confluence_base_url=confluence_base_url
        )

    @classmethod
    def generate(cls, local_page: LocalPage) -> str:
        """Generate markdown content with YAML frontmatter.

        Requires space_key and confluence_base_url when page_id is set.

        If the content already has frontmatter, preserves existing fields and
        adds/updates confluence_url as the first field.

        Args:
            local_page: LocalPage object with page_id, content, space_key,
                       and confluence_base_url

        Returns:
            Full markdown content with frontmatter.
            If page_id is None, returns content without frontmatter.

        Raises:
            ValueError: If page_id is set but space_key or confluence_base_url is missing
        """
        # New files without page_id don't need frontmatter
        if local_page.page_id is None:
            return local_page.content

        # Check if content already has frontmatter that we need to preserve
        existing_frontmatter = {}
        content_without_frontmatter = local_page.content

        match = cls.FRONTMATTER_PATTERN.match(local_page.content)
        if match:
            frontmatter_str = match.group(1)
            content_without_frontmatter = local_page.content[match.end():]
            try:
                existing_frontmatter = yaml.safe_load(frontmatter_str) or {}
                if not isinstance(existing_frontmatter, dict):
                    existing_frontmatter = {}
                # Validate YAML depth to prevent DoS attacks
                cls._validate_yaml_depth(existing_frontmatter)
            except (yaml.YAMLError, FrontmatterError):
                existing_frontmatter = {}

        # Remove confluence_url field if present (we'll regenerate it)
        existing_frontmatter.pop('confluence_url', None)

        # Build new frontmatter with confluence_url first
        new_frontmatter = {}

        if local_page.page_id:
            # Require space_key and confluence_base_url
            if not local_page.space_key or not local_page.confluence_base_url:
                raise ValueError(
                    f"Cannot generate frontmatter for page {local_page.page_id}: "
                    f"space_key and confluence_base_url are required"
                )
            confluence_url = cls.build_confluence_url(
                local_page.confluence_base_url,
                local_page.space_key,
                local_page.page_id
            )
            new_frontmatter['confluence_url'] = confluence_url

        # Merge with existing frontmatter (new fields first, then existing)
        final_frontmatter = {**new_frontmatter, **existing_frontmatter}

        # If no frontmatter fields at all, no frontmatter needed
        if not final_frontmatter and local_page.page_id is None:
            return content_without_frontmatter

        # Generate YAML
        yaml_str = yaml.safe_dump(
            final_frontmatter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False
        )

        # Combine frontmatter and content
        return f"---\n{yaml_str}---\n{content_without_frontmatter}"

    @classmethod
    def extract_frontmatter_and_content(cls, content: str) -> Tuple[dict, str]:
        """Extract frontmatter dict and content separately.

        This is a lower-level method that returns the raw frontmatter dict
        and content without creating a LocalPage object. Useful for testing
        or advanced use cases.

        Args:
            content: Full markdown content including frontmatter

        Returns:
            Tuple of (frontmatter_dict, markdown_content).
            Returns ({}, content) if no frontmatter found.
        """
        # Extract frontmatter
        match = cls.FRONTMATTER_PATTERN.match(content)
        if not match:
            return {}, content

        frontmatter_str = match.group(1)
        markdown_content = content[match.end():]

        # Parse YAML
        try:
            frontmatter = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError as e:
            raise FrontmatterError(
                "<unknown>",
                f"Invalid YAML syntax: {str(e)}"
            )

        if not isinstance(frontmatter, dict):
            raise FrontmatterError(
                "<unknown>",
                f"Frontmatter must be a YAML dictionary, got {type(frontmatter).__name__}"
            )

        # Validate YAML depth to prevent DoS attacks
        cls._validate_yaml_depth(frontmatter)

        return frontmatter, markdown_content

    @classmethod
    def get_page_id(cls, content: str) -> Optional[str]:
        """Extract page_id from content frontmatter.

        Args:
            content: Full markdown content including frontmatter

        Returns:
            Page ID string, or None if not found
        """
        try:
            frontmatter, _ = cls.extract_frontmatter_and_content(content)
        except FrontmatterError:
            return None

        # Extract from confluence_url
        if 'confluence_url' in frontmatter and frontmatter['confluence_url']:
            _, page_id = cls.parse_confluence_url(str(frontmatter['confluence_url']))
            if page_id:
                return page_id

        return None
