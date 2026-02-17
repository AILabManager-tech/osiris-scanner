"""OSIRIS Report — Génération de rapports JSON et Markdown.

Produit des rapports structurés incluant :
- Score global OSIRIS et grade
- Score détaillé par axe
- Détails techniques de chaque axe
- Recommandations
- Formule de scoring (transparence)
- Metadata de traçabilité (version, commit, mode, paramètres)
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from axes.performance import AxisResult
from scoring import (
    WEIGHTS,
    get_formula_description,
)

# --- Constantes ---

OSIRIS_VERSION: str = "0.2.0"
REPORTS_DIR: str = "reports"


def _get_git_commit() -> str | None:
    """Retourne le short hash du commit git courant, ou None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None

AXIS_LABELS: dict[str, str] = {
    "O": "Performance",
    "S": "Security",
    "I": "Intrusion",
    "R": "Resource",
}

RECOMMENDATIONS: dict[str, dict[str, str]] = {
    "O": {
        "low": (
            "Optimisez les Core Web Vitals : compressez les images,"
            " minifiez JS/CSS, activez le lazy loading."
        ),
        "mid": (
            "Performance acceptable. Envisagez un CDN"
            " et le préchargement des ressources critiques."
        ),
        "high": "Excellente performance. Maintenez les bonnes pratiques.",
    },
    "S": {
        "low": (
            "Ajoutez les headers manquants :"
            " HSTS, CSP, X-Frame-Options, Referrer-Policy."
        ),
        "mid": (
            "Sécurité partielle. Renforcez la CSP"
            " et activez Permissions-Policy."
        ),
        "high": "Bonne posture sécurité. Envisagez un audit régulier.",
    },
    "I": {
        "low": (
            "Trop de trackers. Réduisez les scripts tiers"
            " et utilisez un gestionnaire de consentement."
        ),
        "mid": (
            "Quelques trackers présents."
            " Vérifiez la conformité RGPD/CCPA."
        ),
        "high": "Excellent respect de la vie privée. Peu de trackers.",
    },
    "R": {
        "low": (
            "Page trop lourde. Compressez les assets,"
            " réduisez les requêtes HTTP, optimisez les images."
        ),
        "mid": (
            "Poids acceptable. Utilisez des formats modernes"
            " (WebP, AVIF) et la compression Brotli."
        ),
        "high": "Page légère et éco-responsable. Empreinte minimale.",
    },
}


def _get_recommendation(axis: str, score: float) -> str:
    """Retourne la recommandation appropriée pour un axe et un score.

    Args:
        axis: Clé de l'axe (O, S, I, R).
        score: Score de l'axe (0-10).

    Returns:
        Texte de recommandation.
    """
    recs = RECOMMENDATIONS.get(axis, {})
    if score < 5.0:
        return recs.get("low", "")
    if score < 8.0:
        return recs.get("mid", "")
    return recs.get("high", "")


def _extract_domain(url: str) -> str:
    """Extrait le domaine d'une URL.

    Args:
        url: URL complète.

    Returns:
        Domaine sans protocole.
    """
    parsed = urlparse(url)
    return parsed.hostname or "unknown"


def _build_report_data(
    url: str,
    results: dict[str, AxisResult],
    osiris_score: float,
    grade: str,
    scan_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit la structure de données du rapport.

    Args:
        url: URL scannée.
        results: Résultats par axe.
        osiris_score: Score composite.
        grade: Grade OSIRIS.
        scan_meta: Metadata de traçabilité (mode, runs, timeouts, etc.).

    Returns:
        Dictionnaire structuré pour le rapport.
    """
    now = datetime.now(UTC).isoformat()

    axes_data: dict[str, Any] = {}
    for axis_key in ["O", "S", "I", "R"]:
        if axis_key in results:
            r = results[axis_key]
            axes_data[axis_key] = {
                "label": AXIS_LABELS[axis_key],
                "score": r.score,
                "weight": WEIGHTS[axis_key],
                "weighted_score": round(r.score * WEIGHTS[axis_key], 2),
                "tool_used": r.tool_used,
                "details": r.details,
                "recommendation": _get_recommendation(axis_key, r.score),
            }

    # Build meta section
    meta: dict[str, Any] = {
        "timestamp": now,
        "git_commit": _get_git_commit(),
        "mode": "fast",
        "runs": 1,
        "timeouts": 0,
    }
    if scan_meta:
        meta.update(scan_meta)

    return {
        "osiris_version": OSIRIS_VERSION,
        "scan_date": now,
        "url": url,
        "domain": _extract_domain(url),
        "meta": meta,
        "score": osiris_score,
        "grade": grade,
        "formula": get_formula_description(),
        "weights": WEIGHTS,
        "axes": axes_data,
    }


def generate_json_report(
    url: str,
    results: dict[str, AxisResult],
    osiris_score: float,
    grade: str,
    output_dir: str | None = None,
    scan_meta: dict[str, Any] | None = None,
) -> Path:
    """Génère un rapport JSON structuré.

    Args:
        url: URL scannée.
        results: Résultats par axe.
        osiris_score: Score composite.
        grade: Grade OSIRIS.
        output_dir: Répertoire de sortie (défaut: reports/).
        scan_meta: Metadata de traçabilité.

    Returns:
        Chemin du fichier JSON généré.
    """
    report_data = _build_report_data(url, results, osiris_score, grade, scan_meta)

    out_dir = Path(output_dir or REPORTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    domain = _extract_domain(url)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    filename = f"{domain}_{date_str}.json"
    filepath = out_dir / filename

    filepath.write_text(
        json.dumps(report_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return filepath


def generate_markdown_report(
    url: str,
    results: dict[str, AxisResult],
    osiris_score: float,
    grade: str,
    output_dir: str | None = None,
    scan_meta: dict[str, Any] | None = None,
) -> Path:
    """Génère un rapport Markdown lisible.

    Args:
        url: URL scannée.
        results: Résultats par axe.
        osiris_score: Score composite.
        grade: Grade OSIRIS.
        output_dir: Répertoire de sortie (défaut: reports/).
        scan_meta: Metadata de traçabilité.

    Returns:
        Chemin du fichier Markdown généré.
    """
    report_data = _build_report_data(url, results, osiris_score, grade, scan_meta)

    lines: list[str] = []

    # H1 — Titre
    lines.append(f"# Rapport OSIRIS — {report_data['domain']}")
    lines.append("")
    lines.append(f"**URL** : {url}")
    lines.append(f"**Date** : {report_data['scan_date']}")
    lines.append(f"**Version OSIRIS** : {report_data['osiris_version']}")
    lines.append("")

    # H2 — Contexte de scan
    meta = report_data.get("meta", {})
    lines.append("## Contexte de scan")
    lines.append("")
    lines.append("| Parametre | Valeur |")
    lines.append("|-----------|--------|")
    lines.append(f"| Mode | {meta.get('mode', 'fast')} |")
    lines.append(f"| Runs Lighthouse | {meta.get('runs', 1)} |")
    lines.append(f"| Timeouts | {meta.get('timeouts', 0)} |")
    git_commit = meta.get("git_commit") or "N/A"
    lines.append(f"| Git commit | `{git_commit}` |")
    lines.append(f"| Timestamp | {meta.get('timestamp', 'N/A')} |")
    lines.append("")

    # H2 — Score global
    lines.append("## Score Global")
    lines.append("")
    lines.append(f"**Score OSIRIS : {osiris_score}/10 ({grade})**")
    lines.append("")

    # H3 — Tableau comparatif des 4 axes
    lines.append("### Tableau comparatif")
    lines.append("")
    lines.append("| Axe | Score | Poids | Score pondéré | Source |")
    lines.append("|-----|------:|------:|--------------:|--------|")
    for axis_key in ["O", "S", "I", "R"]:
        if axis_key in report_data["axes"]:
            a = report_data["axes"][axis_key]
            lines.append(
                f"| {axis_key} — {a['label']} "
                f"| {a['score']}/10 "
                f"| {int(a['weight'] * 100)}% "
                f"| {a['weighted_score']} "
                f"| {a['tool_used']} |"
            )
    lines.append("")

    # H2 — Formule
    lines.append("## Méthodologie")
    lines.append("")
    lines.append(f"**Formule** : `{report_data['formula']}`")
    lines.append("")
    lines.append("Les pondérations reflètent l'importance relative de chaque axe :")
    lines.append("- Sécurité et Intrusion (30% chacun) : priorité à la protection des utilisateurs")
    lines.append(
        "- Performance et Resource (20% chacun) :"
        " qualité de l'expérience et éco-responsabilité"
    )
    lines.append("")

    # H2 — Détails par axe
    lines.append("## Détails par axe")
    lines.append("")

    for axis_key in ["O", "S", "I", "R"]:
        if axis_key not in report_data["axes"]:
            continue
        a = report_data["axes"][axis_key]

        # H3 — Chaque axe
        lines.append(f"### {axis_key} — {a['label']} ({a['score']}/10)")
        lines.append("")
        lines.append(f"**Source** : {a['tool_used']}")
        lines.append("")

        details = a.get("details", {})
        if details:
            for key, value in details.items():
                if isinstance(value, list) and len(value) > 5:
                    lines.append(f"- **{key}** : {len(value)} éléments")
                elif isinstance(value, list):
                    lines.append(f"- **{key}** : {', '.join(str(v) for v in value) or 'aucun'}")
                elif isinstance(value, dict):
                    lines.append(f"- **{key}** :")
                    for k2, v2 in value.items():
                        lines.append(f"  - {k2}: {v2}")
                else:
                    lines.append(f"- **{key}** : {value}")
        lines.append("")

        # Recommandation
        rec = a.get("recommendation", "")
        if rec:
            lines.append(f"> **Recommandation** : {rec}")
            lines.append("")

    # Detect mode from details
    scan_mode = "fast"
    for axis_key in ["I", "R"]:
        if (
            axis_key in report_data["axes"]
            and report_data["axes"][axis_key].get("details", {}).get("mode") == "deep"
        ):
                scan_mode = "deep"
                break

    # Limitations
    lines.append("## Limitations")
    lines.append("")
    if scan_mode == "fast":
        lines.append("- **Mode** : fast (HTML statique)")
        lines.append(
            "- Axe I : analyse HTML uniquement — les trackers charges"
            " dynamiquement par JS ne sont pas detectes"
        )
        lines.append(
            "- Axe R : mesure le poids du HTML principal"
            " — pas le poids total des assets (images, JS, CSS)"
        )
    else:
        lines.append("- **Mode** : deep (Playwright headless)")
        lines.append(
            "- Axe I : capture les network requests reelles"
            " — detecte les trackers JS dynamiques"
        )
        lines.append(
            "- Axe R : mesure le poids total transfere"
            " — inclut tous les assets"
        )
    lines.append(
        "- Axe O : variance Lighthouse ~10% entre runs"
        " (utiliser --runs 3 pour mediane)"
    )
    lines.append("- Axe S : Observatory peut retourner des resultats caches (24h)")
    lines.append(
        "- Ce rapport n'est pas un pentest ni une certification de conformite"
    )
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Rapport généré par OSIRIS Scanner v{OSIRIS_VERSION}*")
    lines.append("")

    content = "\n".join(lines)

    out_dir = Path(output_dir or REPORTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    domain = _extract_domain(url)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    filename = f"{domain}_{date_str}.md"
    filepath = out_dir / filename

    filepath.write_text(content, encoding="utf-8")

    return filepath


def generate_report_with_history(
    url: str,
    results: dict[str, AxisResult],
    osiris_score: float,
    grade: str,
    output_dir: str | None = None,
    scan_meta: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Generate reports and persist to SOIC history.

    Calls existing report generators, then persists the scan
    and appends convergence/delta section to the Markdown report.

    Args:
        url: URL scannée.
        results: Résultats par axe.
        osiris_score: Score composite.
        grade: Grade OSIRIS.
        output_dir: Répertoire de sortie.
        scan_meta: Metadata de traçabilité.

    Returns:
        Tuple (json_path, md_path).
    """
    json_path = generate_json_report(
        url, results, osiris_score, grade, output_dir, scan_meta,
    )
    md_path = generate_markdown_report(
        url, results, osiris_score, grade, output_dir, scan_meta,
    )

    # Persist and add convergence section
    try:
        from soic_v3.converger import WebConverger
        from soic_v3.osiris_adapter import save_osiris_scan
        from soic_v3.persistence import RunStore

        store = RunStore()
        save_osiris_scan(url, results, osiris_score, grade, store)

        delta = store.get_delta(url)
        history = store.get_web_history(url, limit=10)

        extra_lines: list[str] = []

        if delta:
            extra_lines.append("")
            extra_lines.append("## Convergence")
            extra_lines.append("")
            delta_sign = "+" if delta.delta >= 0 else ""
            extra_lines.append(f"**Delta** : {delta_sign}{delta.delta}/10")
            if delta.improved_axes:
                extra_lines.append(f"- Axes ameliores : {', '.join(delta.improved_axes)}")
            if delta.regressed_axes:
                extra_lines.append(f"- Axes regreses : {', '.join(delta.regressed_axes)}")
            extra_lines.append("")

        if len(history) >= 2:
            scores = [h.get("osiris_score", 0.0) for h in history]
            wc = WebConverger()
            trend = wc.analyze_trend(scores)
            extra_lines.append(f"**Tendance** : {trend}")
            extra_lines.append(
                f"**Historique** : {' -> '.join(f'{s:.1f}' for s in scores[-5:])}"
            )
            extra_lines.append("")

        if extra_lines:
            existing = md_path.read_text(encoding="utf-8")
            md_path.write_text(
                existing + "\n".join(extra_lines), encoding="utf-8",
            )

    except ImportError:
        pass

    return json_path, md_path
