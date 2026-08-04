"""Axe O (Performance) — mesures HTTP et navigateur sous garde réseau."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from axes import register_axis
from url_security import NetworkPolicy, guard_browser_request, safe_fetch
from utils import async_retry


@dataclass
class AxisResult:
    """Résultat standardisé d'un axe OSIRIS."""

    score: float
    details: dict[str, Any] = field(default_factory=dict)
    tool_used: str = ""
    raw_output: Any = None
    coverage: float = 1.0
    observations: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def _score_response_time(elapsed_ms: float) -> float:
    """Convertit un temps de réponse borné en indicateur 0-10."""

    if elapsed_ms <= 500:
        return 10.0
    if elapsed_ms >= 5000:
        return 0.0
    return round(10.0 * (1.0 - (elapsed_ms - 500.0) / 4500.0), 1)


async def scan_deep(url: str, network_policy: NetworkPolicy | None = None) -> AxisResult:
    """Mesure navigation et rendu avec Playwright sous garde SSRF."""

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright indisponible pour la mesure approfondie") from exc

    policy = network_policy or NetworkPolicy()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            service_workers="block",
            user_agent="OSIRIS-Scanner/0.3 (Performance Signals)",
        )
        page = await context.new_page()
        route_cache: dict[str, bool] = {}
        await page.route(
            "**/*",
            lambda route, request: guard_browser_request(route, request, policy, route_cache),
        )
        started = time.monotonic()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            if response is None:
                raise RuntimeError("Navigation sans réponse HTTP")
            await page.wait_for_timeout(500)
            metrics = await page.evaluate(
                """() => {
                  const nav = performance.getEntriesByType('navigation')[0];
                  const paints = Object.fromEntries(
                    performance.getEntriesByType('paint').map(p => [p.name, p.startTime])
                  );
                  return {
                    responseStart: nav ? nav.responseStart : null,
                    domContentLoaded: nav ? nav.domContentLoadedEventEnd : null,
                    loadEvent: nav ? nav.loadEventEnd : null,
                    transferSize: nav ? nav.transferSize : null,
                    firstContentfulPaint: paints['first-contentful-paint'] ?? null
                  };
                }"""
            )
        except Exception as exc:
            raise RuntimeError(f"Mesure Playwright échouée : {exc}") from exc
        finally:
            await browser.close()

    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    dom_ms = float(metrics.get("domContentLoaded") or elapsed_ms)
    score = _score_response_time(dom_ms)
    risks = ["Le rendu initial dépasse 2,5 secondes."] if dom_ms > 2500 else []
    return AxisResult(
        score=score,
        coverage=0.85,
        observations=[f"DOMContentLoaded observé à {dom_ms:.0f} ms."],
        evidence=[{"type": "navigation_timing", **metrics, "wallTime": elapsed_ms}],
        risks=risks,
        recommendations=(
            ["Réduire le JavaScript bloquant et prioriser les ressources critiques."]
            if risks
            else []
        ),
        limitations=[
            "Mesure locale Playwright; elle ne remplace pas un jeu de données utilisateur réel."
        ],
        details={"mode": "deep", "metrics": metrics, "wall_time_ms": elapsed_ms},
        tool_used="Playwright Navigation Timing",
        raw_output=metrics,
    )


@register_axis(
    "O",
    label="Performance",
    weight=0.15,
    exc_types=(RuntimeError, ValueError),
    scan_label="Scan Performance (HTTP sécurisé)...",
    order=10,
)
@async_retry(max_retries=2, backoff=2.0, retry_on=(RuntimeError,))
async def scan(url: str, network_policy: NetworkPolicy | None = None) -> AxisResult:
    """Mesure rapide et SSRF-safe du temps de réponse HTTP principal.

    Lighthouse n'est pas exécuté sur une URL publique non fiable parce que son
    Chrome autonome ne peut pas utiliser la garde réseau OSIRIS.
    """

    started = time.monotonic()
    try:
        response = await safe_fetch(
            url,
            policy=network_policy or NetworkPolicy(),
            headers={"User-Agent": "OSIRIS-Scanner/0.3 (Performance Signals)"},
        )
    except Exception as exc:
        raise RuntimeError(f"Mesure HTTP échouée : {exc}") from exc
    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    if response.status >= 400:
        raise RuntimeError(f"Page HTTP {response.status} durant la mesure performance")
    score = _score_response_time(elapsed_ms)
    risks = ["Le temps de réponse HTTP principal dépasse 1,5 seconde."] if elapsed_ms > 1500 else []
    return AxisResult(
        score=score,
        coverage=0.6,
        observations=[f"Réponse principale reçue en {elapsed_ms:.0f} ms."],
        evidence=[
            {
                "type": "http_timing",
                "elapsed_ms": elapsed_ms,
                "status": response.status,
                "transfer_bytes": len(response.body),
                "redirects": list(response.redirects),
            }
        ],
        risks=risks,
        recommendations=(
            [
                "Mesurer ensuite les Core Web Vitals avec des données terrain "
                "ou un navigateur contrôlé."
            ]
            if risks
            else []
        ),
        limitations=[
            "Mode rapide : le temps HTTP ne mesure ni le rendu JavaScript ni les Core Web Vitals.",
            "Lighthouse historique est désactivé sur les cibles non fiables "
            "pour éviter le SSRF par sous-ressource.",
        ],
        details={
            "mode": "fast",
            "response_time_ms": elapsed_ms,
            "status_code": response.status,
            "transfer_bytes": len(response.body),
            "redirects": list(response.redirects),
        },
        tool_used="Protected HTTP Timing",
        raw_output=None,
    )
