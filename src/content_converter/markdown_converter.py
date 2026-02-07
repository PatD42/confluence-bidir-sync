"""Markdown converter using markdownify and Pandoc.

This module provides bidirectional conversion between Confluence storage format
(XHTML) and markdown. Uses markdownify for HTML→markdown (clean pipe tables)
and Pandoc for markdown→HTML conversion.
"""

import subprocess

from markdownify import MarkdownConverter as BaseMarkdownConverter

from ..confluence_client.errors import ConversionError


class _CustomMarkdownConverter(BaseMarkdownConverter):
    """Custom markdownify converter with Confluence-friendly settings."""

    def __init__(self, **options):
        # Set defaults for clean pipe table output
        options.setdefault('heading_style', 'atx')  # Use # style headings
        options.setdefault('bullets', '-')  # Use - for bullets
        options.setdefault('strong_em_symbol', '*')  # Use * for bold/italic
        super().__init__(**options)

    def _is_in_table_cell(self, parent_tags):
        """Check if we're inside a table cell based on parent tags."""
        # parent_tags contains tag names like 'td', 'th', 'table', etc.
        return 'td' in parent_tags or 'th' in parent_tags

    def convert_p(self, el, text, parent_tags):
        """Convert paragraph, using <br> for line breaks in table cells.

        Confluence stores multi-line table cell content as multiple <p> tags.
        We convert these to <br> separated content to preserve line breaks.
        """
        text = text.strip()
        if not text:
            return ''

        # In table cells, use <br> for paragraph breaks instead of collapsing
        if self._is_in_table_cell(parent_tags):
            # Return text with a special marker that we'll convert to <br>
            # The marker ensures we can distinguish paragraph breaks from regular spaces
            return text + '\n'

        # Default behavior for non-table content
        if '_inline' in parent_tags:
            return ' ' + text + ' '
        return '\n\n%s\n\n' % text

    def convert_td(self, el, text, parent_tags):
        """Convert table cell, preserving line breaks as <br> tags."""
        colspan = 1
        if 'colspan' in el.attrs and el['colspan'].isdigit():
            colspan = max(1, min(1000, int(el['colspan'])))
        # Clean up the text:
        # - Strip leading/trailing whitespace
        # - Convert newlines (from convert_p) to <br> tags
        # - Collapse multiple <br> tags
        cell_text = text.strip()
        # Convert newlines to <br> (these come from our convert_p for paragraphs)
        cell_text = cell_text.replace('\n', '<br>')
        # Clean up multiple consecutive <br> tags
        while '<br><br>' in cell_text:
            cell_text = cell_text.replace('<br><br>', '<br>')
        # Remove trailing <br> tags (use removesuffix, not rstrip which removes characters)
        while cell_text.endswith('<br>'):
            cell_text = cell_text.removesuffix('<br>')
        return ' ' + cell_text + ' |' * colspan

    def convert_th(self, el, text, parent_tags):
        """Convert table header cell, preserving line breaks as <br> tags."""
        colspan = 1
        if 'colspan' in el.attrs and el['colspan'].isdigit():
            colspan = max(1, min(1000, int(el['colspan'])))
        # Same logic as convert_td
        cell_text = text.strip()
        cell_text = cell_text.replace('\n', '<br>')
        while '<br><br>' in cell_text:
            cell_text = cell_text.replace('<br><br>', '<br>')
        # Remove trailing <br> tags (use removesuffix, not rstrip which removes characters)
        while cell_text.endswith('<br>'):
            cell_text = cell_text.removesuffix('<br>')
        return ' ' + cell_text + ' |' * colspan

    def convert_br(self, el, text, parent_tags):
        """Convert <br> tags, preserving them in table cells."""
        # In table cells, preserve <br> as literal HTML
        # (markdown tables support inline HTML)
        if self._is_in_table_cell(parent_tags):
            return '<br>'
        # Outside tables, use standard newline handling
        if '_inline' in parent_tags:
            return ' '
        if self.options['newline_style'].lower() == 'backslash':
            return '\\\n'
        else:
            return '  \n'


def _markdownify(html: str, **options) -> str:
    """Convert HTML to markdown using custom converter."""
    return _CustomMarkdownConverter(**options).convert(html)


class MarkdownConverter:
    """Converts between XHTML and markdown.

    Uses markdownify for HTML→markdown conversion (produces clean pipe tables)
    and Pandoc for markdown→HTML conversion.
    """

    def __init__(self):
        """Initialize MarkdownConverter and verify Pandoc is available.

        Raises:
            ConversionError: If Pandoc is not found on system PATH
        """
        if not self._pandoc_installed():
            raise ConversionError(
                "Pandoc not found. Install: brew install pandoc (macOS) or "
                "apt-get install pandoc (Linux) or download from "
                "https://pandoc.org/installing.html"
            )

    def xhtml_to_markdown(self, xhtml: str) -> str:
        """Convert XHTML to markdown using markdownify.

        Produces clean pipe tables (| col1 | col2 |) that are easy for
        agentic tools to parse.

        Args:
            xhtml: Confluence storage format XHTML string

        Returns:
            Markdown string with pipe-formatted tables
        """
        if not xhtml:
            return ""

        try:
            return _markdownify(xhtml)
        except Exception as e:
            raise ConversionError(f"Markdownify conversion failed: {e}") from e

    def markdown_to_xhtml(self, markdown: str) -> str:
        """Convert markdown to XHTML using Pandoc.

        Args:
            markdown: Markdown string

        Returns:
            XHTML string suitable for Confluence storage format

        Raises:
            ConversionError: If conversion fails or times out
        """
        if not markdown:
            return ""

        # Pre-process: Fix multiline table cells (convert embedded \n to <br>)
        markdown = self._fix_multiline_table_cells(markdown)

        try:
            result = subprocess.run(
                ["pandoc", "-f", "markdown", "-t", "html"],
                input=markdown,
                text=True,
                capture_output=True,
                check=True,
                timeout=10
            )
            xhtml = result.stdout

            # Post-process: Convert <br> in table cells to <p> tags
            # Confluence stores multi-line cell content as <p> tags, not <br>
            xhtml = self._convert_br_to_p_in_cells(xhtml)

            return xhtml
        except subprocess.CalledProcessError as e:
            raise ConversionError(f"Pandoc conversion failed: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise ConversionError("Pandoc conversion timed out (>10s)")

    def _convert_br_to_p_in_cells(self, xhtml: str) -> str:
        """Convert <br> tags inside table cells to <p> tags.

        Confluence stores multi-line table cell content as multiple <p> tags,
        not <br> tags. This method converts <br> back to <p> for proper
        Confluence rendering.

        Args:
            xhtml: HTML string from Pandoc

        Returns:
            HTML with <br> in cells converted to <p> tags
        """
        import re

        def convert_cell_content(match):
            """Convert <br> to </p><p> within a single cell."""
            tag = match.group(1)  # 'td' or 'th'
            content = match.group(2)

            # If no <br> tags, return as-is
            if '<br>' not in content and '<br/>' not in content and '<br />' not in content:
                return f'<{tag}>{content}</{tag}>'

            # Split content by <br> variants and wrap each part in <p>
            # First normalize all <br> variants
            content = re.sub(r'<br\s*/?>', '<br>', content)

            # Split by <br> and create <p> wrapped parts
            parts = content.split('<br>')
            parts = [p.strip() for p in parts if p.strip()]

            if len(parts) <= 1:
                # Single part or empty - no need for <p> tags
                return f'<{tag}>{content.replace("<br>", "")}</{tag}>'

            # Wrap each part in <p> tags
            p_content = ''.join(f'<p>{part}</p>' for part in parts)
            return f'<{tag}>{p_content}</{tag}>'

        # Match <td>...</td> and <th>...</th> (non-greedy)
        xhtml = re.sub(r'<(td|th)>(.*?)</\1>', convert_cell_content, xhtml, flags=re.DOTALL)

        return xhtml

    def _fix_multiline_table_cells(self, markdown: str) -> str:
        """Fix markdown tables with embedded newlines in cells.

        Standard markdown pipe tables don't support actual newlines within cells.
        This method detects broken table rows and converts embedded newlines to
        <br> tags so Pandoc processes them correctly.

        Algorithm:
        1. Count unescaped pipe characters in the header separator row
        2. For each data row, if it doesn't have enough pipes, there's a broken \\n
        3. Concatenate with next line(s) using <br> until we have the right pipe count
        4. If we get more pipes than expected, it's a formatting error

        Example input (broken):
            | Header | Notes |
            |---|---|
            | Cell | Line1
            Line2 |

        Example output (fixed):
            | Header | Notes |
            |---|---|
            | Cell | Line1<br>Line2 |

        Args:
            markdown: Markdown string potentially with broken table cells

        Returns:
            Markdown with multiline cells fixed using <br> tags
        """
        import re

        def count_unescaped_pipes(line: str) -> int:
            """Count pipe characters that are not escaped with backslash."""
            count = 0
            i = 0
            while i < len(line):
                if line[i] == '\\' and i + 1 < len(line):
                    # Skip escaped character
                    i += 2
                elif line[i] == '|':
                    count += 1
                    i += 1
                else:
                    i += 1
            return count

        def is_separator_row(line: str) -> bool:
            """Check if line is a table separator row (|---|---|)."""
            stripped = line.strip()
            if not stripped.startswith('|') or not stripped.endswith('|'):
                return False
            # Remove all pipes and check if remaining is only dashes, colons, spaces
            content = stripped.replace('|', '')
            return bool(re.match(r'^[\s\-:]+$', content)) and '-' in content

        lines = markdown.split('\n')
        result = []
        expected_pipes = None
        in_table = False
        accumulator = []

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Check if this is a separator row (marks start of table body)
            if is_separator_row(stripped):
                # Emit any accumulated content first
                if accumulator:
                    result.append('<br>'.join(accumulator))
                    accumulator = []

                expected_pipes = count_unescaped_pipes(stripped)
                in_table = True
                result.append(line)
                i += 1
                continue

            # If we're in a table, check pipe counts
            if in_table and stripped:
                current_pipes = count_unescaped_pipes(stripped)

                if accumulator:
                    # We're accumulating a broken row
                    accumulated = '<br>'.join(accumulator) + '<br>' + stripped
                    total_pipes = count_unescaped_pipes(accumulated)

                    if total_pipes == expected_pipes:
                        # Perfect - emit the fixed row
                        result.append(accumulated)
                        accumulator = []
                        i += 1
                    elif total_pipes < expected_pipes:
                        # Still not enough pipes, keep accumulating
                        accumulator.append(stripped)
                        i += 1
                    else:
                        # Too many pipes - formatting error, emit what we have and reset
                        result.append('<br>'.join(accumulator))
                        accumulator = []
                        # Don't increment i, reprocess this line
                        in_table = False  # Exit table mode due to error
                elif current_pipes == expected_pipes:
                    # Valid row
                    result.append(line)
                    i += 1
                elif current_pipes < expected_pipes:
                    # Not enough pipes - start accumulating
                    accumulator = [stripped]
                    i += 1
                else:
                    # Too many pipes or end of table
                    in_table = False
                    result.append(line)
                    i += 1
            else:
                # Not in table or empty line
                if accumulator:
                    # End of table while accumulating - emit what we have
                    result.append('<br>'.join(accumulator))
                    accumulator = []
                if not stripped:
                    in_table = False  # Empty line ends table
                    expected_pipes = None
                result.append(line)
                i += 1

        # Handle any remaining accumulated content
        if accumulator:
            result.append('<br>'.join(accumulator))

        return '\n'.join(result)

    def _pandoc_installed(self) -> bool:
        """Check if Pandoc is installed on system PATH.

        Returns:
            True if Pandoc is available, False otherwise
        """
        try:
            result = subprocess.run(
                ["which", "pandoc"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
