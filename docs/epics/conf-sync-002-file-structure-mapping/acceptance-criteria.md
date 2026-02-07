# Acceptance Criteria: File Structure & Mapping Configuration Sync (Epic CONF-SYNC-002)

## Overview

This document tracks the acceptance criteria for the File Structure & Mapping epic. All criteria must be verified and checked off before the epic can be considered complete.

---

## AC-1: Filesafe Filename Conversion

**Status: ✅ COMPLETE**

Filesafe conversion must preserve case and handle all special characters correctly per ADR-010.

- [x] **AC-1.1**: Basic conversion - Spaces to hyphens, .md extension added
  - Example: "Customer Feedback" → "Customer-Feedback.md"
  - Implementation: `src/file_mapper/filesafe_converter.py`
  - Tests: `tests/unit/file_mapper/test_filesafe_converter.py` (100% coverage, 59 tests)
  - Verified: ✅ subtask-2-1, subtask-2-2

- [x] **AC-1.2**: Special character conversion - Colons to double hyphens
  - Example: "API Reference: Getting Started" → "API-Reference--Getting-Started.md"
  - Implementation: Handles `:` → `--` and other special chars (/, \, ?, %, *, |, ", <, >, &) → `-`
  - Tests: Comprehensive test coverage for all special characters
  - Verified: ✅ subtask-2-1, subtask-2-2

- [x] **AC-1.3**: Case preservation - Original case maintained
  - Example: "Q&A Session" → "Q-A-Session.md" (not "q-a-session.md")
  - Implementation: No lowercasing or uppercasing applied
  - Tests: Case preservation verified in all test scenarios
  - Verified: ✅ subtask-2-1, subtask-2-2

---

## AC-2: Hierarchical Folder Structure

**Status: ✅ COMPLETE**

Local folder structure must mirror Confluence page hierarchy.

- [x] **AC-2.1**: Parent page creates markdown file
  - Parent page "Foo" creates `Foo.md` in local directory
  - Implementation: `src/file_mapper/file_mapper.py` (`_build_file_list_from_hierarchy`)
  - Tests: `tests/unit/file_mapper/test_file_mapper.py`, E2E tests
  - Verified: ✅ subtask-4-1, subtask-6-2

- [x] **AC-2.2**: Child pages create nested structure
  - Child "Bar" of parent "Foo" creates `Foo/Bar.md`
  - Implementation: Recursive directory creation in `_write_files_atomic`
  - Tests: E2E tests verify nested structures (3+ levels)
  - Verified: ✅ subtask-4-1, subtask-6-2

- [x] **AC-2.3**: Multiple levels supported
  - Grandchild "Baz" of "Bar" (child of "Foo") creates `Foo/Bar/Baz.md`
  - Implementation: Recursive hierarchy traversal
  - Tests: E2E-1 tests 15-page hierarchy with multiple nesting levels
  - Verified: ✅ subtask-6-2

---

## AC-3: Configuration with Parent PageID

**Status: ✅ COMPLETE**

Configuration must use parent pageID as anchor point per ADR-012.

- [x] **AC-3.1**: Config stored in `.confluence-sync/config.yaml`
  - Configuration file location standardized
  - Implementation: `src/file_mapper/config_loader.py`
  - Tests: `tests/unit/file_mapper/test_config_loader.py` (100% coverage, 45 tests)
  - Verified: ✅ subtask-2-5, subtask-2-6

- [x] **AC-3.2**: Parent pageID stored (not path)
  - Config field: `parent_page_id: "123456"` (not a file path)
  - Implementation: `SpaceConfig` model with `parent_page_id` field
  - Tests: Config loading/saving validated with parent_page_id
  - Verified: ✅ subtask-1-3, subtask-2-5

- [x] **AC-3.3**: Configuration validation on load
  - Required fields validated: space_key, parent_page_id, local_path
  - Invalid configs raise ConfigError with clear messages
  - Implementation: `ConfigLoader._parse_config()` with comprehensive validation
  - Tests: 45 tests cover all validation scenarios
  - Verified: ✅ subtask-2-5, subtask-2-6

---

## AC-4: CQL-Based Page Discovery

**Status: ✅ COMPLETE**

Page discovery must use CQL queries with 100 page limit per ADR-008 and ADR-013.

- [x] **AC-4.1**: CQL query pattern correct
  - Query: `parent = {page_id} AND space = {space_key}`
  - Returns metadata: page_id, title, version.when (last modified)
  - Implementation: `src/file_mapper/hierarchy_builder.py` (`_query_children_cql`)
  - Tests: Integration tests verify real CQL queries
  - Verified: ✅ subtask-3-1, subtask-5-2

- [x] **AC-4.2**: 100 page limit enforced
  - Fail with PageLimitExceededError if >100 pages at any level
  - Error message explains MVP limitation and suggests splitting hierarchy
  - Implementation: `_build_children_recursive` enforces limit
  - Tests: E2E-6 tests limit with 101 pages
  - Verified: ✅ subtask-3-1, subtask-6-5

- [x] **AC-4.3**: Recursive tree building
  - Build complete PageNode tree recursively from parent
  - Each node contains: page_id, title, parent_id, children list
  - Implementation: `build_hierarchy` method
  - Tests: Unit and integration tests verify recursive building
  - Verified: ✅ subtask-3-1, subtask-3-2

- [x] **AC-4.4**: Boundary condition (exactly 100 pages)
  - Exactly 100 pages at one level succeeds (not an error)
  - Only 101+ pages trigger error
  - Implementation: Limit check uses `len(children) > page_limit`
  - Tests: E2E test `test_page_limit_boundary_success`
  - Verified: ✅ subtask-6-5

---

## AC-5: YAML Frontmatter

**Status: ✅ COMPLETE**

All markdown files must have valid YAML frontmatter per ADR-009.

- [x] **AC-5.1**: Required frontmatter fields
  - All files include: page_id, space_key, title, last_synced, confluence_version
  - Optional field: page_id can be null for new files (before push)
  - Implementation: `src/file_mapper/frontmatter_handler.py`
  - Tests: `tests/unit/file_mapper/test_frontmatter_handler.py` (100% coverage, 38 tests)
  - Verified: ✅ subtask-2-3, subtask-2-4

- [x] **AC-5.2**: Frontmatter parsing and generation
  - parse() method extracts and validates frontmatter from markdown
  - generate() method creates markdown with properly formatted frontmatter
  - Implementation: Uses PyYAML safe_load/safe_dump
  - Tests: Parse/generate round-trip tests verify correctness
  - Verified: ✅ subtask-2-3, subtask-2-4

- [x] **AC-5.3**: Error handling for malformed frontmatter
  - FrontmatterError raised for invalid YAML
  - Error includes line number and clear message
  - Missing required fields detected with descriptive errors
  - Implementation: Comprehensive validation in parse() method
  - Tests: 38 tests cover all error conditions
  - Verified: ✅ subtask-2-3, subtask-2-4

---

## AC-6: Initial Sync Direction

**Status: ✅ COMPLETE**

Initial sync must detect which side is empty and sync from populated side per ADR-014.

- [x] **AC-6.1**: Empty local detection
  - If local path empty/nonexistent and Confluence has pages → Pull sync
  - Implementation: `FileMapper._detect_sync_direction()`
  - Tests: Unit tests verify empty local detection
  - Verified: ✅ subtask-4-1, subtask-4-2

- [x] **AC-6.2**: Empty Confluence detection
  - If parent page has no children and local has files → Push sync
  - Implementation: Children count check in sync direction logic
  - Tests: Unit tests and E2E-2 verify push detection
  - Verified: ✅ subtask-4-1, subtask-6-3

- [x] **AC-6.3**: Both sides populated - Error
  - If both sides have content → Fail with clear error
  - Error message suggests using --forcePull or --forcePush
  - Implementation: Raises error in _detect_sync_direction
  - Tests: Unit test `test_detect_sync_direction_both_sides_error`
  - Verified: ✅ subtask-4-1, subtask-4-2

- [x] **AC-6.4**: Force pull flag
  - Config option `force_pull: true` forces pull from Confluence
  - Overrides bidirectional conflict detection
  - Implementation: SyncConfig model with force_pull field
  - Tests: Config validation ensures force_pull/force_push mutually exclusive
  - Verified: ✅ subtask-1-3, subtask-2-5

- [x] **AC-6.5**: Force push flag
  - Config option `force_push: true` forces push to Confluence
  - Mutually exclusive with force_pull
  - Implementation: SyncConfig validation in ConfigLoader
  - Tests: ConfigError raised if both flags true
  - Verified: ✅ subtask-1-3, subtask-2-5

---

## AC-7: Page Title Changes

**Status: ✅ COMPLETE**

Title changes in Confluence must trigger local file rename.

- [x] **AC-7.1**: Title change detection
  - Compare frontmatter title with current Confluence title
  - Detect mismatch during sync
  - Implementation: Title comparison in sync logic
  - Tests: E2E-4 test `test_title_change_renames_local_file`
  - Verified: ✅ subtask-6-4

- [x] **AC-7.2**: File rename with frontmatter update
  - Old file deleted, new file created with updated title
  - Frontmatter updated to match new title
  - Filesafe conversion applied to new title
  - Implementation: File rename logic in FileMapper
  - Tests: E2E tests verify old file deleted, new file exists
  - Verified: ✅ subtask-6-4

- [x] **AC-7.3**: Special characters in new title
  - New title with special chars converted correctly
  - Example: "API Reference: Getting Started & FAQ's" handled properly
  - Implementation: FilesafeConverter applied to new title
  - Tests: E2E test `test_title_change_with_special_characters`
  - Verified: ✅ subtask-6-4

---

## AC-8: Exclusion Patterns

**Status: ✅ COMPLETE**

Pages can be excluded by pageID per ADR-015 (MVP scope: pageID only, no regex).

- [x] **AC-8.1**: Exclusion by pageID
  - Config field: `exclude_page_ids: ["123", "456"]`
  - Excluded pages not synced to local
  - Implementation: Exclusion check in `HierarchyBuilder._build_children_recursive`
  - Tests: Unit tests and E2E-5 `test_exclusion_by_page_id`
  - Verified: ✅ subtask-3-1, subtask-6-5

- [x] **AC-8.2**: Descendants also excluded
  - If page excluded, all descendants automatically excluded
  - Recursive exclusion enforced
  - Implementation: Excluded pages skipped before recursion
  - Tests: E2E-5 verifies descendants not synced
  - Verified: ✅ subtask-6-5

- [x] **AC-8.3**: Multiple exclusions supported
  - Multiple pageIDs can be in exclude list
  - Each excluded independently with descendants
  - Implementation: List of pageIDs in SpaceConfig
  - Tests: E2E test `test_exclusion_with_multiple_excluded_pages`
  - Verified: ✅ subtask-6-5

---

## AC-9: Duplicate Title Handling

**Status: ⚠️ PARTIAL (MVP Scope)**

Handle potential duplicate titles gracefully.

- [x] **AC-9.1**: Filename collision detection
  - Detect if two pages would create same filename
  - Fail with clear error (defensive - should not happen in Confluence)
  - Implementation: Collision detection in file list building
  - Tests: Unit tests verify collision detection logic
  - Verified: ✅ subtask-4-1

- [ ] **AC-9.2**: Unique filename generation (Future Enhancement)
  - Append pageID or number to make filenames unique
  - Example: "Page-Title.md", "Page-Title-2.md"
  - **Status**: Deferred to post-MVP
  - **Rationale**: Confluence enforces unique titles per parent, so collisions should not occur in practice. Added defensive error handling for MVP.

---

## AC-10: Last Modified Optimization

**Status: ⚠️ PARTIAL (MVP Scope)**

Optimize sync by only updating changed pages.

- [x] **AC-10.1**: Store last modified timestamp
  - Frontmatter includes `last_synced` and `confluence_version`
  - CQL query returns `version.when` (last modified time)
  - Implementation: Metadata stored in frontmatter
  - Tests: Frontmatter tests verify timestamp fields
  - Verified: ✅ subtask-2-3, subtask-5-2

- [ ] **AC-10.2**: Skip unchanged pages during sync (Future Enhancement)
  - Compare local `last_synced` with Confluence `version.when`
  - Only sync if Confluence version newer
  - **Status**: Deferred to post-MVP
  - **Rationale**: MVP syncs all pages for simplicity. Optimization added in future iteration for performance.

---

## Summary

### Completion Status

| Acceptance Criteria | Status | Subtasks | Test Coverage |
|---------------------|--------|----------|---------------|
| AC-1: Filesafe Conversion | ✅ Complete | 2-1, 2-2 | 100% (59 tests) |
| AC-2: Hierarchical Structure | ✅ Complete | 4-1, 6-2 | 97% (38 tests + E2E) |
| AC-3: Configuration | ✅ Complete | 2-5, 2-6 | 100% (45 tests) |
| AC-4: CQL Discovery | ✅ Complete | 3-1, 3-2, 5-2 | 100% (21 tests + 15 integration) |
| AC-5: YAML Frontmatter | ✅ Complete | 2-3, 2-4 | 100% (38 tests) |
| AC-6: Initial Sync Direction | ✅ Complete | 4-1, 4-2, 6-2, 6-3 | 97% (38 tests + E2E) |
| AC-7: Title Changes | ✅ Complete | 6-4 | E2E (3 tests) |
| AC-8: Exclusion Patterns | ✅ Complete | 3-1, 6-5 | Unit + E2E (2 tests) |
| AC-9: Duplicate Titles | ⚠️ Partial (MVP) | 4-1 | Detection only |
| AC-10: Last Modified | ⚠️ Partial (MVP) | 2-3, 5-2 | Storage only |

### Overall Status

- **Complete**: 8/10 acceptance criteria fully implemented
- **Partial**: 2/10 criteria have MVP-scope implementation (full implementation deferred)
- **Coverage**: 98% code coverage across file_mapper module
- **Tests**: 287 passing tests (unit + integration + E2E)

### ADR Compliance

All ADRs correctly implemented:
- ✅ ADR-008: CQL-based page discovery
- ✅ ADR-009: YAML frontmatter format
- ✅ ADR-010: Filesafe conversion with case preservation
- ✅ ADR-011: Atomic file operations (two-phase commit)
- ✅ ADR-012: Parent pageID as configuration anchor
- ✅ ADR-013: 100 page limit per level (MVP)
- ✅ ADR-014: Strict initial sync requirement
- ✅ ADR-015: Exclusion by pageID only (MVP)

### Notes

**AC-9.2** and **AC-10.2** are partially implemented for MVP:
- AC-9.2: Collision detection in place, unique filename generation deferred (Confluence prevents duplicates)
- AC-10.2: Timestamp storage in place, skip-unchanged optimization deferred (MVP syncs all pages)

Both deferred features are tracked for future enhancement post-MVP.

---

**Last Updated**: 2026-01-30
**Epic**: CONF-SYNC-002
**Phase**: Final Validation (Phase 8)
