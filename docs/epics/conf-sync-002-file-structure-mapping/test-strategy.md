# Test Strategy - CONF-SYNC-002

---

## Overview

Testing approach for File Structure & Mapping epic.

**Test Philosophy**: High coverage for file operations (data integrity critical), comprehensive E2E tests for user workflows.

---

## Test Levels

### Unit Tests (pytest)

**Target Coverage**: >90% for all file_mapper modules

| Module | Coverage Target | Key Test Areas |
|--------|-----------------|----------------|
| `filesafe_converter.py` | 100% | All special char conversions, edge cases |
| `frontmatter_handler.py` | 100% | Valid/invalid YAML, missing fields, types |
| `config_loader.py` | 100% | Load, validate, save, defaults, errors |
| `hierarchy_builder.py` | >90% | CQL parsing, tree building, limit checks |
| `file_mapper.py` | >90% | Orchestration, error handling, atomicity |

**Unit Test Requirements**:
```python
# tests/unit/file_mapper/test_filesafe_converter.py
def test_title_to_filename_basic():
    """Test basic space-to-hyphen conversion."""
    assert title_to_filename("Customer Feedback") == "Customer-Feedback.md"

def test_title_to_filename_colon():
    """Test colon-to-double-dash conversion."""
    assert title_to_filename("API: Getting Started") == "API--Getting-Started.md"

def test_title_to_filename_case_preservation():
    """Test case is preserved."""
    assert title_to_filename("iOS Setup") == "iOS-Setup.md"

def test_title_to_filename_special_chars():
    """Test Q&A becomes Q-A."""
    assert title_to_filename("Q&A Session") == "Q-A-Session.md"

def test_title_to_filename_multiple_hyphens():
    """Test multiple hyphens are collapsed."""
    # Implementation should handle this edge case
```

---

### Integration Tests (pytest)

**Target**: Test interactions between components and external systems.

| Test | Description | External Dependencies |
|------|-------------|----------------------|
| **IT-1: CQL Query** | Execute real CQL query against test space | Confluence test instance |
| **IT-2: File Write/Read** | Write files with frontmatter, read back | Filesystem (temp dir) |
| **IT-3: Config Persistence** | Save config to YAML, load back | Filesystem (temp dir) |
| **IT-4: Atomic Operations** | Simulate failure during multi-file write | Filesystem (temp dir) |
| **IT-5: YAML Parsing** | Parse various YAML frontmatter formats | PyYAML library |

**Integration Test Requirements**:
```python
# tests/integration/test_cql_queries.py
@pytest.mark.integration
def test_cql_query_children(confluence_test_client):
    """Test CQL query returns expected child pages."""
    builder = HierarchyBuilder(confluence_test_client)
    children = builder.query_children(parent_page_id="TEST_PAGE_ID")

    assert len(children) > 0
    assert all("page_id" in child for child in children)
    assert all("title" in child for child in children)
    assert all("version_when" in child for child in children)

# tests/integration/test_file_operations.py
@pytest.mark.integration
def test_atomic_write_rollback(tmp_path):
    """Test that failed write rolls back all files."""
    mapper = FileMapper(test_config, mock_api)

    # Simulate failure during write
    with patch('file_mapper.write_page') as mock_write:
        mock_write.side_effect = [None, None, IOError("Disk full")]

        with pytest.raises(FilesystemError):
            mapper.write_pages_atomic(test_pages)

    # Verify no files were created
    assert len(list(tmp_path.glob("*.md"))) == 0
```

---

### E2E Tests (pytest)

**Target**: Test complete user workflows end-to-end.

From acceptance criteria, 6 E2E scenarios:

#### E2E-1: Full Pull Sync (Confluence → Local)

**Setup**:
1. Test Confluence space with 15 pages in 3-level hierarchy
2. Empty local folder
3. Valid config file

**Execute**: Run FileMapper.discover_pages() + write_page_to_local()

**Verify**:
- 15 markdown files created
- Correct hierarchy (folders match parent-child)
- All frontmatter has pageIDs
- Filesafe names match Confluence titles
- No .confluence-sync/temp/ files remain

```python
@pytest.mark.e2e
def test_full_pull_sync(confluence_test_space, tmp_path):
    """E2E-1: Pull 15 pages from Confluence to local."""
    # Setup
    config = create_test_config(space="TEST", parent="ROOT_PAGE_ID", local=tmp_path)
    mapper = FileMapper(config, real_api_wrapper)

    # Execute
    pages = mapper.discover_pages()
    assert len(pages) == 15  # Assuming test space has 15 pages

    for page in pages:
        content = fetch_markdown_content(page)
        mapper.write_page_to_local(page, content)

    # Verify
    md_files = list(tmp_path.rglob("*.md"))
    assert len(md_files) == 15

    # Verify frontmatter
    for file_path in md_files:
        local_page = mapper.read_page_from_local(file_path)
        assert local_page.page_id is not None
        assert local_page.space_key == "TEST"
```

#### E2E-2: Full Push Sync (Local → Confluence)

**Setup**:
1. Local folder with 10 markdown files (no pageIDs in frontmatter)
2. Confluence parent page has no children
3. Valid config file

**Execute**: Create pages in Confluence, update frontmatter with pageIDs

**Verify**:
- 10 pages created in Confluence
- Hierarchy matches folder structure
- Frontmatter updated with pageIDs
- Page titles match filesafe conversion

```python
@pytest.mark.e2e
def test_full_push_sync(confluence_test_space, tmp_path):
    """E2E-2: Push 10 local files to Confluence."""
    # Setup: Create 10 markdown files without pageIDs
    create_test_markdown_files(tmp_path, count=10)

    config = create_test_config(space="TEST", parent="EMPTY_PARENT", local=tmp_path)
    mapper = FileMapper(config, real_api_wrapper)

    # Execute
    local_pages = mapper.scan_local_files()
    assert len(local_pages) == 10
    assert all(p.page_id is None for p in local_pages)  # No pageIDs yet

    for local_page in local_pages:
        # Create page in Confluence (via PageOperations from Epic 001)
        created_page = page_operations.create_page(...)
        # Update frontmatter with new pageID
        mapper.update_frontmatter(local_page.file_path, page_id=created_page.page_id)

    # Verify
    updated_pages = mapper.scan_local_files()
    assert all(p.page_id is not None for p in updated_pages)
```

#### E2E-3: Bidirectional Sync with Changes

**Setup**:
1. 5 pages already synced (local + Confluence)
2. Edit 2 local files (different content)
3. Edit 2 Confluence pages (different pages, no conflict)

**Execute**: Detect changes, push local changes, pull remote changes

**Verify**:
- Local changes pushed to Confluence
- Remote changes pulled to local
- No conflicts (different pages modified)

#### E2E-4: Title Change Detection

**Setup**:
1. Confluence page "Old Name" synced to "Old-Name.md"
2. Rename Confluence page to "New Name"

**Execute**: Detect title change, rename local file

**Verify**:
- Local file renamed to "New-Name.md"
- Frontmatter updated with new title
- Old file "Old-Name.md" deleted

```python
@pytest.mark.e2e
def test_title_change_detection(confluence_test_space, tmp_path):
    """E2E-4: Detect and handle page title change."""
    # Setup
    page_id = "12345"
    old_title = "Old Name"
    new_title = "New Name"

    # Create initial file
    old_path = tmp_path / "Old-Name.md"
    write_test_file(old_path, page_id=page_id, title=old_title)

    # Simulate Confluence title change
    update_confluence_page_title(page_id, new_title)

    # Execute
    config = create_test_config(...)
    mapper = FileMapper(config, real_api_wrapper)

    remote_pages = mapper.discover_pages()
    local_pages = mapper.scan_local_files()

    # Detect title mismatch
    for remote_page in remote_pages:
        local_page = find_local_by_page_id(local_pages, remote_page.page_id)
        if local_page and local_page.title != remote_page.title:
            new_path = mapper.rename_local_file(local_page.file_path, remote_page.title)

    # Verify
    assert not old_path.exists()
    new_path = tmp_path / "New-Name.md"
    assert new_path.exists()

    local_page = mapper.read_page_from_local(new_path)
    assert local_page.title == new_title
```

#### E2E-5: Exclusion Pattern

**Setup**:
1. Confluence hierarchy with "Archives" page (pageID 67890)
2. Config excludes pageID 67890
3. Archives has 3 child pages

**Execute**: Discover pages with exclusion

**Verify**:
- Archives page NOT in discovered pages
- Archives descendants NOT in discovered pages
- Other pages discovered normally

#### E2E-6: Page Limit Exceeded

**Setup**:
1. Confluence parent has 100 child pages (at limit)
2. Valid config

**Execute**: Attempt to discover pages

**Verify**:
- Error raised: PageLimitExceededError
- Error message mentions 100 page limit
- No local files created (failed before sync)

---

## Test Data Management

### Test Space Requirements

**Confluence Test Space**: `CONFSYNCTEST`

Required test pages:
```
Root (TEST_ROOT_PAGE)
├── Test Page 01
├── Test Page 02
│   ├── Child Page 02.1
│   └── Child Page 02.2
├── Test Page 03
│   └── Child Page 03.1
│       └── Grandchild Page 03.1.1
├── Archives (TEST_ARCHIVES_PAGE) [for exclusion tests]
│   ├── Old Document 01
│   └── Old Document 02
└── Test Pages 04-15 (for count tests)
```

**Total**: 15 pages (for E2E-1)

### Fixtures

```python
# tests/conftest.py

@pytest.fixture
def confluence_test_client():
    """Provide authenticated Confluence client for integration tests."""
    auth = Authenticator()  # Uses test credentials from .env.test
    return APIWrapper(auth)

@pytest.fixture
def tmp_test_dir(tmp_path):
    """Provide temp directory for file operations."""
    return tmp_path

@pytest.fixture
def test_config(tmp_test_dir):
    """Provide test configuration."""
    return SyncConfig(
        version=1,
        spaces=[SpaceConfig(
            space_key="CONFSYNCTEST",
            parent_page_id="TEST_ROOT_PAGE",
            local_path=tmp_test_dir,
            exclude_page_ids=[]
        )]
    )
```

---

## Mocking Strategy

### Mock Boundaries

| Test Level | Mock Strategy |
|------------|---------------|
| **Unit** | Mock all external dependencies (API, filesystem, YAML) |
| **Integration** | Mock Confluence API only (use real filesystem in temp dir) |
| **E2E** | No mocks (use real test Confluence space + temp dir) |

### Mock Examples

```python
# Unit test: Mock APIWrapper
@patch('file_mapper.hierarchy_builder.APIWrapper')
def test_hierarchy_builder_query_children(mock_api):
    mock_api.execute_cql.return_value = {
        "results": [
            {"id": "12345", "title": "Test Page", "version": {"when": "...", "number": 1}}
        ]
    }

    builder = HierarchyBuilder(mock_api)
    children = builder.query_children("PARENT_ID")

    assert len(children) == 1
    assert children[0]["page_id"] == "12345"

# Integration test: Use real filesystem, mock API
@pytest.mark.integration
def test_write_page_to_local(tmp_path, mock_api):
    config = SyncConfig(...)
    mapper = FileMapper(config, mock_api)

    page_node = PageNode(page_id="12345", title="Test Page", ...)
    content = "# Test Content"

    file_path = mapper.write_page_to_local(page_node, content)

    assert file_path.exists()
    assert "page_id: \"12345\"" in file_path.read_text()
```

---

## Test Execution

### Local Development

```bash
# Run all tests
pytest

# Run only unit tests
pytest tests/unit/

# Run with coverage
pytest --cov=src/file_mapper --cov-report=html

# Run specific test file
pytest tests/unit/file_mapper/test_filesafe_converter.py

# Run E2E tests (requires test Confluence space)
pytest tests/e2e/ -m e2e
```

### CI/CD Pipeline

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run unit tests
        run: pytest tests/unit/ --cov=src/file_mapper --cov-report=xml

      - name: Run integration tests
        run: pytest tests/integration/
        env:
          CONFLUENCE_URL: ${{ secrets.TEST_CONFLUENCE_URL }}
          CONFLUENCE_USER: ${{ secrets.TEST_CONFLUENCE_USER }}
          CONFLUENCE_API_TOKEN: ${{ secrets.TEST_CONFLUENCE_TOKEN }}

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## Success Criteria

- ✅ Unit test coverage >90% for all file_mapper modules
- ✅ All 6 E2E scenarios pass
- ✅ All integration tests pass
- ✅ No test flakiness (tests are deterministic)
- ✅ Test execution time <2 minutes (unit + integration)
- ✅ E2E tests <5 minutes (depends on Confluence API)

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| **Confluence API rate limits** | Use test space with <50 pages; add retry logic |
| **Filesystem permissions on CI** | Use pytest tmp_path fixture (guaranteed writable) |
| **Test data pollution** | Clean up test pages after E2E tests; use unique prefixes |
| **Flaky network tests** | Add retry logic for Confluence API calls; use pytest-rerunfailures |
| **Time-dependent tests** | Mock datetime for frontmatter timestamps |

---

## Test Documentation

Each test should have:
1. **Docstring**: What is being tested
2. **Given-When-Then**: Arrange-Act-Assert structure
3. **Assertions**: Clear, specific checks
4. **Cleanup**: Proper teardown for integration/E2E tests

**Example**:
```python
def test_frontmatter_missing_required_field():
    """Test that missing required field raises FrontmatterError.

    Given: Markdown file with frontmatter missing page_id
    When: parse_frontmatter() is called
    Then: FrontmatterError is raised with clear message
    """
    content = """---
space_key: "TEST"
title: "Test Page"
---

# Test Content
"""

    with pytest.raises(FrontmatterError) as exc_info:
        FrontmatterHandler.parse_frontmatter(content)

    assert "page_id" in str(exc_info.value)
    assert "required field" in str(exc_info.value).lower()
```
