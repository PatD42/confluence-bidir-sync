# Architecture - CONF-SYNC-004

---

## Overview

CLI module providing the `confluence-sync` command. Thin orchestration layer over Epics 001-003.

**Tech Stack**:
- CLI Framework: Typer (type hints, auto-help, shell completion)
- Progress/Output: Rich library (spinners, progress bars, colored output)
- Config: PyYAML (already in project)

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                            src/cli/                              │
│                                                                  │
│  ┌─────────────┐   ┌──────────────┐   ┌────────────────┐        │
│  │   main.py   │──▶│ SyncCommand  │──▶│ ChangeDetector │        │
│  │  (Typer)    │   │              │   │                │        │
│  └─────────────┘   └──────┬───────┘   └────────────────┘        │
│                           │                                      │
│  ┌─────────────┐          │           ┌────────────────┐        │
│  │ config.py   │◀─────────┤           │  output.py     │        │
│  │ StateManager│          │           │  (Rich)        │        │
│  └─────────────┘          │           └────────────────┘        │
│                           │                                      │
└───────────────────────────┼──────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ file_mapper/  │   │git_integration│   │page_operations│
│   (Epic 002)  │   │  (Epic 003)   │   │  (Epic 001)   │
└───────────────┘   └───────────────┘   └───────────────┘
```

---

## Component Specifications

### main.py (Entry Point)

**Responsibility**: Define CLI commands and options via Typer

```python
import typer
from typing import Optional
from pathlib import Path

app = typer.Typer(help="Bidirectional sync between Confluence and local markdown")

@app.command()
def sync(
    file: Optional[Path] = typer.Argument(None, help="Sync single file"),
    force_push: bool = typer.Option(False, "--forcePush", help="Local → Confluence"),
    force_pull: bool = typer.Option(False, "--forcePull", help="Confluence → local"),
    dryrun: bool = typer.Option(False, "--dryrun", help="Preview changes"),
    verbose: int = typer.Option(0, "-v", "--verbose", count=True, help="Verbosity"),
    no_color: bool = typer.Option(False, "--no-color", help="Disable colors"),
):
    """Sync local markdown with Confluence pages."""
    ...

@app.command()
def init(
    space_path: str = typer.Argument(..., help="SPACE:path or SPACE:pageID"),
    local_path: Path = typer.Argument(..., help="Local directory"),
):
    """Initialize sync configuration."""
    ...

if __name__ == "__main__":
    app()
```

### SyncCommand

**Responsibility**: Orchestrate sync workflow

```python
class SyncCommand:
    def __init__(
        self,
        config: SyncConfig,
        state: StateManager,
        file_mapper: FileMapper,
        merge_orchestrator: MergeOrchestrator,
        output: OutputHandler,
    ):
        ...

    def execute(
        self,
        file: Optional[Path] = None,
        force_push: bool = False,
        force_pull: bool = False,
        dryrun: bool = False,
    ) -> int:
        """Execute sync and return exit code."""
        ...
```

### ChangeDetector

**Responsibility**: Detect changes using timestamp comparison

```python
class ChangeDetector:
    def __init__(self, last_synced: datetime):
        ...

    def detect(
        self,
        local_pages: List[LocalPage],
        remote_pages: List[PageNode],
    ) -> ChangeDetectionResult:
        """Classify pages into unchanged, push, pull, conflict."""
        ...

@dataclass
class ChangeDetectionResult:
    unchanged: List[str]      # page_ids
    to_push: List[LocalPage]  # mtime > last_synced
    to_pull: List[PageNode]   # last_modified > last_synced
    conflicts: List[str]      # both modified
```

### StateManager (config.py)

**Responsibility**: Load/save project sync state

```python
class StateManager:
    def __init__(self, state_path: Path = Path(".confluence-sync/state.yaml")):
        ...

    def load(self) -> SyncState:
        """Load state or return default."""
        ...

    def save(self, state: SyncState) -> None:
        """Save state to file."""
        ...

    def update_last_synced(self) -> None:
        """Update last_synced to now."""
        ...

@dataclass
class SyncState:
    last_synced: Optional[datetime] = None
```

### OutputHandler (output.py)

**Responsibility**: Console output with Rich library

```python
class OutputHandler:
    def __init__(self, verbose: int = 0, no_color: bool = False):
        ...

    def progress_bar(self, total: int, description: str) -> Progress:
        """Create progress bar for multi-page operations."""
        ...

    def spinner(self, message: str) -> Status:
        """Create spinner for single operations."""
        ...

    def success(self, message: str) -> None:
        """Print green success message."""
        ...

    def warning(self, message: str) -> None:
        """Print yellow warning message."""
        ...

    def error(self, message: str) -> None:
        """Print red error message."""
        ...

    def info(self, message: str) -> None:
        """Print info (only if verbose >= 1)."""
        ...

    def debug(self, message: str) -> None:
        """Print debug (only if verbose >= 2)."""
        ...
```

---

## File Organization

```
src/
├── cli/                        # NEW MODULE (Epic 004)
│   ├── __init__.py
│   ├── main.py                 # Typer app, CLI entry point
│   ├── sync_command.py         # SyncCommand orchestration
│   ├── init_command.py         # InitCommand for --init
│   ├── change_detector.py      # Timestamp-based change detection
│   ├── config.py               # StateManager, config loading
│   ├── output.py               # OutputHandler (Rich)
│   ├── models.py               # CLI-specific data classes
│   └── errors.py               # CLI-specific exceptions
├── file_mapper/                # Epic 002
├── git_integration/            # Epic 003
├── page_operations/            # Epic 001
├── confluence_client/          # Epic 001
└── content_converter/          # Epic 001
```

---

## Data Models

```python
# src/cli/models.py

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from enum import Enum, auto

class ExitCode(Enum):
    SUCCESS = 0
    GENERAL_ERROR = 1
    CONFLICTS = 2
    AUTH_FAILURE = 3
    NETWORK_ERROR = 4

@dataclass
class SyncState:
    """Project-level sync state."""
    last_synced: Optional[datetime] = None

@dataclass
class ChangeDetectionResult:
    """Result of change detection."""
    unchanged: List[str] = field(default_factory=list)
    to_push: List[str] = field(default_factory=list)
    to_pull: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)

@dataclass
class SyncSummary:
    """Summary of sync operation for output."""
    pushed: int = 0
    pulled: int = 0
    conflicts_resolved: int = 0
    skipped: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)
```

---

## Sequence Diagrams

### Sequence 1: Normal Sync

```
User                CLI                  ChangeDetector     MergeOrchestrator
  │                  │                        │                    │
  │ confluence-sync  │                        │                    │
  │─────────────────▶│                        │                    │
  │                  │                        │                    │
  │                  │ load config/state      │                    │
  │                  │────────────────────────│                    │
  │                  │                        │                    │
  │                  │ detect(local, remote)  │                    │
  │                  │───────────────────────▶│                    │
  │                  │     ChangeResult       │                    │
  │                  │◀───────────────────────│                    │
  │                  │                        │                    │
  │                  │                   sync(pages)               │
  │                  │────────────────────────────────────────────▶│
  │                  │                   SyncResult                │
  │                  │◀────────────────────────────────────────────│
  │                  │                        │                    │
  │                  │ update state.yaml      │                    │
  │                  │────────────────────────│                    │
  │                  │                        │                    │
  │   exit code 0    │                        │                    │
  │◀─────────────────│                        │                    │
```

### Sequence 2: Dry Run

```
User                CLI                  ChangeDetector     OutputHandler
  │                  │                        │                   │
  │ --dryrun         │                        │                   │
  │─────────────────▶│                        │                   │
  │                  │                        │                   │
  │                  │ detect(local, remote)  │                   │
  │                  │───────────────────────▶│                   │
  │                  │     ChangeResult       │                   │
  │                  │◀───────────────────────│                   │
  │                  │                        │                   │
  │                  │                        │  display_dryrun() │
  │                  │────────────────────────────────────────────▶│
  │                  │                        │                   │
  │   (no changes)   │                        │                   │
  │◀─────────────────│                        │                   │
```

---

## Error Handling

### CLI Exit Codes

| Code | Constant | Scenarios |
|------|----------|-----------|
| 0 | SUCCESS | Sync completed |
| 1 | GENERAL_ERROR | Config error, page not found, Pandoc missing |
| 2 | CONFLICTS | Unresolved merge conflicts |
| 3 | AUTH_FAILURE | Invalid credentials |
| 4 | NETWORK_ERROR | API unreachable, rate limit exhausted |

### Exception Translation

```python
def translate_exception(e: Exception) -> int:
    """Translate exception to exit code."""
    if isinstance(e, InvalidCredentialsError):
        return ExitCode.AUTH_FAILURE.value
    elif isinstance(e, (APIUnreachableError, APIAccessError)):
        return ExitCode.NETWORK_ERROR.value
    elif isinstance(e, MergeConflictError):
        return ExitCode.CONFLICTS.value
    else:
        return ExitCode.GENERAL_ERROR.value
```

---

## Configuration Files

### .confluence-sync/config.yaml

```yaml
version: 1
spaces:
  - space_key: "CONFSYNCTEST"
    parent_page_id: "12345"  # null for root
    local_path: "./docs/product/"
    exclude:
      - page_id: "67890"
```

### .confluence-sync/state.yaml

```yaml
last_synced: "2026-01-30T10:00:00Z"
```

---

## Performance Targets

| Operation | Target |
|-----------|--------|
| CLI startup | <500ms |
| Change detection (100 pages) | <2s |
| Progress bar update | 60 fps |
| State file write | <50ms |
