"""Axe L (Legal) — Audit de Conformité Loi 25.

Audit comportemental via automate à 3 phases d'observation :
1. Alpha : Détection des trackers pré-consentement (page vierge).
2. Beta : Vérification du respect du refus (simulation de clic).
3. Gamma : Transparence (RPP désigné + politique de confidentialité publiée).

L'axe NE juge plus en dur. Il **observe** (faits bruts) puis délègue le verdict
au moteur `governance` qui lit `rulesets/loi25.ruleset.yaml` (regulation-as-code).
Chaque verdict est décomposé par règle, cité à sa source légale, et scoré par
poids. Voir `governance.py` pour le garde-fou anti-hallucination (pas de vert
sur citation non vérifiée).
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
from governance import Evaluator, Ruleset, VerdictStatus, evaluate, load_ruleset
from utils import async_retry, extract_domain

logger = logging.getLogger("osiris")

# --- Référentiel ---

BLOCKLIST_PATH = Path(__file__).parent.parent / "blocklists" / "trackers.json"
RULESET_PATH = Path(__file__).parent.parent / "rulesets" / "loi25.ruleset.yaml"


def _load_trackers() -> set[str]:
    """Charge la liste des domaines de trackers."""
    try:
        with open(BLOCKLIST_PATH, encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("domains", []))
    except Exception as e:
        logger.error("Impossible de charger trackers.json : %s", e)
        return set()


TRACKER_DOMAINS = _load_trackers()

# Ruleset chargé paresseusement et mis en cache (idempotent).
_RULESET: Ruleset | None = None


def _get_ruleset() -> Ruleset:
    """Charge (une fois) le ruleset Loi 25."""
    global _RULESET
    if _RULESET is None:
        _RULESET = load_ruleset(RULESET_PATH)
    return _RULESET


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


# =============================================================================
# Évaluateurs par règle — prédicat pass/fail à partir de l'observation brute.
# Un évaluateur ne connaît QUE l'observation ; la citation/sévérité/poids vivent
# dans le YAML. Mapping clé = `id` de la règle dans loi25.ruleset.yaml.
# =============================================================================


def _eval_traceurs_pre_consentement(
    obs: dict[str, Any],
) -> tuple[VerdictStatus, dict[str, Any]]:
    trackers = obs.get("trackers_pre_consent", [])
    if trackers:
        return "fail", {"trackers_pre_consent": trackers}
    return "pass", {"trackers_pre_consent": []}


def _eval_mecanisme_de_refus(
    obs: dict[str, Any],
) -> tuple[VerdictStatus, dict[str, Any]]:
    if obs.get("refuse_button_found"):
        return "pass", {"refuse_pattern": obs.get("refuse_pattern")}
    return "fail", {"refuse_button_found": False}


def _eval_respect_du_refus(
    obs: dict[str, Any],
) -> tuple[VerdictStatus, dict[str, Any]]:
    # Sans mécanisme de refus, impossible de tester son respect. L'échec est déjà
    # capté par `loi25-mecanisme-de-refus` (bloquant) : pas de double peine ici.
    if not obs.get("refuse_button_found"):
        return "non_applicable", {"raison": "aucun mécanisme de refus à tester"}
    after = obs.get("trackers_after_refusal", [])
    if after:
        return "fail", {"trackers_after_refusal": after}
    return "pass", {"trackers_after_refusal": []}


def _eval_designation_rpp(
    obs: dict[str, Any],
) -> tuple[VerdictStatus, dict[str, Any]]:
    # Règle DÉCOUPLÉE de la politique de confidentialité : c'est exactement le
    # faux positif usine-rh (gamma=pass alors que rpp_found=false). Ici l'absence
    # de RPP échoue, point — elle n'est plus noyée par un lien-confidentialité.
    if obs.get("rpp_found"):
        return "pass", {"rpp_evidence": obs.get("rpp_evidence")}
    return "fail", {"rpp_found": False}


def _eval_politique_confidentialite(
    obs: dict[str, Any],
) -> tuple[VerdictStatus, dict[str, Any]]:
    links = obs.get("privacy_policy_links", [])
    if links:
        return "pass", {"privacy_policy_links": links}
    return "fail", {"privacy_policy_links": []}


EVALUATORS: dict[str, Evaluator] = {
    "loi25-traceurs-pre-consentement": _eval_traceurs_pre_consentement,
    "loi25-mecanisme-de-refus": _eval_mecanisme_de_refus,
    "loi25-respect-du-refus": _eval_respect_du_refus,
    "loi25-designation-rpp": _eval_designation_rpp,
    "loi25-politique-confidentialite-publiee": _eval_politique_confidentialite,
}


async def _is_tracker(url: str) -> bool:
    """Vérifie si une URL appartient à un domaine de tracker connu."""
    domain = extract_domain(url)
    # Check direct match or subdomain match
    return any(domain == tracker or domain.endswith(f".{tracker}") for tracker in TRACKER_DOMAINS)


async def _observe(url: str) -> dict[str, Any]:
    """Capture les faits bruts du site (l'observation, pas le verdict).

    Retourne un dict plat dont les clés correspondent aux `preuve` du ruleset :
    trackers_pre_consent, refuse_button_found, refuse_pattern,
    trackers_after_refusal, rpp_found, rpp_evidence, privacy_policy_links.
    """
    observation: dict[str, Any] = {
        "trackers_pre_consent": [],
        "refuse_button_found": False,
        "refuse_pattern": None,
        "trackers_after_refusal": [],
        "rpp_found": False,
        "rpp_evidence": None,
        "privacy_policy_links": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(user_agent="OSIRIS-Scanner/5.0 (Legal Audit)")
        page = await context.new_page()

        # --- Phase Alpha : Capture avant interaction ---
        captured_trackers: list[str] = []

        async def on_request_alpha(request):
            if await _is_tracker(request.url):
                captured_trackers.append(request.url)

        page.on("request", on_request_alpha)

        try:
            await page.goto(url, wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(2000)

            observation["trackers_pre_consent"] = list(set(captured_trackers))

            # --- Phase Beta : Simulation de Refus ---
            refuse_button = None
            for pattern in REFUSE_PATTERNS:
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
                            observation["refuse_pattern"] = pattern
                            logger.debug("Bouton de refus trouvé via pattern : %s", pattern)
                            break
                    except Exception:
                        continue
                if refuse_button:
                    break

            if refuse_button:
                observation["refuse_button_found"] = True
                trackers_after_refusal: list[str] = []
                page.remove_listener("request", on_request_alpha)

                async def on_request_beta(request):
                    if await _is_tracker(request.url):
                        trackers_after_refusal.append(request.url)

                page.on("request", on_request_beta)

                await refuse_button.click()
                await page.wait_for_timeout(3000)  # Activation des trackers post-clic

                observation["trackers_after_refusal"] = list(set(trackers_after_refusal))

            # --- Phase Gamma : Transparence ---
            content = await page.content()
            # RPP : mailto: vers privacy/rpp/confidentialite/legal
            rpp_pattern = (
                r"mailto:[a-zA-Z0-9._%+-]+@"
                r"(privacy|rpp|confidentialite|legal)"
                r"[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
            )
            rpp_match = re.search(rpp_pattern, content, re.I)
            if rpp_match:
                observation["rpp_found"] = True
                observation["rpp_evidence"] = rpp_match.group(0)

            # Liens vers une politique de confidentialité
            links = await page.query_selector_all("a")
            privacy_keywords = ["confidentialité", "privacy", "vie privée", "protection"]
            for link in links:
                href = await link.get_attribute("href")
                text = await link.inner_text()
                if href and any(p in text.lower() for p in privacy_keywords):
                    observation["privacy_policy_links"].append(
                        {"text": text.strip(), "href": href}
                    )

        except Exception as e:
            logger.error("Erreur durant l'observation Loi 25 : %s", e)
        finally:
            await browser.close()

    return observation


@register_axis(
    "L",
    label="Legal",
    weight=0.15,
    exc_types=(RuntimeError,),
    scan_label="Audit Loi 25 (regulation-as-code)...",
)
@async_retry(max_retries=2, backoff=3.0, retry_on=(RuntimeError,))
async def scan(url: str) -> AxisResult:
    """Audit comportemental Loi 25, scoré par règle via le ruleset."""
    ruleset = _get_ruleset()
    observation = await _observe(url)
    audit = evaluate(ruleset, observation, EVALUATORS)

    return AxisResult(
        score=audit.score,
        details={
            "observation": observation,
            "audit": audit.to_dict(),
            "statut": audit.statut_lisible,
            "citations_completes": audit.citations_completes,
        },
        tool_used="OSIRIS Legal (governance ruleset loi25)",
        raw_output=audit.to_dict(),
    )
