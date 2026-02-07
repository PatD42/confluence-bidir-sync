# Test Strategy - CONF-SYNC-004

---

## Overview

Testing strategy for CLI & Sync Orchestration epic.

**Coverage Target**: >90% for `src/cli/` module

---

## Test Boundaries

### Unit Tests (Mock Dependencies)

| Component | What to Mock | What to Test |
|-----------|--------------|--------------|
| `SyncCommand` | FileMapper, MergeOrchestrator, StateManager | Orchestration logic, exit codes |
| `ChangeDetector` | None (pure logic) | Timestamp comparisons, classification |
| `StateManager` | Filesystem | Load/save state, default handling |
| `OutputHandler` | Console | Message formatting, verbosity levels |
| `InitCommand` | FileMapper, APIWrapper | Config creation, path validation |

### Integration Tests (Real Filesystem)

| Test | Description |
|------|-------------|
| Config load/save | Read/write `.confluence-sync/config.yaml` |
| State persistence | Read/write `.confluence-sync/state.yaml` |
| File mtime comparison | Actual filesystem mtime vs timestamps |

### E2E Tests (Real Confluence)

| Test | Description |
|------|-------------|
| Full sync cycle | Init → modify → sync → verify |
| Force push/pull | Override operations |
| Conflict resolution | Trigger and resolve conflicts |
| Error scenarios | Auth failure, network error, rate limits |

---

## Unit Test Coverage

### ChangeDetector Tests

```python
class TestChangeDetector:
    def test_no_changes_when_timestamps_match(self):
        """All files unchanged when mtime <= last_synced."""

    def test_local_change_detected(self):
        """File with mtime > last_synced classified as to_push."""

    def test_remote_change_detected(self):
        """Page with last_modified > last_synced classified as to_pull."""

    def test_conflict_detected(self):
        """Both mtime and last_modified > last_synced = conflict."""

    def test_new_local_file_no_page_id(self):
        """Local file without page_id = new page to create."""

    def test_new_remote_page_no_local(self):
        """Remote page without local file = new page to pull."""
```

### SyncCommand Tests

```python
class TestSyncCommand:
    def test_dryrun_no_changes_applied(self):
        """--dryrun displays changes but doesn't modify anything."""

    def test_force_push_bypasses_detection(self):
        """--forcePush calls force_push() without change detection."""

    def test_force_pull_bypasses_detection(self):
        """--forcePull calls force_pull() without change detection."""

    def test_exit_code_success(self):
        """Returns 0 on successful sync."""

    def test_exit_code_conflicts(self):
        """Returns 2 when unresolved conflicts."""

    def test_exit_code_auth_failure(self):
        """Returns 3 on InvalidCredentialsError."""

    def test_exit_code_network_error(self):
        """Returns 4 on APIUnreachableError."""

    def test_single_file_sync(self):
        """File argument limits sync to that file only."""

    def test_state_updated_on_success(self):
        """last_synced updated after successful sync."""

    def test_state_not_updated_on_failure(self):
        """last_synced NOT updated if sync fails."""
```

### StateManager Tests

```python
class TestStateManager:
    def test_load_missing_file_returns_default(self):
        """Missing state.yaml returns SyncState with None last_synced."""

    def test_load_existing_file(self):
        """Loads last_synced from existing state.yaml."""

    def test_save_creates_file(self):
        """Saves state to file."""

    def test_update_last_synced(self):
        """update_last_synced() sets current time."""
```

### OutputHandler Tests

```python
class TestOutputHandler:
    def test_verbose_0_hides_info(self):
        """Info messages hidden at verbose=0."""

    def test_verbose_1_shows_info(self):
        """Info messages shown at verbose=1."""

    def test_verbose_2_shows_debug(self):
        """Debug messages shown at verbose=2."""

    def test_no_color_strips_ansi(self):
        """--no-color removes ANSI codes."""
```

---

## E2E Test Scenarios

### E2E-1: Full Bidirectional Sync

```python
def test_full_bidirectional_sync():
    """
    1. Init with test space
    2. Modify 3 local files
    3. Modify 3 Confluence pages
    4. Run confluence-sync
    5. Verify all 6 changes synced
    6. Verify state.yaml updated
    """
```

### E2E-2: Conflict Resolution

```python
def test_conflict_resolution():
    """
    1. Sync page to local
    2. Modify local and Confluence
    3. Run confluence-sync
    4. Verify merge tool triggered
    5. Simulate resolution
    6. Verify resolved content pushed
    """
```

### E2E-3: Force Push

```python
def test_force_push():
    """
    1. Sync page
    2. Run --forcePush
    3. Verify local pushed unconditionally
    4. Verify no timestamp check
    """
```

### E2E-4: Force Pull

```python
def test_force_pull():
    """
    1. Sync page
    2. Run --forcePull
    3. Verify Confluence pulled unconditionally
    4. Verify local overwritten
    """
```

### E2E-5: Dry Run

```python
def test_dryrun():
    """
    1. Set up changes
    2. Run --dryrun
    3. Verify output shows changes
    4. Verify NO changes applied
    """
```

### E2E-6: Error Handling

```python
def test_auth_failure_exit_code():
    """Invalid credentials → exit code 3."""

def test_network_error_exit_code():
    """API unreachable → exit code 4."""

def test_rate_limit_exhaustion():
    """429 after 3 retries → exit code 4."""

def test_pandoc_missing():
    """Pandoc not in PATH → exit code 1."""
```

---

## Test Data

### Fixtures

```python
@pytest.fixture
def sync_config():
    """Valid SyncConfig for testing."""
    return SyncConfig(
        version=1,
        spaces=[SpaceConfig(
            space_key="TEST",
            parent_page_id="12345",
            local_path=Path("./test_docs"),
        )]
    )

@pytest.fixture
def sync_state():
    """SyncState with last_synced 1 hour ago."""
    return SyncState(
        last_synced=datetime.now(timezone.utc) - timedelta(hours=1)
    )

@pytest.fixture
def local_page_unchanged(sync_state):
    """LocalPage with mtime before last_synced."""
    ...

@pytest.fixture
def local_page_modified(sync_state):
    """LocalPage with mtime after last_synced."""
    ...
```

### Mock Strategies

```python
# Mock FileMapper
@pytest.fixture
def mock_file_mapper():
    mapper = Mock(spec=FileMapper)
    mapper.discover_pages.return_value = [...]
    mapper.scan_local_files.return_value = [...]
    return mapper

# Mock MergeOrchestrator
@pytest.fixture
def mock_orchestrator():
    orch = Mock(spec=MergeOrchestrator)
    orch.sync.return_value = SyncResult(success=True, ...)
    return orch
```

---

## Test Organization

```
tests/
├── unit/
│   ├── cli/
│   │   ├── test_sync_command.py
│   │   ├── test_init_command.py
│   │   ├── test_change_detector.py
│   │   ├── test_state_manager.py
│   │   └── test_output_handler.py
├── integration/
│   └── cli/
│       ├── test_config_persistence.py
│       └── test_state_persistence.py
├── e2e/
│   ├── test_cli_sync_journey.py
│   ├── test_cli_force_operations.py
│   └── test_cli_error_handling.py
└── fixtures/
    └── cli_fixtures.py
```

---

## CI Integration

```yaml
# Run CLI tests
pytest tests/unit/cli/ -v --cov=src/cli --cov-report=term-missing

# E2E requires real Confluence (skip in CI without credentials)
pytest tests/e2e/test_cli_*.py -v --run-e2e
```
