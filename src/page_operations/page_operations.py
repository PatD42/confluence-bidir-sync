"""Page operations for surgical Confluence updates.

This module provides the main PageOperations class that orchestrates
reading, writing, and creating Confluence pages with support for
surgical XHTML updates.
"""

import logging
import time
from datetime import datetime
from typing import List, Optional

from ..confluence_client.api_wrapper import APIWrapper
from ..confluence_client.auth import Authenticator
from ..confluence_client.errors import (
    APIAccessError,
    PageNotFoundError,
)
from ..content_converter.markdown_converter import MarkdownConverter
from .models import (
    BlockType,
    ContentBlock,
    CreateResult,
    PageSnapshot,
    PageVersion,
    SurgicalOperation,
    UpdateResult,
)
from .surgical_editor import SurgicalEditor
from .content_parser import ContentParser
from .diff_analyzer import DiffAnalyzer
from .macro_preserver import MacroPreserver
from .adf_models import AdfDocument, AdfNodeType, AdfUpdateResult
from .adf_parser import AdfParser, adf_block_type_to_content_block_type
from .adf_editor import AdfEditor

logger = logging.getLogger(__name__)


class PageOperations:
    """High-level page operations with surgical update support.

    Provides read, write, and create operations for Confluence pages.
    The key feature is surgical updates: applying discrete operations
    to XHTML while preserving Confluence-specific formatting.

    Usage:
        ops = PageOperations()

        # Read page with both XHTML and markdown
        snapshot = ops.get_page_snapshot(page_id)

        # Apply surgical operations (operations from external diff)
        result = ops.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,
            base_version=snapshot.version,
            operations=[...]
        )

        # Create new page from markdown
        result = ops.create_page(
            space_key="TEAM",
            title="New Page",
            markdown_content="# Hello\\n\\nWorld",
            parent_id="12345"
        )
    """

    def __init__(self, api: Optional[APIWrapper] = None):
        """Initialize PageOperations with optional API wrapper.

        Args:
            api: APIWrapper instance. If None, creates one with
                 default authentication.
        """
        if api is None:
            auth = Authenticator()
            api = APIWrapper(auth)
        self.api = api
        self.converter = MarkdownConverter()
        self.surgical_editor = SurgicalEditor()
        self.content_parser = ContentParser()
        self.diff_analyzer = DiffAnalyzer()
        self.macro_preserver = MacroPreserver()
        # ADF surgical update components
        self.adf_parser = AdfParser()
        self.adf_editor = AdfEditor()

    def _retry_on_version_conflict(
        self,
        operation_func,
        max_retries: int = 3,
        base_delay: float = 1.0
    ):
        """Retry an operation with exponential backoff on version conflicts.

        This implements H3: automatic retry with exponential backoff when
        version conflicts occur during page updates.

        Args:
            operation_func: Function to execute. Should return UpdateResult.
            max_retries: Maximum number of retry attempts (default: 3)
            base_delay: Base delay in seconds for exponential backoff (default: 1.0)

        Returns:
            UpdateResult from operation_func

        The retry delays follow exponential backoff:
        - Attempt 1: immediate
        - Attempt 2: 1s delay
        - Attempt 3: 2s delay
        - Attempt 4: 4s delay
        """
        for attempt in range(max_retries + 1):
            result = operation_func()

            # If successful or non-version-conflict error, return
            if result.success:
                if attempt > 0:
                    logger.info(f"Operation succeeded after {attempt} retries")
                return result

            # Check if it's a version conflict error
            error_msg = (result.error or "").lower()
            is_version_conflict = (
                "version conflict" in error_msg or
                "conflict" in error_msg or
                "was modified" in error_msg
            )

            if not is_version_conflict:
                # Non-version-conflict error, don't retry
                return result

            # Version conflict - retry if we have attempts left
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                logger.warning(
                    f"Version conflict detected (attempt {attempt + 1}/{max_retries + 1}). "
                    f"Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                # Out of retries
                logger.error(
                    f"Version conflict persists after {max_retries} retries. Giving up."
                )
                return result

        return result

    def get_page_snapshot(
        self, page_id: str, version: Optional[int] = None
    ) -> PageSnapshot:
        """Fetch a page with both XHTML and markdown representations.

        The returned PageSnapshot contains:
        - xhtml: Original XHTML (reference for surgical updates)
        - markdown: Converted markdown (for agents/tools)

        Args:
            page_id: Confluence page ID
            version: Specific version to fetch. None for current version.

        Returns:
            PageSnapshot with complete page state

        Raises:
            PageNotFoundError: If page doesn't exist
            APIAccessError: If API call fails
        """
        # Validate input
        if not page_id or not str(page_id).strip():
            raise ValueError("page_id cannot be empty")

        logger.debug(f"Fetching page snapshot: {page_id}" +
                   (f" (version {version})" if version else ""))

        # Fetch page from API
        expand = "body.storage,version,metadata.labels,ancestors"
        if version:
            # Use version history API for specific versions
            page_data = self.api.get_page_version(page_id, version)
        else:
            page_data = self.api.get_page_by_id(page_id, expand=expand)

        # Extract data
        title = page_data.get("title", "")
        space_key = page_data.get("spaceKey", "")
        if not space_key:
            # Try to get from space object
            space = page_data.get("space", {})
            space_key = space.get("key", "")

        xhtml = page_data.get("body", {}).get("storage", {}).get("value", "")
        ver = page_data.get("version", {}).get("number", 1)

        # Get last_modified timestamp from version.when
        last_modified_str = page_data.get("version", {}).get("when", "")
        if last_modified_str:
            # Parse ISO 8601 timestamp from Confluence
            # Remove timezone suffix if present for Python 3.7+ compatibility
            try:
                # Try parsing with timezone (Python 3.11+)
                last_modified = datetime.fromisoformat(last_modified_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                # Fallback: strip timezone and parse
                import re
                clean_ts = re.sub(r'[+-]\d{2}:\d{2}$|Z$', '', last_modified_str)
                last_modified = datetime.fromisoformat(clean_ts)
        else:
            # Fallback to current time if not available
            last_modified = datetime.now()

        # Get labels
        labels_data = page_data.get("metadata", {}).get("labels", {}).get("results", [])
        labels = [label.get("name", "") for label in labels_data]

        # Get parent ID
        ancestors = page_data.get("ancestors", [])
        parent_id = ancestors[-1].get("id") if ancestors else None

        # Convert XHTML to markdown (preserving macros as placeholders)
        xhtml_no_macros, macros = self._preserve_macros_for_markdown(xhtml)
        markdown = self.converter.xhtml_to_markdown(xhtml_no_macros)

        # Restore macro placeholders in markdown
        markdown = self._add_macro_placeholders(markdown, macros)

        logger.debug(f"  Fetched: {title} (v{ver}, {len(xhtml)} chars XHTML)")

        return PageSnapshot(
            page_id=page_id,
            space_key=space_key,
            title=title,
            xhtml=xhtml,
            markdown=markdown,
            version=ver,
            parent_id=parent_id,
            labels=labels,
            last_modified=last_modified,
        )

    def get_page_versions(self, page_id: str) -> List[PageVersion]:
        """List available versions for a page.

        Args:
            page_id: Confluence page ID

        Returns:
            List of PageVersion objects with version metadata

        Raises:
            PageNotFoundError: If page doesn't exist
            APIAccessError: If API call fails
        """
        logger.debug(f"Fetching version history: {page_id}")

        versions_data = self.api.get_page_versions(page_id)
        versions = []

        for v in versions_data:
            ver_num = v.get("number", 0)
            when = v.get("when", "")
            by = v.get("by", {}).get("displayName", "Unknown")
            message = v.get("message", None)

            # Parse datetime
            try:
                modified_at = datetime.fromisoformat(when.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                modified_at = datetime.now()

            versions.append(
                PageVersion(
                    version=ver_num,
                    modified_at=modified_at,
                    modified_by=by,
                    message=message,
                )
            )

        logger.debug(f"  Found {len(versions)} versions")
        return versions

    def _apply_operations_once(
        self,
        page_id: str,
        base_xhtml: str,
        base_version: int,
        operations: List[SurgicalOperation],
    ) -> UpdateResult:
        """Apply surgical operations to a page (single attempt, no retry).

        Internal helper for apply_operations. Performs one attempt to apply
        operations and update the page.

        Args:
            page_id: Confluence page ID
            base_xhtml: Original XHTML to apply operations to
            base_version: Version number for optimistic locking
            operations: List of surgical operations to apply

        Returns:
            UpdateResult with success status and new version
        """
        logger.debug(f"Applying {len(operations)} operations to page {page_id}")

        # Count macros before
        macros_before = self.surgical_editor.count_macros(base_xhtml)

        # Apply operations
        modified_xhtml, success_count, failure_count = self.surgical_editor.apply_operations(
            base_xhtml, operations
        )

        if failure_count > 0:
            logger.warning(
                f"  {failure_count}/{len(operations)} operations failed to apply"
            )

        # Count macros after (verify preservation)
        macros_after = self.surgical_editor.count_macros(modified_xhtml)
        if macros_after != macros_before:
            logger.warning(
                f"  Macro count changed: {macros_before} → {macros_after}"
            )

        # Get current page title
        page_data = self.api.get_page_by_id(page_id, expand="version")
        title = page_data.get("title", "")
        current_version = page_data.get("version", {}).get("number", 0)

        # Check version conflict
        if current_version != base_version:
            logger.error(
                f"  Version conflict: expected {base_version}, found {current_version}"
            )
            return UpdateResult(
                success=False,
                page_id=page_id,
                old_version=base_version,
                new_version=current_version,
                operations_applied=0,
                error=f"Version conflict: page was modified (v{base_version} → v{current_version})",
            )

        # Upload modified content
        try:
            result = self.api.update_page(
                page_id=page_id,
                title=title,
                body=modified_xhtml,
                version=base_version,
            )
            new_version = result.get("version", {}).get("number", base_version + 1)

            logger.debug(f"  Updated: v{base_version} → v{new_version}")

            return UpdateResult(
                success=True,
                page_id=page_id,
                old_version=base_version,
                new_version=new_version,
                operations_applied=len(operations),
                modified_xhtml=modified_xhtml,
            )

        except APIAccessError as e:
            error_msg = str(e).lower()
            if "conflict" in error_msg or "version" in error_msg:
                logger.error(f"  Version conflict during upload: {e}")
            else:
                logger.error(f"  API error during upload: {e}")
            return UpdateResult(
                success=False,
                page_id=page_id,
                old_version=base_version,
                new_version=base_version,
                operations_applied=0,
                error=str(e),
            )

    def apply_operations(
        self,
        page_id: str,
        base_xhtml: str,
        base_version: int,
        operations: List[SurgicalOperation],
    ) -> UpdateResult:
        """Apply surgical operations to a page with automatic retry on version conflicts.

        Implements H3: Automatic retry with exponential backoff when version
        conflicts occur. On conflict, re-fetches the current page version and
        reapplies operations.

        Takes the original XHTML (from a PageSnapshot), applies the
        operations, and uploads the result to Confluence.

        Args:
            page_id: Confluence page ID
            base_xhtml: Original XHTML to apply operations to
            base_version: Version number for optimistic locking
            operations: List of surgical operations to apply

        Returns:
            UpdateResult with success status and new version

        Raises:
            APIAccessError: If API call fails (non-version-conflict errors)
        """
        # Store original inputs for potential retries
        original_operations = operations

        def attempt_update():
            # On retry, we need to re-fetch the current page state
            nonlocal base_xhtml, base_version

            # Get current page state if this is a retry attempt
            # (first attempt uses provided base_xhtml and base_version)
            if attempt_update.retry_count > 0:
                logger.info(
                    f"Re-fetching page {page_id} for retry attempt {attempt_update.retry_count + 1}"
                )
                try:
                    page_data = self.api.get_page_by_id(page_id, expand="body.storage,version")
                    base_xhtml = page_data.get("body", {}).get("storage", {}).get("value", "")
                    base_version = page_data.get("version", {}).get("number", 0)
                    logger.debug(f"  Fetched current version: {base_version}")
                except Exception as e:
                    logger.error(f"Failed to re-fetch page for retry: {e}")
                    return UpdateResult(
                        success=False,
                        page_id=page_id,
                        old_version=base_version,
                        new_version=base_version,
                        operations_applied=0,
                        error=f"Failed to re-fetch page for retry: {str(e)}",
                    )

            # Attempt the update
            result = self._apply_operations_once(
                page_id=page_id,
                base_xhtml=base_xhtml,
                base_version=base_version,
                operations=original_operations
            )

            attempt_update.retry_count += 1
            return result

        # Initialize retry counter
        attempt_update.retry_count = 0

        # Use retry wrapper with exponential backoff
        return self._retry_on_version_conflict(attempt_update)

    def create_page(
        self,
        space_key: str,
        title: str,
        markdown_content: str,
        parent_id: Optional[str] = None,
        check_duplicate: bool = True,
    ) -> CreateResult:
        """Create a new page from markdown content.

        Args:
            space_key: Space to create page in
            title: Page title
            markdown_content: Markdown content for the page
            parent_id: Parent page ID. None for space root.
            check_duplicate: If True, check for existing page with same title/parent

        Returns:
            CreateResult with success status and page ID

        Raises:
            APIAccessError: If API call fails
        """
        logger.debug(f"Creating page: {title} in space {space_key}")
        if parent_id:
            logger.debug(f"  Parent: {parent_id}")
        else:
            logger.debug("  Parent: (space root)")

        # Check for duplicate title (same title under same parent)
        if check_duplicate:
            existing = self.api.get_page_by_title(
                space=space_key,
                title=title,
                expand="id,ancestors"
            )
            if existing:
                existing_parent_id = None
                if existing.get("ancestors"):
                    existing_parent_id = existing["ancestors"][-1].get("id")
                # Same parent (or both at root) = duplicate
                if existing_parent_id == parent_id:
                    logger.warning(f"  Page already exists: {existing.get('id')}")
                    return CreateResult(
                        success=False,
                        page_id=existing.get("id"),
                        space_key=space_key,
                        title=title,
                        error=f"Page '{title}' already exists under same parent",
                    )

        # Convert markdown to XHTML
        xhtml = self.converter.markdown_to_xhtml(markdown_content)

        try:
            # Create page via API
            result = self.api.create_page(
                space=space_key,
                title=title,
                body=xhtml,
                parent_id=parent_id,
            )
            page_id = result.get("id") if isinstance(result, dict) else str(result)

            logger.debug(f"  Created: {page_id}")

            return CreateResult(
                success=True,
                page_id=page_id,
                space_key=space_key,
                title=title,
                version=1,
            )

        except Exception as e:
            error_msg = str(e).lower()
            # Check if error indicates duplicate title
            if any(kw in error_msg for kw in [
                "already exists",
                "duplicate",
                "title already in use",
                "same title",
            ]):
                logger.warning(f"  Page already exists (detected from API error)")
                return CreateResult(
                    success=False,
                    page_id=None,
                    space_key=space_key,
                    title=title,
                    error=f"Page '{title}' already exists in space {space_key}",
                )
            logger.error(f"  Failed to create page: {e}")
            return CreateResult(
                success=False,
                page_id=None,
                space_key=space_key,
                title=title,
                error=str(e),
            )

    def update_page_content(
        self,
        page_id: str,
        markdown_content: str,
    ) -> UpdateResult:
        """Update a page with new markdown content.

        Converts markdown to XHTML and updates the page. This is simpler
        than surgical updates - it replaces the entire page content.

        Args:
            page_id: Confluence page ID
            markdown_content: New markdown content for the page

        Returns:
            UpdateResult with success status and new version

        Raises:
            PageNotFoundError: If page doesn't exist
            APIAccessError: If API call fails
        """
        logger.debug(f"Updating page content: {page_id}")

        # Get current page to get title and version
        try:
            page_data = self.api.get_page_by_id(page_id, expand="version")
        except PageNotFoundError:
            logger.error(f"  Page not found: {page_id}")
            return UpdateResult(
                success=False,
                page_id=page_id,
                old_version=0,
                new_version=0,
                operations_applied=0,
                error=f"Page {page_id} not found",
            )

        title = page_data.get("title", "")
        current_version = page_data.get("version", {}).get("number", 0)

        # Convert markdown to XHTML
        xhtml = self.converter.markdown_to_xhtml(markdown_content)

        # Update page via API
        try:
            result = self.api.update_page(
                page_id=page_id,
                title=title,
                body=xhtml,
                version=current_version,
            )
            new_version = result.get("version", {}).get("number", current_version + 1)

            logger.debug(f"  Updated: v{current_version} → v{new_version}")

            return UpdateResult(
                success=True,
                page_id=page_id,
                old_version=current_version,
                new_version=new_version,
                operations_applied=1,
                modified_xhtml=xhtml,
            )

        except APIAccessError as e:
            error_msg = str(e).lower()
            if "conflict" in error_msg or "version" in error_msg:
                logger.error(f"  Version conflict during upload: {e}")
            else:
                logger.error(f"  API error during upload: {e}")
            return UpdateResult(
                success=False,
                page_id=page_id,
                old_version=current_version,
                new_version=current_version,
                operations_applied=0,
                error=str(e),
            )

    def update_page_surgical(
        self,
        page_id: str,
        new_markdown_content: str,
    ) -> UpdateResult:
        """Update a page using surgical operations to preserve Confluence elements.

        This method performs a surgical update that:
        1. Fetches current XHTML from Confluence
        2. Extracts content blocks from both XHTML and new markdown
        3. Generates minimal surgical operations using DiffAnalyzer
        4. Applies operations to XHTML preserving inline comments, macros, etc.
        5. Uploads the modified XHTML

        This preserves Confluence-specific elements like:
        - Inline comment markers (ac:inline-comment-marker)
        - Block macros (ac:structured-macro)
        - Labels and local-ids
        - Table formatting

        Args:
            page_id: Confluence page ID
            new_markdown_content: New markdown content for the page

        Returns:
            UpdateResult with success status and new version

        Raises:
            PageNotFoundError: If page doesn't exist
            APIAccessError: If API call fails
        """
        logger.debug(f"Performing surgical update for page: {page_id}")

        # Step 1: Fetch current page snapshot (includes XHTML)
        try:
            snapshot = self.get_page_snapshot(page_id)
        except PageNotFoundError:
            logger.error(f"  Page not found: {page_id}")
            return UpdateResult(
                success=False,
                page_id=page_id,
                old_version=0,
                new_version=0,
                operations_applied=0,
                error=f"Page {page_id} not found",
            )

        original_xhtml = snapshot.xhtml
        current_version = snapshot.version

        # Step 2: Preserve macros and extract text from inline comments
        # This gives us XHTML with inline comment text visible (not hidden in markers)
        xhtml_for_parsing, preserved_macros = self.macro_preserver.preserve_macros(
            original_xhtml
        )

        # Count inline comments before (for verification)
        inline_comments_before = self.macro_preserver.count_inline_comments(original_xhtml)

        # Step 3: Parse content blocks from both sources
        original_blocks = self.content_parser.extract_xhtml_blocks(xhtml_for_parsing)
        modified_blocks = self.content_parser.extract_markdown_blocks(new_markdown_content)

        logger.debug(
            f"  Parsed {len(original_blocks)} original blocks, "
            f"{len(modified_blocks)} modified blocks"
        )

        # Step 4: Generate surgical operations from diff
        operations = self.diff_analyzer.analyze(original_blocks, modified_blocks)

        if not operations:
            logger.debug(f"  No changes detected for page {page_id}")
            return UpdateResult(
                success=True,
                page_id=page_id,
                old_version=current_version,
                new_version=current_version,
                operations_applied=0,
                modified_xhtml=original_xhtml,
            )

        logger.debug(f"  Generated {len(operations)} surgical operations")

        # Step 5: Apply surgical operations to original XHTML
        # Note: We apply to original_xhtml (with macros intact), not xhtml_for_parsing
        modified_xhtml, success_count, failure_count = self.surgical_editor.apply_operations(
            original_xhtml, operations
        )

        # Check if surgical operations failed - fall back to full replacement
        use_full_replacement = False
        if failure_count > 0:
            logger.warning(
                f"  {failure_count}/{len(operations)} surgical operations failed"
            )
            # If more than half failed, or all failed, use full replacement
            if failure_count >= len(operations) / 2:
                logger.warning(
                    "  Too many failures - falling back to full page replacement"
                )
                use_full_replacement = True

        if use_full_replacement:
            # Fall back to full replacement (loses inline comments but ensures changes are applied)
            modified_xhtml = self.converter.markdown_to_xhtml(new_markdown_content)
            logger.debug("  Using full page replacement")
        else:
            # Verify macro preservation for surgical update
            macros_before = self.surgical_editor.count_macros(original_xhtml)
            macros_after = self.surgical_editor.count_macros(modified_xhtml)
            if macros_after != macros_before:
                logger.warning(
                    f"  Macro count changed: {macros_before} → {macros_after}"
                )

            # Count inline comments after
            inline_comments_after = self.macro_preserver.count_inline_comments(modified_xhtml)
            if inline_comments_after != inline_comments_before:
                logger.warning(
                    f"  Inline comment count changed: {inline_comments_before} → {inline_comments_after}"
                )

        # Step 6: Check for version conflict before upload
        page_data = self.api.get_page_by_id(page_id, expand="version")
        latest_version = page_data.get("version", {}).get("number", 0)

        if latest_version != current_version:
            logger.error(
                f"  Version conflict: expected {current_version}, found {latest_version}"
            )
            return UpdateResult(
                success=False,
                page_id=page_id,
                old_version=current_version,
                new_version=latest_version,
                operations_applied=0,
                error=f"Version conflict: page was modified (v{current_version} → v{latest_version})",
            )

        # Step 7: Upload modified XHTML
        title = snapshot.title
        try:
            result = self.api.update_page(
                page_id=page_id,
                title=title,
                body=modified_xhtml,
                version=current_version,
            )
            new_version = result.get("version", {}).get("number", current_version + 1)

            if use_full_replacement:
                logger.debug(
                    f"  Full replacement complete: v{current_version} → v{new_version}"
                )
            else:
                logger.debug(
                    f"  Surgical update complete: v{current_version} → v{new_version} "
                    f"({success_count}/{len(operations)} operations succeeded)"
                )

            return UpdateResult(
                success=True,
                page_id=page_id,
                old_version=current_version,
                new_version=new_version,
                operations_applied=success_count if not use_full_replacement else 1,
                modified_xhtml=modified_xhtml,
            )

        except APIAccessError as e:
            error_msg = str(e).lower()
            if "conflict" in error_msg or "version" in error_msg:
                logger.error(f"  Version conflict during upload: {e}")
            else:
                logger.error(f"  API error during upload: {e}")
            return UpdateResult(
                success=False,
                page_id=page_id,
                old_version=current_version,
                new_version=current_version,
                operations_applied=0,
                error=str(e),
            )

    def update_page_surgical_adf(
        self,
        page_id: str,
        new_markdown_content: str,
        baseline_markdown: str = None,
    ) -> AdfUpdateResult:
        """Update a page using ADF surgical operations with baseline-centric diffing.

        This method implements baseline-centric surgical updates:
        1. Fetches current page content in ADF format (for applying operations)
        2. Extracts content blocks from BASELINE markdown (not ADF!)
        3. Extracts content blocks from new markdown
        4. Compares baseline vs new (same format = no parser mismatch!)
        5. Generates surgical operations using DiffAnalyzer
        6. Applies operations to ADF by localId
        7. Uploads modified ADF

        Key design principle:
        - Diff comparison uses baseline markdown vs new markdown (same format)
        - This eliminates parser mismatch issues (XHTML vs markdown)
        - ADF is only used as the target for applying changes, not for diffing

        Args:
            page_id: Confluence page ID
            new_markdown_content: New markdown content for the page
            baseline_markdown: Baseline markdown from last sync (required for
                accurate diffing). If None, falls back to full replacement.

        Returns:
            AdfUpdateResult with success status and details

        Raises:
            PageNotFoundError: If page doesn't exist
            APIAccessError: If API call fails
        """
        logger.debug(f"Performing ADF surgical update for page: {page_id}")

        # Step 1: Fetch current page in ADF format (needed for applying operations)
        try:
            adf_response = self.api.get_page_adf(page_id)
        except PageNotFoundError:
            logger.error(f"  Page not found: {page_id}")
            return AdfUpdateResult(
                success=False,
                page_id=page_id,
                old_version=0,
                new_version=0,
                operations_applied=0,
                error=f"Page {page_id} not found",
            )

        # Extract ADF content and version
        title = adf_response.get("title", "")
        current_version = adf_response.get("version", {}).get("number", 1)

        adf_body = adf_response.get("body", {}).get("atlas_doc_format", {})
        adf_value = adf_body.get("value", "{}")

        # Parse ADF JSON
        import json
        try:
            adf_json = json.loads(adf_value) if isinstance(adf_value, str) else adf_value
        except json.JSONDecodeError as e:
            logger.error(f"  Failed to parse ADF JSON: {e}")
            return AdfUpdateResult(
                success=False,
                page_id=page_id,
                old_version=current_version,
                new_version=current_version,
                operations_applied=0,
                error=f"Invalid ADF JSON: {e}",
            )

        # Step 2: Parse ADF document (for applying operations later)
        try:
            adf_doc = self.adf_parser.parse_document(adf_json)
        except ValueError as e:
            logger.error(f"  Failed to parse ADF document: {e}")
            return AdfUpdateResult(
                success=False,
                page_id=page_id,
                old_version=current_version,
                new_version=current_version,
                operations_applied=0,
                error=f"Invalid ADF structure: {e}",
            )

        # Count macros before
        macros_before = self.adf_editor.count_macros(adf_doc)

        # Extract ADF blocks (needed for localId mapping when applying operations)
        adf_blocks = self.adf_parser.extract_blocks(adf_doc)

        # Step 3: BASELINE-CENTRIC DIFFING
        # Compare baseline markdown vs new markdown (same format = no parser mismatch!)
        # If no baseline provided, fall back to full replacement
        if baseline_markdown is None:
            logger.debug(f"  No baseline provided for page {page_id} - using full replacement")
            xhtml = self.converter.markdown_to_xhtml(new_markdown_content)
            try:
                result = self.api.update_page(
                    page_id=page_id,
                    title=title,
                    body=xhtml,
                    version=current_version,
                )
                new_version = result.get("version", {}).get("number", current_version + 1)
                return AdfUpdateResult(
                    success=True,
                    page_id=page_id,
                    old_version=current_version,
                    new_version=new_version,
                    operations_applied=1,
                    fallback_used=True,
                    error="No baseline provided - used full replacement",
                )
            except APIAccessError as e:
                return AdfUpdateResult(
                    success=False,
                    page_id=page_id,
                    old_version=current_version,
                    new_version=current_version,
                    operations_applied=0,
                    error=str(e),
                    fallback_used=True,
                )

        # Extract blocks from BASELINE markdown (not ADF!)
        # This is the key fix: compare markdown-to-markdown, not ADF-to-markdown
        baseline_content_blocks = self.content_parser.extract_markdown_blocks(
            baseline_markdown
        )

        # Filter out the title heading from baseline blocks
        baseline_content_blocks = self._filter_title_heading(
            baseline_content_blocks, title
        )

        # Step 4: Extract content blocks from new markdown
        modified_content_blocks = self.content_parser.extract_markdown_blocks(
            new_markdown_content
        )

        # Filter out the title heading from markdown blocks
        modified_content_blocks = self._filter_title_heading(
            modified_content_blocks, title
        )

        logger.debug(
            f"  Parsed {len(baseline_content_blocks)} baseline blocks, "
            f"{len(modified_content_blocks)} modified blocks"
        )

        # Step 5: Generate surgical operations (baseline vs new - same format!)
        operations = self.diff_analyzer.analyze(
            baseline_content_blocks, modified_content_blocks
        )

        if not operations:
            logger.debug(f"  No changes detected for page {page_id}")
            return AdfUpdateResult(
                success=True,
                page_id=page_id,
                old_version=current_version,
                new_version=current_version,
                operations_applied=0,
                modified_adf=adf_json,
            )

        logger.debug(f"  Generated {len(operations)} surgical operations")

        # Build localId map from ADF blocks
        local_id_map = {}
        for block in adf_blocks:
            if block.local_id and block.content:
                local_id_map[block.content] = block.local_id

        # Step 6: Apply operations to ADF
        modified_adf, success_count, failure_count = self.adf_editor.apply_operations(
            adf_doc, operations, local_id_map
        )

        # Check if we need to fall back to full replacement
        use_full_replacement = False
        if failure_count >= len(operations) / 2:
            logger.warning(
                f"  {failure_count}/{len(operations)} ADF operations failed - "
                f"falling back to full replacement"
            )
            use_full_replacement = True

        if use_full_replacement:
            # Fall back to XHTML-based full replacement
            logger.debug("  Falling back to XHTML full replacement")
            xhtml = self.converter.markdown_to_xhtml(new_markdown_content)
            try:
                result = self.api.update_page(
                    page_id=page_id,
                    title=title,
                    body=xhtml,
                    version=current_version,
                )
                new_version = result.get("version", {}).get("number", current_version + 1)
                return AdfUpdateResult(
                    success=True,
                    page_id=page_id,
                    old_version=current_version,
                    new_version=new_version,
                    operations_applied=1,
                    operations_failed=failure_count,
                    fallback_used=True,
                )
            except APIAccessError as e:
                return AdfUpdateResult(
                    success=False,
                    page_id=page_id,
                    old_version=current_version,
                    new_version=current_version,
                    operations_applied=0,
                    operations_failed=failure_count,
                    error=str(e),
                    fallback_used=True,
                )

        # Verify macro preservation
        macros_after = self.adf_editor.count_macros(modified_adf)
        if macros_after != macros_before:
            logger.warning(
                f"  Macro count changed: {macros_before} → {macros_after}"
            )

        # Convert modified ADF back to dict for upload
        modified_adf_dict = modified_adf.to_dict()

        # Step 7: Check version conflict before upload
        try:
            page_data = self.api.get_page_by_id(page_id, expand="version")
            latest_version = page_data.get("version", {}).get("number", 0)

            if latest_version != current_version:
                logger.error(
                    f"  Version conflict: expected {current_version}, found {latest_version}"
                )
                return AdfUpdateResult(
                    success=False,
                    page_id=page_id,
                    old_version=current_version,
                    new_version=latest_version,
                    operations_applied=0,
                    error=f"Version conflict: page was modified (v{current_version} → v{latest_version})",
                )
        except Exception as e:
            logger.warning(f"  Could not verify version: {e}")

        # Step 8: Upload modified ADF
        try:
            result = self.api.update_page_adf(
                page_id=page_id,
                title=title,
                adf_content=modified_adf_dict,
                version=current_version,
            )
            new_version = result.get("version", {}).get("number", current_version + 1)

            logger.debug(
                f"  ADF surgical update complete: v{current_version} → v{new_version} "
                f"({success_count}/{len(operations)} operations succeeded)"
            )

            return AdfUpdateResult(
                success=True,
                page_id=page_id,
                old_version=current_version,
                new_version=new_version,
                operations_applied=success_count,
                operations_failed=failure_count,
                modified_adf=modified_adf_dict,
            )

        except APIAccessError as e:
            error_msg = str(e).lower()
            if "conflict" in error_msg or "version" in error_msg:
                logger.error(f"  Version conflict during ADF upload: {e}")
            else:
                logger.error(f"  API error during ADF upload: {e}")
            return AdfUpdateResult(
                success=False,
                page_id=page_id,
                old_version=current_version,
                new_version=current_version,
                operations_applied=0,
                operations_failed=failure_count,
                error=str(e),
            )

    def _adf_blocks_to_content_blocks(
        self,
        adf_blocks: List,
    ) -> List[ContentBlock]:
        """Convert ADF blocks to ContentBlocks for DiffAnalyzer.

        This adapter allows reusing the existing DiffAnalyzer with
        ADF-sourced content.

        Args:
            adf_blocks: List of AdfBlock objects

        Returns:
            List of ContentBlock objects
        """
        content_blocks = []

        for adf_block in adf_blocks:
            # Map ADF node type to BlockType
            block_type = adf_block_type_to_content_block_type(adf_block.node_type)

            content_block = ContentBlock(
                block_type=block_type,
                content=adf_block.content,
                level=adf_block.level,
                rows=adf_block.rows,
                index=adf_block.index,
            )
            content_blocks.append(content_block)

        return content_blocks

    def _filter_title_heading(
        self,
        blocks: List[ContentBlock],
        title: str,
    ) -> List[ContentBlock]:
        """Filter out the title heading from content blocks.

        In Confluence, the page title is metadata, not content. But in markdown,
        the title is typically an H1 heading at the start. This causes block
        position mismatches during diff analysis.

        This method removes the first H1 heading if it matches the page title.

        Args:
            blocks: List of ContentBlock objects from markdown
            title: Page title to match

        Returns:
            Filtered list with title heading removed
        """
        if not blocks or not title:
            return blocks

        # Normalize title for comparison
        normalized_title = " ".join(title.lower().split())

        # Check if first block is a heading matching the title
        first_block = blocks[0]
        if first_block.block_type == BlockType.HEADING and first_block.level == 1:
            normalized_content = " ".join(first_block.content.lower().split())
            if normalized_content == normalized_title:
                logger.debug(f"Filtering out title heading: {first_block.content}")
                return blocks[1:]

        return blocks

    def delete_page(self, page_id: str) -> None:
        """Delete a page by its ID.

        Args:
            page_id: Confluence page ID to delete

        Raises:
            PageNotFoundError: If page doesn't exist
            APIAccessError: If API call fails
        """
        logger.debug(f"Deleting page: {page_id}")

        try:
            self.api.delete_page(page_id)
            logger.debug(f"  Deleted: {page_id}")
        except Exception as e:
            logger.error(f"  Failed to delete page {page_id}: {e}")
            raise

    def update_page_parent(
        self,
        page_id: str,
        parent_id: Optional[str]
    ) -> UpdateResult:
        """Update the parent of a page.

        Args:
            page_id: Confluence page ID
            parent_id: New parent page ID. None to move to space root.

        Returns:
            UpdateResult with success status and new version

        Raises:
            PageNotFoundError: If page doesn't exist
            APIAccessError: If API call fails
        """
        logger.debug(f"Updating parent for page: {page_id}")
        if parent_id:
            logger.debug(f"  New parent: {parent_id}")
        else:
            logger.debug("  New parent: (space root)")

        # Fetch current page to get title, body, and version
        try:
            page_data = self.api.get_page_by_id(
                page_id,
                expand="body.storage,version"
            )
        except PageNotFoundError:
            logger.error(f"  Page not found: {page_id}")
            return UpdateResult(
                success=False,
                page_id=page_id,
                old_version=0,
                new_version=0,
                operations_applied=0,
                error=f"Page {page_id} not found",
            )

        # Extract current data
        title = page_data.get("title", "")
        body = page_data.get("body", {}).get("storage", {}).get("value", "")
        current_version = page_data.get("version", {}).get("number", 0)

        # Prepare ancestors parameter for parent update
        # If parent_id is None, pass empty list to move to space root
        ancestors = [{"id": parent_id}] if parent_id else []

        try:
            # Update page with new parent
            result = self.api.update_page(
                page_id=page_id,
                title=title,
                body=body,
                version=current_version,
                ancestors=ancestors,
            )
            new_version = result.get("version", {}).get("number", current_version + 1)

            logger.debug(f"  Updated parent: v{current_version} → v{new_version}")

            return UpdateResult(
                success=True,
                page_id=page_id,
                old_version=current_version,
                new_version=new_version,
                operations_applied=1,  # One operation: parent update
            )

        except APIAccessError as e:
            logger.error(f"  Failed to update parent: {e}")
            return UpdateResult(
                success=False,
                page_id=page_id,
                old_version=current_version,
                new_version=current_version,
                operations_applied=0,
                error=str(e),
            )

    def update_or_create(
        self,
        space_key: str,
        page_id: Optional[str],
        parent_id: Optional[str],
        title: str,
        operations: List[SurgicalOperation],
    ) -> UpdateResult | CreateResult:
        """Update existing page or create new one.

        Logic:
        - page_id exists → update (ignore parent_id changes)
        - page_id is None → create under parent_id
        - page_id not found → ERROR

        Args:
            space_key: Space key
            page_id: Page ID to update, or None to create
            parent_id: Parent page ID (used for create, ignored for update)
            title: Page title
            operations: Operations to apply (for update)

        Returns:
            UpdateResult or CreateResult depending on operation
        """
        if page_id is None:
            # Create new page - need markdown content, not operations
            # This case requires different handling
            logger.debug("Creating new page (page_id is None)")
            return CreateResult(
                success=False,
                page_id=None,
                space_key=space_key,
                title=title,
                error="Cannot create page with operations - use create_page() with markdown",
            )

        # Try to fetch existing page
        try:
            snapshot = self.get_page_snapshot(page_id)
        except PageNotFoundError:
            logger.error(f"Page not found: {page_id}")
            return UpdateResult(
                success=False,
                page_id=page_id,
                old_version=0,
                new_version=0,
                operations_applied=0,
                error=f"Page {page_id} not found - only server can create page IDs",
            )

        # Update existing page
        return self.apply_operations(
            page_id=page_id,
            base_xhtml=snapshot.xhtml,
            base_version=snapshot.version,
            operations=operations,
        )

    def _preserve_macros_for_markdown(self, xhtml: str) -> tuple:
        """Preserve macros as placeholders for markdown conversion.

        Args:
            xhtml: Original XHTML with macros

        Returns:
            Tuple of (xhtml_without_macros, list_of_macros)
        """
        from bs4 import BeautifulSoup, Comment

        soup = BeautifulSoup(xhtml, "lxml")
        macros = []
        placeholder_index = 0

        for tag in list(soup.find_all(True)):
            if tag.name and tag.name.startswith("ac:"):
                # Skip nested macros (only preserve top-level)
                if tag.parent and tag.parent.name and tag.parent.name.startswith("ac:"):
                    continue

                macro_html = str(tag)
                placeholder = f"CONFLUENCE_MACRO_PLACEHOLDER_{placeholder_index}"

                macros.append({"placeholder": placeholder, "html": macro_html})

                comment = Comment(f" {placeholder} ")
                tag.replace_with(comment)
                placeholder_index += 1

        body = soup.find("body")
        if body:
            result = "".join(str(child) for child in body.children)
        else:
            result = str(soup)

        return result, macros

    def _add_macro_placeholders(self, markdown: str, macros: list) -> str:
        """Add macro placeholders to markdown.

        Replaces HTML comment placeholders with simple text placeholders
        that will survive markdown editing.

        Args:
            markdown: Markdown with HTML comment placeholders
            macros: List of macro dictionaries

        Returns:
            Markdown with text placeholders
        """
        result = markdown
        for macro in macros:
            placeholder = macro["placeholder"]
            # Replace HTML comment format with simple text
            patterns = [
                f"<!-- {placeholder} -->",
                f"<!--{placeholder}-->",
            ]
            for pattern in patterns:
                if pattern in result:
                    result = result.replace(pattern, placeholder, 1)
                    break
        return result
