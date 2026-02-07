---
status: ready-for-refinement
epic_id: CONF-SYNC-007
title: Comprehensive Test Coverage
phase: Quality
dependencies:
  - CONF-SYNC-001
  - CONF-SYNC-002
  - CONF-SYNC-003
  - CONF-SYNC-004
  - CONF-SYNC-005
blocks: []
created_date: 2026-02-03
---

# Epic: CONF-SYNC-007 - Comprehensive Test Coverage

---

## Overview

This epic addresses critical gaps in test coverage identified during Epic 005 (Extended Features) implementation. The gaps span unit, integration, and E2E tests for newly implemented features including ADF surgical updates, line break format conversion, table-aware 3-way merge, and conflict resolution.

**Problem Statement**:
Recent feature development (ADF surgical updates, `<br>`/hardBreak conversion, cell-level table merge) has unit test coverage but lacks integration and E2E validation. This creates risk that components work in isolation but fail when integrated or used against real Confluence instances.

**Goals**:
- Achieve 90%+ test coverage for new features
- Validate full sync cycle for critical edge cases
- Ensure error recovery paths are tested
- Build confidence for production use

---

## Scope

### In Scope

| Category | Test Type | Priority | Description |
|----------|-----------|----------|-------------|
| ADF Surgical Updates | E2E | P0 | Verify ADF path used for edits with real Confluence |
| ADF Surgical Updates | Integration | P0 | ADF editor + PageOperations integration |
| Line Break Conversion | E2E | P0 | Full `<p>` → `<br>` → `<p>` round-trip |
| Line Break Conversion | Integration | P1 | MarkdownConverter + sync workflow |
| Conflict Resolution | E2E | P1 | Conflict markers written for same-cell edits |
| Conflict Resolution | Integration | P1 | ConflictResolver + TableMerge integration |
| Macro Preservation | E2E | P1 | Macros survive full sync cycle |
| Version Conflict | Integration | P1 | Handle stale version during push |
| Fallback Paths | E2E | P2 | ADF failure triggers full replacement |
| Fallback Paths | Integration | P2 | Error recovery integration |

### Out of Scope

- Performance/load testing
- Security testing
- UI/UX testing (CLI is text-based)
- Backwards compatibility testing with older Confluence versions

---

## Test Gap Analysis

### Unit Tests - Status: ADDRESSED

Recent additions (40 tests) cover:
- `_text_to_adf_nodes()` - `<br>` to hardBreak conversion
- `_replace_node_text()` - Replacing existing hardBreak content
- `_convert_br_to_p_in_cells()` - Push direction conversion
- Table separator handling
- Embedded newlines in cells

### Integration Tests - Status: GAPS IDENTIFIED

| Gap | Component | Risk |
|-----|-----------|------|
| ConflictResolver + TableMerge | CLI workflow | High - Cell-level merge untested at integration |
| ADF vs XHTML path selection | PageOperations | High - Format selection logic untested |
| Version conflict recovery | SyncCommand | Medium - Race condition handling |
| Baseline + 3-way merge | SyncCommand + BaselineManager | Medium - Actual merge operation untested |

### E2E Tests - Status: CRITICAL GAPS

| Gap | Feature | Risk |
|-----|---------|------|
| ADF surgical updates | Real Confluence | Critical - Core feature path untested |
| Line break round-trip | Full sync cycle | Critical - Data integrity risk |
| Conflict marker output | User workflow | High - User-facing behavior untested |
| Macro preservation | Full sync cycle | High - Data loss risk |
| ADF fallback | Error recovery | Medium - Degraded mode untested |

---

## Stories

### Story 1: ADF Surgical Update E2E Tests
**Points**: 5

Validate that edits to synced pages use the ADF surgical update path with proper `hardBreak` node conversion.

**Tests to create**:
1. Edit text in synced page → verify ADF API called (not XHTML storage)
2. Edit text with `<br>` tags → verify `hardBreak` nodes in Confluence ADF
3. Edit table cell → verify TABLE_UPDATE_CELL operation via ADF
4. Multiple edits → verify all apply surgically

### Story 2: Line Break Format Conversion E2E Tests
**Points**: 3

Validate the full round-trip of line break conversion through sync cycles.

**Tests to create**:
1. Pull page with `<p>` tags in table cells → verify `<br>` in local markdown
2. Push page with `<br>` in cells → verify `<p>` tags in Confluence
3. Bidirectional edit with line breaks → verify preservation
4. Multiple `<br>` in same cell → verify all preserved

### Story 3: Conflict Resolution E2E Tests
**Points**: 5

Validate conflict detection and marker output for real edit conflicts.

**Tests to create**:
1. Same cell edited both sides → verify `<<<<<<< local` markers in file
2. Same row, different cells → verify auto-merge (no conflict)
3. Same paragraph edited both sides → verify conflict markers
4. Resolve conflict manually → verify next sync succeeds

### Story 4: Macro Preservation E2E Tests
**Points**: 3

Validate that Confluence macros survive the full sync cycle.

**Tests to create**:
1. Page with TOC macro → pull/edit/push → verify macro intact
2. Page with code macro → edit nearby content → verify macro preserved
3. Page with inline macro → edit same paragraph → verify macro preserved

### Story 5: ConflictResolver Integration Tests
**Points**: 3

Validate ConflictResolver + TableMerge integration in CLI workflow.

**Tests to create**:
1. Cell-level merge via ConflictResolver → verify TableMerge called
2. Non-table content merge → verify standard merge3 used
3. Mixed content (tables + text) → verify correct handler per section

### Story 6: ADF Path Selection Integration Tests
**Points**: 3

Validate ADF vs XHTML format selection in PageOperations.

**Tests to create**:
1. Page with ADF support → verify ADF path chosen
2. Surgical update requested → verify ADF API used
3. ADF failure → verify fallback to XHTML

### Story 7: Version Conflict Integration Tests
**Points**: 3

Validate version conflict handling during bidirectional sync.

**Tests to create**:
1. Version changes between detect and push → verify VersionConflictError
2. Version conflict → verify retry with fresh version
3. Persistent conflict → verify error reported to user

### Story 8: ADF Fallback E2E Tests
**Points**: 3

Validate graceful fallback when ADF surgical updates fail.

**Tests to create**:
1. >50% operations fail → verify fallback to full replacement
2. ADF API error → verify XHTML fallback attempted
3. Fallback succeeds → verify content correct in Confluence

### Story 9: Baseline Manager Integration Tests
**Points**: 2

Validate baseline usage in actual merge operations.

**Tests to create**:
1. Baseline exists → verify used in 3-way merge
2. Baseline missing → verify fallback behavior
3. Baseline stale → verify refresh logic

### Story 10: Error Recovery Integration Tests
**Points**: 2

Validate error recovery paths in integration scenarios.

**Tests to create**:
1. Network error during sync → verify retry with backoff
2. Partial sync failure → verify successful pages committed
3. merge3 failure → verify conflict markers written

---

## Technical Notes

### Test Infrastructure

**E2E Test Requirements**:
- Real Confluence test space (CONFSYNCTEST)
- Test credentials in `.env.test`
- Page cleanup fixtures
- ADF API access

**Integration Test Requirements**:
- Mocked Confluence API (no external calls)
- Real filesystem operations
- Temporary directories

### Key Test Patterns

```python
# E2E: Verify ADF surgical update
def test_edit_uses_adf_surgical_path(synced_page, api_wrapper):
    # 1. Get initial ADF
    initial_adf = api_wrapper.get_page_adf(page_id)

    # 2. Edit local file with <br>
    modify_local_file(file_path, add_br_tag=True)

    # 3. Sync
    sync_cmd.run()

    # 4. Get final ADF
    final_adf = api_wrapper.get_page_adf(page_id)

    # 5. Verify hardBreak nodes present
    assert has_hardbreak_nodes(final_adf)
```

```python
# Integration: Verify ConflictResolver + TableMerge
def test_cell_level_merge_integration(baseline, local, remote):
    resolver = ConflictResolver(baseline_manager)

    # Different cells in same row
    result = resolver.resolve(page_id, local, remote)

    assert not result.has_conflicts
    assert "cell_A_change" in result.merged
    assert "cell_B_change" in result.merged
```

---

## Acceptance Criteria Summary

See `acceptance-criteria.md` for detailed Given/When/Then scenarios.

**Minimum for Epic Completion**:
- All P0 tests passing
- All P1 tests passing
- 90%+ coverage on new features
- No regressions in existing tests

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Flaky E2E tests | CI instability | Retry logic, isolated test spaces |
| Confluence API rate limits | Test timeouts | Exponential backoff, test batching |
| Test data cleanup failures | Orphaned pages | Dedicated cleanup fixtures, manual cleanup script |

---

## Definition of Done

- [ ] All stories implemented
- [ ] All tests passing in CI
- [ ] Test coverage report generated
- [ ] Documentation updated with test matrix
- [ ] No P0/P1 test gaps remaining
