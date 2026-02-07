# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-02-07

### Added
- Initial release of Confluence Bidirectional Sync
- Bidirectional synchronization between Confluence Cloud pages and local Markdown files
- Intelligent 3-way merge conflict detection using baseline snapshots
- Surgical page updates preserving Confluence macros, labels, and comments
- Page exclusion by Confluence URL or local file path (with glob pattern support)
- Single-file sync mode for updating individual files without affecting global state
- CQL-based page hierarchy discovery for efficient space synchronization
- Cell-level table merge for granular conflict detection in tables
- Multi-line content preservation in table cells
- File size limits (10MB) to prevent memory exhaustion
- Recursion depth limits (50 levels) to prevent stack overflow
- URL validation for security
- Credential sanitization in error messages
- Version conflict retry with exponential backoff
- Optimistic locking for concurrent update safety
- CLI with dry-run, force-push, and force-pull modes
- Timestamped file logging with local timezone support
- Minimal frontmatter format (confluence_url only)
- Comprehensive test suite (159 tests, 87% coverage)

### Security
- Path traversal protection with validation
- Page ID validation to prevent injection attacks
- Temporary directory cleanup with try-finally wrappers
- Baseline file locking to prevent race conditions
- YAML depth validation to prevent DoS attacks
- Git command sanitization
- API timeout configuration (30s default)
- Parser security (html.parser instead of lxml for user content)
- Explicit null handling consistency

[Unreleased]: https://github.com/PatD42/confluence-bidir-sync/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/PatD42/confluence-bidir-sync/releases/tag/v0.1.0
