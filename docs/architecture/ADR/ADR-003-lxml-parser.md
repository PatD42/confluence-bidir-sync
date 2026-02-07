# ADR-003: Use lxml Parser for XHTML

## Status

**Accepted**

## Context

Confluence storage format is XHTML with custom namespaces:
- `ac:` namespace for Confluence macros (e.g., `ac:structured-macro`)
- `ri:` namespace for resource identifiers (e.g., `ri:attachment`)

BeautifulSoup supports multiple parsers:

**Option A: html.parser (Python built-in)**
- No external dependencies
- Part of Python standard library
- Limited namespace support

**Option B: html5lib**
- Most lenient parsing
- Creates valid HTML5
- Very slow
- May modify content structure

**Option C: lxml**
- Fast XML/HTML parsing
- Proper namespace support
- External C library dependency

## Decision

We chose **Option C: lxml parser** for BeautifulSoup.

### Implementation

```python
from bs4 import BeautifulSoup

class XHTMLParser:
    def parse(self, xhtml: str) -> BeautifulSoup:
        # Always use 'lxml' parser for better namespace handling (ADR-003)
        return BeautifulSoup(xhtml, 'lxml')
```

### Finding Namespaced Elements

```python
def find_macros(self, soup: BeautifulSoup) -> List:
    # Find all elements with ac: namespace prefix
    return soup.find_all(lambda tag: tag.name.startswith('ac:'))
```

## Consequences

### Positive

1. **Proper namespace handling**: `ac:structured-macro` elements are correctly preserved:
   ```xml
   <ac:structured-macro ac:name="info" ac:schema-version="1">
     <ac:rich-text-body>
       <p>Content</p>
     </ac:rich-text-body>
   </ac:structured-macro>
   ```

2. **Fast parsing**: lxml is significantly faster than html5lib and html.parser for large documents

3. **Maintains element integrity**: Namespace prefixes and attributes are preserved exactly

4. **Reliable macro detection**: Can reliably find all `ac:*` elements for preservation

### Negative

1. **External dependency**: Requires lxml library (`pip install lxml`)

2. **Native compilation**: lxml requires C compiler for installation (binary wheels usually available)

3. **Slightly different behavior**: lxml may parse some edge cases differently than browsers

### Trade-offs Made

- Chose namespace correctness over zero dependencies
- Chose parsing speed over maximum leniency
- Accepted native dependency for proper XML handling

## Alternatives Considered

### html.parser with manual namespace handling

```python
soup = BeautifulSoup(xhtml, 'html.parser')
# Would need to manually handle namespace colons
```

Rejected because:
- html.parser converts `ac:structured-macro` to lowercase `ac:structured-macro`
- Attribute namespace prefixes may be lost
- More complex code to preserve namespaces

### Regular expressions

```python
import re
macros = re.findall(r'<ac:structured-macro.*?</ac:structured-macro>', xhtml, re.DOTALL)
```

Rejected because:
- Regex for XML is fragile
- Nested macros would break matching
- No DOM manipulation capabilities

## Verification

The parser correctly handles Confluence content:

```python
>>> soup = BeautifulSoup("""
... <ac:structured-macro ac:name="info">
...   <ac:rich-text-body><p>Test</p></ac:rich-text-body>
... </ac:structured-macro>
... """, 'lxml')
>>> macro = soup.find('ac:structured-macro')
>>> print(macro.name)
ac:structured-macro
>>> print(macro.get('ac:name'))
info
```

## References

- `src/content_converter/xhtml_parser.py` - Parser implementation
- `src/content_converter/macro_preserver.py` - Uses lxml for macro handling
- [BeautifulSoup Parser Differences](https://www.crummy.com/software/BeautifulSoup/bs4/doc/#differences-between-parsers)
- [lxml Documentation](https://lxml.de/)
