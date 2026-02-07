# ADR-001: Typed Exception Hierarchy with Rich Context

## Status

**Accepted**

## Context

The confluence-bidir-sync library interacts with an external REST API that can fail in many ways:
- Authentication failures (401)
- Resource not found (404)
- Duplicate resources (title conflicts)
- Network connectivity issues
- Rate limiting (429)
- Version conflicts (409)
- Content conversion failures

We needed to decide how to represent these errors to calling code:

**Option A: Use generic exceptions**
- Raise `Exception` or `RuntimeError` with error messages
- Simple to implement
- Callers parse error strings to determine error type

**Option B: HTTP-specific exceptions**
- Create exceptions for each HTTP status code (HTTPError401, HTTPError404)
- Maps 1:1 to HTTP responses
- Exposes HTTP implementation details to callers

**Option C: Domain-specific typed exceptions**
- Create a hierarchy of domain exceptions (PageNotFoundError, InvalidCredentialsError)
- Include relevant context as attributes
- Abstract HTTP details from callers

## Decision

We chose **Option C: Domain-specific typed exceptions with rich context**.

### Implementation

All exceptions inherit from `ConfluenceError` base class:

```python
class ConfluenceError(Exception):
    """Base exception for all Confluence-related errors."""
    pass

class InvalidCredentialsError(ConfluenceError):
    def __init__(self, user: str, endpoint: str):
        super().__init__(f"API key is invalid (user: {user}, endpoint: {endpoint})")
        self.user = user
        self.endpoint = endpoint

class PageNotFoundError(ConfluenceError):
    def __init__(self, page_id: str):
        super().__init__(f"Page {page_id} not found")
        self.page_id = page_id
```

### Exception Hierarchy

```
ConfluenceError (base)
    +-- InvalidCredentialsError(user, endpoint)
    +-- PageNotFoundError(page_id)
    +-- PageAlreadyExistsError(title, parent_id)
    +-- APIUnreachableError(endpoint)
    +-- APIAccessError(message)
    +-- ConversionError(message)
```

## Consequences

### Positive

1. **Type-safe error handling**: Callers can catch specific exceptions:
   ```python
   except PageNotFoundError as e:
       logger.warning(f"Page {e.page_id} doesn't exist")
   ```

2. **Rich context for debugging**: Exceptions include relevant data, not just messages:
   ```python
   except InvalidCredentialsError as e:
       print(f"Check credentials for user {e.user} at {e.endpoint}")
   ```

3. **Easy catch-all**: All library errors can be caught with single `except ConfluenceError`

4. **Self-documenting API**: Exception types in signatures indicate possible failures

5. **IDE support**: Type checkers can verify exception handling is complete

### Negative

1. **More code**: Each exception type requires a class definition

2. **Error translation layer**: `APIWrapper._translate_error()` must map HTTP errors to exceptions

3. **Context loss**: Some HTTP details (headers, response body) are not preserved

### Trade-offs Made

- Chose domain clarity over HTTP transparency
- Chose caller convenience over implementation simplicity
- Chose type safety over dynamic error handling

## References

- `src/confluence_client/errors.py` - Exception definitions
- `src/confluence_client/api_wrapper.py` - Error translation logic
- [Python Exception Hierarchy](https://docs.python.org/3/library/exceptions.html)
