#!/usr/bin/env python3
"""Cleanup script to delete ALL pages from the CONFSYNCTEST space.

This script:
1. Lists all pages in the CONFSYNCTEST space
2. Asks for user confirmation (unless --force is passed)
3. Deletes all pages (children first, then parents)

Usage:
    python scripts/cleanup_all_test_pages.py           # Interactive mode
    python scripts/cleanup_all_test_pages.py --force   # Skip confirmation
    python scripts/cleanup_all_test_pages.py --dry-run # List pages without deleting
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.confluence_client.auth import Authenticator
from src.confluence_client.api_wrapper import APIWrapper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SPACE_KEY = "CONFSYNCTEST"


def get_space_homepage_id(api: APIWrapper, space_key: str) -> Optional[str]:
    """Get the homepage ID for a space.

    Args:
        api: APIWrapper instance
        space_key: Space key to query

    Returns:
        Homepage page ID, or None if not found
    """
    try:
        client = api._get_client()
        space_info = client.get_space(space_key, expand="homepage")
        homepage = space_info.get('homepage', {})
        return homepage.get('id')
    except Exception as e:
        logger.warning(f"Could not get space homepage: {e}")
        return None


def get_all_pages_in_space(
    api: APIWrapper,
    space_key: str,
    exclude_homepage: bool = True
) -> tuple:
    """Get all pages in the specified space using CQL.

    Args:
        api: APIWrapper instance
        space_key: Space key to query
        exclude_homepage: If True, exclude the space homepage from results

    Returns:
        Tuple of (list of page dictionaries, homepage_id or None)
    """
    logger.info(f"Fetching all pages in space '{space_key}'...")

    # Get homepage ID to exclude it
    homepage_id = None
    if exclude_homepage:
        homepage_id = get_space_homepage_id(api, space_key)
        if homepage_id:
            logger.info(f"  Space homepage ID: {homepage_id} (will be preserved)")
        else:
            logger.warning("  Could not determine space homepage - will try to detect by title")

    all_pages = []
    start = 0
    limit = 100

    while True:
        try:
            # Use CQL to find all pages in space
            client = api._get_client()
            cql = f'space = "{space_key}" AND type = "page"'

            result = client.cql(
                cql=cql,
                start=start,
                limit=limit,
                expand="ancestors"
            )

            pages = result.get('results', [])
            if not pages:
                break

            all_pages.extend(pages)
            logger.info(f"  Fetched {len(all_pages)} pages so far...")

            # Check if there are more pages
            if len(pages) < limit:
                break
            start += limit

        except Exception as e:
            logger.error(f"Error fetching pages: {e}")
            break

    # Filter out homepage
    if exclude_homepage:
        filtered_pages = []
        for page in all_pages:
            page_content = page.get('content', page)
            page_id = page_content.get('id')
            page_title = page_content.get('title', '')

            # Skip if this is the homepage (by ID or by title matching space key)
            if page_id == homepage_id:
                logger.info(f"  Excluding homepage: {page_id} - '{page_title}'")
                continue
            if homepage_id is None and page_title == space_key:
                logger.info(f"  Excluding likely homepage (title matches space): {page_id} - '{page_title}'")
                homepage_id = page_id  # Remember this for the return value
                continue

            filtered_pages.append(page)

        logger.info(f"Found {len(filtered_pages)} pages to delete (excluding homepage)")
        return filtered_pages, homepage_id

    logger.info(f"Found {len(all_pages)} total pages in space '{space_key}'")
    return all_pages, homepage_id


def build_deletion_order(pages: List[Dict]) -> List[Dict]:
    """Order pages for deletion (children before parents).

    Pages with more ancestors (deeper in hierarchy) are deleted first.
    This ensures children are deleted before their parents.

    Args:
        pages: List of page dictionaries

    Returns:
        List of pages ordered for safe deletion
    """
    # Sort by ancestor count (descending) - deepest pages first
    def get_depth(page):
        ancestors = page.get('content', {}).get('ancestors', [])
        if not ancestors:
            ancestors = page.get('ancestors', [])
        return len(ancestors) if ancestors else 0

    return sorted(pages, key=get_depth, reverse=True)


def delete_all_pages(
    api: APIWrapper,
    pages: List[Dict],
    dry_run: bool = False
) -> tuple:
    """Delete all pages in the list.

    Args:
        api: APIWrapper instance
        pages: List of page dictionaries to delete
        dry_run: If True, only list pages without deleting

    Returns:
        Tuple of (deleted_count, failed_count)
    """
    ordered_pages = build_deletion_order(pages)

    deleted_count = 0
    failed_count = 0

    for page in ordered_pages:
        # Handle different page structures (CQL vs direct API)
        page_content = page.get('content', page)
        page_id = page_content.get('id')
        page_title = page_content.get('title', 'Unknown')

        if not page_id:
            logger.warning(f"  ⚠ Skipping page with no ID: {page}")
            continue

        if dry_run:
            logger.info(f"  [DRY RUN] Would delete: {page_id} - '{page_title}'")
            deleted_count += 1
            continue

        try:
            api.delete_page(page_id)
            logger.info(f"  ✓ Deleted: {page_id} - '{page_title}'")
            deleted_count += 1
        except Exception as e:
            logger.error(f"  ✗ Failed to delete {page_id} - '{page_title}': {e}")
            failed_count += 1

    return deleted_count, failed_count


def confirm_deletion(page_count: int, homepage_preserved: bool = True) -> bool:
    """Ask user for confirmation before deleting.

    Args:
        page_count: Number of pages to delete
        homepage_preserved: Whether the homepage is being preserved

    Returns:
        True if user confirms, False otherwise
    """
    print()
    print("=" * 60)
    print(f"⚠️  WARNING: This will DELETE {page_count} pages from {SPACE_KEY}")
    if homepage_preserved:
        print(f"   (Space homepage will be PRESERVED)")
    print("=" * 60)
    print()

    while True:
        response = input("Are you sure you want to continue? (yes/no): ").strip().lower()
        if response in ('yes', 'y'):
            return True
        elif response in ('no', 'n'):
            return False
        else:
            print("Please enter 'yes' or 'no'")


def main():
    parser = argparse.ArgumentParser(
        description=f"Delete all pages from the {SPACE_KEY} Confluence space"
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Skip confirmation prompt'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='List pages without deleting them'
    )

    args = parser.parse_args()

    logger.info(f"Confluence Test Space Cleanup")
    logger.info(f"Space: {SPACE_KEY}")
    logger.info("-" * 40)

    # Initialize API
    try:
        authenticator = Authenticator()
        api = APIWrapper(authenticator)
    except Exception as e:
        logger.error(f"Failed to initialize Confluence API: {e}")
        logger.error("Make sure your .env file has valid credentials")
        return 1

    # Get all pages (excluding homepage)
    pages, homepage_id = get_all_pages_in_space(api, SPACE_KEY, exclude_homepage=True)

    if not pages:
        logger.info("No pages found to delete (homepage is preserved).")
        return 0

    # Show page list
    print()
    print(f"Pages to delete ({len(pages)}):")
    print("-" * 40)
    for page in pages:
        page_content = page.get('content', page)
        page_id = page_content.get('id')
        page_title = page_content.get('title', 'Unknown')
        print(f"  - {page_id}: {page_title}")
    print("-" * 40)
    print()

    # Dry run mode
    if args.dry_run:
        logger.info("DRY RUN mode - no pages will be deleted")
        deleted, failed = delete_all_pages(api, pages, dry_run=True)
        logger.info(f"Would delete {deleted} pages")
        return 0

    # Confirm deletion
    if not args.force:
        if not confirm_deletion(len(pages), homepage_preserved=(homepage_id is not None)):
            logger.info("Deletion cancelled by user")
            return 0

    # Delete pages
    logger.info("Starting deletion...")
    deleted, failed = delete_all_pages(api, pages)

    # Summary
    print()
    print("=" * 60)
    print("Cleanup Summary:")
    print(f"  - Pages deleted: {deleted}")
    print(f"  - Pages failed: {failed}")
    print(f"  - Total processed: {len(pages)}")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
