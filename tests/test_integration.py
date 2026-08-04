"""Cohérence de bout en bout du score et des trois rapports."""

from __future__ import annotations

import json
from pathlib import Path

from pypdf import PdfReader

from axes import CANONICAL_AXIS_KEYS
from axes.performance import AxisResult
from report import (
    LEGAL_DISCLAIMER_EN,
    LEGAL_DISCLAIMER_FR,
    _build_report_data,
    generate_json_report,
    generate_markdown_report,
    generate_pdf_report,
    generate_report_with_history,
)
from scoring import METHODOLOGY_VERSION, compute_score_summary, get_grade


def _full_results() -> dict[str, AxisResult]:
    results: dict[str, AxisResult] = {}
    for index, key in enumerate(CANONICAL_AXIS_KEYS):
        results[key] = AxisResult(
            score=8.5 - index * 0.4,
            coverage=0.9,
            tool_used=f"outil-{key}",
            observations=[f"observation-{key}"],
            evidence=[{"type": "preuve", "axis": key}],
            risks=[f"risque-{key}"],
            recommendations=[f"recommandation-{key}"],
            limitations=[f"limite-{key}"],
            details={"axis": key},
        )
    return results


def test_all_formats_share_canonical_content(tmp_path: Path) -> None:
    results = _full_results()
    summary = compute_score_summary(results)
    grade = get_grade(summary.score)
    meta = {
        "scan_id": "integration-contract",
        "mode": "deep",
        "runs": 2,
        "status": "complete",
        "coverage": summary.coverage,
        "technical_score": summary.technical_score,
        "reliability_factor": summary.reliability_factor,
        "duration_seconds": 1.25,
        "failed_axes": {},
    }

    report_data = _build_report_data("https://example.com", results, summary.score, grade, meta)
    json_path = generate_json_report(
        "https://example.com",
        results,
        summary.score,
        grade,
        str(tmp_path),
        meta,
        report_data=report_data,
    )
    markdown_path = generate_markdown_report(
        "https://example.com",
        results,
        summary.score,
        grade,
        str(tmp_path),
        meta,
        report_data=report_data,
    )
    pdf_path = generate_pdf_report(
        "https://example.com",
        results,
        summary.score,
        grade,
        str(tmp_path),
        meta,
        report_data=report_data,
    )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)
    assert {json_path.stem, markdown_path.stem, pdf_path.stem} == {
        "example.com_integration-contract"
    }
    assert tuple(data["axes"]) == CANONICAL_AXIS_KEYS
    assert data["methodology_version"] == METHODOLOGY_VERSION
    assert data["summary"]["score"] == summary.score
    assert data["summary"]["coverage"] == summary.coverage
    assert data["meta"]["mode"] == "deep"
    assert data["profiles"]["diagnostic_technique_loi_25"]["highlighted_axes"] == [
        "S",
        "I",
        "V",
        "L",
    ]
    assert LEGAL_DISCLAIMER_FR in markdown
    assert LEGAL_DISCLAIMER_EN in markdown
    assert f"**{summary.score}/10 — {grade}**" in markdown
    for key in CANONICAL_AXIS_KEYS:
        axis = data["axes"][key]
        assert axis["observations"] == [f"observation-{key}"]
        assert axis["evidence"] == [{"type": "preuve", "axis": key}]
        assert axis["risks"] == [f"risque-{key}"]
        assert axis["recommendations"] == [f"recommandation-{key}"]
        assert axis["limitations"] == [f"limite-{key}"]
        assert f"{key} — {axis['label']}" in markdown
        assert f"{key} — {axis['label']}" in pdf_text
        assert f"observation-{key}" in pdf_text
    assert METHODOLOGY_VERSION in pdf_text
    assert LEGAL_DISCLAIMER_FR in pdf_text
    assert pdf_path.read_bytes().startswith(b"%PDF-")
    assert pdf_path.stat().st_size > 1_000


def test_partial_report_marks_missing_axis_without_inventing_score(tmp_path: Path) -> None:
    results = _full_results()
    del results["V"]
    summary = compute_score_summary(results)
    meta = {
        "status": "partial",
        "failed_axes": {"V": "RuntimeError: géolocalisation indisponible"},
    }
    path = generate_json_report(
        "https://example.com",
        results,
        summary.score,
        get_grade(summary.score),
        str(tmp_path),
        meta,
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["summary"]["status"] == "partial"
    assert data["axes"]["V"]["score"] is None
    assert data["axes"]["V"]["status"] == "erreur technique"
    assert "géolocalisation indisponible" in data["axes"]["V"]["limitations"][0]
    assert data["summary"]["evaluated_axes"] == 5


def test_deep_fallback_is_explicit_error_while_preserving_evidence() -> None:
    results = _full_results()
    data = _build_report_data(
        "https://example.com",
        results,
        7.0,
        "À surveiller",
        {
            "status": "partial",
            "failed_axes": {"O": "Repli après erreur Playwright : navigateur indisponible"},
        },
    )
    assert data["axes"]["O"]["score"] is not None
    assert data["axes"]["O"]["status"] == "erreur technique"
    assert "navigateur indisponible" in data["axes"]["O"]["error"]
    assert data["axes"]["O"]["evidence"]


def test_compatibility_report_bundle_uses_one_collision_safe_stem(tmp_path: Path) -> None:
    results = _full_results()
    summary = compute_score_summary(results)
    json_path, markdown_path = generate_report_with_history(
        "https://example.com",
        results,
        summary.score,
        get_grade(summary.score),
        str(tmp_path),
    )
    assert json_path.stem == markdown_path.stem
    assert len(json_path.stem) > len("example.com_2026-08-04")


def test_default_metadata_is_complete(tmp_path: Path) -> None:
    results = _full_results()
    summary = compute_score_summary(results)
    path = generate_json_report(
        "https://example.com",
        results,
        summary.score,
        get_grade(summary.score),
        str(tmp_path),
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["meta"]["mode"] == "fast"
    assert data["meta"]["runs"] == 1
    assert data["meta"]["timeouts"] == 0
    assert data["legal_disclaimer"] == {
        "fr": LEGAL_DISCLAIMER_FR,
        "en": LEGAL_DISCLAIMER_EN,
    }
