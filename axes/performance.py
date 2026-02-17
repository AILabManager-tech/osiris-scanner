"""Axe O (Performance) — Wrapper Lighthouse CLI.

Mesure la performance d'un site web via Google Lighthouse.
Le score Lighthouse (0-100) est normalisé sur une échelle 0-10.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AxisResult:
    """Résultat standardisé d'un axe OSIRIS."""

    score: float
    details: dict[str, Any] = field(default_factory=dict)
    tool_used: str = ""
    raw_output: Any = None


LIGHTHOUSE_TIMEOUT_SECONDS: int = 120
LIGHTHOUSE_SCORE_MAX: float = 100.0
OSIRIS_SCORE_MAX: float = 10.0


def _find_lighthouse() -> str:
    """Trouve le chemin de l'exécutable Lighthouse.

    Returns:
        Chemin vers l'exécutable lighthouse.

    Raises:
        FileNotFoundError: Si Lighthouse CLI n'est pas installé.
    """
    path = shutil.which("lighthouse")
    if path is None:
        raise FileNotFoundError(
            "Lighthouse CLI introuvable. Installez-le avec : npm install -g lighthouse"
        )
    return path


def _normalize_score(lighthouse_score: float) -> float:
    """Normalise un score Lighthouse (0-100) vers OSIRIS (0-10).

    Args:
        lighthouse_score: Score Lighthouse entre 0 et 100.

    Returns:
        Score normalisé entre 0.0 et 10.0.
    """
    clamped = max(0.0, min(lighthouse_score, LIGHTHOUSE_SCORE_MAX))
    return round(clamped / LIGHTHOUSE_SCORE_MAX * OSIRIS_SCORE_MAX, 1)


def _parse_lighthouse_json(json_path: Path) -> tuple[float, dict[str, Any]]:
    """Parse le fichier JSON de sortie Lighthouse.

    Args:
        json_path: Chemin vers le fichier JSON Lighthouse.

    Returns:
        Tuple (score_0_100, détails).

    Raises:
        ValueError: Si le JSON ne contient pas les données attendues.
    """
    raw = json.loads(json_path.read_text(encoding="utf-8"))

    categories = raw.get("categories", {})
    perf_category = categories.get("performance")
    if perf_category is None:
        raise ValueError("Le rapport Lighthouse ne contient pas la catégorie 'performance'")

    score_raw = perf_category.get("score")
    if score_raw is None:
        raise ValueError("Score performance absent du rapport Lighthouse")

    # Lighthouse retourne un score entre 0.0 et 1.0
    score_0_100 = float(score_raw) * 100.0

    # Extraire les métriques clés si disponibles
    audits = raw.get("audits", {})
    details: dict[str, Any] = {}
    metric_keys = [
        "first-contentful-paint",
        "largest-contentful-paint",
        "total-blocking-time",
        "cumulative-layout-shift",
        "speed-index",
    ]
    for key in metric_keys:
        audit = audits.get(key)
        if audit:
            details[key] = {
                "displayValue": audit.get("displayValue", "N/A"),
                "score": audit.get("score"),
            }

    return score_0_100, details


async def scan(url: str) -> AxisResult:
    """Scanne la performance d'une URL via Lighthouse.

    Exécute Lighthouse CLI en mode headless, parse le résultat JSON,
    et retourne un score normalisé sur 10.

    Args:
        url: URL du site à scanner.

    Returns:
        AxisResult avec le score performance normalisé.

    Raises:
        FileNotFoundError: Si Lighthouse n'est pas installé.
        RuntimeError: Si Lighthouse échoue ou timeout.
        ValueError: Si le rapport est invalide.
    """
    lighthouse_bin = _find_lighthouse()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.json"

        cmd = [
            lighthouse_bin,
            url,
            "--output=json",
            f"--output-path={output_path}",
            '--chrome-flags=--headless=new --no-sandbox --disable-gpu',
            "--quiet",
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=LIGHTHOUSE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
            raise RuntimeError(
                f"Lighthouse timeout après {LIGHTHOUSE_TIMEOUT_SECONDS}s pour {url}"
            ) from None
        except OSError as e:
            raise RuntimeError(f"Impossible de lancer Lighthouse : {e}") from e

        if process.returncode != 0:
            error_msg = stderr.decode(errors="replace").strip()
            raise RuntimeError(
                f"Lighthouse a échoué (code {process.returncode}) : {error_msg}"
            )

        if not output_path.exists():
            raise RuntimeError("Lighthouse n'a pas généré de rapport JSON")

        score_0_100, details = _parse_lighthouse_json(output_path)
        raw_json = json.loads(output_path.read_text(encoding="utf-8"))

    osiris_score = _normalize_score(score_0_100)

    return AxisResult(
        score=osiris_score,
        details={
            "lighthouse_score": score_0_100,
            "metrics": details,
        },
        tool_used="Lighthouse",
        raw_output=raw_json,
    )
