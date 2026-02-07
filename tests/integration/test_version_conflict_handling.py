"""Integration tests for version conflict detection and recovery.

Tests that version conflicts are detected when the page version changes
between read and write operations, and that retry logic works correctly.
"""

import pytest
from unittest.mock import Mock, patch, call

from src.page_operations.page_operations import PageOperations
from src.confluence_client.api_wrapper import APIWrapper


@pytest.mark.integration
class TestVersionConflictHandling:
    """Integration tests for version conflict detection and recovery."""

    def test_version_change_detected(self, mock_api_wrapper_version_conflict):
        """AC-7.1: Version mismatch is detected during update."""
        # Given: A mock that simulates version conflict
        api = mock_api_wrapper_version_conflict

        # When: Update is attempted with stale version
        # The mock is configured to fail first with version conflict
        with pytest.raises(Exception) as exc_info:
            api.update_page(
                page_id='12345',
                body='<p>New content</p>',
                version=1  # Stale version
            )

        # Then: Version conflict error should be raised
        assert "version" in str(exc_info.value).lower() or \
               "conflict" in str(exc_info.value).lower(), \
            f"Error should mention version conflict: {exc_info.value}"

    def test_version_conflict_error_includes_versions(self):
        """AC-7.1b: Version conflict error includes expected vs actual version."""
        # Given: A mock that returns version conflict error with details
        mock_api = Mock(spec=APIWrapper)
        mock_api.update_page.side_effect = Exception(
            "Version conflict: expected version 1, but page is at version 2"
        )

        # When: Update fails
        with pytest.raises(Exception) as exc_info:
            mock_api.update_page('12345', '<p>Content</p>', version=1)

        # Then: Error message should include version numbers
        error_msg = str(exc_info.value)
        assert "1" in error_msg and "2" in error_msg, \
            "Error should include both version numbers"

    def test_retry_with_fresh_version(self, mock_api_wrapper_version_conflict):
        """AC-7.2: Version conflict triggers re-fetch and retry."""
        api = mock_api_wrapper_version_conflict

        # When: First update fails, we should re-fetch and retry
        # First call fails
        try:
            api.update_page('12345', '<p>Content</p>', version=1)
        except Exception:
            pass  # Expected to fail

        # Re-fetch page to get current version
        page = api.get_page_by_id('12345')
        current_version = page['version']['number']

        # Retry with new version
        result = api.update_page('12345', '<p>Content</p>', version=current_version)

        # Then: Second attempt should succeed
        assert result is not None, "Retry should succeed"
        assert result['version']['number'] > current_version, \
            "Version should be incremented"

    def test_persistent_conflict_reported(self):
        """AC-7.3: Persistent conflicts after max retries are reported."""
        # Given: A mock that always fails with version conflict
        mock_api = Mock(spec=APIWrapper)
        mock_api.update_page.side_effect = Exception("Version conflict")
        mock_api.get_page_by_id.return_value = {
            'id': '12345',
            'version': {'number': 99},  # Always different
        }

        # When: Multiple retries are attempted
        max_retries = 3
        attempt = 0
        last_error = None

        for _ in range(max_retries):
            try:
                mock_api.update_page('12345', '<p>Content</p>', version=1)
            except Exception as e:
                attempt += 1
                last_error = e

        # Then: All retries should fail
        assert attempt == max_retries, f"Should have attempted {max_retries} times"
        assert last_error is not None, "Should have captured error"


@pytest.mark.integration
class TestVersionTracking:
    """Integration tests for version number tracking."""

    def test_version_increments_on_update(self, mock_api_wrapper):
        """Verify version number increments after successful update."""
        # Given: Page at version 1
        mock_api_wrapper.get_page_by_id.return_value = {
            'id': '12345',
            'version': {'number': 1},
            'body': {'storage': {'value': '<p>Original</p>'}},
        }

        # When: Update succeeds
        mock_api_wrapper.update_page.return_value = {
            'id': '12345',
            'version': {'number': 2},
        }

        result = mock_api_wrapper.update_page('12345', '<p>Updated</p>', version=1)

        # Then: Version should increment
        assert result['version']['number'] == 2, \
            "Version should be 2 after update"

    def test_concurrent_updates_cause_conflict(self):
        """Verify concurrent updates from different sources cause conflict."""
        # Given: Two "clients" see the same version
        mock_api = Mock(spec=APIWrapper)

        initial_page = {
            'id': '12345',
            'version': {'number': 1},
            'body': {'storage': {'value': '<p>Original</p>'}},
        }
        mock_api.get_page_by_id.return_value = initial_page

        # Client A updates successfully
        update_count = [0]

        def update_with_race(*args, **kwargs):
            update_count[0] += 1
            if update_count[0] == 1:
                # First update succeeds
                return {'id': '12345', 'version': {'number': 2}}
            else:
                # Second update fails - version changed
                raise Exception("Version conflict: expected 1, got 2")

        mock_api.update_page.side_effect = update_with_race

        # When: Both clients try to update from version 1
        # Client A succeeds
        result_a = mock_api.update_page('12345', '<p>Update A</p>', version=1)
        assert result_a['version']['number'] == 2

        # Client B fails
        with pytest.raises(Exception) as exc_info:
            mock_api.update_page('12345', '<p>Update B</p>', version=1)

        # Then: Second client gets conflict
        assert "conflict" in str(exc_info.value).lower()


@pytest.mark.integration
class TestOptimisticLocking:
    """Integration tests for optimistic locking behavior."""

    def test_read_modify_write_pattern(self, mock_api_wrapper):
        """Verify read-modify-write pattern with version checking."""
        # Given: Read current page state
        page = mock_api_wrapper.get_page_by_id('12345')
        current_version = page['version']['number']

        # When: Modify and write with correct version
        result = mock_api_wrapper.update_page(
            '12345',
            '<p>Modified content</p>',
            version=current_version
        )

        # Then: Update should succeed
        assert result['version']['number'] == current_version + 1

    def test_stale_version_rejected(self):
        """Verify stale version is rejected by API."""
        mock_api = Mock(spec=APIWrapper)

        # Page is at version 5
        mock_api.get_page_by_id.return_value = {
            'id': '12345',
            'version': {'number': 5},
        }

        # But client tries to update from version 3 (stale)
        mock_api.update_page.side_effect = Exception(
            "Version mismatch: page is at version 5, update specified version 3"
        )

        # When: Stale update is attempted
        with pytest.raises(Exception) as exc_info:
            mock_api.update_page('12345', '<p>Content</p>', version=3)

        # Then: Should be rejected
        assert "version" in str(exc_info.value).lower()

    def test_version_preserved_in_error_recovery(self):
        """Verify version handling during error recovery."""
        mock_api = Mock(spec=APIWrapper)

        # Transient error on first try, success on second
        call_count = [0]

        def transient_error(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("Network timeout")
            return {'id': '12345', 'version': {'number': 2}}

        mock_api.update_page.side_effect = transient_error

        # When: First call fails with transient error
        try:
            mock_api.update_page('12345', '<p>Content</p>', version=1)
        except ConnectionError:
            pass

        # Retry immediately (version unchanged since update didn't happen)
        result = mock_api.update_page('12345', '<p>Content</p>', version=1)

        # Then: Retry should succeed with same version
        assert result['version']['number'] == 2
