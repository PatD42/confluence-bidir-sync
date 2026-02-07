"""Retry logic with exponential backoff for Confluence API rate limits.

This module provides retry functionality specifically for handling 429 rate limit
responses from the Confluence API. It implements exponential backoff (1s, 2s, 4s)
and fails fast for non-rate-limit errors.
"""

import time
import logging
from typing import Callable, TypeVar
from functools import wraps

from .errors import APIAccessError

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_on_rate_limit(func: Callable[..., T], *args, **kwargs) -> T:
    """Retry function on 429 rate limit with exponential backoff.

    Executes the given function with the provided arguments, retrying up to 3 times
    with exponential backoff (1s, 2s, 4s) when a rate limit error is encountered.
    Fails fast for all other errors.

    Args:
        func: The function to execute with retry logic
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The return value of the function

    Raises:
        APIAccessError: If rate limit persists after 3 retries
        Other exceptions: Passed through immediately without retry

    Example:
        >>> result = retry_on_rate_limit(api.get_page, page_id="123")
    """
    max_retries = 3

    for retry_num in range(max_retries + 1):  # 0, 1, 2, 3 = 4 attempts total
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Check if this is a rate limit error (429)
            is_rate_limit = _is_rate_limit_error(e)

            if not is_rate_limit:
                # Not a rate limit error - fail fast
                raise

            if retry_num >= max_retries:
                # Exhausted retries - give up
                logger.error(
                    f"Rate limit persisted after {max_retries} retries, giving up"
                )
                raise APIAccessError("Confluence API failure (after 3 retries)")

            # Calculate backoff time: 1s, 2s, 4s
            wait_time = 2 ** retry_num
            logger.info(
                f"Rate limit hit, retrying in {wait_time}s "
                f"(retry {retry_num + 1}/{max_retries})"
            )
            time.sleep(wait_time)

    # Should never reach here, but make type checker happy
    raise APIAccessError("Confluence API failure (after 3 retries)")


def as_decorator(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator version of retry_on_rate_limit for use with @decorator syntax.

    Args:
        func: The function to wrap with retry logic

    Returns:
        Wrapped function with retry logic

    Example:
        >>> @as_decorator
        ... def fetch_page(page_id: str):
        ...     return api.get_page(page_id)
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        return retry_on_rate_limit(func, *args, **kwargs)

    return wrapper


def _is_rate_limit_error(exception: Exception) -> bool:
    """Check if an exception represents a rate limit (429) error.

    This checks for common patterns in HTTP 429 responses from various
    HTTP libraries including atlassian-python-api.

    Args:
        exception: The exception to check

    Returns:
        True if this appears to be a rate limit error, False otherwise
    """
    # Check exception message for 429 status code or rate limit phrases
    # Note: We check for specific rate limit phrases, not just "rate limit"
    # which could appear in other error messages (e.g., "Not a rate limit error")
    error_msg = str(exception).lower()
    rate_limit_patterns = [
        '429',
        'too many requests',
        'rate limit exceeded',
        'rate limit hit',
        'rate limited',
    ]
    if any(pattern in error_msg for pattern in rate_limit_patterns):
        return True

    # Check if exception has status_code attribute (common in HTTP libraries)
    if hasattr(exception, 'status_code') and exception.status_code == 429:
        return True

    # Check if exception has response.status_code (requests library pattern)
    if hasattr(exception, 'response') and hasattr(exception.response, 'status_code'):
        if exception.response.status_code == 429:
            return True

    return False
