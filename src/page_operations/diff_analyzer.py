"""Diff analyzer for generating surgical operations from content changes.

This module provides the DiffAnalyzer class which compares original and
modified content blocks to generate surgical operations that can be
applied to XHTML while preserving Confluence-specific elements.
"""

import logging
from typing import List, Optional, Set

from .models import BlockType, ContentBlock, OperationType, SurgicalOperation

logger = logging.getLogger(__name__)


class DiffAnalyzer:
    """Analyzes differences between original and modified content blocks.

    The DiffAnalyzer compares two sets of ContentBlocks (typically from
    XHTML and modified markdown) and generates SurgicalOperation objects
    that describe the minimum changes needed.

    Key principle: Macros (BlockType.MACRO) are never modified - they are
    excluded from the diff analysis to ensure preservation.
    """

    def _normalize_content(self, content: str) -> str:
        """Normalize content for comparison.

        Collapses multiple whitespace to single spaces to handle minor
        differences between XHTML and markdown parsing.

        Args:
            content: Raw content string

        Returns:
            Normalized content with collapsed whitespace
        """
        if not content:
            return ""
        return " ".join(content.split())

    def analyze(
        self,
        original_blocks: List[ContentBlock],
        modified_blocks: List[ContentBlock],
    ) -> List[SurgicalOperation]:
        """Analyze differences and generate surgical operations.

        Compares original and modified blocks using a two-pass approach:
        1. First pass: Exact content matches (no change needed)
        2. Second pass: Position-based matching for changes

        Args:
            original_blocks: Blocks from original XHTML content
            modified_blocks: Blocks from modified markdown content

        Returns:
            List of SurgicalOperation objects to apply
        """
        operations = []

        # Debug logging for block analysis
        logger.debug(f"Analyzing {len(original_blocks)} original blocks vs {len(modified_blocks)} modified blocks")
        for i, block in enumerate(original_blocks):
            logger.debug(f"  Original[{i}]: {block.block_type.value}, rows={len(block.rows) if block.rows else 'N/A'}, content[:50]={block.content[:50] if block.content else 'empty'}...")
        for i, block in enumerate(modified_blocks):
            logger.debug(f"  Modified[{i}]: {block.block_type.value}, rows={len(block.rows) if block.rows else 'N/A'}, content[:50]={block.content[:50] if block.content else 'empty'}...")

        # Create content-based lookup for original blocks
        orig_by_content = {}
        for block in original_blocks:
            key = self._block_key(block)
            orig_by_content[key] = block

        # Track which original blocks are matched
        matched_originals: Set[str] = set()

        # First pass: exact content matches (these don't need operations)
        for mod_block in modified_blocks:
            key = self._block_key(mod_block)
            if key in orig_by_content:
                matched_originals.add(key)

        # Second pass: position-based matching for unmatched blocks
        mod_non_macro = [b for b in modified_blocks if b.block_type != BlockType.MACRO]
        orig_non_macro = [b for b in original_blocks if b.block_type != BlockType.MACRO]

        for i, mod_block in enumerate(mod_non_macro):
            key = self._block_key(mod_block)
            if key in matched_originals:
                # Already matched exactly - no operation needed
                continue

            # Try to find original block at same position
            if i < len(orig_non_macro):
                orig_block = orig_non_macro[i]
                orig_key = self._block_key(orig_block)

                if orig_key not in matched_originals:
                    # Same position, different content = UPDATE
                    matched_originals.add(orig_key)

                    if (
                        orig_block.block_type == BlockType.HEADING
                        and mod_block.block_type == BlockType.HEADING
                    ):
                        # Heading change
                        if mod_block.level != orig_block.level:
                            operations.append(
                                SurgicalOperation(
                                    op_type=OperationType.CHANGE_HEADING_LEVEL,
                                    target_content=orig_block.content,
                                    new_content=mod_block.content,
                                    old_level=orig_block.level,
                                    new_level=mod_block.level,
                                )
                            )
                        elif self._normalize_content(mod_block.content) != self._normalize_content(orig_block.content):
                            operations.append(
                                SurgicalOperation(
                                    op_type=OperationType.UPDATE_TEXT,
                                    target_content=orig_block.content,
                                    new_content=mod_block.content,
                                )
                            )
                    elif (
                        orig_block.block_type == BlockType.TABLE
                        and mod_block.block_type == BlockType.TABLE
                    ):
                        # Table change - use row-level operations for surgical updates
                        if self._table_content_matches(orig_block, mod_block):
                            logger.debug(f"Tables identical, skipping (orig_rows={len(orig_block.rows or [])}, mod_rows={len(mod_block.rows or [])})")
                            continue
                        # Generate row-level operations (insert/delete/update)
                        logger.debug(f"Tables differ, generating row operations (orig_rows={len(orig_block.rows or [])}, mod_rows={len(mod_block.rows or [])})")
                        table_ops = self._analyze_table_changes(orig_block, mod_block)
                        logger.debug(f"Generated {len(table_ops)} table operations: {[op.op_type.value for op in table_ops]}")
                        operations.extend(table_ops)
                    else:
                        # General text update - skip if either content is empty
                        if (orig_block.content and orig_block.content.strip() and
                            mod_block.content and mod_block.content.strip()):
                            operations.append(
                                SurgicalOperation(
                                    op_type=OperationType.UPDATE_TEXT,
                                    target_content=orig_block.content,
                                    new_content=mod_block.content,
                                )
                            )
                    continue

            # No position match found - check for similar block
            similar = self._find_similar_block(mod_block, original_blocks, matched_originals)
            if similar:
                similar_key = self._block_key(similar)
                matched_originals.add(similar_key)
                logger.debug(f"Similar block found for {mod_block.block_type.value} via fallback, generating UPDATE_TEXT")
                # For tables, use row-level operations instead of UPDATE_TEXT
                if mod_block.block_type == BlockType.TABLE and similar.block_type == BlockType.TABLE:
                    if not self._table_content_matches(similar, mod_block):
                        table_ops = self._analyze_table_changes(similar, mod_block)
                        operations.extend(table_ops)
                else:
                    operations.append(
                        SurgicalOperation(
                            op_type=OperationType.UPDATE_TEXT,
                            target_content=similar.content,
                            new_content=mod_block.content,
                        )
                    )
                continue

            # No match found - this is an INSERT
            # Find the previous block to insert after
            after_content = ""
            if i > 0:
                prev_block = mod_non_macro[i - 1]
                after_content = prev_block.content

            operations.append(
                SurgicalOperation(
                    op_type=OperationType.INSERT_BLOCK,
                    new_content=mod_block.content,
                    after_content=after_content,
                )
            )

        # Check for deletions (original blocks not matched)
        for orig_block in original_blocks:
            key = self._block_key(orig_block)
            if key not in matched_originals and orig_block.block_type != BlockType.MACRO:
                # Skip blocks with empty content - can't target them for deletion
                if not orig_block.content or not orig_block.content.strip():
                    logger.debug(f"Skipping DELETE for block with empty content (type={orig_block.block_type})")
                    continue
                operations.append(
                    SurgicalOperation(
                        op_type=OperationType.DELETE_BLOCK,
                        target_content=orig_block.content,
                    )
                )

        logger.debug(f"DiffAnalyzer generated {len(operations)} operations")
        return operations

    def _block_key(self, block: ContentBlock) -> str:
        """Create a unique key for a block based on type and content.

        For headings, includes the level to detect level changes as modifications.
        For tables, includes row count and full content hash to detect row changes.

        Whitespace is normalized to handle minor differences between XHTML and
        markdown parsing (multiple spaces collapsed to single space).

        Args:
            block: ContentBlock to create key for

        Returns:
            String key combining type, level (for headings), and content info
        """
        # Normalize whitespace for consistent matching
        normalized_content = self._normalize_content(block.content)

        if block.block_type == BlockType.HEADING:
            return f"{block.block_type.value}:L{block.level}:{normalized_content[:100]}"

        if block.block_type == BlockType.TABLE:
            # For tables, use row count + content hash to ensure row changes are detected
            row_count = len(block.rows) if block.rows else 0
            # Create a hash of all row content (with normalized whitespace)
            normalized_rows = tuple(
                tuple(self._normalize_content(cell) for cell in row)
                for row in (block.rows or [])
            )
            row_hash = hash(normalized_rows)
            return f"{block.block_type.value}:rows={row_count}:hash={row_hash}"

        # For other blocks, use first 100 chars (normalized)
        return f"{block.block_type.value}:{normalized_content[:100]}"

    def _find_similar_block(
        self,
        mod_block: ContentBlock,
        orig_blocks: List[ContentBlock],
        already_matched: Set[str],
    ) -> Optional[ContentBlock]:
        """Find a similar block in original content for fuzzy matching.

        Uses word overlap similarity to find blocks that may have been
        edited but are fundamentally the same element.

        Args:
            mod_block: Modified block to find match for
            orig_blocks: Original blocks to search
            already_matched: Set of keys already matched

        Returns:
            Similar original block if found, None otherwise
        """
        best_match = None
        best_score = 0.0

        for orig in orig_blocks:
            key = self._block_key(orig)
            if key in already_matched:
                continue

            # Must be same general type
            if orig.block_type != mod_block.block_type:
                # Exception: allow heading-to-heading regardless of level
                if not (
                    orig.block_type == BlockType.HEADING
                    and mod_block.block_type == BlockType.HEADING
                ):
                    continue

            # Calculate similarity
            score = self._similarity(orig.content, mod_block.content)
            if score > best_score and score > 0.3:  # 30% threshold
                best_score = score
                best_match = orig

        return best_match

    def _similarity(self, s1: str, s2: str) -> float:
        """Calculate word overlap similarity between two strings.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Similarity score from 0.0 to 1.0
        """
        if not s1 or not s2:
            return 0.0

        words1 = set(s1.lower().split())
        words2 = set(s2.lower().split())

        if not words1 or not words2:
            return 0.0

        overlap = len(words1 & words2)
        # Use min to be more lenient with partial matches
        min_len = min(len(words1), len(words2))
        return overlap / min_len if min_len > 0 else 0.0

    def _table_content_matches(
        self,
        orig: ContentBlock,
        mod: ContentBlock,
    ) -> bool:
        """Check if two tables have identical row structure.

        Compares tables row-by-row with normalized cell content.
        Only returns True if all rows match exactly (same cells in same order).

        Args:
            orig: Original table block from XHTML
            mod: Modified table block from markdown

        Returns:
            True if the tables have identical rows
        """
        orig_rows = orig.rows or []
        mod_rows = mod.rows or []

        # Different row count = not a match
        if len(orig_rows) != len(mod_rows):
            return False

        # Compare each row
        for orig_row, mod_row in zip(orig_rows, mod_rows):
            orig_normalized = self._normalize_row(orig_row)
            mod_normalized = self._normalize_row(mod_row)
            if orig_normalized != mod_normalized:
                return False

        return True

    def _normalize_row(self, row: List[str]) -> str:
        """Normalize a table row for comparison.

        Args:
            row: List of cell strings

        Returns:
            Normalized pipe-delimited string
        """
        normalized_cells = []
        for cell in row:
            # Normalize: lowercase, collapse whitespace, strip
            normalized = " ".join(str(cell).lower().split())
            normalized_cells.append(normalized)
        return "|".join(normalized_cells)

    def _row_to_pipe_format(self, row: List[str]) -> str:
        """Convert a row to pipe-delimited format for storage.

        Args:
            row: List of cell strings

        Returns:
            Pipe-delimited string (preserves original case)
        """
        return "|".join(str(cell).strip() for cell in row)

    def _analyze_table_changes(
        self,
        orig: ContentBlock,
        mod: ContentBlock,
    ) -> List[SurgicalOperation]:
        """Analyze changes between two tables at the row level.

        Detects row insertions, deletions, and cell updates by comparing
        normalized row content.

        Args:
            orig: Original table block
            mod: Modified table block

        Returns:
            List of table-specific surgical operations
        """
        operations = []
        orig_rows = orig.rows or []
        mod_rows = mod.rows or []

        # Build normalized lookup for original rows
        # Key: normalized row content, Value: (index, original row)
        orig_normalized = {}
        for i, row in enumerate(orig_rows):
            key = self._normalize_row(row)
            orig_normalized[key] = (i, row)

        # Build normalized lookup for modified rows
        mod_normalized = {}
        for i, row in enumerate(mod_rows):
            key = self._normalize_row(row)
            mod_normalized[key] = (i, row)

        # Track matched rows
        matched_orig_keys = set()
        matched_mod_keys = set()

        # First pass: exact matches (no operation needed)
        for mod_key in mod_normalized:
            if mod_key in orig_normalized:
                matched_orig_keys.add(mod_key)
                matched_mod_keys.add(mod_key)

        # Second pass: find similar rows (cell content updates within a row)
        for mod_key, (mod_idx, mod_row) in mod_normalized.items():
            if mod_key in matched_mod_keys:
                continue

            # Try to find a similar row in original (same position, most content matches)
            best_match_key = None
            best_match_score = 0.0

            for orig_key, (orig_idx, orig_row) in orig_normalized.items():
                if orig_key in matched_orig_keys:
                    continue

                # Calculate cell-by-cell similarity
                if len(orig_row) == len(mod_row):
                    matching_cells = sum(
                        1 for o, m in zip(orig_row, mod_row)
                        if " ".join(str(o).lower().split()) == " ".join(str(m).lower().split())
                    )
                    score = matching_cells / len(orig_row) if orig_row else 0

                    # Prefer same position if scores are equal
                    position_bonus = 0.01 if orig_idx == mod_idx else 0
                    score += position_bonus

                    if score > best_match_score and score >= 0.5:  # At least 50% cells match
                        best_match_score = score
                        best_match_key = orig_key

            if best_match_key:
                # This is a row update (some cells changed)
                matched_orig_keys.add(best_match_key)
                matched_mod_keys.add(mod_key)
                orig_idx, orig_row = orig_normalized[best_match_key]

                # Generate cell update operations for changed cells
                for cell_idx, (orig_cell, mod_cell) in enumerate(zip(orig_row, mod_row)):
                    orig_norm = " ".join(str(orig_cell).lower().split())
                    mod_norm = " ".join(str(mod_cell).lower().split())
                    if orig_norm != mod_norm:
                        operations.append(
                            SurgicalOperation(
                                op_type=OperationType.TABLE_UPDATE_CELL,
                                target_content=orig.content,  # Table content for finding table
                                new_content=str(mod_cell).strip(),
                                row_index=orig_idx,
                                cell_index=cell_idx,
                            )
                        )

        # Deletions: original rows not matched
        for orig_key, (orig_idx, orig_row) in orig_normalized.items():
            if orig_key not in matched_orig_keys:
                row_content = self._row_to_pipe_format(orig_row)
                is_empty_row = not row_content.replace("|", "").strip()
                if is_empty_row:
                    logger.debug(f"Generating DELETE for empty row at index {orig_idx}")
                operations.append(
                    SurgicalOperation(
                        op_type=OperationType.TABLE_DELETE_ROW,
                        target_content=orig.content,  # Table content for finding table
                        new_content=row_content if not is_empty_row else "",  # Empty for index-based deletion
                        row_index=orig_idx,
                    )
                )

        # Insertions: modified rows not matched
        for mod_key, (mod_idx, mod_row) in mod_normalized.items():
            if mod_key not in matched_mod_keys:
                row_content = self._row_to_pipe_format(mod_row)
                # Find the row before this one for positioning
                after_content = ""
                if mod_idx > 0 and mod_idx - 1 < len(mod_rows):
                    after_content = self._row_to_pipe_format(mod_rows[mod_idx - 1])
                operations.append(
                    SurgicalOperation(
                        op_type=OperationType.TABLE_INSERT_ROW,
                        target_content=orig.content,  # Table content for finding table
                        new_content=row_content,  # New row cell content
                        row_index=mod_idx,
                        after_content=after_content,  # Row to insert after
                    )
                )

        logger.debug(f"Table analysis: {len(operations)} operations generated")
        return operations
