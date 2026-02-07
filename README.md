# Confluence Bidirectional Sync

A Python CLI tool for bidirectional synchronization between Confluence pages and local Markdown files.

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-alpha-orange)

## Features

- **Keeps Confluence Macros, Labels and Comments**: Updated Confluence pages keep their rich metadata.
- **Bidirectional Sync**: Keep Confluence pages and local Markdown files in sync
- **Conflict Detection**: Intelligent 3-way merge conflict detection
- **Page Exclusions**: Exclude pages by Confluence URL or local file path (CLI or config)
- **Single-File Sync**: Sync individual files without affecting others
- **File Logging**: Optional timestamped log files with local timezone
- **CQL-Based Discovery**: Efficient page hierarchy discovery using single CQL query
- **Minimal Frontmatter**: Clean markdown files with only `page_id` in frontmatter

## Requirements

- Python 3.10+
- Confluence Cloud instance
- API token for authentication

## Installation

### For Users

Once published to PyPI, install via pip:

```bash
pip install confluence-bidir-sync
```

### For Development

Clone the repository and install in editable mode:

```bash
git clone https://github.com/PatD42/confluence-bidir-sync.git
cd confluence-bidir-sync
pip install -e ".[dev]"
```

This creates the `confluence-sync` command in your environment and installs all development dependencies.

## Configuration

### Environment Variables

Create a `.env` file or set the following environment variables:

```bash
CONFLUENCE_URL=https://your-instance.atlassian.net
CONFLUENCE_USER=your-email@example.com
CONFLUENCE_API_TOKEN=your-api-token
```

### Initialize Configuration

Initialize a sync configuration for a Confluence space:

```bash
confluence-sync --init --local ./docs --url https://company.atlassian.net/wiki/spaces/TEAM/pages/123456
```

**With parent page exclusion** (sync only children, not the parent page):
```bash
confluence-sync --init --local ./docs --url https://company.atlassian.net/wiki/spaces/TEAM/pages/123456 --excludeParent
```

This creates a `.confluence-sync/` directory with:
- `config.yaml` - Sync configuration
- `state.yaml` - Sync state tracking
- `baseline/` - Baseline snapshots for conflict detection

## Usage

### Basic Sync

Run bidirectional sync (default behavior):

```bash
confluence-sync
```

### Command-Line Options

| Option | Description |
|--------|-------------|
| `--init` | Initialize sync configuration (requires `--local`, `--url` and optionally `--excludeParent`) |
| `--local FOLDER` | (used with `--init`) Local folder path for synced files  |
| `--url URL` | (used with `--init`) Confluence page URL  |
| `--excludeParent` | (used with `--init`) Exclude parent page from sync (only sync children) |
| `--dry-run` | Preview changes without applying them |
| `--force-push` | Force push local changes to Confluence (local → Confluence) |
| `--force-pull` | Force pull Confluence changes to local (Confluence → local) |
| `--exclude-confluence URL` | Exclude Confluence page by URL (can be repeated) |
| `--exclude-local PATH` | Exclude local file by path (can be repeated) |
| `--logdir DIR` | Write logs to timestamped files in directory |
| `-v, --verbosity LEVEL` | Set verbosity level (0=summary, 1=info, 2=debug) |
| `-V, --version` | Show version and exit |
| `--no-color` | Disable colored output |
| `FILE` | Optional file path to sync (positional argument, syncs only this file) |

### Single-File Sync

Sync a specific file without updating the global sync timestamp:

```bash
confluence-sync path/to/file.md
```

This updates only the specified file and its baseline, leaving other files and the global sync state unchanged.

### Excluding Pages from Sync

You can exclude specific pages from sync using command-line options. Exclusions are **permanent** - they're saved to `.confluence-sync/config.yaml` and persist across all future sync operations.

**Exclude by Confluence URL:**
```bash
confluence-sync --exclude-confluence https://company.atlassian.net/wiki/spaces/TEAM/pages/123456
```

**Exclude by local file path:**
```bash
confluence-sync --exclude-local ./docs/Archive.md
```

**Wildcard support** - Use glob patterns to exclude multiple files at once. This is evaluated when the command is given, not at every sync:
```bash
# Exclude all files matching pattern
confluence-sync --exclude-local ./docs/Archive*

# Exclude files in subdirectories (recursive)
confluence-sync --exclude-local ./docs/**/Archive-*.md
```

**Multiple exclusions (mix both types):**
```bash
confluence-sync \
  --exclude-confluence https://company.atlassian.net/wiki/spaces/TEAM/pages/123456 \
  --exclude-confluence https://company.atlassian.net/wiki/spaces/TEAM/pages/789012 \
  --exclude-local ./docs/Old*.md
```

**Behavior:**
- **Permanent**: CLI exclusions are saved to `.confluence-sync/config.yaml`
- **Processed first**: Exclusions are applied before sync operations run
- **Not deleted**: Excluded pages remain on both sides, just ignored during sync
- **All sync modes**: Works with `--force-push`, `--force-pull`, and bidirectional sync
- **Wildcards expanded once**: Glob patterns are expanded when exclusion is added
- **Merged with existing**: New exclusions are added to existing `exclude_page_ids` in config

## Frontmatter Format

Synced files use minimal YAML frontmatter containing the Confluence URL:

```markdown
---
confluence_url: https://company.atlassian.net/wiki/spaces/TEAM/pages/123456789
---

# Page Title

Your content here...
```

The `confluence_url` format allows extracting both the space key and page ID, making files self-contained.

## Title Resolution

For existing pages, titles come from Confluence. For new pages:

1. **H1 Heading**: Extracted from first `# Heading` in the file
2. **Filename**: Falls back to filename (without `.md` extension) if no H1 exists

## Directory Structure

```
your-project/
├── .confluence-sync/
│   ├── config.yaml          # Sync configuration
│   ├── state.yaml           # Last sync timestamp
│   └── baseline/            # Baseline snapshots
├── page1.md                 # Synced pages
├── subdir/
│   └── page2.md
└── ...
```

## Troubleshooting

### Command Not Found

If `confluence-sync` is not found after installation:

**For development install:**
```bash
pip install -e .
```

**For user install:**
```bash
pip install confluence-bidir-sync
```

### Permission Errors

Ensure your API token has read/write permissions for the target Confluence space.

### Conflict Detection

The tool uses 3-way merge to detect conflicts:
- **Local changes only**: Pushed to Confluence
- **Remote changes only**: Pulled to local
- **Both changed**: Flagged as conflict for manual resolution

## Development

### Running Tests

The test suite has three levels:

**Quick Tests (default, ~20 seconds):**
```bash
pytest                    # Unit + Integration (skips E2E)
pytest tests/unit/        # Unit tests only (fastest)
```

**Integration Tests (~1 minute):**
```bash
pytest tests/integration/ -v  # Filesystem integration, no API calls
```

**Full E2E Tests (~5-10 minutes):**
```bash
pytest -m e2e            # All E2E tests (hits real Confluence API)
pytest tests/e2e/ -v     # Explicit E2E directory
```

**All Tests:**
```bash
pytest tests/ -m ""      # Override default filter, run everything
```

> **Note:** E2E tests are skipped by default because they require Confluence API settling time (eventual consistency). They create/modify/delete real pages in the CONFSYNCTEST space.

### Test Environment

Tests use the `CONFSYNCTEST` space in Confluence. Set the test environment variables:

```bash
CONFLUENCE_TEST_SPACE=CONFSYNCTEST
```

## License

This project is licensed under the MIT License - see below for details:

```
MIT License

Copyright (c) 2026 Patrick Drolet

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Contributing

Contributions are welcome! Please follow these guidelines:

### Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/PatD42/confluence-bidir-sync.git`
3. Install development dependencies: `pip install -e ".[dev]"`
4. Create a feature branch: `git checkout -b feature/your-feature`

### Essential Reading

- **[CLAUDE.md](CLAUDE.md)** - Deep technical context including:
  - Critical architectural decisions (ADRs)
  - Confluence API nuances and gotchas
  - Testing strategy and conventions
  - Domain-specific knowledge
  - Security requirements
  - Common pitfalls to avoid

### Development Guidelines

- **Code Style**: Follow PEP 8 guidelines
- **Type Hints**: Add type hints to all function signatures
- **Testing**: Add tests for new functionality (aim for 90%+ coverage)
- **Documentation**: Update docstrings and README as needed

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run specific test types
pytest tests/unit/ -v           # Unit tests only
pytest tests/integration/ -v    # Integration tests only
```

### Submitting Changes

1. Ensure all tests pass
2. Update documentation if needed
3. Commit with clear, descriptive messages
4. Push to your fork and submit a pull request
5. Describe your changes in the PR description

### Reporting Issues

When reporting issues, please include:
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant log output

### Code of Conduct

Be respectful and inclusive. We welcome contributors of all backgrounds and experience levels.
