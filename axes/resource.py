"""Axe R (Resource) — Poids page et empreinte carbone.

Mesure :
1. Le poids total de la page (octets transférés)
2. Le nombre de requêtes HTTP (ressources dans le HTML)
3. L'empreinte carbone estimée via Website Carbon API
4. Score basé sur interpolation linéaire du poids page
"""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

import requests

from axes.performance import AxisResult

# --- Constantes ---

CARBON_API_URL: str = "https://api.websitecarbon.com/data"
GREENCHECK_API_URL: str = "https://api.thegreenwebfoundation.org/api/v3/greencheck"
PAGE_TIMEOUT_SECONDS: int = 30
CARBON_API_TIMEOUT_SECONDS: int = 15
REQUEST_USER_AGENT: str = "OSIRIS-Scanner/0.1 (Resource Audit)"

# Seuils de scoring (interpolation linéaire)
WEIGHT_THRESHOLD_PERFECT_BYTES: int = 500_000       # < 500 KB = 10/10
WEIGHT_THRESHOLD_ZERO_BYTES: int = 5_000_000         # > 5 MB = 0/10

# Facteur SWD v4 pour calcul local (fallback si API Carbon down)
# Source: Sustainable Web Design Model v4, gCO2/byte (moyenne globale)
SWD_GCO2_PER_BYTE: float = 0.000000442


def _fetch_page_weight(url: str) -> tuple[int, str]:
    """Récupère le poids total d'une page en octets.

    Args:
        url: URL de la page.

    Returns:
        Tuple (poids_en_octets, content_type).

    Raises:
        RuntimeError: Si la requête échoue.
    """
    try:
        response = requests.get(
            url,
            timeout=PAGE_TIMEOUT_SECONDS,
            headers={"User-Agent": REQUEST_USER_AGENT},
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(
            f"Page timeout après {PAGE_TIMEOUT_SECONDS}s pour {url}"
        ) from None
    except requests.RequestException as e:
        raise RuntimeError(f"Impossible de récupérer la page {url} : {e}") from e

    content_bytes = len(response.content)
    content_type = response.headers.get("content-type", "unknown")

    return content_bytes, content_type


def _count_resources(html: str) -> int:
    """Compte le nombre de ressources externes référencées dans le HTML.

    Args:
        html: Contenu HTML de la page.

    Returns:
        Nombre approximatif de ressources externes.
    """
    patterns = [
        r'<script[^>]+src=',
        r'<link[^>]+href=',
        r'<img[^>]+src=',
        r'<iframe[^>]+src=',
        r'<video[^>]+src=',
        r'<audio[^>]+src=',
        r'<source[^>]+src=',
    ]
    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, html, re.IGNORECASE))
    return count


def _fetch_page_with_resources(url: str) -> tuple[int, int, str]:
    """Récupère le poids de la page et compte les ressources.

    Args:
        url: URL de la page.

    Returns:
        Tuple (poids_octets, nombre_ressources, html_brut).

    Raises:
        RuntimeError: Si la requête échoue.
    """
    try:
        response = requests.get(
            url,
            timeout=PAGE_TIMEOUT_SECONDS,
            headers={"User-Agent": REQUEST_USER_AGENT},
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(
            f"Page timeout après {PAGE_TIMEOUT_SECONDS}s pour {url}"
        ) from None
    except requests.RequestException as e:
        raise RuntimeError(f"Impossible de récupérer la page {url} : {e}") from e

    html = response.text
    content_bytes = len(response.content)
    resource_count = _count_resources(html)

    return content_bytes, resource_count, html


def _check_green_hosting(domain: str) -> bool:
    """Vérifie si un domaine utilise un hébergement vert.

    Args:
        domain: Domaine à vérifier (sans protocole).

    Returns:
        True si hébergement vert, False sinon ou en cas d'erreur.
    """
    try:
        response = requests.get(
            f"{GREENCHECK_API_URL}/{domain}",
            timeout=CARBON_API_TIMEOUT_SECONDS,
        )
        if response.status_code == 200:
            data = response.json()
            return bool(data.get("green", False))
    except (requests.RequestException, ValueError):
        pass
    return False


def _fetch_carbon_data(total_bytes: int, green: bool) -> dict[str, Any] | None:
    """Appelle l'API Website Carbon pour estimer les gCO2.

    Args:
        total_bytes: Nombre d'octets de la page.
        green: Si l'hébergement est vert.

    Returns:
        Données JSON de l'API, ou None si l'API est indisponible.
    """
    try:
        response = requests.get(
            CARBON_API_URL,
            params={"bytes": total_bytes, "green": 1 if green else 0},
            timeout=CARBON_API_TIMEOUT_SECONDS,
        )
        if response.status_code == 200:
            return response.json()
    except (requests.RequestException, ValueError):
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
    """Extrait le domaine d'une URL.

    Args:
        url: URL complète.

    Returns:
        Domaine sans protocole.
    """
    parsed = urlparse(url)
    return parsed.hostname or ""


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
    loop = asyncio.get_event_loop()
    is_green = await loop.run_in_executor(None, _check_green_hosting, domain)
    carbon_data = await loop.run_in_executor(
        None, _fetch_carbon_data, total_transfer, is_green,
    )

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


async def scan(url: str) -> AxisResult:
    """Scanne les ressources d'une URL (poids + empreinte carbone).

    Récupère le poids de la page, vérifie l'hébergement vert,
    et estime les gCO2 via Website Carbon API (avec fallback local).

    Args:
        url: URL du site à scanner.

    Returns:
        AxisResult avec le score resource.

    Raises:
        RuntimeError: Si la page est inaccessible.
    """
    loop = asyncio.get_event_loop()

    # Récupérer la page et compter les ressources
    total_bytes, resource_count, _html = await loop.run_in_executor(
        None, _fetch_page_with_resources, url
    )

    # Vérifier hébergement vert + API Carbon en parallèle
    domain = _extract_domain(url)
    green_future = loop.run_in_executor(None, _check_green_hosting, domain)
    is_green = await green_future

    carbon_data = await loop.run_in_executor(
        None, _fetch_carbon_data, total_bytes, is_green
    )

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
