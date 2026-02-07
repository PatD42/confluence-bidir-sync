# Architecture Decision Records - CONF-SYNC-002

---

## ADR-008: CQL-Based Page Discovery

**Date**: 2026-01-30
**Status**: Accepted
**Epic**: CONF-SYNC-002

### Context

Need to discover all pages under a parent page in Confluence hierarchy. Two approaches available:

1. REST API pagination: `/wiki/rest/api/content/{id}/child/page` with `start` and `limit` parameters
2. CQL queries: `parent = {page_id}` with `limit` parameter

### Decision

Use CQL queries with 100 page limit for MVP.

### Consequences

**Positive**:
- Single query returns all children (no pagination loop)
- Can fetch `version.when` timestamp for optimization
- Simpler error handling (one request)
- Faster for hierarchies with <100 pages per level

**Negative**:
- 100 page limit per level (MVP constraint)
- CQL syntax less familiar than REST endpoints
- Must handle >=100 page error gracefully

**Mitigation**:
- Epic 005 will add recursive per-child queries for >100 pages
- Clear error message guides users to split hierarchy

---

## ADR-009: YAML Frontmatter Format

**Date**: 2026-01-30
**Status**: Accepted
**Epic**: CONF-SYNC-002

### Context

Need to store Confluence metadata in local markdown files. Three format options:

1. YAML: Human-friendly, multiline support, used by Hugo/Jekyll
2. JSON: Robust parsing, no whitespace ambiguity
3. TOML: Type-safe, less ambiguous than YAML

### Decision

Use YAML frontmatter with strict validation.

### Rationale

- Most familiar to developers (Jekyll, Hugo, Obsidian use YAML)
- Human-friendly for manual editing
- PyYAML library mature and well-tested
- Multiline strings easier than JSON

### Consequences

**Positive**:
- Familiar format, low learning curve
- Easy to edit manually
- Industry standard for markdown frontmatter

**Negative**:
- YAML whitespace/indentation can cause issues
- Less type-safe than TOML

**Mitigation**:
- Strict YAML validation on load
- Clear error messages with line numbers
- Provide example frontmatter in error messages

**Example**:
```yaml
---
page_id: "12345"
space_key: "CONFSYNCTEST"
title: "Customer Feedback"
last_synced: "2026-01-30T10:00:00Z"
confluence_version: 15
---
```

---

## ADR-010: Filesafe Conversion with Case Preservation

**Date**: 2026-01-30
**Status**: Accepted
**Epic**: CONF-SYNC-002

### Context

Need to convert Confluence page titles to filesafe names. Three strategies:

1. Lowercase + hyphens: Simple, lossy, hard to read (`api-reference--getting-started.md`)
2. Preserve case + encoding: Complex, readable, matches user requirement
3. URL encoding: Ugly but fully reversible (`API%20Reference%3A%20Getting%20Started.md`)

### Decision

Preserve case, encode special characters with simple rules.

**Conversion Rules**:
- Keep: Alphanumeric, hyphen, underscore, period
- Colon (`:`) → Double-dash (`--`)
- Space (` `) → Hyphen (`-`)
- Forward slash (`/`) → Hyphen (`-`)
- Other special chars → Hyphen (`-`)

### Rationale

- Matches user's explicit requirement from discovery (Q1/Q2)
- Readable: `API-Reference--Getting-Started.md`
- Reversible: Frontmatter stores original title
- Consistent with Confluence's internal filesafe conversion

### Consequences

**Positive**:
- Readable filenames preserve case
- Special char handling explicit and predictable
- Users can recognize pages by filename

**Negative**:
- More complex than simple lowercase
- Edge cases possible (multiple hyphens, etc.)

**Examples**:
```
"Customer Feedback" → "Customer-Feedback.md"
"API Reference: Getting Started" → "API-Reference--Getting-Started.md"
"Q&A Session" → "Q-A-Session.md"
"2026-01-30 Meeting Notes" → "2026-01-30-Meeting-Notes.md"
```

---

## ADR-011: Atomic File Operations with Two-Phase Commit

**Date**: 2026-01-30
**Status**: Accepted
**Epic**: CONF-SYNC-002

### Context

Writing multiple files during sync can fail mid-operation, leaving inconsistent state (some files written, others not). Need atomic "all or nothing" behavior.

### Decision

Use two-phase commit pattern with temp directory:

1. **Phase 1 (Prepare)**: Write all files to `.confluence-sync/temp/`
2. **Phase 2 (Commit)**: Atomic rename from temp to final location
3. **Rollback**: If any operation fails, delete temp files

### Rationale

- POSIX `os.rename()` is atomic within same filesystem
- Temp directory isolates failures from production files
- Rollback is simple (delete temp files)
- Industry standard pattern (databases, git)

### Consequences

**Positive**:
- Guarantees consistency (all files written or none)
- Failed sync leaves local state unchanged
- Easy to implement and test

**Negative**:
- Requires disk space for temp files (2x during sync)
- Extra I/O operations (write temp + rename)

**Mitigation**:
- Temp directory cleaned up after success or failure
- Acceptable performance cost for consistency guarantee

### Implementation

```python
def write_pages_atomic(self, pages: List[Tuple[PageNode, str]]) -> None:
    temp_dir = Path(".confluence-sync/temp")
    temp_files = []

    try:
        # Phase 1: Write to temp
        for page_node, content in pages:
            temp_path = temp_dir / filename
            temp_path.write_text(content)
            temp_files.append((temp_path, final_path))

        # Phase 2: Atomic rename
        for temp_path, final_path in temp_files:
            os.rename(temp_path, final_path)  # Atomic

    except Exception:
        # Rollback: delete temp files
        for temp_path, _ in temp_files:
            temp_path.unlink()
        raise
```

---

## ADR-012: Parent PageID as Configuration Anchor

**Date**: 2026-01-30
**Status**: Accepted
**Epic**: CONF-SYNC-002

### Context

Need to specify which Confluence pages to sync. Two approaches:

1. **Page path**: `SPACE:/engineering/products/my-product`
2. **Page ID**: `SPACE:12345` or just `12345`

Page paths are user-friendly but brittle (break if page renamed/moved).
Page IDs are stable but not human-readable.

### Decision

Use parent page ID as configuration anchor.

- During `--init`, accept either path or ID
- Resolve path to pageID immediately
- Store only pageID in config file

### Rationale

- PageID is immutable (never changes)
- Page path can break if page renamed or moved
- Path resolution at init-time provides good UX
- Config file robustness more important than readability

### Consequences

**Positive**:
- Config remains valid even if page renamed/moved
- No path resolution needed during sync (faster)
- Robust to Confluence changes

**Negative**:
- Config file shows pageID not human-readable path
- User must use Confluence UI to find pageID if manually editing config

**Mitigation**:
- `--init` accepts paths for convenience
- Config comments can include original path for reference

**Config Example**:
```yaml
spaces:
  - space_key: "CONFSYNCTEST"
    parent_page_id: "12345"  # /engineering/products/my-product
    local_path: "./docs/product-docs/"
```

---

## ADR-013: 100 Page Limit per Level (MVP)

**Date**: 2026-01-30
**Status**: Accepted (Temporary)
**Epic**: CONF-SYNC-002

### Context

CQL queries have a batch limit of 100 results. For MVP, must choose:

1. Implement pagination (complex, more code)
2. Enforce 100 page limit per level (simple, restrictive)

### Decision

Enforce 100 page limit per level for MVP.

Fail with clear error if any level has >=100 pages.

### Rationale

- Simplifies MVP implementation (no pagination logic)
- Most real-world hierarchies have <100 pages per level
- Clear path to expand in Epic 005 (Future enhancements)
- Acceptable trade-off for faster MVP delivery

### Consequences

**Positive**:
- Simple implementation (single CQL query per level)
- Faster MVP delivery
- Clear error handling

**Negative**:
- Cannot sync large flat hierarchies (100+ siblings)
- Users with large pages must split hierarchy

**Future Enhancement** (Epic 005):
- Add pagination: Query children recursively per page
- Remove 100 page limit

**Error Message**:
```
Error: Parent page 12345 has >=100 child pages (limit: 100).
MVP limitation: Cannot sync hierarchies with >=100 pages at same level.

Options:
  1. Split hierarchy in Confluence (add intermediate parent pages)
  2. Wait for Epic 005 (future release will support >100 pages)
```

---

## ADR-014: Strict Initial Sync Requirement

**Date**: 2026-01-30
**Status**: Accepted
**Epic**: CONF-SYNC-002

### Context

On first sync (no prior sync state), both Confluence and local may have content. How to handle?

Options:
1. **Strict**: Fail if both sides have content (one side must be empty)
2. **Merge**: Attempt to match pages by title and merge
3. **Force**: Require explicit `--forcePush` or `--forcePull`

### Decision

Require one side to be empty on initial sync. Fail if both have content.

Provide `--forcePush` and `--forcePull` flags for override.

### Rationale

- Prevents accidental data loss
- Avoids complex merge logic for MVP
- Clear user intent required for destructive operations
- Simple implementation

### Consequences

**Positive**:
- No accidental data loss
- Simple logic (no complex matching algorithm)
- User forced to make explicit choice

**Negative**:
- Less flexible than auto-merge
- Users with existing content on both sides must choose

**Mitigation**:
- Clear error message with options
- `--forcePull`/`--forcePush` provide escape hatch

**Error Message**:
```
Error: Both Confluence and local folder have content.
Initial sync requires one side to be empty.

Options:
  --forcePull: Overwrite local with Confluence content
  --forcePush: Overwrite Confluence with local content (requires confirmation)

Use with caution - chosen side will be deleted!
```

---

## ADR-015: Exclusion by PageID (MVP)

**Date**: 2026-01-30
**Status**: Accepted
**Epic**: CONF-SYNC-002

### Context

Need to exclude certain pages from sync (e.g., Archives). Two approaches:

1. **PageID-based**: List excluded pageIDs in config
2. **Regex patterns**: Match page titles/paths with regex

Regex is more flexible but riskier (complex patterns, edge cases, performance).

### Decision

For MVP, support pageID-based exclusion only.

**Defer regex patterns to Epic 005** (Future enhancements).

### Rationale

- PageID exclusion is simple, explicit, safe
- Regex patterns add complexity and risk for MVP
- Most use cases covered by pageID (exclude specific pages)
- Clear path to add regex in Epic 005

### Consequences

**Positive**:
- Simple implementation
- No regex edge cases or performance issues
- Explicit exclusion (clear what's excluded)

**Negative**:
- Less flexible (can't exclude by pattern)
- Must know pageID to exclude

**Future Enhancement** (Epic 005):
- Add regex pattern support for advanced exclusion
- Pattern format: `.*/[Aa]rchive.*` matches any path containing "archive"

**Config Example (MVP)**:
```yaml
spaces:
  - space_key: "CONFSYNCTEST"
    parent_page_id: "12345"
    local_path: "./docs/"
    exclude:
      - page_id: "67890"  # Archives page (and all descendants)
```

---

## Summary

| ADR | Decision | Status |
|-----|----------|--------|
| ADR-008 | CQL-based page discovery | Accepted |
| ADR-009 | YAML frontmatter format | Accepted |
| ADR-010 | Filesafe conversion with case preservation | Accepted |
| ADR-011 | Atomic file operations (two-phase commit) | Accepted |
| ADR-012 | Parent pageID as config anchor | Accepted |
| ADR-013 | 100 page limit per level (MVP) | Accepted (Temporary) |
| ADR-014 | Strict initial sync requirement | Accepted |
| ADR-015 | Exclusion by pageID only (MVP) | Accepted |
