# conf-sync-001: Test Strategy

---

## Meta: Phase & Agent Information

**BMAD Phase**: Phase 2 - Context-Engineered Development (Architecture Sub-phase)
**Agent Role**: Architect, QA Engineer
**Created During**: Architecture Phase
**Prerequisites**: Epic Details, Architecture, Acceptance Criteria

---

## Context Dependencies

**Required Context (must exist before this document)**:
- [conf-sync-001: Epic Details](./details.md) - Scope, user stories
- [conf-sync-001: Architecture](./architecture.md) - Component boundaries
- [conf-sync-001: Acceptance Criteria](./acceptance-criteria.md) - What to validate

**Provides Context For (documents that depend on this)**:
- Development Phase: Test-first implementation
- QA Phase: Test execution plan
- Future Epics: Test patterns to follow

---

## Overview

This document defines the testing strategy for Epic 001: Confluence API Integration & Surgical Updates.

**Testing Philosophy**: Test at appropriate boundaries - unit tests for logic, E2E tests for integration with real Confluence.

**Coverage Target**: 90% for core library (achieved: 87%)

---

## Test Types

### 1. Unit Tests

**Purpose**: Fast, isolated tests with no external dependencies.

**Location**: `tests/unit/`

**Characteristics**:
- No network calls
- No file system access (except fixtures)
- Mocked external dependencies
- Sub-second execution

**What to Unit Test**:

| Component | Test Focus |
|-----------|------------|
| `api_wrapper.py` | Error translation, method signatures |
| `auth.py` | Credential loading from env |
| `errors.py` | Exception attributes, inheritance |
| `retry_logic.py` | Backoff timing, retry conditions |
| `markdown_converter.py` | Pandoc invocation (mocked subprocess) |
| `surgical_editor.py` | All 6 operation types on sample XHTML |
| `content_parser.py` | Block extraction for all block types |

**Mocking Strategy**:
- Mock `atlassian-python-api` Confluence client
- Mock `subprocess.run` for Pandoc calls
- Use sample XHTML fixtures for DOM operations

### 2. Integration Tests

**Purpose**: Test component interactions within the library.

**Location**: `tests/unit/` (co-located with unit tests)

**Characteristics**:
- Multiple components working together
- Still no external services
- May use real Pandoc if installed

**What to Integration Test**:

| Integration | Components |
|-------------|------------|
| PageOperations → APIWrapper | Orchestration calls correct API methods |
| PageOperations → MarkdownConverter | Conversion integrated in snapshot |
| PageOperations → SurgicalEditor | Operations applied before upload |

### 3. End-to-End Tests

**Purpose**: Validate complete workflows against real Confluence.

**Location**: `tests/e2e/`

**Characteristics**:
- Requires Confluence Cloud access
- Creates/modifies/deletes real pages
- Slower execution (network latency)
- Test space isolation

**What to E2E Test**:

| Journey | Validates |
|---------|-----------|
| Fetch Journey | API authentication, page fetch, XHTML retrieval, markdown conversion |
| Push Journey | Markdown to XHTML, page creation, duplicate detection, update with version |
| Surgical Journey | All 6 operation types, macro preservation, local-id preservation, version conflicts |

**Test Environment**:
```
CONFLUENCE_TEST_URL=https://test-instance.atlassian.net/wiki
CONFLUENCE_TEST_USER=test-email@company.com
CONFLUENCE_TEST_API_TOKEN=test-api-token
CONFLUENCE_TEST_SPACE=CONFSYNCTEST
```

---

## Test Boundaries

### Component Test Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                      E2E Test Boundary                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                 Integration Boundary                   │  │
│  │  ┌─────────────────┐  ┌─────────────────┐             │  │
│  │  │ Unit: API       │  │ Unit: Content   │             │  │
│  │  │ - api_wrapper   │  │ - converter     │             │  │
│  │  │ - auth          │  │ - parser        │             │  │
│  │  │ - errors        │  │ - editor        │             │  │
│  │  │ - retry         │  │                 │             │  │
│  │  └─────────────────┘  └─────────────────┘             │  │
│  │                                                        │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │ Integration: PageOperations                      │  │  │
│  │  │ - Orchestrates API + Converter + Editor          │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                               │
│                              ▼                               │
│                    ┌─────────────────┐                      │
│                    │ Confluence Cloud │                      │
│                    │ (Real API)       │                      │
│                    └─────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

### What NOT to Test

- Pandoc conversion accuracy (trust Pandoc, test our invocation)
- atlassian-python-api internals (trust library, test our usage)
- Confluence API behavior (trust Atlassian, test our error handling)

---

## Test Data Strategy

### Fixtures

**Location**: `tests/fixtures/`

| Fixture | Purpose |
|---------|---------|
| `sample_pages.py` | Pre-built XHTML samples with/without macros |
| `sample_markdown.py` | Pre-built markdown samples |
| `confluence_credentials.py` | Load test credentials from .env.test |

### Sample XHTML Patterns

```python
# Minimal page
MINIMAL_XHTML = "<p>Hello world</p>"

# Page with macro
PAGE_WITH_MACRO = """
<p>Before macro</p>
<ac:structured-macro ac:name="toc">
  <ac:parameter ac:name="maxLevel">3</ac:parameter>
</ac:structured-macro>
<p>After macro</p>
"""

# Page with local-ids
PAGE_WITH_LOCAL_IDS = """
<p ac:local-id="p1">First paragraph</p>
<p ac:local-id="p2">Second paragraph</p>
"""

# Complex page (headings, tables, lists)
COMPLEX_PAGE = """
<h1>Title</h1>
<p>Introduction</p>
<h2>Section</h2>
<ul><li>Item 1</li><li>Item 2</li></ul>
<table><tr><td>Cell</td></tr></table>
"""
```

### Test Page Lifecycle

```python
# tests/helpers/confluence_test_setup.py

def setup_test_page(space_key: str, title: str, content: str) -> str:
    """Create test page, return page_id."""

def teardown_test_page(page_id: str) -> None:
    """Delete test page (cleanup)."""
```

**Pattern**: Each E2E test creates its own page with unique title, cleans up after.

---

## Test Execution

### Running Tests

```bash
# All tests (requires Confluence access for E2E)
pytest

# Unit tests only (fast, no external deps)
pytest tests/unit/

# E2E tests only (requires Confluence)
pytest tests/e2e/

# Specific test file
pytest tests/unit/test_surgical_editor.py

# With coverage
pytest --cov=src --cov-report=html

# Verbose output
pytest -v
```

### CI/CD Integration

```yaml
# Unit tests (every commit)
- pytest tests/unit/ --cov=src

# E2E tests (nightly or manual trigger)
- pytest tests/e2e/ --tb=short
```

### Test Markers

```python
# Mark E2E tests that require Confluence
@pytest.mark.e2e
@pytest.mark.requires_confluence

# Mark slow tests
@pytest.mark.slow

# Skip if Pandoc not installed
@pytest.mark.skipif(not pandoc_installed(), reason="Pandoc required")
```

---

## Coverage Requirements

### Module Coverage Targets

| Module | Target | Rationale |
|--------|--------|-----------|
| `confluence_client/` | 90% | Core API layer |
| `content_converter/` | 85% | Pandoc wrapper (limited branching) |
| `page_operations/` | 90% | Orchestration logic |
| `models/` | 80% | Data classes (minimal logic) |

### Coverage Exclusions

```ini
# pyproject.toml or .coveragerc
[coverage:run]
omit =
    tests/*
    */__init__.py
```

---

## Error Scenario Testing

### API Errors

| Scenario | Test | Expected |
|----------|------|----------|
| Invalid credentials | Mock 401 response | `InvalidCredentialsError` |
| Page not found | Mock 404 response | `PageNotFoundError` |
| Rate limited | Mock 429 response | Retry with backoff |
| Rate limit exhausted | Mock 429 x4 | `APIAccessError` |
| Network timeout | Mock timeout | `APIUnreachableError` |
| Version conflict | Mock 409 response | `VersionConflictError` |

### Conversion Errors

| Scenario | Test | Expected |
|----------|------|----------|
| Pandoc not installed | Mock subprocess failure | `ConversionError` |
| Invalid XHTML | Pass malformed HTML | Graceful handling |
| Empty content | Pass empty string | Empty markdown |

### Surgical Operation Errors

| Scenario | Test | Expected |
|----------|------|----------|
| Target not found | UPDATE_TEXT with no match | No-op (graceful) |
| Invalid heading level | CHANGE_HEADING_LEVEL h7 | Validation error |
| Table row out of bounds | TABLE_DELETE_ROW index -1 | Validation error |

---

## Regression Testing

### Critical Paths

These paths must always pass:

1. **Fetch Path**: `get_page_snapshot()` returns valid PageSnapshot
2. **Update Path**: `apply_operations()` modifies page without corruption
3. **Create Path**: `create_page()` creates page with correct content
4. **Macro Preservation**: ac: elements never modified

### Regression Test Suite

```bash
# Run critical path tests
pytest tests/e2e/ -k "journey" -v
```

---

## Performance Testing

### Benchmarks

| Operation | Target | Measurement |
|-----------|--------|-------------|
| Single page fetch | <2s | E2E test timing |
| Single page update | <3s | E2E test timing |
| Pandoc conversion | <1s | Unit test timing |
| Surgical operation (single) | <10ms | Unit test timing |

### Performance Test Pattern

```python
import time

def test_fetch_performance():
    start = time.time()
    snapshot = page_ops.get_page_snapshot(page_id)
    elapsed = time.time() - start
    assert elapsed < 2.0, f"Fetch took {elapsed}s, expected <2s"
```

---

## Cross-Epic Test Evolution

### Tests Reusable by Future Epics

| Test Asset | Reuse In |
|------------|----------|
| `confluence_test_setup.py` | All epics needing test pages |
| `sample_pages.py` fixtures | Epics 02-06 |
| API error mocking patterns | Epics 02-06 |

### Tests to Extend

| Epic | Extension |
|------|-----------|
| Epic 02 (File Mapping) | Add file system fixtures, path assertions |
| Epic 03 (Git Integration) | Add git repo fixtures, merge conflict tests |
| Epic 06 (Sync Orchestration) | Add multi-page journey tests |

---

## Test Maintenance

### When to Update Tests

- New acceptance criteria added
- Bug fix requires regression test
- Refactoring changes internal APIs
- New error conditions discovered

### Test Review Checklist

- [ ] Tests follow AAA pattern (Arrange, Act, Assert)
- [ ] Fixtures are reusable
- [ ] E2E tests clean up after themselves
- [ ] Error messages are helpful for debugging
- [ ] Coverage maintained or improved

---

**Contributors**: Architect, QA Engineer
