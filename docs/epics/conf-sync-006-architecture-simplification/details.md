---
status: ready-for-refinement
epic_id: CONF-SYNC-006
title: Architecture Simplification & Single CQL Query
phase: Post-MVP
dependencies:
  - CONF-SYNC-001
  - CONF-SYNC-002
  - CONF-SYNC-004
  - CONF-SYNC-005
blocks: []
created_date: 2026-01-31
---

# Epic: CONF-SYNC-006 - Architecture Simplification & Single CQL Query

---

## Overview

Simplify the sync architecture by using a single CQL query for page discovery and reducing frontmatter to `page_id` only. This refactoring improves performance (fewer API calls), simplifies the data model, and enables proper single-file sync.

**Customer Problems Addressed**:
- **Performance**: Current recursive API calls (one per parent) replaced with single CQL query
- **Simplicity**: Frontmatter bloat removed - only `page_id` needed
- **Single-file sync**: Sync individual files without breaking change detection for others
- **CLI usability**: Simplified command structure without subcommands

---

## Capabilities

| ID | Capability | Priority | Status |
|----|------------|----------|--------|
| ARCH-1 | Single CQL query for all descendant pages | High | New |
| ARCH-2 | Frontmatter simplification (page_id only) | High | New |
| ARCH-3 | Single-file sync without global timestamp update | Medium | New |
| ARCH-4 | Title derivation from CQL/first heading | High | New |
| ARCH-5 | Remove LocalPage deprecated fields | High | New |
| ARCH-6 | Optional `--logdir` parameter for file logging | Medium | New |
| ARCH-7 | Remove `sync` subcommand, add `--init` flag | Medium | New |
| ARCH-8 | Mandatory package installation | Medium | New |

---

## Key Design Decisions

1. **Single CQL Query**: Use `ancestor = {parent_page_id}` to get all descendants in one call
2. **CQL Returns All Needed Data**: page_id, title, last_modified, ancestors (for parent_id derivation)
3. **Frontmatter = page_id only**: No version, no title, no timestamps in frontmatter
4. **Title Sources**:
   - Existing pages: from CQL query result
   - New pages (no page_id): from first H1 heading in markdown
5. **Single-file sync**: Update baseline, NOT `last_synced`; accept one unnecessary conflict cycle on next sync
6. **Global timestamp**: `state.yaml.last_synced` remains the change detection anchor
7. **CLI simplification**: No subcommands; `--init` flag for initialization
8. **Mandatory installation**: `pip install -e .` required; CLI invoked as `confluence-sync`
9. **Local timezone**: All log timestamps (console and file) use local timezone

---

## Data Flow (After Refactoring)

```
1. CQL Query: ancestor = {parent_page_id}
   Returns: [{page_id, title, last_modified, ancestors}, ...]

2. Local Scan: Read *.md files
   Extract: page_id from frontmatter, content

3. Match by page_id:
   - local_pages: Dict[page_id -> file_path]
   - remote_pages: Dict[page_id -> {title, last_modified, parent_id}]

4. Change Detection:
   - local changed: file.mtime > state.last_synced
   - remote changed: page.last_modified > state.last_synced

5. Deletion Detection:
   - tracked_pages - remote_pages = deleted in Confluence
   - tracked_pages - local_pages = deleted locally

6. Move Detection:
   - Compare parent_id from CQL ancestors vs expected from file path
```

---

## CLI Usage (After Refactoring)

```bash
# Install (required)
pip install -e .

# Initialize configuration
confluence-sync --init "ProductXYZ:/" ./docs/

# Run bidirectional sync
confluence-sync

# Preview changes without applying
confluence-sync --dry-run

# Force sync directions
confluence-sync --force-push
confluence-sync --force-pull

# Sync single file
confluence-sync path/to/file.md

# Enable file logging
confluence-sync --logdir ./logs

# Verbose output
confluence-sync -v 2
```

---

## Acceptance Criteria

### AC-1: Single CQL Query
- [ ] HierarchyBuilder uses `ancestor = {page_id}` CQL query
- [ ] Single API call returns all pages under parent
- [ ] Query includes: page_id, title, version.when (last_modified), ancestors
- [ ] Page limit enforced on total results, not per-level

### AC-2: Frontmatter Simplification
- [ ] Generated frontmatter contains only `page_id`
- [ ] Parser accepts files with only `page_id` in frontmatter
- [ ] Existing files with extra fields still parse (backward compatible)
- [ ] New/updated files only write `page_id`

### AC-3: Title Derivation
- [ ] Existing pages: title from CQL result
- [ ] New pages: title from first H1 heading (`# Title`)
- [ ] Fallback: filename without extension if no H1

### AC-4: LocalPage Simplification
- [ ] LocalPage has only: file_path, page_id, content
- [ ] All code using deprecated fields refactored
- [ ] No breaking changes to external interfaces

### AC-5: Single-File Sync
- [ ] `confluence-sync path/to/file.md` works
- [ ] Baseline updated for synced file
- [ ] `state.last_synced` NOT updated
- [ ] Next full sync correctly handles the file (via 3-way merge)

### AC-6: File Logging
- [ ] `--logdir` parameter added to CLI
- [ ] Log file created with `confluence-sync-YYYYMMDD-HHMMSS.log` format
- [ ] Timestamps in filename and log entries use local timezone
- [ ] Directory auto-created if missing
- [ ] Logs go to stderr when `--logdir` not provided

### AC-7: CLI Simplification
- [ ] Remove `sync` and `init` subcommands
- [ ] Default behavior (no args): run bidirectional sync
- [ ] `--init "SPACE:Page" LOCAL_PATH`: initialize configuration
- [ ] `--dry-run`, `--force-push`, `--force-pull` work at top level
- [ ] Positional `FILE` argument for single-file sync

### AC-8: Mandatory Package Installation
- [ ] README documents `pip install -e .` as prerequisite
- [ ] All error messages use `confluence-sync` command format
- [ ] Error when config not found shows: `Run 'confluence-sync --init "SPACE:/" ./local-path' to initialize`

---

## Technical Changes

| Component | Change |
|-----------|--------|
| `HierarchyBuilder` | Replace recursive calls with single CQL query |
| `APIWrapper` | Add `search_by_cql(cql, expand)` method |
| `FrontmatterHandler` | Generate/parse only `page_id` |
| `LocalPage` | Remove: space_key, title, last_synced, confluence_version |
| `FileMapper` | Get title from CQL result, not LocalPage |
| `SyncCommand` | Pass `update_timestamp=False` for single-file sync |
| `ChangeDetector` | Accept remote data from CQL result |
| `src/cli/main.py` | Remove subcommands, add `--init` and `--logdir` flags |
| `README.md` | Document installation requirement and new CLI |

---

## Dependencies

**Depends on:**
- CONF-SYNC-001: Confluence API (CQL search endpoint)
- CONF-SYNC-002: File Structure & Mapping
- CONF-SYNC-004: CLI & Sync Orchestration
- CONF-SYNC-005: Extended Features (deletion/move detection uses CQL data)

**Blocks:**
- None (this is a post-MVP refactoring)

---

## Architecture Summary

### Current (Before)
```
HierarchyBuilder
  └── get_page_by_id(parent)           # API call 1
      └── get_page_child_by_type(p1)   # API call 2
          └── get_page_child_by_type(p2)   # API call 3
              └── ... (recursive)      # API call N
```

### After
```
HierarchyBuilder
  └── search_by_cql("ancestor = {parent_page_id}")  # Single API call
      └── Returns all descendants with metadata
```

### Frontmatter Before
```yaml
---
page_id: "123456"
space_key: "TEAM"
title: "My Page"
last_synced: "2024-01-15T10:30:00Z"
confluence_version: 5
---
```

### Frontmatter After
```yaml
---
page_id: "123456"
---
```

---

## Error Handling

| Error | Exit Code | Message |
|-------|-----------|---------|
| Config not found | 1 | `Configuration file not found: .confluence-sync/config.yaml` + `Run 'confluence-sync --init "SPACE:/" ./local-path' to initialize` |
| CQL query fails | 1 | `Failed to query Confluence pages: {error}` |
| No H1 for new page | 1 | `Cannot determine title for new page: {file_path}. Add '# Title' heading.` |
| Logdir creation fails | 1 | `Failed to create log directory: {path}` |

---

## Risks

| Risk | Mitigation |
|------|------------|
| CQL query pagination for large hierarchies | Confluence paginates; handle `_links.next` |
| Backward compatibility with existing frontmatter | Parser accepts old format, only writes new format |
| Title extraction from markdown | Use regex for H1, fallback to filename |
| Local timezone inconsistency | Python logging uses local time by default |

---

## Release Phase

**Post-MVP**

This epic refactors internal architecture after MVP launch. No new features, but improves performance and maintainability.

---

## Files to Create/Modify

**Epic Documentation:**
- `details.md` (this file)
- `acceptance-criteria.md` - Detailed test scenarios
- `architecture.md` - Component diagrams
- `adr.md` - Architecture decision records

**Source Code:**
- `src/file_mapper/hierarchy_builder.py` - CQL query
- `src/file_mapper/frontmatter_handler.py` - Simplify to page_id
- `src/file_mapper/models.py` - Simplify LocalPage
- `src/confluence_client/api_wrapper.py` - Add CQL method
- `src/cli/main.py` - Remove subcommands, add flags
- `src/cli/sync_command.py` - Single-file timestamp handling

**Documentation:**
- `README.md` - Installation and usage
