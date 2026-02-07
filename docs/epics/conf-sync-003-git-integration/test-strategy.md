# Test Strategy: CONF-SYNC-003 - Git Integration

**Epic**: Git Integration for Conflict Detection and Resolution
**Date**: 2026-01-30

---

## Overview

This document defines the test strategy for git-based conflict resolution. It specifies unit test boundaries, E2E scenarios, mocking approaches, and test data requirements.

---

## Test Pyramid

```
         ┌─────────────────┐
         │   E2E Tests     │  ~15 tests (slower, full system)
         │   (5 journeys)  │
         └─────────────────┘
              │
    ┌─────────────────────┐
    │  Integration Tests  │  ~30 tests (moderate, component pairs)
    │  (component pairs)  │
    └─────────────────────┘
              │
   ┌──────────────────────┐
   │    Unit Tests        │  ~100 tests (fast, isolated)
   │    (pure logic)      │
   └──────────────────────┘
```

**Target Coverage**: >90% for git_integration module

---

## Unit Tests (Fast, No External Dependencies)

### Test File: tests/unit/test_git_repository.py

**Component**: `GitRepository`

**Test Scope**: Git repo management without real git operations

**Mocking Strategy**:
- Mock `subprocess.run()` for all git commands
- Use temp directory for repo path
- Verify git commands called with correct arguments

**Test Cases**:

| Test ID | Test Case | Assertions |
|---------|-----------|------------|
| UT-GR-01 | `test_init_creates_repo()` | - `git init` called<br>- README.md created |
| UT-GR-02 | `test_init_skips_if_exists()` | - `git init` not called if .git/ exists |
| UT-GR-03 | `test_commit_version()` | - File written to `{page_id}.md`<br>- `git add` called<br>- `git commit` with correct message |
| UT-GR-04 | `test_get_version_found()` | - `git log` called<br>- Returns markdown content |
| UT-GR-05 | `test_get_version_not_found()` | - Returns None for missing version |
| UT-GR-06 | `test_validate_repo_valid()` | - `git fsck` exits 0<br>- Returns True |
| UT-GR-07 | `test_validate_repo_invalid()` | - `git fsck` exits non-zero<br>- Returns False |
| UT-GR-08 | `test_git_command_timeout()` | - Raises GitRepositoryError after 10s |
| UT-GR-09 | `test_git_command_failure()` | - Captures stderr<br>- Raises GitRepositoryError with output |
| UT-GR-10 | `test_get_latest_version_number()` | - Parses commit messages<br>- Returns highest version |

**Example**:
```python
@patch("subprocess.run")
def test_commit_version(mock_run):
    # Arrange
    repo = GitRepository("/tmp/test_repo")
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    # Act
    sha = repo.commit_version(
        page_id="123456",
        markdown="# Test",
        version=15
    )

    # Assert
    assert mock_run.call_count == 2  # git add + git commit
    assert "Page 123456: version 15" in str(mock_run.call_args_list)
```

---

### Test File: tests/unit/test_xhtml_cache.py

**Component**: `XHTMLCache`

**Test Scope**: Cache operations with file system, no Confluence API

**Mocking Strategy**:
- Use temp directory for cache_dir
- Real file operations (fast enough for unit tests)
- Mock datetime for timestamp control

**Test Cases**:

| Test ID | Test Case | Assertions |
|---------|-----------|------------|
| UT-XC-01 | `test_put_creates_files()` | - XHTML file created<br>- Metadata JSON created |
| UT-XC-02 | `test_get_cache_hit()` | - Returns XHTML when timestamps match |
| UT-XC-03 | `test_get_cache_miss_timestamp()` | - Returns None when timestamp mismatched |
| UT-XC-04 | `test_get_cache_miss_not_found()` | - Returns None when file doesn't exist |
| UT-XC-05 | `test_invalidate_deletes_files()` | - XHTML and metadata files deleted |
| UT-XC-06 | `test_clear_all()` | - All cache files deleted |
| UT-XC-07 | `test_corrupted_metadata()` | - Returns None on JSON parse error |
| UT-XC-08 | `test_auto_cleanup_old_entries()` | - Entries older than max_age_days deleted |

---

### Test File: tests/unit/test_conflict_detector.py

**Component**: `ConflictDetector`

**Test Scope**: Conflict detection logic, mocked dependencies

**Mocking Strategy**:
- Mock `PageOperations.get_page_snapshot()`
- Mock `GitRepository.get_version()`
- Mock `XHTMLCache.get()`

**Test Cases**:

| Test ID | Test Case | Assertions |
|---------|-----------|------------|
| UT-CD-01 | `test_no_conflicts()` | - All pages in auto_mergeable<br>- conflicts list empty |
| UT-CD-02 | `test_version_mismatch_conflict()` | - Conflict detected when local ≠ remote |
| UT-CD-03 | `test_version_match_no_conflict()` | - No conflict when local == remote |
| UT-CD-04 | `test_base_version_found()` | - ConflictInfo.has_base = True |
| UT-CD-05 | `test_base_version_missing()` | - ConflictInfo.has_base = False |
| UT-CD-06 | `test_cache_hit_no_api_fetch()` | - get_page_snapshot not called if cache valid |
| UT-CD-07 | `test_cache_miss_api_fetch()` | - get_page_snapshot called on cache miss |
| UT-CD-08 | `test_parallel_detection()` | - All pages checked in parallel<br>- Result consistent |
| UT-CD-09 | `test_api_error_in_errors_list()` | - API failures added to errors, not crash |

---

### Test File: tests/unit/test_merge_orchestrator.py

**Component**: `MergeOrchestrator`

**Test Scope**: Workflow orchestration, mocked components

**Mocking Strategy**:
- Mock `ConflictDetector`
- Mock `GitRepository`
- Mock `MergeTool`
- Mock `PageOperations`

**Test Cases**:

| Test ID | Test Case | Assertions |
|---------|-----------|------------|
| UT-MO-01 | `test_sync_no_conflicts()` | - All pages auto-merged<br>- No merge tool launched |
| UT-MO-02 | `test_sync_with_conflicts()` | - Conflict files created<br>- Merge tool launched |
| UT-MO-03 | `test_sync_unresolved_conflicts()` | - Raises MergeConflictError<br>- No push to Confluence |
| UT-MO-04 | `test_force_push()` | - No conflict detection<br>- All pages pushed |
| UT-MO-05 | `test_force_pull()` | - No conflict detection<br>- All pages pulled |
| UT-MO-06 | `test_partial_failure_rollback()` | - If one page fails, others not pushed |
| UT-MO-07 | `test_git_commit_after_push()` | - New versions committed to git repo |

---

### Test File: tests/unit/test_merge_tool.py

**Component**: `MergeTool`

**Test Scope**: Merge tool integration, mocked subprocess

**Mocking Strategy**:
- Mock `subprocess.run()` for tool launch
- Mock `shutil.which()` for tool validation

**Test Cases**:

| Test ID | Test Case | Assertions |
|---------|-----------|------------|
| UT-MT-01 | `test_validate_vscode_available()` | - Returns True if `code` in PATH |
| UT-MT-02 | `test_validate_vscode_unavailable()` | - Returns False if `code` not in PATH |
| UT-MT-03 | `test_launch_vscode()` | - Calls `code --wait --diff` with correct args |
| UT-MT-04 | `test_launch_vim()` | - Calls `vim -d` with correct args |
| UT-MT-05 | `test_launch_custom_command()` | - Custom command template expanded |
| UT-MT-06 | `test_tool_timeout()` | - Raises MergeToolError after 30min |
| UT-MT-07 | `test_tool_exit_nonzero()` | - Raises MergeToolError with stderr |

---

## Integration Tests (Component Pairs)

### Test File: tests/integration/test_git_cache_integration.py

**Test Scope**: `GitRepository` + `XHTMLCache` working together

**Real Components**: Both GitRepository and XHTMLCache (real file operations)

**Mocking**: Confluence API only

**Test Cases**:

| Test ID | Test Case | Assertions |
|---------|-----------|------------|
| IT-GC-01 | `test_commit_and_retrieve_version()` | - Commit markdown to git<br>- Retrieve from git history |
| IT-GC-02 | `test_cache_then_git_fallback()` | - Cache miss → Git retrieval |

---

### Test File: tests/integration/test_detector_cache_integration.py

**Test Scope**: `ConflictDetector` + `XHTMLCache` optimization

**Real Components**: ConflictDetector, XHTMLCache

**Mocking**: Confluence API, GitRepository

**Test Cases**:

| Test ID | Test Case | Assertions |
|---------|-----------|------------|
| IT-DC-01 | `test_cache_reduces_api_calls()` | - First run: N API calls<br>- Second run: 0 API calls (cache hit) |

---

## E2E Tests (Full System)

### Test File: tests/e2e/test_conflict_resolution_journey.py

**Test Scope**: Complete conflict resolution workflow with real Confluence

**Real Components**: All components, real Confluence API, real git repo

**Mocking**: None (real test Confluence instance)

**Setup Requirements**:
- Test Confluence space (from .env.test)
- Pandoc installed
- Git CLI installed
- VS Code installed (or mock merge tool for CI)

**Test Data**: From `tests/fixtures/conflict_scenarios.py`

---

#### E2E-CR-01: Full Conflict Resolution Journey

**Scenario**: Single page with conflicting edits, clean resolution

**Setup**:
1. Create test page "E2E Conflict Test" on Confluence (version 1)
2. Pull to local file
3. Edit local: Change "Installation" section
4. Edit Confluence (external): Change "Installation" section (different content)
5. Confluence now at version 2

**Execution**:
```python
def test_full_conflict_resolution_journey():
    # Arrange: Page setup (above)

    # Act: Run sync
    orchestrator = MergeOrchestrator()
    local_pages = [
        LocalPage(
            page_id=test_page_id,
            file_path="tmp/test.md",
            local_version=1,
            title="E2E Conflict Test"
        )
    ]

    result = orchestrator.sync(local_pages)

    # Assert: Conflict detected
    assert not result.success  # Conflicts unresolved
    assert os.path.exists("tmp/test.md.conflict")

    # Simulate user resolution (auto-resolve for test)
    with open("tmp/test.md.conflict") as f:
        conflict_content = f.read()

    # Remove conflict markers, keep local version
    resolved = re.sub(r"<<<<<<< LOCAL\n(.*?)\n=======\n.*?\n>>>>>>> CONFLUENCE", r"\1", conflict_content, flags=re.DOTALL)

    with open("tmp/test.md", "w") as f:
        f.write(resolved)

    # Act: Continue sync
    result = orchestrator.sync(local_pages)

    # Assert: Success
    assert result.success
    assert result.pages_synced == 1

    # Verify Confluence updated
    snapshot = page_ops.get_page_snapshot(test_page_id)
    assert snapshot.version == 3  # Incremented after merge
    assert "Installation" in snapshot.markdown  # Resolved content
```

**Assertions**:
- Conflict file created with standard git markers
- After resolution, page pushed to Confluence
- Confluence version incremented (1 → 2 → 3 after merge push)
- Git repo has commit for version 3
- Local file updated with merged content

---

#### E2E-CR-02: Multi-Page Batch Resolution

**Scenario**: 3 pages, 2 with conflicts, 1 auto-mergeable

**Setup**:
- Page A: Conflicting edits in Section 1
- Page B: Only local edits (auto-merge)
- Page C: Conflicting edits in Section 2

**Assertions**:
- Batch detection identifies 2 conflicts
- Page B auto-merged without conflict file
- Conflict files created for A and C
- After resolution, all 3 pages synced

---

#### E2E-CR-03: Force Push Overwrites Remote

**Scenario**: Local version 6, Confluence version 8, force push

**Assertions**:
- No conflict detection
- Confluence content overwritten with local
- Confluence version increments to 9 (not based on local version)
- Git repo commits version 9

---

#### E2E-CR-04: Force Pull Overwrites Local

**Scenario**: Local version 6, Confluence version 8, force pull

**Assertions**:
- No conflict detection
- Local file overwritten with Confluence content
- Local frontmatter updated to version 8
- Git repo commits version 8

---

#### E2E-CR-05: Cache Optimization

**Scenario**: Sync twice with no changes between syncs

**Setup**:
1. First sync: Page unchanged since last sync
2. Second sync: Same page, still unchanged

**Assertions**:
- First sync: 2 API calls (metadata + content fetch)
- Second sync: 1 API call (metadata check only, cache hit)
- Cache hit logged in output

---

### Test File: tests/e2e/test_force_operations_journey.py

**E2E scenarios for force push/pull** (E2E-CR-03, E2E-CR-04)

---

### Test File: tests/e2e/test_cache_optimization_journey.py

**E2E scenario for cache hit** (E2E-CR-05)

---

## Test Fixtures

### tests/fixtures/git_test_repos.py

**Purpose**: Sample git repos for testing

**Fixtures**:
```python
@pytest.fixture
def empty_git_repo(tmp_path):
    """Empty initialized git repo."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True)
    return str(repo_path)

@pytest.fixture
def git_repo_with_history(tmp_path):
    """Git repo with 3 committed versions."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True)

    # Commit version 1, 2, 3
    for version in [1, 2, 3]:
        file_path = repo_path / "123456.md"
        file_path.write_text(f"# Version {version}\n\nContent for version {version}")
        subprocess.run(["git", "add", "123456.md"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Page 123456: version {version}"],
            cwd=repo_path,
            check=True
        )

    return str(repo_path)
```

---

### tests/fixtures/conflict_scenarios.py

**Purpose**: Sample conflict data for testing

**Fixtures**:
```python
CONFLICT_SCENARIO_1 = {
    "base": """# Getting Started

## Installation
Install via pip:
```bash
pip install myapp
```
""",
    "local": """# Getting Started

## Installation
Install via pip (with extras):
```bash
pip install myapp[all]
```
""",
    "remote": """# Getting Started

## Installation
Install via poetry:
```bash
poetry add myapp
```
"""
}

CONFLICT_SCENARIO_2 = {
    # Non-overlapping changes (auto-mergeable)
    "base": """# Page

## Section A
Content A

## Section B
Content B
""",
    "local": """# Page

## Section A
Modified content A

## Section B
Content B
""",
    "remote": """# Page

## Section A
Content A

## Section B
Modified content B
"""
}
```

---

## Test Helpers

### tests/helpers/git_test_utils.py

**Purpose**: Utilities for git testing

**Functions**:
```python
def create_temp_git_repo() -> str:
    """Create temporary git repo for testing."""

def commit_file_to_repo(repo_path: str, file_name: str, content: str, message: str) -> str:
    """Commit file to git repo, return SHA."""

def get_file_from_commit(repo_path: str, file_name: str, commit_sha: str) -> str:
    """Retrieve file content from specific commit."""
```

---

## Mocking Guidelines

### What to Mock in Unit Tests

**Always Mock**:
- `subprocess.run()` - Git commands
- `PageOperations` - Confluence API calls
- `MarkdownConverter` - Pandoc subprocess (already tested in CONF-SYNC-001)

**Never Mock**:
- File system operations (use temp directories)
- Data classes (PageSnapshot, ConflictInfo, etc.)
- Pure Python logic (datetime, string manipulation)

### What NOT to Mock in E2E Tests

**Real Components** (E2E tests):
- Git CLI (validate installation in CI)
- File system
- Confluence test instance (from .env.test)
- Pandoc (validate installation in CI)

**Mock in E2E Tests** (only if necessary for CI):
- Merge tool launch (VS Code might not be in CI environment)
  - Mock with auto-resolution or manual resolution test

---

## Test Data Requirements

### Confluence Test Instance

**Required**:
- Test space (e.g., TESTSPACE)
- API credentials in `.env.test`:
  ```
  CONFLUENCE_URL=https://test.atlassian.net
  CONFLUENCE_USER=test@example.com
  CONFLUENCE_API_TOKEN=ATATT3xFfGF0...
  ```

**Test Page Setup**:
- Pages created/deleted in each E2E test
- Cleanup in fixture teardown

---

## CI/CD Considerations

### GitHub Actions Workflow

**Validation Steps**:
```yaml
- name: Validate Git installed
  run: git --version

- name: Validate Pandoc installed
  run: pandoc --version

- name: Run Unit Tests
  run: pytest tests/unit/ -v --cov=src/git_integration

- name: Run E2E Tests (if Confluence creds available)
  run: |
    if [ -f .env.test ]; then
      pytest tests/e2e/ -v
    else
      echo "Skipping E2E tests (no .env.test)"
    fi
```

**Mock Merge Tool in CI**:
```python
@pytest.fixture
def mock_merge_tool_for_ci(monkeypatch):
    """Auto-resolve conflicts in CI where VS Code unavailable."""
    if os.getenv("CI"):
        monkeypatch.setattr("src.git_integration.merge_tool.MergeTool.launch", auto_resolve_mock)
```

---

## Coverage Targets

| Component | Target Coverage | Rationale |
|-----------|----------------|-----------|
| GitRepository | 95% | Critical, complex git operations |
| XHTMLCache | 90% | I/O operations, error paths |
| ConflictDetector | 95% | Core conflict detection logic |
| MergeOrchestrator | 90% | Workflow orchestration, many paths |
| MergeTool | 85% | Subprocess integration, less critical |

**Overall Target**: >90% for `src/git_integration/` module

---

## Test Execution Plan

### Phase 1: Unit Tests (Week 1)
- Implement unit tests for all 5 components
- Achieve >90% coverage
- Fast execution (<5 seconds)

### Phase 2: Integration Tests (Week 1-2)
- Test component pairs
- Validate cache optimization
- Fast execution (<10 seconds)

### Phase 3: E2E Tests (Week 2)
- Implement 5 E2E journeys
- Require test Confluence setup
- Moderate execution (2-3 minutes)

### Phase 4: CI Integration (Week 2)
- GitHub Actions workflow
- Badge: Test coverage >90%
- Badge: E2E tests passing

---

## Definition of Done (Testing)

- [ ] >90% code coverage for `src/git_integration/` module
- [ ] All unit tests pass (<5s execution)
- [ ] All integration tests pass (<10s execution)
- [ ] All E2E tests pass (<3min execution)
- [ ] CI workflow validates git and pandoc installed
- [ ] Merge tool mocked in CI if unavailable
- [ ] Test fixtures cover all conflict scenarios from acceptance criteria
- [ ] Error paths tested (git failures, API failures, tool failures)
