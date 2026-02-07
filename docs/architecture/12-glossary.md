# Architecture - Glossary

---

## Domain Terms

| Term | Definition |
|------|------------|
| **Confluence Cloud** | Atlassian's SaaS version of Confluence wiki/documentation platform |
| **Confluence Data Center** | Self-hosted Confluence (not supported by this library) |
| **Space** | Top-level container for Confluence pages (identified by space key, e.g., "TEAM") |
| **Page** | Single document in Confluence with title, content, and metadata |
| **Page ID** | Unique numeric identifier for a Confluence page |
| **Space Key** | Short alphanumeric code identifying a Confluence space |
| **Storage Format** | Confluence's internal XHTML representation of page content |
| **ADF** | Atlassian Document Format - JSON-based content format with localId attributes |
| **Macro** | Confluence extension providing rich functionality (code blocks, TOC, etc.) |
| **ac: namespace** | XML namespace prefix for Confluence macros and extensions |
| **ri: namespace** | XML namespace prefix for Confluence resource identifiers |
| **localId** | ADF-assigned stable identifier for nodes (used for surgical targeting) |
| **Version Number** | Incremented integer tracking page revisions (used for conflict detection) |
| **Baseline** | Last successfully synced content - source of truth for 3-way merge |
| **hardBreak** | ADF node type representing line break within a block |

## Technical Terms

| Term | Definition |
|------|------------|
| **XHTML** | Extensible HTML - Confluence's content format combining HTML with XML namespaces |
| **Markdown** | Lightweight markup language for formatting text |
| **Pandoc** | Universal document converter (used for markdown→XHTML conversion) |
| **markdownify** | Python library for HTML→markdown conversion with clean pipe tables |
| **merge3** | Python library implementing 3-way merge algorithm (diff3) |
| **BeautifulSoup** | Python library for parsing HTML/XML documents |
| **lxml** | Python XML/HTML processing library (used as BeautifulSoup parser backend) |
| **atlassian-python-api** | Python library wrapping Atlassian REST APIs |
| **python-dotenv** | Python library for loading environment variables from .env files |
| **Pipe Table** | Markdown table format using `|` delimiters (e.g., `| col1 | col2 |`) |

## Architectural Terms

| Term | Definition |
|------|------------|
| **Surgical Update** | Modifying specific content elements without affecting surrounding content |
| **Optimistic Locking** | Conflict detection using version numbers instead of locks |
| **Fail-Fast** | Design pattern that fails immediately on non-recoverable errors |
| **Exponential Backoff** | Retry strategy with exponentially increasing wait times |
| **PageSnapshot** | Complete page state including XHTML, markdown, version, and metadata |
| **SurgicalOperation** | Discrete change instruction (update text, delete block, etc.) |
| **ContentBlock** | Parsed content unit (heading, paragraph, table, macro, etc.) |
| **3-Way Merge** | Merge algorithm using common ancestor (baseline), local, and remote versions |
| **Baseline-Centric Diffing** | Comparing baseline vs. new content (same format) to avoid parser mismatch |
| **Cell-Level Merge** | Table merge at individual cell granularity, not row-level |
| **TableRegion** | Parsed markdown table with position, header, and data rows |
| **AdfDocument** | Parsed ADF content as typed Python object model |
| **AdfEditor** | Surgical editor targeting ADF nodes by localId |
| **DiffAnalyzer** | Generates surgical operations by comparing content blocks |

## API Terms

| Term | Definition |
|------|------------|
| **REST API v2** | Current Confluence Cloud API (used by this library) |
| **expand** | Confluence API parameter to include additional data in responses |
| **body.storage** | API field containing page content in storage format (XHTML) |
| **429** | HTTP status code for "Too Many Requests" (rate limiting) |
| **409** | HTTP status code for "Conflict" (version mismatch) |

## Exception Types

| Exception | Meaning |
|-----------|---------|
| **ConfluenceError** | Base exception for all Confluence-related errors |
| **InvalidCredentialsError** | API token or email is incorrect (HTTP 401) |
| **PageNotFoundError** | Requested page does not exist (HTTP 404) |
| **PageAlreadyExistsError** | Duplicate title when creating page |
| **VersionConflictError** | Page was modified since last fetch (HTTP 409) |
| **APIUnreachableError** | Network error or timeout connecting to Confluence |
| **APIAccessError** | Other API errors (permissions, rate limits exhausted, etc.) |
| **ConversionError** | Pandoc conversion failed |

## Operation Types

| Operation | Description |
|-----------|-------------|
| **UPDATE_TEXT** | Replace text content within an element |
| **DELETE_BLOCK** | Remove a block element (paragraph, heading, list item) |
| **INSERT_BLOCK** | Add a new block element |
| **CHANGE_HEADING_LEVEL** | Change heading tag (h1→h2, etc.) |
| **TABLE_INSERT_ROW** | Add a row to a table |
| **TABLE_DELETE_ROW** | Remove a row from a table |
| **TABLE_UPDATE_CELL** | Update content of a specific table cell |

## Block Types

| Block Type | Description |
|------------|-------------|
| **HEADING** | h1-h6 elements |
| **PARAGRAPH** | p elements |
| **TABLE** | table elements |
| **LIST** | ul/ol elements |
| **CODE** | pre/code blocks |
| **MACRO** | ac: namespace elements |
| **OTHER** | Text nodes, other elements |

## Acronyms

| Acronym | Expansion |
|---------|-----------|
| **ADF** | Atlassian Document Format |
| **ADR** | Architecture Decision Record |
| **API** | Application Programming Interface |
| **CLI** | Command-Line Interface |
| **CRUD** | Create, Read, Update, Delete |
| **CVE** | Common Vulnerabilities and Exposures |
| **E2E** | End-to-End (testing) |
| **HTTP** | Hypertext Transfer Protocol |
| **HTTPS** | HTTP Secure (TLS encrypted) |
| **JSON** | JavaScript Object Notation |
| **REST** | Representational State Transfer |
| **SaaS** | Software as a Service |
| **TLS** | Transport Layer Security |
| **XML** | Extensible Markup Language |

---
