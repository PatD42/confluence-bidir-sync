# Epic: CONF-SYNC-002 - File Structure & Mapping

---

## Overview

Local file system representation of Confluence spaces and pages. This epic establishes the bidirectional mapping between Confluence page hierarchy and local markdown files with YAML frontmatter.

**Customer Problems Addressed**:
- Users need local copies of Confluence pages for offline access
- Agentic teams need markdown files for RAG tools and local processing
- Developers want to use familiar editors (VS Code, vim) instead of browser

---

## Capabilities

| ID | Capability | Priority |
|----|------------|----------|
| FR-2.1 | Map Confluence space to local directory structure | High |
| FR-2.2 | Preserve page hierarchy as nested folders | High |
| FR-2.3 | Generate markdown files with YAML frontmatter | High |
| FR-2.4 | Create mapping file (JSON) tracking page IDs to file paths | High |
| FR-2.5 | Handle page title changes (rename local files) | Medium |

---

## Acceptance Criteria (High-Level)

- [ ] Given a Confluence space, the tool creates a local directory structure mirroring page hierarchy
- [ ] Given a Confluence page, a markdown file is created with YAML frontmatter containing page-id
- [ ] Given a mapping file exists, page IDs can be resolved to local file paths and vice versa
- [ ] Given a page title change in Confluence, the local file is renamed accordingly
- [ ] Given a local file rename, the mapping file is updated (page-id in frontmatter is source of truth)

---

## Dependencies

**Depends on**:
- CONF-SYNC-001: Confluence API Integration & Surgical Updates
  - Requires `PageOperations.get_page_snapshot()` to fetch page content
  - Requires `MarkdownConverter` for XHTML→Markdown conversion
  - Requires `APIWrapper.get_child_pages()` for hierarchy traversal

**Blocks**:
- CONF-SYNC-003: Git Integration (needs local files to merge)
- CONF-SYNC-004: CLI & Sync Orchestration (needs file mapper for sync operations)

---

## Release Phase

⭐ **MVP**

This is foundational for bidirectional sync. Without local file representation, no sync operations are possible.

---

## Proposed Structure

```
my-project/
  .confluence-sync/
    config.yaml           # Space configuration
    mapping.json          # Page ID ↔ file path mapping
  engineering/
    index.md              # Space home page (frontmatter: page_id: 12345)
    getting-started/
      index.md            # Section parent page
      installation.md     # Child page
      configuration.md    # Child page
    api-reference/
      index.md
      endpoints.md
```

**Frontmatter Format**:
```yaml
---
page_id: "12345"
space_key: "TEAM"
title: "Installation Guide"
last_synced: "2026-01-30T10:00:00Z"
confluence_version: 15
---

# Installation Guide

Content here...
```

---

## Technical Considerations

1. **Filesafe naming**: Page titles must be converted to valid filenames
   - Replace spaces with hyphens
   - Remove/encode special characters
   - Handle duplicate names in same folder

2. **Hierarchy depth**: Confluence can have deep hierarchies
   - Support configurable max depth
   - Handle circular references (shouldn't exist, but defensive)

3. **Mapping file format**: JSON for easy parsing
   - Bidirectional lookup (page_id → path, path → page_id)
   - Store last-known title for change detection

---

## Next Steps

After this epic is created in tracking system, run:
```
/workplan conf-sync-002
```
to refine into stories and architecture.
