"""Régressions SSRF, redirections et limites réseau."""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from url_security import (
    NetworkPolicy,
    URLSecurityError,
    guard_browser_request,
    resolve_public_host,
    safe_fetch,
    validate_target_url,
    validate_url_syntax,
)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/a",
        "data:text/plain,secret",
        "javascript:alert(1)",
        "gopher://example.com/",
    ],
)
def test_only_http_and_https(url: str) -> None:
    with pytest.raises(URLSecurityError, match="HTTP"):
        validate_url_syntax(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://app.localhost/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
    ],
)
def test_local_private_and_metadata_targets_are_rejected(url: str) -> None:
    with pytest.raises(URLSecurityError):
        validate_target_url(url)


def test_credentials_and_unapproved_ports_are_rejected() -> None:
    with pytest.raises(URLSecurityError, match="identifiants"):
        validate_url_syntax("https://user:pass@example.com/")
    with pytest.raises(URLSecurityError, match="Port 8080"):
        validate_url_syntax("https://example.com:8080/")


def test_mixed_dns_answer_fails_closed() -> None:
    answers = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ]
    with (
        patch("url_security.socket.getaddrinfo", return_value=answers),
        pytest.raises(URLSecurityError, match="non publique"),
    ):
        resolve_public_host("example.test", 443, NetworkPolicy())


@pytest.mark.asyncio
async def test_each_redirect_is_revalidated(target_server: str) -> None:
    policy = NetworkPolicy(allow_private=True, allowed_ports=None)
    with patch("url_security.validate_target_url", wraps=validate_target_url) as validate:
        response = await safe_fetch(f"{target_server}/redirect", policy=policy)
    assert response.status == 200
    assert response.redirects == (f"{target_server}/simple",)
    assert validate.call_count >= 2


@pytest.mark.asyncio
async def test_redirect_limit_and_response_size(target_server: str) -> None:
    local = NetworkPolicy(allow_private=True, allowed_ports=None, max_redirects=1)
    with pytest.raises(URLSecurityError, match="redirections"):
        await safe_fetch(f"{target_server}/redirect-loop", policy=local)

    small = NetworkPolicy(allow_private=True, allowed_ports=None, max_response_bytes=1_024)
    with pytest.raises(URLSecurityError, match="volumineuse"):
        await safe_fetch(f"{target_server}/large", policy=small)


@pytest.mark.asyncio
async def test_request_timeout_is_bounded(target_server: str) -> None:
    policy = NetworkPolicy(
        allow_private=True,
        allowed_ports=None,
        request_timeout=0.05,
        total_timeout=0.1,
    )
    with pytest.raises(TimeoutError):
        await safe_fetch(f"{target_server}/slow", policy=policy)


@pytest.mark.asyncio
async def test_browser_guard_rechecks_dns_instead_of_caching_authorization() -> None:
    route_one = AsyncMock()
    route_two = AsyncMock()
    request = MagicMock(url="https://example.com/app.js")
    with patch(
        "url_security.validate_target_url",
        side_effect=["https://example.com/app.js", URLSecurityError("rebind privé")],
    ) as validate:
        cache: dict[str, bool] = {}
        await guard_browser_request(route_one, request, NetworkPolicy(), cache)
        await guard_browser_request(route_two, request, NetworkPolicy(), cache)
    route_one.continue_.assert_awaited_once()
    route_two.abort.assert_awaited_once_with("blockedbyclient")
    assert validate.call_count == 2


@pytest.mark.asyncio
async def test_browser_guard_blocks_non_http_subresource() -> None:
    route = AsyncMock()
    request = MagicMock(url="file:///etc/passwd")
    await guard_browser_request(route, request, NetworkPolicy())
    route.abort.assert_awaited_once_with("blockedbyclient")
