"""Root pytest configuration for all tests.

This conftest applies to all test types (unit, integration, e2e).
"""

import logging

# Suppress noisy ERROR logs from atlassian-python-api when pages don't exist.
# The library logs at ERROR level for "page not found" which is expected
# behavior during test setup when checking if pages exist before creating them.
# Setting to WARNING only shows actual warnings, not normal lookup failures.
logging.getLogger("atlassian").setLevel(logging.WARNING)
