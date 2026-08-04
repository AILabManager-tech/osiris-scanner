"""Tests unitaires pour utils.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from utils import async_retry, extract_domain, extract_root_domain

# --- Tests async_retry ---


class TestAsyncRetry:
    async def test_succeeds_first_try(self) -> None:
        call_count = 0

        @async_retry(max_retries=3, backoff=0.01)
        async def always_works() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await always_works()
        assert result == "ok"
        assert call_count == 1

    async def test_retries_on_failure_then_succeeds(self) -> None:
        call_count = 0

        @async_retry(max_retries=3, backoff=0.01)
        async def fails_twice() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            return "ok"

        result = await fails_twice()
        assert result == "ok"
        assert call_count == 3

    async def test_exhausts_retries_raises(self) -> None:
        @async_retry(max_retries=2, backoff=0.01)
        async def always_fails() -> str:
            raise RuntimeError("persistent")

        with pytest.raises(RuntimeError, match="persistent"):
            await always_fails()

    async def test_no_retry_on_non_matching_exception(self) -> None:
        call_count = 0

        @async_retry(max_retries=3, backoff=0.01, retry_on=(RuntimeError,))
        async def raises_value_error() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            await raises_value_error()
        assert call_count == 1

    async def test_backoff_delay(self) -> None:
        """Le délai initial fourni est doublé à chaque nouvelle reprise."""
        attempts = 0

        @async_retry(max_retries=3, backoff=0.05)
        async def timed_failure() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("retry")
            return "ok"

        sleep = AsyncMock()
        with patch("utils.asyncio.sleep", sleep):
            await timed_failure()
        assert attempts == 3
        assert [call.args[0] for call in sleep.await_args_list] == [0.05, 0.1]

    async def test_custom_retry_on(self) -> None:
        call_count = 0

        @async_retry(max_retries=3, backoff=0.01, retry_on=(ValueError, RuntimeError))
        async def fails_with_value_error() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("transient value error")
            return "ok"

        result = await fails_with_value_error()
        assert result == "ok"
        assert call_count == 2


# --- Tests extract_domain ---


class TestExtractDomain:
    def test_simple_url(self) -> None:
        assert extract_domain("https://example.com/path") == "example.com"

    def test_with_port(self) -> None:
        assert extract_domain("https://example.com:8080/path") == "example.com"

    def test_with_subdomain(self) -> None:
        assert extract_domain("https://www.example.com") == "www.example.com"

    def test_http_scheme(self) -> None:
        assert extract_domain("http://example.com") == "example.com"

    def test_invalid_url(self) -> None:
        assert extract_domain("not-a-url") == "unknown"

    def test_co_uk(self) -> None:
        assert extract_domain("https://www.bbc.co.uk") == "www.bbc.co.uk"


# --- Tests extract_root_domain ---


class TestExtractRootDomain:
    def test_simple(self) -> None:
        assert extract_root_domain("https://example.com/path") == "example.com"

    def test_subdomain(self) -> None:
        assert extract_root_domain("https://www.example.com") == "example.com"

    def test_deep_subdomain(self) -> None:
        assert extract_root_domain("https://a.b.example.com") == "example.com"

    def test_co_uk(self) -> None:
        assert extract_root_domain("https://www.bbc.co.uk") == "bbc.co.uk"

    def test_com_au(self) -> None:
        assert extract_root_domain("https://shop.example.com.au") == "example.com.au"

    def test_bare_domain(self) -> None:
        """Accepts domain without protocol."""
        assert extract_root_domain("example.com") == "example.com"

    def test_with_port(self) -> None:
        assert extract_root_domain("https://sub.example.com:443") == "example.com"

    def test_single_part(self) -> None:
        assert extract_root_domain("localhost") == "localhost"
