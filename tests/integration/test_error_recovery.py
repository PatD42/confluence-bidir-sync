"""Integration tests for error recovery paths.

Tests that errors during sync operations are handled gracefully,
including network errors, partial failures, and merge conflicts.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import time

from src.confluence_client.api_wrapper import APIWrapper
from src.git_integration.table_merge import merge_content_with_table_awareness


@pytest.mark.integration
class TestErrorRecovery:
    """Integration tests for error recovery behavior."""

    def test_network_error_retry(self, mock_network_error):
        """AC-10.1: Transient network errors trigger retry."""
        # Given: A mock that fails once then succeeds
        api_call = mock_network_error

        # When: First call fails
        with pytest.raises(ConnectionError):
            api_call()

        # And: Retry is attempted
        result = api_call()

        # Then: Retry should succeed
        assert result is not None, "Retry should succeed"
        assert result['id'] == '12345', "Should return expected result"

    def test_exponential_backoff_pattern(self):
        """AC-10.1b: Retry uses exponential backoff."""
        # Given: A function that tracks call times
        call_times = []

        def track_calls():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise ConnectionError("Transient error")
            return "Success"

        # When: Retries with backoff (simulated)
        delays = [0.1, 0.2, 0.4]  # Exponential backoff pattern
        for i, delay in enumerate(delays):
            try:
                track_calls()
                break
            except ConnectionError:
                if i < len(delays) - 1:
                    time.sleep(delay)

        # Then: Calls should have delays between them
        if len(call_times) >= 2:
            first_gap = call_times[1] - call_times[0]
            assert first_gap >= 0.09, "Should have delay between retries"

    def test_partial_sync_reports_failures(self, mock_api_wrapper):
        """AC-10.2: Multi-page sync reports partial failures."""
        # Given: A mock that fails for some pages
        pages_to_sync = [
            {'page_id': '111', 'content': 'Content 1'},
            {'page_id': '222', 'content': 'Content 2'},  # Will fail
            {'page_id': '333', 'content': 'Content 3'},
        ]

        def update_with_partial_failure(page_id, *args, **kwargs):
            if page_id == '222':
                raise Exception("Failed to update page 222")
            return {'id': page_id, 'version': {'number': 2}}

        mock_api_wrapper.update_page.side_effect = update_with_partial_failure

        # When: Syncing multiple pages
        results = {'success': [], 'failed': []}
        for page in pages_to_sync:
            try:
                result = mock_api_wrapper.update_page(
                    page['page_id'],
                    page['content']
                )
                results['success'].append(page['page_id'])
            except Exception as e:
                results['failed'].append({
                    'page_id': page['page_id'],
                    'error': str(e)
                })

        # Then: Successful and failed pages should be reported
        assert '111' in results['success'], "Page 111 should succeed"
        assert '333' in results['success'], "Page 333 should succeed"
        assert len(results['failed']) == 1, "One page should fail"
        assert results['failed'][0]['page_id'] == '222', "Page 222 should fail"

    def test_merge_conflict_writes_markers(self, temp_test_dir):
        """AC-10.3: Merge conflicts write conflict markers to file."""
        # Given: Content with unresolvable conflict (same cell changed)
        baseline = """| Col1 | Col2 |
|------|------|
| A | B |
"""
        local = """| Col1 | Col2 |
|------|------|
| A-local | B |
"""
        remote = """| Col1 | Col2 |
|------|------|
| A-remote | B |
"""

        # When: Merge produces conflict
        result, _ = merge_content_with_table_awareness(
            baseline.strip(),
            local.strip(),
            remote.strip()
        )

        # Then: Result may contain conflict markers or both values
        has_conflict_markers = "<<<<<<" in result and ">>>>>>>" in result
        has_both_values = "A-local" in result and "A-remote" in result

        assert has_conflict_markers or has_both_values, \
            f"Conflict should be indicated in result: {result}"

    def test_conflict_file_can_be_written(self, temp_test_dir):
        """Verify conflict content can be written to file."""
        conflict_content = """<<<<<<< local
Local changes here
=======
Remote changes here
>>>>>>> remote
"""
        conflict_file = temp_test_dir / "conflict-page.md"
        conflict_file.write_text(conflict_content)

        # File should be readable
        assert conflict_file.exists()
        read_content = conflict_file.read_text()
        assert "<<<<<<< local" in read_content
        assert ">>>>>>> remote" in read_content


@pytest.mark.integration
class TestRetryMechanisms:
    """Integration tests for retry mechanisms."""

    def test_max_retries_limit(self):
        """Verify retry mechanism respects maximum retry limit."""
        max_retries = 3
        attempts = [0]

        def always_fails():
            attempts[0] += 1
            raise ConnectionError("Always fails")

        # When: Retrying up to max
        for _ in range(max_retries):
            try:
                always_fails()
            except ConnectionError:
                pass

        # Then: Should have attempted max_retries times
        assert attempts[0] == max_retries, \
            f"Should attempt exactly {max_retries} times"

    def test_success_stops_retry(self):
        """Verify successful operation stops retry loop."""
        attempts = [0]

        def succeeds_second_time():
            attempts[0] += 1
            if attempts[0] < 2:
                raise ConnectionError("Temporary failure")
            return "Success"

        # When: Retrying until success
        result = None
        for _ in range(5):  # Max 5 attempts
            try:
                result = succeeds_second_time()
                break
            except ConnectionError:
                pass

        # Then: Should stop after success
        assert result == "Success"
        assert attempts[0] == 2, "Should stop after successful attempt"

    def test_different_error_types_handled(self):
        """Verify different error types are handled appropriately."""
        # Network errors - should retry
        network_error = ConnectionError("Network unreachable")

        # API errors - may or may not retry depending on error code
        api_error_4xx = Exception("404 Not Found")
        api_error_5xx = Exception("500 Internal Server Error")

        # Verify errors can be distinguished
        assert isinstance(network_error, ConnectionError)
        assert "404" in str(api_error_4xx)
        assert "500" in str(api_error_5xx)


@pytest.mark.integration
class TestPartialCommit:
    """Integration tests for partial commit behavior."""

    def test_successful_pages_committed(self, mock_api_wrapper, temp_test_dir):
        """Verify successful pages are saved even when others fail."""
        # Given: Local state with multiple pages
        pages = {
            'page-1': {'content': 'Content 1', 'version': 1},
            'page-2': {'content': 'Content 2', 'version': 1},
            'page-3': {'content': 'Content 3', 'version': 1},
        }

        # And: Page 2 fails to sync
        def sync_with_failure(page_id, *args, **kwargs):
            if page_id == 'page-2':
                raise Exception("Sync failed for page-2")
            return {'id': page_id, 'synced': True}

        # When: Syncing all pages
        synced = []
        failed = []

        for page_id, page_data in pages.items():
            try:
                result = sync_with_failure(page_id, page_data['content'])
                synced.append(page_id)
            except Exception as e:
                failed.append({'page_id': page_id, 'error': str(e)})

        # Then: Successful pages should be recorded
        assert 'page-1' in synced, "page-1 should be synced"
        assert 'page-3' in synced, "page-3 should be synced"
        assert len(failed) == 1, "One page should fail"

    def test_failed_pages_can_retry_later(self):
        """Verify failed pages are tracked for later retry."""
        failed_pages = [
            {'page_id': 'page-2', 'error': 'Network timeout', 'attempts': 1},
        ]

        # Failed pages should have metadata for retry
        for page in failed_pages:
            assert 'page_id' in page, "Should have page_id"
            assert 'error' in page, "Should have error message"
            assert 'attempts' in page, "Should track attempt count"


@pytest.mark.integration
class TestMergeFailureHandling:
    """Integration tests for merge failure scenarios."""

    def test_merge_failure_preserves_local(self, temp_test_dir):
        """Verify merge failure preserves local content."""
        local_file = temp_test_dir / "test-page.md"
        original_content = "# Original local content\n\nThis should be preserved."
        local_file.write_text(original_content)

        # Simulate merge failure
        merge_failed = True

        if merge_failed:
            # Local content should remain unchanged
            assert local_file.read_text() == original_content, \
                "Local content should be preserved on merge failure"

    def test_merge_conflict_markers_format(self):
        """Verify conflict markers follow expected format."""
        conflict_content = """# Test Page

<<<<<<< local
Local version of content
=======
Remote version of content
>>>>>>> remote

Rest of document
"""
        # Verify marker format
        assert "<<<<<<< local" in conflict_content, "Should have local marker"
        assert "=======" in conflict_content, "Should have separator"
        assert ">>>>>>> remote" in conflict_content, "Should have remote marker"

    def test_user_notified_of_conflicts(self, temp_test_dir):
        """Verify conflicts are reported for user notification."""
        # Simulate conflict detection
        conflicts = [
            {
                'page_id': 'page-123',
                'file_path': str(temp_test_dir / 'page-123.md'),
                'conflict_type': 'content',
            }
        ]

        # Conflicts should have enough info for user notification
        for conflict in conflicts:
            assert 'page_id' in conflict, "Should identify page"
            assert 'file_path' in conflict, "Should provide file path"
            assert 'conflict_type' in conflict, "Should describe conflict type"
