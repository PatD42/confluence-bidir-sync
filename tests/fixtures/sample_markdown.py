"""Sample markdown content for testing.

These fixtures represent markdown content used for:
- Testing markdown to XHTML conversion
- Testing round-trip conversion (XHTML → markdown → XHTML)
- Creating test pages on Confluence

Safe subset supported: headings, lists, tables, code blocks, links, images
"""

# Simple markdown with headings, paragraphs, and lists
SAMPLE_MARKDOWN_SIMPLE = """# Test Page

This is a simple test page with basic formatting.

## Section 1

Some content in section 1.

- Item 1
- Item 2
- Item 3

## Section 2

Some content in section 2.

1. First
2. Second
3. Third
"""

# Markdown with tables
SAMPLE_MARKDOWN_WITH_TABLES = """# Page with Tables

This page contains tables for testing conversion.

| Header 1 | Header 2 | Header 3 |
|----------|----------|----------|
| Row 1, Col 1 | Row 1, Col 2 | Row 1, Col 3 |
| Row 2, Col 1 | Row 2, Col 2 | Row 2, Col 3 |
| Row 3, Col 1 | Row 3, Col 2 | Row 3, Col 3 |

Content after table.

## Data Table

| Name | Value | Description |
|------|-------|-------------|
| Item A | 100 | First item |
| Item B | 200 | Second item |
| Item C | 300 | Third item |
"""

# Markdown with code blocks
SAMPLE_MARKDOWN_WITH_CODE_BLOCKS = """# Page with Code Blocks

This page contains code blocks for testing conversion.

## Python Code

```python
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(fibonacci(10))
```

## JavaScript Code

```javascript
function greet(name) {
    console.log(`Hello, ${name}!`);
}

greet('World');
```

Inline code example: `print("Hello")`

## Shell Commands

```bash
#!/bin/bash
echo "Running tests..."
pytest tests/ -v
```
"""

# Markdown with images and links
SAMPLE_MARKDOWN_WITH_IMAGES = """# Page with Images

This page contains images and links.

## Embedded Image

![Diagram](diagram.png)

## Image with Link

[![Diagram](diagram.png)](/wiki/download/attachments/123456/diagram.png)

## External Links

- [Confluence Documentation](https://confluence.atlassian.com/doc/)
- [Python Documentation](https://docs.python.org/)
- [Markdown Guide](https://www.markdownguide.org/)

## Internal Links

See [Section 2](#section-2) for more details.

## Section 2

Content referenced above.
"""

# Complex markdown combining multiple elements
SAMPLE_MARKDOWN_COMPLEX = """# Complex Test Page

This page combines multiple markdown elements.

## Introduction

This section has **bold text** and *italic text*.

- Bullet point 1
- Bullet point 2 with `inline code`
- Bullet point 3
  - Nested item 1
  - Nested item 2

## Data Table

| Name | Value | Description |
|------|-------|-------------|
| Item A | 100 | First item |
| Item B | 200 | Second item |

## Code Example

```python
# Example Python code
class Example:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello, {self.name}!"

# Create instance
example = Example("World")
print(example.greet())
```

## Blockquote

> This is a blockquote with multiple lines.
> It can span several lines and contain **formatting**.
>
> - Even lists
> - Inside quotes

## Horizontal Rule

Content above the rule.

---

Content below the rule.

## Mixed Formatting

This paragraph contains **bold**, *italic*, ***bold italic***, and `code` formatting.
It also has a [link to Confluence](https://confluence.atlassian.com/) and ![an image](test.png).
"""

# Markdown with preserved HTML comments (for macro restoration)
SAMPLE_MARKDOWN_WITH_PRESERVED_MACROS = """# Page with Preserved Macros

This page contains HTML comments that represent preserved Confluence macros.

## Info Panel

<!-- CONFLUENCE_MACRO: info -->
This is an informational panel created with a Confluence macro.
<!-- /CONFLUENCE_MACRO: info -->

## Code Block

Regular markdown code:

```python
def hello():
    print("Hello, World!")
```

## Warning Panel

<!-- CONFLUENCE_MACRO: warning -->
This is a warning panel.
<!-- /CONFLUENCE_MACRO: warning -->

Regular content after macro.
"""

# Minimal markdown for testing edge cases
SAMPLE_MARKDOWN_MINIMAL = """# Minimal Page

Single paragraph.
"""

# Empty markdown (edge case)
SAMPLE_MARKDOWN_EMPTY = ""

# Markdown with special characters that need escaping
SAMPLE_MARKDOWN_WITH_SPECIAL_CHARS = """# Special Characters

## HTML Entities

- Less than: <
- Greater than: >
- Ampersand: &
- Quote: "
- Apostrophe: '

## Code with HTML

```html
<div class="container">
  <p>Hello, World!</p>
</div>
```

## Inline HTML entities

Use `&lt;` for less than and `&gt;` for greater than.
"""
