"""Git integration for bidirectional Confluence synchronization.

This package provides conflict detection, three-way merge resolution, and
synchronization capabilities for Confluence pages with local git repositories.
"""

from src.git_integration.conflict_detector import ConflictDetector
from src.git_integration.errors import (
    CacheError,
    GitRepositoryError,
    MergeConflictError,
    MergeToolError,
)
from src.git_integration.git_repository import GitRepository
from src.git_integration.merge_orchestrator import MergeOrchestrator
from src.git_integration.merge_tool import MergeTool
from src.git_integration.models import (
    CachedPage,
    ConflictDetectionResult,
    ConflictInfo,
    LocalPage,
    MergeResult,
    MergeStrategy,
    MergeToolResult,
    SyncResult,
    ThreeWayMergeInputs,
)
from src.git_integration.xhtml_cache import XHTMLCache

__all__ = [
    # Errors
    'CacheError',
    'GitRepositoryError',
    'MergeConflictError',
    'MergeToolError',
    # Components
    'GitRepository',
    'XHTMLCache',
    'ConflictDetector',
    'MergeOrchestrator',
    'MergeTool',
    # Models
    'CachedPage',
    'ConflictDetectionResult',
    'ConflictInfo',
    'LocalPage',
    'MergeResult',
    'MergeStrategy',
    'MergeToolResult',
    'SyncResult',
    'ThreeWayMergeInputs',
]
