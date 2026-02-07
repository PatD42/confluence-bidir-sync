# Architecture Decision Records (ADR)

## confluence-bidir-sync

This directory contains Architecture Decision Records documenting key technical decisions made during the development of the confluence-bidir-sync library.

---

## Index

| ADR | Title | Status | Summary |
|-----|-------|--------|---------|
| [ADR-001](./ADR-001-typed-exceptions.md) | Typed Exception Hierarchy | Accepted | Domain exceptions with rich context |
| [ADR-002](./ADR-002-lazy-client-loading.md) | Lazy Client Loading | Accepted | Delay Confluence client initialization |
| [ADR-003](./ADR-003-lxml-parser.md) | lxml Parser | Accepted | Use lxml for XHTML namespace support |
| [ADR-004](./ADR-004-pandoc-subprocess.md) | Pandoc Subprocess | Accepted | Use Pandoc CLI for markdown conversion |
| [ADR-005](./ADR-005-rate-limit-retry.md) | Rate Limit Retry | Accepted | Retry only on 429, fail-fast for others |
| [ADR-006](./ADR-006-macro-preservation.md) | Macro Preservation | Accepted | Preserve ac: macros as HTML comments |
| [ADR-007](./ADR-007-version-locking.md) | Version Locking | Accepted | Optimistic locking with fail-fast |

---

## ADR Format

Each ADR follows this template:

```markdown
# ADR-XXX: Title

## Status
Accepted | Proposed | Deprecated | Superseded

## Context
What is the issue that we're seeing that is motivating this decision?

## Decision
What is the change that we're proposing and/or doing?

## Consequences
What becomes easier or more difficult as a result of this decision?
```

---

## Decision Categories

### API Design
- [ADR-001](./ADR-001-typed-exceptions.md) - Error handling strategy

### Performance
- [ADR-002](./ADR-002-lazy-client-loading.md) - Initialization timing
- [ADR-005](./ADR-005-rate-limit-retry.md) - Retry behavior

### Content Processing
- [ADR-003](./ADR-003-lxml-parser.md) - HTML/XML parsing
- [ADR-004](./ADR-004-pandoc-subprocess.md) - Format conversion
- [ADR-006](./ADR-006-macro-preservation.md) - Macro handling

### Data Integrity
- [ADR-007](./ADR-007-version-locking.md) - Concurrent modification handling

---

## Adding New ADRs

When making a significant architectural decision:

1. Create a new file: `ADR-XXX-short-name.md`
2. Use the next available number
3. Follow the template above
4. Update this README index
5. Link to relevant code in the "References" section

---

## References

- [ADR GitHub Organization](https://adr.github.io/)
- [Michael Nygard's ADR Article](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
