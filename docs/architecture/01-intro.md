# Architecture - Introduction & Goals

---

## Requirements Overview

**confluence-bidir-sync** is a Python library that enables bidirectional synchronization between Confluence Cloud pages and local markdown files. It allows both human users and agentic AI teams to work with documentation in their preferred format while preserving Confluence's rich features.

### Top 5 Requirements

1. **Bidirectional Content Sync**: Fetch Confluence pages as markdown, push markdown changes back to Confluence
2. **Macro Preservation**: Preserve Confluence-specific macros (`ac:` namespace) during round-trip conversion
3. **Surgical Updates**: Modify only changed content, never touching macros or formatting
4. **Version Conflict Detection**: Detect concurrent edits via optimistic locking, fail-fast on conflicts
5. **Clear Error Handling**: Typed exceptions with actionable messages for debugging

## Quality Goals

| Priority | Quality Goal | Description |
|----------|--------------|-------------|
| 1 | **Reliability** | Never corrupt Confluence content; preserve macros, labels, local-ids through all operations |
| 2 | **Maintainability** | Clean architecture enabling easy extension for future epics (file mapping, git integration, CLI) |
| 3 | **Usability** | Clear API for both human developers and agentic AI tools; readable markdown output |
| 4 | **Security** | Credential protection (no logging), secure subprocess handling (no shell injection) |

## Stakeholders

| Role | Expectations |
|------|--------------|
| **Human Users** | Edit Confluence docs locally with familiar tools (VS Code, vim); preserve formatting on sync |
| **Agentic AI Teams** | CRUD documentation via markdown; use RAG tools on local files; programmatic page manipulation |
| **Developers/Contributors** | Clean codebase with type hints, docstrings, and >80% test coverage |
| **Future CLI Users** | (Epic 04+) Command-line sync operations with dry-run and conflict resolution |

---
