"""File mapper library for bidirectional Confluence sync.

This package provides Python abstractions for mapping between Confluence page
hierarchies and local markdown files with YAML frontmatter, enabling offline
access, RAG tool integration, and local editing workflows.
"""

from .file_mapper import FileMapper
from .models import PageNode, LocalPage, SpaceConfig, SyncConfig
from .errors import (
    FileMapperError,
    FilesystemError,
    ConfigError,
    FrontmatterError,
    PageLimitExceededError,
)
from .config_loader import ConfigLoader
from .filesafe_converter import FilesafeConverter
from .frontmatter_handler import FrontmatterHandler
from .hierarchy_builder import HierarchyBuilder

__all__ = [
    'FileMapper',
    'PageNode',
    'LocalPage',
    'SpaceConfig',
    'SyncConfig',
    'FileMapperError',
    'FilesystemError',
    'ConfigError',
    'FrontmatterError',
    'PageLimitExceededError',
    'ConfigLoader',
    'FilesafeConverter',
    'FrontmatterHandler',
    'HierarchyBuilder',
]
