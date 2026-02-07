"""ADF document fixtures for integration and E2E tests.

Provides reusable ADF document structures for testing ADF-related functionality
including surgical updates, hardBreak handling, table operations, and macro preservation.
"""

from typing import Dict, Any, List


# Type alias for ADF documents
AdfDocument = Dict[str, Any]
AdfNode = Dict[str, Any]


def create_adf_doc(content: List[AdfNode]) -> AdfDocument:
    """Create a basic ADF document with given content nodes."""
    return {
        "type": "doc",
        "version": 1,
        "content": content
    }


def create_paragraph(text: str, local_id: str = None) -> AdfNode:
    """Create an ADF paragraph node with optional localId."""
    node = {
        "type": "paragraph",
        "content": [{"type": "text", "text": text}]
    }
    if local_id:
        node["attrs"] = {"localId": local_id}
    return node


def create_paragraph_with_hardbreak(lines: List[str], local_id: str = None) -> AdfNode:
    """Create a paragraph with multiple lines separated by hardBreak nodes."""
    content = []
    for i, line in enumerate(lines):
        if i > 0:
            content.append({"type": "hardBreak"})
        content.append({"type": "text", "text": line})

    node = {
        "type": "paragraph",
        "content": content
    }
    if local_id:
        node["attrs"] = {"localId": local_id}
    return node


def create_heading(text: str, level: int = 1, local_id: str = None) -> AdfNode:
    """Create an ADF heading node."""
    node = {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}]
    }
    if local_id:
        node["attrs"]["localId"] = local_id
    return node


def create_table_cell(content: str, local_id: str = None) -> AdfNode:
    """Create a table cell with text content."""
    cell = {
        "type": "tableCell",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": content}]
            }
        ]
    }
    if local_id:
        cell["attrs"] = {"localId": local_id}
    return cell


def create_table_header(content: str, local_id: str = None) -> AdfNode:
    """Create a table header cell with text content."""
    cell = {
        "type": "tableHeader",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": content}]
            }
        ]
    }
    if local_id:
        cell["attrs"] = {"localId": local_id}
    return cell


def create_table_row(cells: List[AdfNode], local_id: str = None) -> AdfNode:
    """Create a table row from cells."""
    row = {
        "type": "tableRow",
        "content": cells
    }
    if local_id:
        row["attrs"] = {"localId": local_id}
    return row


def create_table(rows: List[AdfNode], local_id: str = None) -> AdfNode:
    """Create a table from rows."""
    table = {
        "type": "table",
        "content": rows
    }
    if local_id:
        table["attrs"] = {"localId": local_id}
    return table


def create_macro(macro_name: str, local_id: str = None, parameters: Dict[str, str] = None) -> AdfNode:
    """Create an ADF extension/macro node."""
    macro = {
        "type": "extension",
        "attrs": {
            "extensionType": "com.atlassian.confluence.macro.core",
            "extensionKey": macro_name,
        }
    }
    if local_id:
        macro["attrs"]["localId"] = local_id
    if parameters:
        macro["attrs"]["parameters"] = {
            "macroParams": parameters
        }
    return macro


# =============================================================================
# Pre-built ADF Document Fixtures
# =============================================================================

# Document with hardBreak nodes for line break testing
ADF_WITH_HARDBREAK: AdfDocument = create_adf_doc([
    create_heading("Test Document", level=1, local_id="heading-1"),
    create_paragraph_with_hardbreak(
        ["Line 1", "Line 2", "Line 3"],
        local_id="para-with-breaks"
    ),
    create_paragraph("Normal paragraph without breaks.", local_id="para-normal")
])


# Document with a simple table for table operation testing
ADF_WITH_TABLE: AdfDocument = create_adf_doc([
    create_heading("Table Test", level=1, local_id="heading-1"),
    create_table([
        create_table_row([
            create_table_header("Column A", local_id="header-a"),
            create_table_header("Column B", local_id="header-b"),
        ], local_id="header-row"),
        create_table_row([
            create_table_cell("Cell A1", local_id="cell-a1"),
            create_table_cell("Cell B1", local_id="cell-b1"),
        ], local_id="row-1"),
        create_table_row([
            create_table_cell("Cell A2", local_id="cell-a2"),
            create_table_cell("Cell B2", local_id="cell-b2"),
        ], local_id="row-2"),
    ], local_id="table-1"),
    create_paragraph("Text after table.", local_id="para-after-table")
])


# Document with macros for macro preservation testing
ADF_WITH_MACRO: AdfDocument = create_adf_doc([
    create_heading("Macro Test Page", level=1, local_id="heading-1"),
    create_macro("toc", local_id="macro-toc"),
    create_paragraph("Text before code block.", local_id="para-before-code"),
    create_macro("code", local_id="macro-code", parameters={
        "language": "python",
        "title": "Example Code"
    }),
    create_paragraph("Text after code block.", local_id="para-after-code"),
    create_macro("info", local_id="macro-info"),
])


# Complex document with tables, macros, and hardBreaks
ADF_COMPLEX: AdfDocument = create_adf_doc([
    create_heading("Complex Test Document", level=1, local_id="heading-main"),
    create_macro("toc", local_id="toc-macro"),
    create_heading("Section 1", level=2, local_id="heading-s1"),
    create_paragraph_with_hardbreak(
        ["Multi-line content", "with several", "line breaks"],
        local_id="para-multiline"
    ),
    create_heading("Section 2: Table", level=2, local_id="heading-s2"),
    create_table([
        create_table_row([
            create_table_header("Feature", local_id="th-feature"),
            create_table_header("Status", local_id="th-status"),
        ], local_id="table-header-row"),
        create_table_row([
            create_table_cell("ADF Support", local_id="td-feature-1"),
            create_table_cell("Complete", local_id="td-status-1"),
        ], local_id="table-row-1"),
        create_table_row([
            create_table_cell("Table Merge", local_id="td-feature-2"),
            create_table_cell("In Progress", local_id="td-status-2"),
        ], local_id="table-row-2"),
    ], local_id="status-table"),
    create_heading("Section 3: Notes", level=2, local_id="heading-s3"),
    create_macro("warning", local_id="warning-macro"),
    create_paragraph("Final notes paragraph.", local_id="para-final"),
])


# Document for version conflict testing (minimal)
ADF_MINIMAL: AdfDocument = create_adf_doc([
    create_paragraph("Original content", local_id="para-1")
])


# Document with table containing multi-line cells
ADF_TABLE_WITH_MULTILINE_CELLS: AdfDocument = create_adf_doc([
    create_heading("Table with Multi-line Cells", level=1, local_id="heading-1"),
    create_table([
        create_table_row([
            create_table_header("Feature", local_id="th-feature"),
            create_table_header("Description", local_id="th-desc"),
        ], local_id="header-row"),
        create_table_row([
            {
                "type": "tableCell",
                "attrs": {"localId": "cell-login"},
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Login"},
                            {"type": "hardBreak"},
                            {"type": "text", "text": "Authentication"}
                        ]
                    }
                ]
            },
            {
                "type": "tableCell",
                "attrs": {"localId": "cell-login-desc"},
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Users can"},
                            {"type": "hardBreak"},
                            {"type": "text", "text": "authenticate"},
                            {"type": "hardBreak"},
                            {"type": "text", "text": "securely"}
                        ]
                    }
                ]
            }
        ], local_id="row-1"),
    ], local_id="multiline-table"),
])


# =============================================================================
# XHTML Content Fixtures (for conversion testing)
# =============================================================================

# XHTML with <p> tags in table cells (Confluence storage format)
XHTML_TABLE_WITH_P_TAGS = """
<table>
    <tr>
        <th>Feature</th>
        <th>Description</th>
    </tr>
    <tr>
        <td><p>Login</p><p>Authentication</p></td>
        <td><p>Users can</p><p>authenticate</p><p>securely</p></td>
    </tr>
</table>
"""

# Expected markdown with <br> tags after conversion
MARKDOWN_TABLE_WITH_BR_TAGS = """| Feature | Description |
|---------|-------------|
| Login<br>Authentication | Users can<br>authenticate<br>securely |
"""

# XHTML with macros
XHTML_WITH_MACROS = """
<h1>Macro Test</h1>
<ac:structured-macro ac:name="toc"/>
<p>Text with <ac:structured-macro ac:name="status"><ac:parameter ac:name="color">Green</ac:parameter></ac:structured-macro> inline.</p>
<ac:structured-macro ac:name="code">
    <ac:parameter ac:name="language">python</ac:parameter>
    <ac:plain-text-body><![CDATA[print("hello")]]></ac:plain-text-body>
</ac:structured-macro>
"""


# =============================================================================
# Conflict Test Fixtures
# =============================================================================

# Base content for conflict testing
CONFLICT_BASE_MARKDOWN = """| Col1 | Col2 |
|------|------|
| A | B |
| C | D |
"""

# Local edit (cell A changed)
CONFLICT_LOCAL_MARKDOWN = """| Col1 | Col2 |
|------|------|
| A-local | B |
| C | D |
"""

# Remote edit (same cell A changed differently)
CONFLICT_REMOTE_MARKDOWN = """| Col1 | Col2 |
|------|------|
| A-remote | B |
| C | D |
"""

# Local and remote edit different cells (should auto-merge)
CONFLICT_LOCAL_CELL_A_MARKDOWN = """| Col1 | Col2 |
|------|------|
| A-local | B |
| C | D |
"""

CONFLICT_REMOTE_CELL_B_MARKDOWN = """| Col1 | Col2 |
|------|------|
| A | B-remote |
| C | D |
"""

# Expected merge result when different cells edited
CONFLICT_MERGED_NO_CONFLICT = """| Col1 | Col2 |
|------|------|
| A-local | B-remote |
| C | D |
"""


# =============================================================================
# Utility Functions for Tests
# =============================================================================

def get_node_by_local_id(doc: AdfDocument, local_id: str) -> AdfNode:
    """Find a node in an ADF document by its localId."""
    def search(node: AdfNode) -> AdfNode:
        if isinstance(node, dict):
            attrs = node.get("attrs", {})
            if attrs.get("localId") == local_id:
                return node
            for child in node.get("content", []):
                result = search(child)
                if result:
                    return result
        return None

    for content_node in doc.get("content", []):
        result = search(content_node)
        if result:
            return result
    return None


def count_nodes_by_type(doc: AdfDocument, node_type: str) -> int:
    """Count nodes of a specific type in an ADF document."""
    count = 0

    def traverse(node: AdfNode):
        nonlocal count
        if isinstance(node, dict):
            if node.get("type") == node_type:
                count += 1
            for child in node.get("content", []):
                traverse(child)

    for content_node in doc.get("content", []):
        traverse(content_node)
    return count


def extract_text_content(doc: AdfDocument) -> str:
    """Extract all text content from an ADF document."""
    texts = []

    def traverse(node: AdfNode):
        if isinstance(node, dict):
            if node.get("type") == "text":
                texts.append(node.get("text", ""))
            for child in node.get("content", []):
                traverse(child)

    for content_node in doc.get("content", []):
        traverse(content_node)
    return " ".join(texts)
