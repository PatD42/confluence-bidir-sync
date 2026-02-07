# ADR-004: Use Pandoc Subprocess for Markdown Conversion

## Status

**Accepted**

## Context

Bidirectional conversion between Confluence XHTML and Markdown requires a reliable conversion engine. We evaluated several options:

**Option A: Python libraries (markdownify, html2text)**
- Pure Python, no external dependencies
- Limited table support
- Inconsistent roundtrip fidelity

**Option B: Pandoc via pypandoc**
- Python wrapper around Pandoc
- Requires Pandoc installation
- Additional dependency to maintain

**Option C: Pandoc via direct subprocess**
- Direct subprocess calls to Pandoc CLI
- Requires Pandoc installation
- No Python wrapper dependency
- Full control over arguments and error handling

## Decision

We chose **Option C: Pandoc via direct subprocess**.

### Implementation

```python
import subprocess

class MarkdownConverter:
    def xhtml_to_markdown(self, xhtml: str) -> str:
        result = subprocess.run(
            ["pandoc", "-f", "html", "-t", "markdown"],
            input=xhtml,
            text=True,
            capture_output=True,
            check=True,
            timeout=10
        )
        return result.stdout

    def markdown_to_xhtml(self, markdown: str) -> str:
        result = subprocess.run(
            ["pandoc", "-f", "markdown", "-t", "html"],
            input=markdown,
            text=True,
            capture_output=True,
            check=True,
            timeout=10
        )
        return result.stdout
```

### Installation Check

```python
def _pandoc_installed(self) -> bool:
    try:
        result = subprocess.run(
            ["which", "pandoc"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
```

## Consequences

### Positive

1. **Most reliable conversion**: Pandoc is the gold standard for document conversion

2. **Bidirectional fidelity**: HTML <-> Markdown roundtrips preserve structure

3. **Excellent table support**: Complex tables convert correctly

4. **Code block handling**: Language annotations preserved

5. **Full format control**: Can specify exact Pandoc options:
   ```bash
   pandoc -f html -t markdown+pipe_tables+fenced_code_blocks
   ```

6. **No Python wrapper bugs**: Direct subprocess avoids pypandoc issues

7. **Clear error handling**: Subprocess errors are explicit and catchable

### Negative

1. **External dependency**: Requires Pandoc installation on system PATH

2. **Subprocess overhead**: Each conversion spawns a process (~50-100ms)

3. **Not portable**: Pandoc must be pre-installed, not pip-installable

4. **Platform differences**: Pandoc behavior may vary by version

### Trade-offs Made

- Chose conversion quality over pure-Python solution
- Chose explicit control over wrapper convenience
- Accepted external dependency for reliability

## Timeout Strategy

A 10-second timeout prevents hangs on large/malformed content:

```python
timeout=10  # seconds
```

If conversion exceeds 10 seconds, `ConversionError` is raised:
```
Pandoc conversion timed out (>10s)
```

## Alternatives Considered

### pypandoc library

```python
import pypandoc
output = pypandoc.convert_text(xhtml, 'markdown', format='html')
```

Rejected because:
- Added dependency that wraps subprocess anyway
- Had unresolved issues with some content types
- Less control over error handling

### markdownify

```python
from markdownify import markdownify as md
output = md(xhtml)
```

Rejected because:
- Poor table conversion
- No bidirectional support (one-way only)
- Lost significant formatting

### html2text

```python
import html2text
h = html2text.HTML2Text()
output = h.handle(xhtml)
```

Rejected because:
- Tables render as plain text
- Code blocks lose language annotations
- Not suitable for Confluence's XHTML

## Installation Requirements

Users must install Pandoc separately:

```bash
# macOS
brew install pandoc

# Ubuntu/Debian
apt-get install pandoc

# Windows
choco install pandoc
# or download from https://pandoc.org/installing.html
```

The `MarkdownConverter.__init__()` checks for Pandoc and raises `ConversionError` with installation instructions if not found.

## References

- `src/content_converter/markdown_converter.py` - Converter implementation
- [Pandoc Manual](https://pandoc.org/MANUAL.html)
- [Pandoc Installation](https://pandoc.org/installing.html)
