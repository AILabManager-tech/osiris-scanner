"""OSIRIS Utils — Helpers partagés (retry, extraction de domaine).

Fournit des utilitaires réutilisables par tous les axes et le scanner.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar
from urllib.parse import urlparse

logger = logging.getLogger("osiris")

F = TypeVar("F", bound=Callable[..., Any])


def async_retry(
    max_retries: int = 3,
    backoff: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (RuntimeError,),
) -> Callable[[F], F]:
    """Décorateur de retry avec backoff exponentiel pour coroutines async.

    Args:
        max_retries: Nombre maximum de tentatives (incluant la première).
        backoff: Facteur multiplicatif du délai entre chaque retry.
        retry_on: Types d'exceptions déclenchant un retry.

    Returns:
        Décorateur applicable à une coroutine async.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except retry_on as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = backoff**attempt
                        logger.debug(
                            "Retry %d/%d pour %s après %.1fs : %s",
                            attempt + 1,
                            max_retries,
                            func.__name__,
                            delay,
                            e,
                        )
                        await asyncio.sleep(delay)
            raise last_exception  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


def extract_domain(url: str) -> str:
    """Extrait le domaine d'une URL de manière robuste.

    Gère les TLD composés (.co.uk, .com.au), les ports, les sous-domaines.
    Utilise uniquement la stdlib (urllib.parse).

    Args:
        url: URL complète (ex: https://sub.example.co.uk:8080/path).

    Returns:
        Domaine sans protocole ni port (ex: sub.example.co.uk).
        Retourne "unknown" si l'extraction échoue.
    """
    parsed = urlparse(url)
    return parsed.hostname or "unknown"


def extract_root_domain(url: str) -> str:
    """Extrait le domaine racine (sans sous-domaine) d'une URL.

    Heuristique stdlib : prend les 2 derniers segments du hostname.
    Gère les TLD composés courants (.co.uk, .com.au, .org.uk, etc.).

    Args:
        url: URL complète ou domaine brut.

    Returns:
        Domaine racine (ex: 'example.com' pour 'sub.example.com').
    """
    # Si c'est déjà un domaine (pas de ://), on le wrappe
    if "://" not in url:
        url = f"https://{url}"

    hostname = extract_domain(url)
    parts = hostname.split(".")

    # TLD composés courants (2 parties)
    compound_tlds = {
        "co.uk",
        "com.au",
        "com.br",
        "co.nz",
        "co.za",
        "co.in",
        "org.uk",
        "net.au",
        "co.jp",
        "or.jp",
        "ne.jp",
        "ac.uk",
        "gov.uk",
        "com.mx",
        "com.ar",
        "com.co",
        "co.kr",
        "go.kr",
    }

    if len(parts) >= 3:
        potential_tld = ".".join(parts[-2:])
        if potential_tld in compound_tlds:
            return ".".join(parts[-3:])

    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return hostname
