# Architecture - ADR Summary

---

## Overview

Architecture Decision Records (ADRs) document significant technical decisions made during the development of confluence-bidir-sync. Each ADR captures the context, options considered, decision made, and consequences.

**Full ADRs**: `/docs/architecture/ADR/`

---

## ADR Index

| ADR | Date | Epic | Decision | Status |
|-----|------|------|----------|--------|
| [ADR-001](./ADR/ADR-001-typed-exceptions.md) | 2025-01-28 | Epic 01 | Typed Exception Hierarchy | Accepted |
| [ADR-002](./ADR/ADR-002-lazy-client-loading.md) | 2025-01-28 | Epic 01 | Lazy Client Loading | Accepted |
| [ADR-003](./ADR/ADR-003-lxml-parser.md) | 2025-01-28 | Epic 01 | lxml Parser for BeautifulSoup | Accepted |
| [ADR-004](./ADR/ADR-004-pandoc-subprocess.md) | 2025-01-28 | Epic 01 | Pandoc via Subprocess | Accepted |
| [ADR-005](./ADR/ADR-005-rate-limit-retry.md) | 2025-01-28 | Epic 01 | 429-Only Exponential Backoff | Accepted |
| [ADR-006](./ADR/ADR-006-macro-preservation.md) | 2025-01-29 | Epic 01 | Macro Preservation via Surgical Updates | Accepted |
| [ADR-007](./ADR/ADR-007-version-locking.md) | 2025-01-29 | Epic 01 | Optimistic Locking with Versions | Accepted |
| ADR-008 | 2025-02-03 | Epic 05 | ADF over XHTML for Surgical Updates | Accepted |
| ADR-009 | 2025-02-03 | Epic 05 | Baseline-Centric 3-Way Merge | Accepted |
| ADR-010 | 2025-02-03 | Epic 05 | Table-Aware Cell-Level Merge | Accepted |
| ADR-011 | 2025-02-03 | Epic 05 | Markdownify for HTML→Markdown | Accepted |
| ADR-012 | 2025-02-03 | Epic 05 | Line Break Format Conversion | Accepted |

---

## ADR Summaries

### ADR-001: Typed Exception Hierarchy

**Context**: Need precise error handling for different failure modes.

**Decision**: Create 7 typed exception classes inheriting from `ConfluenceError`, each with contextual attributes.

**Consequences**:
- (+) Callers can handle specific error types
- (+) Error messages include debugging context
- (-) More exception classes to maintain

---

### ADR-002: Lazy Client Loading

**Context**: Atlassian client validates credentials on construction.

**Decision**: Delay client instantiation until first API call.

**Consequences**:
- (+) Faster startup
- (+) Unit tests don't need valid credentials
- (-) First API call may be slower

---

### ADR-003: lxml Parser for BeautifulSoup

**Context**: Confluence XHTML uses XML namespaces (`ac:`, `ri:`).

**Decision**: Use lxml parser backend for BeautifulSoup instead of html.parser.

**Consequences**:
- (+) Proper namespace handling
- (+) Better performance
- (-) Additional dependency (lxml)

---

### ADR-004: Pandoc via Subprocess

**Context**: Need reliable XHTML↔markdown conversion.

**Decision**: Call Pandoc CLI via subprocess instead of Python bindings.

**Consequences**:
- (+) Most reliable conversion
- (+) Pandoc actively maintained
- (-) External dependency (user must install Pandoc)
- (-) Subprocess overhead

---

### ADR-005: 429-Only Exponential Backoff

**Context**: Need to handle Confluence rate limits gracefully.

**Decision**: Implement exponential backoff (1s, 2s, 4s) only for 429 responses; fail-fast for all other errors.

**Consequences**:
- (+) Respects rate limits automatically
- (+) Fails fast on real errors
- (-) May fail if rate limits persist beyond 3 retries

---

### ADR-006: Macro Preservation via Surgical Updates

**Context**: Confluence macros (`ac:` elements) must survive editing.

**Decision**: Preserve macros by never modifying `ac:` namespace elements in surgical operations.

**Consequences**:
- (+) Simpler than HTML comment approach
- (+) Macros always preserved
- (-) Can't modify macro content (acceptable limitation)

**Supersedes**: Initial HTML comment approach (moved to test helpers)

---

### ADR-007: Optimistic Locking with Versions

**Context**: Concurrent edits could overwrite changes.

**Decision**: Use Confluence's version numbers for optimistic locking; fail-fast on version mismatch.

**Consequences**:
- (+) Detects concurrent edits
- (+) No distributed locks needed
- (-) Requires version tracking by callers

---

### ADR-008: ADF over XHTML for Surgical Updates

**Context**: XHTML surgical updates use fragile position signatures that break when content shifts.

**Decision**: Prefer ADF format for surgical updates; ADF nodes have stable `localId` attributes for precise targeting.

**Consequences**:
- (+) Stable targeting via localId
- (+) Better macro preservation
- (-) Requires ADF API support
- (-) Fallback to XHTML still needed for some operations

---

### ADR-009: Baseline-Centric 3-Way Merge

**Context**: Comparing ADF/XHTML with markdown causes parser mismatch issues.

**Decision**: Use baseline markdown as source of truth; diff baseline vs. new markdown (same format).

**Consequences**:
- (+) Eliminates format mismatch issues
- (+) Accurate change detection
- (-) Requires baseline tracking per page

---

### ADR-010: Table-Aware Cell-Level Merge

**Context**: Line-based merge treats table rows as atomic units; changes to different cells in same row create false conflicts.

**Decision**: Normalize tables to cell-per-line format before merge3; unique context markers per cell.

**Consequences**:
- (+) Changes to different cells auto-merge
- (+) Preserves cell content with embedded newlines
- (-) Additional processing overhead
- (-) Table structure changes still conflict

---

### ADR-011: Markdownify for HTML→Markdown

**Context**: Pandoc produces complex table syntax; agents need clean pipe tables.

**Decision**: Use markdownify library for HTML→markdown; custom converter for Confluence-friendly output.

**Consequences**:
- (+) Clean pipe tables (`| col1 | col2 |`)
- (+) Configurable output style
- (-) Less comprehensive than Pandoc for edge cases

---

### ADR-012: Line Break Format Conversion

**Context**: Confluence stores multi-line table cells as `<p>` tags (XHTML) or `hardBreak` nodes (ADF); markdown uses `<br>` tags.

**Decision**: Convert between formats at boundaries:
- Confluence `<p>` → markdown `<br>` (on pull)
- Markdown `<br>` → Confluence `<p>` or `hardBreak` (on push)

**Consequences**:
- (+) Multi-line cells preserved through sync cycle
- (+) Markdown remains readable
- (-) Post-processing required on both directions

---

## Decision Categories

### By Quality Attribute

| Quality | ADRs |
|---------|------|
| **Reliability** | ADR-005, ADR-006, ADR-007, ADR-008, ADR-009 |
| **Maintainability** | ADR-001, ADR-002, ADR-010 |
| **Compatibility** | ADR-003, ADR-004, ADR-011, ADR-012 |

### By Component

| Component | ADRs |
|-----------|------|
| `confluence_client/` | ADR-001, ADR-002, ADR-005, ADR-007 |
| `content_converter/` | ADR-003, ADR-004, ADR-011, ADR-012 |
| `page_operations/` | ADR-006, ADR-008 |
| `git_integration/` | ADR-009, ADR-010 |

---

## ADR Template

When new architectural decisions are needed:

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
