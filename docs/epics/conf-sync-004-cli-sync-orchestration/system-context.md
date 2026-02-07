# System Context - CONF-SYNC-004

---

## Overview

The CLI module (`src/cli/`) is the user-facing interface that orchestrates all sync operations. It coordinates the file_mapper (Epic 002), git_integration (Epic 003), and page_operations (Epic 001) modules.

---

## Integration Points

### Dependencies (Modules Used)

| Module | Epic | Purpose | Key Interfaces |
|--------|------|---------|----------------|
| `file_mapper/` | 002 | Local file operations | `FileMapper.discover_pages()`, `scan_local_files()`, `write_page_to_local()` |
| `git_integration/` | 003 | Conflict resolution | `MergeOrchestrator.sync()`, `force_push()`, `force_pull()` |
| `page_operations/` | 001 | Confluence API | `PageOperations.get_page_snapshot()`, `apply_operations()`, `create_page()` |
| `confluence_client/` | 001 | Low-level API | `APIWrapper` (used via PageOperations) |
| `content_converter/` | 001 | Format conversion | `MarkdownConverter` (used via PageOperations) |

### External Dependencies

| Dependency | Purpose | Validation |
|------------|---------|------------|
| Pandoc CLI | Markdown conversion | Check at startup, fail with clear message |
| Git CLI | Merge operations | Check at startup if git_integration needed |
| Merge tool | Conflict resolution | Check when conflicts detected |

---

## Patterns to Follow

### From Epic 001 (confluence_client/)
- **Error handling**: Typed exceptions with context (user, endpoint, page_id)
- **Retry logic**: Exponential backoff for 429 only, fail-fast for others
- **Lazy loading**: Don't validate until first use

### From Epic 002 (file_mapper/)
- **Frontmatter**: Minimal schema (`page_id` only)
- **Filesafe naming**: `FilesafeConverter.title_to_filename()`
- **Config loading**: `ConfigLoader.load_config()` from `.confluence-sync/config.yaml`

### From Epic 003 (git_integration/)
- **Merge workflow**: `MergeOrchestrator` handles all conflict cases
- **Batch operations**: Detect all conflicts before launching merge tool

---

## Inherited Constraints

### From PRD
- Python 3.9+
- Pandoc 3.8.3+
- macOS, Linux only
- Confluence Cloud only

### From Architecture
- No `shell=True` in subprocess calls
- 10-second timeout for Pandoc
- Credentials from `.env` via python-dotenv
- No credentials in logs

### From Epic Dependencies
- File mtime comparison for local change detection (Epic 002)
- `last_synced` stored at project level in `.confluence-sync/state.yaml` (Epic 004 decision)
- Merge tool launched for conflicts (Epic 003)

---

## Data Flow

```
User runs: confluence-sync [options]

1. CLI Initialization
   ├── Load config from .confluence-sync/config.yaml
   ├── Load state from .confluence-sync/state.yaml (last_synced)
   ├── Validate Pandoc available
   └── Initialize modules (FileMapper, MergeOrchestrator)

2. Page Discovery
   ├── FileMapper.discover_pages() → List[PageNode] from Confluence
   └── FileMapper.scan_local_files() → List[LocalPage] from filesystem

3. Change Detection
   ├── Compare file mtime vs project last_synced
   ├── Compare Confluence last_modified vs project last_synced
   └── Classify: unchanged, local_changed, remote_changed, conflict

4. Sync Execution (based on flags)
   ├── --dryrun: Display changes, exit
   ├── --forcePush: MergeOrchestrator.force_push()
   ├── --forcePull: MergeOrchestrator.force_pull()
   └── default: MergeOrchestrator.sync() with conflict resolution

5. State Update
   └── Update .confluence-sync/state.yaml with current timestamp
```

---

## Feasibility Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| Dependencies available | Yes | Epics 001-003 provide all needed interfaces |
| Patterns established | Yes | Error handling, retry, config loading well-defined |
| Constraints clear | Yes | Exit codes, output format, CLI args specified |
| Risk areas | Low | CLI is orchestration only, no complex logic |

**Conclusion**: Feasible. CLI is a thin orchestration layer over well-defined modules.
