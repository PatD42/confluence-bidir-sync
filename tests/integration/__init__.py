"""Integration tests for Confluence bidirectional sync.

These tests validate integration between components using real external services
(Confluence API) and filesystem operations. They bridge the gap between isolated
unit tests and full end-to-end journeys.

Test Coverage:
- CQL Query Execution: Real CQL queries against test Confluence space
- File Operations: Write/read markdown files with frontmatter validation
- Config Persistence: Save/load YAML configuration files
- Atomic Operations: Two-phase commit pattern with rollback verification

Requirements:
- Test credentials in .env.test file
- Access to CONFSYNCTEST space in Confluence
- Write permissions to local filesystem (uses temp directories)

These tests use real external dependencies and may take longer than unit tests.
Use pytest marks to run specific integration test suites:
    pytest tests/integration -m cql_queries
    pytest tests/integration -m file_operations
"""
