# CLAUDE.md - confluence-bidir-sync

**Last Updated:** 2026-02-07
**Purpose:** Provide efficient context for AI agents working on this codebase

---

## Project Essence

Bidirectional sync between Confluence Cloud pages and local markdown files. **Critical insight:** Markdown is the editing surface for agents/tools. XHTML/ADF is the source of truth that gets **surgically modified**. Macros are preserved by **never touching `ac:` namespace elements**.

**Primary Users:** Agentic AI teams working with documentation via markdown + RAG tools, while preserving Confluence's rich features (macros, tables, formatting).

---

## Critical Architectural Decisions

### Dual Update Paths (ADR-008)

Two surgical update mechanisms exist side-by-side:

1. **XHTML Surgical** (`apply_operations`) - Position-signature based
   - Legacy path, fragile with content changes
   - Used when ADF unavailable

2. **ADF Surgical** (`update_page_surgical_adf`) - **Preferred**
   - Targets nodes by `localId` (stable identifier)
   - Baseline-centric diffing (baseline vs. new markdown)
   - **Falls back to full replacement if >50% operations fail**

**When implementing new features:** Default to ADF path unless specific XHTML requirement.

### Baseline-Centric Merge (ADR-009)

3-way merge uses **baseline content** (last successful sync) as common ancestor:

```
baseline markdown → diff → new markdown
```

**Why:** Avoids format mismatch issues from converting confluence→markdown repeatedly. Baseline and new are both markdown (same parser).

### Cell-Level Table Merge (ADR-010)

Tables are normalized to cell-per-line format for merge:

```markdown
| col1 | col2 |
| a    | b    |
```

Becomes:
```
__CELL_START__|0|0|col1__CELL_END__|0|0|
__CELL_START__|0|1|col2__CELL_END__|0|1|
__CELL_START__|1|0|a__CELL_END__|1|0|
__CELL_START__|1|1|b__CELL_END__|1|1|
```

**Benefit:** Changes to different cells in same row auto-merge (no false conflicts).

### Line Break Preservation (ADR-012)

Multi-line content in table cells:
- **Confluence → Markdown:** `<p>` tags become `<br>` markers
- **Markdown → Confluence:** `<br>` markers become `<p>` tags
- **During merge:** `\n` escaped as `__CELL_NEWLINE__`

**Critical:** Don't modify this conversion logic without comprehensive E2E tests.

---

## Confluence API Nuances

### Storage Format vs. ADF

Confluence has **two** content representations:

1. **Storage Format (XHTML):** `body.storage.value` in API
   - Uses XML namespaces (`ac:`, `ri:`)
   - Legacy format, less structured

2. **ADF (Atlassian Document Format):** `body.atlas_doc_format.value`
   - JSON-based, structured
   - Includes `localId` attributes for stable node targeting
   - **Preferred for surgical updates**

### Macro Preservation

Macros use `ac:` namespace. **Never modify these:**

```xml
<ac:structured-macro ac:name="info">
  <ac:rich-text-body>
    <p>This is an info macro</p>
  </ac:rich-text-body>
</ac:structured-macro>
```

Surgical operations check `tag.name.startswith('ac:')` and skip.

### Optimistic Locking (ADR-007)

Version conflicts detected via version number:

```python
# Fetch with version=5
page = get_page_by_id("123456")  # Returns version=5

# Someone else updates → version=6

# Your update fails
update_page(page_id="123456", version=5)  # 409 Conflict!
```

**Behavior:** Fail-fast with `VersionConflictError`. Let CLI layer handle retry/merge.

### Rate Limiting (ADR-005)

**Only retry on HTTP 429**, fail-fast on everything else:

- 401 (auth) → `InvalidCredentialsError` (no retry)
- 404 → `PageNotFoundError` (no retry)
- 409 → `VersionConflictError` (no retry)
- 429 → Exponential backoff: 1s → 2s → 4s (max 3 retries)

---

## Testing Strategy

### Test Structure

```
tests/
  unit/          # Fast, mocked dependencies
  e2e/           # Real Confluence (CONFSYNCTEST space)
  integration/   # Real Pandoc, mocked Confluence (planned)
```

### E2E Test Space

**Space:** `CONFSYNCTEST`
**Credentials:** `.env` file (CONFLUENCE_URL, CONFLUENCE_USER, CONFLUENCE_API_TOKEN)

**Important:** E2E tests create/modify/delete real pages. Use `@pytest.mark.e2e` decorator.

### Test Naming Convention

```python
def test_<function>_<scenario>_<expected>():
    """What the test verifies."""
```

Example: `test_apply_operations_with_version_conflict_raises_error()`

### Mock Patterns

**Mocking Confluence API:**
```python
with patch('src.confluence_client.api_wrapper.Confluence') as mock_conf:
    mock_conf.return_value.get_page_by_id.return_value = {
        'id': '123456',
        'version': {'number': 5},
        'body': {'storage': {'value': '<p>Test</p>'}}
    }
```

**Mocking Pandoc:**
```python
with patch('subprocess.run') as mock_run:
    mock_run.return_value = Mock(
        returncode=0,
        stdout='<p>Test</p>',
        stderr=''
    )
```

---

## Code Conventions

### Type Hints

**Required** on all public APIs. Use `Optional[T]` for nullable, not `T | None` (Python 3.9 compat).

```python
def get_page_snapshot(
    page_id: str,
    version: Optional[int] = None
) -> PageSnapshot:
```

### Error Handling

Use **typed exceptions** from `errors.py`:

```python
from src.confluence_client.errors import PageNotFoundError

if page_data is None:
    raise PageNotFoundError(page_id=page_id)
```

**Never:** Catch `Exception` unless re-raising with context.

### Subprocess Safety

**Never use `shell=True`** (security). Always pass `timeout`:

```python
subprocess.run(
    ['pandoc', '-f', 'markdown', '-t', 'html'],
    input=markdown,
    capture_output=True,
    text=True,
    timeout=10,  # Always specify
    check=False  # Handle errors manually
)
```

### Credential Security

**Never log credentials.** Use sanitization:

```python
# In api_wrapper.py
def _sanitize_credentials(self, text: str) -> str:
    """Remove credentials from error messages (H5)."""
    # See implementation for patterns
```

---

## Domain-Specific Knowledge

### Confluence Page Hierarchy

Pages form a tree:

```
Space Root
├── Engineering
│   ├── Architecture
│   └── Runbooks
└── Product
    └── Roadmap
```

**Parent ID:** Optional. If `None`, page is space root.

### Page Title Uniqueness

Titles must be unique **per parent**:

```python
# OK: Different parents
create_page(title="API", parent_id="123")  # Under Engineering
create_page(title="API", parent_id="456")  # Under Product

# FAIL: Same parent
create_page(title="API", parent_id="123")
create_page(title="API", parent_id="123")  # PageAlreadyExistsError
```

### Frontmatter for Metadata

Local markdown files include YAML frontmatter:

```yaml
---
page_id: "123456"
space_key: "TEAM"
title: "API Documentation"
version: 12
parent_id: "789"
labels: ["api", "public"]
---

# API Documentation

Content here...
```

**Critical:** `page_id` is the source of truth for updates. Title changes OK.

---

## Current Implementation Status

### Epic 01: COMPLETE ✅

- Confluence API integration (auth, CRUD, retry, errors)
- Bidirectional XHTML↔markdown conversion (markdownify + Pandoc)
- Surgical updates (XHTML via position, ADF via localId)
- Macro preservation, version locking, error handling
- **Tests:** 159 tests (138 unit + 21 E2E), 87% coverage

### Epic 02-04: PLANNED

- **Epic 02:** File structure & mapping (local dirs mirroring Confluence hierarchy)
- **Epic 03:** Git integration (custom merge driver, conflict detection)
- **Epic 04:** CLI (sync commands, dry-run, status)

### Known Limitations

1. **No inline comment preservation** - Comments deleted during update (Confluence API limitation)
2. **No attachment sync** - URLs preserved, binary content not synced
3. **Confluence Data Center untested** - Only Cloud tested
4. **Draw.io macros unsupported** - Binary content cannot convert

---

## Common Gotchas

### 1. Markdown Tables Must Be Pipe Format

**Supported:**
```markdown
| Col1 | Col2 |
|------|------|
| A    | B    |
```

**Not Supported:** Grid tables, simple tables (Pandoc variants)

### 2. Line Breaks in Cells

Use `<br>` tags, not `\n`:

```markdown
| Cell with<br>multiple lines |
```

**Why:** Markdown parsers treat literal `\n` as space.

### 3. Version Numbers Are Per-Page

```python
# Page 123 at version 5
# Page 456 at version 12

update_page("123", version=5)  # OK
update_page("456", version=5)  # FAIL - wrong version
```

### 4. Empty Markdown Conversion

Empty string or whitespace-only markdown **must not** be sent to Pandoc:

```python
if not markdown or not markdown.strip():
    return ""  # Don't call Pandoc
```

### 5. Surgical Operations Order Matters

Apply operations in this order to avoid cascading failures:

1. `DELETE_BLOCK` (removes content)
2. `INSERT_BLOCK` (adds content)
3. `UPDATE_TEXT` (modifies existing)
4. `CHANGE_HEADING_LEVEL` (structural change)
5. Table operations (highly specific)

---

## Development Workflow

### Running Tests

```bash
# Unit tests only (fast)
pytest tests/unit/

# E2E tests (requires .env with Confluence creds)
pytest tests/e2e/ -v

# All tests
pytest

# Coverage report
pytest --cov=src --cov-report=html
```

### Linting & Type Checking

```bash
# Linting
ruff check src/ tests/

# Type checking (strict mode)
mypy src/

# Auto-format
ruff format src/ tests/
```

### Adding New ADRs

When making significant architectural decisions:

1. Create `docs/architecture/ADR/ADR-XXX-short-name.md`
2. Follow template in `ADR/README.md`
3. Update ADR index
4. Reference in code comments where relevant

---

## Key Files Reference

### Core Modules

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `src/confluence_client/api_wrapper.py` | Confluence API client | `APIWrapper`, all CRUD methods |
| `src/page_operations/page_operations.py` | Orchestration layer | `PageOperations`, `get_page_snapshot`, `update_page_surgical_adf` |
| `src/page_operations/surgical_editor.py` | XHTML surgical editing | `SurgicalEditor.apply()` |
| `src/page_operations/adf_editor.py` | ADF surgical editing | `AdfEditor.apply_operations()` |
| `src/content_converter/markdown_converter.py` | Format conversion | `xhtml_to_markdown`, `markdown_to_xhtml` |
| `src/git_integration/table_merge.py` | Cell-level 3-way merge | `merge_content_with_table_awareness` |

### Configuration

| File | Purpose |
|------|---------|
| `.env` | Confluence credentials (never commit!) |
| `pytest.ini` | Test configuration |
| `pyproject.toml` | Project metadata, dependencies |
| `.gitignore` | Excludes .env, __pycache__, etc. |

---

## Performance Targets

| Metric | Target | Current Status |
|--------|--------|----------------|
| API calls per page | <5 | ✅ 3-4 typical |
| Memory usage | <500MB | ✅ <100MB for typical pages |
| Test suite runtime | <30s unit, <2min E2E | ✅ ~18s unit |
| Coverage | >90% | ✅ 87% (Epic 01) |

---

## Security Requirements

1. **No credentials in logs** - Use `_sanitize_credentials()` (H5)
2. **No shell injection** - Never `shell=True` in subprocess
3. **Input validation** - Validate page IDs, URLs, file paths (C1, M4)
4. **XXE prevention** - Use `html.parser` not `lxml` for user content (M3)
5. **Path traversal protection** - Validate file paths (C1)

---

## When Working on This Project

### Before Making Changes

1. Read relevant ADR if modifying core architecture
2. Check test coverage of affected modules
3. Consider impact on both update paths (XHTML and ADF)
4. Verify Confluence API compatibility

### After Making Changes

1. Run full unit test suite (`pytest tests/unit/`)
2. Add/update tests for new functionality
3. Update docstrings for public API changes
4. Run type checker (`mypy src/`)
5. Consider E2E test if touching API layer

### Red Flags 🚩

- Adding `shell=True` to subprocess calls
- Catching bare `Exception` without re-raising
- Modifying `ac:` namespace elements
- Removing version number from update calls
- Adding credentials to log messages
- Returning `None` instead of raising typed exception

---

## Useful Commands

```bash
# Find all Confluence API calls
grep -r "self\._client\." src/confluence_client/

# Find all surgical operations
grep -r "OperationType\." src/

# Find all error raises
grep -r "raise.*Error" src/

# Check for shell=True (should be empty)
grep -r "shell=True" src/

# Find todos/fixmes
grep -rn "TODO\|FIXME" src/
```

---

**Remember:** When in doubt about architectural decisions, check `docs/architecture/ADR/`. When in doubt about domain knowledge, check `docs/architecture/12-glossary.md`.
