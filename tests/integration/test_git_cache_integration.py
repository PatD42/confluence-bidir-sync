"""Integration tests for GitRepository + XHTMLCache.

This module tests the integration between GitRepository and XHTMLCache to verify:
- Committing and retrieving markdown versions from git history
- Cache operations with git repository as fallback
- Round-trip persistence (commit to git, retrieve from cache/git)

Requirements:
- Temporary test directories (provided by fixtures)
- Real git operations (via subprocess)
- Real filesystem operations
- No external API calls (Confluence API mocked)
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from src.git_integration.git_repository import GitRepository
from src.git_integration.xhtml_cache import XHTMLCache
from src.git_integration.errors import GitRepositoryError, CacheError


@pytest.mark.integration
class TestGitCacheIntegration:
    """Integration tests for GitRepository + XHTMLCache."""

    @pytest.fixture(scope="function")
    def git_repo(self, temp_test_dir: Path) -> GitRepository:
        """Create a GitRepository in temporary directory.

        Args:
            temp_test_dir: Temporary test directory fixture

        Returns:
            Initialized GitRepository instance
        """
        repo_path = temp_test_dir / "test_repo_md"
        repo = GitRepository(str(repo_path))
        repo.init_if_not_exists()
        return repo

    @pytest.fixture(scope="function")
    def xhtml_cache(self, temp_test_dir: Path) -> XHTMLCache:
        """Create an XHTMLCache in temporary directory.

        Args:
            temp_test_dir: Temporary test directory fixture

        Returns:
            XHTMLCache instance
        """
        cache_dir = temp_test_dir / "test_cache_xhtml"
        return XHTMLCache(str(cache_dir), max_age_days=7)

    def test_commit_and_retrieve_version(
        self,
        git_repo: GitRepository,
        temp_test_dir: Path
    ):
        """Test committing markdown to git and retrieving it from history.

        Verifies:
        - Markdown content is committed to git repository
        - Committed version can be retrieved by version number
        - Content matches exactly after round-trip
        - Multiple versions are stored independently

        Args:
            git_repo: GitRepository fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "123456"
        markdown_v1 = "# Test Page\n\nThis is version 1."
        markdown_v2 = "# Test Page\n\nThis is version 2 with changes."

        # Act: Commit version 1
        sha1 = git_repo.commit_version(
            page_id=page_id,
            markdown=markdown_v1,
            version=1
        )

        # Assert: Commit succeeded
        assert sha1, "Commit should return SHA"
        assert len(sha1) == 40, "SHA should be 40 characters (full commit hash)"

        # Act: Commit version 2
        sha2 = git_repo.commit_version(
            page_id=page_id,
            markdown=markdown_v2,
            version=2
        )

        # Assert: Second commit succeeded
        assert sha2, "Second commit should return SHA"
        assert sha2 != sha1, "Second commit should have different SHA"

        # Act: Retrieve version 1 from git history
        retrieved_v1 = git_repo.get_version(page_id, 1)

        # Assert: Version 1 retrieved correctly
        assert retrieved_v1 is not None, "Version 1 should be found in git history"
        assert retrieved_v1 == markdown_v1, "Retrieved content should match committed content"

        # Act: Retrieve version 2 from git history
        retrieved_v2 = git_repo.get_version(page_id, 2)

        # Assert: Version 2 retrieved correctly
        assert retrieved_v2 is not None, "Version 2 should be found in git history"
        assert retrieved_v2 == markdown_v2, "Retrieved v2 content should match committed content"

        # Act: Try to retrieve non-existent version
        retrieved_v3 = git_repo.get_version(page_id, 3)

        # Assert: Non-existent version returns None
        assert retrieved_v3 is None, "Non-existent version should return None"

    def test_cache_then_git_fallback(
        self,
        git_repo: GitRepository,
        xhtml_cache: XHTMLCache,
        temp_test_dir: Path
    ):
        """Test cache miss triggers git repository fallback.

        Verifies:
        - XHTML is cached with correct metadata
        - Cache hit returns cached content
        - Cache invalidation clears cached content
        - After cache invalidation, git repo can provide fallback

        Args:
            git_repo: GitRepository fixture
            xhtml_cache: XHTMLCache fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "789012"
        version = 5
        markdown = "# Cached Page\n\nThis page will be cached."
        xhtml = "<h1>Cached Page</h1><p>This page will be cached.</p>"
        last_modified = datetime.now()

        # Arrange: Commit markdown to git (for fallback)
        git_repo.commit_version(
            page_id=page_id,
            markdown=markdown,
            version=version
        )

        # Act: Cache XHTML
        xhtml_cache.put(
            page_id=page_id,
            version=version,
            xhtml=xhtml,
            last_modified=last_modified
        )

        # Assert: Cache hit returns cached content
        cached_xhtml = xhtml_cache.get(
            page_id=page_id,
            version=version,
            last_modified=last_modified
        )
        assert cached_xhtml is not None, "Cache should return content on hit"
        assert cached_xhtml == xhtml, "Cached content should match original"

        # Act: Invalidate cache for this page
        xhtml_cache.invalidate(page_id)

        # Assert: Cache miss after invalidation
        cached_xhtml_after_invalidation = xhtml_cache.get(
            page_id=page_id,
            version=version,
            last_modified=last_modified
        )
        assert cached_xhtml_after_invalidation is None, "Cache should miss after invalidation"

        # Act: Retrieve from git as fallback
        markdown_from_git = git_repo.get_version(page_id, version)

        # Assert: Git fallback works
        assert markdown_from_git is not None, "Git should have the version"
        assert markdown_from_git == markdown, "Git content should match original markdown"

    def test_cache_timestamp_mismatch_with_git_fallback(
        self,
        git_repo: GitRepository,
        xhtml_cache: XHTMLCache,
        temp_test_dir: Path
    ):
        """Test cache miss due to timestamp mismatch, with git fallback.

        Verifies:
        - Cache miss when last_modified timestamp changes
        - Git repository provides correct content on cache miss
        - Cache and git work independently but complement each other

        Args:
            git_repo: GitRepository fixture
            xhtml_cache: XHTMLCache fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "345678"
        version = 10
        markdown = "# Timestamp Test\n\nTesting timestamp validation."
        xhtml = "<h1>Timestamp Test</h1><p>Testing timestamp validation.</p>"
        original_timestamp = datetime(2026, 1, 15, 10, 30, 0)
        updated_timestamp = datetime(2026, 1, 15, 11, 45, 0)

        # Arrange: Commit to git
        git_repo.commit_version(
            page_id=page_id,
            markdown=markdown,
            version=version
        )

        # Arrange: Cache with original timestamp
        xhtml_cache.put(
            page_id=page_id,
            version=version,
            xhtml=xhtml,
            last_modified=original_timestamp
        )

        # Act: Try to get from cache with different timestamp
        cached_xhtml = xhtml_cache.get(
            page_id=page_id,
            version=version,
            last_modified=updated_timestamp
        )

        # Assert: Cache miss due to timestamp mismatch
        assert cached_xhtml is None, "Cache should miss when timestamp doesn't match"

        # Act: Fall back to git repository
        markdown_from_git = git_repo.get_version(page_id, version)

        # Assert: Git provides correct content
        assert markdown_from_git is not None, "Git should have the version"
        assert markdown_from_git == markdown, "Git content should be correct"

    def test_multiple_pages_git_and_cache(
        self,
        git_repo: GitRepository,
        xhtml_cache: XHTMLCache,
        temp_test_dir: Path
    ):
        """Test multiple pages managed by git and cache together.

        Verifies:
        - Multiple pages can be committed to git independently
        - Each page can have its own cache entries
        - Git and cache don't interfere with each other
        - Retrieval works correctly for all pages

        Args:
            git_repo: GitRepository fixture
            xhtml_cache: XHTMLCache fixture
            temp_test_dir: Temporary test directory fixture
        """
        # Arrange: Multiple pages
        pages = [
            {
                "page_id": "111111",
                "version": 1,
                "markdown": "# Page 1\n\nFirst page.",
                "xhtml": "<h1>Page 1</h1><p>First page.</p>",
                "last_modified": datetime(2026, 1, 20, 10, 0, 0)
            },
            {
                "page_id": "222222",
                "version": 3,
                "markdown": "# Page 2\n\nSecond page.",
                "xhtml": "<h1>Page 2</h1><p>Second page.</p>",
                "last_modified": datetime(2026, 1, 21, 14, 30, 0)
            },
            {
                "page_id": "333333",
                "version": 7,
                "markdown": "# Page 3\n\nThird page.",
                "xhtml": "<h1>Page 3</h1><p>Third page.</p>",
                "last_modified": datetime(2026, 1, 22, 9, 15, 0)
            },
        ]

        # Act: Commit all pages to git and cache
        for page in pages:
            git_repo.commit_version(
                page_id=page["page_id"],
                markdown=page["markdown"],
                version=page["version"]
            )
            xhtml_cache.put(
                page_id=page["page_id"],
                version=page["version"],
                xhtml=page["xhtml"],
                last_modified=page["last_modified"]
            )

        # Assert: All pages retrievable from git
        for page in pages:
            markdown_from_git = git_repo.get_version(page["page_id"], page["version"])
            assert markdown_from_git is not None, f"Git should have page {page['page_id']}"
            assert markdown_from_git == page["markdown"], f"Git content should match for page {page['page_id']}"

        # Assert: All pages retrievable from cache
        for page in pages:
            xhtml_from_cache = xhtml_cache.get(
                page_id=page["page_id"],
                version=page["version"],
                last_modified=page["last_modified"]
            )
            assert xhtml_from_cache is not None, f"Cache should have page {page['page_id']}"
            assert xhtml_from_cache == page["xhtml"], f"Cache content should match for page {page['page_id']}"

        # Act: Invalidate one page's cache
        xhtml_cache.invalidate("222222")

        # Assert: Invalidated page's cache is empty
        cached_after_invalidation = xhtml_cache.get(
            page_id="222222",
            version=3,
            last_modified=datetime(2026, 1, 21, 14, 30, 0)
        )
        assert cached_after_invalidation is None, "Invalidated page should not be in cache"

        # Assert: Other pages' caches are still intact
        cache_page_1 = xhtml_cache.get(
            page_id="111111",
            version=1,
            last_modified=datetime(2026, 1, 20, 10, 0, 0)
        )
        assert cache_page_1 is not None, "Other pages' cache should be intact"

        # Assert: Git still has all pages (including invalidated cache)
        for page in pages:
            markdown_from_git = git_repo.get_version(page["page_id"], page["version"])
            assert markdown_from_git is not None, f"Git should still have page {page['page_id']}"

    def test_git_latest_version_with_cache(
        self,
        git_repo: GitRepository,
        xhtml_cache: XHTMLCache,
        temp_test_dir: Path
    ):
        """Test getting latest version from git while managing cache.

        Verifies:
        - get_latest_version_number() works correctly
        - Cache can store multiple versions of same page
        - Latest version identification is accurate

        Args:
            git_repo: GitRepository fixture
            xhtml_cache: XHTMLCache fixture
            temp_test_dir: Temporary test directory fixture
        """
        page_id = "999999"

        # Act: Commit multiple versions to git
        for version in [1, 3, 5, 7, 10]:
            markdown = f"# Version {version}\n\nThis is version {version}."
            git_repo.commit_version(
                page_id=page_id,
                markdown=markdown,
                version=version
            )

            # Cache each version
            xhtml = f"<h1>Version {version}</h1><p>This is version {version}.</p>"
            xhtml_cache.put(
                page_id=page_id,
                version=version,
                xhtml=xhtml,
                last_modified=datetime.now()
            )

        # Act: Get latest version number from git
        latest_version = git_repo.get_latest_version_number(page_id)

        # Assert: Latest version is correct
        assert latest_version == 10, "Latest version should be 10"

        # Act: Retrieve latest version content
        latest_markdown = git_repo.get_version(page_id, latest_version)

        # Assert: Content is correct
        assert latest_markdown is not None, "Latest version should exist in git"
        assert "Version 10" in latest_markdown, "Content should be from version 10"

        # Act: Retrieve older versions
        v1 = git_repo.get_version(page_id, 1)
        v5 = git_repo.get_version(page_id, 5)

        # Assert: All versions are accessible
        assert v1 is not None, "Version 1 should be accessible"
        assert "Version 1" in v1, "Version 1 content should be correct"
        assert v5 is not None, "Version 5 should be accessible"
        assert "Version 5" in v5, "Version 5 content should be correct"
