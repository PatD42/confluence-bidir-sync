"""Table-aware 3-way merge using merge3 library.

This module provides cell-level merging for markdown tables, solving the
limitation of line-based merge where changes to different cells in the
same row would create false conflicts.

Example:
    Base:   | 12 | Glossary   | Terms, abbreviations, component names |
    Local:  | 12 | Glossary   | Terms, abbreviations, component names and gizmos |
    Remote: | 12 | Glossaries | Terms, abbreviations, component names |

    Line-based merge: CONFLICT (same line modified)
    Cell-based merge: | 12 | Glossaries | Terms, abbreviations, component names and gizmos |
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from merge3 import Merge3

logger = logging.getLogger(__name__)


@dataclass
class TableRegion:
    """Represents a markdown table region in content."""
    start_line: int
    end_line: int
    header_row: List[str]
    separator_row: str
    data_rows: List[List[str]]


def parse_table_row(line: str) -> Optional[List[str]]:
    """Parse a markdown table row into cells.

    Args:
        line: A markdown table row like "| cell1 | cell2 | cell3 |"

    Returns:
        List of cell contents, or None if not a valid table row
    """
    line = line.strip()
    if not line.startswith('|') or not line.endswith('|'):
        return None

    # Split by | and filter out empty strings from start/end
    parts = line.split('|')
    cells = [cell.strip() for cell in parts[1:-1]]  # Skip first and last empty parts

    return cells if cells else None


def is_separator_row(line: str) -> bool:
    """Check if a line is a markdown table separator row.

    Args:
        line: A line to check, e.g., "| --- | --- | --- |"

    Returns:
        True if this is a separator row
    """
    line = line.strip()
    if not line.startswith('|') or not line.endswith('|'):
        return False

    # Check if all cells contain only dashes, colons, and spaces
    cells = parse_table_row(line)
    if not cells:
        return False

    for cell in cells:
        # Valid separator cells: ---, :---, ---:, :---:
        cleaned = cell.replace('-', '').replace(':', '').strip()
        if cleaned or not cell.replace(':', '').replace(' ', '').startswith('-'):
            return False

    return True


def find_tables(content: str) -> List[TableRegion]:
    """Find all markdown tables in content.

    Args:
        content: Markdown content

    Returns:
        List of TableRegion objects
    """
    lines = content.split('\n')
    tables = []
    i = 0

    while i < len(lines):
        # Look for potential table start (header row)
        header_cells = parse_table_row(lines[i])

        if header_cells and i + 1 < len(lines) and is_separator_row(lines[i + 1]):
            # Found a table
            start_line = i
            separator_row = lines[i + 1].strip()
            data_rows = []

            # Collect data rows
            j = i + 2
            while j < len(lines):
                row_cells = parse_table_row(lines[j])
                if row_cells and len(row_cells) == len(header_cells):
                    data_rows.append(row_cells)
                    j += 1
                else:
                    break

            tables.append(TableRegion(
                start_line=start_line,
                end_line=j - 1,
                header_row=header_cells,
                separator_row=separator_row,
                data_rows=data_rows
            ))

            i = j
        else:
            i += 1

    return tables


# Escape sequence for embedded newlines in cell content
_NEWLINE_ESCAPE = "__CELL_NEWLINE__"


def _escape_cell_newlines(content: str) -> str:
    """Escape newlines in cell content to preserve them through merge."""
    return content.replace("\n", _NEWLINE_ESCAPE)


def _unescape_cell_newlines(content: str) -> str:
    """Restore escaped newlines in cell content."""
    return content.replace(_NEWLINE_ESCAPE, "\n")


def normalize_table_for_merge(table: TableRegion) -> List[str]:
    """Convert a table to normalized format for cell-level merge.

    Each cell becomes its own line with unique context markers around it.
    The context markers ensure merge3 can identify each cell independently,
    allowing changes to different cells in the same row to auto-merge.

    Embedded newlines in cell content are escaped to preserve them.

    Format:
        __CELL_START__|row|col|
        content (with newlines escaped)
        __CELL_END__|row|col|

    Note: All lines include trailing newlines for proper merge3 behavior.
    The merge3 library expects lines with terminators for correct merging.

    Args:
        table: TableRegion to normalize

    Returns:
        List of normalized lines (each with trailing newline)
    """
    lines = []

    # Add header marker with column count
    # Note: All lines must have trailing newlines for merge3 compatibility
    lines.append(f"__TABLE_HEADER__|{len(table.header_row)}|\n")

    # Add header cells with unique context wrappers
    for col_idx, cell in enumerate(table.header_row):
        lines.append(f"__CELL_START__|H|{col_idx}|\n")
        # Escape embedded newlines in cell content
        lines.append(_escape_cell_newlines(cell) + "\n")
        lines.append(f"__CELL_END__|H|{col_idx}|\n")

    # Add separator marker (use ::: delimiter since separator contains | chars)
    lines.append(f"__TABLE_SEP__:::{table.separator_row}\n")

    # Add data rows with unique context wrappers per cell
    for row_idx, row in enumerate(table.data_rows):
        for col_idx, cell in enumerate(row):
            # Unique start marker for this specific cell
            lines.append(f"__CELL_START__|{row_idx}|{col_idx}|\n")
            # Escape embedded newlines in cell content
            lines.append(_escape_cell_newlines(cell) + "\n")
            # Unique end marker for this specific cell
            lines.append(f"__CELL_END__|{row_idx}|{col_idx}|\n")

    lines.append("__TABLE_END__|\n")

    return lines


def denormalize_table(lines: List[str]) -> Optional[str]:
    """Convert normalized table lines back to markdown table format.

    Args:
        lines: Normalized table lines

    Returns:
        Markdown table string, or None if parsing fails
    """
    header_cells = []
    separator = ""
    data_rows = {}  # row_idx -> {col_idx: cell}
    col_count = 0

    # State machine for parsing
    current_cell_row = None
    current_cell_col = None
    current_cell_is_header = False

    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')

        if line.startswith("__TABLE_HEADER__|"):
            parts = line.split('|')
            if len(parts) >= 3:
                col_count = int(parts[1])

        elif line.startswith("__CELL_START__|"):
            # Start of a cell: __CELL_START__|row|col|
            parts = line.split('|')
            if len(parts) >= 4:
                row_part = parts[1]
                col_part = parts[2]
                current_cell_is_header = (row_part == 'H')
                current_cell_row = row_part if current_cell_is_header else int(row_part)
                current_cell_col = int(col_part)

        elif line.startswith("__CELL_END__|"):
            # End of a cell - reset state
            current_cell_row = None
            current_cell_col = None

        elif line.startswith("__TABLE_SEP__:::"):
            # Extract separator after the ::: delimiter
            separator = line[len("__TABLE_SEP__:::"):]

        elif line.startswith("__TABLE_END__|"):
            break

        elif current_cell_row is not None and current_cell_col is not None:
            # This is cell content - unescape embedded newlines
            content = _unescape_cell_newlines(line)
            if current_cell_is_header:
                while len(header_cells) <= current_cell_col:
                    header_cells.append("")
                header_cells[current_cell_col] = content
            else:
                row_idx = current_cell_row
                if row_idx not in data_rows:
                    data_rows[row_idx] = {}
                data_rows[row_idx][current_cell_col] = content

        i += 1

    if not header_cells:
        return None

    # Build markdown table
    result_lines = []

    # Header row
    result_lines.append("| " + " | ".join(header_cells) + " |")

    # Separator row
    result_lines.append(separator)

    # Data rows
    for row_idx in sorted(data_rows.keys()):
        row_cells = []
        for col_idx in range(len(header_cells)):
            cell = data_rows[row_idx].get(col_idx, "")
            row_cells.append(cell)
        result_lines.append("| " + " | ".join(row_cells) + " |")

    return "\n".join(result_lines)


def merge_tables(
    base_table: TableRegion,
    local_table: TableRegion,
    remote_table: TableRegion
) -> Tuple[str, bool]:
    """Perform cell-level 3-way merge on tables.

    Args:
        base_table: Common ancestor table
        local_table: Local version of table
        remote_table: Remote version of table

    Returns:
        Tuple of (merged_table_str, has_conflicts)
    """
    # Normalize all three versions
    base_lines = normalize_table_for_merge(base_table)
    local_lines = normalize_table_for_merge(local_table)
    remote_lines = normalize_table_for_merge(remote_table)

    logger.debug(f"Merging table: base={len(base_lines)} lines, "
                 f"local={len(local_lines)} lines, remote={len(remote_lines)} lines")

    # Perform 3-way merge using merge3
    m3 = Merge3(base_lines, local_lines, remote_lines)

    merged_lines = list(m3.merge_lines(
        name_a='local',
        name_b='remote',
        start_marker='<<<<<<< local',
        mid_marker='=======',
        end_marker='>>>>>>> remote'
    ))

    # Check for conflicts
    has_conflicts = any('<<<<<<< local' in line for line in merged_lines)

    if has_conflicts:
        logger.debug("Table merge has conflicts at cell level")
        # Return the raw merged output with conflict markers
        # We need to try to denormalize what we can
        return _denormalize_with_conflicts(merged_lines), True

    # Clean merge - denormalize back to table
    merged_table = denormalize_table(merged_lines)

    if merged_table is None:
        logger.warning("Failed to denormalize merged table")
        return "", True

    logger.debug("Table merge successful (no conflicts)")
    return merged_table, False


def _denormalize_with_conflicts(lines: List[str]) -> str:
    """Attempt to denormalize merged content that has conflicts.

    This is a best-effort conversion - conflicts will be shown in
    a readable format even if not perfect markdown.

    Args:
        lines: Merged lines with potential conflict markers

    Returns:
        Best-effort table representation with conflict markers
    """
    # For now, just join lines and let the user resolve
    # Future enhancement: smarter conflict presentation
    result_lines = []
    in_conflict = False
    current_cell_info = None

    for line in lines:
        line = line.rstrip('\n')

        if '<<<<<<< local' in line:
            in_conflict = True
            result_lines.append(line)
        elif '=======' in line and in_conflict:
            result_lines.append(line)
        elif '>>>>>>> remote' in line:
            in_conflict = False
            result_lines.append(line)
        elif line.startswith("__CELL_START__|"):
            # Extract cell info for context
            parts = line.split('|')
            if len(parts) >= 4:
                row = parts[1]
                col = parts[2]
                current_cell_info = f"[Row {row}, Col {col}]"
                if in_conflict:
                    result_lines.append(f"{current_cell_info}:")
        elif line.startswith("__CELL_END__|"):
            current_cell_info = None
        elif line.startswith("__"):
            # Skip other markers in conflict output
            pass
        else:
            # Actual content
            if current_cell_info and not in_conflict:
                result_lines.append(f"{current_cell_info}: {line}")
            else:
                result_lines.append(line)

    return "\n".join(result_lines)


def merge_content_with_table_awareness(
    base_content: str,
    local_content: str,
    remote_content: str
) -> Tuple[str, bool]:
    """Merge content with special handling for markdown tables.

    Tables are extracted and merged at cell level, while other content
    uses standard line-based merge.

    Args:
        base_content: Common ancestor content
        local_content: Local version
        remote_content: Remote version

    Returns:
        Tuple of (merged_content, has_conflicts)
    """
    # Find tables in all versions
    base_tables = find_tables(base_content)
    local_tables = find_tables(local_content)
    remote_tables = find_tables(remote_content)

    logger.debug(f"Found tables: base={len(base_tables)}, "
                 f"local={len(local_tables)}, remote={len(remote_tables)}")

    # If no tables or table count mismatch, fall back to line-based merge
    if not base_tables or len(base_tables) != len(local_tables) or len(base_tables) != len(remote_tables):
        logger.debug("Table count mismatch or no tables - using line-based merge")
        return _line_based_merge(base_content, local_content, remote_content)

    # Split content into regions (non-table and table)
    base_lines = base_content.split('\n')
    local_lines = local_content.split('\n')
    remote_lines = remote_content.split('\n')

    # Process content, replacing tables with merged versions
    result_lines = []
    has_any_conflicts = False

    base_pos = 0
    local_pos = 0
    remote_pos = 0

    for table_idx, base_table in enumerate(base_tables):
        local_table = local_tables[table_idx]
        remote_table = remote_tables[table_idx]

        # Merge non-table content before this table
        if base_pos < base_table.start_line:
            pre_base = '\n'.join(base_lines[base_pos:base_table.start_line])
            pre_local = '\n'.join(local_lines[local_pos:local_table.start_line])
            pre_remote = '\n'.join(remote_lines[remote_pos:remote_table.start_line])

            merged_pre, pre_conflicts = _line_based_merge(pre_base, pre_local, pre_remote)
            if merged_pre:
                result_lines.append(merged_pre)
            has_any_conflicts = has_any_conflicts or pre_conflicts

        # Merge the table at cell level
        merged_table, table_conflicts = merge_tables(base_table, local_table, remote_table)
        result_lines.append(merged_table)
        has_any_conflicts = has_any_conflicts or table_conflicts

        # Update positions
        base_pos = base_table.end_line + 1
        local_pos = local_table.end_line + 1
        remote_pos = remote_table.end_line + 1

    # Merge remaining content after last table
    if base_pos < len(base_lines):
        post_base = '\n'.join(base_lines[base_pos:])
        post_local = '\n'.join(local_lines[local_pos:])
        post_remote = '\n'.join(remote_lines[remote_pos:])

        merged_post, post_conflicts = _line_based_merge(post_base, post_local, post_remote)
        if merged_post:
            result_lines.append(merged_post)
        has_any_conflicts = has_any_conflicts or post_conflicts

    return '\n'.join(result_lines), has_any_conflicts


def _line_based_merge(
    base: str,
    local: str,
    remote: str
) -> Tuple[str, bool]:
    """Perform standard line-based 3-way merge.

    Args:
        base: Common ancestor
        local: Local version
        remote: Remote version

    Returns:
        Tuple of (merged_content, has_conflicts)
    """
    base_lines = base.split('\n') if base else []
    local_lines = local.split('\n') if local else []
    remote_lines = remote.split('\n') if remote else []

    m3 = Merge3(base_lines, local_lines, remote_lines)

    merged_lines = list(m3.merge_lines(
        name_a='local',
        name_b='remote',
        start_marker='<<<<<<< local',
        mid_marker='=======',
        end_marker='>>>>>>> remote'
    ))

    # Remove trailing newlines from each line (merge_lines adds them)
    merged_lines = [line.rstrip('\n') for line in merged_lines]

    has_conflicts = any('<<<<<<< local' in line for line in merged_lines)

    return '\n'.join(merged_lines), has_conflicts
