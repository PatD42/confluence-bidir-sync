"""Content parser for extracting blocks from XHTML and markdown.

This module provides parsing functionality to extract content blocks
from both XHTML (Confluence storage format) and markdown. These blocks
are used for diff analysis and mapping changes between formats.
"""

import re
from typing import List

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from .models import BlockType, ContentBlock


def strip_markdown_formatting(text: str) -> str:
    """Strip common markdown formatting to get plain text.

    Removes bold, italic, code, and link formatting while preserving the text.

    Args:
        text: Text with potential markdown formatting

    Returns:
        Plain text without markdown formatting
    """
    # Remove bold/italic markers: **text** or __text__ -> text
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    # Remove italic: *text* or _text_ -> text
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    # Remove inline code: `text` -> text
    text = re.sub(r"`(.+?)`", r"\1", text)
    # Remove links: [text](url) -> text
    text = re.sub(r"\[(.+?)\]\([^)]+\)", r"\1", text)
    return text


class ContentParser:
    """Parses XHTML and markdown into content blocks.

    Content blocks represent discrete document elements (paragraphs,
    headings, tables, etc.) that can be matched between XHTML and
    markdown for surgical update operations.
    """

    def __init__(self):
        """Initialize ContentParser with lxml parser."""
        self.parser = "lxml"

    def parse_xhtml(self, xhtml: str) -> BeautifulSoup:
        """Parse XHTML string into BeautifulSoup object.

        Args:
            xhtml: Confluence storage format XHTML string

        Returns:
            BeautifulSoup object for DOM manipulation
        """
        return BeautifulSoup(xhtml, self.parser)

    def extract_xhtml_blocks(self, xhtml: str) -> List[ContentBlock]:
        """Extract content blocks from XHTML.

        Parses the XHTML and creates ContentBlock objects for each
        discrete content element. Maintains element references for
        surgical operations.

        Searches the entire document tree, not just direct children,
        to handle nested structures (e.g., lists inside divs).

        Args:
            xhtml: Confluence storage format XHTML string

        Returns:
            List of ContentBlock objects with element references
        """
        soup = self.parse_xhtml(xhtml)
        blocks = []
        index = 0

        # Get body content (lxml wraps in html/body)
        body = soup.find("body") or soup

        # Track processed elements to avoid duplicates (e.g., <p> inside <li>)
        processed_elements = set()

        # Process macros first (ac: namespace elements)
        # Only extract top-level macros (skip nested ac: elements)
        # Also skip inline-comment-markers which are transparent annotations
        for element in body.find_all(
            lambda tag: tag.name and tag.name.startswith("ac:")
        ):
            if id(element) in processed_elements:
                continue
            # Skip inline comment markers - they're transparent annotations
            if element.name == "ac:inline-comment-marker":
                continue
            # Skip if parent is also an ac: element (nested macro component)
            if element.parent and element.parent.name and element.parent.name.startswith("ac:"):
                continue
            processed_elements.add(id(element))
            # Mark all nested ac: elements as processed
            for nested in element.find_all(
                lambda tag: tag.name and tag.name.startswith("ac:")
            ):
                processed_elements.add(id(nested))
            blocks.append(
                ContentBlock(
                    block_type=BlockType.MACRO,
                    content=str(element),
                    element=element,
                    index=index,
                )
            )
            index += 1

        # Process headings (h1-h6)
        for element in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            if id(element) in processed_elements:
                continue
            processed_elements.add(id(element))
            level = int(element.name[1])
            blocks.append(
                ContentBlock(
                    block_type=BlockType.HEADING,
                    content=element.get_text(strip=True),
                    level=level,
                    element=element,
                    index=index,
                )
            )
            index += 1

        # Process tables
        for element in body.find_all("table"):
            if id(element) in processed_elements:
                continue
            processed_elements.add(id(element))
            rows = []
            for tr in element.find_all("tr"):
                cells = []
                for cell in tr.find_all(["td", "th"]):
                    cells.append(cell.get_text(strip=True))
                if cells:
                    rows.append(cells)
            text_content = element.get_text(separator=" ", strip=True)
            blocks.append(
                ContentBlock(
                    block_type=BlockType.TABLE,
                    content=text_content,
                    rows=rows,
                    element=element,
                    index=index,
                )
            )
            index += 1

        # Process lists - extract individual items
        # Skip lists that are inside table cells (td/th) as they're part of table content
        for list_element in body.find_all(["ul", "ol"]):
            if id(list_element) in processed_elements:
                continue
            # Skip lists inside table cells
            if list_element.find_parent(["td", "th"]):
                processed_elements.add(id(list_element))
                continue
            processed_elements.add(id(list_element))
            # Mark nested paragraphs as processed to avoid duplicates
            for p in list_element.find_all("p"):
                processed_elements.add(id(p))
            for li in list_element.find_all("li", recursive=False):
                processed_elements.add(id(li))
                # Use separator=" " to preserve spacing around inline elements (e.g., inline-comment-markers)
                item_text = li.get_text(separator=" ", strip=True)
                # Normalize whitespace (collapse multiple spaces)
                item_text = " ".join(item_text.split())
                # Remove spaces before punctuation (artifact of separator between tags)
                item_text = re.sub(r"\s+([,:;.!?])", r"\1", item_text)
                if item_text:
                    blocks.append(
                        ContentBlock(
                            block_type=BlockType.LIST,
                            content=item_text,
                            element=li,
                            index=index,
                        )
                    )
                    index += 1

        # Process code blocks
        for element in body.find_all(["pre", "code"]):
            if id(element) in processed_elements:
                continue
            processed_elements.add(id(element))
            text = element.get_text()
            # Skip empty code blocks
            if not text or not text.strip():
                continue
            blocks.append(
                ContentBlock(
                    block_type=BlockType.CODE,
                    content=text,
                    element=element,
                    index=index,
                )
            )
            index += 1

        # Process paragraphs (skip those inside lists and tables)
        for element in body.find_all("p"):
            if id(element) in processed_elements:
                continue
            # Skip paragraphs inside table cells
            if element.find_parent(["td", "th"]):
                processed_elements.add(id(element))
                continue
            processed_elements.add(id(element))
            text = element.get_text(strip=True)
            if text:
                blocks.append(
                    ContentBlock(
                        block_type=BlockType.PARAGRAPH,
                        content=text,
                        element=element,
                        index=index,
                    )
                )
                index += 1

        return blocks

    def extract_markdown_blocks(self, markdown: str) -> List[ContentBlock]:
        """Extract content blocks from markdown.

        Parses markdown text and creates ContentBlock objects for each
        discrete content element. Used for comparing against XHTML blocks.

        Args:
            markdown: Markdown text string

        Returns:
            List of ContentBlock objects (without element references)
        """
        blocks = []
        lines = markdown.split("\n")
        index = 0
        i = 0

        # Skip YAML frontmatter (--- ... ---)
        if i < len(lines) and lines[i].strip() == "---":
            i += 1
            while i < len(lines) and lines[i].strip() != "---":
                i += 1
            if i < len(lines):
                i += 1  # Skip closing ---

        while i < len(lines):
            line = lines[i]

            # Skip empty lines
            if not line.strip():
                i += 1
                continue

            # Macro placeholder
            if line.strip().startswith("CONFLUENCE_MACRO_PLACEHOLDER"):
                blocks.append(
                    ContentBlock(
                        block_type=BlockType.MACRO, content=line.strip(), index=index
                    )
                )
                index += 1
                i += 1
                continue

            # Headings (# style)
            heading_match = re.match(r"^(#{1,6})\s+(.+?)(?:\s*\{.*\})?\s*$", line)
            if heading_match:
                level = len(heading_match.group(1))
                content = strip_markdown_formatting(heading_match.group(2).strip())
                blocks.append(
                    ContentBlock(
                        block_type=BlockType.HEADING,
                        content=content,
                        level=level,
                        index=index,
                    )
                )
                index += 1
                i += 1
                continue

            # Tables: detect pipe tables, simple tables (pandoc), and grid tables
            # Simple table separator: lines of dashes separated by spaces (e.g., "---  ---  ---")
            simple_table_sep = r"^\s*-+(\s+-+)+\s*$"
            is_simple_table_sep = re.match(simple_table_sep, line)
            # Also check if NEXT line is a simple table separator (pandoc format: header row first)
            next_line_is_sep = (
                i + 1 < len(lines) and re.match(simple_table_sep, lines[i + 1])
            )
            is_pipe_table = "|" in line
            # Grid table: starts with +---+---+ pattern
            is_grid_table = re.match(r"^\s*\+[-+]+\+\s*$", line)

            if is_simple_table_sep or next_line_is_sep or is_pipe_table or is_grid_table:
                table_lines = []

                if is_grid_table:
                    # Grid table format: +---+---+ borders
                    # Collect ALL lines until empty line (grid separators are row boundaries, not table end)
                    grid_sep = r"^\s*\+[-+]+\+\s*$"
                    while i < len(lines):
                        current = lines[i]
                        # End at empty line
                        if not current.strip():
                            break
                        table_lines.append(current)
                        i += 1
                elif is_simple_table_sep or next_line_is_sep:
                    # Simple table format (pandoc) - may start with header or separator
                    while i < len(lines):
                        current = lines[i]
                        is_sep = re.match(simple_table_sep, current)

                        if current.strip():
                            table_lines.append(current)

                        i += 1

                        # End after second separator (or at empty line)
                        if is_sep and len([l for l in table_lines if re.match(simple_table_sep, l)]) >= 2:
                            break
                        if i < len(lines) and not lines[i].strip():
                            break
                else:
                    # Pipe table format
                    while i < len(lines) and (
                        lines[i].strip().startswith("|")
                        or "|" in lines[i]
                        or re.match(r"^[\s\-:|]+$", lines[i])
                    ):
                        if lines[i].strip():
                            table_lines.append(lines[i])
                        i += 1
                        if i < len(lines) and not lines[i].strip():
                            break

                rows = self._parse_markdown_table(table_lines)
                if rows:
                    # Use space-joined text for content (matches XHTML extraction)
                    # Strip markdown formatting so **bold** matches plain text
                    text_content = " ".join(
                        " ".join(strip_markdown_formatting(cell) for cell in row)
                        for row in rows
                    )
                    blocks.append(
                        ContentBlock(
                            block_type=BlockType.TABLE,
                            content=text_content,
                            rows=rows,
                            index=index,
                        )
                    )
                    index += 1
                continue

            # Lists - extract individual items as separate blocks
            if re.match(r"^[\-\*\+]\s+", line) or re.match(r"^\d+\.\s+", line):
                while i < len(lines) and (
                    re.match(r"^[\-\*\+]\s+", lines[i])
                    or re.match(r"^\d+\.\s+", lines[i])
                ):
                    item_match = re.match(r"^[\-\*\+\d.]+\s+(.+)$", lines[i])
                    if item_match:
                        item_text = item_match.group(1).strip()
                        # Handle multi-line list items (indented continuation)
                        i += 1
                        while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                            item_text += " " + lines[i].strip()
                            i += 1
                        blocks.append(
                            ContentBlock(
                                block_type=BlockType.LIST,
                                content=strip_markdown_formatting(item_text),
                                index=index,
                            )
                        )
                        index += 1
                    else:
                        i += 1
                continue

            # Code blocks
            if line.startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # Skip closing ```
                blocks.append(
                    ContentBlock(
                        block_type=BlockType.CODE,
                        content="\n".join(code_lines),
                        index=index,
                    )
                )
                index += 1
                continue

            # Regular paragraph
            para_lines = []
            while (
                i < len(lines)
                and lines[i].strip()
                and not lines[i].startswith("#")
                and not lines[i].startswith("CONFLUENCE")
            ):
                para_lines.append(lines[i])
                i += 1
            if para_lines:
                content = " ".join(para_lines).strip()
                blocks.append(
                    ContentBlock(
                        block_type=BlockType.PARAGRAPH,
                        content=strip_markdown_formatting(content),
                        index=index,
                    )
                )
                index += 1
                continue

            i += 1

        return blocks

    def _parse_markdown_table(self, lines: List[str]) -> List[List[str]]:
        """Parse markdown table lines into rows of cells.

        Supports pipe-delimited tables, pandoc simple tables, and grid tables.

        Args:
            lines: Table lines from markdown

        Returns:
            List of rows, each row is a list of cell strings
        """
        if not lines:
            return []

        # Check if grid table format: +---+---+ borders
        grid_sep_pattern = r"^\s*\+[-+]+\+\s*$"
        is_grid_table = any(re.match(grid_sep_pattern, line) for line in lines[:3])
        if is_grid_table:
            return self._parse_grid_table(lines)

        # Check if simple table format (pandoc) - separator may be first or second line
        simple_sep_pattern = r"^\s*-+(\s+-+)+\s*$"
        is_simple_table = any(re.match(simple_sep_pattern, line) for line in lines[:3])
        if is_simple_table:
            return self._parse_simple_table(lines)

        # Pipe table format
        rows = []
        for line in lines:
            # Skip separator lines (must contain at least one dash)
            # This allows empty rows like | | | | to be parsed as data rows
            if re.match(r"^[\s|:]*-+[\s\-:|]*$", line):
                continue
            # Parse cells
            cells = [cell.strip() for cell in line.split("|")]
            # Remove only first and last empty cells from | borders
            # (keep interior empty cells for rows like | | | |)
            if cells and cells[0] == '':
                cells = cells[1:]
            if cells and cells[-1] == '':
                cells = cells[:-1]
            # Strip markdown formatting (* for bold) and list markers (- for bullets)
            cleaned_cells = []
            for c in cells:
                # Strip bold markers
                c = c.strip("*").strip()
                # Strip list item markers ONLY at the start of cell content
                # (- item, * item, + item, 1. item)
                # IMPORTANT: Don't strip hyphens in the middle of text like "600x - better"
                c = re.sub(r"^[\-\*\+]\s+", "", c)
                c = re.sub(r"^\d+\.\s+", "", c)
                c = c.strip()
                cleaned_cells.append(c)
            # Allow rows even when all cells are empty (e.g., | | | |)
            if cleaned_cells:
                rows.append(cleaned_cells)
        return rows

    def _parse_grid_table(self, lines: List[str]) -> List[List[str]]:
        """Parse pandoc grid table format.

        Grid tables use +---+---+ for borders and | for cell separators.
        Multi-line cells are supported by continuing on the next line.

        Args:
            lines: Table lines including grid borders

        Returns:
            List of rows, each row is a list of cell strings
        """
        if not lines:
            return []

        grid_sep_pattern = r"^\s*\+[-+]+\+\s*$"
        rows = []
        current_row_cells = []
        in_row = False

        for line in lines:
            # Skip grid separator lines, but use them to mark row boundaries
            if re.match(grid_sep_pattern, line):
                if current_row_cells:
                    # Clean up multi-line cells
                    cleaned = [" ".join(c.split()).strip() for c in current_row_cells]
                    if any(c for c in cleaned):
                        rows.append(cleaned)
                    current_row_cells = []
                in_row = False
                continue

            # Data row: | cell | cell |
            if "|" in line:
                cells = [cell.strip() for cell in line.split("|")]
                # Remove empty first/last cells from | borders
                if cells and not cells[0]:
                    cells = cells[1:]
                if cells and not cells[-1]:
                    cells = cells[:-1]

                if not current_row_cells:
                    current_row_cells = cells
                else:
                    # Multi-line row: append to existing cells
                    for i, cell in enumerate(cells):
                        if i < len(current_row_cells):
                            current_row_cells[i] += " " + cell
                        else:
                            current_row_cells.append(cell)
                in_row = True

        # Don't forget the last row
        if current_row_cells:
            cleaned = [" ".join(c.split()).strip() for c in current_row_cells]
            if any(c for c in cleaned):
                rows.append(cleaned)

        # Strip ALL list markers from all cells (- item, * item, etc.)
        # These can appear at start of cell or after space (for multi-item cells)
        for row in rows:
            for i, cell in enumerate(row):
                cell = re.sub(r"(^|\s)[\-\*\+]\s+", r"\1", cell)
                cell = re.sub(r"(^|\s)\d+\.\s+", r"\1", cell)
                row[i] = cell.strip()

        return rows

    def _parse_simple_table(self, lines: List[str]) -> List[List[str]]:
        """Parse pandoc simple table format.

        Simple tables use whitespace-aligned columns with separator lines.
        The separator line may be first or second (after header row).

        Args:
            lines: Table lines including separator lines

        Returns:
            List of rows, each row is a list of cell strings
        """
        if not lines:
            return []

        # Find the separator line (may be first or second line)
        separator_pattern = r"^\s*-+(\s+-+)+\s*$"
        separator = None
        for line in lines:
            if re.match(separator_pattern, line):
                separator = line
                break

        if not separator:
            return []

        # Find column boundaries from separator line
        col_ranges = []
        in_col = False
        start = 0

        for i, char in enumerate(separator):
            if char == "-" and not in_col:
                start = i
                in_col = True
            elif char != "-" and in_col:
                col_ranges.append((start, i))
                in_col = False
        if in_col:
            col_ranges.append((start, len(separator)))

        # Parse all non-separator rows using column boundaries
        rows = []
        for line in lines:
            # Skip separator lines
            if re.match(r"^\s*-+(\s+-+)*\s*$", line):
                continue

            cells = []
            for col_start, col_end in col_ranges:
                # Extend end to capture overflow
                end = min(col_end + 2, len(line)) if col_end < len(line) else len(line)
                if col_start < len(line):
                    cell = line[col_start:end].strip()
                    cell = cell.strip("*").strip()
                    cells.append(cell)
                else:
                    cells.append("")

            if cells and any(c for c in cells):
                rows.append(cells)

        # Strip ALL list markers from all cells (- item, * item, etc.)
        # These can appear at start of cell or after space (for multi-item cells)
        for row in rows:
            for i, cell in enumerate(row):
                cell = re.sub(r"(^|\s)[\-\*\+]\s+", r"\1", cell)
                cell = re.sub(r"(^|\s)\d+\.\s+", r"\1", cell)
                row[i] = cell.strip()

        return rows
