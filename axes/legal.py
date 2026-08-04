"""Axe L — Prédiagnostic technique de signaux de vie privée.

Audit comportemental via automate à 3 états :
1. Alpha : Détection des trackers pré-consentement (Vierge).
2. Beta : Vérification du respect du refus (Simulation de clic).
3. Gamma : transparence observable (liens et signal de contact spécialisé).

Ces observations ne déterminent pas la conformité juridique globale.
"""

from __future__ import annotations

import json
import logging
import re
from importlib.resources import files
from typing import Any

from axes import register_axis
from axes.performance import AxisResult
from url_security import NetworkPolicy, guard_browser_request, safe_fetch
from utils import extract_domain

logger = logging.getLogger("osiris")

# --- Référentiel ---

BLOCKLIST_PATH = files("blocklists").joinpath("trackers.json")


def _load_trackers() -> set[str]:
    """Charge la liste des domaines de trackers."""
    try:
        with BLOCKLIST_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("domains", []))
    except Exception as e:
        logger.error("Impossible de charger trackers.json : %s", e)
        return set()


TRACKER_DOMAINS = _load_trackers()

# Patterns pour détecter le bouton de refus
REFUSE_PATTERNS = [
    "refuser",
    "decline",
    "non merci",
    "tout refuser",
    "continuer sans accepter",
    "reject",
    "deny",
    "non",
    "pas maintenant",
]


async def _is_tracker(url: str) -> bool:
    """Vérifie si une URL appartient à un domaine de tracker connu."""
    domain = extract_domain(url)
    return any(domain == tracker or domain.endswith(f".{tracker}") for tracker in TRACKER_DOMAINS)


def _privacy_links_from_html(content: str) -> list[str]:
    """Extrait les liens dont le libellé évoque la vie privée."""

    matches = re.findall(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    links: list[str] = []
    for href, raw_text in matches:
        text = re.sub(r"<[^>]+>", " ", raw_text)
        if any(term in text.lower() for term in ("confidentialité", "privacy", "vie privée")):
            links.append(href)
    return sorted(set(links))


async def scan_static(url: str, network_policy: NetworkPolicy | None = None) -> AxisResult:
    """Observe les indicateurs vie privée accessibles sans exécuter JavaScript."""

    from axes.intrusion import _extract_domains_from_html, _is_tracker

    response = await safe_fetch(
        url,
        policy=network_policy or NetworkPolicy(),
        headers={"User-Agent": "OSIRIS-Scanner/0.3 (Privacy Signals)"},
    )
    if response.status >= 400:
        raise RuntimeError(f"Page HTTP {response.status} durant le prédiagnostic vie privée")

    content = response.text
    domains = _extract_domains_from_html(content)
    trackers = sorted(domain for domain in domains if _is_tracker(domain, TRACKER_DOMAINS))
    privacy_links = _privacy_links_from_html(content)
    visible_text = re.sub(r"<[^>]+>", " ", content).lower()
    consent_signal = any(
        term in visible_text
        for term in ("gérer les témoins", "gérer les cookies", "cookie settings", "tout refuser")
    )

    indicators = {
        "trackers_in_static_markup": not trackers,
        "privacy_link_visible": bool(privacy_links),
        "consent_control_visible": consent_signal,
    }
    score = round(
        (5.0 if indicators["trackers_in_static_markup"] else 0.0)
        + (3.0 if indicators["privacy_link_visible"] else 0.0)
        + (2.0 if indicators["consent_control_visible"] else 0.0),
        1,
    )
    risks: list[str] = []
    recommendations: list[str] = []
    if trackers:
        risks.append("Des domaines de traçage connus sont référencés dans le HTML initial.")
        recommendations.append(
            "Vérifier que les traceurs non essentiels restent bloqués avant le choix."
        )
    if not privacy_links:
        risks.append("Aucun lien de politique de confidentialité n'a été observé dans le HTML.")
        recommendations.append("Rendre la politique de confidentialité clairement accessible.")
    if not consent_signal:
        recommendations.append(
            "Rendre le contrôle de consentement observable et accessible au clavier."
        )

    return AxisResult(
        score=score,
        coverage=0.55,
        observations=[
            f"{len(trackers)} domaine(s) de traçage connu(s) dans le HTML statique.",
            f"{len(privacy_links)} lien(s) de confidentialité visible(s).",
        ],
        evidence=[{"type": "tracker_domain", "value": domain} for domain in trackers]
        + [{"type": "privacy_link", "value": href} for href in privacy_links],
        risks=risks,
        recommendations=recommendations,
        limitations=[
            "Mode rapide : aucun clic de refus ni chargement JavaScript n'est évalué.",
            "Les signaux observés ne permettent pas de conclure à une conformité juridique.",
        ],
        details={
            "mode": "fast",
            "indicators": indicators,
            "tracker_domains": trackers,
            "privacy_links": privacy_links,
            "refusal_behavior_evaluated": False,
        },
        tool_used="OSIRIS Technical Privacy Signals (HTML)",
        raw_output={"domains": sorted(domains)},
    )


@register_axis(
    "L",
    label="Signaux vie privée",
    weight=0.15,
    exc_types=(RuntimeError,),
    scan_label="Prédiagnostic vie privée (automate 3 états)...",
    order=60,
)
async def scan(url: str, network_policy: NetworkPolicy | None = None) -> AxisResult:
    """Prédiagnostic comportemental d'indicateurs techniques de vie privée."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright indisponible pour le prédiagnostic dynamique vie privée"
        ) from exc
    results: dict[str, Any] = {
        "alpha": {"passed": True, "trackers": []},
        "beta": {"evaluated": False, "passed": None, "trackers_after_refusal": []},
        "gamma": {"privacy_link_found": False, "contact_signal_found": False, "links": []},
    }
    policy = network_policy or NetworkPolicy()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="OSIRIS-Scanner/0.3 (Privacy Signals)",
            service_workers="block",
        )
        page = await context.new_page()
        route_cache: dict[str, bool] = {}
        await page.route(
            "**/*",
            lambda route, request: guard_browser_request(route, request, policy, route_cache),
        )

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
                    f"span:has-text('{pattern}')",
                ]
                for sel in selectors:
                    try:
                        handle = await page.query_selector(sel)
                        if handle and await handle.is_visible():
                            refuse_button = handle
                            logger.debug("Bouton de refus trouvé via pattern : %s", pattern)
                            break
                    except Exception as exc:
                        logger.debug("Sélecteur de refus non applicable (%s) : %s", pattern, exc)
                        continue
                if refuse_button:
                    break

            if refuse_button:
                results["beta"]["evaluated"] = True
                results["beta"]["passed"] = True
                # Reset capture pour Beta
                trackers_after_refusal = []
                page.remove_listener("request", on_request_alpha)

                async def on_request_beta(request):
                    if await _is_tracker(request.url):
                        trackers_after_refusal.append(request.url)

                page.on("request", on_request_beta)

                await refuse_button.click()
                await page.wait_for_timeout(3000)  # Attente de l'activation des trackers post-clic

                if trackers_after_refusal:
                    results["beta"]["passed"] = False
                    results["beta"]["trackers_after_refusal"] = list(set(trackers_after_refusal))
            else:
                results["beta"]["details"] = (
                    "Aucun contrôle de refus détecté; comportement non évalué"
                )

            # --- État Gamma : Transparence ---
            # Recherche du RPP (Responsable Protection Privée)
            content = await page.content()
            # Recherche de mailto: contenant privacy, rpp, confidentialite
            rpp_match = re.search(
                r"mailto:[a-zA-Z0-9._%+-]+@"
                r"(privacy|rpp|confidentialite|legal)"
                r"[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                content,
                re.I,
            )
            if rpp_match:
                results["gamma"]["contact_signal_found"] = True

            # Recherche de liens vers Politique de confidentialité
            links = await page.query_selector_all("a")
            for link in links:
                href = await link.get_attribute("href")
                text = await link.inner_text()
                privacy_terms = (
                    "confidentialité",
                    "privacy",
                    "vie privée",
                    "protection",
                )
                if href and any(term in text.lower() for term in privacy_terms):
                    results["gamma"]["links"].append({"text": text.strip(), "href": href})

            if results["gamma"]["links"]:
                results["gamma"]["privacy_link_found"] = True

        except Exception as e:
            logger.error("Erreur durant le prédiagnostic vie privée : %s", e)
            raise RuntimeError(f"Échec du prédiagnostic dynamique vie privée : {e}") from e
        finally:
            await browser.close()

    checks: list[tuple[float, bool]] = [
        (0.4, bool(results["alpha"]["passed"])),
        (0.15, bool(results["gamma"]["privacy_link_found"])),
        (0.1, bool(results["gamma"]["contact_signal_found"])),
    ]
    if results["beta"]["evaluated"]:
        checks.append((0.35, bool(results["beta"]["passed"])))
    assessed_weight = sum(weight for weight, _passed in checks)
    score = round(sum(weight for weight, passed in checks if passed) / assessed_weight * 10, 1)
    coverage = 0.95 if results["beta"]["evaluated"] else 0.65
    risks: list[str] = []
    recommendations: list[str] = []
    if not results["alpha"]["passed"]:
        risks.append("Des traceurs connus ont été observés avant toute interaction.")
    if results["beta"]["evaluated"] and not results["beta"]["passed"]:
        risks.append("Des traceurs connus ont été observés après l'action de refus testée.")
    if not results["gamma"]["privacy_link_found"]:
        risks.append("Aucun lien de confidentialité visible n'a été observé.")
    if risks:
        recommendations.append(
            "Faire valider les finalités, le consentement et les mentions "
            "par une personne qualifiée."
        )

    return AxisResult(
        score=score,
        coverage=coverage,
        observations=[
            f"{len(results['alpha']['trackers'])} traceur(s) connu(s) avant interaction.",
            (
                "Le comportement après refus a été évalué."
                if results["beta"]["evaluated"]
                else "Le comportement après refus n'a pas pu être évalué."
            ),
        ],
        evidence=[
            {"type": "tracker_before_choice", "value": tracker}
            for tracker in results["alpha"]["trackers"]
        ]
        + [
            {"type": "privacy_link", "value": link.get("href", "")}
            for link in results["gamma"]["links"]
        ],
        risks=risks,
        recommendations=recommendations,
        limitations=[
            "Le clic automatisé ne couvre pas toutes les bannières ni tous les parcours.",
            "Les observations techniques ne constituent ni une certification ni un avis juridique.",
        ],
        details=results,
        tool_used="OSIRIS Technical Privacy Signals (Playwright)",
        raw_output=results,
    )
