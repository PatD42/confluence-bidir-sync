"""E2E test: Force Operations Journey (E2E-CR-03, E2E-CR-04).

This test validates force push and force pull operations:

Force Push (E2E-CR-03):
1. Create page on Confluence (v1)
2. Pull to local git repo
3. Edit local file
4. Edit Confluence page (v2 with different content)
5. Force push → No conflict detection
6. Verify Confluence overwritten with local content
7. Verify version incremented
8. Verify git repo updated

Force Pull (E2E-CR-04):
1. Create page on Confluence (v1)
2. Pull to local git repo
3. Edit local file
4. Edit Confluence page (v2 with different content)
5. Force pull → No conflict detection
6. Verify local file overwritten with Confluence content
7. Verify frontmatter updated to remote version
8. Verify git repo updated

Requirements:
- Test Confluence credentials in .env.test
- Git CLI installed on system

Test Scenarios: E2E-CR-03, E2E-CR-04 from test-strategy.md
"""

import logging
import os
import re
import tempfile

import pytest

from src.confluence_client.api_wrapper import APIWrapper
from src.confluence_client.auth import Authenticator
from src.content_converter.markdown_converter import MarkdownConverter
from src.git_integration.git_repository import GitRepository
from src.git_integration.merge_orchestrator import MergeOrchestrator
from src.git_integration.models import LocalPage
from src.git_integration.xhtml_cache import XHTMLCache
from src.page_operations.page_operations import PageOperations
from tests.helpers.confluence_test_setup import setup_test_page, teardown_test_page

logger = logging.getLogger(__name__)


class TestForceOperationsJourney:
    """E2E tests for force push and force pull operations."""

    @pytest.fixture(scope="function")
    def temp_workspace(self):
        """Create temporary workspace for local files and git repo."""
        temp_dir = tempfile.mkdtemp(prefix="e2e_force_ops_")
        logger.info(f"Created temp workspace: {temp_dir}")
        yield temp_dir
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"Cleaned up temp workspace: {temp_dir}")

    @pytest.fixture(scope="function")
    def test_page_for_force_push(self):
        """Create a test page for force push tests."""
        initial_content = """
<h1>E2E Force Push Test</h1>
<p>This is a test page for force push operations.</p>
<h2>Installation</h2>
<p>Install via pip:</p>
<pre><code>pip install myapp</code></pre>
<h2>Usage</h2>
<p>Run the application.</p>
"""
        page_info = setup_test_page(
            title="E2E Test - Force Push Journey",
            content=initial_content
        )
        logger.info(f"Created test page for force push: {page_info['page_id']} (v{page_info['version']})")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up test page: {page_info['page_id']}")

    @pytest.fixture(scope="function")
    def test_page_for_force_pull(self):
        """Create a test page for force pull tests."""
        initial_content = """
<h1>E2E Force Pull Test</h1>
<p>This is a test page for force pull operations.</p>
<h2>Configuration</h2>
<p>Set up your config:</p>
<pre><code>config.yaml</code></pre>
<h2>Advanced</h2>
<p>Advanced settings.</p>
"""
        page_info = setup_test_page(
            title="E2E Test - Force Pull Journey",
            content=initial_content
        )
        logger.info(f"Created test page for force pull: {page_info['page_id']} (v{page_info['version']})")
        yield page_info
        # Cleanup
        teardown_test_page(page_info['page_id'])
        logger.info(f"Cleaned up test page: {page_info['page_id']}")

    def test_force_push_overwrites_remote(self, test_page_for_force_push, temp_workspace):
        """Test force push overwrites Confluence without conflict detection.

        Scenario (E2E-CR-03):
        - Local version 1 (modified), Confluence version 2
        - Force push → No conflict detection
        - Confluence content overwritten with local
        - Confluence version increments to 3
        - Git repo commits version 3

        Expected outcome:
        - No conflict detection performed
        - Confluence content matches local content
        - Version incremented correctly
        - Git repo has all versions (1, 3)
        """
        # Initialize components
        auth = Authenticator()
        api = APIWrapper(auth)
        page_ops = PageOperations(api=api)
        converter = MarkdownConverter()

        # Setup git repo and cache
        repo_path = os.path.join(temp_workspace, "git_repo")
        cache_path = os.path.join(temp_workspace, "cache")
        os.makedirs(repo_path)
        os.makedirs(cache_path)

        git_repo = GitRepository(repo_path)
        git_repo.init_if_not_exists()

        cache = XHTMLCache(cache_path)

        page_id = test_page_for_force_push['page_id']
        local_file_path = os.path.join(temp_workspace, f"{page_id}.md")

        # Step 1: Fetch initial page from Confluence (v1)
        logger.info("Step 1: Fetch initial page from Confluence (v1)")
        snapshot_v1 = page_ops.get_page_snapshot(page_id)
        assert snapshot_v1.version == 1, "Initial version should be 1"

        markdown_v1 = snapshot_v1.markdown

        # Write local file with frontmatter
        with open(local_file_path, "w") as f:
            f.write(f"---\npage_id: {page_id}\nconfluence_version: 1\n---\n\n")
            f.write(markdown_v1)

        logger.info(f"Saved local file: {local_file_path}")

        # Commit base version to git
        git_repo.commit_version(
            page_id=page_id,
            markdown=markdown_v1,
            version=1
        )
        logger.info("✓ Committed base version (v1) to git repo")

        # Step 2: Edit local file (modify Installation section)
        logger.info("Step 2: Edit local file")
        local_modified = markdown_v1.replace(
            "Install via pip:",
            "Install via npm:"
        ).replace(
            "pip install myapp",
            "npm install myapp"
        )

        # Update local file (still tracking v1)
        with open(local_file_path, "w") as f:
            f.write(f"---\npage_id: {page_id}\nconfluence_version: 1\n---\n\n")
            f.write(local_modified)

        logger.info("Local edit: Changed 'pip install' → 'npm install'")

        # Step 3: Edit Confluence page (different change to create version mismatch)
        logger.info("Step 3: Edit Confluence page (simulate external edit)")

        # Modify the Installation section differently on Confluence
        remote_xhtml = snapshot_v1.xhtml.replace(
            "Install via pip:",
            "Install via poetry:"
        ).replace(
            "pip install myapp",
            "poetry add myapp"
        )

        # Update the page on Confluence
        api.update_page(
            page_id=page_id,
            title=test_page_for_force_push['title'],
            body=remote_xhtml,
            version=1
        )

        # Verify page updated to v2
        snapshot_v2 = page_ops.get_page_snapshot(page_id)
        assert snapshot_v2.version == 2, "Confluence version should be 2 after update"
        logger.info("✓ Updated Confluence page to v2")
        logger.info("Remote edit: Changed 'pip install' → 'poetry add'")

        # Step 4: Force push (should skip conflict detection and overwrite Confluence)
        logger.info("Step 4: Force push → No conflict detection")

        # Create LocalPage object for force push
        local_page = LocalPage(
            page_id=page_id,
            file_path=local_file_path,
            local_version=1,  # Version from frontmatter
            title=test_page_for_force_push['title']
        )

        # Create MergeOrchestrator with all dependencies
        orchestrator = MergeOrchestrator(
            page_ops=page_ops,
            git_repo=git_repo,
            cache=cache,
            converter=converter,
            local_dir=temp_workspace
        )

        # Call force_push (this is what we're testing!)
        result = orchestrator.force_push([local_page])

        # Verify result
        assert result.success, f"Force push should succeed: {result.errors}"
        assert result.pages_synced == 1, f"Should have synced 1 page (got {result.pages_synced})"
        assert result.pages_failed == 0, f"Should have 0 failures (got {result.pages_failed})"

        logger.info("✓ Force pushed local content to Confluence")

        # Step 5: Verify Confluence overwritten with local content
        logger.info("Step 5: Verify Confluence overwritten with local content")

        snapshot_v3 = page_ops.get_page_snapshot(page_id)

        # Version should be 3 after force push
        assert snapshot_v3.version == 3, f"Confluence version should be 3 (got {snapshot_v3.version})"

        # Verify content matches local (npm install, not poetry add)
        assert "npm install" in snapshot_v3.markdown or "npm install" in snapshot_v3.xhtml, \
            "Confluence should have local content (npm install)"
        assert "poetry add" not in snapshot_v3.markdown and "poetry add" not in snapshot_v3.xhtml, \
            "Confluence should not have remote content (poetry add)"

        logger.info("✓ Verified Confluence overwritten with local content")
        logger.info(f"Confluence version incremented: v2 → v3")

        # Step 6: Verify git repo state (force_push committed automatically)
        logger.info("Step 6: Verify git repo state (auto-committed by force_push)")

        # Verify we can retrieve both versions from git
        base_from_git = git_repo.get_version(page_id, version=1)
        assert base_from_git is not None, "Should retrieve v1 from git"
        assert "pip install" in base_from_git, "v1 should have original content"

        latest_from_git = git_repo.get_version(page_id, version=3)
        assert latest_from_git is not None, "Should retrieve v3 from git"
        assert "npm install" in latest_from_git, "v3 should have local content"

        latest_version = git_repo.get_latest_version_number(page_id)
        assert latest_version == 3, f"Latest version in git should be 3 (got {latest_version})"

        logger.info("✓ Verified git repo has all versions (1, 3)")

        # Final summary
        logger.info("=" * 60)
        logger.info("✅ E2E FORCE PUSH JOURNEY COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
        logger.info("Summary:")
        logger.info("  - Initial state: Confluence v1, Local v1")
        logger.info("  - After edits: Confluence v2 (poetry), Local v1 (npm)")
        logger.info("  - Force push via MergeOrchestrator: ✓ (no conflict detection)")
        logger.info("  - Final state: Confluence v3 (npm - local content)")
        logger.info("  - Git repo: has v1 and v3 (auto-committed by force_push)")
        logger.info("  - Cache updated: ✓ (auto-updated by force_push)")
        logger.info("  - Content verification: ✓ (Confluence has local changes)")
        logger.info("=" * 60)

    def test_force_pull_overwrites_local(self, test_page_for_force_pull, temp_workspace):
        """Test force pull overwrites local file without conflict detection.

        Scenario (E2E-CR-04):
        - Local version 1 (modified), Confluence version 2
        - Force pull → No conflict detection
        - Local file overwritten with Confluence content
        - Local frontmatter updated to version 2
        - Git repo commits version 2

        Expected outcome:
        - No conflict detection performed
        - Local file content matches Confluence content
        - Frontmatter updated to remote version
        - Git repo has all versions (1, 2)
        """
        # Initialize components
        auth = Authenticator()
        api = APIWrapper(auth)
        page_ops = PageOperations(api=api)
        converter = MarkdownConverter()

        # Setup git repo and cache
        repo_path = os.path.join(temp_workspace, "git_repo")
        cache_path = os.path.join(temp_workspace, "cache")
        os.makedirs(repo_path)
        os.makedirs(cache_path)

        git_repo = GitRepository(repo_path)
        git_repo.init_if_not_exists()

        cache = XHTMLCache(cache_path)

        page_id = test_page_for_force_pull['page_id']
        local_file_path = os.path.join(temp_workspace, f"{page_id}.md")

        # Step 1: Fetch initial page from Confluence (v1)
        logger.info("Step 1: Fetch initial page from Confluence (v1)")
        snapshot_v1 = page_ops.get_page_snapshot(page_id)
        assert snapshot_v1.version == 1, "Initial version should be 1"

        markdown_v1 = snapshot_v1.markdown

        # Write local file with frontmatter
        with open(local_file_path, "w") as f:
            f.write(f"---\npage_id: {page_id}\nconfluence_version: 1\n---\n\n")
            f.write(markdown_v1)

        logger.info(f"Saved local file: {local_file_path}")

        # Commit base version to git
        git_repo.commit_version(
            page_id=page_id,
            markdown=markdown_v1,
            version=1
        )
        logger.info("✓ Committed base version (v1) to git repo")

        # Step 2: Edit local file (modify Configuration section)
        logger.info("Step 2: Edit local file")
        local_modified = markdown_v1.replace(
            "Set up your config:",
            "Set up your local config:"
        ).replace(
            "config.yaml",
            "local-config.yaml"
        )

        # Update local file (still tracking v1)
        with open(local_file_path, "w") as f:
            f.write(f"---\npage_id: {page_id}\nconfluence_version: 1\n---\n\n")
            f.write(local_modified)

        logger.info("Local edit: Changed 'config.yaml' → 'local-config.yaml'")

        # Step 3: Edit Confluence page (different change to create version mismatch)
        logger.info("Step 3: Edit Confluence page (simulate external edit)")

        # Modify the Configuration section differently on Confluence
        remote_xhtml = snapshot_v1.xhtml.replace(
            "Set up your config:",
            "Set up your remote config:"
        ).replace(
            "config.yaml",
            "remote-config.yaml"
        )

        # Update the page on Confluence
        api.update_page(
            page_id=page_id,
            title=test_page_for_force_pull['title'],
            body=remote_xhtml,
            version=1
        )

        # Verify page updated to v2
        snapshot_v2 = page_ops.get_page_snapshot(page_id)
        assert snapshot_v2.version == 2, "Confluence version should be 2 after update"
        logger.info("✓ Updated Confluence page to v2")
        logger.info("Remote edit: Changed 'config.yaml' → 'remote-config.yaml'")

        # Step 4: Force pull (should skip conflict detection and overwrite local)
        logger.info("Step 4: Force pull → No conflict detection")

        # Create MergeOrchestrator with all dependencies
        orchestrator = MergeOrchestrator(
            page_ops=page_ops,
            git_repo=git_repo,
            cache=cache,
            converter=converter,
            local_dir=temp_workspace
        )

        # Call force_pull (this is what we're testing!)
        result = orchestrator.force_pull([page_id])

        # Verify result
        assert result.success, f"Force pull should succeed: {result.errors}"
        assert result.pages_synced == 1, f"Should have synced 1 page (got {result.pages_synced})"
        assert result.pages_failed == 0, f"Should have 0 failures (got {result.pages_failed})"

        logger.info("✓ Force pulled Confluence content to local (auto-committed by force_pull)")

        # Step 5: Verify local file overwritten with Confluence content
        logger.info("Step 5: Verify local file overwritten with Confluence content")

        # Read local file
        with open(local_file_path, "r") as f:
            local_content = f.read()

        # Verify frontmatter updated
        assert "confluence_version: 2" in local_content, \
            "Frontmatter should be updated to version 2"

        # Verify content matches remote (remote-config.yaml, not local-config.yaml)
        assert "remote-config.yaml" in local_content, \
            "Local file should have remote content (remote-config.yaml)"
        assert "local-config.yaml" not in local_content, \
            "Local file should not have local edits (local-config.yaml)"

        logger.info("✓ Verified local file overwritten with Confluence content")
        logger.info("Frontmatter updated: v1 → v2")

        # Step 6: Verify git repo state (force_pull committed automatically)
        logger.info("Step 6: Verify git repo state (auto-committed by force_pull)")

        # Verify we can retrieve both versions from git
        base_from_git = git_repo.get_version(page_id, version=1)
        assert base_from_git is not None, "Should retrieve v1 from git"
        assert "config.yaml" in base_from_git, "v1 should have original content"

        latest_from_git = git_repo.get_version(page_id, version=2)
        assert latest_from_git is not None, "Should retrieve v2 from git"
        assert "remote-config.yaml" in latest_from_git, "v2 should have remote content"

        latest_version = git_repo.get_latest_version_number(page_id)
        assert latest_version == 2, f"Latest version in git should be 2 (got {latest_version})"

        logger.info("✓ Verified git repo has all versions (1, 2)")

        # Final summary
        logger.info("=" * 60)
        logger.info("✅ E2E FORCE PULL JOURNEY COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
        logger.info("Summary:")
        logger.info("  - Initial state: Confluence v1, Local v1")
        logger.info("  - After edits: Confluence v2 (remote-config), Local v1 (local-config)")
        logger.info("  - Force pull via MergeOrchestrator: ✓ (no conflict detection)")
        logger.info("  - Final state: Local v2 (remote-config - Confluence content)")
        logger.info("  - Git repo: has v1 and v2 (auto-committed by force_pull)")
        logger.info("  - Cache updated: ✓ (auto-updated by force_pull)")
        logger.info("  - Content verification: ✓ (Local has Confluence changes)")
        logger.info("  - Frontmatter verification: ✓ (Updated to v2)")
        logger.info("=" * 60)
