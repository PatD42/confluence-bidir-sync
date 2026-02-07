# Architecture Decision Records - CONF-SYNC-005

---

## ADR-017: Independent Page Deletion Detection

**Status**: Accepted

**Context**:
When a Confluence page is deleted, child pages may or may not be affected. A parent page deletion could also be confused with a page move.

**Decision**:
Detect each page deletion independently by checking if `page_id` exists in Confluence. Do not automatically cascade deletions to child files.

**Rationale**:
- Each page has its own `page_id` tracked independently
- A page move appears as "page exists elsewhere" not "page deleted"
- Avoids accidental deletion of child content when parent moved
- Git history provides recovery for incorrectly deleted files

**Consequences**:
- (+) Safer deletion behavior
- (+) Move vs delete disambiguation
- (-) Each page requires existence check (mitigated by batch CQL query)

---

## ADR-018: No Deletion Confirmation Prompts

**Status**: Accepted

**Context**:
Original design included interactive confirmation for deletions. User feedback indicated this complicates scripted/automated usage.

**Decision**:
Deletions execute without confirmation prompts. Users preview operations with `--dryrun` before running actual sync.

**Rationale**:
- `--dryrun` provides safe preview mechanism
- Consistent with Unix philosophy (commands do what asked)
- Enables CI/CD and scripted usage
- Git history serves as backup for accidental deletions

**Consequences**:
- (+) Scriptable/automatable
- (+) Simpler code (no interactive prompts)
- (-) Users must remember to use `--dryrun` for safety

---

## ADR-019: Move Detection via CQL Ancestors

**Status**: Accepted

**Context**:
Detecting page moves requires comparing local folder structure with Confluence hierarchy. Options:
1. Store `parent_id` in frontmatter
2. Query Confluence for parent via individual API calls
3. Use CQL with `expand=ancestors`

**Decision**:
Use CQL search with `expand=ancestors` to get parent chain for all pages in a single query.

**Rationale**:
- Single API call vs N individual calls
- Ancestors provides full path for deep hierarchies
- No frontmatter pollution with `parent_id`
- Consistent with minimal frontmatter principle (ADR-015)

**Consequences**:
- (+) Efficient API usage
- (+) Clean frontmatter
- (-) Slightly larger response payload
- (-) Requires parsing ancestors array

---

## ADR-020: State File Tracks Page IDs

**Status**: Accepted

**Context**:
To detect local deletions (file removed), we need to know which page_ids were previously tracked.

**Decision**:
Extend `.confluence-sync/state.yaml` to include `tracked_pages` list with page_id → local_path mapping.

```yaml
last_synced: "2026-01-31T10:00:00Z"
tracked_pages:
  - page_id: "12345"
    local_path: "docs/page.md"
```

**Rationale**:
- Central location for sync state (already exists)
- Enables "file deleted locally" detection
- Enables orphan detection (page_id in state but no file)
- Single source of truth for tracked pages

**Consequences**:
- (+) Local deletion detection works
- (+) State file already managed atomically
- (-) State file grows with page count
- (-) State can become stale (mitigated by sync updates)

---

## ADR-021: Confluence Trash vs Permanent Delete

**Status**: Accepted

**Context**:
Confluence API supports both trash (soft delete) and permanent delete.

**Decision**:
Use trash (soft delete) only. Pages moved to Confluence trash can be recovered via UI.

**Rationale**:
- Safety: users can recover accidentally deleted pages
- Consistent with Confluence UI behavior
- Matches "git history as backup" philosophy
- Permanent delete would require explicit flag (not needed for MVP)

**Consequences**:
- (+) Recoverable deletions
- (+) Safer default
- (-) Trash accumulation (user responsibility to empty)

---

## ADR-022: Hidden Baseline Repository for 3-Way Merge

**Status**: Accepted

**Context**:
Timestamp-based detection identifies WHEN conflicts occur (both sides changed). But to AUTO-RESOLVE conflicts, we need to know WHAT changed. 3-way merge requires:
- BASE: common ancestor (content at last sync)
- OURS: current local content
- THEIRS: current remote content (fetched from Confluence)

Options considered:
1. Use user's git repo - rejected: interferes with user workflow
2. Shadow copies in plain files - works but no merge tooling
3. Hidden git repo in `.confluence-sync/baseline/` - git merge capabilities, isolated

**Decision**:
Create a hidden git repository at `.confluence-sync/baseline/` to store content baselines. After each successful sync, commit the synced content. On conflict, use `git merge-file` for 3-way merge.

**Rationale**:
- Isolated from user's git workflow (inside `.gitignore`'d directory)
- Leverages git's proven merge algorithms
- Single baseline sufficient (Confluence content fetched fresh)
- Enables auto-merge when changes don't overlap
- Graceful fallback to conflict markers when overlap detected

**Consequences**:
- (+) Automatic merge for non-overlapping changes
- (+) No user workflow interference
- (+) Uses battle-tested git merge
- (-) Disk space for baseline copies
- (-) Dependency on git CLI for merge operations

---

## ADR-023: Create Parent Then Move Pattern

**Status**: Accepted

**Context**:
User scenario (AC-4.6): Create new markdown file (no page_id), create folder with same name, move existing page into folder.

**Decision**:
Process operations in order:
1. Create new pages (files without page_id)
2. Update page parents (moved files with page_id)

This ensures parent page exists before moving child.

**Rationale**:
- Natural workflow for creating new sections
- Avoids "parent not found" errors
- Order of operations determined by dependency analysis
- Matches intuitive user expectations

**Consequences**:
- (+) Supports section creation workflow
- (+) Predictable operation ordering
- (-) Two-phase processing adds complexity

---

## ADR-024: Move Conflict Resolution

**Status**: Accepted

**Context**:
When moving a file, target path may already exist (different file at destination).

**Decision**:
Log error and skip the conflicting move. Continue with other operations. User must resolve manually.

**Rationale**:
- No automatic merge/overwrite for safety
- Clear error message guides resolution
- Partial success better than full failure
- Consistent with other conflict handling

**Consequences**:
- (+) Safe handling of conflicts
- (+) Clear user feedback
- (-) Manual resolution required
- (-) Partial sync state (some moves applied, some skipped)

---

## Summary

| ADR | Decision |
|-----|----------|
| 017 | Independent page deletion detection |
| 018 | No confirmation prompts (use --dryrun) |
| 019 | CQL ancestors for move detection |
| 020 | State file tracks page IDs |
| 021 | Trash only (soft delete) |
| 022 | Hidden baseline repo for 3-way merge |
| 023 | Create-then-move ordering |
| 024 | Skip conflicting moves |
