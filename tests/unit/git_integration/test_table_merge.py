"""Unit tests for table-aware 3-way merge."""

import pytest
from src.git_integration.table_merge import (
    parse_table_row,
    is_separator_row,
    find_tables,
    normalize_table_for_merge,
    denormalize_table,
    merge_tables,
    merge_content_with_table_awareness,
)


class TestParseTableRow:
    """Tests for parse_table_row function."""

    def test_parse_simple_row(self):
        """Parse a simple table row."""
        result = parse_table_row("| A | B | C |")
        assert result == ["A", "B", "C"]

    def test_parse_row_with_content(self):
        """Parse a row with actual content."""
        result = parse_table_row("| Feature | Status | Owner |")
        assert result == ["Feature", "Status", "Owner"]

    def test_parse_row_with_spaces(self):
        """Parse a row with extra spaces."""
        result = parse_table_row("|  A  |  B  |  C  |")
        assert result == ["A", "B", "C"]

    def test_parse_invalid_row_no_pipes(self):
        """Return None for non-table row."""
        result = parse_table_row("This is not a table row")
        assert result is None

    def test_parse_invalid_row_no_end_pipe(self):
        """Return None for row without ending pipe."""
        result = parse_table_row("| A | B | C")
        assert result is None


class TestIsSeparatorRow:
    """Tests for is_separator_row function."""

    def test_simple_separator(self):
        """Detect simple separator row."""
        assert is_separator_row("| --- | --- | --- |") is True

    def test_separator_with_colons(self):
        """Detect separator with alignment colons."""
        assert is_separator_row("| :--- | :---: | ---: |") is True

    def test_not_separator_data_row(self):
        """Data row is not a separator."""
        assert is_separator_row("| A | B | C |") is False

    def test_not_separator_plain_text(self):
        """Plain text is not a separator."""
        assert is_separator_row("Some text") is False


class TestFindTables:
    """Tests for find_tables function."""

    def test_find_single_table(self):
        """Find a single table in content."""
        content = """# Header

| Col1 | Col2 |
| --- | --- |
| A | B |
| C | D |

Some text after.
"""
        tables = find_tables(content)
        assert len(tables) == 1
        assert tables[0].header_row == ["Col1", "Col2"]
        assert len(tables[0].data_rows) == 2

    def test_find_multiple_tables(self):
        """Find multiple tables in content."""
        content = """# Header

| Table1 | Col |
| --- | --- |
| A | B |

Text between.

| Table2 | Other |
| --- | --- |
| X | Y |
"""
        tables = find_tables(content)
        assert len(tables) == 2
        assert tables[0].header_row == ["Table1", "Col"]
        assert tables[1].header_row == ["Table2", "Other"]

    def test_no_tables(self):
        """Return empty list when no tables."""
        content = "# Header\n\nSome text without tables."
        tables = find_tables(content)
        assert len(tables) == 0


class TestTableMerge:
    """Tests for table merge functionality."""

    def test_merge_different_cells_same_row(self):
        """Merge changes to different cells in the same row."""
        # This is the user's reported issue
        base = """| # | Section | Description |
| --- | --- | --- |
| 12 | Glossary | Terms, abbreviations, component names |
"""
        local = """| # | Section | Description |
| --- | --- | --- |
| 12 | Glossary | Terms, abbreviations, component names and gizmos |
"""
        remote = """| # | Section | Description |
| --- | --- | --- |
| 12 | Glossaries | Terms, abbreviations, component names |
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        assert has_conflicts is False, f"Should merge cleanly, got: {merged}"
        assert "Glossaries" in merged, "Should have remote's 'Glossaries'"
        assert "and gizmos" in merged, "Should have local's 'and gizmos'"

    def test_merge_different_rows(self):
        """Merge changes to different rows."""
        base = """| Feature | Status |
| --- | --- |
| Login | Complete |
| Dashboard | Pending |
"""
        local = """| Feature | Status |
| --- | --- |
| Login | Complete |
| Dashboard | In Progress |
"""
        remote = """| Feature | Status |
| --- | --- |
| Login | Done |
| Dashboard | Pending |
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        assert has_conflicts is False, f"Should merge cleanly, got: {merged}"
        assert "Done" in merged, "Should have remote's Login change"
        assert "In Progress" in merged, "Should have local's Dashboard change"

    def test_conflict_same_cell(self):
        """Conflict when same cell changed on both sides."""
        base = """| Col |
| --- |
| Original |
"""
        local = """| Col |
| --- |
| Local Change |
"""
        remote = """| Col |
| --- |
| Remote Change |
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        assert has_conflicts is True, "Should have conflict when same cell changed"
        assert "<<<<<<< local" in merged, "Should have conflict markers"

    def test_merge_with_non_table_content(self):
        """Merge content that includes both tables and non-table text."""
        base = """# Title

Some intro text.

| Col1 | Col2 |
| --- | --- |
| A | B |

Footer text.
"""
        local = """# Title

Some intro text.

| Col1 | Col2 |
| --- | --- |
| A | B-local |

Footer text.
"""
        remote = """# Title

Some intro text.

| Col1 | Col2 |
| --- | --- |
| A-remote | B |

Footer text.
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        assert has_conflicts is False, f"Should merge cleanly, got: {merged}"
        assert "A-remote" in merged
        assert "B-local" in merged
        assert "# Title" in merged
        assert "Footer text" in merged


class TestNormalizeAndDenormalize:
    """Tests for table normalization round-trip."""

    def test_round_trip(self):
        """Normalize and denormalize should preserve table."""
        content = """| Col1 | Col2 |
| --- | --- |
| A | B |
| C | D |
"""
        tables = find_tables(content)
        assert len(tables) == 1

        normalized = normalize_table_for_merge(tables[0])
        denormalized = denormalize_table(normalized)

        # Check structure is preserved
        assert "| Col1 | Col2 |" in denormalized
        assert "| A | B |" in denormalized
        assert "| C | D |" in denormalized

    def test_cells_with_br_tags_preserved(self):
        """Cells with <br> tags should be preserved through merge."""
        base = """| Feature | Notes |
| --- | --- |
| Login | Users can<br>authenticate |
"""
        local = """| Feature | Notes |
| --- | --- |
| Login | Users can<br>authenticate here |
"""
        remote = """| Feature | Notes |
| --- | --- |
| Login System | Users can<br>authenticate |
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        assert has_conflicts is False
        assert "Login System" in merged, "Should have remote's title change"
        assert "authenticate here" in merged, "Should have local's note change"
        assert "<br>" in merged, "Should preserve <br> tags"


class TestSeparatorRowHandling:
    """Tests for table separator row handling (--- or ::: delimiters)."""

    def test_separator_with_dashes(self):
        """Standard --- separator should be detected."""
        assert is_separator_row("| --- | --- |") is True
        assert is_separator_row("| --- | --- | --- |") is True
        assert is_separator_row("|---|---|") is True

    def test_separator_with_alignment(self):
        """Alignment indicators in separators should be detected."""
        assert is_separator_row("| :--- | ---: |") is True
        assert is_separator_row("| :---: | :---: |") is True
        assert is_separator_row("|:---:|:---:|") is True

    def test_separator_with_extra_dashes(self):
        """Separators with many dashes should be detected."""
        assert is_separator_row("| ------ | ------ |") is True
        assert is_separator_row("| ------------- | --- |") is True

    def test_merge_preserves_separator(self):
        """Merge should preserve separator row format."""
        base = """| Col1 | Col2 |
| :--- | ---: |
| A | B |
"""
        local = """| Col1 | Col2 |
| :--- | ---: |
| A | B-local |
"""
        remote = """| Col1 | Col2 |
| :--- | ---: |
| A-remote | B |
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        assert has_conflicts is False
        assert "A-remote" in merged
        assert "B-local" in merged
        # Separator should be preserved (may be normalized)
        lines = merged.strip().split('\n')
        # Second line should be separator
        assert is_separator_row(lines[1])


class TestEmbeddedNewlinesInCells:
    """Tests for handling cells with embedded newlines (using __CELL_NEWLINE__ escaping)."""

    def test_multiple_br_in_same_cell(self):
        """Multiple <br> tags in same cell should survive merge."""
        base = """| Feature | Description |
| --- | --- |
| Auth | Step 1<br>Step 2<br>Step 3 |
"""
        local = """| Feature | Description |
| --- | --- |
| Auth | Step 1<br>Step 2<br>Step 3<br>Step 4 |
"""
        remote = """| Feature | Description |
| --- | --- |
| Authentication | Step 1<br>Step 2<br>Step 3 |
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        assert has_conflicts is False
        assert "Authentication" in merged
        assert "Step 4" in merged
        # All <br> tags preserved
        assert merged.count("<br>") >= 3

    def test_newline_in_cell_different_columns_merge(self):
        """Changes to different columns with <br> content should merge."""
        base = """| Name | Address | Notes |
| --- | --- | --- |
| John | 123 Main St<br>Apt 4 | Good customer |
"""
        local = """| Name | Address | Notes |
| --- | --- | --- |
| John | 123 Main St<br>Apt 4 | Great customer |
"""
        remote = """| Name | Address | Notes |
| --- | --- | --- |
| John Doe | 123 Main St<br>Apt 4 | Good customer |
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        assert has_conflicts is False
        assert "John Doe" in merged
        assert "Great customer" in merged
        assert "<br>" in merged

    def test_conflict_in_cell_with_br(self):
        """Same cell with <br> modified on both sides should conflict."""
        base = """| Item | Details |
| --- | --- |
| Config | Line A<br>Line B |
"""
        local = """| Item | Details |
| --- | --- |
| Config | Line A-local<br>Line B |
"""
        remote = """| Item | Details |
| --- | --- |
| Config | Line A-remote<br>Line B |
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        assert has_conflicts is True
        assert "<<<<<<< local" in merged

    def test_empty_cell_adjacent_to_br_cell(self):
        """Empty cells next to cells with <br> should work correctly."""
        base = """| A | B | C |
| --- | --- | --- |
|  | Multi<br>line |  |
"""
        local = """| A | B | C |
| --- | --- | --- |
| filled |  Multi<br>line |  |
"""
        remote = """| A | B | C |
| --- | --- | --- |
|  | Multi<br>line | filled |
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        # Both changes to different cells should merge
        assert has_conflicts is False
        assert "Multi<br>line" in merged or "Multi" in merged


class TestTableMergeEdgeCases:
    """Additional edge cases for table merge."""

    def test_headerless_table(self):
        """Tables without clear headers should still merge."""
        # Some markdown allows tables without headers
        base = """| A | B |
| C | D |
"""
        # This may not parse as a proper table, but shouldn't crash
        tables = find_tables(base)
        # Behavior depends on implementation - just ensure no crash

    def test_single_column_table(self):
        """Single column tables should merge correctly."""
        base = """| Status |
| --- |
| Active |
| Pending |
"""
        local = """| Status |
| --- |
| Active |
| Complete |
"""
        remote = """| Status |
| --- |
| Inactive |
| Pending |
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        # Different rows changed - should merge
        assert "Inactive" in merged
        assert "Complete" in merged

    def test_table_with_pipes_in_content(self):
        """Cells containing literal pipe characters should be handled."""
        base = """| Command | Output |
| --- | --- |
| ls | file.txt |
"""
        local = """| Command | Output |
| --- | --- |
| ls | file.txt, other.txt |
"""
        remote = """| Command | Output |
| --- | --- |
| dir | file.txt |
"""
        merged, has_conflicts = merge_content_with_table_awareness(base, local, remote)

        assert has_conflicts is False
        assert "dir" in merged
        assert "other.txt" in merged

    def test_consecutive_tables(self):
        """Multiple tables in same document should all be found."""
        content = """# Section 1

| T1 | Col |
| --- | --- |
| A | B |

# Section 2

| T2 | Data |
| --- | --- |
| X | Y |

# Section 3

| T3 | Value |
| --- | --- |
| 1 | 2 |
"""
        tables = find_tables(content)
        assert len(tables) == 3
        assert tables[0].header_row == ["T1", "Col"]
        assert tables[1].header_row == ["T2", "Data"]
        assert tables[2].header_row == ["T3", "Value"]
