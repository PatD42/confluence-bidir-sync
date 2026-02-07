# Architecture - Runtime View

---

## Key Runtime Scenarios

### Scenario 1: Get Page Snapshot

**Actor**: Agentic AI or Human User
**Goal**: Fetch a Confluence page with both XHTML (for surgical updates) and markdown (for editing)

```mermaid
sequenceDiagram
    participant Agent
    participant PO as PageOperations
    participant AW as APIWrapper
    participant CC as Confluence Cloud
    participant MC as MarkdownConverter
    participant Pandoc

    Agent->>PO: get_page_snapshot(page_id)
    PO->>AW: get_page_by_id(page_id, expand="body.storage,version,metadata.labels")

    Note over AW: Apply retry logic
    AW->>CC: GET /wiki/api/v2/pages/{id}
    CC-->>AW: Page JSON (XHTML in body.storage.value)

    alt 404 Not Found
        AW-->>PO: raise PageNotFoundError(page_id)
        PO-->>Agent: PageNotFoundError
    else 401 Unauthorized
        AW-->>PO: raise InvalidCredentialsError
        PO-->>Agent: InvalidCredentialsError
    else 200 OK
        AW-->>PO: Page dict
        PO->>MC: xhtml_to_markdown(xhtml)
        MC->>Pandoc: subprocess stdin
        Pandoc-->>MC: markdown stdout
        MC-->>PO: markdown string
        PO-->>Agent: PageSnapshot(xhtml, markdown, version, labels, ...)
    end
```

**Key Points**:
- XHTML is preserved as-is for surgical updates
- Markdown is for human/agent editing
- Version number captured for optimistic locking

---

### Scenario 2: Apply Surgical Operations

**Actor**: Agentic AI
**Goal**: Modify specific content without corrupting macros or formatting

```mermaid
sequenceDiagram
    participant Agent
    participant PO as PageOperations
    participant SE as SurgicalEditor
    participant AW as APIWrapper
    participant CC as Confluence Cloud

    Agent->>PO: apply_operations(page_id, base_xhtml, base_version, [operations])

    PO->>SE: apply(xhtml, operations)
    loop For each operation
        SE->>SE: Find target element (skip ac: elements)
        SE->>SE: Apply modification
    end
    SE-->>PO: modified_xhtml

    Note over PO: Verify macro count unchanged
    PO->>PO: count_macros(before) == count_macros(after)

    PO->>AW: get_page_by_id(page_id)
    Note over AW: Check current version
    AW->>CC: GET /wiki/api/v2/pages/{id}
    CC-->>AW: Current page (version N)

    alt Version mismatch
        AW-->>PO: version != base_version
        PO-->>Agent: UpdateResult(success=False, error="Version conflict")
    else Version matches
        PO->>AW: update_page(page_id, title, modified_xhtml, version)
        AW->>CC: PUT /wiki/api/v2/pages/{id}
        CC-->>AW: Updated page (version N+1)
        AW-->>PO: Result dict
        PO-->>Agent: UpdateResult(success=True, new_version=N+1)
    end
```

**Key Points**:
- Surgical editor NEVER modifies `ac:` namespace elements
- Version check before upload prevents silent overwrites
- Macro count verification ensures preservation

---

### Scenario 3: Create New Page

**Actor**: Agentic AI or Human User
**Goal**: Create a Confluence page from markdown content

```mermaid
sequenceDiagram
    participant Agent
    participant PO as PageOperations
    participant MC as MarkdownConverter
    participant AW as APIWrapper
    participant CC as Confluence Cloud

    Agent->>PO: create_page(space_key, title, markdown, parent_id, check_duplicate=True)

    alt check_duplicate=True
        PO->>AW: get_page_by_title(space, title)
        AW->>CC: GET /wiki/api/v2/spaces/{key}/pages?title={title}
        alt Page exists
            CC-->>AW: Existing page data
            AW-->>PO: Page dict
            PO-->>Agent: CreateResult(success=False, error="Page already exists")
        else Page doesn't exist
            CC-->>AW: null/empty
            AW-->>PO: None
        end
    end

    PO->>MC: markdown_to_xhtml(markdown)
    MC-->>PO: xhtml

    PO->>AW: create_page(space, title, xhtml, parent_id)
    AW->>CC: POST /wiki/api/v2/spaces/{key}/pages

    alt 409 Conflict (race condition)
        CC-->>AW: Error response
        AW-->>PO: raise PageAlreadyExistsError
        PO-->>Agent: CreateResult(success=False, error="...")
    else 200 Created
        CC-->>AW: Created page JSON
        AW-->>PO: Page dict
        PO-->>Agent: CreateResult(success=True, page_id, version=1)
    end
```

**Key Points**:
- Optional duplicate detection before create attempt
- Handles race condition via API error
- Returns page_id for subsequent operations

---

### Scenario 4: Rate Limit Handling

**Actor**: System (during any API call)
**Goal**: Automatically retry on 429 without user intervention

```mermaid
sequenceDiagram
    participant Caller
    participant RL as retry_on_rate_limit
    participant AW as APIWrapper
    participant CC as Confluence Cloud

    Caller->>RL: retry_on_rate_limit(api_call, args)

    loop Max 3 retries
        RL->>AW: Execute API call
        AW->>CC: HTTP Request

        alt 200 OK
            CC-->>AW: Success response
            AW-->>RL: Result
            RL-->>Caller: Result
        else 429 Rate Limited
            CC-->>AW: 429 + Retry-After header
            Note over RL: Wait 1s, 2s, 4s (exponential)
            RL->>RL: sleep(backoff)
        else Other Error (401, 404, 500, etc.)
            CC-->>AW: Error response
            AW-->>RL: raise specific exception
            RL-->>Caller: raise exception (no retry)
        end
    end

    Note over RL: After 3 retries
    RL-->>Caller: raise APIAccessError("Rate limit persisted")
```

**Key Points**:
- Only 429 responses trigger retry
- Exponential backoff: 1s → 2s → 4s
- Other errors fail immediately (fail-fast)
- Respects Retry-After header when present

---

### Scenario 5: Error Translation

**Actor**: System (in APIWrapper)
**Goal**: Convert HTTP/API errors to typed exceptions

```mermaid
sequenceDiagram
    participant Caller
    participant AW as APIWrapper
    participant Client as atlassian-python-api
    participant CC as Confluence Cloud

    Caller->>AW: get_page_by_id("12345")
    AW->>Client: confluence.get_page_by_id()
    Client->>CC: GET /wiki/api/v2/pages/12345

    alt HTTP 401
        CC-->>Client: Unauthorized
        Client-->>AW: HTTPError(401)
        AW-->>Caller: raise InvalidCredentialsError(user, endpoint)
    else HTTP 404
        CC-->>Client: Not Found
        Client-->>AW: HTTPError(404)
        AW-->>Caller: raise PageNotFoundError("12345")
    else HTTP 409
        CC-->>Client: Conflict
        Client-->>AW: HTTPError(409)
        AW-->>Caller: raise VersionConflictError(...)
    else Connection Error
        Client-->>AW: ConnectionError
        AW-->>Caller: raise APIUnreachableError(endpoint)
    else Timeout
        Client-->>AW: Timeout
        AW-->>Caller: raise APIUnreachableError(endpoint)
    else Other
        CC-->>Client: Error response
        Client-->>AW: Exception
        AW-->>Caller: raise APIAccessError(message)
    end
```

**Key Points**:
- Each HTTP status maps to a specific exception type
- Exceptions include context (page_id, endpoint, user)
- Enables precise error handling by callers

---

### Scenario 6: Bidirectional Sync with 3-Way Merge

**Actor**: CLI User
**Goal**: Synchronize local markdown files with Confluence, handling concurrent edits

```mermaid
sequenceDiagram
    participant User
    participant CLI as sync_command
    participant BM as BaselineManager
    participant FM as FileMapper
    participant TM as TableMerge
    participant PO as PageOperations
    participant CC as Confluence Cloud

    User->>CLI: confluence-sync sync --bidir
    CLI->>BM: get_baseline_content(page_id)
    BM-->>CLI: baseline_markdown

    CLI->>FM: detect_changes()
    FM->>CC: Fetch remote pages
    CC-->>FM: Remote content
    FM-->>CLI: ConflictingPages list

    loop For each conflict
        CLI->>TM: merge_content_with_table_awareness(baseline, local, remote)

        alt Tables detected
            TM->>TM: normalize_table_for_merge()
            TM->>TM: merge3 cell-level merge
            TM->>TM: denormalize_table()
        else No tables
            TM->>TM: line-based merge3
        end

        alt Clean merge
            TM-->>CLI: (merged_content, has_conflicts=False)
            CLI->>CLI: Write merged to local file
            CLI->>PO: update_page_surgical_adf(page_id, merged, baseline)
            PO->>CC: PUT ADF update
            CLI->>BM: update_baseline(page_id, merged)
        else Conflict
            TM-->>CLI: (content_with_markers, has_conflicts=True)
            CLI->>CLI: Write conflict markers to local file
            CLI-->>User: "Resolve conflicts manually"
        end
    end
```

**Key Points**:
- Baseline is the source of truth for 3-way merge
- Table-aware merge handles cell-level changes in same row
- Auto-merged content is pushed to Confluence and baseline updated
- Conflicts require manual resolution

---

### Scenario 7: ADF Surgical Update with Baseline Diffing

**Actor**: Sync Command
**Goal**: Update Confluence page using ADF with precise diffing

```mermaid
sequenceDiagram
    participant CLI as SyncCommand
    participant PO as PageOperations
    participant DA as DiffAnalyzer
    participant AE as AdfEditor
    participant AW as APIWrapper
    participant CC as Confluence Cloud

    CLI->>PO: update_page_surgical_adf(page_id, new_md, baseline_md)

    PO->>AW: get_page_adf(page_id)
    AW->>CC: GET /wiki/api/v2/pages/{id}?body-format=atlas_doc_format
    CC-->>AW: ADF JSON
    AW-->>PO: ADF document

    Note over PO: Baseline-centric diffing
    PO->>PO: extract_markdown_blocks(baseline_md)
    PO->>PO: extract_markdown_blocks(new_md)
    PO->>DA: analyze(baseline_blocks, new_blocks)
    DA-->>PO: List[SurgicalOperation]

    PO->>AE: apply_operations(adf_doc, operations, local_id_map)
    Note over AE: Convert <br> to hardBreak nodes
    AE-->>PO: (modified_adf, success_count, failure_count)

    alt >50% operations failed
        PO->>PO: Fall back to full replacement
        PO->>AW: update_page(xhtml)
    else Operations succeeded
        PO->>AW: update_page_adf(page_id, modified_adf)
        AW->>CC: PUT /wiki/api/v2/pages/{id}
    end

    CC-->>AW: Updated page
    AW-->>PO: Result
    PO-->>CLI: AdfUpdateResult
```

**Key Points**:
- Diff is baseline vs. new markdown (same format = no parser mismatch)
- ADF operations target nodes by localId (stable identifier)
- `<br>` tags in markdown become `hardBreak` ADF nodes
- Falls back to full replacement if surgical operations fail

---
