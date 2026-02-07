# File Mapper Library

Bidirectional mapping between Confluence page hierarchies and local markdown files with YAML frontmatter.

## Overview

The `file_mapper` library provides Python abstractions for syncing Confluence spaces to local markdown files and vice versa. It enables offline access, RAG tool integration, and local editing workflows while maintaining bidirectional synchronization with Confluence.

### Key Features

- **CQL-Based Page Discovery** (ADR-008): Discover page hierarchies using Confluence Query Language
- **Filesafe Filename Conversion** (ADR-010): Convert page titles to valid filenames with case preservation
- **YAML Frontmatter** (ADR-009): Embed Confluence metadata in markdown files
- **Atomic File Operations** (ADR-011): Two-phase commit ensures all-or-nothing writes
- **Hierarchical Folder Structure**: Mirror Confluence page hierarchy as nested folders
- **Initial Sync Direction Detection** (ADR-014): Automatically detect which side to sync from
- **Page Exclusion** (ADR-015): Exclude specific pages and their descendants from sync
- **Page Limit Enforcement** (ADR-013): Enforce 100 page limit per hierarchy level (MVP)

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Basic Usage

```python
from src.file_mapper import FileMapper, ConfigLoader
from src.confluence_client.auth import Authenticator

# Initialize with authentication
auth = Authenticator()
mapper = FileMapper(auth)

# Load configuration
config = ConfigLoader.load('.confluence-sync/config.yaml')

# Sync all configured spaces
mapper.sync_spaces(config)
```

### Configuration

Create a configuration file at `.confluence-sync/config.yaml`:

```yaml
spaces:
  - space_key: "TEAM"
    parent_page_id: "123456"
    local_path: "./team-space"
    exclude_page_ids:
      - "789012"  # Archives page

page_limit: 100
force_pull: false
force_push: false
temp_dir: ".confluence-sync/temp"
```

See `config/example.yaml` for a complete configuration example with detailed comments.

## Filesafe Conversion Rules

The library converts Confluence page titles to filesystem-safe filenames following **ADR-010: Filesafe Conversion with Case Preservation**.

### Conversion Rules

| Input Character | Conversion | Example |
|----------------|------------|---------|
| Space | `→ -` (hyphen) | "Customer Feedback" → "Customer-Feedback.md" |
| Colon `:` | `→ --` (double hyphen) | "API Reference: Getting Started" → "API-Reference--Getting-Started.md" |
| Special chars (`/`, `\`, `?`, `%`, `*`, `\|`, `"`, `<`, `>`, `&`) | `→ -` (hyphen) | "Q&A Session" → "Q-A-Session.md" |
| Leading/trailing hyphens | Trimmed | "- Draft -" → "Draft.md" |
| Multiple consecutive hyphens (3+) | Collapsed to `--` | "A---B" → "A--B.md" |
| **Case** | **Preserved** | "MyPage" → "MyPage.md" (not "mypage.md") |

### Filesafe Conversion Examples

```python
from src.file_mapper import FilesafeConverter

# Basic conversion
FilesafeConverter.title_to_filename("Customer Feedback")
# Returns: "Customer-Feedback.md"

# Colon conversion (common in documentation)
FilesafeConverter.title_to_filename("API Reference: Getting Started")
# Returns: "API-Reference--Getting-Started.md"

# Special character handling
FilesafeConverter.title_to_filename("Q&A Session")
# Returns: "Q-A-Session.md"

# Case preservation
FilesafeConverter.title_to_filename("MyCompanyName")
# Returns: "MyCompanyName.md"

# Complex example with multiple special characters
FilesafeConverter.title_to_filename("How-To: Setup & Configure?")
# Returns: "How-To--Setup-Configure.md"

# Reverse conversion (best effort)
FilesafeConverter.filename_to_title("Customer-Feedback.md")
# Returns: "Customer Feedback"
```

**Note**: Reverse conversion is lossy - double hyphens (`--`) are always converted to colons, even if the original title contained consecutive hyphens.

## Architecture

### Component Hierarchy

```
FileMapper (Orchestration)
├── HierarchyBuilder (CQL Queries & Tree Building)
│   └── APIWrapper (Confluence API Access)
├── FilesafeConverter (Title → Filename Conversion)
├── FrontmatterHandler (YAML Frontmatter Operations)
├── ConfigLoader (Configuration Management)
└── PageCreator (Page Creation & Updates)
```

### Core Components

#### FileMapper

Main orchestration class that coordinates all sync operations.

```python
from src.file_mapper import FileMapper
from src.confluence_client.auth import Authenticator

auth = Authenticator()
mapper = FileMapper(auth)
config = ConfigLoader.load('.confluence-sync/config.yaml')
mapper.sync_spaces(config)
```

**Key Methods:**
- `sync_spaces(config: SyncConfig)`: Sync all configured spaces

#### HierarchyBuilder

Discovers Confluence page hierarchies using CQL queries.

```python
from src.file_mapper import HierarchyBuilder
from src.confluence_client.auth import Authenticator

auth = Authenticator()
builder = HierarchyBuilder(auth)

# Build hierarchy from parent page
root = builder.build_hierarchy(
    parent_page_id="123456",
    space_key="TEAM",
    exclude_page_ids=["789012"],
    page_limit=100
)

# Access hierarchy
print(f"Root page: {root.title}")
for child in root.children:
    print(f"  Child: {child.title}")
```

**Key Features:**
- CQL-based discovery: `parent = {page_id} AND space = {space_key}`
- Recursive tree building
- Page limit enforcement (100 pages per level)
- Page exclusion support

#### FilesafeConverter

Converts page titles to filesafe filenames with case preservation.

```python
from src.file_mapper import FilesafeConverter

# Convert title to filename
filename = FilesafeConverter.title_to_filename("API Reference: Setup")
# Returns: "API-Reference--Setup.md"

# Convert filename back to title
title = FilesafeConverter.filename_to_title(filename)
# Returns: "API Reference: Setup"
```

See [Filesafe Conversion Rules](#filesafe-conversion-rules) for detailed conversion rules.

#### FrontmatterHandler

Parses and generates YAML frontmatter in markdown files.

```python
from src.file_mapper import FrontmatterHandler

handler = FrontmatterHandler()

# Parse existing file
with open('page.md', 'r') as f:
    content = f.read()

frontmatter, body = handler.parse(content)
print(f"Page ID: {frontmatter['page_id']}")
print(f"Title: {frontmatter['title']}")

# Generate new file with frontmatter
markdown = handler.generate(
    page_id="123456",
    space_key="TEAM",
    title="My Page",
    last_synced="2024-01-15T10:30:00Z",
    confluence_version=5,
    content="# My Page\n\nContent here..."
)
```

**Frontmatter Format (ADR-009):**
```yaml
---
page_id: "123456"
space_key: "TEAM"
title: "My Page"
last_synced: "2024-01-15T10:30:00Z"
confluence_version: 5
---

# My Page

Content here...
```

**Required Fields:**
- `space_key`: Confluence space key (e.g., "TEAM")
- `title`: Page title
- `last_synced`: ISO 8601 timestamp of last sync
- `confluence_version`: Page version number at last sync

**Optional Fields:**
- `page_id`: Confluence page ID (null for new local files not yet synced)

#### ConfigLoader

Loads and validates configuration from YAML files.

```python
from src.file_mapper import ConfigLoader, SyncConfig, SpaceConfig

# Load configuration
config = ConfigLoader.load('.confluence-sync/config.yaml')

# Access configuration
for space in config.spaces:
    print(f"Space: {space.space_key}")
    print(f"Parent: {space.parent_page_id}")
    print(f"Local path: {space.local_path}")

# Create and save configuration
config = SyncConfig(
    spaces=[
        SpaceConfig(
            space_key="TEAM",
            parent_page_id="123456",
            local_path="./team-space",
            exclude_page_ids=["789012"]
        )
    ],
    page_limit=100,
    force_pull=False,
    force_push=False
)

ConfigLoader.save(config, '.confluence-sync/config.yaml')
```

**Configuration Structure (ADR-012):**
- Parent pageID serves as hierarchy anchor (not file paths)
- Supports multiple spaces
- Per-space page exclusion
- Global sync options (force flags, page limits)

## Data Models

### PageNode

Represents a node in the Confluence page hierarchy.

```python
from src.file_mapper import PageNode

node = PageNode(
    page_id="123456",
    title="My Page",
    parent_id="654321",
    children=[],
    last_modified="2024-01-15T10:30:00Z",
    space_key="TEAM"
)
```

### LocalPage

Represents a local markdown file with frontmatter.

```python
from src.file_mapper import LocalPage

page = LocalPage(
    file_path="./team-space/My-Page.md",
    page_id="123456",
    space_key="TEAM",
    title="My Page",
    last_synced="2024-01-15T10:30:00Z",
    confluence_version=5,
    content="# My Page\n\nContent..."
)
```

### SpaceConfig

Configuration for a single Confluence space.

```python
from src.file_mapper import SpaceConfig

space = SpaceConfig(
    space_key="TEAM",
    parent_page_id="123456",
    local_path="./team-space",
    exclude_page_ids=["789012"]
)
```

### SyncConfig

Overall sync configuration with options.

```python
from src.file_mapper import SyncConfig, SpaceConfig

config = SyncConfig(
    spaces=[space],
    page_limit=100,
    force_pull=False,
    force_push=False,
    temp_dir=".confluence-sync/temp"
)
```

## Error Handling

All exceptions inherit from `FileMapperError` for easy catching.

```python
from src.file_mapper import (
    FileMapperError,
    FilesystemError,
    ConfigError,
    FrontmatterError,
    PageLimitExceededError
)

try:
    mapper.sync_spaces(config)
except PageLimitExceededError as e:
    print(f"Too many pages: {e.current_count} exceeds limit of {e.limit}")
except ConfigError as e:
    print(f"Invalid config: {e.original_message}")
except FilesystemError as e:
    print(f"File operation failed: {e.operation} on {e.file_path}")
except FrontmatterError as e:
    print(f"Frontmatter error in {e.file_path}: {e.message}")
except FileMapperError as e:
    print(f"File mapper error: {e}")
```

### Error Types

| Exception | When Raised | Attributes |
|-----------|-------------|------------|
| `FilesystemError` | File read/write/permission errors | `file_path`, `operation`, `reason` |
| `ConfigError` | Invalid configuration | `config_field`, `original_message` |
| `FrontmatterError` | Malformed YAML frontmatter | `file_path`, `message` |
| `PageLimitExceededError` | Page count exceeds limit | `current_count`, `limit` |

## Hierarchical Folder Structure

The library mirrors Confluence page hierarchies as nested folders.

### Structure Example

**Confluence Hierarchy:**
```
Team Space (parent_page_id: 123456)
├── Getting Started
│   ├── Installation
│   └── Quick Start
├── User Guide
│   ├── Basic Features
│   └── Advanced Features
└── API Reference
    ├── Authentication
    └── Endpoints
```

**Local File Structure:**
```
team-space/
├── Getting-Started.md
├── Getting-Started/
│   ├── Installation.md
│   └── Quick-Start.md
├── User-Guide.md
├── User-Guide/
│   ├── Basic-Features.md
│   └── Advanced-Features.md
├── API-Reference.md
└── API-Reference/
    ├── Authentication.md
    └── Endpoints.md
```

### Rules

1. **Parent Page as File**: The parent page itself becomes a markdown file
2. **Parent Page as Directory**: If the parent has children, a directory with the same name is created
3. **Child Pages as Files**: Child pages become markdown files inside the parent directory
4. **Recursive Nesting**: This pattern repeats recursively for all levels

## Sync Behavior

### Initial Sync Direction (ADR-014)

The library automatically detects which side to sync from:

| Local State | Confluence State | Action |
|-------------|------------------|--------|
| Empty | Has pages | Pull from Confluence |
| Has files | Empty | Push to Confluence |
| Has files | Has pages | **Error** (unless `force_pull` or `force_push` set) |

**Example:**

```python
# First sync (local is empty) - automatically pulls from Confluence
mapper.sync_spaces(config)

# If both sides have content, you must force:
config.force_pull = True  # Overwrite local with Confluence
# OR
config.force_push = True  # Overwrite Confluence with local
mapper.sync_spaces(config)
```

**Warning**: Force flags will overwrite changes without warning. Use with caution.

### Bidirectional Sync

After initial sync, the library syncs changes in both directions:

- **Local changes**: Pushed to Confluence
- **Confluence changes**: Pulled to local
- **Title changes**: Local files are renamed to match

### Page Exclusion (ADR-015)

Exclude specific pages and their descendants from sync:

```yaml
spaces:
  - space_key: "TEAM"
    parent_page_id: "123456"
    local_path: "./team-space"
    exclude_page_ids:
      - "789012"  # Archives page
      - "345678"  # Old Documentation
```

**Behavior:**
- Excluded pages are not synced to local files
- All descendants of excluded pages are also excluded
- Existing local files for excluded pages are **not** deleted (manual cleanup required)

## Atomic File Operations (ADR-011)

The library uses a two-phase commit pattern to ensure atomic writes:

### Two-Phase Commit

1. **Phase 1 - Staging**: Write all files to temporary directory
2. **Phase 2 - Commit**: Move files from temp to final location

**Guarantees:**
- All-or-nothing: Either all files are written or none are
- No partial state: If any write fails, the entire operation is rolled back
- Clean rollback: Temporary files are cleaned up on failure

```python
# If any file write fails, ALL changes are rolled back
try:
    mapper.sync_spaces(config)
except FilesystemError as e:
    print(f"Sync failed, no files were modified: {e}")
```

### Temporary Directory

Files are staged in `.confluence-sync/temp/` by default:

```
.confluence-sync/
├── config.yaml
└── temp/           # Staging area for atomic writes
    ├── stage-1/    # Temporary files during sync
    └── stage-2/    # Moved here before final commit
```

## Page Limits (ADR-013)

The MVP enforces a 100 page limit per hierarchy level:

```yaml
# config.yaml
page_limit: 100  # Maximum pages per level
```

**Behavior:**
- If a parent page has >100 children, sync fails with `PageLimitExceededError`
- Error message suggests splitting the hierarchy
- Future epic will add pagination support

**Example:**

```python
try:
    mapper.sync_spaces(config)
except PageLimitExceededError as e:
    print(f"Page limit exceeded: {e.current_count} pages, limit is {e.limit}")
    print("Consider splitting your hierarchy or increasing the limit")
```

## Testing

The library has comprehensive test coverage (>90% for all modules):

### Unit Tests

```bash
# Run all unit tests
pytest tests/unit/file_mapper/ -v

# Run with coverage
pytest tests/unit/file_mapper/ --cov=src/file_mapper --cov-report=html

# Run specific component tests
pytest tests/unit/file_mapper/test_filesafe_converter.py -v
pytest tests/unit/file_mapper/test_frontmatter_handler.py -v
pytest tests/unit/file_mapper/test_config_loader.py -v
```

### Integration Tests

```bash
# Run integration tests (requires Confluence credentials)
pytest tests/integration/ -m integration -v

# Test CQL queries
pytest tests/integration/test_cql_queries.py -v

# Test file operations
pytest tests/integration/test_file_operations.py -v
```

### End-to-End Tests

```bash
# Run E2E tests (requires CONFSYNCTEST space access)
pytest tests/e2e/file_mapper/ -m e2e -v

# Test specific scenarios
pytest tests/e2e/file_mapper/test_full_pull_sync.py -v
pytest tests/e2e/file_mapper/test_full_push_sync.py -v
pytest tests/e2e/file_mapper/test_bidirectional_sync.py -v
```

### Test Environment Setup

Create `.env.test` with Confluence credentials:

```bash
CONFLUENCE_URL=https://your-domain.atlassian.net
CONFLUENCE_USER=your-email@example.com
CONFLUENCE_API_TOKEN=your-api-token
```

## Architecture Decision Records (ADRs)

The library implements the following ADRs:

| ADR | Decision | Implementation |
|-----|----------|----------------|
| **ADR-008** | CQL-Based Page Discovery | `HierarchyBuilder` uses CQL queries |
| **ADR-009** | YAML Frontmatter Format | `FrontmatterHandler` enforces format |
| **ADR-010** | Filesafe Conversion with Case Preservation | `FilesafeConverter` preserves case |
| **ADR-011** | Atomic File Operations | Two-phase commit in `FileMapper` |
| **ADR-012** | Parent PageID as Configuration Anchor | `SpaceConfig.parent_page_id` |
| **ADR-013** | 100 Page Limit per Level (MVP) | Enforced by `HierarchyBuilder` |
| **ADR-014** | Strict Initial Sync Requirement | Enforced by `FileMapper._detect_sync_direction()` |
| **ADR-015** | Exclusion by PageID Only (MVP) | `SpaceConfig.exclude_page_ids` |

Full ADR documentation: `docs/epics/conf-sync-002-file-structure-mapping/adr.md`

## Limitations (MVP)

The following features are planned for future epics:

- **Pagination**: >100 pages per level (Epic 005)
- **Regex-based exclusion**: Pattern-based page filtering (Epic 005)
- **Conflict resolution**: Merge logic for simultaneous edits
- **CLI interface**: Command-line tool for end users (Epic 004)
- **Git integration**: Automatic commits on sync (Epic 003)

## API Reference

For detailed API documentation, see the docstrings in each module:

- `file_mapper.py`: Main orchestration class
- `hierarchy_builder.py`: CQL queries and tree building
- `filesafe_converter.py`: Title-to-filename conversion
- `frontmatter_handler.py`: YAML frontmatter operations
- `config_loader.py`: Configuration management
- `models.py`: Data models
- `errors.py`: Exception types

## Contributing

### Development Setup

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Set up test environment
cp .env.example .env.test
# Edit .env.test with test credentials
```

### Running Tests

```bash
# Run all tests with coverage
pytest tests/ --cov=src/file_mapper --cov-report=html

# Run specific test types
pytest tests/unit/ -v
pytest tests/integration/ -m integration -v
pytest tests/e2e/ -m e2e -v
```

### Code Quality

- Follow existing code patterns (see `patterns_from` in spec)
- Maintain >90% unit test coverage
- Include comprehensive docstrings
- Type all function parameters and returns
- Use dataclasses for data models
- Inherit all exceptions from `FileMapperError`

## License

See repository license file.

## Support

For questions or issues:

1. Check the [Configuration Example](../../config/example.yaml)
2. Review [Architecture Documentation](../../docs/epics/conf-sync-002-file-structure-mapping/architecture.md)
3. Check [Acceptance Criteria](../../docs/epics/conf-sync-002-file-structure-mapping/acceptance-criteria.md)
4. Review [Test Strategy](../../docs/epics/conf-sync-002-file-structure-mapping/test-strategy.md)
