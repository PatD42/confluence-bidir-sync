"""Unit tests for git_integration.xhtml_cache module."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.git_integration.errors import CacheError
from src.git_integration.xhtml_cache import XHTMLCache


class TestXHTMLCachePut:
    """Test cases for XHTMLCache.put() method."""

    def test_put_creates_files(self):
        """XHTMLCache.put() should create both XHTML and metadata files."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)
            page_id = "123456"
            version = 15
            xhtml_content = "<p>Test content</p>"
            last_modified = datetime(2026, 1, 30, 12, 0, 0)

            # Act
            cache.put(page_id, version, xhtml_content, last_modified)

            # Assert - XHTML file created
            xhtml_path = os.path.join(cache_dir, f"{page_id}_v{version}.xhtml")
            assert os.path.exists(xhtml_path)
            with open(xhtml_path, "r", encoding="utf-8") as f:
                assert f.read() == xhtml_content

            # Assert - Metadata file created
            meta_path = os.path.join(cache_dir, f"{page_id}_v{version}.meta.json")
            assert os.path.exists(meta_path)
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                assert metadata["last_modified"] == last_modified.isoformat()
                assert "cached_at" in metadata

    def test_put_raises_cache_error_on_write_failure(self):
        """XHTMLCache.put() should raise CacheError if write fails."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)
            page_id = "123456"
            version = 15
            xhtml_content = "<p>Test</p>"
            last_modified = datetime.now()

            # Make cache directory read-only to force write failure
            os.chmod(cache_dir, 0o444)

            # Act & Assert
            try:
                with pytest.raises(CacheError) as exc_info:
                    cache.put(page_id, version, xhtml_content, last_modified)
                assert cache_dir in str(exc_info.value)
            finally:
                # Restore permissions for cleanup
                os.chmod(cache_dir, 0o755)


class TestXHTMLCacheGet:
    """Test cases for XHTMLCache.get() method."""

    def test_get_cache_hit(self):
        """XHTMLCache.get() should return XHTML when timestamps match."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)
            page_id = "123456"
            version = 15
            xhtml_content = "<p>Test content</p>"
            last_modified = datetime(2026, 1, 30, 12, 0, 0)

            # Put content in cache
            cache.put(page_id, version, xhtml_content, last_modified)

            # Act - retrieve with same timestamp
            result = cache.get(page_id, version, last_modified)

            # Assert
            assert result == xhtml_content

    def test_get_cache_miss_timestamp(self):
        """XHTMLCache.get() should return None when timestamp mismatched."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)
            page_id = "123456"
            version = 15
            xhtml_content = "<p>Test content</p>"
            original_last_modified = datetime(2026, 1, 30, 12, 0, 0)

            # Put content in cache
            cache.put(page_id, version, xhtml_content, original_last_modified)

            # Act - retrieve with different timestamp
            different_last_modified = datetime(2026, 1, 30, 13, 0, 0)
            result = cache.get(page_id, version, different_last_modified)

            # Assert
            assert result is None

    def test_get_cache_miss_not_found(self):
        """XHTMLCache.get() should return None when file doesn't exist."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)
            page_id = "999999"
            version = 99
            last_modified = datetime.now()

            # Act - try to get non-existent cache entry
            result = cache.get(page_id, version, last_modified)

            # Assert
            assert result is None

    def test_get_cache_miss_max_age_exceeded(self):
        """XHTMLCache.get() should return None when entry too old."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir, max_age_days=7)
            page_id = "123456"
            version = 15
            xhtml_content = "<p>Old content</p>"
            last_modified = datetime(2026, 1, 30, 12, 0, 0)

            # Mock cached_at to be 8 days ago
            old_cached_at = datetime.now() - timedelta(days=8)
            with patch("src.git_integration.xhtml_cache.datetime") as mock_datetime:
                mock_datetime.now.return_value = old_cached_at
                mock_datetime.fromisoformat = datetime.fromisoformat
                cache.put(page_id, version, xhtml_content, last_modified)

            # Act - try to get old cache entry
            result = cache.get(page_id, version, last_modified)

            # Assert
            assert result is None


class TestXHTMLCacheCorruptedMetadata:
    """Test cases for corrupted metadata handling."""

    def test_corrupted_metadata_raises_cache_error(self):
        """XHTMLCache.get() should raise CacheError on JSON parse error."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)
            page_id = "123456"
            version = 15

            # Create XHTML file
            xhtml_path = os.path.join(cache_dir, f"{page_id}_v{version}.xhtml")
            with open(xhtml_path, "w", encoding="utf-8") as f:
                f.write("<p>Test</p>")

            # Create corrupted metadata file
            meta_path = os.path.join(cache_dir, f"{page_id}_v{version}.meta.json")
            with open(meta_path, "w", encoding="utf-8") as f:
                f.write("{invalid json")

            # Act & Assert
            with pytest.raises(CacheError) as exc_info:
                cache.get(page_id, version, datetime.now())
            assert "Failed to read or parse metadata" in str(exc_info.value)
            assert meta_path in str(exc_info.value)

    def test_missing_metadata_fields_raises_cache_error(self):
        """XHTMLCache.get() should raise CacheError if metadata missing required fields."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)
            page_id = "123456"
            version = 15

            # Create XHTML file
            xhtml_path = os.path.join(cache_dir, f"{page_id}_v{version}.xhtml")
            with open(xhtml_path, "w", encoding="utf-8") as f:
                f.write("<p>Test</p>")

            # Create metadata with missing fields
            meta_path = os.path.join(cache_dir, f"{page_id}_v{version}.meta.json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"cached_at": datetime.now().isoformat()}, f)

            # Act & Assert
            with pytest.raises(CacheError) as exc_info:
                cache.get(page_id, version, datetime.now())
            assert "Failed to read or parse metadata" in str(exc_info.value)


class TestXHTMLCacheInvalidate:
    """Test cases for XHTMLCache.invalidate() method."""

    def test_invalidate_deletes_files(self):
        """XHTMLCache.invalidate() should delete XHTML and metadata files."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)
            page_id = "123456"
            last_modified = datetime.now()

            # Create multiple versions
            cache.put(page_id, 15, "<p>v15</p>", last_modified)
            cache.put(page_id, 16, "<p>v16</p>", last_modified)
            cache.put(page_id, 17, "<p>v17</p>", last_modified)

            # Verify files exist
            assert os.path.exists(os.path.join(cache_dir, f"{page_id}_v15.xhtml"))
            assert os.path.exists(os.path.join(cache_dir, f"{page_id}_v15.meta.json"))
            assert os.path.exists(os.path.join(cache_dir, f"{page_id}_v16.xhtml"))
            assert os.path.exists(os.path.join(cache_dir, f"{page_id}_v17.xhtml"))

            # Act
            cache.invalidate(page_id)

            # Assert - all files for this page_id deleted
            assert not os.path.exists(os.path.join(cache_dir, f"{page_id}_v15.xhtml"))
            assert not os.path.exists(os.path.join(cache_dir, f"{page_id}_v15.meta.json"))
            assert not os.path.exists(os.path.join(cache_dir, f"{page_id}_v16.xhtml"))
            assert not os.path.exists(os.path.join(cache_dir, f"{page_id}_v16.meta.json"))
            assert not os.path.exists(os.path.join(cache_dir, f"{page_id}_v17.xhtml"))
            assert not os.path.exists(os.path.join(cache_dir, f"{page_id}_v17.meta.json"))

    def test_invalidate_only_deletes_matching_page(self):
        """XHTMLCache.invalidate() should only delete files for specified page."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)
            last_modified = datetime.now()

            # Create entries for two different pages
            cache.put("123456", 15, "<p>Page A</p>", last_modified)
            cache.put("789012", 15, "<p>Page B</p>", last_modified)

            # Act - invalidate only first page
            cache.invalidate("123456")

            # Assert - first page deleted, second page preserved
            assert not os.path.exists(os.path.join(cache_dir, "123456_v15.xhtml"))
            assert os.path.exists(os.path.join(cache_dir, "789012_v15.xhtml"))
            assert os.path.exists(os.path.join(cache_dir, "789012_v15.meta.json"))

    def test_invalidate_nonexistent_page_succeeds(self):
        """XHTMLCache.invalidate() should not error on non-existent page."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)

            # Act & Assert - should not raise
            cache.invalidate("999999")


class TestXHTMLCacheClearAll:
    """Test cases for XHTMLCache.clear_all() method."""

    def test_clear_all_deletes_all_cache_files(self):
        """XHTMLCache.clear_all() should delete all XHTML and metadata files."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)
            last_modified = datetime.now()

            # Create multiple pages and versions
            cache.put("123456", 15, "<p>Page A v15</p>", last_modified)
            cache.put("123456", 16, "<p>Page A v16</p>", last_modified)
            cache.put("789012", 10, "<p>Page B v10</p>", last_modified)
            cache.put("789012", 11, "<p>Page B v11</p>", last_modified)

            # Verify files exist
            cache_path = Path(cache_dir)
            files_before = list(cache_path.glob("*"))
            assert len(files_before) == 8  # 4 xhtml + 4 meta.json

            # Act
            cache.clear_all()

            # Assert - all cache files deleted
            files_after = list(cache_path.glob("*.xhtml"))
            meta_files_after = list(cache_path.glob("*.meta.json"))
            assert len(files_after) == 0
            assert len(meta_files_after) == 0

    def test_clear_all_preserves_non_cache_files(self):
        """XHTMLCache.clear_all() should preserve non-cache files."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)
            last_modified = datetime.now()

            # Create cache files
            cache.put("123456", 15, "<p>Test</p>", last_modified)

            # Create non-cache file
            readme_path = os.path.join(cache_dir, "README.txt")
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("This is not a cache file")

            # Act
            cache.clear_all()

            # Assert - cache files deleted, README preserved
            assert not os.path.exists(os.path.join(cache_dir, "123456_v15.xhtml"))
            assert not os.path.exists(os.path.join(cache_dir, "123456_v15.meta.json"))
            assert os.path.exists(readme_path)

    def test_clear_all_on_empty_cache_succeeds(self):
        """XHTMLCache.clear_all() should not error on empty cache."""
        with tempfile.TemporaryDirectory() as cache_dir:
            # Arrange
            cache = XHTMLCache(cache_dir)

            # Act & Assert - should not raise
            cache.clear_all()


class TestXHTMLCacheInitialization:
    """Test cases for XHTMLCache initialization."""

    def test_init_creates_cache_directory(self):
        """XHTMLCache.__init__() should create cache directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            cache_dir = os.path.join(temp_dir, "new_cache_dir")
            assert not os.path.exists(cache_dir)

            # Act
            cache = XHTMLCache(cache_dir)

            # Assert
            assert os.path.exists(cache_dir)
            assert os.path.isdir(cache_dir)

    def test_init_converts_relative_path_to_absolute(self):
        """XHTMLCache.__init__() should convert relative path to absolute."""
        # Arrange
        relative_path = "./test_cache"

        # Act
        cache = XHTMLCache(relative_path)

        # Assert
        assert os.path.isabs(cache.cache_dir)

    def test_init_raises_cache_error_on_permission_denied(self):
        """XHTMLCache.__init__() should raise CacheError if directory creation fails."""
        # Arrange - try to create directory in read-only location
        # Using /dev/null as a non-creatable directory path
        invalid_cache_dir = "/dev/null/cache"

        # Act & Assert
        with pytest.raises(CacheError) as exc_info:
            XHTMLCache(invalid_cache_dir)
        assert "Failed to create cache directory" in str(exc_info.value)
