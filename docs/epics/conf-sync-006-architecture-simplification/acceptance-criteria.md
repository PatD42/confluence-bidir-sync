---
epic_id: CONF-SYNC-006
title: Acceptance Criteria - Architecture Simplification
created_date: 2026-01-31
---

# Acceptance Criteria: CONF-SYNC-006

## AC-1: Single CQL Query

### AC-1.1: CQL Query Replaces Recursive Calls
**Given** a parent page with 50 descendant pages across 4 levels
**When** HierarchyBuilder.build_hierarchy() is called
**Then** exactly 1 CQL API call is made (not 50+ recursive calls)
**And** all 50 pages are returned with their metadata

### AC-1.2: CQL Query Returns Required Fields
**Given** a CQL query for descendants
**When** the query executes
**Then** each result includes:
  - `id` (page_id)
  - `title`
  - `version.when` (last_modified timestamp)
  - `ancestors` (list of parent pages)
  - `space.key`

### AC-1.3: Page Limit Enforcement
**Given** a parent page with 150 descendant pages
**And** page_limit is set to 100
**When** sync runs
**Then** PageLimitExceededError is raised with count=150, limit=100

### AC-1.4: CQL Pagination Handling
**Given** a parent page with 300 descendant pages
**And** Confluence returns paginated results (limit 25 per page)
**When** HierarchyBuilder queries descendants
**Then** all 300 pages are fetched across multiple pagination requests
**And** results are combined into single response

---

## AC-2: Frontmatter Simplification

### AC-2.1: New Files Have Minimal Frontmatter
**Given** a page is pulled from Confluence
**When** the markdown file is written
**Then** frontmatter contains only:
```yaml
---
page_id: "123456"
---
```

### AC-2.2: Parser Accepts Minimal Frontmatter
**Given** a markdown file with only `page_id` in frontmatter
**When** FrontmatterHandler.parse() is called
**Then** LocalPage is returned with page_id and content populated

### AC-2.3: Backward Compatibility
**Given** an existing markdown file with old frontmatter format:
```yaml
---
page_id: "123456"
space_key: "TEAM"
title: "Old Format"
last_synced: "2024-01-15T10:30:00Z"
confluence_version: 5
---
```
**When** FrontmatterHandler.parse() is called
**Then** LocalPage is returned successfully (extra fields ignored)
**And** page_id is extracted correctly

### AC-2.4: Updated Files Use New Format
**Given** a file with old frontmatter format
**When** the file is synced and rewritten
**Then** frontmatter is simplified to page_id only

---

## AC-3: Title Derivation

### AC-3.1: Title from CQL for Existing Pages
**Given** a local file with page_id "123456"
**And** CQL query returns title "Product Overview" for page 123456
**When** the page is pushed to Confluence
**Then** title "Product Overview" is used (from CQL, not file)

### AC-3.2: Title from H1 for New Pages
**Given** a new local file with no page_id (page_id: null)
**And** content starts with `# My New Feature`
**When** the page is created in Confluence
**Then** page title is "My New Feature"

### AC-3.3: Title Fallback to Filename
**Given** a new local file with no page_id
**And** content has no H1 heading
**And** filename is `feature-overview.md`
**When** the page is created in Confluence
**Then** page title is "feature-overview"

### AC-3.4: Error for No Title
**Given** a new local file with no page_id
**And** content has no H1 heading
**And** filename cannot be used (e.g., invalid characters)
**When** sync attempts to create the page
**Then** error is raised: "Cannot determine title for new page"

---

## AC-4: LocalPage Simplification

### AC-4.1: LocalPage Dataclass
**Given** the LocalPage model
**Then** it has only these fields:
  - `file_path: str`
  - `page_id: Optional[str]`
  - `content: str`

### AC-4.2: No References to Deprecated Fields
**Given** any source file in `src/`
**When** searched for `local_page.space_key`, `local_page.title`, `local_page.last_synced`, `local_page.confluence_version`
**Then** no matches are found

---

## AC-5: Single-File Sync

### AC-5.1: Single File Sync Works
**Given** configuration is initialized
**And** multiple files exist locally
**When** `confluence-sync docs/specific-page.md` is run
**Then** only `specific-page.md` is synced
**And** other files are not affected

### AC-5.2: Baseline Updated for Single File
**Given** `page-A.md` is synced individually
**When** sync completes successfully
**Then** baseline for page-A is updated in `.confluence-sync/baseline/`

### AC-5.3: Global Timestamp Not Updated
**Given** `state.yaml` has `last_synced: "2026-01-30T10:00:00"`
**When** single file sync runs for `page-A.md`
**Then** `state.yaml.last_synced` remains "2026-01-30T10:00:00" (unchanged)

### AC-5.4: Next Full Sync Handles Correctly
**Given** page-A was synced individually (baseline updated, timestamp unchanged)
**When** next full sync runs
**Then** page-A is flagged as potential conflict (both sides changed since last_synced)
**And** 3-way merge finds local = baseline = remote
**And** no action is taken for page-A (correctly identified as no-op)

---

## AC-6: File Logging

### AC-6.1: Logdir Creates File
**Given** `--logdir ./logs` is passed
**When** sync runs at 2026-01-31 14:30:22 local time
**Then** log file is created: `./logs/confluence-sync-20260131-143022.log`

### AC-6.2: Directory Auto-Created
**Given** `./logs` directory does not exist
**When** `--logdir ./logs` is passed
**Then** directory is created automatically
**And** log file is written inside it

### AC-6.3: Local Timezone in Filename
**Given** local timezone is America/Toronto (EST, UTC-5)
**And** current time is 2026-01-31 19:30:00 UTC
**When** sync runs with `--logdir`
**Then** filename uses local time: `confluence-sync-20260131-143000.log`

### AC-6.4: Local Timezone in Log Entries
**Given** `--logdir ./logs` is passed
**When** log entries are written
**Then** timestamps use local timezone (not UTC)
**Example:** `2026-01-31 14:30:22 - src.cli.sync_command - INFO - Starting sync`

### AC-6.5: No Logdir Uses Stderr
**Given** `--logdir` is not passed
**When** sync runs
**Then** logs are written to stderr (current behavior)

---

## AC-7: CLI Simplification

### AC-7.1: No Subcommands
**Given** the CLI is installed
**When** `confluence-sync sync` is run
**Then** error: "No such command 'sync'"

### AC-7.2: Default Runs Sync
**Given** configuration exists
**When** `confluence-sync` is run with no arguments
**Then** bidirectional sync executes

### AC-7.3: Init Flag Works
**Given** no configuration exists
**When** `confluence-sync --init "ProductXYZ:/" ./docs/` is run
**Then** `.confluence-sync/config.yaml` is created
**And** page "ProductXYZ:/" is resolved to page ID

### AC-7.4: Dry Run at Top Level
**Given** configuration exists
**When** `confluence-sync --dry-run` is run
**Then** changes are previewed without applying

### AC-7.5: Force Flags at Top Level
**Given** configuration exists
**When** `confluence-sync --force-push` is run
**Then** local content overwrites Confluence

### AC-7.6: Single File as Positional Argument
**Given** configuration exists
**When** `confluence-sync docs/page.md` is run
**Then** only `docs/page.md` is synced

### AC-7.7: Combined Flags
**Given** configuration exists
**When** `confluence-sync --dry-run --logdir ./logs -v 2` is run
**Then** dry-run executes with debug logging to file

---

## AC-8: Mandatory Package Installation

### AC-8.1: README Documents Installation
**Given** the README.md file
**Then** it includes:
```bash
pip install -e .
```
**And** states installation is required before use

### AC-8.2: Error Messages Use confluence-sync
**Given** configuration file does not exist
**When** sync runs
**Then** error message shows:
```
Configuration file not found: .confluence-sync/config.yaml
Run 'confluence-sync --init "SPACE:/" ./local-path' to initialize
```

### AC-8.3: Help Text Uses confluence-sync
**Given** `confluence-sync --help` is run
**Then** examples show `confluence-sync` command (not `python -m`)
