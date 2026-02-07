---
status: ready-for-implementation
epic_id: CONF-SYNC-003
title: Git Integration
phase: MVP
dependencies:
  - CONF-SYNC-001
blocks:
  - CONF-SYNC-004
refined_date: 2026-01-30
---

# Epic: CONF-SYNC-003 - Git Integration

---

## Overview

Seamless integration with git version control workflows for conflict detection and resolution. This epic enables developers to resolve Confluence sync conflicts using familiar git tools and workflows.

**Customer Problems Addressed**:
- G3: Merge conflicts management using git-like approach
- Concurrent edits between local and Confluence need resolution
- Team collaboration requires conflict visibility

---

## Capabilities

| ID | Capability | Priority |
|----|------------|----------|
| FR-3.1 | Custom git merge driver for confluence markdown | High |
| FR-3.2 | Three-way merge for concurrent edits | High |
| FR-3.4 | Conflict detection before push to Confluence | High |
| FR-3.6 | Automatic conflict markers in markdown | Medium |

---

## Acceptance Criteria (High-Level)

- [ ] Given concurrent edits (local + Confluence), conflicts are detected before any push
- [ ] Given a conflict, the tool creates a merge file with standard git conflict markers
- [ ] Given a configured merge tool (e.g., VS Code), it is launched for conflict resolution
- [ ] Given all conflicts resolved, the sync can proceed with the merged content
- [ ] Given `--forcePush`, local content overwrites Confluence without merge
- [ ] Given `--forcePull`, Confluence content overwrites local without merge

---

## Dependencies

**Depends on**:
- CONF-SYNC-001: Confluence API Integration & Surgical Updates
  - Requires version number for conflict detection
  - Requires `PageSnapshot` for three-way merge base
- CONF-SYNC-002: File Structure & Mapping
  - Requires local markdown files to merge
  - Requires frontmatter with `confluence_version` for comparison

**Blocks**:
- CONF-SYNC-004: CLI & Sync Orchestration (needs conflict resolution for sync command)

---

## Release Phase

⭐ **MVP**

Conflict resolution is a core product promise. Without it, users risk overwriting each other's work.

---

## Conflict Detection Flow

```
┌─────────────────┐     ┌─────────────────┐
│   Local File    │     │   Confluence    │
│ (version: 15)   │     │  (version: 17)  │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
    ┌─────────────────────────────────┐
    │   Version Mismatch Detected     │
    │   local: 15, remote: 17         │
    └─────────────────────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────┐
    │   Fetch Remote Version (v17)    │
    │   Fetch Base Version (v15)      │
    └─────────────────────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────┐
    │   Three-Way Merge               │
    │   Base (v15) + Local + Remote   │
    └─────────────────────────────────┘
                    │
         ┌─────────┴─────────┐
         ▼                   ▼
    ┌──────────┐       ┌──────────────┐
    │ No Conflict│     │ Conflict!    │
    │ Auto-merge │     │ Create .conflict│
    └──────────┘       │ Launch tool  │
                       └──────────────┘
```

---

## Technical Considerations

1. **Base version storage**: Need to store base version for three-way merge
   - Option A: Store in `.confluence-sync/base/` folder
   - Option B: Store hash/version in mapping file, fetch base on demand

2. **Merge driver configuration**: Git custom merge driver
   ```gitattributes
   *.md merge=confluence-sync
   ```
   ```gitconfig
   [merge "confluence-sync"]
       name = Confluence Sync Merge Driver
       driver = confluence-sync merge %O %A %B %P
   ```

3. **Conflict marker format**: Standard git markers
   ```markdown
   <<<<<<< LOCAL
   My local changes
   =======
   Remote Confluence changes
   >>>>>>> CONFLUENCE
   ```

---

## Next Steps

After this epic is created in tracking system, run:
```
/workplan conf-sync-003
```
to refine into stories and architecture.
