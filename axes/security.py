"""Axe S (Security) — Mozilla Observatory + Headers HTTP.

Mesure la posture sécurité d'un site web via :
1. L'API Mozilla Observatory (grade global)
2. L'analyse directe des headers HTTP de sécurité
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, cast

import aiohttp

from axes import register_axis
from axes.performance import AxisResult
from cache import DEFAULT_TTLS, scan_cache
from url_security import NetworkPolicy, URLSecurityError, safe_fetch
from utils import async_retry, extract_domain

logger = logging.getLogger("osiris")

# --- Constantes ---

OBSERVATORY_API_URL: str = "https://observatory-api.mdn.mozilla.net/api/v2/scan"
OBSERVATORY_TIMEOUT_SECONDS: int = 30
HEADERS_TIMEOUT_SECONDS: int = 15
REQUEST_USER_AGENT: str = "OSIRIS-Scanner/0.3 (Security Signals)"

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


async def _fetch_observatory(host: str) -> dict[str, Any]:
    """Appelle l'API Mozilla Observatory pour un domaine (async, avec cache).

    Args:
        host: Domaine à scanner (sans protocole).

    Returns:
        Réponse JSON de l'API Observatory.

    Raises:
        RuntimeError: Si l'API retourne une erreur ou est inaccessible.
    """
    cache_key = f"observatory:{host}"
    cached = scan_cache.get(cache_key)
    if cached is not None:
        return cached

    timeout = aiohttp.ClientTimeout(total=OBSERVATORY_TIMEOUT_SECONDS)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            # L'API v2 ignore le corps, mais son déploiement actuel refuse les POST
            # aiohttp sans type de contenu. Un objet JSON vide garde l'appel explicite
            # et compatible avec le contrat POST documenté.
            session.post(OBSERVATORY_API_URL, params={"host": host}, json={}) as response,
        ):
            response.raise_for_status()
            data: dict[str, Any] = await response.json()
    except TimeoutError:
        raise RuntimeError(
            f"Observatory API timeout après {OBSERVATORY_TIMEOUT_SECONDS}s"
        ) from None
    except aiohttp.ClientError as e:
        raise RuntimeError(f"Observatory API inaccessible : {e}") from e

    if data.get("error"):
        raise RuntimeError(
            f"Observatory erreur pour {host} : {data.get('error')} — {data.get('message', '')}"
        )

    scan_cache.set(cache_key, data, ttl=DEFAULT_TTLS["observatory"])
    return data


async def _fetch_headers(url: str, policy: NetworkPolicy | None = None) -> dict[str, str]:
    """Récupère les headers HTTP d'une URL (async).

    Args:
        url: URL complète à analyser.

    Returns:
        Dictionnaire des headers (clés en minuscules).

    Raises:
        RuntimeError: Si la requête échoue.
    """
    req_headers = {"User-Agent": REQUEST_USER_AGENT}
    try:
        response = await safe_fetch(url, policy=policy, method="HEAD", headers=req_headers)
        if response.status >= 400:
            response = await safe_fetch(url, policy=policy, headers=req_headers)
        if response.status >= 400:
            raise RuntimeError(f"Page HTTP {response.status} pour {url}")
        return response.headers
    except (TimeoutError, aiohttp.ClientError, URLSecurityError) as e:
        raise RuntimeError(f"Impossible de récupérer les headers de {url} : {e}") from e


def _evaluate_hsts(value: str) -> float:
    """Évalue la qualité du header HSTS. Retourne 0.0-1.0."""
    value = value.lower()
    try:
        max_age = int(value.split("max-age=")[1].split(";")[0].strip())
    except (IndexError, ValueError):
        return 0.2  # Present but unparseable
    if max_age >= 31536000:  # 1 year
        score = 0.8
        if "includesubdomains" in value:
            score += 0.1
        if "preload" in value:
            score += 0.1
        return score
    if max_age >= 2592000:  # 30 days
        return 0.5
    return 0.3  # Too short


def _evaluate_csp(value: str) -> float:
    """Évalue la qualité du header CSP. Retourne 0.0-1.0."""
    value = value.lower()
    score = 0.3  # Present = base score
    if "default-src" in value:
        score += 0.2
    if "'unsafe-inline'" not in value and "'unsafe-eval'" not in value:
        score += 0.3
    if "script-src" in value:
        score += 0.1
    if "frame-ancestors" in value:
        score += 0.1
    return min(score, 1.0)


def _evaluate_xfo(value: str) -> float:
    """Évalue la qualité du header X-Frame-Options. Retourne 0.0-1.0."""
    value = value.upper().strip()
    if value in ("DENY", "SAMEORIGIN"):
        return 1.0
    return 0.3  # Present but weak (e.g., ALLOW-FROM)


def _evaluate_xcto(value: str) -> float:
    """Évalue le header X-Content-Type-Options. Retourne 0.0-1.0."""
    return 1.0 if value.strip().lower() == "nosniff" else 0.3


def _evaluate_referrer(value: str) -> float:
    """Évalue la qualité du header Referrer-Policy. Retourne 0.0-1.0."""
    strong = {"no-referrer", "same-origin", "strict-origin", "strict-origin-when-cross-origin"}
    return 1.0 if value.strip().lower() in strong else 0.5


def _evaluate_permissions(value: str) -> float:
    """Évalue le header Permissions-Policy. Retourne 0.0-1.0."""
    # Any non-empty policy is decent; more restrictive = better
    restricted = value.count("=()")
    if restricted >= 3:
        return 1.0
    if restricted >= 1:
        return 0.7
    return 0.4  # Present but permissive


# Header evaluators mapping
HEADER_EVALUATORS: dict[str, Callable[[str], float]] = {
    "strict-transport-security": _evaluate_hsts,
    "content-security-policy": _evaluate_csp,
    "x-frame-options": _evaluate_xfo,
    "x-content-type-options": _evaluate_xcto,
    "referrer-policy": _evaluate_referrer,
    "permissions-policy": _evaluate_permissions,
}


def _analyze_headers(headers: dict[str, str]) -> tuple[float, dict[str, Any]]:
    """Analyse les headers de sécurité (présence ET qualité).

    Args:
        headers: Dictionnaire des headers HTTP (clés en minuscules).

    Returns:
        Tuple (score_headers_0_10, détail_analyse).
    """
    analysis: dict[str, Any] = {}
    weighted_sum: float = 0.0

    for header_name, weight in SECURITY_HEADERS.items():
        present = header_name in headers
        if present:
            evaluator = HEADER_EVALUATORS.get(header_name)
            quality = evaluator(headers[header_name]) if evaluator else 1.0
            weighted_sum += weight * quality
            analysis[header_name] = {"present": True, "quality": round(quality, 2)}
        else:
            analysis[header_name] = {"present": False, "quality": 0.0}

    score = (weighted_sum / HEADERS_WEIGHT_TOTAL) * 10.0
    return round(score, 1), analysis


def _extract_host(url: str) -> str:
    """Extrait le domaine d'une URL (délègue à utils.extract_domain).

    Args:
        url: URL complète (ex: https://example.com/path).

    Returns:
        Domaine sans protocole, port ni chemin.
    """
    return extract_domain(url)


@register_axis(
    "S",
    label="Sécurité",
    weight=0.25,
    exc_types=(RuntimeError,),
    scan_label="Scan Security (Observatory + Headers)...",
    order=20,
)
@async_retry(max_retries=3, backoff=2.0, retry_on=(RuntimeError,))
async def scan(url: str, network_policy: NetworkPolicy | None = None) -> AxisResult:
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

    # Les deux sources sont indépendantes : conserver une observation partielle
    # plutôt que transformer l'indisponibilité d'Observatory en mauvais score.
    gathered = await asyncio.gather(
        _fetch_observatory(host),
        _fetch_headers(url, network_policy),
        return_exceptions=True,
    )
    observatory_value = cast(dict[str, Any] | BaseException, gathered[0])
    headers_value = cast(dict[str, str] | BaseException, gathered[1])

    if isinstance(observatory_value, BaseException) and isinstance(headers_value, BaseException):
        raise RuntimeError(
            f"Sources sécurité indisponibles : Observatory={observatory_value}; "
            f"headers={headers_value}"
        )

    observatory_data = {} if isinstance(observatory_value, BaseException) else observatory_value
    raw_headers = {} if isinstance(headers_value, BaseException) else headers_value

    # Analyser les résultats
    grade = observatory_data.get("grade")
    observatory_score = _grade_to_score(grade) if grade else None
    headers_score, headers_analysis = _analyze_headers(raw_headers)

    if observatory_score is None:
        final_score = headers_score
        coverage = 0.4
    elif not raw_headers:
        final_score = observatory_score
        coverage = 0.6
    else:
        final_score = round(
            observatory_score * OBSERVATORY_WEIGHT + headers_score * HEADERS_WEIGHT,
            1,
        )
        coverage = 0.95

    headers_found = [h for h, info in headers_analysis.items() if info["present"]]
    headers_missing = [h for h, info in headers_analysis.items() if not info["present"]]
    observations = [f"{len(headers_found)}/{len(SECURITY_HEADERS)} en-têtes de sécurité observés."]
    if grade:
        observations.append(f"Mozilla Observatory a retourné le grade technique {grade}.")
    risks = (
        [f"En-têtes absents ou non observés : {', '.join(headers_missing)}."]
        if headers_missing
        else []
    )
    recommendations = (
        ["Configurer et vérifier les en-têtes manquants selon le contexte de l'application."]
        if headers_missing
        else []
    )
    limitations: list[str] = []
    if isinstance(observatory_value, BaseException):
        limitations.append(f"Mozilla Observatory indisponible : {observatory_value}")
    if isinstance(headers_value, BaseException):
        limitations.append(f"En-têtes de la cible indisponibles : {headers_value}")

    return AxisResult(
        score=final_score,
        coverage=coverage,
        observations=observations,
        evidence=[
            {
                "type": "security_header",
                "name": name,
                **info,
            }
            for name, info in headers_analysis.items()
        ],
        risks=risks,
        recommendations=recommendations,
        limitations=limitations,
        details={
            "observatory_grade": grade,
            "observatory_score_raw": observatory_data.get("score", 0),
            "observatory_tests_passed": observatory_data.get("tests_passed", 0),
            "observatory_tests_failed": observatory_data.get("tests_failed", 0),
            "headers_score": headers_score,
            "headers_found": headers_found,
            "headers_missing": headers_missing,
            "headers_quality": headers_analysis,
        },
        tool_used="Mozilla Observatory + Headers",
        raw_output={
            "observatory": observatory_data,
            "headers": dict(raw_headers),
        },
    )
