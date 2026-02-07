"""Test fixtures for CLI module.

Provides test fixtures for CLI operations including:
- Sample SyncState objects
- Sample ChangeDetectionResult objects
- Sample SyncSummary objects
- Sample state.yaml content
- Helper functions for timestamp generation
- Mock CLI argument structures

These fixtures are used by unit, integration, and E2E tests for the CLI module.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from src.cli.models import (
    SyncState,
    ChangeDetectionResult,
    SyncSummary,
    ExitCode,
)


# ==============================================================================
# Sample SyncState Objects
# ==============================================================================

def get_fresh_sync_state() -> SyncState:
    """Create a fresh sync state (never synced before).

    Returns:
        SyncState with last_synced=None

    Example:
        >>> state = get_fresh_sync_state()
        >>> assert state.last_synced is None
    """
    return SyncState(last_synced=None)


def get_synced_state(timestamp: Optional[str] = None) -> SyncState:
    """Create a sync state with a last_synced timestamp.

    Args:
        timestamp: ISO 8601 timestamp string. If None, uses a default timestamp.

    Returns:
        SyncState with the specified or default timestamp

    Example:
        >>> state = get_synced_state("2026-01-30T10:00:00Z")
        >>> assert state.last_synced == "2026-01-30T10:00:00Z"
    """
    if timestamp is None:
        timestamp = "2026-01-30T10:00:00Z"
    return SyncState(last_synced=timestamp)


# ==============================================================================
# Sample ChangeDetectionResult Objects
# ==============================================================================

def get_empty_change_result() -> ChangeDetectionResult:
    """Create an empty change detection result (no changes).

    Returns:
        ChangeDetectionResult with all empty lists

    Example:
        >>> result = get_empty_change_result()
        >>> assert len(result.to_push) == 0
    """
    return ChangeDetectionResult()


def get_push_only_result(page_ids: list[str] = None) -> ChangeDetectionResult:
    """Create a change result with pages to push.

    Args:
        page_ids: List of page IDs to push. Defaults to ["123", "456"]

    Returns:
        ChangeDetectionResult with specified pages in to_push

    Example:
        >>> result = get_push_only_result(["123"])
        >>> assert result.to_push == ["123"]
    """
    if page_ids is None:
        page_ids = ["123", "456"]
    return ChangeDetectionResult(to_push=page_ids)


def get_pull_only_result(page_ids: list[str] = None) -> ChangeDetectionResult:
    """Create a change result with pages to pull.

    Args:
        page_ids: List of page IDs to pull. Defaults to ["789"]

    Returns:
        ChangeDetectionResult with specified pages in to_pull

    Example:
        >>> result = get_pull_only_result(["789"])
        >>> assert result.to_pull == ["789"]
    """
    if page_ids is None:
        page_ids = ["789"]
    return ChangeDetectionResult(to_pull=page_ids)


def get_conflict_result(conflict_ids: list[str] = None) -> ChangeDetectionResult:
    """Create a change result with conflicting pages.

    Args:
        conflict_ids: List of conflicting page IDs. Defaults to ["012"]

    Returns:
        ChangeDetectionResult with specified pages in conflicts

    Example:
        >>> result = get_conflict_result(["012"])
        >>> assert result.conflicts == ["012"]
    """
    if conflict_ids is None:
        conflict_ids = ["012"]
    return ChangeDetectionResult(conflicts=conflict_ids)


def get_mixed_change_result() -> ChangeDetectionResult:
    """Create a change result with all types of changes.

    Returns:
        ChangeDetectionResult with pages in all categories

    Example:
        >>> result = get_mixed_change_result()
        >>> assert len(result.to_push) == 2
        >>> assert len(result.to_pull) == 1
        >>> assert len(result.conflicts) == 1
    """
    return ChangeDetectionResult(
        unchanged=["111", "222"],
        to_push=["123", "456"],
        to_pull=["789"],
        conflicts=["012"],
    )


# ==============================================================================
# Sample SyncSummary Objects
# ==============================================================================

def get_empty_summary() -> SyncSummary:
    """Create an empty sync summary (no changes).

    Returns:
        SyncSummary with all counts at 0

    Example:
        >>> summary = get_empty_summary()
        >>> assert summary.pushed_count == 0
    """
    return SyncSummary()


def get_push_summary(count: int = 5) -> SyncSummary:
    """Create a sync summary with pushed pages.

    Args:
        count: Number of pages pushed. Defaults to 5

    Returns:
        SyncSummary with specified pushed_count

    Example:
        >>> summary = get_push_summary(5)
        >>> assert summary.pushed_count == 5
    """
    return SyncSummary(pushed_count=count)


def get_pull_summary(count: int = 3) -> SyncSummary:
    """Create a sync summary with pulled pages.

    Args:
        count: Number of pages pulled. Defaults to 3

    Returns:
        SyncSummary with specified pulled_count

    Example:
        >>> summary = get_pull_summary(3)
        >>> assert summary.pulled_count == 3
    """
    return SyncSummary(pulled_count=count)


def get_mixed_summary() -> SyncSummary:
    """Create a sync summary with all types of operations.

    Returns:
        SyncSummary with counts in all categories

    Example:
        >>> summary = get_mixed_summary()
        >>> assert summary.pushed_count == 5
        >>> assert summary.pulled_count == 3
    """
    return SyncSummary(
        pushed_count=5,
        pulled_count=3,
        conflict_count=1,
        unchanged_count=10,
    )


# ==============================================================================
# Sample State YAML Content
# ==============================================================================

SAMPLE_STATE_FRESH = """# Empty state - never synced
"""

SAMPLE_STATE_SYNCED = """last_synced: "2026-01-30T10:00:00Z"
"""

SAMPLE_STATE_INVALID_YAML = """last_synced: "2026-01-30T10:00:00Z
# Missing closing quote - invalid YAML
"""

SAMPLE_STATE_INVALID_TYPE = """last_synced: 12345
# Should be string, not number
"""


# ==============================================================================
# Timestamp Helper Functions
# ==============================================================================

def get_iso_timestamp(dt: Optional[datetime] = None) -> str:
    """Convert datetime to ISO 8601 timestamp string.

    Args:
        dt: Datetime object to convert. If None, uses current UTC time.

    Returns:
        ISO 8601 formatted timestamp string with Z suffix

    Example:
        >>> dt = datetime(2026, 1, 30, 10, 0, 0)
        >>> timestamp = get_iso_timestamp(dt)
        >>> assert timestamp == "2026-01-30T10:00:00Z"
    """
    if dt is None:
        dt = datetime.utcnow()
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_timestamp_ago(hours: int = 1) -> str:
    """Get ISO 8601 timestamp N hours ago from now.

    Args:
        hours: Number of hours in the past. Defaults to 1

    Returns:
        ISO 8601 formatted timestamp string

    Example:
        >>> timestamp = get_timestamp_ago(hours=2)
        >>> # Returns timestamp 2 hours ago
    """
    past_time = datetime.utcnow() - timedelta(hours=hours)
    return get_iso_timestamp(past_time)


def get_timestamp_future(hours: int = 1) -> str:
    """Get ISO 8601 timestamp N hours in the future from now.

    Args:
        hours: Number of hours in the future. Defaults to 1

    Returns:
        ISO 8601 formatted timestamp string

    Example:
        >>> timestamp = get_timestamp_future(hours=2)
        >>> # Returns timestamp 2 hours from now
    """
    future_time = datetime.utcnow() + timedelta(hours=hours)
    return get_iso_timestamp(future_time)


# ==============================================================================
# Mock CLI Arguments
# ==============================================================================

def get_default_cli_args() -> Dict[str, Any]:
    """Get default CLI arguments for sync command.

    Returns:
        Dictionary of default CLI arguments

    Example:
        >>> args = get_default_cli_args()
        >>> assert args['dry_run'] is False
        >>> assert args['force_push'] is False
    """
    return {
        'dry_run': False,
        'force_push': False,
        'force_pull': False,
        'verbose': 0,
        'no_color': False,
        'file_path': None,
    }


def get_dry_run_args() -> Dict[str, Any]:
    """Get CLI arguments for dry run mode.

    Returns:
        Dictionary with dry_run=True

    Example:
        >>> args = get_dry_run_args()
        >>> assert args['dry_run'] is True
    """
    args = get_default_cli_args()
    args['dry_run'] = True
    return args


def get_force_push_args() -> Dict[str, Any]:
    """Get CLI arguments for force push mode.

    Returns:
        Dictionary with force_push=True

    Example:
        >>> args = get_force_push_args()
        >>> assert args['force_push'] is True
    """
    args = get_default_cli_args()
    args['force_push'] = True
    return args


def get_force_pull_args() -> Dict[str, Any]:
    """Get CLI arguments for force pull mode.

    Returns:
        Dictionary with force_pull=True

    Example:
        >>> args = get_force_pull_args()
        >>> assert args['force_pull'] is True
    """
    args = get_default_cli_args()
    args['force_pull'] = True
    return args


def get_verbose_args(level: int = 1) -> Dict[str, Any]:
    """Get CLI arguments with verbose level.

    Args:
        level: Verbosity level (1 for -v, 2 for -vv). Defaults to 1

    Returns:
        Dictionary with verbose level set

    Example:
        >>> args = get_verbose_args(level=2)
        >>> assert args['verbose'] == 2
    """
    args = get_default_cli_args()
    args['verbose'] = level
    return args


# ==============================================================================
# Sample Config Dictionaries
# ==============================================================================

def get_sample_state_dict(last_synced: Optional[str] = None) -> Dict[str, Any]:
    """Get a sample state dictionary for testing.

    Args:
        last_synced: ISO 8601 timestamp. If None, creates fresh state

    Returns:
        Dictionary representing state.yaml content

    Example:
        >>> state_dict = get_sample_state_dict("2026-01-30T10:00:00Z")
        >>> assert state_dict['last_synced'] == "2026-01-30T10:00:00Z"
    """
    return {
        'last_synced': last_synced
    }
