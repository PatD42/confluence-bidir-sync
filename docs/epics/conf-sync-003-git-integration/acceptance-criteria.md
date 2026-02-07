# Acceptance Criteria: CONF-SYNC-003 - Git Integration

**Epic**: Git Integration for Conflict Detection and Resolution
**Phase**: Epic Validation
**Date**: 2026-01-30

---

## Overview

This epic enables seamless git-based conflict resolution for bidirectional Confluence synchronization. It uses git as the merge engine by maintaining a local git repository that mirrors Confluence content in markdown format.

---

## Core Operations

### Sync Command (Bidirectional with Conflict Resolution)

**Given** a sync operation is initiated
**When** content exists on both local and Confluence
**Then** the tool performs three-way merge using git merge algorithms

**Given** no conflicts are detected during sync
**When** three-way merge completes successfully
**Then** merged content is pushed to both local files and Confluence

**Given** conflicts are detected during sync
**When** batch conflict detection completes across all pages
**Then** all conflict files are created before any merge tool is launched

### Pull Command (Force Confluence → Local)

**Given** `confluence-sync pull` is executed
**When** the command runs
**Then** all local content is overwritten with latest Confluence content
**And** no conflict detection is performed
**And** local git repo `.confluence-sync/{space-key}_md/` is updated to match Confluence

### Push Command (Force Local → Confluence)

**Given** `confluence-sync push` is executed
**When** the command runs
**Then** all Confluence content is overwritten with local content
**And** no conflict detection is performed
**And** local git repo `.confluence-sync/{space-key}_md/` is updated to match new Confluence state

---

## Happy Path Scenarios

### HP-1: Clean Sync (No Conflicts)

**Given**
- Local file modified: `docs/getting-started.md` (version 15)
- Confluence unchanged: page still at version 15
- Git repo `.confluence-sync/MYSPACE_md/` has base version 15 committed

**When** `confluence-sync` runs

**Then**
- Local changes are pushed to Confluence
- Confluence version increments to 16
- Git repo commits new version 16 from Confluence
- No merge conflicts occur

### HP-2: Auto-Merge (Non-Conflicting Changes)

**Given**
- Local file modified: Section A changed (version 15 base)
- Confluence modified: Section B changed (now version 16)
- Changes are in different sections (non-overlapping)

**When** `confluence-sync` runs

**Then**
- Three-way merge succeeds automatically
- Local file contains both Section A and Section B changes
- Merged content pushed to Confluence (version 17)
- Git repo commits merged version 17
- No user intervention required

### HP-3: Batch Conflict Detection and Resolution

**Given**
- Page 1: Conflicting edits in Section A
- Page 2: Conflicting edits in Section B
- Page 3: No conflicts (auto-mergeable)

**When** `confluence-sync` runs

**Then**
1. **Detection Phase**: All pages scanned, conflicts identified for Page 1 and Page 2
2. **Conflict Files Created**:
   - `docs/page-1.md.conflict` created with git conflict markers
   - `docs/page-2.md.conflict` created with git conflict markers
   - Page 3 merged automatically (no conflict file)
3. **User Notification**:
   ```
   Conflicts detected in 2 pages:
   - docs/page-1.md
   - docs/page-2.md

   Launching merge tool...
   ```
4. **Merge Tool Launch**: Configured merge tool opened for each conflict file
5. **Post-Resolution**: User resolves all conflicts, saves merged files
6. **Sync Completion**: All resolved pages pushed to Confluence

---

## Edge Cases

### EC-1: No Local Git Repo Exists

**Given** `.confluence-sync/{space-key}_md/` does not exist
**When** first sync is attempted
**Then**
- Git repo is initialized at `.confluence-sync/{space-key}_md/`
- Current Confluence content (in markdown) is committed as base version
- Sync proceeds normally

### EC-2: Version Mismatch Detection

**Given**
- Local frontmatter shows `confluence_version: 15`
- Confluence API reports current version: 17

**When** sync begins

**Then**
- Tool detects version mismatch (15 != 17)
- Fetches Confluence version 17 as "remote"
- Fetches base version 15 from `.confluence-sync/{space-key}_md/` git history
- Initiates three-way merge

### EC-3: Base Version Not in Git History

**Given**
- Local frontmatter shows `confluence_version: 15`
- Git repo `.confluence-sync/{space-key}_md/` only has versions 10-14 and 16-17 (15 missing)

**When** sync attempts three-way merge

**Then**
- Tool falls back to two-way merge (local vs remote, no base)
- Warns user: "Base version 15 not found, using two-way merge"
- Conflict markers show LOCAL vs CONFLUENCE (no base reference)

### EC-4: Merge Tool Not Found

**Given**
- Config specifies merge tool: `merge_tool: "vscode"`
- VS Code is not installed or not in PATH

**When** conflicts are detected

**Then**
- Tool attempts to launch `code --wait --diff`
- Launch fails with error
- Fallback: Lists conflict files and instructs manual resolution:
  ```
  Error: Merge tool 'vscode' not found.

  Please resolve conflicts manually in:
  - docs/page-1.md.conflict
  - docs/page-2.md.conflict

  Then run: confluence-sync --continue
  ```

### EC-5: User Aborts Conflict Resolution

**Given**
- Merge tool is launched for 3 conflict files
- User resolves 2 files, exits merge tool without resolving 3rd

**When** tool detects incomplete resolution

**Then**
- Sync is aborted
- Changes are not pushed to Confluence
- User sees message:
  ```
  Unresolved conflicts remain:
  - docs/page-3.md.conflict

  Resolve and run: confluence-sync --continue
  ```

### EC-6: XHTML Cache Hit (Optimization)

**Given**
- Confluence page last modified: 2026-01-25 10:30 AM
- Cached XHTML in `.confluence-sync/{space-key}_xhtml/page-123.xhtml` has metadata `last_modified: 2026-01-25 10:30 AM`

**When** sync checks for remote changes

**Then**
- Tool compares timestamps
- Cache hit: No fetch from Confluence API
- Uses cached XHTML for conversion to markdown

### EC-7: XHTML Cache Miss (Fetch Required)

**Given**
- Confluence page last modified: 2026-01-30 14:00 PM
- Cached XHTML metadata shows `last_modified: 2026-01-25 10:30 AM`

**When** sync checks for remote changes

**Then**
- Tool detects cache stale (timestamp mismatch)
- Fetches latest XHTML from Confluence API
- Updates cache with new XHTML and metadata
- Converts to markdown for merge

---

## Error Scenarios

### ERR-1: Invalid Git State

**Given** `.confluence-sync/{space-key}_md/` exists but is not a valid git repo
**When** sync attempts to access git history
**Then**
- Tool detects invalid git directory
- Errors with message:
  ```
  Error: .confluence-sync/MYSPACE_md/ is not a valid git repository.

  Fix: Delete the directory and run sync again to reinitialize.
  ```
- Sync aborts (does not auto-fix to prevent data loss)

### ERR-2: Confluence API Unreachable During Sync

**Given** sync has detected conflicts and created conflict files
**When** Confluence API becomes unreachable
**Then**
- Conflict resolution continues (uses cached data)
- After resolution, push to Confluence fails with:
  ```
  Error: Cannot reach Confluence API to push resolved changes.

  Resolved files saved locally. Retry sync when API is available.
  ```

### ERR-3: Git Merge Command Fails

**Given** three-way merge is attempted
**When** git merge command exits with non-zero status
**Then**
- Tool captures git error output
- Presents error to user:
  ```
  Error: Git merge failed for docs/page-1.md

  Git output:
  [error details]

  Manual intervention required.
  ```

---

## Acceptance Criteria Checklist

### Conflict Detection

- [x] **AC-1.1**: Version mismatch detected by comparing local frontmatter `confluence_version` with Confluence API current version
- [x] **AC-1.2**: Batch detection scans all pages in sync scope before creating any conflict files
- [x] **AC-1.3**: Conflict files created with standard git conflict markers:
  ```markdown
  <<<<<<< LOCAL
  Local changes here
  =======
  Confluence changes here
  >>>>>>> CONFLUENCE
  ```
- [x] **AC-1.4**: Auto-mergeable changes (non-overlapping sections) merge without user intervention

### Three-Way Merge

- [x] **AC-2.1**: Base version retrieved from git repo `.confluence-sync/{space-key}_md/` commit history
- [x] **AC-2.2**: Three-way merge uses git merge algorithms (base + local + remote)
- [x] **AC-2.3**: If base version missing, falls back to two-way merge with warning
- [x] **AC-2.4**: Merge preserves Confluence macros (ac: namespace elements) during round-trip

### Git Repository Management

- [x] **AC-3.1**: Git repo initialized at `.confluence-sync/{space-key}_md/` on first sync
- [x] **AC-3.2**: Each successful sync commits new Confluence state (in markdown) to git repo
- [x] **AC-3.3**: Commit messages include version number: `"Confluence sync: version 17"`
- [x] **AC-3.4**: Git repo tracks only markdown versions (XHTML stored separately in cache)

### XHTML Cache

- [x] **AC-4.1**: XHTML cached at `.confluence-sync/{space-key}_xhtml/{page-id}.xhtml`
- [x] **AC-4.2**: Cache metadata includes `last_modified` timestamp from Confluence API
- [x] **AC-4.3**: Cache hit when Confluence `last_modified` matches cached timestamp (no API fetch)
- [x] **AC-4.4**: Cache miss triggers fetch and cache update

### Merge Tool Integration

- [x] **AC-5.1**: Default merge tool is VS Code (`code --wait --diff`) if not configured
- [x] **AC-5.2**: User can override in `.confluence-sync/config.yaml`:
  ```yaml
  merge_tool: vscode  # or vim, meld, kdiff3, etc.
  ```
- [x] **AC-5.3**: Merge tool launched for each conflict file sequentially
- [x] **AC-5.4**: If merge tool fails to launch, tool provides manual resolution instructions

### Force Operations

- [x] **AC-6.1**: `confluence-sync pull` overwrites all local files with Confluence content (entire sync scope)
- [x] **AC-6.2**: `confluence-sync push` overwrites all Confluence pages with local content (entire sync scope)
- [x] **AC-6.3**: Force operations skip conflict detection entirely
- [x] **AC-6.4**: Force operations update git repo to match post-operation state

### Conflict Resolution Workflow

- [x] **AC-7.1**: Batch mode: All conflicts detected before any merge tool launched
- [x] **AC-7.2**: User resolves all conflicts, then sync resumes
- [x] **AC-7.3**: Unresolved conflicts prevent sync completion
- [x] **AC-7.4**: `confluence-sync --continue` flag allows resuming after manual conflict resolution

### Error Handling

- [x] **AC-8.1**: Invalid git repo detected and reported with recovery instructions
- [x] **AC-8.2**: Network failures during conflict resolution gracefully deferred (push on next sync)
- [x] **AC-8.3**: Git merge failures captured and presented with actionable error messages
- [x] **AC-8.4**: All errors include context: which page, which operation, what failed

---

## E2E Test Scenarios

### E2E-1: Full Conflict Resolution Journey

**Setup**:
1. Initial sync: Page "Getting Started" at version 10
2. Local edit: Change section "Installation"
3. Confluence edit (external): Change section "Installation" (different content)
4. Confluence now at version 11

**Execution**:
```bash
confluence-sync
```

**Expected Flow**:
1. Tool detects version mismatch (local: 10, remote: 11)
2. Fetches Confluence version 11, retrieves base version 10 from git
3. Three-way merge detects conflict in "Installation" section
4. Creates `docs/getting-started.md.conflict` with markers
5. Launches VS Code with conflict file
6. User resolves conflict, saves file
7. Tool pushes merged content to Confluence (version 12)
8. Git repo commits version 12
9. Local file updated with merged content

**Assertions**:
- Confluence page version = 12
- Local file has resolved content
- Git repo has commit for version 12
- No `.conflict` files remain

### E2E-2: Multi-Page Batch Resolution

**Setup**:
1. Three pages: A, B, C all at version 5
2. Local edits to all three pages
3. Confluence edits to pages A and C (external)
4. Page B unchanged on Confluence

**Execution**:
```bash
confluence-sync
```

**Expected Flow**:
1. Batch scan detects conflicts on pages A and C
2. Page B auto-merges (only local changes)
3. Creates `docs/page-a.md.conflict` and `docs/page-c.md.conflict`
4. User notified: "Conflicts in 2 pages"
5. Merge tool launched for A, then C
6. User resolves both
7. All three pages synced to Confluence

**Assertions**:
- Page A: version 6 (merged)
- Page B: version 6 (auto-merged)
- Page C: version 6 (merged)
- Git repo has commits for all versions

### E2E-3: Force Push Overwrites Remote

**Setup**:
1. Page at version 8 on Confluence
2. Local version shows version 6 (outdated)
3. Local has significant edits

**Execution**:
```bash
confluence-sync push
```

**Expected Flow**:
1. No conflict detection performed
2. Local content pushed to Confluence
3. Confluence version increments to 9 (8 + 1)
4. Git repo commits version 9 matching new Confluence state

**Assertions**:
- Confluence version = 9
- Confluence content matches local exactly
- All remote edits (versions 7-8) discarded

### E2E-4: Cache Optimization

**Setup**:
1. Page last modified on Confluence: 2026-01-25
2. Cached XHTML with matching timestamp

**Execution**:
```bash
confluence-sync
```

**Expected Flow**:
1. Tool checks Confluence API for page metadata (lightweight call)
2. Compares `last_modified` timestamp
3. Cache hit: No XHTML fetch
4. Uses cached XHTML for conversion
5. Sync completes without full page fetch

**Assertions**:
- Only 1 API call (metadata check), not 2 (metadata + content)
- Cache hit logged in verbose output

---

## Non-Functional Acceptance Criteria

### Performance

- [x] **NF-1**: Three-way merge completes in <2 seconds for pages up to 50KB
- [x] **NF-2**: Cache hit reduces API calls by 50% for unchanged pages
- [x] **NF-3**: Batch conflict detection completes in <5 seconds for 100 pages

### Reliability

- [x] **NF-4**: No data loss if sync interrupted during conflict resolution
- [x] **NF-5**: Git repo corruption detected and reported (does not auto-fix)
- [x] **NF-6**: XHTML cache corruption triggers re-fetch (no error)

### Usability

- [x] **NF-7**: Conflict markers are standard git format (compatible with all merge tools)
- [x] **NF-8**: Error messages include next action (e.g., "Run: confluence-sync --continue")
- [x] **NF-9**: Progress indicators show: "Scanning page 5/20...", "Resolving conflicts: 2/3 complete"

---

## Out of Scope (Future Enhancements)

- Per-page force push/pull (MVP forces entire sync scope)
- Interactive conflict resolution mode (MVP is batch only)
- Custom git merge strategies (MVP uses default git merge)
- Conflict resolution via web UI (MVP is CLI + merge tool only)
- Automatic conflict resolution using AI (MVP requires human resolution)

---

## Dependencies

**From CONF-SYNC-001**:
- `APIWrapper` for fetching page content and metadata
- `MarkdownConverter` for XHTML ↔ Markdown conversion
- `PageSnapshot` model with `confluence_version` field
- Error handling for network failures

**From CONF-SYNC-002**:
- Local file structure with frontmatter containing `confluence_version`
- Mapping file to track page IDs to file paths
- Directory structure conventions

**External Dependencies**:
- Git CLI installed and available in PATH
- Configured merge tool (VS Code, vim, meld, etc.) installed

---

## Definition of Done

- [x] All acceptance criteria (AC-1.1 through AC-8.4) implemented and tested
- [x] All E2E test scenarios pass
- [x] Non-functional criteria validated (performance, reliability, usability)
- [x] Error messages reviewed for clarity and actionability
- [x] Documentation updated with conflict resolution workflow
- [x] Code coverage >90% for conflict detection and merge logic
- [x] Manual testing completed with multiple merge tools (VS Code, vim)
- [x] Git repo corruption scenarios tested and handled gracefully
