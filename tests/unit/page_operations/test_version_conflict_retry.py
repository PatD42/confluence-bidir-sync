"""Unit tests for version conflict retry in PageOperations.

Tests H3: Version conflict retry with exponential backoff.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import time

from src.page_operations.page_operations import PageOperations
from src.page_operations.models import UpdateResult, SurgicalOperation, OperationType
from src.confluence_client.errors import APIAccessError


class TestVersionConflictRetry:
    """Test cases for version conflict retry (H3)."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API wrapper."""
        api = Mock()
        return api

    @pytest.fixture
    def page_ops(self, mock_api):
        """Create PageOperations with mocked API."""
        return PageOperations(api=mock_api)

    def test_successful_update_without_conflict(self, page_ops, mock_api):
        """Verify successful update without conflicts requires no retries."""
        # Mock successful page fetch and update
        mock_api.get_page_by_id.return_value = {
            "id": "123456",
            "title": "Test Page",
            "version": {"number": 5},
            "body": {"storage": {"value": "<p>Content</p>"}}
        }
        mock_api.update_page.return_value = {
            "id": "123456",
            "version": {"number": 6}
        }

        # Apply operations
        operations = [
            SurgicalOperation(op_type=OperationType.UPDATE_TEXT, target_content="old", new_content="new")
        ]
        result = page_ops.apply_operations(
            page_id="123456",
            base_xhtml="<p>Content</p>",
            base_version=5,
            operations=operations
        )

        # Should succeed on first attempt
        assert result.success is True
        assert result.new_version == 6
        # Should only call get_page_by_id once (no retries)
        assert mock_api.get_page_by_id.call_count == 1

    def test_version_conflict_with_successful_retry(self, page_ops, mock_api):
        """Verify version conflict triggers retry that succeeds (CRITICAL TEST)."""
        # Each attempt calls get_page_by_id once in _apply_operations_once
        # Retries also call it once to refetch
        # Attempt 1: get_page (conflict) -> Retry 1: refetch + get_page (success)
        get_page_calls = [
            # Attempt 1: version conflict (6 != 5)
            {"id": "123456", "title": "Test", "version": {"number": 6}, "body": {"storage": {"value": "<p>V6</p>"}}},
            # Retry 1: refetch current page
            {"id": "123456", "title": "Test", "version": {"number": 6}, "body": {"storage": {"value": "<p>V6</p>"}}},
            # Retry 1: check version in _apply_operations_once
            {"id": "123456", "title": "Test", "version": {"number": 6}, "body": {"storage": {"value": "<p>V6</p>"}}},
        ]
        mock_api.get_page_by_id.side_effect = get_page_calls

        # Update succeeds on retry
        mock_api.update_page.return_value = {"id": "123456", "version": {"number": 7}}

        operations = [SurgicalOperation(op_type=OperationType.UPDATE_TEXT, target_content="old", new_content="new")]

        # Apply with base version 5 (will conflict with current version 6)
        result = page_ops.apply_operations(
            page_id="123456",
            base_xhtml="<p>V5</p>",
            base_version=5,
            operations=operations
        )

        # Should succeed after retry
        assert result.success is True
        assert result.new_version == 7

    def test_multiple_retries_with_final_success(self, page_ops, mock_api):
        """Verify multiple version conflicts retry up to 3 times."""
        # Simulate 2 conflicts, then success
        # Attempt 1: get_page (v6, conflict)
        # Retry 1: refetch (v7) + get_page (v7, conflict)
        # Retry 2: refetch (v8) + get_page (v8, success)
        get_page_calls = [
            # Attempt 1: check version (conflict: 6 != 5)
            {"id": "123456", "title": "Test", "version": {"number": 6}, "body": {"storage": {"value": "<p>V6</p>"}}},
            # Retry 1: refetch
            {"id": "123456", "title": "Test", "version": {"number": 7}, "body": {"storage": {"value": "<p>V7</p>"}}},
            # Retry 1: check version (conflict: 7 != 6 after refetch)
            {"id": "123456", "title": "Test", "version": {"number": 7}, "body": {"storage": {"value": "<p>V7</p>"}}},
            # Retry 2: refetch
            {"id": "123456", "title": "Test", "version": {"number": 8}, "body": {"storage": {"value": "<p>V8</p>"}}},
            # Retry 2: check version (success: 8 == 8)
            {"id": "123456", "title": "Test", "version": {"number": 8}, "body": {"storage": {"value": "<p>V8</p>"}}},
        ]
        mock_api.get_page_by_id.side_effect = get_page_calls

        # Final update succeeds
        mock_api.update_page.return_value = {"id": "123456", "version": {"number": 9}}

        operations = [SurgicalOperation(op_type=OperationType.UPDATE_TEXT, target_content="old", new_content="new")]

        result = page_ops.apply_operations(
            page_id="123456",
            base_xhtml="<p>V5</p>",
            base_version=5,
            operations=operations
        )

        # Should succeed after 2 retries
        assert result.success is True
        assert result.new_version == 9

    def test_max_retries_exhausted(self, page_ops, mock_api):
        """Verify retry stops after 3 attempts."""
        # Simulate persistent version conflicts - race condition where page keeps getting updated
        # Attempt 1: check (6 != 5) - conflict
        # Retry 1: refetch (6) but check sees (7) - someone updated between refetch and check
        # Retry 2: refetch (7) but check sees (8) - someone updated between refetch and check
        # Retry 3: refetch (8) but check sees (9) - someone updated between refetch and check
        mock_api.get_page_by_id.side_effect = [
            # Attempt 1: check (6 != 5)
            {"id": "123456", "title": "Test", "version": {"number": 6}, "body": {"storage": {"value": "<p>V6</p>"}}},
            # Retry 1: refetch (gets v6) + check (sees v7) - race condition!
            {"id": "123456", "title": "Test", "version": {"number": 6}, "body": {"storage": {"value": "<p>V6</p>"}}},
            {"id": "123456", "title": "Test", "version": {"number": 7}, "body": {"storage": {"value": "<p>V7</p>"}}},
            # Retry 2: refetch (gets v7) + check (sees v8) - race condition!
            {"id": "123456", "title": "Test", "version": {"number": 7}, "body": {"storage": {"value": "<p>V7</p>"}}},
            {"id": "123456", "title": "Test", "version": {"number": 8}, "body": {"storage": {"value": "<p>V8</p>"}}},
            # Retry 3: refetch (gets v8) + check (sees v9) - race condition!
            {"id": "123456", "title": "Test", "version": {"number": 8}, "body": {"storage": {"value": "<p>V8</p>"}}},
            {"id": "123456", "title": "Test", "version": {"number": 9}, "body": {"storage": {"value": "<p>V9</p>"}}},
        ]

        operations = [SurgicalOperation(op_type=OperationType.UPDATE_TEXT, target_content="old", new_content="new")]

        result = page_ops.apply_operations(
            page_id="123456",
            base_xhtml="<p>V5</p>",
            base_version=5,
            operations=operations
        )

        # Should fail after exhausting retries
        assert result.success is False
        assert "Version conflict" in result.error

    def test_exponential_backoff_delays(self, page_ops, mock_api, monkeypatch):
        """Verify exponential backoff timing (1s, 2s, 4s)."""
        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        monkeypatch.setattr(time, 'sleep', mock_sleep)

        # Simulate 3 conflicts (will exhaust retries) - race condition
        mock_api.get_page_by_id.side_effect = [
            # Attempt 1: check (6 != 5)
            {"id": "123456", "title": "Test", "version": {"number": 6}, "body": {"storage": {"value": "<p>V6</p>"}}},
            # Retry 1: refetch (gets v6) + check (sees v7) - race condition!
            {"id": "123456", "title": "Test", "version": {"number": 6}, "body": {"storage": {"value": "<p>V6</p>"}}},
            {"id": "123456", "title": "Test", "version": {"number": 7}, "body": {"storage": {"value": "<p>V7</p>"}}},
            # Retry 2: refetch (gets v7) + check (sees v8) - race condition!
            {"id": "123456", "title": "Test", "version": {"number": 7}, "body": {"storage": {"value": "<p>V7</p>"}}},
            {"id": "123456", "title": "Test", "version": {"number": 8}, "body": {"storage": {"value": "<p>V8</p>"}}},
            # Retry 3: refetch (gets v8) + check (sees v9) - race condition!
            {"id": "123456", "title": "Test", "version": {"number": 8}, "body": {"storage": {"value": "<p>V8</p>"}}},
            {"id": "123456", "title": "Test", "version": {"number": 9}, "body": {"storage": {"value": "<p>V9</p>"}}},
        ]

        operations = [SurgicalOperation(op_type=OperationType.UPDATE_TEXT, target_content="old", new_content="new")]

        page_ops.apply_operations(
            page_id="123456",
            base_xhtml="<p>V5</p>",
            base_version=5,
            operations=operations
        )

        # Verify exponential backoff: 1s, 2s, 4s
        assert sleep_calls == [1.0, 2.0, 4.0]

    def test_non_conflict_error_no_retry(self, page_ops, mock_api):
        """Verify non-version-conflict errors don't trigger retries."""
        mock_api.get_page_by_id.return_value = {
            "id": "123456",
            "title": "Test",
            "version": {"number": 5},
            "body": {"storage": {"value": "<p>Content</p>"}}
        }

        # Simulate a network error (not version conflict)
        mock_api.update_page.side_effect = APIAccessError("Network timeout")

        operations = [SurgicalOperation(op_type=OperationType.UPDATE_TEXT, target_content="old", new_content="new")]

        result = page_ops.apply_operations(
            page_id="123456",
            base_xhtml="<p>Content</p>",
            base_version=5,
            operations=operations
        )

        # Should fail without retry
        assert result.success is False
        assert "Network timeout" in result.error
        # Should only call get_page_by_id once (no retries)
        assert mock_api.get_page_by_id.call_count == 1

    def test_refetch_failure_during_retry(self, page_ops, mock_api):
        """Verify handling when re-fetch fails during retry."""
        # First call succeeds (detects conflict)
        # Second call fails (re-fetch error)
        mock_api.get_page_by_id.side_effect = [
            {"id": "123456", "title": "Test", "version": {"number": 6}, "body": {"storage": {"value": "<p>V6</p>"}}},
            APIAccessError("Network error during re-fetch"),
        ]

        operations = [SurgicalOperation(op_type=OperationType.UPDATE_TEXT, target_content="old", new_content="new")]

        result = page_ops.apply_operations(
            page_id="123456",
            base_xhtml="<p>V5</p>",
            base_version=5,
            operations=operations
        )

        # Should fail gracefully
        assert result.success is False
        assert "Failed to re-fetch page for retry" in result.error

    def test_operations_reapplied_to_new_version(self, page_ops, mock_api):
        """Verify operations are reapplied to refetched page content."""
        # Track what XHTML was passed to surgical editor
        xhtml_inputs = []

        original_apply = page_ops._apply_operations_once

        def track_xhtml(*args, **kwargs):
            xhtml_inputs.append(kwargs.get('base_xhtml', args[1] if len(args) > 1 else None))
            return original_apply(*args, **kwargs)

        page_ops._apply_operations_once = track_xhtml

        # Conflict, then success
        mock_api.get_page_by_id.side_effect = [
            # Attempt 1: check version (conflict)
            {"id": "123456", "title": "Test", "version": {"number": 6}, "body": {"storage": {"value": "<p>V6 content</p>"}}},
            # Retry 1: refetch new content
            {"id": "123456", "title": "Test", "version": {"number": 7}, "body": {"storage": {"value": "<p>V7 content</p>"}}},
            # Retry 1: check version (success)
            {"id": "123456", "title": "Test", "version": {"number": 7}, "body": {"storage": {"value": "<p>V7 content</p>"}}},
        ]

        mock_api.update_page.return_value = {"id": "123456", "version": {"number": 8}}

        operations = [SurgicalOperation(op_type=OperationType.UPDATE_TEXT, target_content="old", new_content="new")]

        page_ops.apply_operations(
            page_id="123456",
            base_xhtml="<p>V5 content</p>",
            base_version=5,
            operations=operations
        )

        # First attempt should use original base_xhtml
        assert "<p>V5 content</p>" in xhtml_inputs[0]
        # Retry should use refetched XHTML
        assert "<p>V7 content</p>" in xhtml_inputs[1]
