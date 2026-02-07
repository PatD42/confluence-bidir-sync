# ADR-002: Lazy-Load Confluence Client

## Status

**Accepted**

## Context

The `APIWrapper` class wraps the `atlassian-python-api` Confluence client. We needed to decide when to initialize the underlying client and validate credentials:

**Option A: Eager initialization**
- Create Confluence client in `__init__`
- Validate credentials immediately
- Fail fast if credentials are invalid

**Option B: Lazy initialization**
- Create Confluence client on first API call
- Delay credential validation until needed
- Allow object construction even with invalid credentials

## Decision

We chose **Option B: Lazy initialization** of the Confluence client.

### Implementation

```python
class APIWrapper:
    def __init__(self, authenticator: Authenticator):
        self._authenticator = authenticator
        self._client: Optional[Confluence] = None  # Not created yet

    def _get_client(self) -> Confluence:
        """Get or create the Confluence API client."""
        if self._client is None:
            creds = self._authenticator.get_credentials()
            self._client = Confluence(
                url=creds.url,
                username=creds.user,
                password=creds.api_token,
                cloud=True,
            )
        return self._client
```

The client is created on first call to `_get_client()`, which happens when any API method is invoked.

## Consequences

### Positive

1. **Faster initialization**: Creating `APIWrapper` is instant, no network call

2. **Conditional usage**: Applications can construct the wrapper without needing valid credentials until they actually use it

3. **Testing friendly**: Unit tests can create `APIWrapper` instances without mocking the Confluence client

4. **Error at point of use**: Credential errors occur where the API is called, making debugging easier:
   ```python
   wrapper = APIWrapper(auth)  # Success, even with bad creds
   # ... later ...
   wrapper.get_page_by_id("123")  # InvalidCredentialsError here
   ```

5. **Dependency injection support**: Components can be constructed and wired together before credentials are available

### Negative

1. **Delayed error discovery**: Invalid credentials aren't discovered until first API call

2. **Inconsistent timing**: First API call is slower (includes client creation)

3. **Thread safety**: `_get_client()` creates the client; concurrent calls during first access could theoretically race (mitigated by Python GIL)

### Trade-offs Made

- Chose flexibility over fail-fast validation
- Chose test convenience over guaranteed early errors
- Accepted slight first-call latency for faster construction

## Alternatives Considered

### Eager with validate() method

```python
class APIWrapper:
    def __init__(self, authenticator: Authenticator):
        self._client = create_client(authenticator)  # Immediate

    @staticmethod
    def validate_credentials(authenticator: Authenticator) -> bool:
        # Separate validation method
```

Rejected because:
- Still required network call somewhere
- Added complexity without clear benefit
- Tests would still need mocking

### Optional eager flag

```python
class APIWrapper:
    def __init__(self, authenticator: Authenticator, eager: bool = False):
        if eager:
            self._client = create_client(authenticator)
```

Rejected because:
- Added API complexity
- Most callers would use default (lazy) anyway

## References

- `src/confluence_client/api_wrapper.py` - `_get_client()` implementation
- [Lazy Initialization Pattern](https://en.wikipedia.org/wiki/Lazy_initialization)
