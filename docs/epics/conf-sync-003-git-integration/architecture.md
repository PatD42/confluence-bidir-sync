# Architecture Design: CONF-SYNC-003 - Git Integration

**Epic**: Git Integration for Conflict Detection and Resolution
**Phase**: Architecture Design
**Date**: 2026-01-30

---

## Overview

This document defines the architecture for git-based conflict resolution in confluence-bidir-sync. It specifies components, data models, API contracts, and data flows.

---

## Component Architecture

### High-Level Structure

```
src/
  git_integration/               # NEW MODULE
    __init__.py                  # Package exports
    git_repository.py            # Git repo management
    xhtml_cache.py               # XHTML caching layer
    conflict_detector.py         # Version comparison & conflict detection
    merge_orchestrator.py        # Coordinates merge workflow
    merge_tool.py                # Merge tool integration
    models.py                    # Git-specific data models
    errors.py                    # Git-specific exceptions
```

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      MergeOrchestrator                          │
│  (Coordinates entire sync/merge workflow)                       │
└───────┬──────────────────────────┬──────────────────┬──────────┘
        │                          │                  │
        ▼                          ▼                  ▼
┌───────────────┐         ┌─────────────────┐  ┌──────────────┐
│ GitRepository │         │ ConflictDetector│  │ MergeTool    │
│               │         │                 │  │              │
│ - init_repo() │         │ - detect()      │  │ - launch()   │
│ - commit()    │         │ - get_base()    │  │ - validate() │
│ - get_version()│        │ - compare()     │  │              │
└───────┬───────┘         └────────┬────────┘  └──────────────┘
        │                          │
        ▼                          ▼
┌───────────────┐         ┌─────────────────┐
│  XHTMLCache   │         │ PageOperations  │
│               │         │ (from CONF-001) │
│ - get()       │         │                 │
│ - put()       │         │ - get_snapshot()│
│ - is_valid()  │         │ - apply_ops()   │
└───────────────┘         └─────────────────┘
```

---

## Component Specifications

### 1. GitRepository

**Responsibility**: Manage markdown mirror repository at `.confluence-sync/{space-key}_md/`

**Public API**:
```python
class GitRepository:
    """Manages git repository for Confluence markdown mirror."""

    def __init__(self, repo_path: str):
        """Initialize git repository manager.

        Args:
            repo_path: Path to git repo (e.g., .confluence-sync/MYSPACE_md)
        """

    def init_if_not_exists(self) -> None:
        """Initialize git repo if it doesn't exist.

        Creates directory and runs 'git init'.

        Raises:
            GitRepositoryError: If initialization fails
        """

    def commit_version(
        self,
        page_id: str,
        markdown: str,
        version: int,
        message: Optional[str] = None
    ) -> str:
        """Commit markdown version to git repo.

        Args:
            page_id: Confluence page ID
            markdown: Markdown content to commit
            version: Confluence version number
            message: Optional commit message

        Returns:
            Commit SHA

        Raises:
            GitRepositoryError: If commit fails
        """

    def get_version(self, page_id: str, version: int) -> Optional[str]:
        """Retrieve markdown for specific version from git history.

        Args:
            page_id: Confluence page ID
            version: Version number to retrieve

        Returns:
            Markdown content, or None if version not found

        Raises:
            GitRepositoryError: If git command fails
        """

    def get_latest_version_number(self, page_id: str) -> Optional[int]:
        """Get latest version number committed for page.

        Parses commit messages to extract version numbers.

        Args:
            page_id: Confluence page ID

        Returns:
            Latest version number, or None if no commits

        Raises:
            GitRepositoryError: If git log fails
        """

    def validate_repo(self) -> bool:
        """Check if repo is valid git repository.

        Runs 'git fsck' to detect corruption.

        Returns:
            True if valid, False otherwise
        """
```

**Implementation Notes**:
- Files stored as `{page-id}.md` in flat structure
- Commit messages: `"Page {page_id}: version {version}"`
- Use `subprocess.run()` for git commands with 10-second timeout
- Capture stderr for error messages

**File Structure**:
```
.confluence-sync/MYSPACE_md/
  .git/                  # Git internals
  123456.md              # Page ID 123456
  789012.md              # Page ID 789012
  README.md              # Auto-generated: "Managed by confluence-bidir-sync"
```

---

### 2. XHTMLCache

**Responsibility**: Cache XHTML content to minimize Confluence API calls

**Public API**:
```python
class XHTMLCache:
    """Manages XHTML cache with timestamp validation."""

    def __init__(self, cache_dir: str, max_age_days: int = 7):
        """Initialize XHTML cache.

        Args:
            cache_dir: Cache directory (e.g., .confluence-sync/MYSPACE_xhtml)
            max_age_days: Max age before re-fetch (default: 7 days)
        """

    def get(
        self,
        page_id: str,
        version: int,
        last_modified: datetime
    ) -> Optional[str]:
        """Retrieve XHTML from cache if valid.

        Args:
            page_id: Confluence page ID
            version: Version number
            last_modified: Confluence last_modified timestamp

        Returns:
            Cached XHTML if valid, None if cache miss

        Raises:
            CacheError: If cache file corrupted
        """

    def put(
        self,
        page_id: str,
        version: int,
        xhtml: str,
        last_modified: datetime
    ) -> None:
        """Store XHTML in cache.

        Args:
            page_id: Confluence page ID
            version: Version number
            xhtml: XHTML content to cache
            last_modified: Confluence last_modified timestamp

        Raises:
            CacheError: If write fails
        """

    def invalidate(self, page_id: str) -> None:
        """Delete all cache entries for page.

        Args:
            page_id: Confluence page ID
        """

    def clear_all(self) -> None:
        """Delete all cache entries (all pages)."""
```

**Implementation Notes**:
- Files: `{page_id}_v{version}.xhtml` (XHTML content)
- Metadata: `{page_id}_v{version}.meta.json` (last_modified, cached_at)
- Cache hit: Check if `last_modified` in metadata matches Confluence
- Cache miss: Re-fetch from API, update cache
- Auto-cleanup: Delete entries older than `max_age_days`

**File Structure**:
```
.confluence-sync/MYSPACE_xhtml/
  123456_v15.xhtml       # XHTML content
  123456_v15.meta.json   # {"last_modified": "2026-01-30T10:00:00Z", "cached_at": "..."}
  123456_v16.xhtml
  123456_v16.meta.json
```

---

### 3. ConflictDetector

**Responsibility**: Detect version conflicts and retrieve base versions for merge

**Public API**:
```python
class ConflictDetector:
    """Detects conflicts by comparing local and remote versions."""

    def __init__(
        self,
        page_ops: PageOperations,
        git_repo: GitRepository,
        cache: XHTMLCache
    ):
        """Initialize conflict detector.

        Args:
            page_ops: PageOperations for Confluence API
            git_repo: GitRepository for base versions
            cache: XHTMLCache for XHTML caching
        """

    def detect_conflicts(
        self,
        local_pages: List[LocalPage]
    ) -> ConflictDetectionResult:
        """Batch detect conflicts for multiple pages.

        Args:
            local_pages: List of LocalPage with page_id, local_version, file_path

        Returns:
            ConflictDetectionResult with conflicts and auto-mergeable pages

        Raises:
            APIAccessError: If Confluence API unreachable
        """

    def get_three_way_merge_inputs(
        self,
        page_id: str,
        local_version: int,
        remote_version: int
    ) -> ThreeWayMergeInputs:
        """Fetch base, local (cached), and remote markdown for merge.

        Args:
            page_id: Confluence page ID
            local_version: Version in local frontmatter
            remote_version: Current version on Confluence

        Returns:
            ThreeWayMergeInputs with base, local, remote markdown

        Raises:
            APIAccessError: If Confluence fetch fails
            GitRepositoryError: If base version not in git history
        """
```

**Implementation Notes**:
- Batch metadata check: Fetch all page versions in single API call (if supported)
- Fallback: Parallel fetch with rate limit respect
- Cache lookup: If Confluence `last_modified` matches cache, skip fetch
- Base version: Retrieve from `GitRepository.get_version(page_id, local_version)`

---

### 4. MergeOrchestrator

**Responsibility**: Coordinate entire merge workflow (detection → merge → resolution → push)

**Public API**:
```python
class MergeOrchestrator:
    """Orchestrates conflict detection and resolution workflow."""

    def __init__(
        self,
        page_ops: Optional[PageOperations] = None,
        git_repo: Optional[GitRepository] = None,
        cache: Optional[XHTMLCache] = None,
        detector: Optional[ConflictDetector] = None,
        merge_tool: Optional[MergeTool] = None
    ):
        """Initialize merge orchestrator with dependencies."""

    def sync(
        self,
        local_pages: List[LocalPage],
        strategy: MergeStrategy = MergeStrategy.THREE_WAY
    ) -> SyncResult:
        """Perform bidirectional sync with conflict resolution.

        Workflow:
        1. Detect conflicts (batch)
        2. Auto-merge non-conflicting pages
        3. Create .conflict files for conflicts
        4. Launch merge tool for resolution
        5. Push resolved content to Confluence
        6. Commit new versions to git repo

        Args:
            local_pages: Pages in sync scope
            strategy: Merge strategy (THREE_WAY, FORCE_PUSH, FORCE_PULL)

        Returns:
            SyncResult with success/failure details

        Raises:
            MergeConflictError: If unresolved conflicts remain
            GitRepositoryError: If git operations fail
            APIAccessError: If Confluence push fails
        """

    def force_push(self, local_pages: List[LocalPage]) -> SyncResult:
        """Force push local content to Confluence (no conflict detection).

        Args:
            local_pages: Pages to push

        Returns:
            SyncResult with push details
        """

    def force_pull(self, page_ids: List[str]) -> SyncResult:
        """Force pull Confluence content to local (no conflict detection).

        Args:
            page_ids: Pages to pull

        Returns:
            SyncResult with pull details
        """
```

**Implementation Notes**:
- `sync()` implements batch conflict detection from acceptance criteria
- Creates `.conflict` files with git markers before launching merge tool
- Validates all conflicts resolved before pushing
- Rolls back on error (no partial pushes)

---

### 5. MergeTool

**Responsibility**: Integrate with external merge tools (VS Code, vim, meld, etc.)

**Public API**:
```python
class MergeTool:
    """Launches external merge tools for conflict resolution."""

    def __init__(self, tool_name: str = "vscode", custom_command: Optional[str] = None):
        """Initialize merge tool.

        Args:
            tool_name: Tool name (vscode, vim, meld, kdiff3)
            custom_command: Custom command template with {LOCAL}, {BASE}, {REMOTE}
        """

    def validate_available(self) -> bool:
        """Check if merge tool is installed and in PATH.

        Returns:
            True if available, False otherwise
        """

    def launch(
        self,
        local_file: str,
        base_file: str,
        remote_file: str,
        output_file: str
    ) -> MergeToolResult:
        """Launch merge tool for three-way merge.

        Args:
            local_file: Local version path
            base_file: Base version path
            remote_file: Remote version path
            output_file: Where to save merged result

        Returns:
            MergeToolResult with success status

        Raises:
            MergeToolError: If tool launch fails or exits with error
        """
```

**Implementation Notes**:
- Tool commands:
  - `vscode`: `code --wait --diff {LOCAL} {REMOTE}`
  - `vim`: `vim -d {LOCAL} {BASE} {REMOTE}`
  - `meld`: `meld {LOCAL} {BASE} {REMOTE} --output {OUTPUT}`
- Wait for tool to exit before continuing
- Timeout: 30 minutes (user might take time to resolve)
- If tool fails, provide fallback instructions for manual resolution

---

## Data Models

### New Models (src/git_integration/models.py)

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class MergeStrategy(Enum):
    """Merge strategies for sync operation."""
    THREE_WAY = "three_way"      # Default: git merge with conflict detection
    FORCE_PUSH = "force_push"    # Overwrite Confluence with local
    FORCE_PULL = "force_pull"    # Overwrite local with Confluence


@dataclass
class LocalPage:
    """Represents a local markdown file in sync scope.

    Attributes:
        page_id: Confluence page ID (from frontmatter)
        file_path: Path to local .md file
        local_version: Version from frontmatter
        title: Page title (for display)
    """
    page_id: str
    file_path: str
    local_version: int
    title: str


@dataclass
class ConflictInfo:
    """Information about a detected conflict.

    Attributes:
        page_id: Confluence page ID
        file_path: Local file path
        local_version: Version in local frontmatter
        remote_version: Current Confluence version
        has_base: Whether base version found in git history
    """
    page_id: str
    file_path: str
    local_version: int
    remote_version: int
    has_base: bool


@dataclass
class ConflictDetectionResult:
    """Result of batch conflict detection.

    Attributes:
        conflicts: Pages with conflicts requiring resolution
        auto_mergeable: Pages that can auto-merge (no conflicts)
        errors: Pages that failed conflict detection
    """
    conflicts: List[ConflictInfo]
    auto_mergeable: List[LocalPage]
    errors: List[tuple[str, str]]  # (page_id, error_message)


@dataclass
class ThreeWayMergeInputs:
    """Inputs for three-way git merge.

    Attributes:
        page_id: Confluence page ID
        base_markdown: Base version markdown (from git history)
        local_markdown: Local file markdown
        remote_markdown: Confluence current version markdown
        local_version: Version number for base/local
        remote_version: Version number for remote
    """
    page_id: str
    base_markdown: str
    local_markdown: str
    remote_markdown: str
    local_version: int
    remote_version: int


@dataclass
class MergeResult:
    """Result of git merge operation.

    Attributes:
        success: Whether merge succeeded without conflicts
        merged_markdown: Merged content (if success or after resolution)
        conflict_file: Path to .conflict file (if conflicts)
        git_output: Git merge command output
    """
    success: bool
    merged_markdown: str = ""
    conflict_file: Optional[str] = None
    git_output: str = ""


@dataclass
class MergeToolResult:
    """Result of merge tool execution.

    Attributes:
        success: Whether tool exited successfully
        resolved_content: Merged content from tool
        error: Error message if tool failed
    """
    success: bool
    resolved_content: str = ""
    error: Optional[str] = None


@dataclass
class SyncResult:
    """Overall result of sync operation.

    Attributes:
        success: Whether entire sync succeeded
        pages_synced: Number of pages successfully synced
        pages_failed: Number of pages that failed
        conflicts_resolved: Number of conflicts resolved
        errors: Error messages by page_id
    """
    success: bool
    pages_synced: int
    pages_failed: int
    conflicts_resolved: int
    errors: dict[str, str] = field(default_factory=dict)  # page_id -> error


@dataclass
class CachedPage:
    """Cached XHTML metadata.

    Attributes:
        page_id: Confluence page ID
        version: Version number
        xhtml: XHTML content
        last_modified: Confluence last_modified timestamp
        cached_at: When this entry was cached
    """
    page_id: str
    version: int
    xhtml: str
    last_modified: datetime
    cached_at: datetime
```

### Extended Models (src/page_operations/models.py)

```python
# ADD to existing PageSnapshot:
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
    last_modified: datetime  # NEW FIELD for cache validation
```

---

## Error Hierarchy

### New Exceptions (src/git_integration/errors.py)

```python
from src.confluence_client.errors import ConfluenceError


class GitRepositoryError(ConfluenceError):
    """Raised when git repository operations fail.

    Attributes:
        repo_path: Path to git repository
        message: Error description
        git_output: Git command stderr output
    """

    def __init__(self, repo_path: str, message: str, git_output: str = ""):
        super().__init__(f"Git repository error at {repo_path}: {message}")
        self.repo_path = repo_path
        self.message = message
        self.git_output = git_output


class MergeConflictError(ConfluenceError):
    """Raised when merge conflicts are detected and unresolved.

    Attributes:
        conflicts: List of ConflictInfo for unresolved conflicts
    """

    def __init__(self, conflicts: List[ConflictInfo]):
        page_ids = ", ".join([c.page_id for c in conflicts])
        super().__init__(f"Unresolved merge conflicts for pages: {page_ids}")
        self.conflicts = conflicts


class MergeToolError(ConfluenceError):
    """Raised when merge tool fails to launch or execute.

    Attributes:
        tool_name: Name of merge tool
        error: Error description
    """

    def __init__(self, tool_name: str, error: str):
        super().__init__(f"Merge tool '{tool_name}' failed: {error}")
        self.tool_name = tool_name
        self.error = error


class CacheError(ConfluenceError):
    """Raised when cache operations fail.

    Attributes:
        cache_path: Path to cache file
        message: Error description
    """

    def __init__(self, cache_path: str, message: str):
        super().__init__(f"Cache error at {cache_path}: {message}")
        self.cache_path = cache_path
        self.message = message
```

---

## Data Flows

### Flow 1: Sync with Conflict Resolution

```
User: confluence-sync

1. MergeOrchestrator.sync(local_pages)
   │
   ▼
2. ConflictDetector.detect_conflicts(local_pages)
   │
   ├─► For each page:
   │   - Fetch metadata from Confluence (version, last_modified)
   │   - Compare with local frontmatter version
   │   - Check XHTMLCache for cached content
   │
   └─► Returns: ConflictDetectionResult
       - conflicts: [ConflictInfo, ...]
       - auto_mergeable: [LocalPage, ...]

3. Auto-merge non-conflicting pages:
   │
   ├─► For each auto_mergeable page:
   │   - Fetch remote markdown (via cache)
   │   - Git merge (base=local, remote=confluence)
   │   - Push merged content to Confluence
   │   - Commit to GitRepository
   │
   └─► Update local files

4. Handle conflicts:
   │
   ├─► For each conflict:
   │   - ConflictDetector.get_three_way_merge_inputs()
   │   - Fetch base from GitRepository
   │   - Fetch remote from Confluence (via cache)
   │   - Run: git merge-file base local remote
   │   - If conflict: Create .conflict file with markers
   │
   └─► Launch MergeTool for each .conflict file

5. User resolves conflicts in merge tool
   │
   └─► Saves resolved files, exits tool

6. Validate and push:
   │
   ├─► Check all .conflict files resolved
   │   - If unresolved: Raise MergeConflictError
   │
   ├─► Convert merged markdown to XHTML
   │   - MarkdownConverter.markdown_to_xhtml()
   │
   ├─► Push to Confluence
   │   - PageOperations.apply_operations()
   │
   ├─► Commit to GitRepository
   │   - GitRepository.commit_version()
   │
   └─► Update XHTMLCache
       - cache.put(page_id, version, xhtml, last_modified)

7. Return SyncResult to user
```

### Flow 2: Force Push

```
User: confluence-sync push

1. MergeOrchestrator.force_push(local_pages)
   │
   ▼
2. NO conflict detection
   │
   ▼
3. For each page:
   │
   ├─► Read local markdown
   │
   ├─► Convert to XHTML
   │   - MarkdownConverter.markdown_to_xhtml()
   │
   ├─► Push to Confluence (overwrites remote)
   │   - PageOperations.apply_operations()
   │
   ├─► Commit new Confluence version to GitRepository
   │   - GitRepository.commit_version(page_id, markdown, new_version)
   │
   └─► Update XHTMLCache
       - cache.put(page_id, new_version, xhtml, last_modified)

4. Return SyncResult
```

### Flow 3: Force Pull

```
User: confluence-sync pull

1. MergeOrchestrator.force_pull(page_ids)
   │
   ▼
2. NO conflict detection
   │
   ▼
3. For each page:
   │
   ├─► Fetch latest from Confluence
   │   - PageOperations.get_page_snapshot(page_id)
   │
   ├─► Overwrite local file with markdown
   │   - Write to file_path with frontmatter
   │
   ├─► Commit Confluence version to GitRepository
   │   - GitRepository.commit_version(page_id, markdown, version)
   │
   └─► Update XHTMLCache
       - cache.put(page_id, version, xhtml, last_modified)

4. Return SyncResult
```

---

## Configuration Schema

### .confluence-sync/config.yaml

```yaml
# Space configuration
space_key: MYSPACE
space_name: "My Team Space"

# Git integration settings
git:
  enable: true
  markdown_repo: ".confluence-sync/MYSPACE_md"
  cache_dir: ".confluence-sync/MYSPACE_xhtml"
  auto_init: true  # Auto-initialize git repo if missing

# Merge tool configuration
merge:
  tool: vscode  # Options: vscode, vim, meld, kdiff3, custom
  custom_command: null  # Example: "/usr/local/bin/meld {LOCAL} {BASE} {REMOTE} --output {OUTPUT}"
  timeout_minutes: 30  # Max time to wait for merge tool

# Cache settings
cache:
  enable: true
  max_age_days: 7  # Re-fetch if older than 7 days
  auto_cleanup: true  # Delete old cache entries on startup

# Performance settings
performance:
  parallel_fetches: 10  # Max parallel Confluence API calls
  pandoc_timeout_seconds: 10  # Timeout for each Pandoc conversion
```

---

## API Contracts

### Public API: MergeOrchestrator

**Primary interface for CLI to use:**

```python
from src.git_integration.merge_orchestrator import MergeOrchestrator
from src.git_integration.models import LocalPage, MergeStrategy

# Initialize
orchestrator = MergeOrchestrator()

# Sync with conflict resolution (default)
local_pages = [
    LocalPage(
        page_id="123456",
        file_path="docs/getting-started.md",
        local_version=15,
        title="Getting Started"
    ),
    # ... more pages
]

result = orchestrator.sync(local_pages, strategy=MergeStrategy.THREE_WAY)

if result.success:
    print(f"Synced {result.pages_synced} pages")
else:
    print(f"Failed: {result.errors}")

# Force push
result = orchestrator.force_push(local_pages)

# Force pull
result = orchestrator.force_pull(["123456", "789012"])
```

### Internal API: ConflictDetector

**Used by MergeOrchestrator only:**

```python
from src.git_integration.conflict_detector import ConflictDetector

detector = ConflictDetector(page_ops, git_repo, cache)

# Batch detect conflicts
detection_result = detector.detect_conflicts(local_pages)

for conflict in detection_result.conflicts:
    print(f"Conflict: {conflict.page_id} (v{conflict.local_version} → v{conflict.remote_version})")

# Get merge inputs for conflicting page
inputs = detector.get_three_way_merge_inputs(
    page_id="123456",
    local_version=15,
    remote_version=17
)
# Returns: ThreeWayMergeInputs with base, local, remote markdown
```

---

## Directory Structure After Implementation

```
confluence-bidir-sync/
  .confluence-sync/              # NEW: Git integration data
    config.yaml                  # Space and tool configuration
    MYSPACE_md/                  # Git repo mirroring Confluence in markdown
      .git/                      # Git internals
      123456.md                  # Page 123456 markdown
      789012.md                  # Page 789012 markdown
      README.md                  # "Managed by confluence-bidir-sync"
    MYSPACE_xhtml/               # XHTML cache
      123456_v15.xhtml           # Cached XHTML
      123456_v15.meta.json       # Cache metadata
      123456_v16.xhtml
      123456_v16.meta.json

  src/
    git_integration/             # NEW MODULE
      __init__.py
      git_repository.py
      xhtml_cache.py
      conflict_detector.py
      merge_orchestrator.py
      merge_tool.py
      models.py
      errors.py

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
    fixtures/
      git_test_repos.py
      conflict_scenarios.py
    helpers/
      git_test_utils.py
```

---

## Dependencies

### Python Packages (No New Dependencies)

All git operations use `subprocess.run()` with git CLI, no Python library needed.

### External Tools (Validation Required)

| Tool | Required | Validation |
|------|----------|------------|
| Git CLI | Yes | `git --version` (2.x+) |
| VS Code | No (default merge tool) | `code --version` |
| Vim | No (alternative) | `vim --version` |
| Meld | No (alternative) | `meld --version` |

---

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Conflict detection (100 pages) | <5 seconds | With 80% cache hit |
| Three-way merge (single page) | <2 seconds | Includes Pandoc conversion |
| Batch merge (20 pages) | <10 seconds | Parallel Pandoc |
| Git repo validation | <500ms | `git fsck` on startup |
| Cache lookup | <50ms | File read + JSON parse |

---

## Security Considerations

### Git Repository Security

- **No sensitive data**: Git repo contains markdown, not credentials
- **Local only**: Repo never pushed to remote (no .git/config remote)
- **User permissions**: Respect OS file permissions on `.confluence-sync/`

### XHTML Cache Security

- **No credentials**: Cache contains only XHTML content
- **Temp files**: Use secure temp directory for merge operations
- **Cleanup**: Delete temp files after merge completes

### Subprocess Security

- **No shell=True**: All subprocess calls use list syntax
- **Timeout**: 10-second timeout prevents hangs
- **Input validation**: Validate all paths before passing to git/merge tool

---

## Next Steps

After architecture design approval:

1. **Write ADRs**: Document key decisions
   - ADR-008: Git as merge engine
   - ADR-009: XHTML caching strategy
   - ADR-010: Merge tool integration approach

2. **Define Test Strategy**: Unit vs E2E boundaries

3. **Generate Specs**: Technical specs for Auto Claude implementation
