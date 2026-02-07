# Architecture Decision Records: CONF-SYNC-003

**Epic**: Git Integration for Conflict Detection and Resolution
**Date**: 2026-01-30

---

## ADR-008: Use Git as Merge Engine

### Status
Accepted

### Context
Need to perform three-way merge for concurrent edits between local markdown and Confluence content. Multiple approaches possible:
1. **Implement custom merge algorithm** - Write Python difflib-based three-way merge
2. **Use existing merge library** - Use library like `merge3` or `python-diff-match-patch`
3. **Leverage git CLI** - Use `git merge-file` as subprocess
4. **Leverage git library** - Use GitPython or pygit2

### Decision
**Use git CLI with `git merge-file` command** for three-way merge.

### Rationale

**Why git CLI?**
- ✅ Battle-tested merge algorithms (used by millions of developers)
- ✅ Handles complex conflict scenarios (overlapping edits, whitespace, etc.)
- ✅ Standard conflict marker format (compatible with all tools)
- ✅ Fast (written in C)
- ✅ Already required for markdown repo management
- ✅ Zero new Python dependencies

**Why not custom algorithm?**
- ❌ Reinventing the wheel (git merge is battle-tested)
- ❌ Edge cases poorly handled (whitespace, line endings, etc.)
- ❌ Maintenance burden

**Why not merge library?**
- ❌ Additional Python dependency
- ❌ Less mature than git
- ❌ Non-standard conflict markers (incompatible with merge tools)

**Why not GitPython/pygit2?**
- ❌ Heavy dependencies (especially pygit2 with libgit2)
- ❌ API complexity for simple merge operation
- ❌ Still uses git under the hood

### Implementation

**Git repo structure**:
- Repo at `.confluence-sync/{space-key}_md/`
- Files: `{page-id}.md` (flat structure)
- Commits: Each Confluence version committed with message `"Page {page_id}: version {version}"`

**Merge workflow**:
```bash
# 1. Write base, local, remote to temp files
echo "$base_markdown" > /tmp/base.md
echo "$local_markdown" > /tmp/local.md
echo "$remote_markdown" > /tmp/remote.md

# 2. Run git merge-file
git merge-file -p /tmp/local.md /tmp/base.md /tmp/remote.md > /tmp/merged.md

# 3. Check exit code
# 0 = clean merge
# >0 = conflicts (merged.md has conflict markers)
```

**Conflict marker format**:
```markdown
<<<<<<< LOCAL
Local changes here
=======
Confluence changes here
>>>>>>> CONFLUENCE
```

### Consequences

**Positive**:
- Reliable merge with proven algorithm
- Compatible with all standard merge tools
- No new Python dependencies
- Fast performance

**Negative**:
- Git CLI must be installed (validation required)
- Subprocess overhead (~50ms per merge call)
- Conflict markers might be unfamiliar to non-git users (mitigated by tool integration)

**Risks**:
- Git not installed: Validate on startup, fail with clear message
- Git version too old: Require git 2.x+, validate version

---

## ADR-009: XHTML Caching with Timestamp Validation

### Status
Accepted

### Context
Three-way merge requires fetching base and remote versions from Confluence. For 100 pages with conflicts, this could mean 200+ API calls (base + remote for each). Need caching to minimize API calls.

Cache strategies:
1. **No caching** - Fetch every time (simple, slow)
2. **Version-based cache** - Cache by `{page_id}_{version}.xhtml` (fast, no validation)
3. **Timestamp-validated cache** - Cache with `last_modified` check (balanced)
4. **TTL-based cache** - Cache expires after N days (risky, might be stale)

### Decision
**Use timestamp-validated cache** with version-based keys.

### Rationale

**Cache key**: `{page_id}_v{version}.xhtml`
- Unique per version
- Never stale (version immutable in Confluence history)

**Cache validation**: Check `last_modified` timestamp
- Lightweight API call (metadata only, no content fetch)
- If `last_modified` matches cached metadata, use cache
- If mismatch, re-fetch and update cache

**Why not version-only cache?**
- ❌ Cache grows indefinitely (every historical version stored)
- ❌ No cleanup mechanism

**Why not TTL-only?**
- ❌ Might use stale cache if content changed recently
- ❌ Arbitrary expiration (7 days might be too short or too long)

### Implementation

**Cache structure**:
```
.confluence-sync/MYSPACE_xhtml/
  123456_v15.xhtml         # XHTML content
  123456_v15.meta.json     # {"last_modified": "2026-01-30T10:00:00Z", "cached_at": "..."}
```

**Validation flow**:
```python
def get_cached_xhtml(page_id: str, version: int, last_modified: datetime) -> Optional[str]:
    cache_path = f".confluence-sync/MYSPACE_xhtml/{page_id}_v{version}.xhtml"
    meta_path = f".confluence-sync/MYSPACE_xhtml/{page_id}_v{version}.meta.json"

    if not (os.path.exists(cache_path) and os.path.exists(meta_path)):
        return None  # Cache miss

    with open(meta_path) as f:
        meta = json.load(f)

    if meta["last_modified"] != last_modified.isoformat():
        return None  # Stale cache

    with open(cache_path) as f:
        return f.read()  # Cache hit
```

**Cleanup strategy**:
- On startup: Delete cache entries older than `max_age_days` (default: 7 days)
- Rationale: Historical versions rarely accessed after a week

### Consequences

**Positive**:
- 50% reduction in API calls for unchanged pages
- Fast validation (metadata check ~50ms vs full fetch ~200ms)
- Predictable cleanup (old versions auto-deleted)

**Negative**:
- Disk usage: ~50KB per cached page version (acceptable)
- Metadata check still requires API call (but lightweight)

**Performance**:
- Cache hit: 1 API call (metadata check) + 1 file read (~50ms)
- Cache miss: 2 API calls (metadata + content) + 1 file write (~250ms)
- Net savings: 200ms per cache hit

**Risks**:
- Disk space: 1000 pages × 5 versions × 50KB = 250MB (acceptable for modern systems)
- Cache corruption: Detect on read, re-fetch if corrupted

---

## ADR-010: Configurable Merge Tools with VS Code Default

### Status
Accepted

### Context
After git merge creates conflict files, user must resolve conflicts. Need to integrate with merge tools:
1. **Hardcode VS Code** - Assume VS Code installed
2. **Hardcode vim** - Assume vim installed (safer, but poor UX)
3. **Auto-detect available tools** - Check PATH for vscode, vim, meld, etc.
4. **User-configurable with default** - Config file specifies tool, default to VS Code

### Decision
**User-configurable with VS Code default**, fallback to manual resolution.

### Rationale

**Default to VS Code**:
- ✅ Popular among developers (70%+ install base)
- ✅ Excellent diff/merge UI
- ✅ `code --wait` waits for file save before exiting
- ✅ Cross-platform (macOS, Linux, Windows)

**Support alternatives**:
- Vim (universal on Unix systems)
- Meld (graphical, popular on Linux)
- KDiff3 (graphical, cross-platform)
- Custom command (power users)

**Fallback to manual**:
- If tool not available, list conflict files and instructions
- User resolves manually, runs `confluence-sync --continue`

**Why not auto-detect?**
- ❌ Unpredictable behavior (might pick wrong tool)
- ❌ Confusion if user expects specific tool

**Why not hardcode vim?**
- ❌ Poor UX for non-vim users
- ❌ Steep learning curve for merge workflow

### Implementation

**Configuration**:
```yaml
# .confluence-sync/config.yaml
merge:
  tool: vscode  # Options: vscode, vim, meld, kdiff3, custom
  custom_command: null  # Example: "/usr/local/bin/difftool {LOCAL} {BASE} {REMOTE}"
```

**Tool commands**:
```python
MERGE_TOOLS = {
    "vscode": ["code", "--wait", "--diff", "{LOCAL}", "{REMOTE}"],
    "vim": ["vim", "-d", "{LOCAL}", "{BASE}", "{REMOTE}"],
    "meld": ["meld", "{LOCAL}", "{BASE}", "{REMOTE}", "--output", "{OUTPUT}"],
    "kdiff3": ["kdiff3", "{BASE}", "{LOCAL}", "{REMOTE}", "-o", "{OUTPUT}"],
}
```

**Validation**:
```python
def validate_merge_tool(tool_name: str) -> bool:
    """Check if merge tool is available in PATH."""
    tool_command = MERGE_TOOLS.get(tool_name)
    if not tool_command:
        return False  # Unknown tool

    # Check first command in PATH
    binary = tool_command[0]
    return shutil.which(binary) is not None
```

**Fallback workflow**:
```python
if not validate_merge_tool(config.merge.tool):
    print(f"Merge tool '{config.merge.tool}' not found.")
    print("Please resolve conflicts manually in:")
    for conflict_file in conflict_files:
        print(f"  - {conflict_file}")
    print("\nThen run: confluence-sync --continue")
    sys.exit(1)
```

### Consequences

**Positive**:
- User choice (vim users can use vim, VS Code users can use VS Code)
- Graceful degradation (manual fallback if tool unavailable)
- Clear error messages guiding to resolution

**Negative**:
- Configuration required for non-VS Code users
- Validation overhead (check tool on every sync)

**Risks**:
- Tool installed but not in PATH: Provide clear error with PATH suggestion
- Tool crashes: Conflict files remain, user can re-run or resolve manually

---

## ADR-011: Batch Conflict Detection with Parallel Fetches

### Status
Accepted

### Context
Conflict detection for 100 pages requires checking version for each page. Two approaches:
1. **Sequential checks** - Loop through pages, fetch metadata one-by-one
2. **Batch API call** - Single API call with multiple page IDs (if API supports)
3. **Parallel fetches** - Concurrent API calls with rate limit respect

### Decision
**Parallel fetches with rate limit pooling** (fallback if batch API unavailable).

### Rationale

**Confluence API v2 batch support**: Unknown, needs investigation
- If batch endpoint exists: Use it (ideal, 1 API call for 100 pages)
- If not: Use parallel fetches

**Parallel fetch strategy**:
- `concurrent.futures.ThreadPoolExecutor` with pool size 10
- Rate limit: If 429 received, apply backoff to entire pool
- Progress indicator: "Checking page 5/100..."

**Why not sequential?**
- ❌ Slow (100 pages × 200ms = 20 seconds)
- ❌ Poor user experience

**Why not single-threaded async?**
- ❌ Added complexity (asyncio + aiohttp)
- ❌ Requires refactoring existing sync API wrapper

### Implementation

**Batch detection**:
```python
def detect_conflicts_batch(
    local_pages: List[LocalPage]
) -> ConflictDetectionResult:
    """Batch detect conflicts with parallel fetches."""

    conflicts = []
    auto_mergeable = []
    errors = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all fetch tasks
        futures = {
            executor.submit(check_single_page, page): page
            for page in local_pages
        }

        # Collect results with progress
        for i, future in enumerate(as_completed(futures)):
            page = futures[future]
            print(f"Checking page {i+1}/{len(local_pages)}...")

            try:
                result = future.result()
                if result.has_conflict:
                    conflicts.append(result)
                else:
                    auto_mergeable.append(page)
            except Exception as e:
                errors.append((page.page_id, str(e)))

    return ConflictDetectionResult(conflicts, auto_mergeable, errors)
```

**Rate limit handling**:
- If any thread hits 429, apply exponential backoff to all threads
- Shared backoff state across pool

### Consequences

**Positive**:
- Fast (100 pages in ~2-3 seconds with 10 threads)
- Respects rate limits
- Progress indicator improves UX

**Negative**:
- Complexity (thread pool management)
- Rate limit handling requires shared state

**Performance**:
- Sequential: 100 pages × 200ms = 20 seconds
- Parallel (10 threads): 100 pages / 10 threads × 200ms = 2 seconds

---

## ADR-012: Minimal CONF-SYNC-002 Frontmatter Dependency

### Status
Accepted

### Context
Git integration requires `confluence_version` in frontmatter to detect conflicts. CONF-SYNC-002 (File Structure & Mapping) is not yet implemented. Options:
1. **Block on CONF-SYNC-002** - Wait for full implementation
2. **Implement full frontmatter in CONF-SYNC-003** - Duplicate effort
3. **Implement minimal frontmatter in CONF-SYNC-003** - Just `confluence_version`

### Decision
**Implement minimal frontmatter** in CONF-SYNC-003, extend in CONF-SYNC-002.

### Rationale

**Minimal frontmatter for git integration**:
```yaml
---
page_id: "123456"
confluence_version: 15
---

# Page Content
```

**Why not wait for CONF-SYNC-002?**
- ❌ Blocks git integration epic
- ❌ CONF-SYNC-002 might include complex mapping logic unneeded for git

**Why not duplicate full frontmatter?**
- ❌ Duplicate effort
- ❌ Conflicts when CONF-SYNC-002 implemented

**Minimal scope**:
- Read frontmatter: Extract `page_id` and `confluence_version`
- Write frontmatter: Update `confluence_version` after sync
- **Out of scope**: File mapping, hierarchy, labels, title changes

### Implementation

**Frontmatter parser (minimal)**:
```python
import yaml

def extract_version_from_frontmatter(file_path: str) -> int:
    """Extract confluence_version from YAML frontmatter."""
    with open(file_path) as f:
        content = f.read()

    # Split frontmatter
    if not content.startswith("---\n"):
        raise ValueError("No frontmatter found")

    parts = content.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError("Invalid frontmatter format")

    frontmatter = yaml.safe_load(parts[1])
    return frontmatter["confluence_version"]

def update_version_in_frontmatter(file_path: str, new_version: int) -> None:
    """Update confluence_version in frontmatter."""
    with open(file_path) as f:
        content = f.read()

    parts = content.split("---\n", 2)
    frontmatter = yaml.safe_load(parts[1])
    frontmatter["confluence_version"] = new_version

    # Reconstruct file
    new_content = f"---\n{yaml.dump(frontmatter)}---\n{parts[2]}"
    with open(file_path, "w") as f:
        f.write(new_content)
```

**Validation**:
- Fail fast if frontmatter missing
- Clear error: "File {file_path} missing frontmatter with confluence_version"

### Consequences

**Positive**:
- Unblocks git integration epic
- Minimal scope (just version tracking)
- Easy to extend in CONF-SYNC-002

**Negative**:
- Slight duplication with future CONF-SYNC-002 work
- Need to ensure compatibility when CONF-SYNC-002 extends frontmatter

**Compatibility plan**:
- CONF-SYNC-002 will add fields: `title`, `space_key`, `parent_id`, `labels`
- Existing `page_id` and `confluence_version` remain unchanged
- Git integration only reads/writes `confluence_version`, ignores other fields

---

## Summary of Decisions

| ADR | Decision | Impact |
|-----|----------|--------|
| ADR-008 | Use git CLI for merge | Reliable, fast, no new deps |
| ADR-009 | Timestamp-validated XHTML cache | 50% API call reduction |
| ADR-010 | Configurable merge tools, VS Code default | User choice, good UX |
| ADR-011 | Parallel conflict detection | 10x faster for large page sets |
| ADR-012 | Minimal frontmatter in CONF-SYNC-003 | Unblocks epic, extends in CONF-SYNC-002 |
