"""Tests d'intégration end-to-end pour OSIRIS Scanner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axes.performance import AxisResult
from report import generate_json_report, generate_markdown_report, generate_pdf_report
from scoring import compute_osiris_score, get_grade


def _mock_axis_result(score: float, tool: str, details: dict | None = None) -> AxisResult:
    """Helper pour créer un AxisResult mock."""
    return AxisResult(
        score=score,
        details=details or {},
        tool_used=tool,
        raw_output=None,
    )


class TestEndToEndWithMocks:
    """Test le pipeline complet : scan 6 axes OSIRVL → scoring → report."""

    def _make_full_results(self) -> dict[str, AxisResult]:
        return {
            "O": _mock_axis_result(
                7.5,
                "Lighthouse",
                {
                    "lighthouse_score": 75.0,
                    "metrics": {},
                },
            ),
            "S": _mock_axis_result(
                6.0,
                "Mozilla Observatory + Headers",
                {
                    "observatory_grade": "C+",
                    "observatory_score_raw": 60,
                    "observatory_tests_passed": 7,
                    "observatory_tests_failed": 3,
                    "headers_score": 5.0,
                    "headers_found": ["strict-transport-security"],
                    "headers_missing": ["content-security-policy"],
                },
            ),
            "I": _mock_axis_result(
                8.0,
                "OSIRIS Blocklist Analysis",
                {
                    "trackers_found": 3,
                    "tracker_domains": ["google-analytics.com"],
                    "third_party_domains": ["cdn.example.com"],
                    "first_party_domains": ["example.com"],
                    "total_domains": 5,
                    "first_party_ratio": 0.20,
                },
            ),
            "R": _mock_axis_result(
                9.0,
                "Page Weight + Website Carbon API",
                {
                    "page_weight_bytes": 350000,
                    "page_weight_kb": 341.8,
                    "resource_count": 12,
                    "gco2": 0.035,
                    "green_hosting": True,
                    "carbon_source": "Website Carbon API",
                    "carbon_rating": "A",
                    "cleaner_than": 0.85,
                },
            ),
            "V": _mock_axis_result(
                7.0,
                "Sovereignty Analysis",
                {"hosting_region": "EU", "cdn_region": "EU"},
            ),
            "L": _mock_axis_result(
                7.0,
                "Loi 25 Engine",
                {"cookie_banner": True, "privacy_policy": True},
            ),
        }

    def test_scoring_pipeline(self) -> None:
        """Vérifie que le scoring fonctionne sur des résultats complets."""
        results = self._make_full_results()
        score = compute_osiris_score(results)
        grade = get_grade(score)

        # Moyenne géométrique pondérée 6 axes (O7.5 S6 I8 R9 V7 L7) ≈ 7.2
        assert score == pytest.approx(7.2, abs=0.1)
        assert grade == "Conforme"

    def test_json_report_generation(self, tmp_path: Path) -> None:
        """Vérifie la génération du rapport JSON."""
        results = self._make_full_results()
        score = compute_osiris_score(results)
        grade = get_grade(score)

        json_path = generate_json_report(
            "https://example.com",
            results,
            score,
            grade,
            output_dir=str(tmp_path),
        )

        assert json_path.exists()
        assert json_path.suffix == ".json"

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["score"] == pytest.approx(7.2, abs=0.1)
        assert data["grade"] == "Conforme"
        assert data["url"] == "https://example.com"
        assert "formula" in data
        assert len(data["axes"]) == 6
        for axis_key in ["O", "S", "I", "R", "V", "L"]:
            assert axis_key in data["axes"]
            assert "score" in data["axes"][axis_key]
            assert "weight" in data["axes"][axis_key]
            assert "recommendation" in data["axes"][axis_key]

    def test_json_report_contains_meta(self, tmp_path: Path) -> None:
        """Vérifie que le rapport JSON contient la section meta."""
        results = self._make_full_results()
        score = compute_osiris_score(results)
        grade = get_grade(score)

        scan_meta = {"mode": "deep", "runs": 3, "timeouts": 1}
        json_path = generate_json_report(
            "https://example.com",
            results,
            score,
            grade,
            output_dir=str(tmp_path),
            scan_meta=scan_meta,
        )

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert "meta" in data
        assert data["meta"]["mode"] == "deep"
        assert data["meta"]["runs"] == 3
        assert data["meta"]["timeouts"] == 1
        assert "timestamp" in data["meta"]
        assert "git_commit" in data["meta"]

    def test_json_report_default_meta(self, tmp_path: Path) -> None:
        """Sans scan_meta explicite, les defaults sont remplis."""
        results = self._make_full_results()
        score = compute_osiris_score(results)
        grade = get_grade(score)

        json_path = generate_json_report(
            "https://example.com",
            results,
            score,
            grade,
            output_dir=str(tmp_path),
        )

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["meta"]["mode"] == "fast"
        assert data["meta"]["runs"] == 1
        assert data["meta"]["timeouts"] == 0

    def test_markdown_report_generation(self, tmp_path: Path) -> None:
        """Vérifie la génération du rapport Markdown."""
        results = self._make_full_results()
        score = compute_osiris_score(results)
        grade = get_grade(score)

        md_path = generate_markdown_report(
            "https://example.com",
            results,
            score,
            grade,
            output_dir=str(tmp_path),
        )

        assert md_path.exists()
        assert md_path.suffix == ".md"

        content = md_path.read_text(encoding="utf-8")

        # Vérifier la hiérarchie H1→H3
        assert content.startswith("# Rapport OSIRIS")
        assert "## Score Global" in content
        assert "## Méthodologie" in content
        assert "## Détails par axe" in content
        assert "### O — Performance" in content
        assert "### S — Security" in content
        assert "### I — Intrusion" in content
        assert "### R — Resource" in content
        assert "### V — Sovereignty" in content
        assert "### L — Legal" in content

        # Vérifier le tableau comparatif
        assert "| Axe | Score | Poids | Score pondéré | Source |" in content

        # Vérifier la formule (moyenne géométrique pondérée v5.0)
        assert "**Formule**" in content
        assert "Moyenne Géométrique Pondérée" in content

        # Vérifier les recommandations
        assert "Recommandation" in content

        # Vérifier la section contexte de scan
        assert "## Contexte de scan" in content
        assert "| Mode |" in content
        assert "| Runs Lighthouse |" in content
        assert "| Timeouts |" in content
        assert "| Git commit |" in content

    def test_markdown_report_with_meta(self, tmp_path: Path) -> None:
        """Vérifie que le Markdown reflète les paramètres de scan."""
        results = self._make_full_results()
        score = compute_osiris_score(results)
        grade = get_grade(score)

        scan_meta = {"mode": "deep", "runs": 3, "timeouts": 0}
        md_path = generate_markdown_report(
            "https://example.com",
            results,
            score,
            grade,
            output_dir=str(tmp_path),
            scan_meta=scan_meta,
        )

        content = md_path.read_text(encoding="utf-8")
        assert "| Mode | deep |" in content
        assert "| Runs Lighthouse | 3 |" in content

    def test_full_pipeline_extreme_good(self, tmp_path: Path) -> None:
        """Site parfait → score 10, grade Exemplaire."""
        results = {
            "O": _mock_axis_result(10.0, "Lighthouse"),
            "S": _mock_axis_result(10.0, "Observatory"),
            "I": _mock_axis_result(10.0, "Blocklist"),
            "R": _mock_axis_result(10.0, "Carbon"),
            "V": _mock_axis_result(10.0, "Sovereignty"),
            "L": _mock_axis_result(10.0, "Loi 25"),
        }
        score = compute_osiris_score(results)
        grade = get_grade(score)

        assert score == 10.0
        assert grade == "Exemplaire"

        json_path = generate_json_report(
            "https://perfect.example",
            results,
            score,
            grade,
            output_dir=str(tmp_path),
        )
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["score"] == 10.0
        assert data["grade"] == "Exemplaire"

    def test_full_pipeline_extreme_bad(self, tmp_path: Path) -> None:
        """Site catastrophique → score 0, grade Critique."""
        results = {
            "O": _mock_axis_result(0.0, "Lighthouse"),
            "S": _mock_axis_result(0.0, "Observatory"),
            "I": _mock_axis_result(0.0, "Blocklist"),
            "R": _mock_axis_result(0.0, "Carbon"),
            "V": _mock_axis_result(0.0, "Sovereignty"),
            "L": _mock_axis_result(0.0, "Loi 25"),
        }
        score = compute_osiris_score(results)
        grade = get_grade(score)

        # Plancher epsilon=0.1 (moyenne géométrique) → jamais 0.0 exact.
        assert score == 0.1
        assert grade == "Critique"

    def test_pdf_report_generation(self, tmp_path: Path) -> None:
        """Vérifie la génération du rapport PDF."""
        results = self._make_full_results()
        score = compute_osiris_score(results)
        grade = get_grade(score)

        pdf_path = generate_pdf_report(
            "https://example.com",
            results,
            score,
            grade,
            output_dir=str(tmp_path),
        )

        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        assert pdf_path.stat().st_size > 0
        # PDF files start with %PDF
        content = pdf_path.read_bytes()
        assert content[:5] == b"%PDF-"

    def test_report_data_consistency(self, tmp_path: Path) -> None:
        """Vérifie la cohérence entre JSON et Markdown."""
        results = self._make_full_results()
        score = compute_osiris_score(results)
        grade = get_grade(score)

        json_path = generate_json_report(
            "https://example.com",
            results,
            score,
            grade,
            output_dir=str(tmp_path),
        )
        md_path = generate_markdown_report(
            "https://example.com",
            results,
            score,
            grade,
            output_dir=str(tmp_path),
        )

        json_data = json.loads(json_path.read_text(encoding="utf-8"))
        md_content = md_path.read_text(encoding="utf-8")

        # Le score JSON doit apparaître dans le Markdown
        assert str(json_data["score"]) in md_content
        assert json_data["grade"] in md_content
