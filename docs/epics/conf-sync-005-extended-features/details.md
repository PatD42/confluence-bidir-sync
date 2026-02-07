---
status: ready-for-implementation
epic_id: CONF-SYNC-005
title: Extended Features (Deletion & Moves)
phase: Post-MVP
dependencies:
  - CONF-SYNC-001
  - CONF-SYNC-002
  - CONF-SYNC-004
blocks: []
refined_date: 2026-01-31
---

# Epic: CONF-SYNC-005 - Extended Features (Deletion & Moves)

---

## Overview

Post-MVP enhancements focusing on page deletion handling and page move detection. This refined scope addresses the most critical edge cases for a complete sync workflow.

**Customer Problems Addressed**:
- Deletion propagation: Pages deleted in Confluence or locally should sync correctly
- Page reorganization: Moving pages in either system should update the other
- Safe preview: `--dryrun` shows all operations before execution

**Refined Scope (from `/epic_refine`):**
- EXT-4: Page deletion handling (both directions)
- FR-2.6: Page moves (both directions)
- Conflict resolution via 3-way merge (hidden baseline repo)

**Deferred to future:**
- Git hooks for pre-push validation (user controls git workflow)
- Change detection daemon
- Flat file mode
- Mermaid conversion
- Internal page reference conversion

---

## Capabilities

| ID | Capability | Priority | Status |
|----|------------|----------|--------|
| EXT-4 | Page deletion handling (Confluence → Local) | High | In Scope |
| EXT-4 | Page deletion handling (Local → Confluence) | High | In Scope |
| FR-2.6 | Page moves (Confluence → Local) | High | In Scope |
| FR-2.6 | Page moves (Local → Confluence) | High | In Scope |
| FR-3.4 | 3-way merge for conflict resolution | High | In Scope |

---

## Key Design Decisions

1. **No confirmation prompts**: Deletions execute directly; use `--dryrun` to preview
2. **Independent deletion detection**: Each page tracked by page_id, no cascading
3. **Move via CQL ancestors**: Single query with `expand=ancestors`
4. **Trash only**: Confluence pages soft-deleted (recoverable)
5. **Create-then-move**: New pages created before children moved under them
6. **Hidden baseline repo**: `.confluence-sync/baseline/` stores content at last sync for 3-way merge
7. **Auto-merge non-overlapping**: Changes to different parts of file merge automatically

---

## Acceptance Criteria (Summary)

### Page Deletion - Confluence → Local
- Detect deleted pages by checking page_id existence
- Delete local files (not child folders automatically)
- Distinguish deletion from move

### Page Deletion - Local → Confluence
- Detect local deletions via tracked_pages in state.yaml
- Move Confluence pages to trash
- Use `--dryrun` for preview

### Page Moves - Confluence → Local
- Detect moves via CQL ancestors comparison
- Move local files to match hierarchy
- Handle nested moves (parent + children)

### Page Moves - Local → Confluence
- Detect local moves via folder structure changes
- Update Confluence page parent
- Support create-parent-then-move workflow

See `acceptance-criteria.md` for full details.

---

## Dependencies

**Depends on**:
- CONF-SYNC-001: Confluence API Integration
  - Delete page API call
  - Update page parent API call
  - CQL search with ancestors
- CONF-SYNC-002: File Structure & Mapping
  - File move/delete operations
  - Path resolution
- CONF-SYNC-004: CLI & Sync Orchestration
  - SyncCommand extension
  - ChangeDetector extension
  - OutputHandler message formats

**Blocks**:
- None (this is a post-MVP enhancement)

---

## Architecture Summary

```
src/cli/
├── change_detector.py   # + detect_deletions(), detect_moves()
├── deletion_handler.py  # NEW: delete operations
├── move_handler.py      # NEW: move operations
├── ancestor_resolver.py # NEW: CQL ancestors parsing
└── models.py            # + DeletionInfo, MoveInfo, etc.
```

See `architecture.md` for component specifications.

---

## Error Handling

| Error | Exit Code | Handling |
|-------|-----------|----------|
| Delete permission denied | 1 | Log, continue with others |
| Move target exists | 1 | Log conflict, skip |
| Parent page not found | 1 | Log, skip move |
| Invalid frontmatter YAML | 1 | Log validation error |

See `docs/architecture/13-specs/errors/by-domain/conf-sync-005-extended.yaml` for full error codes.

---

## Release Phase

🔮 **Post-MVP**

This epic enhances the product after MVP launch. Features are valuable but not required for initial release.

---

## Files Created During Refinement

**Epic Documentation:**
- `acceptance-criteria.md` - 30 acceptance scenarios (AC-1 to AC-5)
- `architecture.md` - Component design with Mermaid diagrams
- `adr.md` - Architecture decision records (ADR-017 to ADR-024)

**Technical Specifications:**
- `docs/architecture/13-specs/errors/by-domain/conf-sync-005-extended.yaml`
  - 14 error codes (EXT-001 to EXT-093)
  - Deletion, move, merge errors
- `docs/architecture/13-specs/schemas/domain/conf-sync-005-extended-models.json`
  - 12 data models including MergeResult, ConflictInfo
- `docs/architecture/13-specs/api/conf-sync-005-extended-api.yaml`
  - 6 component interfaces
  - 3 Confluence API endpoints
