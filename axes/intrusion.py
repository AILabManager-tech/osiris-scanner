"""Axe I (Intrusion) — Détection de trackers et requêtes tierces.

Analyse une page web pour détecter :
- Les scripts/pixels de tracking connus (vs blocklist)
- Le ratio de requêtes 1st-party vs tierces
- Les domaines tiers contactés

Méthode : parsing HTML + analyse des ressources référencées.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from axes.performance import AxisResult

# --- Constantes ---

BLOCKLIST_PATH: str = "blocklists/trackers.json"
PAGE_TIMEOUT_SECONDS: int = 30
REQUEST_USER_AGENT: str = "OSIRIS-Scanner/0.1 (Intrusion Audit)"

# Scoring : score inversé basé sur le nombre de trackers
# 0 tracker = 10/10, >= MAX_TRACKERS_FOR_ZERO = 0/10
MAX_TRACKERS_FOR_ZERO: int = 15

# Regex pour extraire les URLs des ressources dans le HTML
URL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'src=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'url\(["\']?([^"\')\s]+)["\']?\)', re.IGNORECASE),
    re.compile(r'https?://[^\s"\'<>]+', re.IGNORECASE),
]


def _load_blocklist(blocklist_path: str | None = None) -> set[str]:
    """Charge la liste de domaines de tracking depuis le fichier JSON.

    Args:
        blocklist_path: Chemin vers le fichier blocklist. Si None, utilise le chemin par défaut.

    Returns:
        Ensemble de domaines de tracking (en minuscules).

    Raises:
        FileNotFoundError: Si le fichier blocklist n'existe pas.
        ValueError: Si le format du fichier est invalide.
    """
    path = Path(blocklist_path or BLOCKLIST_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Blocklist introuvable : {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    domains = data.get("domains")
    if not isinstance(domains, list):
        raise ValueError("Format blocklist invalide : 'domains' manquant ou pas une liste")

    return {d.lower().strip() for d in domains if isinstance(d, str)}


def _fetch_page(url: str) -> str:
    """Récupère le contenu HTML d'une page.

    Args:
        url: URL de la page à récupérer.

    Returns:
        Contenu HTML brut.

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

    return response.text


def _extract_domains_from_html(html: str) -> set[str]:
    """Extrait tous les domaines référencés dans le HTML.

    Args:
        html: Contenu HTML brut.

    Returns:
        Ensemble de domaines trouvés (en minuscules).
    """
    urls: set[str] = set()
    for pattern in URL_PATTERNS:
        for match in pattern.finditer(html):
            urls.add(match.group(1) if pattern.groups else match.group(0))

    domains: set[str] = set()
    for raw_url in urls:
        if not raw_url.startswith(("http://", "https://", "//")):
            continue
        try:
            parsed = urlparse(raw_url if "://" in raw_url else f"https:{raw_url}")
            hostname = parsed.hostname
            if hostname:
                domains.add(hostname.lower())
        except ValueError:
            continue

    return domains


def _extract_host(url: str) -> str:
    """Extrait le domaine racine d'une URL.

    Args:
        url: URL complète.

    Returns:
        Domaine racine (ex: 'example.com' pour 'sub.example.com').
    """
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    parts = hostname.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return hostname


def _is_tracker(domain: str, blocklist: set[str]) -> bool:
    """Vérifie si un domaine est un tracker connu.

    Args:
        domain: Domaine à vérifier (en minuscules).
        blocklist: Ensemble de domaines de tracking.

    Returns:
        True si le domaine ou un parent est dans la blocklist.
    """
    parts = domain.split(".")
    for i in range(len(parts)):
        candidate = ".".join(parts[i:])
        if candidate in blocklist:
            return True
    return False


def _classify_domains(
    domains: set[str],
    site_domain: str,
    blocklist: set[str],
) -> tuple[list[str], list[str], list[str]]:
    """Classifie les domaines en 1st-party, 3rd-party et trackers.

    Args:
        domains: Ensemble de domaines trouvés.
        site_domain: Domaine racine du site scanné.
        blocklist: Ensemble de domaines de tracking.

    Returns:
        Tuple (first_party, third_party, trackers).
    """
    first_party: list[str] = []
    third_party: list[str] = []
    trackers: list[str] = []

    for domain in sorted(domains):
        domain_root = _extract_host(f"https://{domain}")
        if domain_root == site_domain or domain.endswith(f".{site_domain}"):
            first_party.append(domain)
        elif _is_tracker(domain, blocklist):
            trackers.append(domain)
        else:
            third_party.append(domain)

    return first_party, third_party, trackers


def _compute_score(tracker_count: int) -> float:
    """Calcule le score d'intrusion (inversé : plus de trackers = score bas).

    Args:
        tracker_count: Nombre de trackers détectés.

    Returns:
        Score entre 0.0 et 10.0.
    """
    if tracker_count <= 0:
        return 10.0
    if tracker_count >= MAX_TRACKERS_FOR_ZERO:
        return 0.0
    return round(10.0 * (1.0 - tracker_count / MAX_TRACKERS_FOR_ZERO), 1)


async def scan_deep(url: str, blocklist_path: str | None = None) -> AxisResult:
    """Scan deep : Playwright capture les network requests reelles.

    Detecte les trackers charges dynamiquement par JavaScript,
    invisible en mode fast (HTML statique).

    Args:
        url: URL du site a scanner.
        blocklist_path: Chemin optionnel vers la blocklist.

    Returns:
        AxisResult avec le score d'intrusion (deep).
    """
    from playwright.async_api import async_playwright

    blocklist = _load_blocklist(blocklist_path)
    site_domain = _extract_host(url)

    network_domains: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        def on_request(request: object) -> None:
            try:
                req_url = request.url  # type: ignore[union-attr]
                parsed = urlparse(req_url)
                if parsed.hostname:
                    network_domains.add(parsed.hostname.lower())
            except Exception:
                pass

        page.on("request", on_request)

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            # Wait extra for lazy-loaded trackers
            await page.wait_for_timeout(3000)
        except Exception:
            pass
        finally:
            await browser.close()

    first_party, third_party, trackers = _classify_domains(
        network_domains, site_domain, blocklist,
    )

    total_domains = len(first_party) + len(third_party) + len(trackers)
    first_party_ratio = len(first_party) / total_domains if total_domains > 0 else 1.0
    score = _compute_score(len(trackers))

    return AxisResult(
        score=score,
        details={
            "trackers_found": len(trackers),
            "tracker_domains": trackers,
            "third_party_domains": third_party,
            "first_party_domains": first_party,
            "total_domains": total_domains,
            "first_party_ratio": round(first_party_ratio, 2),
            "mode": "deep",
            "network_requests_captured": len(network_domains),
        },
        tool_used="OSIRIS Deep Analysis (Playwright)",
        raw_output={
            "all_domains": sorted(network_domains),
            "blocklist_size": len(blocklist),
        },
    )


async def scan(url: str, blocklist_path: str | None = None) -> AxisResult:
    """Scanne une URL pour détecter les trackers et requêtes tierces.

    Récupère le HTML, extrait les domaines référencés, les compare
    à la blocklist, et calcule un score inversé.

    Args:
        url: URL du site à scanner.
        blocklist_path: Chemin optionnel vers la blocklist.

    Returns:
        AxisResult avec le score d'intrusion.

    Raises:
        FileNotFoundError: Si la blocklist est introuvable.
        RuntimeError: Si la page est inaccessible.
    """
    import asyncio

    loop = asyncio.get_event_loop()

    # Charger la blocklist
    blocklist = await loop.run_in_executor(None, _load_blocklist, blocklist_path)

    # Récupérer la page
    html = await loop.run_in_executor(None, _fetch_page, url)

    # Extraire les domaines
    domains = _extract_domains_from_html(html)

    # Classifier
    site_domain = _extract_host(url)
    first_party, third_party, trackers = _classify_domains(domains, site_domain, blocklist)

    total_domains = len(first_party) + len(third_party) + len(trackers)
    first_party_ratio = len(first_party) / total_domains if total_domains > 0 else 1.0

    score = _compute_score(len(trackers))

    return AxisResult(
        score=score,
        details={
            "trackers_found": len(trackers),
            "tracker_domains": trackers,
            "third_party_domains": third_party,
            "first_party_domains": first_party,
            "total_domains": total_domains,
            "first_party_ratio": round(first_party_ratio, 2),
        },
        tool_used="OSIRIS Blocklist Analysis",
        raw_output={
            "all_domains": sorted(domains),
            "blocklist_size": len(blocklist),
        },
    )
