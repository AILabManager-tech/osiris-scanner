"""Axe S (Security) — Mozilla Observatory + Headers HTTP.

Mesure la posture sécurité d'un site web via :
1. L'API Mozilla Observatory (grade global)
2. L'analyse directe des headers HTTP de sécurité
"""

from __future__ import annotations

import asyncio
from typing import Any

import requests

from axes.performance import AxisResult

# --- Constantes ---

OBSERVATORY_API_URL: str = "https://observatory-api.mdn.mozilla.net/api/v2/scan"
OBSERVATORY_TIMEOUT_SECONDS: int = 30
HEADERS_TIMEOUT_SECONDS: int = 15
REQUEST_USER_AGENT: str = "OSIRIS-Scanner/0.1 (Security Audit)"

# Headers de sécurité vérifiés et leur poids dans le bonus
SECURITY_HEADERS: dict[str, float] = {
    "strict-transport-security": 1.0,
    "content-security-policy": 1.0,
    "x-frame-options": 0.5,
    "x-content-type-options": 0.5,
    "referrer-policy": 0.5,
    "permissions-policy": 0.5,
}

# Poids total possible pour les headers (somme des valeurs)
HEADERS_WEIGHT_TOTAL: float = sum(SECURITY_HEADERS.values())

# Mapping grade Observatory → score de base (0-10)
GRADE_SCORES: dict[str, float] = {
    "A+": 10.0,
    "A": 9.5,
    "A-": 9.0,
    "B+": 8.5,
    "B": 8.0,
    "B-": 7.5,
    "C+": 7.0,
    "C": 6.0,
    "C-": 5.5,
    "D+": 5.0,
    "D": 4.0,
    "D-": 3.0,
    "F": 1.5,
}

# Proportion du score final : 70% Observatory, 30% headers
OBSERVATORY_WEIGHT: float = 0.70
HEADERS_WEIGHT: float = 0.30


def _grade_to_score(grade: str) -> float:
    """Convertit un grade Observatory en score OSIRIS (0-10).

    Args:
        grade: Grade retourné par Observatory (ex: "A+", "F").

    Returns:
        Score entre 0.0 et 10.0.
    """
    return GRADE_SCORES.get(grade, 0.0)


def _fetch_observatory(host: str) -> dict[str, Any]:
    """Appelle l'API Mozilla Observatory pour un domaine.

    Args:
        host: Domaine à scanner (sans protocole).

    Returns:
        Réponse JSON de l'API Observatory.

    Raises:
        RuntimeError: Si l'API retourne une erreur ou est inaccessible.
    """
    try:
        response = requests.post(
            OBSERVATORY_API_URL,
            params={"host": host},
            timeout=OBSERVATORY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(
            f"Observatory API timeout après {OBSERVATORY_TIMEOUT_SECONDS}s"
        ) from None
    except requests.RequestException as e:
        raise RuntimeError(f"Observatory API inaccessible : {e}") from e

    data: dict[str, Any] = response.json()

    if data.get("error"):
        raise RuntimeError(
            f"Observatory erreur pour {host} : {data.get('error')} — {data.get('message', '')}"
        )

    return data


def _fetch_headers(url: str) -> dict[str, str]:
    """Récupère les headers HTTP d'une URL.

    Args:
        url: URL complète à analyser.

    Returns:
        Dictionnaire des headers (clés en minuscules).

    Raises:
        RuntimeError: Si la requête échoue.
    """
    try:
        req_headers = {"User-Agent": REQUEST_USER_AGENT}
        # HEAD d'abord, fallback GET+stream si le serveur refuse HEAD
        response = requests.head(
            url,
            timeout=HEADERS_TIMEOUT_SECONDS,
            allow_redirects=True,
            headers=req_headers,
        )
        if response.status_code >= 400:
            response = requests.get(
                url,
                timeout=HEADERS_TIMEOUT_SECONDS,
                allow_redirects=True,
                stream=True,
                headers=req_headers,
            )
            response.close()
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(
            f"Headers HTTP timeout après {HEADERS_TIMEOUT_SECONDS}s pour {url}"
        ) from None
    except requests.RequestException as e:
        raise RuntimeError(f"Impossible de récupérer les headers de {url} : {e}") from e

    return {k.lower(): v for k, v in response.headers.items()}


def _analyze_headers(headers: dict[str, str]) -> tuple[float, dict[str, bool]]:
    """Analyse les headers de sécurité présents.

    Args:
        headers: Dictionnaire des headers HTTP (clés en minuscules).

    Returns:
        Tuple (score_headers_0_10, détail_présence).
    """
    presence: dict[str, bool] = {}
    weighted_sum: float = 0.0

    for header_name, weight in SECURITY_HEADERS.items():
        present = header_name in headers
        presence[header_name] = present
        if present:
            weighted_sum += weight

    score = (weighted_sum / HEADERS_WEIGHT_TOTAL) * 10.0
    return round(score, 1), presence


def _extract_host(url: str) -> str:
    """Extrait le domaine d'une URL.

    Args:
        url: URL complète (ex: https://example.com/path).

    Returns:
        Domaine sans protocole ni chemin.
    """
    host = url.split("://", 1)[-1]
    host = host.split("/", 1)[0]
    host = host.split("?", 1)[0]
    return host


async def scan(url: str) -> AxisResult:
    """Scanne la sécurité d'une URL via Observatory + headers HTTP.

    Le score final combine :
    - 70% du score Observatory (grade → 0-10)
    - 30% du score headers de sécurité (présence pondérée → 0-10)

    Args:
        url: URL du site à scanner.

    Returns:
        AxisResult avec le score sécurité.

    Raises:
        RuntimeError: Si Observatory ou la requête headers échoue.
    """
    host = _extract_host(url)

    loop = asyncio.get_event_loop()

    # Exécuter les deux appels HTTP en parallèle via le thread pool
    observatory_future = loop.run_in_executor(None, _fetch_observatory, host)
    headers_future = loop.run_in_executor(None, _fetch_headers, url)

    observatory_data = await observatory_future
    raw_headers = await headers_future

    # Analyser les résultats
    grade = observatory_data.get("grade", "F")
    observatory_score = _grade_to_score(grade)

    headers_score, headers_presence = _analyze_headers(raw_headers)

    # Score composite
    final_score = round(
        observatory_score * OBSERVATORY_WEIGHT + headers_score * HEADERS_WEIGHT,
        1,
    )

    headers_found = [h for h, present in headers_presence.items() if present]
    headers_missing = [h for h, present in headers_presence.items() if not present]

    return AxisResult(
        score=final_score,
        details={
            "observatory_grade": grade,
            "observatory_score_raw": observatory_data.get("score", 0),
            "observatory_tests_passed": observatory_data.get("tests_passed", 0),
            "observatory_tests_failed": observatory_data.get("tests_failed", 0),
            "headers_score": headers_score,
            "headers_found": headers_found,
            "headers_missing": headers_missing,
        },
        tool_used="Mozilla Observatory + Headers",
        raw_output={
            "observatory": observatory_data,
            "headers": dict(raw_headers),
        },
    )
