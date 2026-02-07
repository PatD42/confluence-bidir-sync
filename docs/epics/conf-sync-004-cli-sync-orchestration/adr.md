# Architecture Decision Records - CONF-SYNC-004

---

## ADR-011: Typer for CLI Framework

**Status**: Accepted

**Context**: Need a CLI framework for the `confluence-sync` command.

**Options**:
1. **Click** - Mature, widely used, decorator-based
2. **Typer** - Built on Click, uses type hints, auto-generates help
3. **argparse** - Standard library, verbose

**Decision**: Typer

**Rationale**:
- Type hints align with project standards (mypy clean)
- Auto-generated help from type annotations
- Shell completion built-in
- Built on Click (stable foundation)
- Modern, Pythonic API

---

## ADR-012: Rich for Terminal Output

**Status**: Accepted

**Context**: Need progress bars, spinners, and colored output.

**Options**:
1. **Rich** - Full-featured terminal formatting
2. **tqdm** - Progress bars only
3. **Click echo** - Basic colored output

**Decision**: Rich

**Rationale**:
- Progress bars, spinners, tables, colors in one library
- Graceful fallback for non-TTY
- Active maintenance
- Works well with Typer (same author)

---

## ADR-013: Project-Level Sync State

**Status**: Accepted

**Context**: Need to track when last sync occurred for change detection.

**Options**:
1. **Per-file frontmatter** - `last_synced` in each markdown file
2. **Project-level state** - Single `.confluence-sync/state.yaml`
3. **No state** - Always do full comparison

**Decision**: Project-level state in `.confluence-sync/state.yaml`

**Rationale**:
- Simpler frontmatter (only `page_id` required)
- No user-visible metadata clutter
- Single point of truth for sync timing
- Assumption: No changes during sync operation
- Easy to implement and debug

**Trade-off**: Can't track per-file sync times. Acceptable for MVP.

---

## ADR-014: Timestamp-Based Change Detection

**Status**: Accepted

**Context**: Need to detect what changed since last sync.

**Options**:
1. **Version numbers** - Store Confluence version in frontmatter
2. **Timestamps** - Compare mtime vs last_synced
3. **Content hash** - Hash content and compare

**Decision**: Timestamps

**Rationale**:
- Single source of truth (content IS truth, not version number)
- File mtime automatically tracks local changes
- Confluence API provides `last_modified`
- Simple comparison: `mtime > last_synced` = local changed
- No risk of version drift

---

## ADR-015: Minimal Frontmatter

**Status**: Accepted

**Context**: What metadata to store in markdown frontmatter.

**Options**:
1. **Full metadata** - page_id, space_key, title, version, last_synced
2. **Minimal** - page_id only

**Decision**: Minimal (page_id only)

**Rationale**:
- Title inferred from Confluence CQL results
- Space key from project config
- last_synced at project level
- Version not needed (timestamps for change detection)
- Less clutter in user files
- Single source of truth for each piece of data

---

## ADR-016: Exit Code Strategy

**Status**: Accepted

**Context**: Define exit codes for scripting/CI integration.

**Decision**:

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (config, validation, page not found) |
| 2 | Conflicts (unresolved merge conflicts) |
| 3 | Authentication failure |
| 4 | Network error (unreachable, rate limit) |

**Rationale**:
- 0/1 standard for success/failure
- Specific codes for actionable categories
- Scripts can handle auth vs network differently
- Conflicts get unique code (user action required)

---

## Index

| ADR | Title | Status |
|-----|-------|--------|
| ADR-011 | Typer for CLI Framework | Accepted |
| ADR-012 | Rich for Terminal Output | Accepted |
| ADR-013 | Project-Level Sync State | Accepted |
| ADR-014 | Timestamp-Based Change Detection | Accepted |
| ADR-015 | Minimal Frontmatter | Accepted |
| ADR-016 | Exit Code Strategy | Accepted |
