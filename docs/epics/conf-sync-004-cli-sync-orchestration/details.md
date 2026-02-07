---
status: ready-for-implementation
epic_id: CONF-SYNC-004
title: CLI & Sync Orchestration
phase: MVP
dependencies:
  - CONF-SYNC-001
  - CONF-SYNC-002
  - CONF-SYNC-003
blocks:
  - CONF-SYNC-005
refined_date: 2026-01-30
---

# Epic: CONF-SYNC-004 - CLI & Sync Orchestration

---

## Overview

Command-line interface for all sync operations. This epic provides the user-facing CLI that orchestrates file mapping, conflict detection, and Confluence API operations into a seamless sync workflow.

**Customer Problems Addressed**:
- G1: Bidirectional Sync - single command to sync both directions
- G8: Forced push or pull - override conflict handling when needed
- G9: Single page sync - sync individual pages, not just whole hierarchies
- G10: Dry run - preview changes before applying

---

## Capabilities

| ID | Capability | Priority |
|----|------------|----------|
| FR-4.1 | `confluence-sync` - Bidirectional sync command | High |
| FR-4.2 | `--forcePush` - Local overwrites Confluence | High |
| FR-4.3 | `--forcePull` - Confluence overwrites local | High |
| FR-4.4 | `--dryrun` - Preview changes without applying | High |
| FR-4.5 | `--init` - Create minimal configuration | High |

---

## Acceptance Criteria (High-Level)

- [ ] Given `confluence-sync`, both local and Confluence changes are synchronized
- [ ] Given `confluence-sync --forcePush`, local content overwrites Confluence
- [ ] Given `confluence-sync --forcePull`, Confluence content overwrites local
- [ ] Given `confluence-sync --dryrun`, changes are displayed but not applied
- [ ] Given `confluence-sync --init <confluence-path> <local-path>`, config file is created
- [ ] Given a single file path argument, only that page is synced
- [ ] Given network failure during sync, partial state is not corrupted
- [ ] Given rate limiting (429), sync retries with backoff and continues

---

## Dependencies

**Depends on**:
- CONF-SYNC-001: Confluence API Integration & Surgical Updates
  - All API operations (fetch, update, create)
  - Error handling (all 7 exception types)
- CONF-SYNC-002: File Structure & Mapping
  - Local file creation/reading
  - Mapping file management
  - Hierarchy traversal
- CONF-SYNC-003: Git Integration
  - Conflict detection
  - Merge conflict resolution workflow

**Blocks**:
- CONF-SYNC-005: Extended Features (builds on working CLI)

---

## Release Phase

⭐ **MVP**

The CLI is the primary user interface. Without it, users cannot use the tool.

---

## CLI Commands

### `confluence-sync`
Main sync command. Bidirectional by default.

```bash
# Sync all configured pages
confluence-sync

# Sync specific file/page
confluence-sync path/to/page.md

# Force overwrite modes
confluence-sync --forcePush
confluence-sync --forcePull

# Preview mode
confluence-sync --dryrun

# Verbose output
confluence-sync -v
confluence-sync --verbose
```

### `confluence-sync --init`
Initialize sync configuration.

```bash
# Interactive setup
confluence-sync --init

# With arguments
confluence-sync --init SPACE:/path/to/root ./local/docs
```

Creates:
```yaml
# .confluence-sync/config.yaml
space_key: SPACE
root_page_path: /path/to/root
local_root: ./local/docs
exclude_paths:
  - /path/to/root/archives
```

---

## Sync Flow

```
confluence-sync
       │
       ▼
┌─────────────────────┐
│ Load Configuration  │
│ (.confluence-sync/) │
└─────────────────────┘
       │
       ▼
┌─────────────────────┐
│ Build Page Tree     │
│ (Confluence API)    │
└─────────────────────┘
       │
       ▼
┌─────────────────────┐
│ Scan Local Files    │
│ (file_mapper)       │
└─────────────────────┘
       │
       ▼
┌─────────────────────┐
│ Detect Changes      │
│ - New local files   │
│ - New remote pages  │
│ - Modified (both)   │
│ - Deleted (both)    │
└─────────────────────┘
       │
       ├─── --dryrun? ──► Display changes, exit
       │
       ▼
┌─────────────────────┐
│ Check for Conflicts │
│ (version mismatch)  │
└─────────────────────┘
       │
       ├─── Conflicts? ──► Launch merge tool
       │
       ▼
┌─────────────────────┐
│ Apply Changes       │
│ - Push local→remote │
│ - Pull remote→local │
└─────────────────────┘
       │
       ▼
┌─────────────────────┐
│ Update Mapping      │
│ Update Frontmatter  │
└─────────────────────┘
       │
       ▼
    SUCCESS
```

---

## Technical Considerations

1. **CLI Framework**: Typer or Click
   - Typer preferred (modern, type hints)
   - Auto-generated help text
   - Shell completion

2. **Progress indication**: Rich library
   - Progress bars for multi-page sync
   - Status spinners for individual operations
   - Color-coded output (green=success, red=error, yellow=warning)

3. **Exit codes**:
   - 0: Success
   - 1: General error
   - 2: Conflicts detected (user action required)
   - 3: Authentication failure
   - 4: Network error

4. **Logging levels**:
   - Default: Summary only
   - `-v`: Info level (page names, operations)
   - `-vv`: Debug level (API calls, timing)

---

## Next Steps

After this epic is created in tracking system, run:
```
/workplan conf-sync-004
```
to refine into stories and architecture.
