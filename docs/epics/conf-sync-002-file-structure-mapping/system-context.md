# System Context - CONF-SYNC-002

---

## Overview

Analysis of system context for File Structure & Mapping epic. This includes integration points with existing Epic 001 components, inherited patterns, and constraints.

---

## Integration Points

### Existing Components (Epic 001)

| Component | Integration Point | How We Use It |
|-----------|-------------------|---------------|
| **APIWrapper** | `get_page_by_id()`, `get_child_pages()`, `create_page()`, `update_page()` | Fetch page hierarchy, create/update pages during sync |
| **PageOperations** | `get_page_snapshot()`, `apply_operations()`, `create_page()` | High-level page CRUD with macro preservation |
| **MarkdownConverter** | `xhtml_to_markdown()`, `markdown_to_xhtml()` | Convert between Confluence storage format and local markdown |
| **Authenticator** | Credential loading from .env | Reuse existing authentication |
| **Error Hierarchy** | 7 exception types | Reuse existing error handling patterns |

### New External Integration

| External System | Purpose | Risk Assessment |
|-----------------|---------|-----------------|
| **Confluence CQL API** | Query pages by parent with version.when timestamp | Low risk - standard Confluence API, well-documented |
| **Local Filesystem** | Read/write markdown files, create directories | Medium risk - permissions, encoding, atomic operations needed |
| **YAML Parser** | Parse/generate frontmatter | Low risk - PyYAML is standard, well-tested |

---

## Patterns to Follow

### Pattern 1: Layered Architecture (Epic 001)

Epic 001 established 3 layers:
```
Orchestration Layer:  page_operations.py
Domain Layer:         surgical_editor.py, content_parser.py, models.py
Infrastructure Layer: api_wrapper.py, markdown_converter.py
```

**For Epic 002**, we add `file_mapper/` as a new orchestration component:
```
CLI Layer (Epic 004):      confluence-sync command
Orchestration Layer:        file_mapper.py (NEW)
                           page_operations.py (existing)
Domain Layer:              hierarchy.py (NEW), config.py (NEW)
Infrastructure Layer:      api_wrapper.py (existing)
```

### Pattern 2: Dataclass Models

Epic 001 uses dataclasses for all data structures:
- `PageSnapshot`
- `SurgicalOperation`
- `ConfluencePage`

**For Epic 002**, continue this pattern:
- `LocalPage` - represents local markdown file with frontmatter
- `SyncConfig` - represents .confluence-sync/config.yaml
- `PageNode` - represents page in hierarchy tree

### Pattern 3: Exception Hierarchy

Epic 001 defined 7 exception types under `ConfluenceError` base class.

**For Epic 002**, add new exceptions:
- `FilesystemError` - file I/O failures
- `ConfigError` - invalid configuration
- `FrontmatterError` - YAML parsing failures

Inherit from `ConfluenceError` base for consistency.

### Pattern 4: Single Responsibility

Each file has ONE clear responsibility:
- `api_wrapper.py` - HTTP client only
- `auth.py` - Credentials only
- `markdown_converter.py` - Pandoc subprocess only

**For Epic 002**, maintain this:
- `file_mapper.py` - Orchestrates file operations
- `hierarchy_builder.py` - Builds page tree from CQL queries
- `filesafe_converter.py` - Filename conversion logic
- `frontmatter_handler.py` - YAML frontmatter operations
- `config_loader.py` - Config file management

---

## Inherited Constraints

### From Epic 001

| Constraint | Impact on Epic 002 |
|------------|-------------------|
| **Python 3.9+** | Use type hints, dataclasses, modern syntax |
| **No shell=True in subprocess** | Safe YAML parsing, no shell injection risk |
| **Type hints mandatory** | All functions must have type annotations |
| **100% error handling** | All file I/O must have try/except with typed exceptions |
| **Test coverage >90%** | Comprehensive unit tests for file_mapper module |

### New Constraints (Epic 002)

| Constraint | Rationale |
|------------|-----------|
| **100 page limit per level** | MVP limitation - CQL query batch size |
| **One side empty on init** | Prevents data loss, simplifies conflict resolution |
| **Atomic file operations** | Use temp files + rename for durability |
| **UTF-8 encoding only** | Simplifies parsing, Confluence uses UTF-8 |
| **POSIX-safe filenames** | Support macOS, Linux (Windows secondary) |

---

## Architecture Risks

### Risk 1: Filesystem Atomicity (HIGH)

**Problem**: Writing multiple files during sync can fail mid-operation, leaving inconsistent state.

**Mitigation**:
1. Write to temp directory first (`.confluence-sync/temp/`)
2. Validate all operations succeeded
3. Atomic move/rename temp files to final location
4. If any operation fails, rollback (delete temp)

**Pattern to use**: Two-phase commit
```python
# Phase 1: Prepare (write to temp)
temp_files = []
for page in pages:
    temp_path = write_to_temp(page)
    temp_files.append(temp_path)

# Phase 2: Commit (atomic move)
for temp_path in temp_files:
    final_path = get_final_path(temp_path)
    os.rename(temp_path, final_path)  # Atomic on POSIX
```

### Risk 2: CQL Query Performance (MEDIUM)

**Problem**: CQL query for 100 pages may be slow (>5 seconds).

**Mitigation**:
1. Only fetch required fields: pageID, title, version.when
2. Use progress indicator for user feedback
3. Cache query results for duration of sync (don't re-query)

**Contingency**: If 100 page limit is too restrictive, Epic 005 can add pagination (query children recursively per page).

### Risk 3: Filename Collision Edge Cases (LOW)

**Problem**: Unlikely but theoretically possible that Confluence allows titles that produce same filesafe name.

**Mitigation**:
1. Detect collision before writing
2. Fail with clear error message
3. Log both pageIDs for debugging
4. Don't attempt to "fix" collision (user must rename in Confluence)

### Risk 4: YAML Frontmatter Corruption (MEDIUM)

**Problem**: Manual editing of frontmatter could corrupt YAML syntax.

**Mitigation**:
1. Validate YAML on load with clear error messages
2. Show line number of YAML error
3. Provide example of correct frontmatter in error message
4. Consider using JSON for frontmatter (more robust) - but less human-friendly

**Decision**: Stick with YAML for human-friendliness, validate strictly.

---

## Patterns from Other Systems

### Pattern: Hugo Static Site Generator

Hugo uses frontmatter + markdown files for content. Their approach:
- YAML/TOML/JSON frontmatter (we choose YAML)
- Filesafe URL slugs (we use filesafe names)
- Content organization by filesystem (we mirror Confluence hierarchy)

**What we adopt**: Frontmatter format, filesafe conversion

**What we don't adopt**: No draft/published status (Confluence handles this)

### Pattern: Obsidian Markdown Editor

Obsidian manages large collections of markdown files with:
- Filesystem-based organization
- Wikilink-style references `[[Page Name]]`
- Frontmatter for metadata

**What we adopt**: Filesystem organization, frontmatter metadata

**What we don't adopt**: Wikilinks (we use Confluence internal links, handled in Epic 005)

---

## Technology Decisions

### Decision 1: CQL vs REST API Pagination

**Options**:
- **A**: Use CQL query with parent filter (limit 100)
- **B**: Use REST API `/wiki/rest/api/content/{id}/child/page` with pagination

**Choice**: A (CQL)

**Rationale**:
- CQL allows filtering by parent in single query
- CQL returns version.when for optimization
- REST API pagination requires multiple round-trips
- 100 page limit acceptable for MVP

### Decision 2: Frontmatter Format

**Options**:
- **A**: YAML (human-friendly, multiline support)
- **B**: JSON (robust parsing, no whitespace issues)
- **C**: TOML (type-safe, less ambiguous)

**Choice**: A (YAML)

**Rationale**:
- Most familiar to developers (Jekyll, Hugo use YAML)
- Human-friendly for manual editing
- Python PyYAML library is robust
- Accept risk of YAML quirks with strict validation

### Decision 3: Filesafe Conversion Strategy

**Options**:
- **A**: Lowercase + hyphens (lossy, simple)
- **B**: Preserve case + special char encoding (complex but reversible)
- **C**: URL encoding (ugly but fully reversible)

**Choice**: B (Preserve case + encoding)

**Rationale**:
- Preserves original case for readability
- Special chars encoded (colon → `--`, etc.)
- Matches user's requirement from Q1/Q2
- Acceptable complexity for better UX

### Decision 4: Config File Format

**Options**:
- **A**: YAML (human-friendly, nested structure)
- **B**: TOML (type-safe, unambiguous)
- **C**: JSON (simple, robust parsing)

**Choice**: A (YAML)

**Rationale**:
- Consistent with frontmatter format
- Human-friendly for manual editing
- Nested structure for multiple spaces (future)

---

## Feasibility Assessment

### Feasible ✅

- CQL queries for page discovery (well-documented API)
- Filesafe name conversion (straightforward algorithm)
- YAML frontmatter (PyYAML library mature)
- Atomic file operations (POSIX primitives available)
- Integration with Epic 001 (clean interfaces exist)

### Feasible with Constraints ⚠️

- 100 page limit per level (MVP constraint, expand in Epic 005)
- Regex exclusion patterns (decide in architecture phase - may defer to Epic 005)

### Not Feasible ❌

- None identified

---

## Conclusion

**Feasibility**: ✅ Feasible

**Key Enablers**:
- Solid foundation from Epic 001 (API wrapper, error handling, conversion)
- Clear separation of concerns (file operations vs sync logic)
- Well-defined constraints (100 page limit, atomic operations)

**Key Risks** (mitigated):
- Filesystem atomicity → Two-phase commit pattern
- CQL performance → Progress indicators, field selection
- YAML corruption → Strict validation with clear errors

**Ready to proceed with detailed architecture design.**
