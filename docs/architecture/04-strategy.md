# Architecture - Solution Strategy

---

## Technology Decisions

| Decision Area | Choice | Rationale |
|--------------|--------|-----------|
| **Language** | Python 3.9+ | Broad compatibility, rich ecosystem, agentic tool friendly |
| **API Client** | atlassian-python-api | Well-maintained, official-ish Confluence REST wrapper |
| **XHTML Parsing** | BeautifulSoup4 + lxml | Industry standard; lxml handles XML namespaces (`ac:`) |
| **HTML→Markdown** | markdownify | Clean pipe tables; customizable for Confluence-specific handling |
| **Markdown→HTML** | Pandoc subprocess | Most reliable conversion; no Python bindings needed |
| **3-Way Merge** | merge3 library | Python implementation of diff3; cell-level customization possible |
| **Credentials** | python-dotenv | Simple, standard .env file loading |

## Architecture Patterns

### Primary Patterns

- **Layered Architecture**: Clear separation between API client, content conversion, and page operations
- **Repository Pattern**: `APIWrapper` abstracts all Confluence API interactions
- **Strategy Pattern**: Surgical operations are discrete, composable units
- **Fail-Fast**: Non-retryable errors fail immediately; only 429 rate limits trigger retry

### Design Principles

1. **Never corrupt source data**: Macros (`ac:` elements) are never modified by surgical operations
2. **Explicit over implicit**: Typed exceptions, explicit version numbers, clear operation results
3. **Composition over inheritance**: Small, focused modules composed by `PageOperations`
4. **Defense in depth**: Validate at boundaries (API responses, subprocess output, user input)
5. **Baseline as source of truth**: 3-way merge uses baseline content to avoid format mismatch
6. **Graceful degradation**: Fall back to full replacement if surgical operations fail

## High-Level Structure

### Layers

```
┌─────────────────────────────────────────────────────┐
│              Application Layer                       │
│         (PageOperations - Orchestration)            │
├─────────────────────────────────────────────────────┤
│              Domain Layer                            │
│  ┌────────────────┐  ┌────────────────┐            │
│  │ SurgicalEditor │  │ AdfEditor      │            │
│  │ (XHTML)        │  │ (ADF)          │            │
│  └────────────────┘  └────────────────┘            │
│  ┌────────────────┐  ┌────────────────┐            │
│  │ ContentParser  │  │ DiffAnalyzer   │            │
│  │ (Extraction)   │  │ (Comparison)   │            │
│  └────────────────┘  └────────────────┘            │
├─────────────────────────────────────────────────────┤
│           Git Integration Layer                      │
│  ┌────────────────────────────────────────────────┐ │
│  │ TableMerge (Cell-level 3-way merge)            │ │
│  └────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│           Infrastructure Layer                       │
│  ┌──────────────────┐  ┌────────────────────────┐  │
│  │ confluence_client│  │ content_converter      │  │
│  │ (API + Auth)     │  │ (markdownify + Pandoc) │  │
│  └──────────────────┘  └────────────────────────┘  │
├─────────────────────────────────────────────────────┤
│              External Systems                        │
│   Confluence Cloud API + ADF  │  Pandoc  │  merge3  │
└─────────────────────────────────────────────────────┘
```

### Key Subsystems

| Subsystem | Responsibility |
|-----------|---------------|
| **confluence_client/** | API authentication, HTTP client, error translation, retry logic |
| **content_converter/** | Bidirectional XHTML↔markdown via markdownify + Pandoc |
| **page_operations/** | High-level orchestration, XHTML surgical editing, ADF surgical editing, content parsing, diff analysis |
| **git_integration/** | Table-aware 3-way merge, baseline management |
| **models/** | Shared data structures (PageSnapshot, SurgicalOperation, AdfDocument, etc.) |

## Quality Goals Achievement

| Quality Goal | Architectural Approach |
|--------------|----------------------|
| **Reliability** | Surgical updates never touch `ac:` elements; version locking prevents overwrites; typed exceptions for clear failure modes |
| **Maintainability** | Layered architecture; single responsibility per module; comprehensive type hints; >80% test coverage |
| **Usability** | `PageSnapshot` provides both XHTML and markdown; clear API for common operations; actionable error messages |
| **Security** | Credentials from .env (never hardcoded); no `shell=True`; `requests` pinned for CVE mitigations |

## Key Architectural Decisions

| ADR | Decision | Key Rationale |
|-----|----------|---------------|
| ADR-001 | Typed Exception Hierarchy | Enable precise error handling with context |
| ADR-002 | Lazy Client Loading | Delay credential validation until needed |
| ADR-003 | lxml Parser | Proper XML namespace handling for `ac:` |
| ADR-004 | Pandoc Subprocess | Most reliable markdown→HTML conversion |
| ADR-005 | 429-Only Retry | Fail-fast for non-transient errors |
| ADR-006 | Surgical Updates | Preserve macros by never modifying them |
| ADR-007 | Optimistic Locking | Detect conflicts via version numbers |
| ADR-008 | ADF over XHTML | Stable localId targeting vs. fragile position signatures |
| ADR-009 | Baseline-Centric Merge | Same-format diffing eliminates parser mismatch |
| ADR-010 | Cell-Level Table Merge | Avoid false conflicts for different cells in same row |
| ADR-011 | Markdownify for HTML→MD | Clean pipe tables for agentic tools |
| ADR-012 | Line Break Conversion | Preserve multi-line cells through sync cycle |

---
