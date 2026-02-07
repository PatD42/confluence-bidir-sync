# Test Strategy - CONF-SYNC-007: Comprehensive Test Coverage

---

## Overview

This document defines the testing approach for implementing the test coverage gaps identified in Epic 007. Since this epic IS about testing, the strategy focuses on test infrastructure, patterns, and quality metrics.

---

## Test Levels

### Unit Tests (Already Addressed)

**Status**: 40 tests added in prior work

**Location**: `tests/unit/`

**Coverage**:
- `tests/unit/page_operations/test_adf_editor.py` - ADF `<br>`/hardBreak conversion
- `tests/unit/test_markdown_converter.py` - `<p>`/`<br>` format conversion
- `tests/unit/git_integration/test_table_merge.py` - Cell-level merge, separators

### Integration Tests (Gaps to Fill)

**Location**: `tests/integration/`

**New Test Files**:
```
tests/integration/
├── test_conflict_resolver_integration.py   # AC-5: ConflictResolver + TableMerge
├── test_adf_path_selection.py              # AC-6: ADF vs XHTML routing
├── test_version_conflict_handling.py       # AC-7: Version conflict recovery
├── test_baseline_merge_integration.py      # AC-9: Baseline in 3-way merge
└── test_error_recovery.py                  # AC-10: Error handling paths
```

**Characteristics**:
- No external API calls (mocked Confluence API)
- Real filesystem operations
- Tests component interactions
- Fast execution (<5s per test)

### E2E Tests (Critical Gaps)

**Location**: `tests/e2e/`

**New Test Files**:
```
tests/e2e/
├── test_adf_surgical_e2e.py                # AC-1: ADF surgical updates
├── test_line_break_roundtrip_e2e.py        # AC-2: Line break conversion
├── test_conflict_markers_e2e.py            # AC-3: Conflict resolution
├── test_macro_preservation_e2e.py          # AC-4: Macro survival
└── test_adf_fallback_e2e.py                # AC-8: Fallback paths
```

**Characteristics**:
- Real Confluence API calls
- Full sync workflow execution
- Slower execution (30-60s per test)
- Requires test credentials

---

## Test Infrastructure

### E2E Test Requirements

```python
# Required fixtures (in conftest.py)
@pytest.fixture(scope="function")
def test_credentials():
    """Load credentials from .env.test"""
    return get_test_credentials()

@pytest.fixture(scope="function")
def cleanup_test_pages():
    """Track pages for cleanup after test"""
    page_ids = []
    yield page_ids
    for page_id in reversed(page_ids):
        teardown_test_page(page_id)

@pytest.fixture(scope="function")
def synced_test_page(test_credentials, cleanup_test_pages, temp_test_dir):
    """Create page, sync to local, return context"""
    # ... setup code
```

### Mock Patterns for Integration Tests

```python
# Mock APIWrapper for integration tests
@pytest.fixture
def mock_api_wrapper():
    """Mock API wrapper with controlled responses"""
    with patch('src.confluence_client.api_wrapper.APIWrapper') as mock:
        instance = mock.return_value
        instance.get_page_by_id.return_value = {
            'id': '12345',
            'version': {'number': 1},
            'body': {'storage': {'value': '<p>Content</p>'}}
        }
        yield instance

# Mock for ADF API
@pytest.fixture
def mock_adf_api():
    """Mock ADF-specific API calls"""
    with patch.object(APIWrapper, 'get_page_adf') as mock_get:
        with patch.object(APIWrapper, 'update_page_adf') as mock_update:
            yield {'get': mock_get, 'update': mock_update}
```

---

## Test Data

### E2E Test Content Templates

```python
# Table with multi-line cells for line break tests
TABLE_WITH_BR = """
| Feature | Description |
|---------|-------------|
| Login | Users can<br>authenticate<br>securely |
| Dashboard | View<br>metrics |
"""

# Page with macro for preservation tests
PAGE_WITH_MACRO = """
<h1>Test Page</h1>
<p>Before macro</p>
<ac:structured-macro ac:name="toc"/>
<p>After macro</p>
"""

# Content for conflict tests
CONFLICT_BASE = """| Col1 | Col2 |
|------|------|
| A | B |
"""
CONFLICT_LOCAL = """| Col1 | Col2 |
|------|------|
| A-local | B |
"""
CONFLICT_REMOTE = """| Col1 | Col2 |
|------|------|
| A-remote | B |
"""
```

### Test Fixtures for ADF

```python
# ADF document with hardBreak nodes
ADF_WITH_HARDBREAK = {
    "type": "doc",
    "version": 1,
    "content": [
        {
            "type": "paragraph",
            "attrs": {"localId": "para-1"},
            "content": [
                {"type": "text", "text": "Line 1"},
                {"type": "hardBreak"},
                {"type": "text", "text": "Line 2"}
            ]
        }
    ]
}

# ADF document with macro
ADF_WITH_MACRO = {
    "type": "doc",
    "version": 1,
    "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "Before"}]},
        {
            "type": "extension",
            "attrs": {
                "extensionType": "com.atlassian.confluence.macro.core",
                "extensionKey": "toc",
                "localId": "macro-1"
            }
        },
        {"type": "paragraph", "content": [{"type": "text", "text": "After"}]}
    ]
}
```

---

## Test Execution Strategy

### Local Development

```bash
# Run all new tests
pytest tests/unit/page_operations/test_adf_editor.py \
       tests/unit/test_markdown_converter.py \
       tests/unit/git_integration/test_table_merge.py \
       tests/integration/test_conflict_resolver_integration.py \
       -v

# Run E2E tests (requires credentials)
pytest tests/e2e/test_adf_surgical_e2e.py -v --tb=short
```

### CI Pipeline

```yaml
# Suggested CI configuration
test:
  stages:
    - unit:
        script: pytest tests/unit/ -v --cov=src --cov-report=xml
        timeout: 5m

    - integration:
        script: pytest tests/integration/ -v -m integration
        timeout: 10m

    - e2e:
        script: pytest tests/e2e/ -v -m e2e
        timeout: 30m
        secrets:
          - CONFLUENCE_URL
          - CONFLUENCE_USER
          - CONFLUENCE_TOKEN
```

### Test Markers

```python
# In conftest.py or pytest.ini
pytest.mark.unit       # Unit tests (fast, no deps)
pytest.mark.integration # Integration tests (mocked API)
pytest.mark.e2e        # E2E tests (real Confluence)
pytest.mark.slow       # Tests taking >10s
```

---

## Coverage Requirements

### Minimum Coverage Targets

| Component | Target | Current | Gap |
|-----------|--------|---------|-----|
| `adf_editor.py` | 90% | 85% | 5% |
| `markdown_converter.py` | 90% | 80% | 10% |
| `table_merge.py` | 90% | 75% | 15% |
| `conflict_resolver.py` | 80% | 60% | 20% |
| `page_operations.py` | 80% | 70% | 10% |

### Coverage Measurement

```bash
# Generate coverage report
pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

# View coverage for specific module
pytest tests/ --cov=src/page_operations/adf_editor.py --cov-report=term-missing
```

---

## Test Quality Guidelines

### Assertion Best Practices

```python
# GOOD: Specific assertion with message
assert "hardBreak" in str(adf_content), \
    f"Expected hardBreak node in ADF, got: {adf_content}"

# BAD: Generic assertion
assert result  # What was expected?

# GOOD: Multiple focused assertions
assert result.success_count == 3
assert result.failure_count == 0
assert "AdminUser" in result.content

# BAD: Single assertion hiding multiple checks
assert result.success_count == 3 and result.failure_count == 0 and "AdminUser" in result.content
```

### Test Isolation

```python
# GOOD: Each test creates its own data
def test_scenario_a(self, temp_test_dir, cleanup_test_pages):
    page = create_test_page(...)  # Fresh page for this test
    cleanup_test_pages.append(page['page_id'])
    # ... test logic

# BAD: Tests sharing state
class TestSharedState:
    page_id = None  # Shared across tests - BAD!

    def test_create(self):
        self.page_id = create_page()

    def test_edit(self):
        edit_page(self.page_id)  # Depends on test_create running first
```

### Flaky Test Prevention

```python
# GOOD: Explicit waits with retry
def wait_for_confluence_index(api, page_id, expected_content, max_retries=5):
    for _ in range(max_retries):
        page = api.get_page_by_id(page_id)
        if expected_content in page['body']['storage']['value']:
            return True
        time.sleep(2)
    return False

# BAD: Fixed sleep
time.sleep(10)  # Hope Confluence is ready...
```

---

## Test Prioritization

### P0 (Must Have) - Block Release

1. AC-1.1: Edit uses ADF path
2. AC-1.2: BR converts to hardBreak
3. AC-2.1: Pull converts P to BR
4. AC-2.2: Push converts BR to P
5. AC-6.1: ADF path chosen

### P1 (Should Have) - Important

6. AC-3.1: Conflict markers written
7. AC-3.2: Cell-level auto-merge
8. AC-4.1: TOC macro preserved
9. AC-5.1: TableMerge integration
10. AC-7.1: Version conflict detected

### P2 (Nice to Have) - Enhancement

11. AC-8: Fallback tests
12. AC-10: Error recovery tests

---

## Success Criteria

### Epic Complete When

- [ ] All P0 tests implemented and passing
- [ ] All P1 tests implemented and passing
- [ ] Coverage targets met (90%+ for new features)
- [ ] No flaky tests in CI (3 consecutive green runs)
- [ ] Test documentation complete
