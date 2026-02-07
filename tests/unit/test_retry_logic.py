"""Unit tests for confluence_client.retry_logic module."""

import pytest
from unittest.mock import patch, MagicMock
from src.confluence_client.retry_logic import retry_on_rate_limit, as_decorator, _is_rate_limit_error
from src.confluence_client.errors import APIAccessError


class TestIsRateLimitError:
    """Test cases for _is_rate_limit_error function."""

    def test_detects_429_in_message(self):
        """_is_rate_limit_error should detect '429' in exception message."""
        error = Exception("HTTP 429 Too Many Requests")
        assert _is_rate_limit_error(error) is True

    def test_detects_rate_limit_text_in_message(self):
        """_is_rate_limit_error should detect 'rate limit' in exception message."""
        error = Exception("Rate limit exceeded")
        assert _is_rate_limit_error(error) is True

    def test_detects_too_many_requests_in_message(self):
        """_is_rate_limit_error should detect 'too many requests' in exception message."""
        error = Exception("Too many requests, please slow down")
        assert _is_rate_limit_error(error) is True

    def test_detects_status_code_attribute(self):
        """_is_rate_limit_error should detect status_code=429 attribute."""
        error = Exception("API error")
        error.status_code = 429
        assert _is_rate_limit_error(error) is True

    def test_detects_response_status_code_attribute(self):
        """_is_rate_limit_error should detect response.status_code=429 attribute."""
        error = Exception("API error")
        error.response = MagicMock()
        error.response.status_code = 429
        assert _is_rate_limit_error(error) is True

    def test_returns_false_for_non_rate_limit_error(self):
        """_is_rate_limit_error should return False for non-rate-limit errors."""
        error = Exception("Something went wrong")
        assert _is_rate_limit_error(error) is False

    def test_returns_false_for_404_status_code(self):
        """_is_rate_limit_error should return False for other status codes."""
        error = Exception("Not found")
        error.status_code = 404
        assert _is_rate_limit_error(error) is False


class TestRetryOnRateLimit:
    """Test cases for retry_on_rate_limit function."""

    def test_success_on_first_attempt(self):
        """retry_on_rate_limit should return result on first successful attempt."""
        mock_func = MagicMock(return_value="success")
        result = retry_on_rate_limit(mock_func, "arg1", kwarg1="value1")

        assert result == "success"
        mock_func.assert_called_once_with("arg1", kwarg1="value1")

    @patch('time.sleep')
    def test_retries_on_rate_limit_error(self, mock_sleep):
        """retry_on_rate_limit should retry on rate limit errors."""
        mock_func = MagicMock()

        # First two calls raise rate limit error, third succeeds
        rate_limit_error = Exception("HTTP 429 Rate limit exceeded")
        mock_func.side_effect = [rate_limit_error, rate_limit_error, "success"]

        result = retry_on_rate_limit(mock_func)

        assert result == "success"
        assert mock_func.call_count == 3
        # Should have slept twice: 1s, 2s
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    @patch('time.sleep')
    def test_exponential_backoff_timing(self, mock_sleep):
        """retry_on_rate_limit should use exponential backoff: 1s, 2s, 4s."""
        mock_func = MagicMock()

        # Fail 3 times with rate limit, succeed on 4th
        rate_limit_error = Exception("429")
        mock_func.side_effect = [rate_limit_error, rate_limit_error, rate_limit_error, "success"]

        result = retry_on_rate_limit(mock_func)

        assert result == "success"
        assert mock_func.call_count == 4
        # Should sleep 1s, 2s, 4s
        assert mock_sleep.call_count == 3
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls == [1, 2, 4]

    @patch('time.sleep')
    def test_raises_api_access_error_after_max_retries(self, mock_sleep):
        """retry_on_rate_limit should raise APIAccessError after exhausting retries."""
        mock_func = MagicMock()

        # Always raise rate limit error
        rate_limit_error = Exception("429 Too Many Requests")
        mock_func.side_effect = rate_limit_error

        with pytest.raises(APIAccessError) as exc_info:
            retry_on_rate_limit(mock_func)

        assert str(exc_info.value) == "Confluence API failure (after 3 retries)"
        # Should try 4 times total (0, 1, 2, 3)
        assert mock_func.call_count == 4
        # Should sleep 3 times (after attempts 0, 1, 2)
        assert mock_sleep.call_count == 3

    def test_fails_fast_on_non_rate_limit_error(self):
        """retry_on_rate_limit should not retry on non-rate-limit errors."""
        mock_func = MagicMock()

        # Raise a different error (not rate limit)
        other_error = Exception("Page not found")
        mock_func.side_effect = other_error

        with pytest.raises(Exception) as exc_info:
            retry_on_rate_limit(mock_func)

        assert str(exc_info.value) == "Page not found"
        # Should only try once (fail fast)
        assert mock_func.call_count == 1

    @patch('time.sleep')
    def test_preserves_function_arguments(self, mock_sleep):
        """retry_on_rate_limit should preserve positional and keyword arguments across retries."""
        mock_func = MagicMock()

        # Fail once, then succeed
        rate_limit_error = Exception("429")
        mock_func.side_effect = [rate_limit_error, "success"]

        result = retry_on_rate_limit(mock_func, "arg1", "arg2", kwarg1="val1", kwarg2="val2")

        assert result == "success"
        # Both calls should have same arguments
        assert mock_func.call_count == 2
        for call in mock_func.call_args_list:
            assert call[0] == ("arg1", "arg2")
            assert call[1] == {"kwarg1": "val1", "kwarg2": "val2"}


class TestAsDecorator:
    """Test cases for as_decorator function."""

    @patch('time.sleep')
    def test_decorator_wraps_function(self, mock_sleep):
        """as_decorator should wrap function with retry logic."""
        @as_decorator
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    @patch('time.sleep')
    def test_decorator_retries_on_rate_limit(self, mock_sleep):
        """as_decorator should retry on rate limit errors."""
        call_count = 0

        @as_decorator
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("429 Rate limit")
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 3

    @patch('time.sleep')
    def test_decorator_preserves_function_name(self, mock_sleep):
        """as_decorator should preserve the wrapped function's __name__."""
        @as_decorator
        def my_special_function():
            return "success"

        assert my_special_function.__name__ == "my_special_function"

    @patch('time.sleep')
    def test_decorator_preserves_arguments(self, mock_sleep):
        """as_decorator should preserve function arguments."""
        @as_decorator
        def test_func(arg1, arg2, kwarg1=None):
            return f"{arg1}-{arg2}-{kwarg1}"

        result = test_func("a", "b", kwarg1="c")
        assert result == "a-b-c"

    def test_decorator_fails_fast_on_non_rate_limit(self):
        """as_decorator should fail fast on non-rate-limit errors."""
        @as_decorator
        def test_func():
            raise ValueError("Not a rate limit error")

        with pytest.raises(ValueError) as exc_info:
            test_func()

        assert str(exc_info.value) == "Not a rate limit error"
