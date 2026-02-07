# Cross-Cutting - Operations

---

## Error Handling

### Exception Hierarchy

```
ConfluenceError (base)
├── InvalidCredentialsError(user, endpoint)      # 401
├── PageNotFoundError(page_id)                   # 404
├── PageAlreadyExistsError(title, parent_id)     # Duplicate on create
├── VersionConflictError(page_id, expected, actual)  # 409
├── APIUnreachableError(endpoint)                # Network/timeout
├── APIAccessError(message)                      # Other API errors
└── ConversionError(message)                     # Pandoc failures
```

### Error Handling Patterns

**Caller Pattern** (recommended):
```python
try:
    snapshot = page_ops.get_page_snapshot(page_id)
    result = page_ops.apply_operations(page_id, snapshot.xhtml, snapshot.version, ops)
except PageNotFoundError as e:
    logger.warning(f"Page {e.page_id} not found")
except VersionConflictError as e:
    logger.warning(f"Conflict: expected v{e.expected}, found v{e.actual}")
    # Re-fetch and retry
except ConfluenceError as e:
    logger.error(f"Confluence error: {e}")
```

**Result Object Pattern**:
```python
result = page_ops.apply_operations(...)
if not result.success:
    logger.error(f"Update failed: {result.error}")
else:
    logger.info(f"Updated to version {result.new_version}")
```

## Logging

### Logging Strategy

**Output**: Console (stdout/stderr)
**Format**: Standard Python logging with configurable levels

### Log Levels

| Level | Usage |
|-------|-------|
| DEBUG | API request/response details, Pandoc invocation |
| INFO | Operation success (page fetched, updated, created) |
| WARNING | Recoverable issues (retry on 429, version conflict) |
| ERROR | Operation failures, unrecoverable errors |

### Logging Configuration

```python
import logging

# Basic configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Library-specific logger
logger = logging.getLogger('confluence_bidir_sync')
logger.setLevel(logging.DEBUG)  # More verbose for debugging
```

### Log Examples

```
2024-01-29 10:30:15 - confluence_client.api_wrapper - INFO - Fetching page 12345
2024-01-29 10:30:16 - confluence_client.api_wrapper - DEBUG - Response: 200 OK
2024-01-29 10:30:16 - page_operations - INFO - Converted to markdown (1024 chars)
2024-01-29 10:30:17 - surgical_editor - DEBUG - Applied 3 operations, 2 macros preserved
2024-01-29 10:30:18 - confluence_client.api_wrapper - WARNING - Rate limited, retry 1/3
2024-01-29 10:30:19 - confluence_client.api_wrapper - INFO - Updated page 12345 to v6
```

## Caching

### Current State

**No caching implemented** - each operation makes fresh API calls.

### Future Considerations

| Cache Type | Benefit | Implementation |
|------------|---------|----------------|
| Page metadata cache | Reduce API calls for hierarchy traversal | TTL-based, invalidate on update |
| Version cache | Skip fetch if version unchanged | ETag-based |
| Pandoc result cache | Skip re-conversion of unchanged content | Content hash key |

## Configuration

### Current Configuration

**Single source**: `.env` file

```bash
# Required
CONFLUENCE_URL=https://your-instance.atlassian.net/wiki
CONFLUENCE_USER=your-email@company.com
CONFLUENCE_API_TOKEN=your-api-token

# Optional (future)
CONFLUENCE_TIMEOUT=30
CONFLUENCE_RETRY_MAX=3
LOG_LEVEL=INFO
```

### Configuration Loading

```python
from dotenv import load_dotenv
import os

load_dotenv()  # Load .env file

url = os.environ["CONFLUENCE_URL"]
user = os.environ["CONFLUENCE_USER"]
token = os.environ["CONFLUENCE_API_TOKEN"]

# Optional with defaults
timeout = int(os.environ.get("CONFLUENCE_TIMEOUT", "30"))
```

### Future: Configuration File

```yaml
# confluence-sync.yaml (planned for CLI epic)
confluence:
  url: https://your-instance.atlassian.net/wiki
  user: your-email@company.com
  # token: from environment only (never in config file)

sync:
  root_pages:
    - TEAM:/Engineering/Products
  exclude:
    - "*/Archives/*"

options:
  dry_run: false
  force_push: false
```

## Retry Logic

### Rate Limit Handling

**Trigger**: HTTP 429 (Too Many Requests)
**Strategy**: Exponential backoff

| Attempt | Wait | Cumulative |
|---------|------|------------|
| 1 | 0s | 0s |
| 2 | 1s | 1s |
| 3 | 2s | 3s |
| 4 | 4s | 7s |
| Fail | - | `APIAccessError` |

### Retry-After Header

When Confluence provides `Retry-After` header:
```python
if 'Retry-After' in response.headers:
    wait_time = int(response.headers['Retry-After'])
else:
    wait_time = 2 ** retry_count  # Exponential backoff
```

### Non-Retryable Errors

| Status | Exception | Retry |
|--------|-----------|-------|
| 401 | `InvalidCredentialsError` | No |
| 403 | `APIAccessError` | No |
| 404 | `PageNotFoundError` | No |
| 409 | `VersionConflictError` | No |
| 429 | - | Yes (backoff) |
| 5xx | `APIAccessError` | No (fail-fast) |

## Monitoring (Future)

### Health Check

```python
def health_check() -> dict:
    """Check system health."""
    return {
        "confluence_reachable": check_confluence_connection(),
        "pandoc_installed": check_pandoc_version(),
        "credentials_valid": check_credentials(),
    }
```

### Metrics (Planned)

| Metric | Type | Description |
|--------|------|-------------|
| `pages_fetched_total` | Counter | Total pages fetched |
| `pages_updated_total` | Counter | Total pages updated |
| `api_errors_total` | Counter | API errors by type |
| `operation_duration_seconds` | Histogram | Operation latency |

---
