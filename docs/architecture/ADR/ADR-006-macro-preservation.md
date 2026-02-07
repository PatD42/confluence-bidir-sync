# ADR-006: Preserve Macros as HTML Comments

## Status

**Accepted**

## Context

Confluence uses custom macros in the `ac:` namespace for rich functionality:
- Info/warning/note panels
- Code blocks with syntax highlighting
- Table of contents
- Embedded content (images, attachments)

These macros are stored as XHTML:

```xml
<ac:structured-macro ac:name="info" ac:schema-version="1">
  <ac:rich-text-body>
    <p>Important information here.</p>
  </ac:rich-text-body>
</ac:structured-macro>
```

When converting to Markdown, these macros must survive the roundtrip so they can be restored when pushing back to Confluence.

**Option A: Convert macros to Markdown equivalents**
- Info panels -> blockquotes
- Code macros -> code blocks
- Lossy conversion, some macros have no equivalent

**Option B: Strip macros entirely**
- Simple approach
- Content is lost
- Markdown is cleaner

**Option C: Preserve macros as HTML comments**
- Wrap macro XHTML in HTML comments
- Survives Pandoc conversion
- Restored on push back

## Decision

We chose **Option C: Preserve macros as HTML comments**.

### Implementation

#### Before Conversion (preserve)

```python
def preserve_as_comments(self, soup: BeautifulSoup) -> BeautifulSoup:
    macros = self.detect_macros(soup)
    for macro in macros:
        macro_html = str(macro)
        comment_text = f" CONFLUENCE_MACRO: {macro_html} "
        comment = soup.new_string(comment_text, Comment)
        macro.replace_with(comment)
    return soup
```

**Before:**
```xml
<p>Text before</p>
<ac:structured-macro ac:name="info">
  <ac:rich-text-body><p>Info content</p></ac:rich-text-body>
</ac:structured-macro>
<p>Text after</p>
```

**After preservation:**
```html
<p>Text before</p>
<!-- CONFLUENCE_MACRO: <ac:structured-macro ac:name="info"><ac:rich-text-body><p>Info content</p></ac:rich-text-body></ac:structured-macro> -->
<p>Text after</p>
```

#### After Conversion (restore)

```python
def restore_from_comments(self, html: str) -> str:
    soup = BeautifulSoup(html, 'lxml')
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if 'CONFLUENCE_MACRO:' in str(comment):
            macro_html = str(comment).split('CONFLUENCE_MACRO:', 1)[1].strip()
            macro_soup = BeautifulSoup(macro_html, 'lxml')
            macro_element = macro_soup.find(lambda tag: tag.name.startswith('ac:'))
            if macro_element:
                comment.replace_with(macro_element)
    return str(soup)
```

### Comment Format

```
<!-- CONFLUENCE_MACRO: <ac:structured-macro ...>...</ac:structured-macro> -->
```

The format is:
1. HTML comment opening: `<!--`
2. Space and marker: ` CONFLUENCE_MACRO: `
3. Complete macro XHTML (all attributes and children)
4. Space and comment closing: ` -->`

## Consequences

### Positive

1. **Lossless roundtrip**: Macros survive Markdown conversion exactly:
   ```
   XHTML -> preserve -> Pandoc -> Markdown -> Pandoc -> restore -> XHTML
   ```

2. **Visible in Markdown**: Users can see where macros are (as comments)

3. **Safe modification**: Users can edit text around macros without breaking them

4. **Macro types preserved**: All macro types (info, code, toc, etc.) handled uniformly

5. **Attributes preserved**: Macro parameters like language, title are kept intact

### Negative

1. **Comments in Markdown**: Output markdown contains HTML comments (may be visible in some renderers)

2. **Large comments**: Complex macros create large comment blocks

3. **Pandoc dependency**: Assumes Pandoc preserves HTML comments (it does, but version-dependent)

4. **Manual editing risk**: Users might accidentally modify comment content

### Trade-offs Made

- Chose preservation over conversion (no information loss)
- Chose visibility over hiding (users see where macros are)
- Accepted comment clutter for roundtrip fidelity

## Alternatives Considered

### YAML front matter

```markdown
---
macros:
  - position: 42
    content: "<ac:structured-macro...>"
---

Regular markdown content here...
```

Rejected because:
- Position tracking is fragile
- Doesn't handle inline macros well
- Complex merge scenarios

### Custom Markdown extensions

```markdown
:::confluence-macro info
Important information here.
:::
```

Rejected because:
- Lossy (macro parameters lost)
- Not all macros have text content
- Would need custom parser

### Placeholder tokens

```markdown
Text before
[MACRO_001]
Text after
```

With separate macro storage file.

Rejected because:
- Requires managing separate files
- Merge conflicts harder to resolve
- Not self-contained

## Warning Generation

The `MacroPreserver.get_macro_types()` method provides data for user warnings:

```python
macro_types = preserver.get_macro_types(soup)
# {'ac:structured-macro': 3, 'ac:image': 1}

warnings = []
for macro_name, count in macro_types.items():
    warnings.append(f"Found {count} '{macro_name}' macro(s) - preserved as HTML comments")
```

This tells users what macros were found and that they're preserved.

## References

- `src/content_converter/macro_preserver.py` - Preservation implementation
- [Confluence Macros](https://confluence.atlassian.com/doc/macros-139387.html)
- [BeautifulSoup Comments](https://www.crummy.com/software/BeautifulSoup/bs4/doc/#comments-and-other-special-strings)
