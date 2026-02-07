# ADR-005: Retry Only on 429 Rate Limits (Fail-Fast for Others)

## Status

**Accepted**

## Context

The Confluence Cloud API can return various error responses. We needed to decide which errors warrant automatic retry:

**Option A: Retry on all transient errors**
- Retry 429 (rate limit), 5xx (server errors), network errors
- Maximum resilience
- May mask underlying issues

**Option B: Retry only on 429 rate limits**
- Only retry when explicitly rate-limited
- Fail fast for other errors
- Clear feedback to callers

**Option C: No automatic retry**
- Let caller handle all retries
- Maximum control
- More complex caller code

## Decision

We chose **Option B: Retry only on 429 rate limits** with exponential backoff.

### Implementation

```python
def retry_on_rate_limit(func, *args, **kwargs):
    max_retries = 3
    for retry_num in range(max_retries + 1):  # 0, 1, 2, 3
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if not _is_rate_limit_error(e):
                raise  # Fail-fast for non-rate-limit errors
            if retry_num >= max_retries:
                raise APIAccessError("Confluence API failure (after 3 retries)")
            wait_time = 2 ** retry_num  # 1, 2, 4 seconds
            time.sleep(wait_time)
```

### Exponential Backoff Schedule

| Attempt | Wait Before | Formula |
|---------|-------------|---------|
| 1 | 0s | Immediate |
| 2 | 1s | 2^0 |
| 3 | 2s | 2^1 |
| 4 | 4s | 2^2 |
| Fail | - | `APIAccessError` |

Total maximum wait: 7 seconds before failure.

### Rate Limit Detection

```python
def _is_rate_limit_error(exception: Exception) -> bool:
    error_msg = str(exception).lower()
    rate_limit_patterns = [
        '429',
        'too many requests',
        'rate limit exceeded',
        'rate limit hit',
        'rate limited',
    ]
    if any(pattern in error_msg for pattern in rate_limit_patterns):
        return True
    # Also check status_code attribute
    if hasattr(exception, 'status_code') and exception.status_code == 429:
        return True
    return False
```

## Consequences

### Positive

1. **Clear error semantics**: Rate limits are handled transparently; other errors surface immediately

2. **Fast failure**: 401 (auth), 404 (not found), 409 (conflict) fail immediately - these won't succeed on retry

3. **Predictable behavior**: Maximum 7 seconds of retry delay before failure

4. **Logging visibility**: Each retry is logged, making rate limit patterns visible:
   ```
   Rate limit hit, retrying in 1s (retry 1/3)
   Rate limit hit, retrying in 2s (retry 2/3)
   ```

5. **API-friendly**: Exponential backoff respects Confluence's rate limit recovery

### Negative

1. **5xx errors fail immediately**: Server errors could potentially succeed on retry

2. **Network glitches not retried**: Temporary network issues cause immediate failure

3. **Fixed retry count**: 3 retries may not be enough for sustained rate limiting

### Trade-offs Made

- Chose clarity over maximum resilience
- Chose fail-fast for debugging ease
- Chose simple retry logic over complex backoff algorithms

## Why Not Retry Other Errors?

| Error Type | Why Not Retry |
|------------|---------------|
| 401 Unauthorized | Credentials won't become valid |
| 404 Not Found | Page won't appear on retry |
| 409 Conflict | Requires user decision to resolve |
| 5xx Server | May mask persistent issues |
| Network Error | May mask connectivity problems |

For these cases, immediate failure gives callers the information they need to take appropriate action.

## Alternatives Considered

### Retry all 5xx errors

```python
if is_rate_limit_error(e) or is_server_error(e):
    retry()
```

Rejected because:
- 5xx during maintenance could retry for hours
- Masks persistent server issues
- Callers should be notified of infrastructure problems

### Configurable retry policy

```python
retry_on_rate_limit(func, retry_on=[429, 500, 502, 503], max_retries=5)
```

Rejected because:
- Added API complexity
- Most callers would use defaults anyway
- YAGNI (You Aren't Gonna Need It)

### Using Retry-After header

```python
retry_after = int(response.headers.get('Retry-After', wait_time))
```

Rejected because:
- `atlassian-python-api` doesn't expose response headers
- Would require lower-level HTTP access
- Exponential backoff is sufficient

## References

- `src/confluence_client/retry_logic.py` - Retry implementation
- [Confluence Cloud Rate Limits](https://developer.atlassian.com/cloud/confluence/rate-limiting/)
- [Exponential Backoff](https://en.wikipedia.org/wiki/Exponential_backoff)
