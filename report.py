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
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from axes.performance import AxisResult
from scoring import (
    _get_weights,
    get_formula_description,
    get_scan_status,
    get_status_grade,
)
from utils import extract_domain

# --- Constantes ---

OSIRIS_VERSION: str = "0.2.0"
REPORTS_DIR: str = "reports"
BUILD_MANIFEST_PATH: Path = Path(__file__).resolve().parent / "build-manifest.json"


def _provenance_value(value: Any) -> str | None:
    """Normalise une valeur explicite sans en fabriquer une par défaut."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _read_build_manifest(path: Path) -> dict[str, Any]:
    """Lit un manifeste explicite; un fichier absent ou invalide reste indéterminé."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_build_provenance() -> dict[str, str | None]:
    """Résout la provenance fournie par le runner ou un manifeste de build.

    Aucun appel à Git n'est fait ici. Un commit n'est publié que s'il a été
    fourni explicitement par le runner ou inscrit dans un manifeste livré avec
    le build.
    """
    explicit_manifest = _provenance_value(os.environ.get("OSIRIS_BUILD_MANIFEST"))
    manifest_path = Path(explicit_manifest) if explicit_manifest else BUILD_MANIFEST_PATH
    manifest = _read_build_manifest(manifest_path)

    env_build_id = _provenance_value(os.environ.get("OSIRIS_BUILD_ID"))
    env_commit = _provenance_value(os.environ.get("OSIRIS_BUILD_COMMIT"))
    manifest_build_id = _provenance_value(manifest.get("build_id"))
    manifest_commit = _provenance_value(manifest.get("build_commit", manifest.get("commit")))
    build_id = env_build_id or manifest_build_id
    build_commit = env_commit or manifest_commit

    sources: list[str] = []
    if env_build_id or env_commit:
        sources.append("runner_env")
    if (not env_build_id and manifest_build_id) or (not env_commit and manifest_commit):
        sources.append("manifest")

    return {
        "build_id": build_id,
        "build_commit": build_commit,
        "source": "+".join(sources) if sources else "unavailable",
        "status": "observed" if build_id or build_commit else "indeterminate",
    }


AXIS_LABELS: dict[str, str] = {
    "O": "Performance",
    "S": "Security",
    "I": "Intrusion",
    "R": "Resource",
    "V": "Sovereignty",
    "L": "Legal",
}

RECOMMENDATIONS: dict[str, dict[str, str]] = {
    "O": {
        "low": (
            "Optimisez les Core Web Vitals : compressez les images,"
            " minifiez JS/CSS, activez le lazy loading."
        ),
        "mid": (
            "Performance acceptable. Envisagez un CDN et le préchargement des ressources critiques."
        ),
        "high": "Excellente performance. Maintenez les bonnes pratiques.",
    },
    "S": {
        "low": ("Ajoutez les headers manquants : HSTS, CSP, X-Frame-Options, Referrer-Policy."),
        "mid": ("Sécurité partielle. Renforcez la CSP et activez Permissions-Policy."),
        "high": "Bonne posture sécurité. Envisagez un audit régulier.",
    },
    "I": {
        "low": (
            "Trop de trackers. Réduisez les scripts tiers"
            " et utilisez un gestionnaire de consentement."
        ),
        "mid": ("Quelques trackers présents. Vérifiez la conformité RGPD/CCPA."),
        "high": "Excellent respect de la vie privée. Peu de trackers.",
    },
    "R": {
        "low": (
            "Page trop lourde. Compressez les assets,"
            " réduisez les requêtes HTTP, optimisez les images."
        ),
        "mid": (
            "Poids acceptable. Utilisez des formats modernes (WebP, AVIF) et la compression Brotli."
        ),
        "high": "Page légère et éco-responsable. Empreinte minimale.",
    },
    "V": {
        "low": (
            "Sorties de territoire massives. Relocalisez vos données"
            " au Québec/Canada et évitez la dépendance aux GAFAM."
        ),
        "mid": (
            "Connexions GAFAM persistantes. Envisagez des alternatives"
            " souveraines pour vos flux critiques."
        ),
        "high": "Excellente souveraineté numérique. Flux locaux et écosystème maîtrisé.",
    },
    "L": {
        "low": (
            "Non-conformité Loi 25. Trackers actifs sans consentement"
            " ou après refus. RPP non identifié."
        ),
        "mid": (
            "Conformité partielle. Vérifiez l'exhaustivité des mentions"
            " légales et le mécanisme de refus."
        ),
        "high": "Respect rigoureux de la Loi 25. Consentement granulaire et transparence totale.",
    },
}


def _ordered_axes(keys: dict[str, Any] | list[str]) -> list[str]:
    """Retourne les clés d'axes dans l'ordre canonique OSIRVL.

    Les axes connus (O, S, I, R, V, L) viennent d'abord dans l'ordre de
    AXIS_LABELS ; tout axe additionnel (plugin tiers) est ajouté ensuite,
    trié. Pilote l'affichage et la sérialisation pour rester aligné sur le
    registre 6-axes sans hardcoder la liste partout.
    """
    present = set(keys)
    ordered = [k for k in AXIS_LABELS if k in present]
    extras = sorted(k for k in present if k not in AXIS_LABELS)
    return ordered + extras


def _get_recommendation(axis: str, score: float) -> str:
    """Retourne la recommandation appropriée pour un axe et un score.

    Args:
        axis: Clé de l'axe (O, S, I, R, V, L).
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
    """Extrait le domaine d'une URL (délègue à utils.extract_domain)."""
    return extract_domain(url)


def _axis_status(details: dict[str, Any]) -> str:
    """Extrait un statut d'axe à partir des schémas actuels et historiques."""
    audit = details.get("audit")
    if isinstance(audit, dict):
        status = audit.get("statut") or audit.get("status")
        if status:
            return str(status)
    return str(details.get("statut") or details.get("status") or "success")


def _axis_evidence(details: dict[str, Any]) -> list[Any]:
    evidence = details.get("evidence", details.get("preuves", []))
    return evidence if isinstance(evidence, list) else [evidence]


def _axis_limitations(details: dict[str, Any]) -> list[Any]:
    limitations = details.get("limitations", details.get("limites", []))
    return limitations if isinstance(limitations, list) else [limitations]


def _next_report_path(output_dir: Path, domain: str, suffix: str) -> Path:
    """Alloue un nom unique sans écraser un rapport produit le même jour."""
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    base = output_dir / f"{domain}_{date_str}.{suffix}"
    if not base.exists():
        return base
    index = 2
    while True:
        candidate = output_dir / f"{domain}_{date_str}_{index}.{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _global_limitations(mode: str) -> list[str]:
    limitations = []
    if mode == "fast":
        limitations.extend(
            [
                "Mode fast : les trackers chargés dynamiquement par JavaScript "
                "ne sont pas détectés.",
                "Mode fast : le poids total des sous-ressources n'est pas mesuré.",
            ]
        )
    else:
        limitations.append("Mode deep : les observations dépendent du rendu Playwright capturé.")
    limitations.extend(
        [
            "Lighthouse peut varier entre les runs et Observatory peut retourner "
            "un résultat caché.",
            "Ce rapport n'est ni un pentest, ni une certification de conformité, "
            "ni un avis juridique.",
        ]
    )
    return limitations


def _pdf_text(value: Any) -> str:
    """Sérialise et échappe une valeur pour un Paragraph ReportLab."""
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        rendered = str(value)
    return escape(rendered)


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

    weights = _get_weights()
    axes_data: dict[str, Any] = {}
    for axis_key in _ordered_axes(results):
        r = results[axis_key]
        axis_weight = weights.get(axis_key, 0.0)
        axes_data[axis_key] = {
            "label": AXIS_LABELS.get(axis_key, axis_key),
            "score": r.score,
            "weight": axis_weight,
            "weighted_score": round(r.score * axis_weight, 2),
            "tool_used": r.tool_used,
            "status": _axis_status(r.details),
            "evidence": _axis_evidence(r.details),
            "limitations": _axis_limitations(r.details),
            "details": r.details,
            "recommendation": (
                "Statut indéterminé : les preuves disponibles ne permettent pas de conclure."
                if axis_key == "L" and _axis_status(r.details) in {"indetermine", "indeterminate"}
                else _get_recommendation(axis_key, r.score)
            ),
        }

    # Build meta section
    resolved_provenance = resolve_build_provenance()
    meta: dict[str, Any] = {
        "timestamp": now,
        "build_id": resolved_provenance["build_id"],
        "build_commit": resolved_provenance["build_commit"],
        "git_commit": resolved_provenance["build_commit"],
        "provenance_source": resolved_provenance["source"],
        "provenance_status": resolved_provenance["status"],
        "mode": "fast",
        "runs": 1,
        "timeouts": 0,
    }
    if scan_meta:
        meta.update(scan_meta)

    expected_axes = list(meta.get("expected_axes") or weights)
    missing_axes = [axis for axis in _ordered_axes(expected_axes) if axis not in results]
    raw_errors = meta.get("axis_errors") or {}
    axis_errors = raw_errors if isinstance(raw_errors, dict) else {}
    status = get_scan_status(results, expected_axes)
    score_grade = grade
    display_grade = get_status_grade(status, score_grade)
    if axis_errors:
        meta["timeouts"] = sum(
            isinstance(error, dict) and error.get("kind") == "timeout"
            for error in axis_errors.values()
        )
    build_id = _provenance_value(meta.get("build_id"))
    build_commit = _provenance_value(meta.get("build_commit") or meta.get("git_commit"))
    provenance_source = _provenance_value(meta.get("provenance_source"))
    if not provenance_source:
        provenance_source = "unavailable"
    provenance_status = "observed" if build_id or build_commit else "indeterminate"
    meta["build_id"] = build_id
    meta["build_commit"] = build_commit
    meta["git_commit"] = build_commit
    meta["provenance_source"] = provenance_source
    meta["provenance_status"] = provenance_status
    meta["status_global"] = status
    meta["expected_axes"] = expected_axes
    meta["missing_axes"] = missing_axes
    meta["axis_errors"] = axis_errors
    scan_timestamp = str(meta["timestamp"])

    return {
        "osiris_version": OSIRIS_VERSION,
        "scan_date": scan_timestamp,
        "url": url,
        "domain": _extract_domain(url),
        "meta": meta,
        "provenance": {
            "build_id": build_id,
            "build_commit": build_commit,
            "source": provenance_source,
            "status": provenance_status,
        },
        "status": status,
        "score": osiris_score,
        "score_grade": score_grade,
        "grade": display_grade,
        "formula": get_formula_description(),
        "weights": _get_weights(),
        "missing_axes": missing_axes,
        "axis_errors": axis_errors,
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
    filepath = _next_report_path(out_dir, domain, "json")

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
    lines.append(f"| Statut global | {report_data['status']} |")
    lines.append(f"| Timeouts | {meta.get('timeouts', 0)} |")
    build_id = meta.get("build_id") or "N/A"
    build_commit = meta.get("build_commit") or "N/A"
    lines.append(f"| Build ID | `{build_id}` |")
    lines.append(f"| Build commit | `{build_commit}` |")
    lines.append(f"| Git commit | `{build_commit}` |")
    lines.append(f"| Provenance source | {meta.get('provenance_source', 'unavailable')} |")
    lines.append(f"| Provenance status | {meta.get('provenance_status', 'indeterminate')} |")
    lines.append(f"| Timestamp | {meta.get('timestamp', 'N/A')} |")
    lines.append("")

    # H2 — Score global
    lines.append("## Score Global")
    lines.append("")
    lines.append(f"**Score OSIRIS : {report_data['score']}/10 ({report_data['grade']})**")
    lines.append("")

    lines.append("## Couverture et erreurs")
    lines.append("")
    missing_axes = report_data["missing_axes"]
    lines.append(f"**Axes absents** : {', '.join(missing_axes) if missing_axes else 'aucun'}")
    lines.append("")
    axis_errors = report_data["axis_errors"]
    if axis_errors:
        for axis_key in _ordered_axes(axis_errors):
            error = axis_errors[axis_key]
            if isinstance(error, dict):
                lines.append(
                    f"- **{axis_key}** [{error.get('kind', 'error')}] "
                    f"{error.get('error_type', 'Error')} : {error.get('message', '')}"
                )
    else:
        lines.append("- Aucune erreur d'axe.")
    lines.append("")

    # H3 — Tableau comparatif des axes
    lines.append("### Tableau comparatif")
    lines.append("")
    lines.append("| Axe | Score | Poids | Score pondéré | Source |")
    lines.append("|-----|------:|------:|--------------:|--------|")
    for axis_key in report_data["axes"]:
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
    lines.append("")
    lines.append("| Axe | Poids |")
    lines.append("|-----|------:|")
    weights = report_data.get("weights", {})
    for axis_key in _ordered_axes(weights):
        label = AXIS_LABELS.get(axis_key, axis_key)
        lines.append(f"| {axis_key} — {label} | {int(weights[axis_key] * 100)}% |")
    lines.append("")

    # H2 — Détails par axe
    lines.append("## Détails par axe")
    lines.append("")

    for axis_key in report_data["axes"]:
        a = report_data["axes"][axis_key]

        # H3 — Chaque axe
        lines.append(f"### {axis_key} — {a['label']} ({a['score']}/10)")
        lines.append("")
        lines.append(f"**Source** : {a['tool_used']}")
        lines.append(f"**Statut** : {a['status']}")
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

    # Limitations
    lines.append("## Limitations")
    lines.append("")
    for limitation in _global_limitations(str(meta.get("mode", "fast"))):
        lines.append(f"- {limitation}")
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
    filepath = _next_report_path(out_dir, domain, "md")

    filepath.write_text(content, encoding="utf-8")

    return filepath


def generate_pdf_report(
    url: str,
    results: dict[str, AxisResult],
    osiris_score: float,
    grade: str,
    output_dir: str | None = None,
    scan_meta: dict[str, Any] | None = None,
) -> Path:
    """Génère un rapport PDF professionnel.

    Args:
        url: URL scannée.
        results: Résultats par axe.
        osiris_score: Score composite.
        grade: Grade OSIRIS.
        output_dir: Répertoire de sortie (défaut: reports/).
        scan_meta: Metadata de traçabilité.

    Returns:
        Chemin du fichier PDF généré.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        TableStyle,
    )
    from reportlab.platypus import (
        Table as RLTable,
    )

    report_data = _build_report_data(url, results, osiris_score, grade, scan_meta)

    out_dir = Path(output_dir or REPORTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    domain = _extract_domain(url)
    filepath = _next_report_path(out_dir, domain, "pdf")

    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "OsirisTitle",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "OsirisHeading",
        parent=styles["Heading2"],
        fontSize=14,
        spaceAfter=8,
    )
    body_style = styles["Normal"]

    elements: list = []

    # Title
    elements.append(Paragraph(f"Rapport OSIRIS — {domain}", title_style))
    elements.append(Spacer(1, 6 * mm))

    # Meta
    elements.append(Paragraph(f"<b>URL</b> : {_pdf_text(url)}", body_style))
    elements.append(Paragraph(f"<b>Date</b> : {report_data['scan_date']}", body_style))
    version = report_data["osiris_version"]
    elements.append(Paragraph(f"<b>Version</b> : OSIRIS {version}", body_style))
    meta = report_data["meta"]
    elements.append(Paragraph(f"<b>Statut global</b> : {report_data['status']}", body_style))
    elements.append(Paragraph(f"<b>Mode</b> : {_pdf_text(meta.get('mode', 'fast'))}", body_style))
    elements.append(Paragraph(f"<b>Runs Lighthouse</b> : {meta.get('runs', 1)}", body_style))
    elements.append(Paragraph(f"<b>Timeouts</b> : {meta.get('timeouts', 0)}", body_style))
    build_id = meta.get("build_id") or "N/A"
    build_commit = meta.get("build_commit") or "N/A"
    elements.append(Paragraph(f"<b>Build ID</b> : {_pdf_text(build_id)}", body_style))
    elements.append(Paragraph(f"<b>Build commit</b> : {_pdf_text(build_commit)}", body_style))
    elements.append(
        Paragraph(
            f"<b>Provenance source</b> : {_pdf_text(meta.get('provenance_source', 'unavailable'))}",
            body_style,
        )
    )
    elements.append(
        Paragraph(
            f"<b>Provenance status</b> : "
            f"{_pdf_text(meta.get('provenance_status', 'indeterminate'))}",
            body_style,
        )
    )
    elements.append(
        Paragraph(f"<b>Timestamp</b> : {_pdf_text(meta.get('timestamp', 'N/A'))}", body_style)
    )
    elements.append(Spacer(1, 4 * mm))

    # Score global
    display_grade = report_data["grade"]
    grade_color = {
        "Exemplaire": colors.HexColor("#2E7D32"),
        "Conforme": colors.HexColor("#1565C0"),
        "À risque": colors.HexColor("#F57F17"),
        "Critique": colors.HexColor("#C62828"),
        "Partiel": colors.HexColor("#F57F17"),
        "Indéterminé": colors.HexColor("#F57F17"),
        "Échec": colors.HexColor("#C62828"),
    }.get(display_grade, colors.black)

    elements.append(Paragraph("Score Global", heading_style))
    elements.append(
        Paragraph(
            f'<font size="16" color="{grade_color.hexval()}">'
            f"<b>{report_data['score']}/10 ({display_grade})</b></font>",
            body_style,
        )
    )
    elements.append(Spacer(1, 6 * mm))

    # Couverture et erreurs
    elements.append(Paragraph("Couverture et erreurs", heading_style))
    missing_axes = report_data["missing_axes"]
    missing_text = ", ".join(missing_axes) if missing_axes else "aucun"
    elements.append(Paragraph(f"<b>Axes absents</b> : {_pdf_text(missing_text)}", body_style))
    axis_errors = report_data["axis_errors"]
    if axis_errors:
        for axis_key in _ordered_axes(axis_errors):
            error = axis_errors[axis_key]
            elements.append(
                Paragraph(
                    f"<b>{_pdf_text(axis_key)}</b> : {_pdf_text(error)}",
                    body_style,
                )
            )
    else:
        elements.append(Paragraph("Aucune erreur d'axe.", body_style))
    elements.append(Spacer(1, 6 * mm))

    # Tableau des axes
    elements.append(Paragraph("Résultats par axe", heading_style))
    table_data = [["Axe", "Score", "Poids", "Statut", "Source"]]
    for axis_key in report_data["axes"]:
        a = report_data["axes"][axis_key]
        table_data.append(
            [
                f"{axis_key} — {a['label']}",
                f"{a['score']}/10",
                f"{int(a['weight'] * 100)}%",
                a["status"],
                a["tool_used"],
            ]
        )

    table = RLTable(table_data, colWidths=[105, 50, 45, 75, 205])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A237E")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("ALIGN", (1, 0), (3, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))

    # Détails nécessaires à l'audit, incluant le statut légal, les preuves et limites.
    elements.append(Paragraph("Détails, preuves et limites par axe", heading_style))
    for axis_key in report_data["axes"]:
        axis = report_data["axes"][axis_key]
        elements.append(
            Paragraph(
                f"<b>{_pdf_text(axis_key)} — {_pdf_text(axis['label'])}</b> "
                f"(statut : {_pdf_text(axis['status'])})",
                body_style,
            )
        )
        elements.append(Paragraph(f"<b>Preuves</b> : {_pdf_text(axis['evidence'])}", body_style))
        elements.append(Paragraph(f"<b>Limites</b> : {_pdf_text(axis['limitations'])}", body_style))
        details = axis.get("details", {})
        if isinstance(details, dict) and "technical_observation" in details:
            elements.append(
                Paragraph(
                    f"<b>technical_observation</b> : {_pdf_text(details['technical_observation'])}",
                    body_style,
                )
            )
        if isinstance(details, dict) and "legal_status" in details:
            elements.append(
                Paragraph(
                    f"<b>legal_status</b> : {_pdf_text(details['legal_status'])}",
                    body_style,
                )
            )
        elements.append(Spacer(1, 2 * mm))

    elements.append(Spacer(1, 4 * mm))

    # Recommandations
    elements.append(Paragraph("Recommandations", heading_style))
    for axis_key in report_data["axes"]:
        a = report_data["axes"][axis_key]
        rec = a.get("recommendation", "")
        if rec:
            elements.append(
                Paragraph(
                    f"<b>{axis_key} — {a['label']}</b> : {rec}",
                    body_style,
                )
            )
            elements.append(Spacer(1, 2 * mm))

    elements.append(Spacer(1, 6 * mm))

    # Formule
    elements.append(Paragraph("Méthodologie", heading_style))
    elements.append(
        Paragraph(
            f"<b>Formule</b> : {report_data['formula']}",
            body_style,
        )
    )
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("Limitations", heading_style))
    for limitation in _global_limitations(str(meta.get("mode", "fast"))):
        elements.append(Paragraph(f"• {_pdf_text(limitation)}", body_style))
    elements.append(Spacer(1, 4 * mm))

    # Footer
    elements.append(Spacer(1, 10 * mm))
    elements.append(
        Paragraph(
            f"<i>Rapport généré par OSIRIS Scanner v{OSIRIS_VERSION}</i>",
            ParagraphStyle("Footer", parent=body_style, fontSize=8, textColor=colors.grey),
        )
    )

    doc.build(elements)

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
        url,
        results,
        osiris_score,
        grade,
        output_dir,
        scan_meta,
    )
    md_path = generate_markdown_report(
        url,
        results,
        osiris_score,
        grade,
        output_dir,
        scan_meta,
    )

    # Persist and add convergence section
    try:
        from soic.converger import WebConverger
        from soic.osiris_adapter import save_osiris_scan
        from soic.persistence import RunStore

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
            extra_lines.append(f"**Historique** : {' -> '.join(f'{s:.1f}' for s in scores[-5:])}")
            extra_lines.append("")

        if extra_lines:
            existing = md_path.read_text(encoding="utf-8")
            md_path.write_text(
                existing + "\n".join(extra_lines),
                encoding="utf-8",
            )

    except ImportError:
        pass

    return json_path, md_path
