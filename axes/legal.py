"""Axe L (Legal) — Audit de Conformité Loi 25.

Audit comportemental via automate à 3 états :
1. Alpha : Détection des trackers pré-consentement (Vierge).
2. Beta : Vérification du respect du refus (Simulation de clic).
3. Gamma : Transparence (Présence du RPP et mentions légales).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from axes import register_axis
from axes.performance import AxisResult
from utils import async_retry, extract_domain

logger = logging.getLogger("osiris")

# --- Référentiel ---

BLOCKLIST_PATH = Path(__file__).parent.parent / "blocklists" / "trackers.json"

def _load_trackers() -> set[str]:
    """Charge la liste des domaines de trackers."""
    try:
        with open(BLOCKLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("domains", []))
    except Exception as e:
        logger.error("Impossible de charger trackers.json : %s", e)
        return set()

TRACKER_DOMAINS = _load_trackers()

# Patterns pour détecter le bouton de refus
REFUSE_PATTERNS = [
    "refuser", "decline", "non merci", "tout refuser", "continuer sans accepter",
    "reject", "deny", "non", "pas maintenant"
]

async def _is_tracker(url: str) -> bool:
    """Vérifie si une URL appartient à un domaine de tracker connu."""
    domain = extract_domain(url)
    # Check direct match or subdomain match
    for tracker in TRACKER_DOMAINS:
        if domain == tracker or domain.endswith(f".{tracker}"):
            return True
    return False

@register_axis(
    "L",
    label="Legal",
    weight=0.15,
    exc_types=(RuntimeError,),
    scan_label="Audit Loi 25 (Automate 3-États)...",
)
@async_retry(max_retries=2, backoff=3.0, retry_on=(RuntimeError,))
async def scan(url: str) -> AxisResult:
    """Audit comportemental Loi 25."""
    results = {
        "alpha": {"passed": True, "trackers": []},
        "beta": {"passed": True, "trackers_after_refusal": []},
        "gamma": {"passed": False, "rpp_found": False, "links": []}
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(user_agent="OSIRIS-Scanner/5.0 (Legal Audit)")
        page = await context.new_page()

        # --- État Alpha : Capture avant interaction ---
        captured_trackers = []
        async def on_request_alpha(request):
            if await _is_tracker(request.url):
                captured_trackers.append(request.url)

        page.on("request", on_request_alpha)
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(2000)
            
            if captured_trackers:
                results["alpha"]["passed"] = False
                results["alpha"]["trackers"] = list(set(captured_trackers))
            
            # --- État Beta : Simulation de Refus ---
            # Recherche active du bouton de refus dans le DOM
            refuse_button = None
            for pattern in REFUSE_PATTERNS:
                # Recherche par texte (case insensitive)
                selectors = [
                    f"button:has-text('{pattern}')",
                    f"a:has-text('{pattern}')",
                    f"span:has-text('{pattern}')"
                ]
                for sel in selectors:
                    try:
                        handle = await page.query_selector(sel)
                        if handle and await handle.is_visible():
                            refuse_button = handle
                            logger.debug("Bouton de refus trouvé via pattern : %s", pattern)
                            break
                    except Exception:
                        continue
                if refuse_button:
                    break
            
            if refuse_button:
                # Reset capture pour Beta
                trackers_after_refusal = []
                page.remove_listener("request", on_request_alpha)
                
                async def on_request_beta(request):
                    if await _is_tracker(request.url):
                        trackers_after_refusal.append(request.url)
                
                page.on("request", on_request_beta)
                
                await refuse_button.click()
                await page.wait_for_timeout(3000) # Attente de l'activation des trackers post-clic
                
                if trackers_after_refusal:
                    results["beta"]["passed"] = False
                    results["beta"]["trackers_after_refusal"] = list(set(trackers_after_refusal))
            else:
                # Si pas de bouton de refus, on considère que le choix n'est pas offert (Échec Beta par défaut)
                results["beta"]["passed"] = False
                results["beta"]["details"] = "Aucun mécanisme de refus détecté"

            # --- État Gamma : Transparence ---
            # Recherche du RPP (Responsable Protection Privée)
            content = await page.content()
            # Recherche de mailto: contenant privacy, rpp, confidentialite
            rpp_match = re.search(r'mailto:[a-zA-Z0-9._%+-]+@(privacy|rpp|confidentialite|legal)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', content, re.I)
            if rpp_match:
                results["gamma"]["rpp_found"] = True
                results["gamma"]["passed"] = True
            
            # Recherche de liens vers Politique de confidentialité
            links = await page.query_selector_all("a")
            for link in links:
                href = await link.get_attribute("href")
                text = await link.inner_text()
                if href and any(p in text.lower() for p in ["confidentialité", "privacy", "vie privée", "protection"]):
                    results["gamma"]["links"].append({"text": text.strip(), "href": href})
            
            if results["gamma"]["links"]:
                results["gamma"]["passed"] = results["gamma"]["passed"] or True

        except Exception as e:
            logger.error("Erreur durant l'audit Loi 25 : %s", e)
        finally:
            await browser.close()

    # --- Scoring ---
    score = 10.0
    
    # Échec Alpha : -3 pts
    if not results["alpha"]["passed"]:
        score -= 3.0
        
    # Échec Beta : -5 pts (Critique : le refus n'est pas respecté ou impossible)
    if not results["beta"]["passed"]:
        score -= 5.0
        
    # Échec Gamma : -2 pts
    if not results["gamma"]["passed"]:
        score -= 2.0
        
    score = max(0.0, round(score, 1))

    return AxisResult(
        score=score,
        details=results,
        tool_used="OSIRIS Legal Automaton (Loi 25)",
        raw_output=results
    )
