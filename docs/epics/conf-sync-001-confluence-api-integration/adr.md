# conf-sync-001: Architecture Decision Records

---

## Meta: Phase & Agent Information

**BMAD Phase**: Phase 2 - Context-Engineered Development (Architecture Sub-phase)
**Agent Role**: Architect
**Created During**: Architecture Phase - Decision Documentation
**Prerequisites**: Epic Details, System Context

---

## Context Dependencies

**Required Context (must exist before this document)**:
- [conf-sync-001: Epic Details](./details.md) - Scope and constraints
- [conf-sync-001: Architecture](./architecture.md) - Component design

**Provides Context For (documents that depend on this)**:
- Development Phase: Developers follow these decisions
- Future Epics: Build on established patterns
- Maintenance: Understand why things are built this way

---

## Overview

This document indexes Architecture Decision Records (ADRs) for Epic 001. Full ADR content is maintained in the global ADR directory for cross-epic reference.

**ADR Location**: `/docs/architecture/ADR/`

---

## Epic 001 ADRs

### ADR-001: Typed Exception Hierarchy

**Status**: Accepted
**Decision**: Create 7 typed exception classes inheriting from `ConfluenceError`
**Rationale**: Enable precise error handling; each error type has actionable information
**Link**: [ADR-001-typed-exceptions.md](../../architecture/ADR/ADR-001-typed-exceptions.md)

**Impact on Epic**:
- `errors.py` implements full hierarchy
- All API methods raise typed exceptions
- Unit tests verify exception attributes

---

### ADR-002: Lazy Client Loading

**Status**: Accepted
**Decision**: Load Confluence client lazily on first API call, not at import
**Rationale**: Faster startup; credentials only needed when actually used
**Link**: [ADR-002-lazy-client-loading.md](../../architecture/ADR/ADR-002-lazy-client-loading.md)

**Impact on Epic**:
- `APIWrapper.__init__()` doesn't connect
- First method call triggers authentication
- Unit tests can run without credentials

---

### ADR-003: lxml Parser for BeautifulSoup

**Status**: Accepted
**Decision**: Use lxml parser backend for BeautifulSoup
**Rationale**: Faster, more lenient with malformed HTML, handles Confluence XHTML quirks
**Link**: [ADR-003-lxml-parser.md](../../architecture/ADR/ADR-003-lxml-parser.md)

**Impact on Epic**:
- `BeautifulSoup(xhtml, 'lxml')` everywhere
- `lxml` added to dependencies
- Handles Confluence's non-standard XHTML

---

### ADR-004: Pandoc via Subprocess

**Status**: Accepted
**Decision**: Call Pandoc CLI via subprocess, not Python bindings
**Rationale**: Pandoc bindings are less maintained; CLI is stable and well-documented
**Link**: [ADR-004-pandoc-subprocess.md](../../architecture/ADR/ADR-004-pandoc-subprocess.md)

**Impact on Epic**:
- `markdown_converter.py` uses `subprocess.run()`
- No `shell=True` (security)
- Requires Pandoc installed on system

---

### ADR-005: Exponential Backoff for Rate Limits

**Status**: Accepted
**Decision**: Implement exponential backoff (1s, 2s, 4s) for 429 responses only
**Rationale**: Respect Confluence rate limits; fail fast for other errors
**Link**: [ADR-005-rate-limit-retry.md](../../architecture/ADR/ADR-005-rate-limit-retry.md)

**Impact on Epic**:
- `retry_logic.py` implements backoff
- Only 429 triggers retry
- Max 3 retries before failure

---

### ADR-006: Macro Preservation via Surgical Updates

**Status**: Accepted (supersedes initial HTML comment approach)
**Decision**: Preserve macros by never modifying `ac:` namespace elements
**Rationale**: Simpler, more reliable than comment-based preservation
**Link**: [ADR-006-macro-preservation.md](../../architecture/ADR/ADR-006-macro-preservation.md)

**Impact on Epic**:
- `surgical_editor.py` skips ac: elements
- No macro-to-comment conversion needed
- Macros survive all operations implicitly

---

### ADR-007: Optimistic Locking with Version Numbers

**Status**: Accepted
**Decision**: Use Confluence's version number for optimistic locking on updates
**Rationale**: Detect concurrent edits; prevent accidental overwrites
**Link**: [ADR-007-version-locking.md](../../architecture/ADR/ADR-007-version-locking.md)

**Impact on Epic**:
- `PageSnapshot.version` captures current version
- `apply_operations()` checks version before update
- 409 response → `VersionConflictError`

---

## Consolidation Decisions (Implementation Phase)

These decisions were made during implementation, not formal ADRs:

### CD-001: Remove Wrapper Classes

**Decision**: Remove `page_fetcher.py`, `page_updater.py`, `page_creator.py`
**Rationale**: Thin wrappers added no value; use `APIWrapper` directly
**Status**: Implemented

### CD-002: Remove XHTML Parser Wrapper

**Decision**: Remove `xhtml_parser.py`, use BeautifulSoup directly
**Rationale**: Wrapper added no value; BeautifulSoup API is simple enough
**Status**: Implemented

### CD-003: Move MacroPreserver to Test Helpers

**Decision**: Move `macro_preserver.py` to `tests/helpers/macro_test_utils.py`
**Rationale**: HTML comment approach obsolete for production; useful for E2E test verification
**Status**: Implemented

---

## ADR Template for Future Decisions

When new architectural decisions are needed, use this template:

```markdown
# ADR-NNN: [Title]

## Status
[Proposed | Accepted | Deprecated | Superseded by ADR-XXX]

## Context
[What is the issue we're facing?]

## Decision
[What decision was made?]

## Rationale
[Why was this decision made?]

## Consequences
[What are the positive and negative consequences?]

## Alternatives Considered
[What other options were evaluated?]
```

---

## Decision Log

| ADR | Date | Status | Decision |
|-----|------|--------|----------|
| ADR-001 | 2025-01-28 | Accepted | Typed exception hierarchy |
| ADR-002 | 2025-01-28 | Accepted | Lazy client loading |
| ADR-003 | 2025-01-28 | Accepted | lxml parser for BeautifulSoup |
| ADR-004 | 2025-01-28 | Accepted | Pandoc via subprocess |
| ADR-005 | 2025-01-28 | Accepted | Exponential backoff for rate limits |
| ADR-006 | 2025-01-29 | Accepted | Macro preservation via surgical updates |
| ADR-007 | 2025-01-29 | Accepted | Optimistic locking with versions |

---

**Contributors**: Architect
