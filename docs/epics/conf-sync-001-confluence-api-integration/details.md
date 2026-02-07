# conf-sync-001: Confluence API Integration & Surgical Updates

---

## Meta: Phase & Agent Information

**BMAD Phase**: Phase 1 - Agentic Planning (Complete)
**Agent Role**: Product Owner, Architect
**Created During**: Epic Implementation
**Prerequisites**: Product Strategy, Product Definition completed

---

## Strategic Alignment

**Related Product Strategy**: Enable agentic teams to work with Confluence documentation in markdown format while preserving Confluence's rich features.

**Strategic Goals Addressed**:
- G1: Bidirectional Sync - Foundation layer enabling local↔Confluence content flow
- G2: Content Preservation - Surgical updates preserve macros, labels, formatting
- G3: Error Handling - Typed exceptions for clear feedback to users and agents

**Product Decisions Applied**: Surgical XHTML updates (modify only what changed, never touch ac: elements)

---

## Context Dependencies

**Required Context (must exist before this document)**:
- Product Strategy: Vision, target markets, customer problems
- Product Definition: Use cases and capability map
- Product Reference: Feature catalog, terminology

**Provides Context For (documents that depend on this)**:
- [conf-sync-001: Architecture](./architecture.md) - Component design, data flow
- [conf-sync-001: Acceptance Criteria](./acceptance-criteria.md) - Story-level AC
- Epic 02 (File Structure & Mapping) - Builds on this foundation
- Epic 03 (Git Integration) - Uses page operations for merge support

---

## Epic Documentation

**Child Pages**:
- [conf-sync-001: Architecture](./architecture.md) - Component diagrams, data models, integration points
- [conf-sync-001: Acceptance Criteria](./acceptance-criteria.md) - Story-level AC and validation checklist
- [conf-sync-001: Test Strategy](./test-strategy.md) - Test types, boundaries, and coverage targets
- [conf-sync-001: ADR](./adr.md) - Architecture Decision Records index
- [conf-sync-001: File Plan](./file-plan.yaml) - File intent documentation
- [conf-sync-001: Implementation Summary](./implementation-summary.md) - What was built

---

## Epic Summary

**Goal**: Provide a complete Python library for Confluence Cloud integration with bidirectional content conversion and surgical XHTML updates that preserve all Confluence formatting.

**User Value**:
- Agentic teams can read/modify Confluence content in markdown format
- Scripts, linters, translators work on local markdown without destroying Confluence features
- Users continue using Confluence's rich editing while agents make surgical changes

**Technical Approach**:
- **API Layer**: `confluence_client/` provides HTTP client with authentication, error translation, and retry logic
- **Content Conversion**: `content_converter/` wraps Pandoc for XHTML↔markdown bidirectional conversion
- **Page Operations**: `page_operations/` provides high-level read/write/create with surgical update support
- **Key Insight**: Markdown is the editing surface; XHTML is source of truth surgically modified via discrete operations

## Tech Stack

| Component | Technology | Version | Rationale |
|-----------|-----------|---------|-----------|
| HTTP Client | atlassian-python-api | 4.0.7 | Well-maintained Confluence REST API wrapper |
| XHTML Parsing | BeautifulSoup4 + lxml | 4.14.3 / 5.3.0 | Industry standard, robust macro handling |
| Content Conversion | Pandoc | 3.8.3+ | Best-in-class markdown↔HTML conversion |
| Credentials | python-dotenv | 1.0.0 | Simple .env file loading |
| Testing | pytest + pytest-cov | - | Standard Python testing |

## Scope

### In Scope

- **API Layer**
  - Authentication via API token from .env
  - Fetch page by ID/title with storage format
  - List child pages
  - Create page with parent_id support
  - Update page with version management
  - Duplicate title detection
  - Exponential backoff for rate limits (429)
  - Version conflict detection (409)
  - 7 typed exception classes

- **Content Conversion**
  - XHTML to markdown (via Pandoc)
  - Markdown to XHTML (via Pandoc)
  - Macro preservation (ac: namespace elements never modified)

- **Page Operations (Surgical Updates)**
  - PageSnapshot with XHTML + markdown + metadata
  - 6 surgical operation types: UPDATE_TEXT, DELETE_BLOCK, INSERT_BLOCK, CHANGE_HEADING_LEVEL, TABLE_INSERT_ROW, TABLE_DELETE_ROW
  - Local-id attribute preservation
  - Label preservation
  - Version conflict handling

### Out of Scope

- Sync orchestration (push/pull commands) - Epic 06
- Local file system management - Epic 02
- Git merge integration - Epic 03
- Diff generation and analysis (caller provides operations)
- Page move operations (parent_id changes)
- Binary attachment synchronization

## User Stories

1. **As an** agentic tool, **I want** to fetch a Confluence page as markdown, **so that** I can analyze and modify documentation content.

2. **As an** agentic tool, **I want** to apply surgical updates to a page, **so that** my changes don't destroy Confluence macros and formatting.

3. **As an** agentic tool, **I want** to create new pages from markdown, **so that** I can generate documentation programmatically.

4. **As a** developer, **I want** clear error messages when API operations fail, **so that** I can debug issues quickly.

5. **As a** user syncing many pages, **I want** automatic rate limit handling, **so that** bulk operations complete without intervention.

**Implementation Order**: Stories 1→4→5→2→3 (API foundation first, then surgical updates)

## Dependencies

### Epic Dependencies

| Epic ID | Title | Relationship | Status |
|---------|-------|-------------|--------|
| N/A | Foundation epic | - | Complete |

### External Dependencies

- Confluence Cloud API access with valid API token
- Pandoc 3.8.3+ installed on system
- Network access to Confluence Cloud

## Success Criteria

**See**: [conf-sync-001: Acceptance Criteria](./acceptance-criteria.md) for detailed story-level AC

### Epic-Level Criteria

- [x] All stories complete with AC verified
- [x] Cross-story integration validated (E2E tests)
- [x] Performance targets met (API calls optimized)
- [x] Security requirements validated (no credentials in logs)
- [x] Documentation complete

## Key Metrics

| Metric | Target | Actual |
|--------|--------|--------|
| Unit test coverage | >90% | 87% |
| E2E test count | 10+ | 21 |
| Error types with actionable messages | 100% | 100% (7 types) |
| Round-trip fidelity for supported content | 100% | 100% |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pandoc conversion loses formatting | High | Macro preservation via surgical updates (never convert macros) |
| API rate limits block bulk sync | Medium | Exponential backoff implemented |
| Confluence storage format changes | High | Pin atlassian-python-api version |
| Content matching fails in surgical ops | Medium | Multiple strategies (exact, CSS selector) |

## Timeline

**Target Release**: 0.1.0

**Key Milestones**:
- [x] API layer complete (api_wrapper, auth, errors, retry_logic)
- [x] Content conversion complete (markdown_converter)
- [x] Surgical updates complete (surgical_editor, content_parser)
- [x] PageOperations orchestration complete
- [x] E2E tests passing

---

## Agent Ownership by Phase

| Phase | Agent Role | Responsibilities | Deliverables |
|-------|-----------|------------------|--------------|
| **Planning** | Product Owner | Define epic scope, user stories, strategic alignment | This document, Acceptance Criteria |
| **Architecture** | Architect | Design API layer, surgical editor, data models | Architecture doc, ADR |
| **Development** | Developer | Implement all modules, tests | Code, unit tests |
| **QA** | QA Engineer | Execute test strategy, E2E tests | Test results |
| **Completion** | Architect | Document consolidation decisions | Implementation Summary |

---

## Files

### Source (Final State After Consolidation)

```
src/
  confluence_client/           # API layer (4 files)
    __init__.py               # Public exports
    api_wrapper.py            # HTTP client with CRUD, error translation
    auth.py                   # Credential management from .env
    errors.py                 # 7 typed exception classes
    retry_logic.py            # Exponential backoff for 429s

  content_converter/           # Format conversion (1 file)
    __init__.py               # Exports MarkdownConverter
    markdown_converter.py     # Pandoc subprocess wrapper

  models/                      # Data structures
    __init__.py
    confluence_page.py        # ConfluencePage dataclass
    conversion_result.py      # ConversionResult dataclass

  page_operations/             # High-level operations (5 files)
    __init__.py               # Public exports
    page_operations.py        # Orchestration (get_page_snapshot, apply_operations, create_page)
    surgical_editor.py        # 6 operation types for XHTML modification
    content_parser.py         # XHTML/markdown block extraction
    models.py                 # PageSnapshot, SurgicalOperation, BlockType
```

### Tests

```
tests/
  unit/
    test_api_wrapper.py       # API wrapper unit tests
    test_auth.py              # Authentication tests
    test_errors.py            # Exception tests
    test_retry_logic.py       # Retry logic tests
    test_markdown_converter.py # Pandoc wrapper tests
    test_surgical_editor.py   # Surgical operation tests
    test_content_parser.py    # Block parsing tests
    test_macro_preserver.py   # Test helper for fetch journey tests

  e2e/
    test_confluence_fetch_journey.py   # Fetch + convert workflow
    test_confluence_push_journey.py    # Convert + push workflow
    test_surgical_update_journey.py    # Surgical update E2E

  helpers/
    macro_test_utils.py       # MacroPreserver test helper (OLD approach docs)
    confluence_test_setup.py  # Test page setup/teardown
```

---

## Implementation Notes

### Consolidation Decisions

During implementation, several redundant abstractions were removed:

1. **Removed from confluence_client/**:
   - `page_fetcher.py` - Thin wrapper around api_wrapper (use APIWrapper directly)
   - `page_updater.py` - Thin wrapper around api_wrapper (use APIWrapper directly)
   - `page_creator.py` - Thin wrapper around api_wrapper (use APIWrapper directly)

2. **Removed from content_converter/**:
   - `xhtml_parser.py` - Thin wrapper around BeautifulSoup (use BeautifulSoup directly)
   - `macro_preserver.py` - Moved to test helpers (OLD approach, surgical updates don't need it)

3. **Key Insight**: Surgical updates preserve macros by never touching `ac:` elements, not by converting them to HTML comments. The HTML comment approach was Epic 01's initial solution; surgical updates made it obsolete for production code.

### Macro Preservation Approaches

| Approach | Location | Used For |
|----------|----------|----------|
| **Surgical (Production)** | page_operations/ | Never modify ac: elements |
| **HTML Comments (Test Helper)** | tests/helpers/macro_test_utils.py | E2E fetch journey testing only |

---
