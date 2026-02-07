---
epic_id: CONF-SYNC-006
title: Architecture Decision Records
created_date: 2026-01-31
---

# Architecture Decision Records: CONF-SYNC-006

## ADR-025: Single CQL Query for Page Discovery

### Status
Accepted

### Context
The current HierarchyBuilder makes recursive API calls to discover page hierarchies:
- 1 call to get parent page
- 1 call per parent to get its children
- For a hierarchy with 50 pages, this results in 10-20+ API calls

This is inefficient and slow for large hierarchies.

### Decision
Replace recursive `get_page_child_by_type` calls with a single CQL query:
```
ancestor = {parent_page_id} AND space = {space_key}
```

This query returns all descendants of a page in one call.

### Consequences
**Positive:**
- Single API call regardless of hierarchy depth
- Faster sync for large page trees
- Simpler code (no recursion)
- All page metadata available upfront

**Negative:**
- Must handle CQL pagination for results > 25
- Page limit now applies to total descendants, not per-level

---

## ADR-026: Frontmatter Contains Only page_id

### Status
Accepted

### Context
Current frontmatter includes 5 fields:
- `page_id`
- `space_key`
- `title`
- `last_synced`
- `confluence_version`

Most of these are redundant:
- `space_key`: Available from config
- `title`: Available from CQL query or derivable from content
- `last_synced`: Global timestamp in state.yaml
- `confluence_version`: Not needed; we use last_modified timestamp

### Decision
Reduce frontmatter to only `page_id`:
```yaml
---
page_id: "123456"
---
```

### Consequences
**Positive:**
- Cleaner markdown files
- Single source of truth for each piece of data
- Smaller file diffs when syncing

**Negative:**
- Must derive title from CQL or content for new pages
- Backward compatibility needed for existing files

---

## ADR-027: Title Derivation Strategy

### Status
Accepted

### Context
With `title` removed from frontmatter, we need alternative sources for page titles.

### Decision
Title resolution order:
1. **Existing pages**: Use `title` from CQL query result (authoritative)
2. **New pages**: Extract from first H1 heading (`# Title`)
3. **Fallback**: Use filename without `.md` extension

### Consequences
**Positive:**
- Titles always match Confluence (for existing pages)
- Intuitive behavior for new pages (H1 = title)
- Graceful fallback

**Negative:**
- New pages without H1 get less descriptive titles
- Error case needed if title cannot be determined

---

## ADR-028: Single-File Sync Without Timestamp Update

### Status
Accepted

### Context
The global `last_synced` timestamp in state.yaml is used for change detection. If we update it after syncing a single file, other files will appear "unchanged" on next sync (their changes would be missed).

### Decision
When syncing a single file:
1. Update the baseline for that file
2. Do NOT update `state.last_synced`

On next full sync:
- The single-synced file may be flagged as "conflict" (both sides changed since last_synced)
- 3-way merge will find local = baseline = remote (no actual changes)
- Result: Correct behavior with one unnecessary conflict cycle

### Consequences
**Positive:**
- Single-file sync doesn't break change detection for other files
- Functionally correct behavior
- Simple implementation

**Negative:**
- One unnecessary conflict detection cycle for the synced file on next run
- Slightly confusing if user inspects change detection output

---

## ADR-029: CLI Without Subcommands

### Status
Accepted

### Context
Current CLI has two subcommands:
- `confluence-sync sync [options]`
- `confluence-sync init SPACE:PATH LOCAL_PATH`

This adds verbosity for a tool with simple usage patterns.

### Decision
Remove subcommands:
- Default (no args): Run bidirectional sync
- `--init "SPACE:Path" LOCAL_PATH`: Initialize configuration
- All other flags (`--dry-run`, `--force-push`, etc.) at top level

### Consequences
**Positive:**
- Simpler commands: `confluence-sync` vs `confluence-sync sync`
- Consistent with other CLI tools (git, docker)
- Fewer keystrokes for common operations

**Negative:**
- Breaking change for existing users
- `--init` requires two positional-like arguments

---

## ADR-030: Mandatory Package Installation

### Status
Accepted

### Context
The CLI can be run two ways:
1. `confluence-sync` (after `pip install -e .`)
2. `python -m src.cli.main` (without installation)

Supporting both complicates documentation and error messages.

### Decision
Require package installation:
- Documentation shows only `pip install -e .` + `confluence-sync`
- Error messages reference `confluence-sync` command
- No documentation for `python -m` invocation

### Consequences
**Positive:**
- Consistent user experience
- Simpler documentation
- Command available in PATH

**Negative:**
- Extra setup step for new users
- Development requires reinstall after code changes (unless `-e` used)

---

## ADR-031: File Logging with Local Timezone

### Status
Accepted

### Context
Users need persistent logs for debugging sync issues. Current logging goes only to stderr.

### Decision
Add `--logdir` parameter:
- When provided: Write logs to `{logdir}/confluence-sync-YYYYMMDD-HHMMSS.log`
- Timestamp in filename uses local timezone
- Log entry timestamps use local timezone
- Directory auto-created if missing
- When not provided: Logs to stderr (current behavior)

### Consequences
**Positive:**
- Persistent logs for debugging
- Timestamps match user's local time (intuitive)
- Non-breaking change (opt-in)

**Negative:**
- Log files accumulate (no auto-cleanup)
- Local timezone may cause confusion in distributed teams

---

## ADR-032: Backward Compatible Frontmatter Parsing

### Status
Accepted

### Context
Existing repositories have files with old frontmatter format (5 fields). We need to support these during migration.

### Decision
- **Parse**: Accept both old and new formats (extra fields ignored)
- **Write**: Always use new format (page_id only)

Files are gradually migrated as they are synced.

### Consequences
**Positive:**
- No manual migration required
- Existing repositories continue to work
- Gradual, automatic migration

**Negative:**
- Mixed formats during transition period
- Old fields in files until next sync

---

## ADR-033: Hybrid Change Detection (mtime + Baseline)

### Status
Accepted

### Context
Bidirectional sync needs to determine which local files and remote pages have changed since the last sync. Two approaches exist:

1. **Timestamp-only**: Compare file mtime / remote last_modified against `last_synced`
   - Fast: No file I/O or content comparison
   - Unreliable: File touch updates mtime without content change; clock skew causes false positives

2. **Baseline-only**: Compare current content against stored baseline
   - Accurate: Detects actual content changes
   - Slow: Requires reading every file and comparing strings

### Decision
Use a **hybrid approach** that combines both methods:

1. **mtime check (fast filter)**: If file mtime ≤ `last_synced`, skip baseline check (file definitely unchanged)
2. **Baseline check (confirmation)**: If mtime > `last_synced`, compare content against baseline to confirm actual change

This is implemented via `SyncConfig` extensions:
```python
@dataclass
class SyncConfig:
    # ... existing fields ...
    last_synced: Optional[str] = None  # ISO 8601 timestamp for mtime comparison
    get_baseline: Optional[Callable[[str], Optional[str]]] = None  # Callback to retrieve baseline content
```

And helper methods in `FileMapper`:
```python
def _is_locally_modified(self, file_path: str, local_page: LocalPage, sync_config: SyncConfig) -> bool:
    """Check if local file has been modified using hybrid approach."""
    # Step 1: mtime check (fast filter)
    if sync_config.last_synced:
        file_mtime = os.path.getmtime(file_path)
        last_synced_ts = datetime.fromisoformat(sync_config.last_synced.replace('Z', '+00:00')).timestamp()
        if file_mtime <= last_synced_ts:
            return False  # Definitely not modified

    # Step 2: baseline check (confirmation)
    if sync_config.get_baseline and local_page.page_id:
        baseline_content = sync_config.get_baseline(local_page.page_id)
        if baseline_content is not None:
            current_content = FrontmatterHandler.generate(local_page)
            if current_content == baseline_content:
                return False  # Content unchanged

    return True  # Modified or new

def _is_remotely_modified(self, page_id: str, remote_content: str, sync_config: SyncConfig) -> bool:
    """Check if remote page has been modified by comparing to baseline."""
    if sync_config.get_baseline:
        baseline_content = sync_config.get_baseline(page_id)
        if baseline_content is not None:
            return remote_content != baseline_content
    return True  # Assume modified if no baseline
```

### Consequences
**Positive:**
- Fast: mtime check skips most unchanged files without I/O
- Accurate: Baseline comparison catches false positives from file touch/clock skew
- Scalable: O(1) for unchanged files, O(n) only for actually changed files
- Consistent: Same baseline used for change detection and 3-way merge

**Negative:**
- Requires baseline storage (already needed for 3-way merge)
- Two-step check adds minor complexity
- First sync has no baseline, so all files marked as "potentially changed"
