"""Axe R (Resource) — Poids page et empreinte carbone.

Mesure :
1. Le poids total de la page (octets transférés)
2. Le nombre de requêtes HTTP (ressources dans le HTML)
3. L'empreinte carbone estimée via Website Carbon API
4. Score basé sur interpolation linéaire du poids page
"""

from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp

from axes import register_axis
from axes.performance import AxisResult
from utils import async_retry
from utils import extract_domain as _utils_extract_domain

logger = logging.getLogger("osiris")

# --- Constantes ---

CARBON_API_URL: str = "https://api.websitecarbon.com/data"
GREENCHECK_API_URL: str = "https://api.thegreenwebfoundation.org/api/v3/greencheck"
PAGE_TIMEOUT_SECONDS: int = 30
CARBON_API_TIMEOUT_SECONDS: int = 15
REQUEST_USER_AGENT: str = "OSIRIS-Scanner/0.1 (Resource Audit)"

# Seuils de scoring (interpolation linéaire)
WEIGHT_THRESHOLD_PERFECT_BYTES: int = 500_000  # < 500 KB = 10/10
WEIGHT_THRESHOLD_ZERO_BYTES: int = 5_000_000  # > 5 MB = 0/10

# Facteur SWD v4 pour calcul local (fallback si API Carbon down)
# Source: Sustainable Web Design Model v4, gCO2/byte (moyenne globale)
SWD_GCO2_PER_BYTE: float = 0.000000442


async def _fetch_page_weight(url: str) -> tuple[int, str]:
    """Récupère le poids total d'une page en octets (async).

    Args:
        url: URL de la page.

    Returns:
        Tuple (poids_en_octets, content_type).

    Raises:
        RuntimeError: Si la requête échoue.
    """
    timeout = aiohttp.ClientTimeout(total=PAGE_TIMEOUT_SECONDS)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(
                url,
                headers={"User-Agent": REQUEST_USER_AGENT},
                allow_redirects=True,
            ) as response,
        ):
            response.raise_for_status()
            content = await response.read()
            content_type = response.headers.get("content-type", "unknown")
            return len(content), content_type
    except TimeoutError:
        raise RuntimeError(f"Page timeout après {PAGE_TIMEOUT_SECONDS}s pour {url}") from None
    except aiohttp.ClientError as e:
        raise RuntimeError(f"Impossible de récupérer la page {url} : {e}") from e


def _count_resources(html: str) -> int:
    """Compte le nombre de ressources externes référencées dans le HTML.

    Args:
        html: Contenu HTML de la page.

    Returns:
        Nombre approximatif de ressources externes.
    """
    patterns = [
        r"<script[^>]+src=",
        r"<link[^>]+href=",
        r"<img[^>]+src=",
        r"<iframe[^>]+src=",
        r"<video[^>]+src=",
        r"<audio[^>]+src=",
        r"<source[^>]+src=",
    ]
    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, html, re.IGNORECASE))
    return count


async def _fetch_page_with_resources(url: str) -> tuple[int, int, str]:
    """Récupère le poids de la page et compte les ressources (async).

    Args:
        url: URL de la page.

    Returns:
        Tuple (poids_octets, nombre_ressources, html_brut).

    Raises:
        RuntimeError: Si la requête échoue.
    """
    timeout = aiohttp.ClientTimeout(total=PAGE_TIMEOUT_SECONDS)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(
                url,
                headers={"User-Agent": REQUEST_USER_AGENT},
                allow_redirects=True,
            ) as response,
        ):
            response.raise_for_status()
            content = await response.read()
            html = content.decode(response.get_encoding() or "utf-8", errors="replace")
            content_bytes = len(content)
            resource_count = _count_resources(html)
            return content_bytes, resource_count, html
    except TimeoutError:
        raise RuntimeError(f"Page timeout après {PAGE_TIMEOUT_SECONDS}s pour {url}") from None
    except aiohttp.ClientError as e:
        raise RuntimeError(f"Impossible de récupérer la page {url} : {e}") from e


async def _check_green_hosting(domain: str) -> bool:
    """Vérifie si un domaine utilise un hébergement vert (async).

    Args:
        domain: Domaine à vérifier (sans protocole).

    Returns:
        True si hébergement vert, False sinon ou en cas d'erreur.
    """
    timeout = aiohttp.ClientTimeout(total=CARBON_API_TIMEOUT_SECONDS)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(f"{GREENCHECK_API_URL}/{domain}") as response,
        ):
            if response.status == 200:
                data = await response.json()
                return bool(data.get("green", False))
    except (TimeoutError, aiohttp.ClientError, ValueError):
        pass
    return False


async def _fetch_carbon_data(total_bytes: int, green: bool) -> dict[str, Any] | None:
    """Appelle l'API Website Carbon pour estimer les gCO2 (async).

    Args:
        total_bytes: Nombre d'octets de la page.
        green: Si l'hébergement est vert.

    Returns:
        Données JSON de l'API, ou None si l'API est indisponible.
    """
    timeout = aiohttp.ClientTimeout(total=CARBON_API_TIMEOUT_SECONDS)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(
                CARBON_API_URL,
                params={"bytes": total_bytes, "green": 1 if green else 0},
            ) as response,
        ):
            if response.status == 200:
                return await response.json()
    except (TimeoutError, aiohttp.ClientError, ValueError):
        pass
    return None


def _estimate_carbon_local(total_bytes: int) -> float:
    """Estime les gCO2 localement via le modèle SWD v4 (fallback).

    Args:
        total_bytes: Nombre d'octets.

    Returns:
        Estimation en gCO2.
    """
    return total_bytes * SWD_GCO2_PER_BYTE


def _compute_score(total_bytes: int) -> float:
    """Calcule le score Resource par interpolation linéaire du poids.

    Args:
        total_bytes: Poids total de la page en octets.

    Returns:
        Score entre 0.0 et 10.0.
    """
    if total_bytes <= WEIGHT_THRESHOLD_PERFECT_BYTES:
        return 10.0
    if total_bytes >= WEIGHT_THRESHOLD_ZERO_BYTES:
        return 0.0

    ratio = (total_bytes - WEIGHT_THRESHOLD_PERFECT_BYTES) / (
        WEIGHT_THRESHOLD_ZERO_BYTES - WEIGHT_THRESHOLD_PERFECT_BYTES
    )
    return round(10.0 * (1.0 - ratio), 1)


def _extract_domain(url: str) -> str:
    """Extrait le domaine d'une URL (délègue à utils.extract_domain).

    Args:
        url: URL complète.

    Returns:
        Domaine sans protocole.
    """
    return _utils_extract_domain(url)


async def scan_deep(url: str) -> AxisResult:
    """Scan deep : Playwright mesure le poids reel total (tous assets).

    Capture toutes les network requests et somme transferSize,
    au lieu de mesurer seulement le HTML principal.

    Args:
        url: URL du site a scanner.

    Returns:
        AxisResult avec le score resource (deep).
    """
    from playwright.async_api import async_playwright

    total_transfer: int = 0
    request_count: int = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        async def on_response(response: object) -> None:
            nonlocal total_transfer, request_count
            try:
                body = await response.body()  # type: ignore[union-attr]
                total_transfer += len(body)
                request_count += 1
            except Exception:
                request_count += 1

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(2000)
        except Exception:
            pass
        finally:
            await browser.close()

    domain = _extract_domain(url)
    is_green = await _check_green_hosting(domain)
    carbon_data = await _fetch_carbon_data(total_transfer, is_green)

    carbon_source = "Website Carbon API"
    if carbon_data and "statistics" in carbon_data:
        gco2 = carbon_data["statistics"]["co2"]["grid"]["grams"]
        cleaner_than = carbon_data.get("cleanerThan", None)
        carbon_rating = carbon_data.get("rating", None)
    else:
        gco2 = _estimate_carbon_local(total_transfer)
        cleaner_than = None
        carbon_rating = None
        carbon_source = "SWD v4 (estimation locale)"

    score = _compute_score(total_transfer)
    weight_kb = round(total_transfer / 1024, 1)

    return AxisResult(
        score=score,
        details={
            "page_weight_bytes": total_transfer,
            "page_weight_kb": weight_kb,
            "resource_count": request_count,
            "gco2": round(gco2, 4),
            "green_hosting": is_green,
            "carbon_source": carbon_source,
            "carbon_rating": carbon_rating,
            "cleaner_than": cleaner_than,
            "mode": "deep",
            "total_network_requests": request_count,
        },
        tool_used=f"Deep Analysis (Playwright) + {carbon_source}",
        raw_output={
            "carbon_api_response": carbon_data,
        },
    )


def _extract_lighthouse_weight(scan_context: dict) -> int | None:
    """Extrait totalByteWeight depuis le raw_output Lighthouse si disponible.

    Args:
        scan_context: Contexte partagé entre axes.

    Returns:
        Poids total en octets depuis Lighthouse, ou None.
    """
    raw = scan_context.get("lighthouse_raw")
    if not raw or not isinstance(raw, dict):
        return None
    audits = raw.get("audits", {})
    total_weight = audits.get("total-byte-weight", {})
    numeric = total_weight.get("numericValue")
    if numeric is not None:
        return int(numeric)
    return None


@register_axis(
    "R",
    label="Resource",
    weight=0.10,
    exc_types=(RuntimeError,),
    scan_label="Scan Resource (Page Weight + Carbon)...",
)
@async_retry(max_retries=3, backoff=2.0, retry_on=(RuntimeError,))
async def scan(url: str, scan_context: dict | None = None) -> AxisResult:
    """Scanne les ressources d'une URL (poids + empreinte carbone).

    Récupère le poids de la page, vérifie l'hébergement vert,
    et estime les gCO2 via Website Carbon API (avec fallback local).
    Si le scan_context contient des données Lighthouse, utilise le poids
    total réel (totalByteWeight) au lieu du simple HTML.

    Args:
        url: URL du site à scanner.
        scan_context: Contexte partagé entre axes (optionnel).

    Returns:
        AxisResult avec le score resource.

    Raises:
        RuntimeError: Si la page est inaccessible.
    """
    # Tenter d'utiliser le poids Lighthouse (plus précis)
    lighthouse_weight = _extract_lighthouse_weight(scan_context or {})

    # Récupérer la page et compter les ressources (async)
    total_bytes, resource_count, _html = await _fetch_page_with_resources(url)

    weight_source = "HTML only"
    if lighthouse_weight is not None and lighthouse_weight > total_bytes:
        total_bytes = lighthouse_weight
        weight_source = "Lighthouse totalByteWeight"

    # Vérifier hébergement vert + API Carbon en parallèle (async)
    domain = _extract_domain(url)
    is_green = await _check_green_hosting(domain)

    carbon_data = await _fetch_carbon_data(total_bytes, is_green)

    # Extraire gCO2 (API ou fallback local)
    carbon_source = "Website Carbon API"
    if carbon_data and "statistics" in carbon_data:
        gco2 = carbon_data["statistics"]["co2"]["grid"]["grams"]
        cleaner_than = carbon_data.get("cleanerThan", None)
        carbon_rating = carbon_data.get("rating", None)
    else:
        gco2 = _estimate_carbon_local(total_bytes)
        cleaner_than = None
        carbon_rating = None
        carbon_source = "SWD v4 (estimation locale)"

    score = _compute_score(total_bytes)
    weight_kb = round(total_bytes / 1024, 1)

    return AxisResult(
        score=score,
        details={
            "page_weight_bytes": total_bytes,
            "page_weight_kb": weight_kb,
            "weight_source": weight_source,
            "resource_count": resource_count,
            "gco2": round(gco2, 4),
            "green_hosting": is_green,
            "carbon_source": carbon_source,
            "carbon_rating": carbon_rating,
            "cleaner_than": cleaner_than,
        },
        tool_used=f"Page Weight + {carbon_source}",
        raw_output={
            "carbon_api_response": carbon_data,
        },
    )
