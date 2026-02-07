"""XHTML caching layer for Confluence pages.

This module provides the XHTMLCache class for caching XHTML content from
Confluence pages to minimize API calls. It validates cached entries using
last_modified timestamps and supports automatic cleanup of old entries.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.git_integration.errors import CacheError

logger = logging.getLogger(__name__)


class XHTMLCache:
    """Manages XHTML cache with timestamp validation.

    This class handles caching of XHTML content for Confluence pages to reduce
    API calls. Each cache entry consists of two files:
    - {page_id}_v{version}.xhtml: The XHTML content
    - {page_id}_v{version}.meta.json: Metadata (last_modified, cached_at)

    Cache validation is based on Confluence's last_modified timestamp. If the
    timestamp matches, the cached content is valid.

    File structure:
        .confluence-sync/MYSPACE_xhtml/
          123456_v15.xhtml       # XHTML content
          123456_v15.meta.json   # {"last_modified": "...", "cached_at": "..."}
          123456_v16.xhtml
          123456_v16.meta.json

    Example:
        >>> cache = XHTMLCache(".confluence-sync/MYSPACE_xhtml")
        >>> xhtml = cache.get("123456", 15, datetime.now())
        >>> if xhtml is None:
        ...     # Cache miss - fetch from API
        ...     cache.put("123456", 15, xhtml_content, datetime.now())
    """

    def __init__(self, cache_dir: str, max_age_days: int = 7):
        """Initialize XHTML cache.

        Args:
            cache_dir: Cache directory (e.g., .confluence-sync/MYSPACE_xhtml)
            max_age_days: Max age before re-fetch (default: 7 days)
        """
        self.cache_dir = cache_dir
        self.max_age_days = max_age_days
        self._ensure_absolute_path()
        self._ensure_cache_dir_exists()

    def _ensure_absolute_path(self) -> None:
        """Convert cache_dir to absolute path if relative."""
        if not os.path.isabs(self.cache_dir):
            self.cache_dir = os.path.abspath(self.cache_dir)

    def _ensure_cache_dir_exists(self) -> None:
        """Create cache directory if it doesn't exist."""
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            logger.debug(f"Cache directory ready: {self.cache_dir}")
        except OSError as e:
            raise CacheError(
                cache_path=self.cache_dir,
                message=f"Failed to create cache directory: {e}",
            )

    def _get_cache_paths(self, page_id: str, version: int) -> tuple[str, str]:
        """Get file paths for XHTML and metadata.

        Args:
            page_id: Confluence page ID
            version: Version number

        Returns:
            Tuple of (xhtml_path, meta_path)
        """
        base_name = f"{page_id}_v{version}"
        xhtml_path = os.path.join(self.cache_dir, f"{base_name}.xhtml")
        meta_path = os.path.join(self.cache_dir, f"{base_name}.meta.json")
        return xhtml_path, meta_path

    def get(
        self,
        page_id: str,
        version: int,
        last_modified: datetime,
    ) -> Optional[str]:
        """Retrieve XHTML from cache if valid.

        Validates cache entry by:
        1. Checking if files exist
        2. Verifying last_modified matches Confluence timestamp
        3. Ensuring cached_at is within max_age_days

        Args:
            page_id: Confluence page ID
            version: Version number
            last_modified: Confluence last_modified timestamp

        Returns:
            Cached XHTML if valid, None if cache miss

        Raises:
            CacheError: If cache file corrupted
        """
        xhtml_path, meta_path = self._get_cache_paths(page_id, version)

        # Check if cache files exist
        if not os.path.exists(xhtml_path) or not os.path.exists(meta_path):
            logger.debug(f"Cache miss: files not found for page {page_id} v{version}")
            return None

        # Load and validate metadata
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            cached_last_modified = datetime.fromisoformat(metadata["last_modified"])
            cached_at = datetime.fromisoformat(metadata["cached_at"])

        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            raise CacheError(
                cache_path=meta_path,
                message=f"Failed to read or parse metadata: {e}",
            )

        # Validate last_modified matches
        if cached_last_modified != last_modified:
            logger.debug(
                f"Cache miss: last_modified mismatch for page {page_id} v{version}"
            )
            return None

        # Check max age
        age = datetime.now() - cached_at
        if age > timedelta(days=self.max_age_days):
            logger.debug(
                f"Cache miss: entry too old ({age.days} days) for page {page_id} v{version}"
            )
            return None

        # Load XHTML content
        try:
            with open(xhtml_path, "r", encoding="utf-8") as f:
                xhtml = f.read()

            logger.debug(f"Cache hit: page {page_id} v{version}")
            return xhtml

        except OSError as e:
            raise CacheError(
                cache_path=xhtml_path,
                message=f"Failed to read XHTML content: {e}",
            )

    def put(
        self,
        page_id: str,
        version: int,
        xhtml: str,
        last_modified: datetime,
    ) -> None:
        """Store XHTML in cache.

        Creates two files:
        - {page_id}_v{version}.xhtml: XHTML content
        - {page_id}_v{version}.meta.json: Metadata with last_modified and cached_at

        Args:
            page_id: Confluence page ID
            version: Version number
            xhtml: XHTML content to cache
            last_modified: Confluence last_modified timestamp

        Raises:
            CacheError: If write fails
        """
        xhtml_path, meta_path = self._get_cache_paths(page_id, version)

        # Write XHTML content
        try:
            with open(xhtml_path, "w", encoding="utf-8") as f:
                f.write(xhtml)
        except OSError as e:
            raise CacheError(
                cache_path=xhtml_path,
                message=f"Failed to write XHTML content: {e}",
            )

        # Write metadata
        metadata = {
            "last_modified": last_modified.isoformat(),
            "cached_at": datetime.now().isoformat(),
        }

        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except OSError as e:
            # Try to clean up XHTML file if metadata write fails
            try:
                os.remove(xhtml_path)
            except OSError:
                pass

            raise CacheError(
                cache_path=meta_path,
                message=f"Failed to write metadata: {e}",
            )

        logger.info(f"Cached page {page_id} v{version}")

    def invalidate(self, page_id: str) -> None:
        """Delete all cache entries for page.

        Removes all {page_id}_v*.xhtml and {page_id}_v*.meta.json files.

        Args:
            page_id: Confluence page ID
        """
        pattern = f"{page_id}_v*"
        cache_path = Path(self.cache_dir)

        deleted_count = 0
        for file_path in cache_path.glob(pattern):
            try:
                file_path.unlink()
                deleted_count += 1
            except OSError as e:
                logger.warning(f"Failed to delete cache file {file_path}: {e}")

        if deleted_count > 0:
            logger.info(f"Invalidated {deleted_count} cache entries for page {page_id}")
        else:
            logger.debug(f"No cache entries found for page {page_id}")

    def clear_all(self) -> None:
        """Delete all cache entries (all pages).

        Removes all .xhtml and .meta.json files from cache directory.
        """
        cache_path = Path(self.cache_dir)

        deleted_count = 0
        for file_path in cache_path.glob("*"):
            if file_path.is_file() and (
                file_path.suffix == ".xhtml" or file_path.name.endswith(".meta.json")
            ):
                try:
                    file_path.unlink()
                    deleted_count += 1
                except OSError as e:
                    logger.warning(f"Failed to delete cache file {file_path}: {e}")

        logger.info(f"Cleared cache: deleted {deleted_count} files")
