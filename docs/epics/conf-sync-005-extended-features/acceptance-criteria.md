# Acceptance Criteria - CONF-SYNC-005

---

## Overview

Acceptance criteria for Extended Features epic (subset: deletion, page moves).

**Features in scope:**
- EXT-4: Page deletion handling
- FR-2.6: Page moves (reorganize local folders)

**Key Design Decisions:**
- Confluence deletion → delete local file (git history as backup)
- Local deletion → propagates to Confluence (no confirmation; use --dryrun to preview)
- Page moves → detected via CQL ancestors field
- No parent_id in frontmatter; hierarchy inferred from folder structure

---

## AC-1: Page Deletion - Confluence → Local (EXT-4)

### AC-1.1: Detect Deleted Page
**Given** a local file with `page_id: 12345` in frontmatter
**And** Confluence page 12345 no longer exists (deleted or moved to trash)
**When** `confluence-sync` runs
**Then** the deletion is detected
**And** output displays: "Deleted in Confluence: Getting-Started.md (page 12345)"

### AC-1.2: Delete Local File Only
**Given** a Confluence page was deleted
**When** sync detects the deletion
**Then** the local markdown file is deleted
**And** output displays: "Removed local: docs/Getting-Started.md"
**Note**: Child folders are NOT automatically deleted. Each page deletion is detected independently via its page_id. A page move could appear as deletion if only checking the deleted page.

### AC-1.3: Dry Run Shows Deletions
**Given** a Confluence page was deleted
**When** `confluence-sync --dryrun` runs
**Then** output shows: "Would delete: docs/Getting-Started.md (page deleted in Confluence)"
**And** no files are deleted

### AC-1.4: Multiple Deletions
**Given** 3 Confluence pages were deleted independently
**When** sync runs
**Then** each deletion is detected by checking page_id existence
**And** all 3 local files are deleted
**And** summary shows: "Deleted 3 local files (pages removed from Confluence)"

### AC-1.5: Distinguish Deletion from Move
**Given** a Confluence page was moved (not deleted)
**When** sync runs
**Then** page still exists in Confluence (different parent)
**And** file is NOT deleted (handled by move detection instead)

---

## AC-2: Page Deletion - Local → Confluence (EXT-4)

### AC-2.1: Detect Local Deletion
**Given** a local file with `page_id: 12345` existed at last sync (tracked in state.yaml)
**And** the local file has been deleted
**When** `confluence-sync` runs
**Then** the deletion is detected
**And** output displays: "Local file deleted: Getting-Started.md (page 12345)"

### AC-2.2: Delete Confluence Page
**Given** local file was deleted
**When** sync proceeds
**Then** Confluence page is moved to trash (not permanently deleted)
**And** output displays: "Deleted from Confluence: Getting Started (page 12345)"
**Note**: No confirmation prompt. Use `--dryrun` to preview deletions before running.

### AC-2.3: Dry Run Shows Pending Deletions
**Given** local files were deleted
**When** `confluence-sync --dryrun` runs
**Then** output shows: "Would delete from Confluence: Getting Started (page 12345)"
**And** no Confluence pages are deleted

### AC-2.4: Multiple Local Deletions
**Given** 3 local files were deleted
**When** sync runs
**Then** all 3 Confluence pages are moved to trash
**And** summary shows: "Deleted 3 pages from Confluence"

---

## AC-3: Conflict Resolution via 3-Way Merge

### AC-3.1: Baseline Repository Initialization
**Given** `.confluence-sync/baseline/` does not exist
**When** first successful sync completes
**Then** hidden git repo is created at `.confluence-sync/baseline/`
**And** synced file content is committed as initial baseline
**And** `.confluence-sync/baseline/.git/` contains the repo

### AC-3.2: Baseline Update After Sync
**Given** sync completes successfully
**When** files are pushed or pulled
**Then** `.confluence-sync/baseline/` is updated with synced content
**And** changes are committed with message: "baseline: {timestamp}"

### AC-3.3: Auto-Merge Non-Overlapping Changes
**Given** local file changed (lines 10-15)
**And** Confluence changed (lines 50-55, no overlap)
**When** sync detects both-sides-changed conflict
**Then** 3-way merge is attempted using `git merge-file`
**And** BASE = baseline content, OURS = local, THEIRS = Confluence
**And** merge succeeds automatically
**And** merged result is pushed to Confluence
**And** output displays: "Auto-merged: page.md (no conflicts)"

### AC-3.4: Manual Resolution for Overlapping Changes
**Given** local file changed (lines 10-20)
**And** Confluence changed (lines 15-25, overlap on 15-20)
**When** sync detects conflict with overlap
**Then** 3-way merge produces conflict markers (`<<<<`, `====`, `>>>>`)
**And** local file is updated with conflict markers
**And** sync stops for this file
**And** output displays: "Conflict: page.md requires manual resolution"

### AC-3.5: Dry Run Shows Merge Preview
**Given** both-sides-changed conflict exists
**When** `confluence-sync --dryrun` runs
**Then** output shows: "Would attempt merge: page.md"
**And** indicates if merge would succeed or have conflicts
**And** no files are modified

---

## AC-4: Page Moves - Confluence → Local (FR-2.6)

### AC-4.1: Detect Page Move via Ancestors
**Given** a local file `docs/old-parent/page.md` with `page_id: 12345`
**And** Confluence page 12345 was moved under a different parent
**When** `confluence-sync` runs
**Then** the move is detected via CQL query with `ancestors` expansion
**And** current parent from API differs from local folder structure
**And** output displays: "Moved in Confluence: page.md (old-parent → new-parent)"
**Note**: CQL query must include `expand=ancestors` to get parent chain.

### AC-4.2: Move Local File to Match
**Given** Confluence page was moved to new location
**When** sync detects the move
**Then** local file is moved to match new hierarchy
**And** old folder is deleted if empty
**And** output displays: "Moved local: docs/old-parent/page.md → docs/new-parent/page.md"

### AC-4.3: Handle Nested Moves
**Given** a parent page with 5 children is moved in Confluence
**When** sync runs
**Then** all 6 files (parent + 5 children) are moved together
**And** folder structure is preserved
**And** summary shows: "Moved 6 files to new location"

### AC-4.4: Dry Run Shows Moves
**Given** pages were moved in Confluence
**When** `confluence-sync --dryrun` runs
**Then** output shows: "Would move: docs/old-parent/page.md → docs/new-parent/page.md"
**And** no files are moved

### AC-4.5: Conflict - Local File Exists at Target
**Given** Confluence page was moved to new location
**And** a different local file already exists at the target path
**When** sync runs
**Then** error displays: "Move conflict: target path already exists"
**And** sync fails for this page (continue with others)
**And** user must resolve manually

---

## AC-5: Page Moves - Local → Confluence (FR-2.6)

### AC-5.1: Detect Local File Move
**Given** a local file with `page_id: 12345` was moved to different folder
**When** `confluence-sync` runs
**Then** the move is detected (page_id in new location, missing from old)
**And** output displays: "Moved locally: page.md (old-parent → new-parent)"

### AC-5.2: Update Confluence Parent
**Given** local file was moved
**When** sync detects the move
**Then** Confluence page parent is updated to match new hierarchy
**And** output displays: "Updated Confluence parent for: Getting Started"

### AC-5.3: Find Parent by Path
**Given** local file moved to `docs/new-section/page.md`
**And** `docs/new-section/` corresponds to Confluence page with id 67890
**When** sync runs
**Then** page 12345's parent is changed to 67890 in Confluence

### AC-5.4: Move to Root
**Given** local file moved to root sync folder (no parent folder)
**When** sync runs
**Then** page is moved under configured root parent_page_id in Confluence

### AC-5.5: Invalid Move Target
**Given** local file moved to folder that doesn't correspond to a Confluence page
**When** sync runs
**Then** error displays: "Cannot move: target folder 'new-section' has no Confluence page"
**And** sync fails for this page

### AC-5.6: Create Parent via New File and Folder
**Given** user creates a new markdown file `docs/new-section.md` (no page_id)
**And** user creates folder `docs/new-section/`
**And** user moves existing file with `page_id: 12345` into `docs/new-section/`
**When** `confluence-sync` runs
**Then** new page is created for `new-section.md` with new page_id
**And** existing page 12345's parent is updated to the newly created page
**And** output displays:
  - "Created: new-section (page 99999)"
  - "Moved: Getting Started under new-section"

---

## Error Scenarios

| ID | Scenario | Error Message | Exit Code |
|----|----------|---------------|-----------|
| ES-1 | Delete Confluence page fails (permissions) | "Cannot delete page 12345: insufficient permissions" | 1 |
| ES-2 | Move fails (API error) | "Failed to move page 12345: {api error}" | 1 |
| ES-3 | Move conflict (target exists) | "Move conflict: target path already exists" | 1 |
| ES-4 | Invalid frontmatter YAML | "Invalid frontmatter in {file}: {details}" | 1 |
| ES-5 | Page not found during move | "Page 12345 not found in Confluence" | 1 |
| ES-6 | Parent folder has no corresponding page | "Cannot move: target folder has no Confluence page" | 1 |

---

## E2E Test Scenarios

### E2E-1: Confluence Deletion Flow
1. Sync space with 10 pages
2. Delete 2 pages in Confluence (via API or UI)
3. Run `confluence-sync`
4. Verify 2 local files deleted
5. Verify remaining 8 files unchanged
6. Verify child folders NOT auto-deleted (each deletion independent)

### E2E-2: Local Deletion Flow
1. Sync space with 10 pages
2. Delete 2 local files
3. Run `confluence-sync --dryrun` first
4. Verify dry run shows pending deletions
5. Run `confluence-sync`
6. Verify 2 Confluence pages in trash
7. Verify remaining 8 pages unchanged

### E2E-3: Page Move in Confluence
1. Sync space with nested hierarchy
2. Move parent page to different location in Confluence
3. Run `confluence-sync`
4. Verify local files moved to match
5. Verify old folders cleaned up if empty

### E2E-4: Page Move Locally
1. Sync space with nested hierarchy
2. Move local file to different folder
3. Run `confluence-sync`
4. Verify Confluence page parent updated
5. Verify page accessible at new location in Confluence

### E2E-5: Dry Run for All Operations
1. Set up scenario with deletions and moves
2. Run `confluence-sync --dryrun`
3. Verify output shows all pending operations
4. Verify NO changes made to files or Confluence

### E2E-6: Create Parent and Move Child
1. Sync space with flat structure (pages A, B, C at root)
2. Locally: create `docs/new-section.md` (new file, no page_id)
3. Locally: create folder `docs/new-section/`
4. Locally: move `docs/page-B.md` into `docs/new-section/`
5. Run `confluence-sync`
6. Verify new page created for new-section
7. Verify page B's parent updated to new-section in Confluence
8. Verify hierarchy in Confluence matches local folder structure

### E2E-7: Distinguish Move from Deletion
1. Sync space with page under parent-A
2. In Confluence: move page to parent-B
3. Run `confluence-sync`
4. Verify page NOT deleted (still exists in Confluence)
5. Verify local file moved to parent-B folder
6. Verify old parent-A folder cleaned up if empty

### E2E-8: Conflict Resolution
1. Sync space with pages A and B in separate folders
2. In Confluence: move page A to folder where B exists locally
3. Run `confluence-sync`
4. Verify error reported for conflict
5. Verify page B unchanged
6. Verify manual resolution required

---

## Success Criteria

- [ ] All acceptance criteria pass (AC-1 through AC-5)
- [ ] All error scenarios handled gracefully (ES-1 through ES-6)
- [ ] All E2E test scenarios pass (E2E-1 through E2E-8)
- [ ] Unit test coverage >90% for new modules
- [ ] Moves preserve frontmatter and content
- [ ] CQL queries with ancestors expansion work efficiently
