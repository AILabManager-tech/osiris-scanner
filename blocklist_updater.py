"""OSIRIS Blocklist Updater — Mise à jour automatique des listes de trackers.

Télécharge et merge les listes Disconnect.me et EasyPrivacy pour maintenir
la blocklist de trackers à jour.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger("osiris")

BLOCKLIST_PATH: str = "blocklists/trackers.json"

# Sources de blocklists
DISCONNECT_URL: str = "https://raw.githubusercontent.com/nicedayreg/servicelist/main/services.json"
EASYPRIVACY_URL: str = "https://easylist.to/easylist/easyprivacy.txt"


async def _fetch_disconnect_domains() -> set[str]:
    """Télécharge et extrait les domaines de la liste Disconnect.me.

    Returns:
        Ensemble de domaines de tracking.
    """
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(DISCONNECT_URL) as response,
        ):
            if response.status != 200:
                logger.warning("Disconnect.me HTTP %d", response.status)
                return set()
            data = await response.json(content_type=None)
    except (aiohttp.ClientError, Exception) as e:
        logger.warning("Disconnect.me indisponible : %s", e)
        return set()

    domains: set[str] = set()
    categories = data.get("categories", {})
    for category_name, entries in categories.items():
        if category_name.lower() in ("disconnect", "content"):
            continue  # Skip non-tracking categories
        for entry in entries:
            if isinstance(entry, dict):
                for _service_name, service_data in entry.items():
                    if isinstance(service_data, dict):
                        for _url_key, domain_list in service_data.items():
                            if isinstance(domain_list, list):
                                domains.update(
                                    d.lower().strip() for d in domain_list if isinstance(d, str)
                                )
                            elif isinstance(domain_list, str):
                                domains.add(domain_list.lower().strip())

    return domains


async def _fetch_easyprivacy_domains() -> set[str]:
    """Télécharge et extrait les domaines de la liste EasyPrivacy.

    Extraction basique : lignes commençant par ||domain^ (format Adblock Plus).

    Returns:
        Ensemble de domaines de tracking.
    """
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(EASYPRIVACY_URL) as response,
        ):
            if response.status != 200:
                logger.warning("EasyPrivacy HTTP %d", response.status)
                return set()
            text = await response.text()
    except (aiohttp.ClientError, Exception) as e:
        logger.warning("EasyPrivacy indisponible : %s", e)
        return set()

    domains: set[str] = set()
    pattern = re.compile(r"^\|\|([a-z0-9][\w.-]+)\^", re.MULTILINE)
    for match in pattern.finditer(text.lower()):
        domain = match.group(1).strip()
        # Filter out IPs and overly short domains
        if "." in domain and len(domain) > 4:
            domains.add(domain)

    return domains


def _load_existing_blocklist(path: str | None = None) -> tuple[set[str], dict[str, Any]]:
    """Charge la blocklist existante.

    Args:
        path: Chemin vers le fichier blocklist.

    Returns:
        Tuple (ensemble de domaines, metadata existante).
    """
    blocklist_path = Path(path or BLOCKLIST_PATH)
    if not blocklist_path.exists():
        return set(), {}

    data = json.loads(blocklist_path.read_text(encoding="utf-8"))
    domains = set(data.get("domains", []))
    meta = data.get("_meta", {})
    return domains, meta


def _save_blocklist(
    domains: set[str],
    path: str | None = None,
    sources: list[str] | None = None,
) -> Path:
    """Sauvegarde la blocklist mise à jour.

    Args:
        domains: Ensemble de domaines à sauvegarder.
        path: Chemin vers le fichier blocklist.
        sources: Liste des sources utilisées.

    Returns:
        Chemin du fichier sauvegardé.
    """
    blocklist_path = Path(path or BLOCKLIST_PATH)
    blocklist_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "_meta": {
            "description": "Tracker domains blocklist for OSIRIS Scanner",
            "updated": datetime.now(UTC).isoformat(),
            "sources": sources or [],
            "count": len(domains),
        },
        "domains": sorted(domains),
    }

    blocklist_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return blocklist_path


async def update_blocklist(path: str | None = None) -> dict[str, Any]:
    """Met à jour la blocklist en mergeant les sources upstream.

    Args:
        path: Chemin vers le fichier blocklist.

    Returns:
        Dictionnaire avec les statistiques de mise à jour.
    """
    existing, _ = _load_existing_blocklist(path)
    existing_count = len(existing)

    # Fetch from sources
    disconnect_domains = await _fetch_disconnect_domains()
    easyprivacy_domains = await _fetch_easyprivacy_domains()

    # Merge
    merged = existing | disconnect_domains | easyprivacy_domains
    new_count = len(merged) - existing_count

    sources = []
    if disconnect_domains:
        sources.append(f"Disconnect.me ({len(disconnect_domains)} domains)")
    if easyprivacy_domains:
        sources.append(f"EasyPrivacy ({len(easyprivacy_domains)} domains)")

    saved_path = _save_blocklist(merged, path, sources)

    return {
        "path": str(saved_path),
        "previous_count": existing_count,
        "new_count": new_count,
        "total_count": len(merged),
        "sources": sources,
    }
