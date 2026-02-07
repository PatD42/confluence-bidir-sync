"""E2E tests for file_mapper module.

This package contains end-to-end tests for the file_mapper module that validate
complete workflows using real Confluence API and filesystem operations against
the CONFSYNCTEST space.

E2E Test Scenarios:
- E2E-1: Full Pull Sync (Confluence → Local)
- E2E-2: Full Push Sync (Local → Confluence)
- E2E-3: Bidirectional Sync
- E2E-4: Title Change Detection
- E2E-5: Exclusion by PageID
- E2E-6: Page Limit Enforcement

Requirements:
- Test Confluence credentials in .env.test
- CONFSYNCTEST space must exist in test Confluence instance
- Tests create/modify/delete pages under parent page in CONFSYNCTEST space
- All test pages are automatically cleaned up after tests complete

Test Fixtures (defined in conftest.py):
- test_credentials: Load credentials from .env.test
- api_wrapper: Authenticated Confluence API wrapper
- temp_test_dir: Temporary directory for local file operations
- test_config_dir: .confluence-sync configuration directory
- cleanup_test_pages: Automatic cleanup of test pages
- test_parent_page: Parent page for test hierarchies
- file_mapper_instance: Configured FileMapper instance
"""
