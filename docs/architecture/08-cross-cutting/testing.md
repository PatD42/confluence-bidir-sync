# Cross-Cutting - Testing

---

## Test Levels

### Unit Tests

**Location**: `tests/unit/`

**Characteristics**:
- Fast execution (<1s per test)
- No external dependencies
- Mocked API calls, subprocess
- Run anywhere, anytime

**Coverage Target**: 90%

**What to Test**:
- Error translation logic
- Retry backoff timing
- Surgical operation correctness
- Content block extraction
- Data class validation

### Integration Tests

**Location**: `tests/integration/` (planned)

**Characteristics**:
- Real Pandoc subprocess
- Mocked Confluence API
- Tests conversion pipeline

**What to Test**:
- XHTML → Markdown → XHTML round-trip
- Macro placeholder handling
- Complex document conversion

### End-to-End Tests

**Location**: `tests/e2e/`

**Characteristics**:
- Real Confluence Cloud API
- Real Pandoc subprocess
- Uses `CONFSYNCTEST` space
- Slower execution (network)

**Test Space**: `CONFSYNCTEST` (dedicated test space)

**What to Test**:
- Full fetch journey
- Full push journey
- Surgical update with macros
- Version conflict detection

### Contract Tests (Planned)

**Purpose**: Validate against Confluence API contract

**What to Test**:
- API response structure matches expectations
- Error response formats
- Required fields present

## Coverage Targets

| Module | Target | Current |
|--------|--------|---------|
| `confluence_client/` | 90% | 87% |
| `content_converter/` | 85% | 85% |
| `page_operations/` | 90% | 88% |
| `models/` | 80% | 80% |
| **Overall** | **80%** | **87%** |

## Test Data Management

### Fixtures

**Location**: `tests/fixtures/`

| Fixture | Purpose |
|---------|---------|
| `sample_pages.py` | Pre-built XHTML samples |
| `sample_markdown.py` | Pre-built markdown samples |
| `confluence_credentials.py` | Load test credentials |

### Sample XHTML Patterns

```python
# tests/fixtures/sample_pages.py

MINIMAL_XHTML = "<p>Hello world</p>"

PAGE_WITH_MACRO = """
<p>Before macro</p>
<ac:structured-macro ac:name="toc">
  <ac:parameter ac:name="maxLevel">3</ac:parameter>
</ac:structured-macro>
<p>After macro</p>
"""

PAGE_WITH_LOCAL_IDS = """
<p ac:local-id="p1">First paragraph</p>
<p ac:local-id="p2">Second paragraph</p>
"""

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
    # Creates page in CONFSYNCTEST space
    # Returns page_id for test use

def teardown_test_page(page_id: str) -> None:
    """Delete test page (cleanup)."""
    # Always called in finally block
```

### Test Naming Convention

```
test_<function>_<scenario>_<expected>
```

Examples:
- `test_get_page_by_id_valid_id_returns_page`
- `test_get_page_by_id_invalid_id_raises_not_found`
- `test_apply_operations_with_macros_preserves_macros`

## Mocking Strategy

### API Mocking

```python
# Unit tests mock atlassian-python-api
@pytest.fixture
def mock_confluence(mocker):
    mock = mocker.MagicMock()
    mocker.patch('confluence_client.api_wrapper.Confluence', return_value=mock)
    return mock

def test_get_page_by_id(mock_confluence):
    mock_confluence.get_page_by_id.return_value = {"id": "123", "title": "Test"}
    api = APIWrapper(authenticator)
    result = api.get_page_by_id("123")
    assert result["title"] == "Test"
```

### Subprocess Mocking

```python
# Unit tests mock Pandoc subprocess
@pytest.fixture
def mock_pandoc(mocker):
    mock_result = mocker.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "# Heading\n\nParagraph"
    mocker.patch('subprocess.run', return_value=mock_result)
    return mock_result
```

### Response Fixtures

```python
# tests/fixtures/api_responses.py

PAGE_RESPONSE = {
    "id": "12345",
    "type": "page",
    "status": "current",
    "title": "Test Page",
    "space": {"key": "TEAM"},
    "body": {
        "storage": {
            "value": "<p>Content</p>",
            "representation": "storage"
        }
    },
    "version": {"number": 1}
}

ERROR_404 = {
    "statusCode": 404,
    "message": "Page not found"
}
```

## Test Execution

### Running Tests

```bash
# All tests
pytest

# Unit tests only (fast)
pytest tests/unit/

# E2E tests only (requires Confluence)
pytest tests/e2e/

# With coverage report
pytest --cov=src --cov-report=html

# Verbose output
pytest -v

# Specific test file
pytest tests/unit/test_surgical_editor.py

# Specific test
pytest tests/unit/test_surgical_editor.py::test_update_text_preserves_macros
```

### Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=src --cov-report=html

# View report
open htmlcov/index.html
```

### Test Markers

```python
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
markers = [
    "e2e: End-to-end tests requiring Confluence",
    "slow: Tests that take >1 second",
    "integration: Integration tests with real Pandoc",
]
```

```bash
# Run only E2E tests
pytest -m e2e

# Skip slow tests
pytest -m "not slow"
```

## Test Environment

### Required for Unit Tests

- Python 3.9+
- pytest, pytest-cov, pytest-mock

### Required for E2E Tests

- Pandoc 3.8.3+
- Confluence Cloud access
- `CONFSYNCTEST` space with edit permissions
- Test credentials in `.env.test`

### Test Credentials

```bash
# .env.test
CONFLUENCE_TEST_URL=https://test-instance.atlassian.net/wiki
CONFLUENCE_TEST_USER=test-email@company.com
CONFLUENCE_TEST_API_TOKEN=test-api-token
CONFLUENCE_TEST_SPACE=CONFSYNCTEST
```

---
