"""Axe V (Sovereignty) — Cartographie de Flux Dynamique.

Analyse la destination réelle des paquets (IP, ASN, Pays) via Playwright.
Pénalise l'usage des GAFAM et les sorties de territoire hors Québec/Canada.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from playwright.async_api import async_playwright

from axes import register_axis
from axes.performance import AxisResult
from utils import async_retry, extract_domain

logger = logging.getLogger("osiris")

# --- Constantes ---

GEOIP_API_URL: str = "http://ip-api.com/json"  # API de lookup (determinisme IP/ASN)
GAFAM_ASNS: set[int] = {
    15169, 139190, 139070, # Google
    16509, 14618, 11624,   # Amazon
    32934,                 # Facebook/Meta
    714,                   # Apple
    8075, 8068, 8069,      # Microsoft
}

# Destinations autorisées (ISO Country Codes)
ALLOWED_COUNTRIES: set[str] = {"CA"} # Canada (incluant Québec)

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
        async with aiohttp.ClientSession() as session, session.get(
            f"{GEOIP_API_URL}/{ip}?fields=status,message,countryCode,as,org"
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("status") == "success":
                    # Parse ASN: "AS15169 Google LLC" -> 15169
                    as_raw = data.get("as", "")
                    asn = 0
                    if as_raw.startswith("AS"):
                        try:
                            asn = int(as_raw.split()[0][2:])
                        except (IndexError, ValueError):
                            pass
                    return {
                        "country": data.get("countryCode"),
                        "asn": asn,
                        "org": data.get("org")
                    }
    except Exception as e:
        logger.warning("Geo-IP lookup échoué pour %s : %s", ip, e)
    return {}

@register_axis(
    "V",
    label="Sovereignty",
    weight=0.15,
    exc_types=(RuntimeError,),
    scan_label="Scan Sovereignty (Flux Dynamique)...",
)
@async_retry(max_retries=2, backoff=3.0, retry_on=(RuntimeError,))
async def scan(url: str) -> AxisResult:
    """Analyse la souveraineté des flux réseau via interception Playwright.

    Capture toutes les IPs de destination, résout leur ASN et Pays,
    et calcule un score basé sur la souveraineté physique des données.

    Args:
        url: URL du site à scanner.

    Returns:
        AxisResult avec le score souveraineté.
    """
    flows: dict[str, FlowInfo] = {}
    
    async with async_playwright() as p:
        # Lancement en mode headless, sans bac à sable pour Docker si nécessaire
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(user_agent="OSIRIS-Scanner/5.0 (Sovereignty Audit)")
        page = await context.new_page()

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
            except Exception:
                # On ignore les erreurs sur les requêtes avortées ou sans IP
                pass

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

    # Phase d'enrichissement Géo-IP (parallélisée)
    ips = list(flows.keys())
    tasks = [_get_geo_info(ip) for ip in ips]
    geo_results = await asyncio.gather(*tasks)
    
    for ip, geo in zip(ips, geo_results):
        flow = flows[ip]
        flow.country = geo.get("country", "Unknown")
        flow.asn = geo.get("asn", 0)
        flow.org = geo.get("org", "Unknown")
        flow.is_gafam = flow.asn in GAFAM_ASNS
        flow.is_outside = flow.country not in ALLOWED_COUNTRIES and flow.country != "Unknown"

    # --- Moteur de Scoring Physique ---
    # On commence à 10.0 et on déduit selon les violations
    score = 10.0
    gafam_flows = [f for f in flows.values() if f.is_gafam]
    outside_flows = [f for f in flows.values() if f.is_outside]
    
    # Pénalité GAFAM (impact modéré par flux unique, max 4 pts)
    gafam_count = len(gafam_flows)
    if gafam_count > 0:
        score -= min(4.0, gafam_count * 0.5)
        
    # Pénalité Sortie de Territoire (impact fort, max 5 pts)
    outside_count = len(outside_flows)
    if outside_count > 0:
        score -= min(5.0, outside_count * 1.0)
        
    score = max(0.0, round(score, 1))

    return AxisResult(
        score=score,
        details={
            "total_destinations_ip": len(flows),
            "gafam_connections": gafam_count,
            "outside_territory_connections": outside_count,
            "flows": [vars(f) for f in flows.values()],
            "summary": {
                "gafam_orgs": sorted(list({f.org for f in gafam_flows})),
                "outside_countries": sorted(list({f.country for f in outside_flows})),
            }
        },
        tool_used="Playwright Dynamic Flow Mapping (GEARGRINDER)",
        raw_output={ip: vars(f) for ip, f in flows.items()}
    )
