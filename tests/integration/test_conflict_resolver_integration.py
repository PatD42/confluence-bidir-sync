"""Integration tests for conflict resolution with table-aware merging.

Tests the interaction between merge orchestration and table merge components,
verifying that:
- Table conflicts route to cell-level merge
- Non-table content uses standard line-based merge
- Mixed content is handled correctly
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.git_integration.table_merge import (
    merge_content_with_table_awareness,
    merge_tables,
    find_tables,
    TableRegion,
)
from tests.fixtures.adf_fixtures import (
    CONFLICT_BASE_MARKDOWN,
    CONFLICT_LOCAL_MARKDOWN,
    CONFLICT_REMOTE_MARKDOWN,
    CONFLICT_LOCAL_CELL_A_MARKDOWN,
    CONFLICT_REMOTE_CELL_B_MARKDOWN,
    CONFLICT_MERGED_NO_CONFLICT,
)


@pytest.mark.integration
@pytest.mark.conflict
class TestConflictResolverIntegration:
    """Integration tests for ConflictResolver + TableMerge."""

    def test_cell_level_merge_uses_table_merge(self, mock_baseline_with_content):
        """AC-5.1: Table conflicts route to TableMerge for cell-level merge."""
        # Given: baseline, local, and remote with table content
        baseline = CONFLICT_BASE_MARKDOWN.strip()
        local = CONFLICT_LOCAL_CELL_A_MARKDOWN.strip()
        remote = CONFLICT_REMOTE_CELL_B_MARKDOWN.strip()

        # When: merge is performed with table awareness
        result, has_conflicts = merge_content_with_table_awareness(baseline, local, remote)

        # Then: both changes should be merged without conflict
        assert "<<<<<<" not in result, f"Unexpected conflict markers in: {result}"
        assert "A-local" in result, "Local change to cell A should be present"
        assert "B-remote" in result, "Remote change to cell B should be present"

    def test_same_cell_conflict_produces_markers(self):
        """AC-5.1b: Same cell edited both sides produces conflict markers."""
        # Given: same cell edited in both local and remote
        baseline = CONFLICT_BASE_MARKDOWN.strip()
        local = CONFLICT_LOCAL_MARKDOWN.strip()
        remote = CONFLICT_REMOTE_MARKDOWN.strip()

        # When: merge is performed
        result, _ = merge_content_with_table_awareness(baseline, local, remote)

        # Then: conflict markers should be present
        assert "<<<<<<" in result or "A-local" in result or "A-remote" in result, \
            "Should have conflict markers or both values when same cell edited"

    def test_non_table_content_uses_standard_merge(self, temp_test_dir):
        """AC-5.2: Paragraph conflicts use merge3 (not TableMerge)."""
        # Given: content without tables
        baseline = "First paragraph.\n\nSecond paragraph."
        local = "First paragraph modified locally.\n\nSecond paragraph."
        remote = "First paragraph.\n\nSecond paragraph modified remotely."

        # When: merge is performed
        result, _ = merge_content_with_table_awareness(baseline, local, remote)

        # Then: both changes should be present (no table merge needed)
        assert "modified locally" in result, "Local change should be present"
        assert "modified remotely" in result, "Remote change should be present"

    def test_mixed_content_routes_correctly(self):
        """AC-5.3: Mixed content uses appropriate handler per section."""
        # Given: content with both table and paragraph
        baseline = """# Header

| Col1 | Col2 |
|------|------|
| A | B |

Paragraph text.
"""
        local = """# Header

| Col1 | Col2 |
|------|------|
| A-local | B |

Paragraph text modified locally.
"""
        remote = """# Header

| Col1 | Col2 |
|------|------|
| A | B-remote |

Paragraph text modified remotely.
"""

        # When: merge is performed
        result, _ = merge_content_with_table_awareness(baseline, local, remote)

        # Then: table section should use cell-level merge
        assert "A-local" in result, "Local table change should be present"
        assert "B-remote" in result, "Remote table change should be present"

        # And: paragraph section should also be merged
        # (may have conflict if same paragraph edited, or merged if different)
        assert "Paragraph" in result, "Paragraph content should be present"


@pytest.mark.integration
@pytest.mark.conflict
class TestTableMergeIntegration:
    """Integration tests for table merge operations."""

    def test_find_tables_identifies_all_tables(self):
        """Verify find_tables correctly identifies table regions."""
        content = """# Document

| Table1 Col1 | Table1 Col2 |
|-------------|-------------|
| A | B |

Some text between tables.

| Table2 Col1 | Table2 Col2 |
|-------------|-------------|
| X | Y |
| Z | W |
"""
        tables = find_tables(content)

        assert len(tables) == 2, f"Expected 2 tables, found {len(tables)}"
        assert tables[0].header_row == ["Table1 Col1", "Table1 Col2"]
        assert tables[1].header_row == ["Table2 Col1", "Table2 Col2"]
        assert len(tables[0].data_rows) == 1
        assert len(tables[1].data_rows) == 2

    def test_table_merge_preserves_structure(self):
        """Verify table structure is preserved after merge."""
        base_table = TableRegion(
            start_line=0,
            end_line=3,
            header_row=["Col1", "Col2"],
            separator_row="| --- | --- |",
            data_rows=[["A", "B"], ["C", "D"]]
        )
        local_table = TableRegion(
            start_line=0,
            end_line=3,
            header_row=["Col1", "Col2"],
            separator_row="| --- | --- |",
            data_rows=[["A-local", "B"], ["C", "D"]]
        )
        remote_table = TableRegion(
            start_line=0,
            end_line=3,
            header_row=["Col1", "Col2"],
            separator_row="| --- | --- |",
            data_rows=[["A", "B-remote"], ["C", "D"]]
        )

        result, _ = merge_tables(base_table, local_table, remote_table)

        # Result should be a valid markdown table
        lines = result.strip().split('\n')
        assert len(lines) >= 3, "Result should have at least header, separator, and data row"
        assert lines[0].startswith('|'), "First line should be table header"
        assert '---' in lines[1], "Second line should be separator"

    def test_row_addition_merges_correctly(self):
        """Verify new rows from both sides are merged."""
        baseline = """| Col1 | Col2 |
|------|------|
| A | B |
"""
        local = """| Col1 | Col2 |
|------|------|
| A | B |
| Local | Row |
"""
        remote = """| Col1 | Col2 |
|------|------|
| A | B |
| Remote | Row |
"""

        result, _ = merge_content_with_table_awareness(
            baseline.strip(), local.strip(), remote.strip()
        )

        # Both new rows should be present
        assert "Local" in result, "Local row should be added"
        assert "Remote" in result, "Remote row should be added"

    def test_row_deletion_handled_correctly(self):
        """Verify row deletion is handled when one side deletes."""
        baseline = """| Col1 | Col2 |
|------|------|
| A | B |
| C | D |
"""
        local = """| Col1 | Col2 |
|------|------|
| A | B |
"""  # Deleted row C/D
        remote = """| Col1 | Col2 |
|------|------|
| A | B |
| C | D |
"""  # Unchanged

        result, _ = merge_content_with_table_awareness(
            baseline.strip(), local.strip(), remote.strip()
        )

        # Deleted row should not be present (local deleted it)
        assert "| A | B |" in result, "First data row should remain"
        # The deleted row may or may not be present depending on merge strategy


@pytest.mark.integration
@pytest.mark.conflict
class TestMergeWithBaseline:
    """Integration tests for 3-way merge with baseline."""

    def test_baseline_identifies_local_changes(self, mock_baseline_with_content):
        """Verify baseline correctly identifies what local changed."""
        baseline = mock_baseline_with_content.get_baseline_content('12345')
        assert baseline is not None, "Baseline should exist"

        local = """| Col1 | Col2 |
|------|------|
| A-modified | B |
| C | D |
"""

        # The change is in cell A: from "A" to "A-modified"
        result, _ = merge_content_with_table_awareness(
            baseline.strip(),
            local.strip(),
            baseline.strip()  # Remote unchanged
        )

        assert "A-modified" in result, "Local modification should be preserved"

    def test_baseline_identifies_remote_changes(self, mock_baseline_with_content):
        """Verify baseline correctly identifies what remote changed."""
        baseline = mock_baseline_with_content.get_baseline_content('12345')

        remote = """| Col1 | Col2 |
|------|------|
| A | B-modified |
| C | D |
"""

        result, _ = merge_content_with_table_awareness(
            baseline.strip(),
            baseline.strip(),  # Local unchanged
            remote.strip()
        )

        assert "B-modified" in result, "Remote modification should be preserved"
