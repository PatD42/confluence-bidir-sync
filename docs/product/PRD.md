# Product Requirements Document (PRD)

## confluence-bidir-sync

---

## 1. Executive Summary

**confluence-bidir-sync** is a Python library and CLI tool that enables bidirectional synchronization between Confluence Cloud pages and local markdown files. It allows developers and technical writers to edit documentation in Confluence while enabling Agentic teams to CRUD documentation locally, with full git version control, while maintaining compatibility with Confluence's rich content features.

The tool bridges the gap between Confluence's web-based WYSIWYG editor and the developer workflow of editing text files locally. Users can pull Confluence pages as markdown, edit them with familiar tools (VS Code, vim, etc.), and push changes back to Confluence without losing macros, formatting, or page hierarchy. While one-way sync projects exist, this is the biggest unique value of the project: performing "surgical" updates to confluence pages so that all Confluence value add (macros, labels, page hierarchy) are preserved.

**Key Value Proposition**: Work in Confluence Cloud or in local markdown transparently.

---

## 2. Problem Statement

### 2.1 Pain Points with Confluence Editing

1. **Web-Only Editing**: Confluence requires a browser to edit content. Great for human, terrible for agentic team who trive with local content in markdown format, espcially if they use RAG tools to quickly find relevant information in a large collection of documents.

2. **Slow API Interactions**: AI coding agents working with Confluence must make multiple API calls, which slow, token-expensive and unfriendly to RAG tools. Agents and local tools work better with local text files.

3. **No Offline Access**: Editing documentation requires network access to Confluence.

4. **Batch Operations Difficult**: Renaming a term across 50 pages, or applying formatting changes, requires manual editing of each page.

### 2.2 Target Audience Needs

**Users**: need documentation that preserves the rich features Confluence provides (macros, tables, code blocks)
**Agentic teams: need documentation locally, in markdown format.

---

## 3. Goals & Success Metrics

### 3.1 Product Goals

| Goal | Description |
|------|-------------|
| **G1: Bidirectional Sync** | Changes flow both ways - local edits push to Confluence, Confluence edits pull to local |
| **G2: Content Preservation** | Confluence macros, labels and rich content survive round-trip conversion |
| **G3: Merge conflicts management** | Conflicts are handled in using a git-like approach, leveraging a tool such as VS Code to manually resolve conflicts. All conflicts are reviewed at once (eg: detect all conflicts, have user fix all conflicts, then sync) |
| **G4: Page title changes** | Changes in the page's title is handled transparently |
| **G5: Page hierarchy inclusion** | Config defines the the list of root page hierarchy to synchronize from, using filesafe convention. Ex.: {space-key}:/engineering/products/product-we-are-working-on |
| **G6: Page hierarchy exclusion** | Config defines the the list of root page hierarchy to exclude fron synchronization, using filesafe convention. Ex.: {space-key}:/engineering/products/product-we-are-working-on/archives |
| **G7: Confluence metadata in markdown files** | Metadata such page-id is stored as frontmatter content in the markdown file to handle page title changes and moved pages (future) |
| **G8: Forced push or pull** | One-way sync, overwriting existing content on the other end. Push = local overwrites confluence. Pull = confluence overwrites local |
| **G9: Single page sync** | While the tool is built for folders and page hierachies, a use may request that a single content be synchronized |
| **G10: Dry run** | Option dry-run shows what would be changed on each side and where there would be conflicts, but does not make any changes |

### 3.2 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Round-trip Fidelity** | 100% for supported content types | Content pulled, edited, pushed should be identical to direct Confluence edit |
| **Error Clarity** | 100% of errors have actionable messages | All exception types have descriptive messages |
| **Test Coverage** | >90% for core library | pytest-cov reporting |

### 3.3 Roadmap features

- Change detection deamon - Local folders monitoring
- Change detection deamon - Confluence periodic polling
- Page moved to a different location
- Internal page reference conversion (content that includes link to another page that is monitored)
- Page deletion
- Additional confluence metadata in Frontmatter (ex.: labels)
- Auto Convert Mermaid diagrams using mermaid.ink to easily view mermaid diagrams in Confluence

### 3.4 Non-Goals / Out of Scope

- Real-time collaborative editing (Confluence handles this natively)
- Support for Confluence Data Center (Data center not tested and not factored in for MVP)
- Binary attachment synchronization (URLs preserved, content not synced)
- OAuth authentication flows (API token authentication only)
- Confluence space creation/deletion (focus is on page content)
- Inline comments preservation - they will likely be deleted during the update (as per Confluence API documentation).

---

## 5. User Stories

### 5.1 Core Workflow Stories

#### US-1: Happy path 2-way sync

**As a** developer,
**I want to** sync Confluence pages with my local markdown content folder,
**So that** Use tools that only work on local files (doing CRUD).

**Acceptance Criteria**:
- [ ] CLI command `confluence-sync` updates both Confluence and local. User is notified if merge conflicts need to be resolved
- [ ] Local pages are clean, readable markdown
- [ ] Confluence pages have macros and labels preserved
- [ ] Page metadata (pade-id) is stored in frontmatter
- [ ] File is saved locally in the proper hierarchical path using filesafe name infered from page title

---

#### US-2: Handle Version Conflicts

**As a** developer,
**I want to** be notified when there are merge conflicts between my local version and Confluence,
**So that** I don't accidentally overwrite someone else's changes.

**Acceptance Criteria**:
- [ ] Sync fails.
- [ ] Error message indicates conflict. The merge conflict tool (ex.: VS code) is called after all conflicts have been identified
- [ ] User can force push (from local to Confluence) with `--forcePush` flag
- [ ] User can force pull (from Confluence to local) with `--forcePull` flag

---

### 5.2 Error Handling Stories

#### US-3: Invalid Credentials

**As a** user,
**I want** clear error messages when my API credentials are wrong, or the endpoint is not responding,
**So that** I can fix authentication and endpoint issues quickly.

**Acceptance Criteria**:
- [ ] Error message: "API key is invalid (user: {email}, endpoint: {url})"
- [ ] Suggests checking API token and permissions
- [ ] Does not retry on authentication failure

---

#### US-4: Rate Limit Handling

**As a** user syncing many pages,
**I want** the tool to automatically handle rate limits,
**So that** bulk operations complete without manual intervention.

**Acceptance Criteria**:
- [ ] 429 responses trigger automatic retry
- [ ] Exponential backoff: 1s, 2s, 4s delays
- [ ] After 3 retries, fails with actionable error message
- [ ] Progress indicator shows retry status

---

#### US-5: Git Merge Integration

**As a** developer,
**I want** the sync tool to integrate with git merge,
**So that** conflicting documentation changes can be resolved like code conflicts.

**Acceptance Criteria**:
- [ ] Custom git merge driver for Confluence markdown files
- [ ] Three-way merge support (local, remote, base)
- [ ] Conflict markers compatible with standard git tools

---

## 6. Functional Requirements

### 6.1 Epic 01: Confluence API Integration & Surgical Updates (COMPLETE)

Complete foundation layer providing API integration, content conversion, and surgical XHTML updates. This epic consolidates the originally planned Epic 01 (API), Epic 04 (Content Parsing), and Epic 05 (Surgical Updates) into a single cohesive implementation.

**Key Insight**: Markdown is the editing surface for agents/tools. XHTML is the source of truth that gets surgically modified via discrete operations. Macros are preserved by never touching `ac:` elements.

| Requirement | Description | Status |
|-------------|-------------|--------|
| **FR-1.1** | Authentication via API token loaded from .env file | Done |
| **FR-1.2** | Fetch page by ID returning storage format (XHTML) | Done |
| **FR-1.3** | Fetch page by space key + title | Done |
| **FR-1.4** | List child pages of a parent page | Done |
| **FR-1.5** | Update page content with automatic version increment | Done |
| **FR-1.6** | Create new page with optional parent | Done |
| **FR-1.7** | Duplicate title detection on create | Done |
| **FR-1.8** | XHTML to markdown conversion (via Pandoc) | Done |
| **FR-1.9** | Markdown to XHTML conversion (via Pandoc) | Done |
| **FR-1.10** | Typed exception hierarchy (7 error types) | Done |
| **FR-1.11** | Exponential backoff for 429 rate limits | Done |
| **FR-1.12** | Version conflict detection (409 errors) | Done |
| **FR-1.13** | Parse XHTML into content blocks (headings, paragraphs, tables, lists) | Done |
| **FR-1.14** | Identify block types (HEADING, PARAGRAPH, TABLE, LIST, CODE, MACRO) | Done |
| **FR-1.15** | Apply UPDATE_TEXT surgical operation | Done |
| **FR-1.16** | Apply DELETE_BLOCK surgical operation | Done |
| **FR-1.17** | Apply INSERT_BLOCK surgical operation | Done |
| **FR-1.18** | Apply CHANGE_HEADING_LEVEL operation | Done |
| **FR-1.19** | Apply TABLE_INSERT_ROW operation | Done |
| **FR-1.20** | Apply TABLE_DELETE_ROW operation | Done |
| **FR-1.21** | Preserve Confluence macros (ac: namespace never modified) | Done |
| **FR-1.22** | Preserve labels during surgical updates | Done |
| **FR-1.23** | Preserve local-ids during surgical updates | Done |
| **FR-1.24** | PageSnapshot with XHTML + markdown + metadata | Done |

**Implementation Details**:
- API layer: `src/confluence_client/` (api_wrapper, auth, errors, retry_logic)
- Content conversion: `src/content_converter/` (markdown_converter only)
- Page operations: `src/page_operations/` (page_operations, surgical_editor, content_parser, models)
- 159 tests (138 unit + 21 E2E), 87% coverage
- Dependencies: atlassian-python-api, BeautifulSoup4, lxml, Pandoc CLI

**Consolidation Notes**:
- Removed redundant wrappers: PageFetcher, PageUpdater, PageCreator (use APIWrapper directly)
- Removed redundant parser: XHTMLParser (use BeautifulSoup directly)
- MacroPreserver moved to test helpers (surgical updates preserve macros implicitly)

---

### 6.2 Epic 02: File Structure & Mapping (PLANNED)

Local file system representation of Confluence spaces and pages.

| Requirement | Description | Priority |
|-------------|-------------|----------|
| **FR-2.1** | Map Confluence space to local directory structure | High |
| **FR-2.2** | Preserve page hierarchy as nested folders | High |
| **FR-2.3** | Generate markdown files with YAML frontmatter | High |
| **FR-2.4** | Create mapping file (JSON) tracking page IDs to file paths | High |
| **FR-2.5** | Handle page title changes (rename local files) | Medium |
| **FR-2.6** | Handle page moves (reorganize local folders) | Medium |
| **FR-2.7** | Support flat file mode (all pages in one folder) | Low |

**Proposed Structure**:
```
my-project/
  .confluence-sync/
    config.yaml       # Space configuration
  index.md            # Space home page
  getting-started/
    index.md          # Section parent page
    installation.md   # Child page
    configuration.md  # Child page
  api-reference/
    index.md
    endpoints.md
    authentication.md
```

---

### 6.3 Epic 03: Git Integration (PLANNED)

Seamless integration with git version control workflows.

| Requirement | Description | Priority |
|-------------|-------------|----------|
| **FR-3.1** | Custom git merge driver for confluence markdown | High |
| **FR-3.2** | Three-way merge for concurrent edits | High |
| **FR-3.3** | Git hooks for pre-push validation | Medium |
| **FR-3.4** | Conflict detection before push to Confluence | High |
| **FR-3.5** | Integration with GitHub/GitLab PR workflows | Medium |
| **FR-3.6** | Automatic conflict markers in markdown | Medium |

---

### 6.4 Epic 04: CLI & Sync Orchestration (PLANNED)

Command-line interface for all sync operations.

| Requirement | Description | Priority |
|-------------|-------------|----------|
| **FR-4.1** | `confluence-sync` - Sync local and Confluence | High |
| **FR-4.2** | `confluence-sync --forcePush` - Download single page | High |
| **FR-4.3** | `confluence-sync --forcePull` - Upload single page | High |
| **FR-4.4** | `confluence-sync --dryrun` - Dry-run mode for all operations | High |
| **FR-4.5** | `confluence-sync --init {confluence-path} {local-path}` - Minimal config creation | High |

---

## 7. Non-Functional Requirements

### 7.1 Performance

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **Space sync (100 pages)** | <5 minutes | Practical for daily sync |
| **API calls per page** | <5 calls | Minimize rate limit impact |
| **Memory usage** | <500MB | Support large pages without swapping |
| **Concurrent syncs** | 10 parallel | Speed up space-wide operations |

### 7.2 Reliability

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **Retry on transient failure** | 3 retries | Handle network blips |
| **No data loss on failure** | 100% | Never lose local or remote changes |
| **Graceful degradation** | Required | Partial sync better than total failure |
| **Idempotent operations** | Required | Safe to retry any operation |

### 7.3 Security

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| **Credentials in env vars** | Load from .env via python-dotenv | Done |
| **No credentials in logs** | Logging filters credentials | Done |
| **No credentials in git** | .env in .gitignore | Done |
| **HTTPS only** | All Confluence API calls over HTTPS | Done |
| **No shell injection** | No `shell=True` in subprocess | Done |
| **Input validation** | Validate all user input | Done |

### 7.4 Compatibility

| Requirement | Target |
|-------------|--------|
| **Python version** | 3.9+ |
| **Pandoc version** | 3.8.3+ |
| **Operating systems** | macOS, Linux |
| **Confluence** | Cloud only (Data Center not tested) |

### 7.5 Maintainability

| Requirement | Implementation |
|-------------|----------------|
| **Type hints** | 100% type coverage (mypy clean) |
| **Test coverage** | >90% for core library |
| **Documentation** | Docstrings on all public APIs |
| **Linting** | ruff with standard config |
| **Dependency pinning** | Exact versions in requirements.txt |


---

## 9. Dependencies & Assumptions

### 9.1 External Dependencies

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| **atlassian-python-api** | 4.0.7 | Confluence REST API wrapper | Low - well maintained |
| **BeautifulSoup4** | 4.14.3 | XHTML parsing | Low - industry standard |
| **lxml** | 5.3.0 | XML parser for BeautifulSoup | Low - performance focused |
| **python-dotenv** | 1.0.0 | Load credentials from .env | Low - simple utility |
| **Pandoc** | 3.8.3+ | Markdown conversion | Medium - external CLI binary |

### 9.2 Assumptions

1. **Users have Confluence Cloud access**: The tool targets Confluence Cloud customers with API access.

2. **Users have valid API tokens**: Authentication requires pre-generated Atlassian API tokens.

3. **Pandoc is installed**: Users must install Pandoc separately (not bundled).

4. **Network access to Confluence**: The tool requires internet access for sync operations.

5. **Git is available**: Git integration features assume git is installed and configured.

6. **Markdown is sufficient**: Users accept that some Confluence formatting may not map to markdown perfectly.

### 9.3 Constraints

1. **API Rate Limits**: Confluence Cloud enforces rate limits; bulk operations must respect them.

2. **Storage Format Changes**: Atlassian may change storage format; conversion logic may need updates.

3. **Macro Compatibility**: Not all macros can be preserved through markdown conversion.

---

## 10. Risks & Mitigations

### 10.1 Technical Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Pandoc conversion loses formatting** | High | Medium | Extensive round-trip testing; HTML comments for unsupported content |
| **API rate limits block bulk sync** | Medium | Medium | Exponential backoff; incremental sync; parallel limits |
| **Confluence storage format changes** | High | Low | Pin atlassian-python-api version; integration tests |
| **Macro types not supported** | Medium | Medium | Preserve as HTML comments; document limitations |

### 10.2 Product Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Users expect real-time sync** | Medium | Medium | Clear documentation that this is point-in-time sync |
| **Conflict resolution is confusing** | Medium | Medium | Good error messages; conflict workflow documentation |
| **Learning curve too steep** | Medium | Low | Example workflows; getting started guide |

### 10.3 Business Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Atlassian changes API terms** | High | Low | Monitor Atlassian announcements; standard API usage |
| **Competing product from Atlassian** | High | Low | Focus on developer workflow integration (git, CLI) |

---

## 11. Release Plan

### 11.1 Phase 1: Foundation & Precision Editing (COMPLETE)

**Epic 01: Confluence API Integration & Surgical Updates**

- Status: Complete
- Deliverables:
  - Python library for Confluence CRUD operations (`confluence_client/`)
  - Bidirectional content conversion via Pandoc (`content_converter/`)
  - Surgical XHTML updates with 6 operation types (`page_operations/`)
  - PageOperations orchestration with PageSnapshot (XHTML + markdown)
  - Macro preservation (ac: namespace elements never modified)
  - Error handling with 7 typed exception classes
  - Test suite: 159 tests (138 unit + 21 E2E), 87% coverage

**Consolidation**: Originally planned as Epic 01 (API), Epic 04 (Content Parsing), and Epic 05 (Surgical Updates) - consolidated into single Epic 01 during implementation.

---

### 11.2 Phase 2: Local Files (PLANNED)

**Epic 02: File Structure & Mapping**

- Deliverables:
  - Local directory structure mirroring Confluence hierarchy
  - Mapping file tracking page IDs to local paths
  - Frontmatter metadata in markdown files
  - Configuration file for sync settings

**Epic 03: Git Integration**

- Deliverables:
  - Custom git merge driver
  - Conflict detection and resolution workflow
  - Git hooks for validation

---

### 11.3 Phase 3: User Interface (PLANNED)

**Epic 04: CLI & Sync Orchestration**

- Deliverables:
  - Full CLI implementation (`confluence-sync` command)
  - Space-wide sync operations
  - Status and diff commands
  - Dry-run and JSON output modes

---

## Appendix A: Technical Architecture

### A.1 Component Overview (After Consolidation)

```
confluence-bidir-sync/
  src/
    confluence_client/      # Confluence API layer (4 files)
      api_wrapper.py        # HTTP client with CRUD, error translation
      auth.py               # Credential management from .env
      errors.py             # 7 typed exception classes
      retry_logic.py        # Exponential backoff for rate limits
    content_converter/      # Format conversion (1 file)
      markdown_converter.py # Pandoc subprocess wrapper
    models/                 # Shared data structures
      confluence_page.py    # ConfluencePage dataclass
      conversion_result.py  # ConversionResult dataclass
    page_operations/        # High-level operations (4 files)
      models.py             # PageSnapshot, SurgicalOperation, BlockType
      content_parser.py     # XHTML/markdown block extraction
      surgical_editor.py    # 6 operation types for XHTML modification
      page_operations.py    # Orchestration: get_page_snapshot, apply_operations, create_page
    file_mapper/            # (Epic 02) Local file operations
    cli/                    # (Epic 04) Command-line interface
```

**Removed During Consolidation**:
- `page_fetcher.py`, `page_updater.py`, `page_creator.py` - Use APIWrapper directly
- `xhtml_parser.py` - Use BeautifulSoup directly
- `macro_preserver.py` - Moved to test helpers (surgical updates don't need it)

### A.2 Data Flow

```
Confluence Cloud
      |
      | Confluence REST API v2
      v
[api_wrapper.py] <-- [auth.py] <-- .env credentials
      |
      | Page JSON with XHTML (body.storage.value)
      v
[page_operations.py] --> Orchestrates read/write
      |
      ├─────────────────────────────┐
      |                             |
      v                             v
[markdown_converter.py]    [surgical_editor.py]
      |                             |
      | Pandoc subprocess           | Apply operations to XHTML
      |                             | (never touch ac: elements)
      v                             v
PageSnapshot                  Modified XHTML
(xhtml + markdown)            (preserves macros/labels/ids)
      |
      v
[file_mapper.py] --> Local .md file (Epic 02)
```

**Key Insight**: Markdown is for reading/editing by agents. XHTML is surgically modified. Macros are preserved by never touching `ac:` namespace elements.

### A.3 Error Handling

```
ConfluenceError (base)
  |-- InvalidCredentialsError  # 401 Unauthorized
  |-- PageNotFoundError        # 404 Not Found
  |-- PageAlreadyExistsError   # Duplicate title on create
  |-- APIUnreachableError      # Network/timeout errors
  |-- APIAccessError           # Other API failures, rate limit exhaustion
  |-- ConversionError          # Pandoc or parsing failures
```

---

## Appendix B: Confluence Macro Handling

### B.1 Macro Preservation Strategy

Confluence macros use the `ac:` XML namespace. The surgical update approach preserves them implicitly:

1. **Detection**: `BeautifulSoup.find_all(lambda tag: tag.name.startswith('ac:'))`
2. **Preservation**: Surgical operations NEVER modify `ac:` namespace elements
3. **Result**: Macros remain intact through all update operations

**Note**: The HTML comment approach (`<!-- CONFLUENCE_MACRO: ... -->`) was the initial Epic 01 design but was superseded by surgical updates. The comment-based approach is preserved only in `tests/helpers/macro_test_utils.py` for E2E fetch journey testing.

### B.2 Known Limitations

| Macro Type | Support Level | Notes |
|------------|---------------|-------|
| `ac:structured-macro` | Preserved | Generic macro container |
| `ac:image` | Preserved | Image references maintained |
| `ac:link` | Preserved | Internal links maintained |
| `ac:emoticon` | Preserved | Emoji macros |
| `ac:task-list` | Preserved | Task list items |
| **Draw.io** | Not Supported | Binary content cannot be converted |
| **Jira macro** | Preserved | Query preserved, results are live |

---

## Appendix C: Glossary

| Term | Definition |
|------|------------|
| **Storage Format** | Confluence's internal XHTML representation of page content |
| **Confluence Cloud** | Atlassian's SaaS version of Confluence |
| **Confluence Data Center** | Self-hosted Confluence (not supported) |
| **Space** | Top-level container for Confluence pages |
| **Page ID** | Unique numeric identifier for a Confluence page |
| **Space Key** | Short code identifying a Confluence space (e.g., "TEAM") |
| **Macro** | Confluence extension providing rich functionality (code blocks, tables, etc.) |
| **ac: namespace** | XML namespace prefix for Confluence macros |
| **Version Number** | Incremented integer tracking page revisions |
| **Optimistic Locking** | Conflict detection using version numbers |

---
