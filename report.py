"""Rapports OSIRIS JSON, Markdown et PDF à partir d'un modèle unique."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from axes import CANONICAL_AXIS_KEYS, discover_axes, registry
from axes.performance import AxisResult
from provenance import provenance_label, resolve_provenance
from scoring import (
    METHODOLOGY_VERSION,
    _get_weights,
    compute_score_summary,
    get_formula_description,
)
from utils import extract_domain

OSIRIS_VERSION = "0.3.0"
REPORTS_DIR = "reports"
LEGAL_DISCLAIMER_FR = (
    "Prédiagnostic technique automatisé. Ne constitue pas une certification de conformité "
    "ni un avis juridique."
)
LEGAL_DISCLAIMER_EN = (
    "Automated technical pre-assessment. It does not constitute compliance certification "
    "or legal advice."
)


def _resolved_provenance(meta: dict[str, Any]) -> dict[str, Any]:
    """Respecte une provenance déclarée, sinon la résout localement."""

    declared = meta.get("provenance")
    if isinstance(declared, dict) and declared:
        return declared
    return resolve_provenance().to_dict()


def _axis_status(result: AxisResult | None, error: str | None = None) -> str:
    if error:
        return "erreur technique"
    if result is None:
        return "non évalué"
    if result.coverage < 0.7:
        return "donnée insuffisante"
    if result.score >= 8.5:
        return "bon"
    if result.score >= 6.5:
        return "à surveiller"
    return "risque élevé"


def _fallback_recommendation(axis: str, score: float) -> str:
    recommendations = {
        "O": "Mesurer les Core Web Vitals et réduire les ressources bloquantes.",
        "S": "Vérifier les en-têtes et la configuration TLS selon le contexte applicatif.",
        "I": "Réduire les scripts tiers et documenter leurs finalités.",
        "R": "Réduire le poids transféré et optimiser les médias.",
        "V": "Vérifier les régions de traitement et les fournisseurs externes.",
        "L": "Faire confirmer les obligations applicables par une personne qualifiée.",
    }
    if score >= 8.5:
        return "Maintenir les contrôles observés et revalider après chaque changement majeur."
    return recommendations[axis]


def _build_report_data(
    url: str,
    results: dict[str, AxisResult],
    osiris_score: float,
    grade: str,
    scan_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit la source de vérité consommée par tous les formats."""

    discover_axes()
    now = datetime.now(UTC).isoformat()
    meta: dict[str, Any] = {
        "timestamp": now,
        "provenance": resolve_provenance().to_dict(),
        "mode": "fast",
        "runs": 1,
        "status": "complete" if len(results) == len(CANONICAL_AXIS_KEYS) else "partial",
        "duration_seconds": None,
        "timeouts": 0,
        "failed_axes": {},
    }
    if scan_meta:
        meta.update(scan_meta)
    provenance = _resolved_provenance(meta)
    meta["provenance"] = provenance
    meta["git_commit"] = provenance.get("commit_short")

    failed_axes = meta.get("failed_axes") or {}
    weights = _get_weights()
    summary = compute_score_summary(results) if results else None
    coverage_value = meta.get("coverage")
    coverage = float(
        coverage_value if coverage_value is not None else summary.coverage if summary else 0.0
    )
    technical_score = meta.get(
        "technical_score",
        summary.technical_score if summary else None,
    )
    reliability_value = meta.get("reliability_factor")
    reliability_factor = float(
        reliability_value
        if reliability_value is not None
        else summary.reliability_factor
        if summary
        else 0.0
    )

    axes_data: dict[str, Any] = {}
    priority_issues: list[dict[str, str]] = []
    for key in CANONICAL_AXIS_KEYS:
        info = registry.get(key)
        result = results.get(key)
        error = failed_axes.get(key)
        label = info.label if info else key
        if result is None:
            axes_data[key] = {
                "key": key,
                "label": label,
                "score": None,
                "weight": weights[key],
                "status": _axis_status(None, error),
                "error": error,
                "coverage": 0.0,
                "tool_used": None,
                "observations": [],
                "evidence": [],
                "risks": [],
                "recommendations": [],
                "limitations": [error or "Aucune donnée produite pour cet axe."],
                "details": {},
            }
            continue

        recommendations = list(result.recommendations)
        if not recommendations:
            recommendations.append(_fallback_recommendation(key, result.score))
        limitations = list(result.limitations)
        if error and error not in limitations:
            limitations.insert(0, error)
        axis_data = {
            "key": key,
            "label": label,
            "score": result.score,
            "weight": weights[key],
            "status": _axis_status(result, error),
            "error": error,
            "coverage": round(result.coverage, 3),
            "tool_used": result.tool_used,
            "observations": list(result.observations),
            "evidence": list(result.evidence),
            "risks": list(result.risks),
            "recommendations": recommendations,
            "limitations": limitations,
            "details": result.details,
        }
        axes_data[key] = axis_data
        priority_issues.extend({"axis": key, "label": label, "risk": risk} for risk in result.risks)

    global_limits = [
        "Les mesures dépendent du réseau, du rendu observé et de services externes.",
        "Une absence de preuve n'est ni une réussite ni la preuve d'une absence de risque.",
        LEGAL_DISCLAIMER_FR,
        LEGAL_DISCLAIMER_EN,
    ]
    if meta.get("status") == "partial":
        global_limits.insert(0, "Scan partiel : au moins un axe a rencontré une erreur technique.")

    return {
        "schema_version": "1.0.0",
        "osiris_version": OSIRIS_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "scan_date": now,
        "url": url,
        "domain": extract_domain(url),
        "meta": meta,
        "provenance": provenance,
        "summary": {
            "status": meta.get("status"),
            "score": osiris_score,
            "technical_score": technical_score,
            "grade": grade,
            "coverage": round(coverage, 3),
            "reliability_factor": round(reliability_factor, 3),
            "evaluated_axes": len(results),
            "total_axes": len(CANONICAL_AXIS_KEYS),
        },
        # Compatibilité de lecture avec les rapports 0.2.
        "score": osiris_score,
        "grade": grade,
        "formula": get_formula_description(),
        "weights": weights,
        "axes": axes_data,
        "priority_issues": priority_issues,
        "limitations": global_limits,
        "legal_disclaimer": {"fr": LEGAL_DISCLAIMER_FR, "en": LEGAL_DISCLAIMER_EN},
        "profiles": {
            "diagnostic_technique_loi_25": {
                "label": "Diagnostic technique Loi 25",
                "highlighted_axes": ["S", "I", "V", "L"],
                "scope": (
                    "Lecture ciblée des traceurs, du consentement observable, des services "
                    "externes, de la souveraineté apparente et des mentions visibles."
                ),
                "disclaimer": LEGAL_DISCLAIMER_FR,
            }
        },
    }


def _report_path(
    url: str,
    output_dir: str | None,
    suffix: str,
    report_data: dict[str, Any] | None = None,
) -> Path:
    directory = Path(output_dir or REPORTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    scan_id = str((report_data or {}).get("meta", {}).get("scan_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", scan_id):
        timestamp = str((report_data or {}).get("scan_date", ""))
        scan_id = re.sub(r"[^A-Za-z0-9]+", "", timestamp)[:64]
    if len(scan_id) < 8:
        scan_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    domain = re.sub(r"[^A-Za-z0-9.-]+", "-", extract_domain(url)).strip("-.") or "site"
    return directory / f"{domain}_{scan_id}.{suffix}"


def generate_json_report(
    url: str,
    results: dict[str, AxisResult],
    osiris_score: float,
    grade: str,
    output_dir: str | None = None,
    scan_meta: dict[str, Any] | None = None,
    *,
    report_data: dict[str, Any] | None = None,
) -> Path:
    data = report_data or _build_report_data(url, results, osiris_score, grade, scan_meta)
    path = _report_path(url, output_dir, "json", data)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def generate_markdown_report(
    url: str,
    results: dict[str, AxisResult],
    osiris_score: float,
    grade: str,
    output_dir: str | None = None,
    scan_meta: dict[str, Any] | None = None,
    *,
    report_data: dict[str, Any] | None = None,
) -> Path:
    data = report_data or _build_report_data(url, results, osiris_score, grade, scan_meta)
    summary = data["summary"]
    meta = data["meta"]
    lines = [
        f"# Rapport OSIRIS — {data['domain']}",
        "",
        f"**URL** : {url}",
        f"**Date** : {data['scan_date']}",
        f"**Version** : OSIRIS {OSIRIS_VERSION} · méthode {METHODOLOGY_VERSION}",
        "",
        f"> {LEGAL_DISCLAIMER_FR}",
        f"> {LEGAL_DISCLAIMER_EN}",
        "",
        "## 1. Résumé du scan",
        "",
        f"- État : **{summary['status']}**",
        f"- Mode : **{meta.get('mode', 'fast')}**",
        f"- Axes évalués : **{summary['evaluated_axes']}/{summary['total_axes']}**",
        f"- Durée : **{meta.get('duration_seconds', 'N/D')} s**",
        f"- Provenance : **{provenance_label(data.get('provenance'))}**",
        f"- Build ID : **{data.get('provenance', {}).get('build_id') or 'non disponible'}**",
        "",
        "## 2. Fiabilité et couverture",
        "",
        f"- Couverture pondérée : **{summary['coverage']:.0%}**",
        f"- Facteur de fiabilité : **{summary['reliability_factor']:.3f}**",
        f"- Score technique avant pénalité : **{summary['technical_score']}/10**",
        "",
        "## 3. Score global",
        "",
        f"**{summary['score']}/10 — {summary['grade']}**",
        "",
        "## 4. Scores par axe",
        "",
        "| Axe | Score | Poids | Couverture | Statut | Source |",
        "|---|---:|---:|---:|---|---|",
    ]
    for axis in data["axes"].values():
        score = "—" if axis["score"] is None else f"{axis['score']}/10"
        lines.append(
            f"| {axis['key']} — {axis['label']} | {score} | {axis['weight']:.0%} | "
            f"{axis['coverage']:.0%} | {axis['status']} | {axis['tool_used'] or '—'} |"
        )

    lines.extend(["", "## 5. Problèmes prioritaires", ""])
    if data["priority_issues"]:
        lines.extend(
            f"- **{issue['axis']} — {issue['label']}** : {issue['risk']}"
            for issue in data["priority_issues"]
        )
    else:
        lines.append("- Aucun risque prioritaire n'a été observé dans les données disponibles.")

    lines.extend(["", "## 6. Observations techniques", ""])
    for axis in data["axes"].values():
        lines.append(f"### {axis['key']} — {axis['label']}")
        lines.append("")
        if axis["observations"]:
            lines.extend(f"- {item}" for item in axis["observations"])
        else:
            lines.append("- Aucune observation disponible.")
        lines.append("")

    lines.extend(["## 7. Preuves", ""])
    for axis in data["axes"].values():
        if not axis["evidence"]:
            continue
        lines.append(f"### {axis['key']} — {axis['label']}")
        lines.append("")
        lines.extend(f"- `{_format_value(item)}`" for item in axis["evidence"])
        lines.append("")
    if not any(axis["evidence"] for axis in data["axes"].values()):
        lines.extend(["- Aucune preuve structurée disponible.", ""])

    lines.extend(["## 8. Recommandations", ""])
    for axis in data["axes"].values():
        for recommendation in axis["recommendations"]:
            lines.append(f"- **{axis['key']} — {axis['label']}** : {recommendation}")

    lines.extend(["", "## 9. Limites", ""])
    lines.extend(f"- {item}" for item in data["limitations"])
    for axis in data["axes"].values():
        lines.extend(f"- **{axis['key']}** : {item}" for item in axis["limitations"])

    lines.extend(
        [
            "",
            "## 10. Méthodologie",
            "",
            f"- Version : `{METHODOLOGY_VERSION}`",
            f"- Formule : `{data['formula']}`",
            f"- Poids : `{json.dumps(data['weights'], ensure_ascii=False)}`",
            "",
            "---",
            f"*Un outil Auxo Systems · OSIRIS Scanner v{OSIRIS_VERSION}*",
            "",
        ]
    )
    path = _report_path(url, output_dir, "md", data)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def generate_pdf_report(
    url: str,
    results: dict[str, AxisResult],
    osiris_score: float,
    grade: str,
    output_dir: str | None = None,
    scan_meta: dict[str, Any] | None = None,
    *,
    report_data: dict[str, Any] | None = None,
) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    data = report_data or _build_report_data(url, results, osiris_score, grade, scan_meta)
    path = _report_path(url, output_dir, "pdf", data)
    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "OsirisTitle",
            parent=styles["Title"],
            textColor=colors.HexColor("#183F32"),
            fontSize=19,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            "OsirisHeading",
            parent=styles["Heading2"],
            textColor=colors.HexColor("#183F32"),
            fontSize=13,
            spaceBefore=8,
            spaceAfter=6,
        )
    )
    body = styles["BodyText"]
    elements: list[Any] = [
        Paragraph(f"OSIRIS Scanner — {escape(data['domain'])}", styles["OsirisTitle"]),
        Paragraph("Diagnostic multidimensionnel de sites web · Un outil Auxo Systems", body),
        Spacer(1, 4 * mm),
        Paragraph(f"<b>URL :</b> {escape(url)}", body),
        Paragraph(f"<b>État :</b> {escape(str(data['summary']['status']))}", body),
        Paragraph(
            f"<b>Provenance :</b> {escape(provenance_label(data.get('provenance')))}",
            body,
        ),
        Paragraph(
            f"<b>Build ID :</b> "
            f"{escape(str(data.get('provenance', {}).get('build_id') or 'non disponible'))}",
            body,
        ),
        Paragraph(
            f"<b>Score :</b> {data['summary']['score']}/10 — {escape(grade)} · "
            f"couverture {data['summary']['coverage']:.0%}",
            body,
        ),
        Spacer(1, 4 * mm),
        Paragraph(escape(LEGAL_DISCLAIMER_FR), body),
        Paragraph(escape(LEGAL_DISCLAIMER_EN), body),
        Spacer(1, 5 * mm),
        Paragraph("Scores par axe", styles["OsirisHeading"]),
    ]
    table_rows: list[list[Any]] = [["Axe", "Score", "Couverture", "Statut"]]
    for axis in data["axes"].values():
        table_rows.append(
            [
                f"{axis['key']} — {axis['label']}",
                "—" if axis["score"] is None else f"{axis['score']}/10",
                f"{axis['coverage']:.0%}",
                axis["status"],
            ]
        )
    table = Table(table_rows, colWidths=[65 * mm, 25 * mm, 28 * mm, 40 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183F32")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CAD2CC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F1E8")]),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elements.extend([table, Spacer(1, 5 * mm)])

    sections = (
        ("Problèmes prioritaires", [item["risk"] for item in data["priority_issues"]]),
        (
            "Observations techniques",
            [
                f"{axis['key']} — {observation}"
                for axis in data["axes"].values()
                for observation in axis["observations"]
            ],
        ),
        (
            "Preuves",
            [
                f"{axis['key']} — {_format_value(item)}"
                for axis in data["axes"].values()
                for item in axis["evidence"]
            ],
        ),
        (
            "Recommandations",
            [
                f"{axis['key']} — {item}"
                for axis in data["axes"].values()
                for item in axis["recommendations"]
            ],
        ),
        (
            "Limites",
            data["limitations"]
            + [
                f"{axis['key']} — {item}"
                for axis in data["axes"].values()
                for item in axis["limitations"]
            ],
        ),
    )
    for heading, items in sections:
        elements.append(Paragraph(heading, styles["OsirisHeading"]))
        if not items:
            elements.append(Paragraph("Aucun élément observé.", body))
        for item in items:
            elements.append(Paragraph(f"• {escape(str(item))}", body))
            elements.append(Spacer(1, 1.5 * mm))

    elements.extend(
        [
            Paragraph("Méthodologie", styles["OsirisHeading"]),
            Paragraph(escape(data["formula"]), body),
            Paragraph(f"Version {METHODOLOGY_VERSION}", body),
            Spacer(1, 5 * mm),
            Paragraph(f"OSIRIS Scanner v{OSIRIS_VERSION} · Auxo Systems", body),
        ]
    )
    document.build(elements)
    return path


def generate_report_with_history(
    url: str,
    results: dict[str, AxisResult],
    osiris_score: float,
    grade: str,
    output_dir: str | None = None,
    scan_meta: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Compatibilité : génère JSON + Markdown sans dépendance SOIC privée."""

    data = _build_report_data(url, results, osiris_score, grade, scan_meta)
    return (
        generate_json_report(
            url,
            results,
            osiris_score,
            grade,
            output_dir,
            scan_meta,
            report_data=data,
        ),
        generate_markdown_report(
            url,
            results,
            osiris_score,
            grade,
            output_dir,
            scan_meta,
            report_data=data,
        ),
    )
