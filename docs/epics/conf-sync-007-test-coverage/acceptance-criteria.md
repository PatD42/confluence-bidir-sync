# Acceptance Criteria - CONF-SYNC-007: Comprehensive Test Coverage

---

## AC-1: ADF Surgical Update E2E Tests

### AC-1.1: Edit Uses ADF Path

**Given** a page synced to local with ADF support
**When** I edit the markdown file and run sync
**Then** the sync should use the ADF API (not XHTML storage)
**And** the page version should increment by 1

### AC-1.2: BR Tags Convert to HardBreak Nodes

**Given** a synced markdown file
**When** I add `<br>` tags to a paragraph and sync
**Then** the Confluence ADF should contain `hardBreak` nodes
**And** NOT contain literal `<br>` text

### AC-1.3: Table Cell Update via ADF

**Given** a page with a table synced locally
**When** I edit a single cell and sync
**Then** the sync should generate a TABLE_UPDATE_CELL operation
**And** apply it via ADF surgical update

### AC-1.4: Multiple Edits Apply Surgically

**Given** a synced page with paragraphs and tables
**When** I make edits to 3 different locations and sync
**Then** all 3 operations should apply successfully
**And** macro count should remain unchanged

---

## AC-2: Line Break Format Conversion E2E Tests

### AC-2.1: Pull Converts P Tags to BR

**Given** a Confluence page with table cells containing multiple `<p>` tags
**When** I pull the page to local
**Then** the markdown should have `<br>` tags between lines in cells
**And** NOT have `<p>` tags in the markdown

### AC-2.2: Push Converts BR to P Tags

**Given** a local markdown file with `<br>` tags in table cells
**When** I push to Confluence
**Then** the Confluence storage should have `<p>` tags (XHTML) OR `hardBreak` nodes (ADF)
**And** NOT have `<br>` tags in storage format

### AC-2.3: Bidirectional Edit Preserves Line Breaks

**Given** a page with multi-line table cells synced both directions
**When** Confluence adds a line AND local adds a different line
**Then** both lines should be preserved after merge
**And** all `<br>` tags should be present

### AC-2.4: Multiple BR in Same Cell Preserved

**Given** a table cell with 4+ lines (3+ `<br>` tags)
**When** I edit one line and sync
**Then** all other lines should be preserved
**And** all `<br>` tags should remain intact

---

## AC-3: Conflict Resolution E2E Tests

### AC-3.1: Same Cell Conflict Shows Markers

**Given** a table cell edited on both Confluence and local
**When** I run bidirectional sync
**Then** the local file should contain `<<<<<<< local` markers
**And** contain `>>>>>>> remote` markers
**And** exit code should indicate conflict

### AC-3.2: Same Row Different Cells Auto-Merge

**Given** a table row where Confluence edits cell A and local edits cell B
**When** I run bidirectional sync
**Then** both changes should merge automatically
**And** NO conflict markers should be present
**And** Confluence should have both changes

### AC-3.3: Same Paragraph Conflict Shows Markers

**Given** the same paragraph edited on both sides
**When** I run bidirectional sync
**Then** the local file should contain conflict markers
**And** both versions should be visible for manual resolution

### AC-3.4: Resolved Conflict Syncs Successfully

**Given** a file with conflict markers from previous sync
**When** I manually resolve conflicts (remove markers, keep desired content)
**And** run sync again
**Then** the sync should succeed without errors
**And** Confluence should reflect resolved content

---

## AC-4: Macro Preservation E2E Tests

### AC-4.1: TOC Macro Survives Sync Cycle

**Given** a Confluence page with a `{toc}` macro
**When** I pull → edit nearby content → push
**Then** the TOC macro should still be present in Confluence
**And** macro functionality should work

### AC-4.2: Code Macro Preserved During Edit

**Given** a page with a `{code}` macro containing code
**When** I edit text above or below the macro and sync
**Then** the code macro should be unchanged
**And** code content should be preserved exactly

### AC-4.3: Inline Macro in Paragraph Preserved

**Given** a paragraph containing an inline macro (e.g., `{status}`)
**When** I edit other words in the same paragraph and sync
**Then** the inline macro should remain intact
**And** macro rendering should work correctly

---

## AC-5: ConflictResolver Integration Tests

### AC-5.1: Cell-Level Merge Uses TableMerge

**Given** a page with tables having conflicting edits in different cells
**When** ConflictResolver.resolve() is called
**Then** TableMerge should be invoked for table regions
**And** cell-level merge should occur

### AC-5.2: Non-Table Content Uses Standard Merge

**Given** a page with only paragraph content and conflicts
**When** ConflictResolver.resolve() is called
**Then** standard merge3 algorithm should be used
**And** TableMerge should NOT be invoked

### AC-5.3: Mixed Content Routes Correctly

**Given** a page with both tables and paragraphs
**When** conflicts exist in both tables and paragraphs
**Then** table conflicts should use cell-level merge
**And** paragraph conflicts should use line-level merge

---

## AC-6: ADF Path Selection Integration Tests

### AC-6.1: ADF Path Chosen for Supported Pages

**Given** a page that supports ADF format
**When** surgical update is requested
**Then** PageOperations should use ADF API endpoint
**And** NOT use XHTML storage endpoint

### AC-6.2: Surgical Update Uses ADF Editor

**Given** a surgical update request with operations
**When** update_page_surgical() is called
**Then** AdfEditor should be invoked
**And** operations should target nodes by localId

### AC-6.3: ADF Failure Falls Back to XHTML

**Given** an ADF surgical update that fails (>50% operations fail)
**When** the failure is detected
**Then** system should fall back to XHTML full replacement
**And** log the fallback reason

---

## AC-7: Version Conflict Integration Tests

### AC-7.1: Version Change Detected

**Given** a page version changes between detect and push
**When** the push is attempted
**Then** VersionConflictError should be raised
**And** error should include expected vs actual version

### AC-7.2: Version Conflict Triggers Retry

**Given** a version conflict error during sync
**When** retry logic executes
**Then** page should be re-fetched with current version
**And** merge should be re-attempted

### AC-7.3: Persistent Conflict Reported

**Given** version conflicts that persist across 3 retries
**When** max retries exceeded
**Then** error should be reported to user
**And** sync should fail with appropriate exit code

---

## AC-8: ADF Fallback E2E Tests

### AC-8.1: High Failure Rate Triggers Fallback

**Given** a surgical update where >50% of operations fail
**When** the threshold is exceeded
**Then** system should abandon surgical approach
**And** use full page replacement instead

### AC-8.2: ADF API Error Triggers Fallback

**Given** an ADF API error (network, timeout, server error)
**When** the error is caught
**Then** system should attempt XHTML fallback
**And** log the fallback attempt

### AC-8.3: Fallback Produces Correct Content

**Given** a fallback from ADF to XHTML occurred
**When** the fallback completes
**Then** Confluence page content should be correct
**And** match the intended edits

---

## AC-9: Baseline Manager Integration Tests

### AC-9.1: Baseline Used in 3-Way Merge

**Given** a baseline exists for a page with conflicts
**When** 3-way merge is performed
**Then** the baseline content should be the common ancestor
**And** merge should correctly identify changes from both sides

### AC-9.2: Missing Baseline Fallback

**Given** no baseline exists for a conflicting page
**When** merge is attempted
**Then** system should handle gracefully (e.g., use oldest version)
**And** NOT crash or produce corrupt output

### AC-9.3: Baseline Refresh on Sync

**Given** a successful sync completes
**When** post-sync processing runs
**Then** baseline should be updated with current content
**And** be available for next merge cycle

---

## AC-10: Error Recovery Integration Tests

### AC-10.1: Network Error Retry

**Given** a transient network error during sync
**When** retry logic executes
**Then** exponential backoff should be applied
**And** sync should succeed on retry

### AC-10.2: Partial Sync Commit

**Given** a multi-page sync where some pages fail
**When** errors occur on subset of pages
**Then** successful pages should be committed
**And** failed pages should be reported

### AC-10.3: Merge Failure Writes Markers

**Given** merge3 fails to produce clean merge
**When** conflicts are detected
**Then** conflict markers should be written to file
**And** user should be notified

---

## Test Matrix Summary

| AC | Category | Type | Priority | Tests |
|----|----------|------|----------|-------|
| AC-1 | ADF Surgical | E2E | P0 | 4 |
| AC-2 | Line Break | E2E | P0 | 4 |
| AC-3 | Conflict Resolution | E2E | P1 | 4 |
| AC-4 | Macro Preservation | E2E | P1 | 3 |
| AC-5 | ConflictResolver | Integration | P1 | 3 |
| AC-6 | ADF Path Selection | Integration | P0 | 3 |
| AC-7 | Version Conflict | Integration | P1 | 3 |
| AC-8 | ADF Fallback | E2E | P2 | 3 |
| AC-9 | Baseline Manager | Integration | P1 | 3 |
| AC-10 | Error Recovery | Integration | P2 | 3 |

**Total: 33 acceptance scenarios across 10 categories**

---

## Verification Checklist

For each AC scenario:

- [ ] Test file created in appropriate directory
- [ ] Test follows project naming conventions
- [ ] Test is properly marked (`@pytest.mark.e2e` or `@pytest.mark.integration`)
- [ ] Test includes cleanup fixtures
- [ ] Test has clear assertions with error messages
- [ ] Test passes locally
- [ ] Test passes in CI
