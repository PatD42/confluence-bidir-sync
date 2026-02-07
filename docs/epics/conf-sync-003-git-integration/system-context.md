# System Context: CONF-SYNC-003 - Git Integration

**Epic**: Git Integration for Conflict Detection and Resolution
**Phase**: System Context Analysis
**Date**: 2026-01-30

---

## Overview

This document analyzes the system context for implementing git-based conflict resolution. It identifies integration points with existing components, patterns to follow, and inherited constraints.

---

## Integration Points

### 1. Confluence API Integration (CONF-SYNC-001)

**Component**: `src/page_operations/page_operations.py`

**Integration Needs**:
- **Fetch page snapshots**: Use `PageOperations.get_page_snapshot(page_id, version)` to fetch specific versions for three-way merge
- **Fetch page metadata**: Need `last_modified` timestamp for cache validation (not currently in PageSnapshot)
- **Update pages after merge**: Use `PageOperations.apply_operations()` to push merged content

**Required Changes**:
- Extend `PageSnapshot` model to include `last_modified: datetime` field
- Add method to `APIWrapper`: `get_page_metadata(page_id) -> Dict[str, Any]` for lightweight metadata-only fetches

### 2. Content Conversion (CONF-SYNC-001)

**Component**: `src/content_converter/markdown_converter.py`

**Integration Needs**:
- **XHTML to Markdown**: Convert cached XHTML to markdown for git repo commits
- **Markdown to XHTML**: Convert merged markdown back to XHTML for Confluence push
- **Macro preservation**: Ensure macros survive round-trip through git merge

**Pattern to Follow**:
- Conversion happens via `MarkdownConverter.xhtml_to_markdown()` and `markdown_to_xhtml()`
- No changes needed to converter; git integration operates on markdown outputs

### 3. Data Models (CONF-SYNC-001)

**Component**: `src/page_operations/models.py`

**Integration Needs**:
- **PageSnapshot**: Central data structure already has `version: int` for optimistic locking
- **Need to extend**: Add `last_modified: datetime` for cache validation

**Required Changes**:
```python
@dataclass
class PageSnapshot:
    page_id: str
    space_key: str
    title: str
    xhtml: str
    markdown: str
    version: int
    parent_id: Optional[str]
    labels: List[str]
    last_modified: datetime  # NEW FIELD
```

### 4. Error Handling (CONF-SYNC-001)

**Component**: `src/confluence_client/errors.py`

**Integration Needs**:
- Follow typed exception pattern with context
- All exceptions inherit from `ConfluenceError` base

**New Exceptions Needed**:
```python
class GitRepositoryError(ConfluenceError):
    """Raised when git repository operations fail."""
    def __init__(self, repo_path: str, message: str):
        super().__init__(f"Git repository error at {repo_path}: {message}")
        self.repo_path = repo_path
        self.message = message

class MergeConflictError(ConfluenceError):
    """Raised when merge conflicts are detected."""
    def __init__(self, page_id: str, file_path: str):
        super().__init__(f"Merge conflict detected for page {page_id} at {file_path}")
        self.page_id = page_id
        self.file_path = file_path

class MergeToolError(ConfluenceError):
    """Raised when merge tool fails to launch or execute."""
    def __init__(self, tool_name: str, error: str):
        super().__init__(f"Merge tool '{tool_name}' failed: {error}")
        self.tool_name = tool_name
        self.error = error
```

### 5. File Structure (CONF-SYNC-002)

**Component**: To be implemented in CONF-SYNC-002

**Integration Needs**:
- Local markdown files with YAML frontmatter containing `confluence_version`
- Mapping file tracking page IDs to file paths
- Directory structure for organizing pages

**Critical Dependency**:
- Git integration requires frontmatter with `confluence_version` to detect conflicts
- If CONF-SYNC-002 not complete, git integration cannot detect version mismatches
- **Decision**: Implement minimal frontmatter support in CONF-SYNC-003 if needed

---

## Existing Patterns to Follow

### 1. Module Structure Pattern

**Current Structure**:
```
src/
  confluence_client/    # API layer
  content_converter/    # Format conversion
  page_operations/      # High-level operations
  models/               # Shared data structures
```

**New Structure**:
```
src/
  git_integration/      # NEW: Git-based conflict resolution
    __init__.py
    git_repository.py   # Git repo management
    xhtml_cache.py      # XHTML caching
    conflict_detector.py # Version comparison
    merge_orchestrator.py # Merge workflow
    merge_tool.py       # Merge tool integration
    models.py           # Git-specific models
    errors.py           # Git-specific exceptions
```

### 2. Dependency Injection Pattern

**Current Pattern**:
```python
class PageOperations:
    def __init__(self, api: Optional[APIWrapper] = None):
        if api is None:
            auth = Authenticator()
            api = APIWrapper(auth)
        self.api = api
```

**Apply to Git Integration**:
```python
class MergeOrchestrator:
    def __init__(
        self,
        page_ops: Optional[PageOperations] = None,
        git_repo: Optional[GitRepository] = None,
        cache: Optional[XHTMLCache] = None
    ):
        self.page_ops = page_ops or PageOperations()
        self.git_repo = git_repo or GitRepository()
        self.cache = cache or XHTMLCache()
```

### 3. Typed Exception Pattern

**Current Pattern**:
- Base class: `ConfluenceError`
- Specific exceptions with context fields
- Descriptive messages with actionable information

**Apply to Git Integration**:
- New exceptions inherit from `ConfluenceError`
- Include context: `repo_path`, `page_id`, `tool_name`, etc.
- Messages guide user to resolution steps

### 4. Dataclass Pattern

**Current Pattern**:
- Use `@dataclass` for models
- Type hints on all fields
- Optional fields with `Optional[T]`
- Default factories for lists: `field(default_factory=list)`

**Apply to Git Integration**:
```python
@dataclass
class CachedPage:
    page_id: str
    xhtml: str
    last_modified: datetime
    version: int
    cache_path: str
```

### 5. Test Structure Pattern

**Current Structure**:
```
tests/
  unit/              # Fast, no external dependencies
  e2e/               # Full system tests
  fixtures/          # Shared test data
  helpers/           # Test utilities
```

**New Structure**:
```
tests/
  unit/
    test_git_repository.py
    test_xhtml_cache.py
    test_conflict_detector.py
    test_merge_orchestrator.py
    test_merge_tool.py
  e2e/
    test_conflict_resolution_journey.py
    test_force_operations_journey.py
    test_cache_optimization_journey.py
  fixtures/
    git_test_repos.py    # Sample git repos for testing
    conflict_scenarios.py # Sample conflict data
  helpers/
    git_test_utils.py    # Git repo setup/teardown
```

---

## Inherited Constraints

### 1. Macro Preservation (ADR-006)

**Constraint**: Confluence macros (ac: namespace) must survive round-trip conversion

**Impact on Git Integration**:
- Macros converted to HTML comments before git merge
- After merge, comments restored to ac: elements
- **Risk**: Git merge might corrupt HTML comments if not careful

**Mitigation**:
- Use existing `MacroPreserver` (from test helpers) for preservation
- Test macro preservation through merge workflow
- Document macro limitations in conflict scenarios

### 2. Pandoc Dependency (ADR-004)

**Constraint**: Pandoc subprocess for XHTML ↔ Markdown conversion

**Impact on Git Integration**:
- Git repo stores markdown (Pandoc output)
- XHTML cache stores pre-conversion content
- **Performance**: Each merge requires 2-3 Pandoc calls (base, local, remote)

**Mitigation**:
- Cache XHTML aggressively to minimize Pandoc calls
- Only re-convert when version changes
- Consider batch conversion for multi-page merges

### 3. Optimistic Locking (ADR-007)

**Constraint**: Version numbers for conflict detection

**Impact on Git Integration**:
- Conflict detection relies on version comparison
- Local frontmatter must track `confluence_version`
- **Failure mode**: If version metadata missing, cannot detect conflicts

**Mitigation**:
- Validate frontmatter before merge attempt
- Fail fast if `confluence_version` not found
- Clear error message guiding user to fix frontmatter

### 4. Rate Limiting (ADR-005)

**Constraint**: 429 retry with exponential backoff

**Impact on Git Integration**:
- Multi-page conflict detection hits API repeatedly
- Fetching multiple versions (base, current) doubles API calls

**Mitigation**:
- Batch metadata checks (single API call for multiple pages)
- Cache XHTML aggressively to avoid re-fetching
- Implement parallel fetching with rate limit respect

### 5. Fail-Fast Philosophy (ADR-005)

**Constraint**: Non-transient errors fail immediately, no retry

**Impact on Git Integration**:
- Git command failures abort immediately
- Merge tool launch failures abort immediately
- **User experience**: Clear error messages with next steps

**Mitigation**:
- Pre-validate git installation before merge
- Pre-validate merge tool availability
- Provide actionable error messages: "Install git" or "Configure merge_tool"

---

## External Dependencies

### 1. Git CLI

**Requirement**: Git 2.x+ installed and in PATH

**Usage**:
- `git init` - Initialize markdown mirror repo
- `git add` - Stage markdown changes
- `git commit` - Commit Confluence versions
- `git merge-file` - Three-way merge algorithm
- `git log` - Retrieve historical versions

**Validation**:
```python
def validate_git_installed() -> bool:
    """Check if git is available in PATH."""
    result = subprocess.run(["git", "--version"], capture_output=True)
    return result.returncode == 0
```

### 2. Merge Tools (Optional, Configurable)

**Default**: VS Code (`code --wait --diff`)

**Supported Alternatives**:
- `vim` - Vimdiff
- `meld` - Meld (graphical)
- `kdiff3` - KDiff3 (graphical)
- Any tool accepting 3-file syntax: `tool LOCAL BASE REMOTE`

**Validation**:
```python
def validate_merge_tool(tool_name: str) -> bool:
    """Check if merge tool is available in PATH."""
    tool_commands = {
        "vscode": ["code", "--version"],
        "vim": ["vim", "--version"],
        "meld": ["meld", "--version"],
    }
    cmd = tool_commands.get(tool_name, [tool_name, "--version"])
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0
```

---

## System Boundaries

### What Git Integration Owns

- Git repository management at `.confluence-sync/{space-key}_md/`
- XHTML cache management at `.confluence-sync/{space-key}_xhtml/`
- Conflict detection via version comparison
- Three-way merge orchestration
- Merge tool integration
- Conflict file generation with git markers

### What Git Integration Does NOT Own

- Confluence API calls (delegated to `PageOperations`)
- XHTML/Markdown conversion (delegated to `MarkdownConverter`)
- Local file structure (delegated to CONF-SYNC-002)
- CLI commands (delegated to CONF-SYNC-004)

---

## Configuration Requirements

### New Config File: `.confluence-sync/config.yaml`

```yaml
# Space configuration
space_key: MYSPACE
space_name: "My Team Space"

# Git integration settings
git:
  enable: true
  markdown_repo: ".confluence-sync/MYSPACE_md"
  cache_dir: ".confluence-sync/MYSPACE_xhtml"

# Merge tool configuration
merge:
  tool: vscode  # vscode, vim, meld, kdiff3, custom
  custom_command: null  # Override: /path/to/tool {LOCAL} {BASE} {REMOTE}

# Performance settings
cache:
  enable: true
  max_age_days: 7  # Re-fetch if cache older than 7 days
```

---

## Data Flow Analysis

### Sync with Conflict Resolution

```
1. User runs: confluence-sync

2. Conflict Detection Phase:
   ┌─────────────────────────────────────────┐
   │ For each page in sync scope:            │
   │ - Read local frontmatter (version)      │
   │ - Fetch Confluence metadata (version)   │
   │ - Compare versions                      │
   └─────────────────────────────────────────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
   No Conflict           Conflict Detected
   (auto-merge)          (queue for resolution)

3. Fetch Phase (only for conflicts):
   ┌─────────────────────────────────────────┐
   │ - Check XHTML cache (timestamp match?)  │
   │   Cache Hit: Use cached XHTML            │
   │   Cache Miss: Fetch from API, update cache│
   │ - Convert XHTML to markdown (Pandoc)    │
   │ - Fetch base version from git history   │
   └─────────────────────────────────────────┘

4. Merge Phase:
   ┌─────────────────────────────────────────┐
   │ For each conflict:                       │
   │ - Run: git merge-file LOCAL BASE REMOTE │
   │ - If success: Auto-merged               │
   │ - If failure: Create .conflict file     │
   └─────────────────────────────────────────┘

5. Resolution Phase (if conflicts):
   ┌─────────────────────────────────────────┐
   │ - Launch merge tool for each .conflict  │
   │ - User resolves conflicts, saves files  │
   │ - Validate all conflicts resolved       │
   └─────────────────────────────────────────┘

6. Push Phase:
   ┌─────────────────────────────────────────┐
   │ - Convert merged markdown to XHTML      │
   │ - Push to Confluence (optimistic lock)  │
   │ - Commit new version to git repo        │
   │ - Update XHTML cache                    │
   └─────────────────────────────────────────┘
```

---

## Performance Considerations

### API Call Optimization

**Problem**: Version checking for 100 pages = 100 API calls

**Solution**: Batch metadata endpoint (if available in Confluence API v2)
```python
# Instead of 100 individual calls:
for page_id in page_ids:
    metadata = api.get_page_by_id(page_id, expand="version")

# Use single batch call (if API supports):
all_metadata = api.get_pages_batch(page_ids, expand="version")
```

**Fallback**: If batch not available, parallelize with rate limit respect

### XHTML Cache Hit Rate

**Goal**: >80% cache hit rate for typical workflows

**Strategy**:
- Cache keyed by `{page_id}_{version}.xhtml`
- Metadata file: `{page_id}_{version}.meta.json` with `last_modified` timestamp
- Cache invalidation: Delete when `last_modified` changes

**Expected Savings**:
- Cache hit: 1 API call (metadata check)
- Cache miss: 2 API calls (metadata + content)
- **50% reduction** in API calls for unchanged pages

### Git Merge Performance

**Expected**:
- `git merge-file` for 50KB markdown: <100ms
- Batch of 20 pages: <2 seconds total

**Bottleneck**: Pandoc conversion, not git merge
- Each page requires 2-3 Pandoc calls (base, local, remote to markdown)
- Pandoc subprocess: ~200ms per call
- **Mitigation**: Parallelize Pandoc conversions

---

## Risk Assessment

### High Risk: Git Repo Corruption

**Scenario**: User manually edits `.confluence-sync/{space-key}_md/` repo

**Impact**: Cannot retrieve base versions, three-way merge fails

**Mitigation**:
- Document repo as "managed by tool, do not edit manually"
- Detect corruption: `git fsck` on startup
- Recovery: Delete repo, reinitialize from Confluence (warn user of data loss)

### Medium Risk: XHTML Cache Stale

**Scenario**: Confluence page updated, cache not invalidated

**Impact**: Merge uses outdated content, conflicts incorrect

**Mitigation**:
- Always fetch metadata (lightweight) to check `last_modified`
- Cache only used if timestamp matches
- If in doubt, re-fetch

### Medium Risk: Merge Tool Unavailable

**Scenario**: VS Code not installed, user config invalid

**Impact**: Cannot resolve conflicts, sync aborted

**Mitigation**:
- Validate tool on startup
- Provide fallback instructions for manual resolution
- Support multiple tools (vim, meld, kdiff3)

### Low Risk: Pandoc Failure During Merge

**Scenario**: Pandoc hangs or crashes during conversion

**Impact**: Single page merge fails

**Mitigation**:
- 10-second timeout per Pandoc call
- Isolate failures: One page failure doesn't abort entire sync
- Retry Pandoc call once on failure

---

## Feasibility Assessment

### ✅ Feasible

Git-based conflict resolution is **feasible** with the following conditions:

1. **Git CLI available**: Required, must validate on startup
2. **CONF-SYNC-002 frontmatter**: Minimal implementation needed (confluence_version field)
3. **XHTML caching**: Critical for performance, straightforward to implement
4. **Merge tool configurable**: Default to VS Code, support alternatives

### ⚠️ Feasible with Constraints

**Constraint 1**: CONF-SYNC-002 dependency
- **Issue**: Need frontmatter with `confluence_version`
- **Solution**: Implement minimal frontmatter in CONF-SYNC-003 if CONF-SYNC-002 incomplete
- **Scope**: Just version field, not full file mapping

**Constraint 2**: API rate limits
- **Issue**: Multi-page conflict detection hits API repeatedly
- **Solution**: XHTML cache reduces fetches by 50%
- **Acceptable**: Users can wait 5-10 seconds for 100 pages

**Constraint 3**: Macro preservation through merge
- **Issue**: Git merge might corrupt HTML comment macros
- **Solution**: Test macro preservation in E2E scenarios
- **Acceptable**: If macros corrupted, tool fails loudly (doesn't silently lose macros)

---

## Integration Summary

| Component | Integration Point | Changes Required |
|-----------|-------------------|------------------|
| PageOperations | Fetch snapshots with version | Add `last_modified` to PageSnapshot |
| APIWrapper | Metadata fetches | Add `get_page_metadata()` method |
| MarkdownConverter | XHTML ↔ Markdown | None (reuse existing) |
| Error Hierarchy | New exceptions | Add 3 new exception types |
| CONF-SYNC-002 | Frontmatter version | Minimal implementation if incomplete |
| Git CLI | External dependency | Validate installation on startup |
| Merge Tools | External optional | Support multiple, default VS Code |

---

## Next Steps

After this system context analysis, proceed to:

1. **Architecture Design**: Define component structure, APIs, and data flows
2. **ADRs**: Document key decisions (git merge strategy, cache design, tool selection)
3. **Test Strategy**: Define test boundaries, mock strategies, and E2E scenarios
4. **Spec Generation**: Create technical specs for Auto Claude implementation
