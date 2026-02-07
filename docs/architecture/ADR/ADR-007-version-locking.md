# ADR-007: Optimistic Version Locking with Fail-Fast on Conflicts

## Status

**Accepted**

## Context

Confluence pages have version numbers that increment with each update. When updating a page, the API requires the current version number to prevent concurrent modifications from overwriting each other.

Possible conflict handling strategies:

**Option A: Last-write-wins**
- Always force update regardless of version
- Simpler code
- Risk of data loss

**Option B: Optimistic locking with automatic merge**
- Detect conflicts
- Automatically merge changes
- Complex logic, may produce incorrect results

**Option C: Optimistic locking with fail-fast**
- Detect conflicts
- Immediately fail with descriptive error
- Let caller decide how to handle

## Decision

We chose **Option C: Optimistic locking with fail-fast**.

### Implementation

```python
def update_page(self, page_id: str, title: str, body: str, version: int, **kwargs):
    def _update():
        try:
            client = self._get_client()
            return client.update_page(
                page_id=page_id,
                title=title,
                body=body,
                **kwargs
            )
        except Exception as e:
            error_msg = str(e).lower()
            if '409' in error_msg or 'conflict' in error_msg:
                raise APIAccessError(
                    f"Version conflict updating page {page_id} "
                    f"(version {version} is stale)"
                )
            raise self._translate_error(e, f"update_page({page_id})")
    return retry_on_rate_limit(_update)
```

### Conflict Detection

The Confluence API returns HTTP 409 when:
- The provided version doesn't match the current version
- Another user updated the page since it was fetched

We detect this in `_translate_error()` and raise `APIAccessError` with a descriptive message.

## Consequences

### Positive

1. **No silent data loss**: Concurrent modifications are detected, not overwritten

2. **Clear error messages**: Caller knows exactly what happened:
   ```
   Version conflict updating page 123456 (version 5 is stale)
   ```

3. **Caller control**: Application can decide how to handle:
   - Re-fetch and retry
   - Show diff to user
   - Abort operation

4. **Simple implementation**: No complex merge logic

5. **Auditable**: Version conflicts appear in logs for debugging

### Negative

1. **Manual conflict resolution**: Caller must implement retry/merge logic

2. **More code for caller**: Simple use cases need conflict handling

3. **Potential retry loops**: Busy pages may have repeated conflicts

### Trade-offs Made

- Chose data safety over convenience
- Chose explicit handling over automatic merge
- Chose simplicity over built-in conflict resolution

## Usage Pattern

### Basic Update (may fail on conflict)

```python
try:
    new_version = updater.update_page(
        page_id=page.page_id,
        title=page.title,
        content=new_content,
        version=page.version
    )
    print(f"Updated to version {new_version}")
except APIAccessError as e:
    if "version conflict" in str(e).lower():
        print("Page was modified - please refresh and try again")
    else:
        raise
```

### Update with Conflict Retry

```python
max_attempts = 3
for attempt in range(max_attempts):
    try:
        # Fetch latest version
        page = fetcher.fetch_page(page_id)

        # Apply our changes
        modified_content = apply_changes(page.content_storage)

        # Attempt update
        new_version = updater.update_page(
            page_id=page.page_id,
            title=page.title,
            content=modified_content,
            version=page.version
        )
        print(f"Updated to version {new_version}")
        break

    except APIAccessError as e:
        if "version conflict" not in str(e).lower():
            raise
        if attempt < max_attempts - 1:
            print(f"Conflict detected, retrying (attempt {attempt + 1})")
        else:
            raise Exception("Max retry attempts exceeded")
```

## Alternatives Considered

### Force update (ignore version)

Some APIs support force updates that bypass version checks:
```python
client.update_page(page_id, content, force=True)
```

Rejected because:
- atlassian-python-api doesn't support this
- Risks losing concurrent changes
- Not suitable for collaborative editing

### Automatic three-way merge

```python
def update_with_merge(page_id, our_changes):
    base = get_base_version()
    current = fetch_current()
    merged = three_way_merge(base, our_changes, current)
    update(page_id, merged)
```

Rejected because:
- XHTML merge is complex and error-prone
- May produce invalid content
- Unexpected results for users
- Would need base version storage

### Pessimistic locking

```python
lock = confluence.lock_page(page_id)
try:
    # Make changes
    update_page()
finally:
    confluence.unlock_page(page_id)
```

Rejected because:
- Confluence Cloud doesn't support explicit locks
- Would require external locking mechanism
- Risk of orphaned locks

## Version Number Flow

```
1. Fetch page         -> version=5
2. Modify locally     -> version still 5
3. Update with v=5    -> Confluence checks 5 == current
   a) If current=5    -> Success, new version=6
   b) If current=6    -> 409 Conflict
```

The `atlassian-python-api` library automatically increments the version number when calling `update_page()`, but it still validates against the current server version.

## References

- `src/confluence_client/api_wrapper.py` - Version conflict detection
- `src/confluence_client/page_updater.py` - Update with version parameter
- [Optimistic Locking](https://en.wikipedia.org/wiki/Optimistic_concurrency_control)
- [Confluence REST API - Update Content](https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-content/#api-wiki-rest-api-content-id-put)
