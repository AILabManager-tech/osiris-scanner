"""Axe V (Sovereignty) — Cartographie de Flux Dynamique.

Analyse la destination réelle des paquets (IP, ASN, Pays) via Playwright.
Pénalise l'usage des GAFAM et les sorties de territoire hors Québec/Canada.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from axes import register_axis
from axes.performance import AxisResult
from url_security import (
    NetworkPolicy,
    guard_browser_request,
    resolve_public_host,
    safe_fetch,
)
from utils import extract_domain

logger = logging.getLogger("osiris")

# --- Constantes ---

GEOIP_API_URL: str = "https://ipwho.is"
GAFAM_ASNS: set[int] = {
    15169,
    139190,
    139070,  # Google
    16509,
    14618,
    11624,  # Amazon
    32934,  # Facebook/Meta
    714,  # Apple
    8075,
    8068,
    8069,  # Microsoft
}

# Destinations autorisées (ISO Country Codes)
ALLOWED_COUNTRIES: set[str] = {"CA"}  # Canada (incluant Québec)


@dataclass
class FlowInfo:
    """Informations sur un flux réseau capturé."""

    url: str
    ip: str
    host: str
    country: str = "Unknown"
    asn: int = 0
    org: str = "Unknown"
    is_gafam: bool = False
    is_outside: bool = False


async def _get_geo_info(ip: str) -> dict[str, Any]:
    """Récupère les infos Géo-IP/ASN pour une adresse IP via API externe."""
    # Note: ip-api.com est limité à 45 requêtes/min. Pour OSIRIS v5.0 industriel,
    # une base MaxMind locale (GeoLite2-ASN/City) est recommandée.
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(f"{GEOIP_API_URL}/{ip}") as resp,
        ):
            if resp.status == 200:
                data = await resp.json()
                if data.get("success", False):
                    connection = data.get("connection") or {}
                    return {
                        "country": data.get("country_code"),
                        "asn": int(connection.get("asn") or 0),
                        "org": connection.get("org") or connection.get("isp") or "Unknown",
                    }
    except Exception as e:
        logger.warning("Geo-IP lookup échoué pour %s : %s", ip, e)
    return {}


async def _build_result(flows: dict[str, FlowInfo], *, tool: str, coverage: float) -> AxisResult:
    """Enrichit et score un ensemble de flux observés."""

    ips = list(flows.keys())
    geo_results = await asyncio.gather(*(_get_geo_info(ip) for ip in ips))
    for ip, geo in zip(ips, geo_results, strict=True):
        flow = flows[ip]
        flow.country = geo.get("country", "Unknown")
        flow.asn = geo.get("asn", 0)
        flow.org = geo.get("org", "Unknown")
        flow.is_gafam = flow.asn in GAFAM_ASNS
        flow.is_outside = flow.country not in ALLOWED_COUNTRIES and flow.country != "Unknown"

    gafam_flows = [flow for flow in flows.values() if flow.is_gafam]
    outside_flows = [flow for flow in flows.values() if flow.is_outside]
    score = max(
        0.0,
        round(10.0 - min(4.0, len(gafam_flows) * 0.5) - min(5.0, len(outside_flows)), 1),
    )
    known_geo = sum(flow.country != "Unknown" for flow in flows.values())
    geo_coverage = known_geo / len(flows) if flows else 0.0
    effective_coverage = round(coverage * (0.5 + 0.5 * geo_coverage), 2)

    observations = [f"{len(flows)} destination(s) réseau observée(s)."]
    risks: list[str] = []
    recommendations: list[str] = []
    if gafam_flows:
        risks.append(f"{len(gafam_flows)} destination(s) associée(s) à un grand fournisseur cloud.")
    if outside_flows:
        risks.append(f"{len(outside_flows)} destination(s) apparente(s) hors Canada.")
    if risks:
        recommendations.append(
            "Vérifier les finalités, contrats et régions de traitement des services externes."
        )

    return AxisResult(
        score=score,
        coverage=effective_coverage,
        observations=observations,
        evidence=[
            {
                "type": "network_destination",
                "host": flow.host,
                "ip": flow.ip,
                "country": flow.country,
                "asn": flow.asn,
                "organization": flow.org,
            }
            for flow in flows.values()
        ],
        risks=risks,
        recommendations=recommendations,
        limitations=(
            [
                "La géolocalisation IP est indicative et ne prouve pas "
                "le lieu juridique de traitement."
            ]
            if geo_coverage == 1.0
            else [
                "La géolocalisation IP est indicative et incomplète pour certaines destinations.",
                "L'absence de géolocalisation ne signifie pas que le flux est local.",
            ]
        ),
        details={
            "total_destinations_ip": len(flows),
            "geolocated_destinations": known_geo,
            "gafam_connections": len(gafam_flows),
            "outside_territory_connections": len(outside_flows),
            "flows": [vars(flow) for flow in flows.values()],
            "summary": {
                "gafam_orgs": sorted({flow.org for flow in gafam_flows}),
                "outside_countries": sorted({flow.country for flow in outside_flows}),
            },
        },
        tool_used=tool,
        raw_output={ip: vars(flow) for ip, flow in flows.items()},
    )


async def scan_static(url: str, network_policy: NetworkPolicy | None = None) -> AxisResult:
    """Cartographie limitée aux hôtes visibles dans le HTML statique."""

    from axes.intrusion import _extract_domains_from_html

    policy = network_policy or NetworkPolicy()
    response = await safe_fetch(
        url,
        policy=policy,
        headers={"User-Agent": "OSIRIS-Scanner/0.3 (Sovereignty Signals)"},
    )
    if response.status >= 400:
        raise RuntimeError(f"Page HTTP {response.status} durant le scan souveraineté")

    parsed = urlsplit(response.url)
    domains = _extract_domains_from_html(response.text)
    if parsed.hostname:
        domains.add(parsed.hostname)
    flows: dict[str, FlowInfo] = {}
    for host in sorted(domains)[:25]:
        try:
            addresses = await asyncio.to_thread(resolve_public_host, host, 443, policy)
        except Exception as exc:
            logger.debug("Résolution ignorée pour %s : %s", host, exc)
            continue
        if addresses:
            ip = addresses[0]
            flows.setdefault(ip, FlowInfo(url=f"https://{host}/", ip=ip, host=host))
    if not flows:
        raise RuntimeError("Aucune destination réseau publique n'a pu être résolue")
    result = await _build_result(flows, tool="DNS + HTML Static Flow Mapping", coverage=0.6)
    result.limitations.append(
        "Mode rapide : seuls les hôtes visibles dans le HTML statique sont cartographiés."
    )
    return result


@register_axis(
    "V",
    label="Souveraineté",
    weight=0.15,
    exc_types=(RuntimeError,),
    scan_label="Scan Sovereignty (Flux Dynamique)...",
    order=50,
)
async def scan(url: str, network_policy: NetworkPolicy | None = None) -> AxisResult:
    """Analyse la souveraineté des flux réseau via interception Playwright.

    Capture toutes les IPs de destination, résout leur ASN et Pays,
    et calcule un score basé sur la souveraineté physique des données.

    Args:
        url: URL du site à scanner.

    Returns:
        AxisResult avec le score souveraineté.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright indisponible pour la cartographie dynamique de souveraineté"
        ) from exc

    flows: dict[str, FlowInfo] = {}
    policy = network_policy or NetworkPolicy()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="OSIRIS-Scanner/0.3 (Sovereignty Signals)",
            service_workers="block",
        )
        page = await context.new_page()
        route_cache: dict[str, bool] = {}
        await page.route(
            "**/*",
            lambda route, request: guard_browser_request(route, request, policy, route_cache),
        )

        async def on_response(response):
            """Hook d'interception des réponses pour capturer les adresses IP réelles."""
            try:
                # server_addr() fournit l'IP réelle après résolution DNS/CDN
                remote_addr = await response.server_addr()
                if remote_addr:
                    ip = remote_addr.get("ipAddress")
                    if ip and ip not in flows:
                        flow_url = response.url
                        host = extract_domain(flow_url)
                        flows[ip] = FlowInfo(url=flow_url, ip=ip, host=host)
            except Exception as exc:
                logger.debug("Réponse Playwright sans adresse exploitable : %s", exc)

        page.on("response", on_response)

        try:
            # On attend networkidle pour capturer les scripts asynchrones et trackers
            await page.goto(url, wait_until="networkidle", timeout=60000)
            # Délai de grâce pour les flux tardifs
            await page.wait_for_timeout(3000)
        except Exception as e:
            logger.error("Erreur Playwright durant le scan Souveraineté : %s", e)
            if not flows:
                raise RuntimeError(f"Échec critique du scan dynamique : {e}") from e
        finally:
            await browser.close()

    if not flows:
        raise RuntimeError("Aucune destination réseau capturée par Playwright")
    return await _build_result(
        flows,
        tool="Playwright Dynamic Flow Mapping",
        coverage=0.9,
    )
