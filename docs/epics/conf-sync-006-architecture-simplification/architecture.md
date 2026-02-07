---
epic_id: CONF-SYNC-006
title: Architecture - Architecture Simplification
created_date: 2026-01-31
---

# Architecture: CONF-SYNC-006

## Component Changes

### 1. HierarchyBuilder - Single CQL Query

**Before (Recursive API Calls):**
```
build_hierarchy(parent_id)
    └── get_page_by_id(parent_id)           # Call 1
    └── get_page_child_by_type(parent_id)   # Call 2
        └── for each child:
            └── get_page_child_by_type(child_id)  # Call 3..N
                └── recursive...
```

**After (Single CQL Query):**
```
build_hierarchy(parent_id)
    └── search_by_cql("ancestor = {parent_id}")  # Single call
        └── Returns all descendants with metadata
        └── Handle pagination if > 25 results
```

**CQL Query:**
```
ancestor = {parent_page_id} AND space = {space_key}
```

**Expand Parameters:**
```
expand=version,space,ancestors
```

**Response Fields Used:**
- `id`: page_id
- `title`: page title
- `version.when`: last_modified timestamp
- `ancestors`: list of {id, title} for parent chain
- `space.key`: space key

---

### 2. APIWrapper - New CQL Method

```python
class APIWrapper:
    def search_by_cql(
        self,
        cql: str,
        expand: str = "version,space,ancestors",
        limit: int = 25
    ) -> List[Dict[str, Any]]:
        """Execute CQL search and return all results (handles pagination).

        Args:
            cql: CQL query string
            expand: Fields to expand
            limit: Results per page

        Returns:
            List of all matching pages with expanded fields
        """
        all_results = []
        start = 0

        while True:
            response = self._client.cql(
                cql=cql,
                expand=expand,
                start=start,
                limit=limit
            )
            results = response.get('results', [])
            all_results.extend(results)

            # Check for more pages
            if len(results) < limit:
                break
            start += limit

        return all_results
```

---

### 3. LocalPage - Simplified Model

**Before:**
```python
@dataclass
class LocalPage:
    file_path: str
    page_id: Optional[str]
    space_key: str
    title: str
    last_synced: str
    confluence_version: int
    content: str = ""
```

**After:**
```python
@dataclass
class LocalPage:
    file_path: str
    page_id: Optional[str]
    content: str = ""
```

---

### 4. FrontmatterHandler - Minimal Frontmatter

**Generate (After):**
```python
@classmethod
def generate(cls, local_page: LocalPage) -> str:
    frontmatter = {'page_id': local_page.page_id}
    yaml_str = yaml.safe_dump(frontmatter, sort_keys=False)
    return f"---\n{yaml_str}---\n{local_page.content}"
```

**Parse (After):**
```python
@classmethod
def parse(cls, file_path: str, content: str) -> LocalPage:
    # Extract frontmatter
    match = cls.FRONTMATTER_PATTERN.match(content)
    frontmatter = yaml.safe_load(match.group(1))

    # Only page_id needed (can be null for new files)
    page_id = frontmatter.get('page_id')
    if page_id is not None:
        page_id = str(page_id)

    return LocalPage(
        file_path=file_path,
        page_id=page_id,
        content=content[match.end():]
    )
```

---

### 5. CLI Main - No Subcommands

**Before:**
```python
app = typer.Typer()

@app.command()
def sync(...): ...

@app.command()
def init(...): ...
```

**After:**
```python
app = typer.Typer()

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    init: Optional[str] = typer.Option(None, "--init"),
    file: Optional[Path] = typer.Argument(None),
    dry_run: bool = typer.Option(False, "--dry-run"),
    force_push: bool = typer.Option(False, "--force-push"),
    force_pull: bool = typer.Option(False, "--force-pull"),
    logdir: Optional[Path] = typer.Option(None, "--logdir"),
    verbosity: int = typer.Option(0, "-v", "--verbosity"),
    no_color: bool = typer.Option(False, "--no-color"),
):
    _configure_logging(verbosity, logdir)

    if init:
        # Parse "SPACE:Path" and local_path from init and file
        run_init(init, file)
    else:
        run_sync(file, dry_run, force_push, force_pull)
```

---

### 6. Logging Configuration

```python
def _configure_logging(verbosity: int, logdir: Optional[Path] = None) -> None:
    level = {0: logging.WARNING, 1: logging.INFO}.get(verbosity, logging.DEBUG)

    # Format with local timezone (default behavior)
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    handlers = []

    if logdir:
        logdir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_file = logdir / f"confluence-sync-{timestamp}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Always add stderr handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    logging.basicConfig(level=level, handlers=handlers, force=True)
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI (main.py)                           │
│  confluence-sync [--init "SPACE:/"] [FILE] [--dry-run] [--logdir]│
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
            ┌──────────────┐        ┌──────────────┐
            │  InitCommand │        │  SyncCommand │
            └──────────────┘        └──────────────┘
                    │                       │
                    ▼                       ▼
            ┌──────────────┐        ┌──────────────────────────────┐
            │  APIWrapper  │        │       HierarchyBuilder       │
            │ (resolve ID) │        │  search_by_cql("ancestor=X") │
            └──────────────┘        └──────────────────────────────┘
                                            │
                                            ▼
                                    ┌──────────────────┐
                                    │  Single CQL Call │
                                    │  Returns: All    │
                                    │  descendants     │
                                    └──────────────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    │                       │                       │
                    ▼                       ▼                       ▼
            ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
            │    page_id   │        │    title     │        │ last_modified│
            │  ancestors   │        │  space_key   │        │   (version)  │
            └──────────────┘        └──────────────┘        └──────────────┘
                    │                       │                       │
                    └───────────────────────┼───────────────────────┘
                                            │
                                            ▼
                                    ┌──────────────────┐
                                    │  ChangeDetector  │
                                    │ (hybrid: mtime + │
                                    │    baseline)     │
                                    └──────────────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    │                       │                       │
                    ▼                       ▼                       ▼
            ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
            │   to_push    │        │   to_pull    │        │  conflicts   │
            └──────────────┘        └──────────────┘        └──────────────┘
```

---

## Frontmatter Migration

### Reading (Backward Compatible)
```python
# Old format still parseable
---
page_id: "123456"
space_key: "TEAM"           # Ignored
title: "Old Format"         # Ignored
last_synced: "..."          # Ignored
confluence_version: 5       # Ignored
---

# New format
---
page_id: "123456"
---

# Both produce:
LocalPage(file_path="...", page_id="123456", content="...")
```

### Writing (New Format Only)
All writes produce minimal frontmatter:
```yaml
---
page_id: "123456"
---
```

---

## Title Resolution Strategy

```python
def get_title_for_page(local_page: LocalPage, cql_results: Dict) -> str:
    """Determine title for a page.

    Args:
        local_page: Local page data
        cql_results: Dict mapping page_id to CQL result data

    Returns:
        Title string
    """
    # 1. Existing page: use title from CQL
    if local_page.page_id and local_page.page_id in cql_results:
        return cql_results[local_page.page_id]['title']

    # 2. New page: extract from first H1
    h1_match = re.match(r'^#\s+(.+)$', local_page.content, re.MULTILINE)
    if h1_match:
        return h1_match.group(1).strip()

    # 3. Fallback: filename without extension
    filename = Path(local_page.file_path).stem
    return filename
```

---

## Single-File Sync Handling

```python
def run_sync(
    file: Optional[Path],
    dry_run: bool,
    force_push: bool,
    force_pull: bool
) -> ExitCode:
    sync_cmd = SyncCommand()

    # Single file mode: don't update global timestamp
    update_timestamp = file is None

    return sync_cmd.run(
        dry_run=dry_run,
        force_push=force_push,
        force_pull=force_pull,
        single_file=str(file) if file else None,
        update_timestamp=update_timestamp,  # New parameter
    )
```

In SyncCommand:
```python
def run(self, ..., update_timestamp: bool = True) -> ExitCode:
    # ... sync logic ...

    if success and update_timestamp:
        state.last_synced = datetime.now(UTC).isoformat()
        self.state_manager.save(state)
```

---

## Hybrid Change Detection

### Overview
Change detection uses a two-step hybrid approach combining mtime (fast filter) and baseline comparison (accuracy confirmation). See ADR-033 for decision rationale.

### Flow Diagram
```
┌─────────────────────────────────────────────────────────────┐
│                   Local File Change Detection               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Check file mtime │
                    │  vs last_synced   │
                    └──────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
    ┌──────────────────┐            ┌──────────────────┐
    │ mtime ≤ last_synced│          │ mtime > last_synced│
    │ (fast path)       │            │ (check baseline) │
    └──────────────────┘            └──────────────────┘
              │                               │
              ▼                               ▼
    ┌──────────────────┐            ┌──────────────────┐
    │  NOT MODIFIED    │            │ Compare content  │
    │  (skip file)     │            │  to baseline     │
    └──────────────────┘            └──────────────────┘
                                              │
                              ┌───────────────┴───────────────┐
                              │                               │
                              ▼                               ▼
                    ┌──────────────────┐            ┌──────────────────┐
                    │ content = baseline│           │ content ≠ baseline│
                    └──────────────────┘            └──────────────────┘
                              │                               │
                              ▼                               ▼
                    ┌──────────────────┐            ┌──────────────────┐
                    │  NOT MODIFIED    │            │    MODIFIED      │
                    │ (mtime false pos)│            │  (include in sync)│
                    └──────────────────┘            └──────────────────┘
```

### SyncConfig Extensions
```python
@dataclass
class SyncConfig:
    spaces: List[SpaceConfig] = field(default_factory=list)
    page_limit: int = 100
    force_pull: bool = False
    force_push: bool = False
    temp_dir: str = ".confluence-sync/temp"
    # Hybrid change detection fields:
    last_synced: Optional[str] = None  # ISO 8601 timestamp for mtime comparison
    get_baseline: Optional[Callable[[str], Optional[str]]] = None  # Callback for baseline content
```

### CLI Integration
The CLI layer wires up the hybrid change detection:
```python
# In SyncCommand.run():
config.last_synced = state.last_synced
config.get_baseline = self.baseline_manager.get_baseline_content
```

### FileMapper Helper Methods
```python
def _is_locally_modified(self, file_path: str, local_page: LocalPage, sync_config: SyncConfig) -> bool:
    """Check if local file has been modified using hybrid approach."""
    # Step 1: mtime check (fast filter)
    if sync_config.last_synced:
        file_mtime = os.path.getmtime(file_path)
        last_synced_ts = datetime.fromisoformat(
            sync_config.last_synced.replace('Z', '+00:00')
        ).timestamp()
        if file_mtime <= last_synced_ts:
            return False  # Definitely not modified

    # Step 2: baseline check (confirmation)
    if sync_config.get_baseline and local_page.page_id:
        baseline_content = sync_config.get_baseline(local_page.page_id)
        if baseline_content is not None:
            current_content = FrontmatterHandler.generate(local_page)
            if current_content == baseline_content:
                return False  # Content unchanged (mtime was false positive)

    return True  # Modified or new

def _is_remotely_modified(self, page_id: str, remote_content: str, sync_config: SyncConfig) -> bool:
    """Check if remote page has been modified by comparing to baseline."""
    if sync_config.get_baseline:
        baseline_content = sync_config.get_baseline(page_id)
        if baseline_content is not None:
            return remote_content != baseline_content
    return True  # Assume modified if no baseline
```

### Performance Characteristics
| Scenario | mtime Check | Baseline Check | Total I/O |
|----------|-------------|----------------|-----------|
| Unchanged file (mtime not updated) | ✓ (skip) | — | 1 stat() |
| Unchanged file (mtime updated) | ✓ | ✓ (match) | 1 stat() + 2 reads |
| Changed file | ✓ | ✓ (diff) | 1 stat() + 2 reads |
| New file (no baseline) | ✓ | — (no baseline) | 1 stat() |

---

## Error Messages

| Scenario | Message |
|----------|---------|
| Config not found | `Configuration file not found: .confluence-sync/config.yaml`<br>`Run 'confluence-sync --init "SPACE:/" ./local-path' to initialize` |
| CQL query fails | `Failed to query Confluence pages: {error}` |
| No title for new page | `Cannot determine title for new page: {file_path}. Add '# Title' heading or rename file.` |
| Logdir creation fails | `Failed to create log directory: {path}: {error}` |
| Invalid --init format | `Invalid --init format: '{value}'. Expected 'SPACE:Path' (e.g., 'ProductXYZ:/')` |
