"""Validation réseau et requêtes HTTP protégées pour OSIRIS.

La politique est volontairement fail-closed : une cible ou une redirection n'est
autorisée que si toutes ses adresses DNS sont publiques. Le résolveur aiohttp
répète cette validation au moment de la connexion afin de limiter le DNS rebinding.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult


class URLSecurityError(ValueError):
    """Une URL ou une destination réseau viole la politique OSIRIS."""


@dataclass(frozen=True)
class NetworkPolicy:
    """Limites réseau appliquées à une cible de scan."""

    allow_private: bool = False
    allowed_ports: frozenset[int] | None = field(default_factory=lambda: frozenset({80, 443}))
    max_redirects: int = 5
    max_response_bytes: int = 5 * 1024 * 1024
    max_browser_bytes: int = 20 * 1024 * 1024
    request_timeout: float = 30.0
    total_timeout: float = 180.0


@dataclass(frozen=True)
class SafeHTTPResponse:
    """Réponse HTTP bornée, suffisante pour les axes OSIRIS."""

    url: str
    status: int
    headers: dict[str, str]
    body: bytes
    redirects: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        charset = "utf-8"
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type.lower():
            charset = content_type.lower().split("charset=", 1)[1].split(";", 1)[0].strip()
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


_FORBIDDEN_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
    "instance-data",
    "instance-data.ec2.internal",
}


def validate_url_syntax(url: str, policy: NetworkPolicy | None = None) -> str:
    """Normalise une URL HTTP(S) sans effectuer de résolution DNS."""

    active_policy = policy or NetworkPolicy()
    candidate = url.strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise URLSecurityError(f"URL invalide : {url}") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise URLSecurityError("Seuls les schémas HTTP et HTTPS sont autorisés")
    if not parsed.hostname:
        raise URLSecurityError("L'URL doit contenir un nom d'hôte")
    if parsed.username is not None or parsed.password is not None:
        raise URLSecurityError("Les identifiants intégrés à l'URL sont interdits")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in _FORBIDDEN_HOSTS or hostname.endswith(".localhost"):
        raise URLSecurityError("Localhost et les services de métadonnées sont interdits")

    effective_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    if not 1 <= effective_port <= 65535:
        raise URLSecurityError("Port hors plage")
    if (
        active_policy.allowed_ports is not None
        and effective_port not in active_policy.allowed_ports
    ):
        raise URLSecurityError(
            f"Port {effective_port} interdit; seuls 80 et 443 sont permis publiquement"
        )

    host_for_netloc = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    netloc = (
        host_for_netloc if effective_port == default_port else f"{host_for_netloc}:{effective_port}"
    )
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def redact_url(url: str) -> str:
    """Retire les paramètres et fragments susceptibles de contenir des identifiants."""

    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    host = f"[{hostname}]" if ":" in hostname else hostname
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme, netloc, parsed.path or "/", "", ""))


def _validate_ip(ip_text: str, policy: NetworkPolicy) -> str:
    """Refuse toute adresse non globale, sauf politique de test explicite."""

    try:
        address = ipaddress.ip_address(ip_text.split("%", 1)[0])
    except ValueError as exc:
        raise URLSecurityError(f"Adresse IP invalide : {ip_text}") from exc

    if policy.allow_private:
        return str(address)
    if not address.is_global or address.is_multicast:
        raise URLSecurityError(f"Adresse réseau non publique interdite : {address}")
    return str(address)


def resolve_public_host(hostname: str, port: int, policy: NetworkPolicy) -> tuple[str, ...]:
    """Résout un hôte et refuse un résultat DNS mixte ou non public."""

    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise URLSecurityError(f"Résolution DNS impossible pour {hostname}: {exc}") from exc

    addresses = tuple(dict.fromkeys(str(info[4][0]) for info in infos))
    if not addresses:
        raise URLSecurityError(f"Résolution DNS vide pour {hostname}")
    return tuple(_validate_ip(address, policy) for address in addresses)


def validate_target_url(url: str, policy: NetworkPolicy | None = None) -> str:
    """Valide syntaxe, port et résolution DNS d'une cible."""

    active_policy = policy or NetworkPolicy()
    normalized = validate_url_syntax(url, active_policy)
    parsed = urlsplit(normalized)
    if parsed.hostname is None:
        raise URLSecurityError("L'URL doit contenir un nom d'hôte")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        literal = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        resolve_public_host(parsed.hostname, port, active_policy)
    else:
        _validate_ip(str(literal), active_policy)
    return normalized


class GuardedResolver(AbstractResolver):
    """Résolveur aiohttp qui épingle uniquement des adresses autorisées."""

    def __init__(self, policy: NetworkPolicy) -> None:
        self.policy = policy

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_UNSPEC,
    ) -> list[ResolveResult]:
        del family
        addresses = await asyncio.to_thread(resolve_public_host, host, port, self.policy)
        return [
            {
                "hostname": host,
                "host": address,
                "port": port,
                "family": socket.AF_INET6 if ":" in address else socket.AF_INET,
                "proto": 0,
                "flags": socket.AI_NUMERICHOST,
            }
            for address in addresses
        ]

    async def close(self) -> None:
        return None


async def safe_fetch(
    url: str,
    *,
    policy: NetworkPolicy | None = None,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> SafeHTTPResponse:
    """Effectue une requête bornée avec validation de chaque redirection."""

    active_policy = policy or NetworkPolicy()
    current = validate_target_url(url, active_policy)
    redirects: list[str] = []
    timeout = aiohttp.ClientTimeout(total=active_policy.request_timeout)
    connector = aiohttp.TCPConnector(
        resolver=GuardedResolver(active_policy),
        ttl_dns_cache=0,
        limit_per_host=4,
    )

    async with asyncio.timeout(active_policy.total_timeout):
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            for redirect_count in range(active_policy.max_redirects + 1):
                async with session.request(
                    method.upper(),
                    current,
                    allow_redirects=False,
                    headers=headers,
                ) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise URLSecurityError("Redirection sans en-tête Location")
                        if redirect_count >= active_policy.max_redirects:
                            raise URLSecurityError("Limite de redirections dépassée")
                        current = validate_target_url(urljoin(current, location), active_policy)
                        redirects.append(current)
                        if response.status == 303:
                            method = "GET"
                        continue

                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            declared_size = int(content_length)
                        except ValueError:
                            declared_size = 0
                        if declared_size > active_policy.max_response_bytes:
                            raise URLSecurityError("Réponse trop volumineuse")

                    body = bytearray()
                    if method.upper() != "HEAD":
                        async for chunk in response.content.iter_chunked(64 * 1024):
                            body.extend(chunk)
                            if len(body) > active_policy.max_response_bytes:
                                raise URLSecurityError("Réponse trop volumineuse")

                    return SafeHTTPResponse(
                        url=str(response.url),
                        status=response.status,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        body=bytes(body),
                        redirects=tuple(redirects),
                    )

    raise URLSecurityError("Requête interrompue avant toute réponse")


_REQUEST_HEADERS_REMOVED = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_RESPONSE_HEADERS_REMOVED = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class BrowserNetworkGuard:
    """Relais HTTP borné : Chromium ne se connecte jamais directement à la cible."""

    def __init__(self, policy: NetworkPolicy) -> None:
        self.policy = policy
        self.total_bytes = 0
        self._lock = asyncio.Lock()

    async def handle(self, route: Any, request: Any) -> None:
        request_url = str(request.url)
        scheme = urlsplit(request_url).scheme.lower()
        if scheme in {"about", "blob", "data"}:
            await route.continue_()
            return
        if scheme not in {"http", "https"}:
            await route.abort("blockedbyclient")
            return

        method = str(getattr(request, "method", "GET")).upper()
        if method not in {"GET", "HEAD"}:
            await route.abort("blockedbyclient")
            return
        raw_headers = getattr(request, "headers", {}) or {}
        request_headers = {
            str(key): str(value)
            for key, value in dict(raw_headers).items()
            if str(key).lower() not in _REQUEST_HEADERS_REMOVED
        }

        try:
            # La sérialisation borne la mémoire simultanée et rend le budget agrégé déterministe.
            async with self._lock:
                response = await safe_fetch(
                    request_url,
                    policy=self.policy,
                    method=method,
                    headers=request_headers,
                )
                projected_total = self.total_bytes + len(response.body)
                if projected_total > self.policy.max_browser_bytes:
                    raise URLSecurityError("Budget réseau du navigateur dépassé")
                self.total_bytes = projected_total
        except (TimeoutError, aiohttp.ClientError, URLSecurityError):
            await route.abort("blockedbyclient")
            return

        response_headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in _RESPONSE_HEADERS_REMOVED
        }
        await route.fulfill(
            status=response.status,
            headers=response_headers,
            body=response.body,
        )


async def guard_browser_request(
    route: Any,
    request: Any,
    policy: NetworkPolicy,
    cache: dict[str, Any] | None = None,
) -> None:
    """Relaye une requête Playwright via :func:`safe_fetch` avec budget agrégé."""

    state = cache if cache is not None else {}
    guard = state.get("browser_network_guard")
    if not isinstance(guard, BrowserNetworkGuard):
        guard = BrowserNetworkGuard(policy)
        state["browser_network_guard"] = guard
    await guard.handle(route, request)
