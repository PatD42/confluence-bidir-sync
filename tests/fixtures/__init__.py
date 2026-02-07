"""Test fixtures for Confluence integration tests.

This module provides test fixtures for:
- Confluence credentials (from .env.test)
- Sample Confluence XHTML pages (with/without macros)
- Sample markdown content for conversion tests
- Git repository fixtures for git integration testing
- CLI fixtures for CLI module testing

These fixtures are extensible by future epics.
"""

from .confluence_credentials import get_test_credentials
from .sample_pages import (
    SAMPLE_PAGE_SIMPLE,
    SAMPLE_PAGE_WITH_MACROS,
    SAMPLE_PAGE_WITH_TABLES,
    SAMPLE_PAGE_WITH_CODE_BLOCKS,
)
from .sample_markdown import (
    SAMPLE_MARKDOWN_SIMPLE,
    SAMPLE_MARKDOWN_WITH_TABLES,
    SAMPLE_MARKDOWN_WITH_CODE_BLOCKS,
    SAMPLE_MARKDOWN_WITH_IMAGES,
)
from .git_test_repos import (
    empty_git_repo,
    repo_with_history,
    repo_with_page_versions,
    get_commit_count,
    get_file_content_at_commit,
    get_latest_commit_sha,
)
from .cli_fixtures import (
    get_fresh_sync_state,
    get_synced_state,
    get_empty_change_result,
    get_push_only_result,
    get_pull_only_result,
    get_conflict_result,
    get_mixed_change_result,
    get_empty_summary,
    get_push_summary,
    get_pull_summary,
    get_mixed_summary,
    get_iso_timestamp,
    get_timestamp_ago,
    get_timestamp_future,
    get_default_cli_args,
    get_dry_run_args,
    get_force_push_args,
    get_force_pull_args,
    get_verbose_args,
    get_sample_state_dict,
    SAMPLE_STATE_FRESH,
    SAMPLE_STATE_SYNCED,
    SAMPLE_STATE_INVALID_YAML,
    SAMPLE_STATE_INVALID_TYPE,
)

__all__ = [
    "get_test_credentials",
    "SAMPLE_PAGE_SIMPLE",
    "SAMPLE_PAGE_WITH_MACROS",
    "SAMPLE_PAGE_WITH_TABLES",
    "SAMPLE_PAGE_WITH_CODE_BLOCKS",
    "SAMPLE_MARKDOWN_SIMPLE",
    "SAMPLE_MARKDOWN_WITH_TABLES",
    "SAMPLE_MARKDOWN_WITH_CODE_BLOCKS",
    "SAMPLE_MARKDOWN_WITH_IMAGES",
    "empty_git_repo",
    "repo_with_history",
    "repo_with_page_versions",
    "get_commit_count",
    "get_file_content_at_commit",
    "get_latest_commit_sha",
    # CLI fixtures
    "get_fresh_sync_state",
    "get_synced_state",
    "get_empty_change_result",
    "get_push_only_result",
    "get_pull_only_result",
    "get_conflict_result",
    "get_mixed_change_result",
    "get_empty_summary",
    "get_push_summary",
    "get_pull_summary",
    "get_mixed_summary",
    "get_iso_timestamp",
    "get_timestamp_ago",
    "get_timestamp_future",
    "get_default_cli_args",
    "get_dry_run_args",
    "get_force_push_args",
    "get_force_pull_args",
    "get_verbose_args",
    "get_sample_state_dict",
    "SAMPLE_STATE_FRESH",
    "SAMPLE_STATE_SYNCED",
    "SAMPLE_STATE_INVALID_YAML",
    "SAMPLE_STATE_INVALID_TYPE",
]
