"""Sample Confluence XHTML pages for testing.

These fixtures represent Confluence storage format (XHTML) content
with various elements including macros, tables, code blocks, etc.

XHTML format uses Confluence-specific namespaces:
- ac: namespace for Confluence macros
- ri: namespace for resource identifiers (images, attachments)
"""

# Simple page with headings, paragraphs, and lists
SAMPLE_PAGE_SIMPLE = """
<h1>Test Page</h1>
<p>This is a simple test page with basic formatting.</p>
<h2>Section 1</h2>
<p>Some content in section 1.</p>
<ul>
<li>Item 1</li>
<li>Item 2</li>
<li>Item 3</li>
</ul>
<h2>Section 2</h2>
<p>Some content in section 2.</p>
<ol>
<li>First</li>
<li>Second</li>
<li>Third</li>
</ol>
"""

# Page with Confluence macros (ac: namespace elements)
SAMPLE_PAGE_WITH_MACROS = """
<h1>Page with Macros</h1>
<p>This page contains Confluence macros that should be preserved.</p>
<h2>Info Panel</h2>
<ac:structured-macro ac:name="info" ac:schema-version="1">
<ac:rich-text-body>
<p>This is an informational panel created with a Confluence macro.</p>
</ac:rich-text-body>
</ac:structured-macro>
<h2>Code Block</h2>
<ac:structured-macro ac:name="code" ac:schema-version="1">
<ac:parameter ac:name="language">python</ac:parameter>
<ac:plain-text-body><![CDATA[def hello():
    print("Hello, World!")]]></ac:plain-text-body>
</ac:structured-macro>
<h2>Warning Panel</h2>
<ac:structured-macro ac:name="warning" ac:schema-version="1">
<ac:rich-text-body>
<p>This is a warning panel.</p>
</ac:rich-text-body>
</ac:structured-macro>
<p>Regular content after macro.</p>
"""

# Page with tables
SAMPLE_PAGE_WITH_TABLES = """
<h1>Page with Tables</h1>
<p>This page contains tables for testing conversion.</p>
<table>
<thead>
<tr>
<th>Header 1</th>
<th>Header 2</th>
<th>Header 3</th>
</tr>
</thead>
<tbody>
<tr>
<td>Row 1, Col 1</td>
<td>Row 1, Col 2</td>
<td>Row 1, Col 3</td>
</tr>
<tr>
<td>Row 2, Col 1</td>
<td>Row 2, Col 2</td>
<td>Row 2, Col 3</td>
</tr>
<tr>
<td>Row 3, Col 1</td>
<td>Row 3, Col 2</td>
<td>Row 3, Col 3</td>
</tr>
</tbody>
</table>
<p>Content after table.</p>
"""

# Page with code blocks (using pre/code tags)
SAMPLE_PAGE_WITH_CODE_BLOCKS = """
<h1>Page with Code Blocks</h1>
<p>This page contains code blocks for testing conversion.</p>
<h2>Python Code</h2>
<pre><code class="language-python">def fibonacci(n):
    if n &lt;= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(fibonacci(10))</code></pre>
<h2>JavaScript Code</h2>
<pre><code class="language-javascript">function greet(name) {
    console.log(`Hello, ${name}!`);
}

greet('World');</code></pre>
<p>Inline code example: <code>print("Hello")</code></p>
"""

# Page with images and attachments (URLs preserved, content not downloaded)
SAMPLE_PAGE_WITH_IMAGES = """
<h1>Page with Images</h1>
<p>This page contains images and attachments.</p>
<h2>Embedded Image</h2>
<p>
<ac:image ac:height="250">
<ri:attachment ri:filename="diagram.png"/>
</ac:image>
</p>
<h2>Image with Link</h2>
<p>
<a href="/wiki/download/attachments/123456/diagram.png">
<ac:image>
<ri:attachment ri:filename="diagram.png"/>
</ac:image>
</a>
</p>
<h2>Attachment Link</h2>
<p>Download the <a href="/wiki/download/attachments/123456/document.pdf">PDF document</a>.</p>
"""

# Complex page combining multiple elements
SAMPLE_PAGE_COMPLEX = """
<h1>Complex Test Page</h1>
<p>This page combines multiple Confluence elements.</p>
<ac:structured-macro ac:name="toc" ac:schema-version="1">
<ac:parameter ac:name="minLevel">2</ac:parameter>
<ac:parameter ac:name="maxLevel">3</ac:parameter>
</ac:structured-macro>
<h2>Introduction</h2>
<p>This section has <strong>bold text</strong> and <em>italic text</em>.</p>
<ul>
<li>Bullet point 1</li>
<li>Bullet point 2 with <code>inline code</code></li>
<li>Bullet point 3</li>
</ul>
<h2>Data Table</h2>
<table>
<thead>
<tr>
<th>Name</th>
<th>Value</th>
<th>Description</th>
</tr>
</thead>
<tbody>
<tr>
<td>Item A</td>
<td>100</td>
<td>First item</td>
</tr>
<tr>
<td>Item B</td>
<td>200</td>
<td>Second item</td>
</tr>
</tbody>
</table>
<h2>Code Example</h2>
<ac:structured-macro ac:name="code" ac:schema-version="1">
<ac:parameter ac:name="language">python</ac:parameter>
<ac:parameter ac:name="title">example.py</ac:parameter>
<ac:plain-text-body><![CDATA[# Example Python code
class Example:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello, {self.name}!"]]></ac:plain-text-body>
</ac:structured-macro>
<h2>Important Note</h2>
<ac:structured-macro ac:name="info" ac:schema-version="1">
<ac:rich-text-body>
<p>Remember to run tests before deployment!</p>
</ac:rich-text-body>
</ac:structured-macro>
"""
