"""Command-line interface for bidirectional Confluence sync.

This package provides the `confluence-sync` CLI tool that orchestrates
bidirectional synchronization between local Markdown files and Confluence pages.
It integrates file mapping, conflict detection, and Confluence API operations
into a seamless command-line workflow with progress indication and error handling.
"""

from .sync_command import SyncCommand
from .init_command import InitCommand
from .models import ExitCode, SyncState, ChangeDetectionResult, SyncSummary
from .errors import (
    CLIError,
    ConfigNotFoundError,
    InitError,
    StateError,
    StateFilesystemError,
)

__all__ = [
    'SyncCommand',
    'InitCommand',
    'ExitCode',
    'SyncState',
    'ChangeDetectionResult',
    'SyncSummary',
    'CLIError',
    'ConfigNotFoundError',
    'InitError',
    'StateError',
    'StateFilesystemError',
]
