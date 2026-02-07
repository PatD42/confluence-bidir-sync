# conf-sync-001: Acceptance Criteria

---

## Meta: Phase & Agent Information

**BMAD Phase**: Phase 1 - Agentic Planning
**Agent Role**: Product Owner
**Created During**: Epic Planning (created with Epic Details)
**Prerequisites**: Epic Details, Product Definition

---

## Context Dependencies

**Required Context (must exist before this document)**:
- [conf-sync-001: Epic Details](./details.md) - User stories, success criteria, scope
- Product Definition: Use cases and capability map

**Provides Context For (documents that depend on this)**:
- Development Phase: Developers implement to satisfy AC
- QA Phase: QA validates AC are met
- [conf-sync-001: Implementation Summary](./implementation-summary.md) - Documents which AC were satisfied

---

## Overview

This page documents acceptance criteria (AC) for all stories within Epic 001. AC define the conditions that must be met for each story to be considered complete.

**Epic Goal**: Provide complete Python library for Confluence Cloud integration with bidirectional content conversion and surgical XHTML updates.

**Total Stories**: 5

---

## Story Acceptance Criteria

### Story 1: Fetch Page as Markdown

**User Story**: As an agentic tool, I want to fetch a Confluence page as markdown, so that I can analyze and modify documentation content.

**Acceptance Criteria**:
- [x] **AC1**: `get_page_by_id()` returns page data with storage format (XHTML)
- [x] **AC2**: `get_page_by_title()` returns page data by space key + title
- [x] **AC3**: `xhtml_to_markdown()` converts XHTML to clean markdown
- [x] **AC4**: `PageSnapshot` contains both XHTML and markdown
- [x] **AC5**: Version number is captured for optimistic locking

**Definition of Done**:
- [x] Unit tests pass
- [x] E2E tests pass (test_confluence_fetch_journey.py)
- [x] Code review complete
- [x] Documentation updated

**Notes**: PageSnapshot is the primary interface for agents - provides XHTML for surgical updates and markdown for reading/editing.

---

### Story 2: Apply Surgical Updates

**User Story**: As an agentic tool, I want to apply surgical updates to a page, so that my changes don't destroy Confluence macros and formatting.

**Acceptance Criteria**:
- [x] **AC1**: `UPDATE_TEXT` operation replaces text content within elements
- [x] **AC2**: `DELETE_BLOCK` operation removes paragraphs, headings, list items
- [x] **AC3**: `INSERT_BLOCK` operation adds new block elements
- [x] **AC4**: `CHANGE_HEADING_LEVEL` operation modifies heading tags (h1-h6)
- [x] **AC5**: `TABLE_INSERT_ROW` operation adds rows to tables
- [x] **AC6**: `TABLE_DELETE_ROW` operation removes rows from tables
- [x] **AC7**: Confluence macros (ac: namespace) are never modified
- [x] **AC8**: Labels are preserved during updates
- [x] **AC9**: Local-id attributes are preserved on all elements

**Definition of Done**:
- [x] Unit tests pass (test_surgical_editor.py)
- [x] E2E tests pass (test_surgical_update_journey.py)
- [x] Code review complete
- [x] Documentation updated

**Notes**: Key insight - macros are preserved by never touching `ac:` elements, not by converting them to comments.

---

### Story 3: Create New Pages

**User Story**: As an agentic tool, I want to create new pages from markdown, so that I can generate documentation programmatically.

**Acceptance Criteria**:
- [x] **AC1**: `create_page()` creates page in specified space
- [x] **AC2**: `parent_id` parameter places page in hierarchy
- [x] **AC3**: Duplicate title detection prevents accidental overwrites
- [x] **AC4**: Returns `page_id` and `version` on success
- [x] **AC5**: Returns actionable error on failure

**Definition of Done**:
- [x] Unit tests pass
- [x] E2E tests pass (test_confluence_push_journey.py)
- [x] Code review complete
- [x] Documentation updated

**Notes**: Duplicate detection checks both via API and error message parsing (Confluence API returns different error formats).

---

### Story 4: Clear Error Messages

**User Story**: As a developer, I want clear error messages when API operations fail, so that I can debug issues quickly.

**Acceptance Criteria**:
- [x] **AC1**: `InvalidCredentialsError` for 401 responses with helpful message
- [x] **AC2**: `PageNotFoundError` for 404 responses with page ID
- [x] **AC3**: `PageAlreadyExistsError` for duplicate title on create
- [x] **AC4**: `VersionConflictError` for 409 responses with version info
- [x] **AC5**: `APIUnreachableError` for network/timeout errors
- [x] **AC6**: `APIAccessError` for other API failures
- [x] **AC7**: `ConversionError` for Pandoc failures

**Definition of Done**:
- [x] Unit tests pass (test_errors.py)
- [x] Code review complete
- [x] Documentation updated

**Notes**: All exceptions inherit from `ConfluenceError` for easy catching.

---

### Story 5: Rate Limit Handling

**User Story**: As a user syncing many pages, I want automatic rate limit handling, so that bulk operations complete without intervention.

**Acceptance Criteria**:
- [x] **AC1**: 429 responses trigger automatic retry
- [x] **AC2**: Exponential backoff: 1s, 2s, 4s delays
- [x] **AC3**: After max retries, raises `APIAccessError` with rate limit info
- [x] **AC4**: Retry-After header is respected when present

**Definition of Done**:
- [x] Unit tests pass (test_retry_logic.py)
- [x] Code review complete
- [x] Documentation updated

**Notes**: Implemented in `retry_logic.py`, used by `APIWrapper` for all HTTP calls.

---

## Epic-Level Acceptance Criteria

- [x] All stories complete and AC verified
- [x] Cross-story integration verified (E2E tests)
- [x] Performance targets met
- [x] Security requirements validated
- [x] Documentation complete

---

## Validation Checklist

### Functional Validation
- [x] All story AC verified in test environment
- [x] User workflows tested end-to-end
- [x] Edge cases handled appropriately
- [x] Error messages clear and actionable

### Non-Functional Validation
- [x] Performance benchmarks met (API calls optimized)
- [x] Security scan passed (no credentials in logs)
- [x] No `shell=True` in subprocess calls

### Quality Validation
- [x] Code coverage meets threshold (87% > 80% minimum)
- [x] No critical or high-severity bugs
- [x] Technical debt documented (consolidation complete)
- [x] API documentation in docstrings

---

**Contributors**: Product Owner, Architect
