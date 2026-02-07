# Architecture - Context & Scope

---

## System Context (C4 Level 1)

### Context Diagram

```mermaid
graph LR
    subgraph Users
        Human[Human User<br/>Developer/Tech Writer]
        Agent[Agentic AI<br/>LLM/RAG Tools]
    end

    subgraph "System Boundary"
        ConfSync[confluence-bidir-sync<br/>Python Library]
    end

    subgraph "External Systems"
        Confluence[Confluence Cloud<br/>REST API v2]
        Pandoc[Pandoc<br/>Document Converter]
        LocalFS[Local File System<br/>Markdown Files]
    end

    Human -->|Uses API| ConfSync
    Agent -->|Uses API| ConfSync
    ConfSync -->|HTTPS REST| Confluence
    ConfSync -->|subprocess| Pandoc
    ConfSync -.->|Future: Epic 02| LocalFS

    classDef user fill:#f9f,stroke:#333,stroke-width:2px
    classDef system fill:#9cf,stroke:#333,stroke-width:3px
    classDef external fill:#fcf,stroke:#333,stroke-width:2px

    class Human,Agent user
    class ConfSync system
    class Confluence,Pandoc,LocalFS external
```

### External Interfaces

| External Entity | Type | Relationship | Protocol/Interface |
|----------------|------|--------------|-------------------|
| **Confluence Cloud** | External Service | Bidirectional CRUD | HTTPS REST API v2 |
| **Pandoc** | Local Tool | Format conversion | subprocess stdin/stdout |
| **Local File System** | Storage | Read/write markdown (Epic 02) | Python file I/O |
| **Human User** | Actor | Invokes library functions | Python API |
| **Agentic AI** | Actor | Programmatic page manipulation | Python API |

## Business Context

### Input/Output

**Inputs**:
- Confluence page ID or space/title path
- Markdown content for create/update operations
- API credentials (URL, email, token) from `.env`
- Surgical operations (UPDATE_TEXT, DELETE_BLOCK, etc.)

**Outputs**:
- `PageSnapshot`: XHTML + markdown + version + metadata
- `UpdateResult`: Success status, new version, error details
- `CreateResult`: Page ID, version, success status
- Typed exceptions with actionable error messages

### Primary Use Cases

| Use Case | Actor | Flow |
|----------|-------|------|
| **Fetch as Markdown** | Agent/User | Request page → API fetch → XHTML → Pandoc → Markdown |
| **Surgical Update** | Agent | Provide operations → Apply to XHTML → Upload → Verify |
| **Create Page** | Agent/User | Markdown → XHTML → API create → Return page ID |
| **Detect Conflicts** | System | Compare versions → Fail if mismatch → Clear error |

## Technical Context

| Channel | Protocol | Data Format | Security |
|---------|----------|-------------|----------|
| Confluence API | HTTPS REST | JSON (XHTML in body.storage) | API Token + TLS 1.3 |
| Pandoc | subprocess | stdin/stdout (text) | Local only, no shell |
| Credentials | Environment | .env file | Never logged |

### Authentication Flow

```
.env file
    │
    ▼
Authenticator.load()
    │
    ▼
Credentials(url, email, token)
    │
    ▼
atlassian-python-api Confluence client
    │
    ▼
HTTP Basic Auth over HTTPS
```

---
