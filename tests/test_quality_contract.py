"""Régressions de syntaxe, imports, CLI et prudence juridique."""

from __future__ import annotations

import importlib
import json
import py_compile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner
from pypdf import PdfReader

from axes.performance import AxisResult
from history import ScanHistory
from provenance import ENV_BUILD_ID, ENV_COMMIT, ENV_COMMIT_STATE, resolve_provenance
from report import (
    LEGAL_DISCLAIMER_EN,
    LEGAL_DISCLAIMER_FR,
    _build_report_data,
    generate_markdown_report,
    generate_pdf_report,
)
from scanner import ScanOutcome, main
from scoring import compute_score_summary

ROOT = Path(__file__).parents[1]
PUBLIC_MODULES = (
    "scanner",
    "scoring",
    "report",
    "history",
    "provenance",
    "calibrate",
    "cache",
    "utils",
    "url_security",
    "blocklist_updater",
    "webapp",
    "axes.performance",
    "axes.security",
    "axes.intrusion",
    "axes.resource",
    "axes.sovereignty",
    "axes.legal",
)


def test_all_shipped_python_files_compile() -> None:
    paths = [*ROOT.glob("*.py"), *ROOT.glob("axes/*.py"), *ROOT.glob("benchmark/*.py")]
    assert paths
    for path in paths:
        py_compile.compile(str(path), doraise=True)


def test_all_public_modules_import() -> None:
    for module in PUBLIC_MODULES:
        assert importlib.import_module(module)


def test_report_syntax_regression_has_no_unmatched_brace() -> None:
    py_compile.compile(str(ROOT / "report.py"), doraise=True)


def test_cli_help_and_invalid_scheme() -> None:
    runner = CliRunner()
    help_result = runner.invoke(main, ["--help"])
    assert help_result.exit_code == 0
    assert "--mode [fast|deep]" in help_result.output

    invalid = runner.invoke(main, ["--url", "file:///etc/passwd"])
    assert invalid.exit_code == 2
    assert "HTTP et HTTPS" in invalid.output


def test_cli_fast_mode_calls_engine() -> None:
    outcome = ScanOutcome(url="https://example.com/", mode="fast", status="failed")
    with patch("scanner._run_scan", new_callable=AsyncMock, return_value=outcome) as run:
        result = CliRunner().invoke(main, ["--url", "https://example.com", "--mode", "fast"])
    assert result.exit_code == 1
    run.assert_awaited_once()


def test_product_language_avoids_absolute_legal_conclusions() -> None:
    product_files = [
        *ROOT.glob("*.py"),
        *ROOT.glob("axes/*.py"),
        *ROOT.glob("osiris_web/static/*"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in product_files)
    forbidden = (
        "conforme à la Loi 25",
        "non-conformité Loi 25",
        "respect garanti",
        "conformité démontrée",
        "Audit de Conformité Loi 25",
    )
    for phrase in forbidden:
        assert phrase.casefold() not in text.casefold()
    assert LEGAL_DISCLAIMER_FR in text
    assert LEGAL_DISCLAIMER_EN in text


def test_provenance_prefers_runner_then_packaged_manifest(tmp_path: Path, monkeypatch) -> None:
    commit = "6d6102db463ce9b59b951786af74fb98bf715253"
    package_manifest = tmp_path / "osiris_web" / "BUILD_INFO.json"
    package_manifest.parent.mkdir()
    package_manifest.write_text(
        json.dumps(
            {
                "schema": "osiris.provenance/1",
                "commit": commit,
                "commit_state": "derived",
                "build_id": "osiris-0.3.0-functional",
            }
        ),
        encoding="utf-8",
    )
    for name in (ENV_COMMIT, ENV_COMMIT_STATE, ENV_BUILD_ID):
        monkeypatch.delenv(name, raising=False)

    manifest = resolve_provenance(tmp_path)
    assert manifest.source == "manifest"
    assert manifest.commit == commit
    assert manifest.commit_state == "derived"
    assert manifest.build_id == "osiris-0.3.0-functional"

    monkeypatch.setenv(ENV_COMMIT, "abcdef1234567890")
    monkeypatch.setenv(ENV_COMMIT_STATE, "exact")
    monkeypatch.setenv(ENV_BUILD_ID, "runner-build")
    runner = resolve_provenance(tmp_path)
    assert runner.source == "runner_env"
    assert runner.commit == "abcdef1234567890"
    assert runner.build_id == "runner-build"


def test_invalid_commit_is_never_invented(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(ENV_COMMIT, "pas-un-sha")
    monkeypatch.delenv(ENV_BUILD_ID, raising=False)
    provenance = resolve_provenance(tmp_path)
    assert provenance.source == "unavailable"
    assert provenance.commit is None
    assert "Aucun commit n'est supposé" in (provenance.note or "")


def test_provenance_crosses_markdown_pdf_and_sqlite(tmp_path: Path) -> None:
    provenance = {
        "source": "manifest",
        "commit": "6d6102db463ce9b59b951786af74fb98bf715253",
        "commit_short": "6d6102d",
        "commit_state": "derived",
        "build_id": "osiris-0.3.0-functional",
        "manifest_path": "/artifact/BUILD_INFO.json",
        "note": "Build fonctionnel dérivé.",
    }
    results = {"O": AxisResult(score=8.0, coverage=1.0, tool_used="fixture")}
    summary = compute_score_summary(results)
    report_data = _build_report_data(
        "https://example.com",
        results,
        summary.score,
        "Donnée insuffisante",
        {"provenance": provenance},
    )
    markdown_path = generate_markdown_report(
        "https://example.com",
        results,
        summary.score,
        "Donnée insuffisante",
        str(tmp_path),
        report_data=report_data,
    )
    pdf_path = generate_pdf_report(
        "https://example.com",
        results,
        summary.score,
        "Donnée insuffisante",
        str(tmp_path),
        report_data=report_data,
    )
    markdown = markdown_path.read_text(encoding="utf-8")
    pdf = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)
    assert report_data["meta"]["git_commit"] == "6d6102d"
    assert report_data["provenance"] == provenance
    assert "osiris-0.3.0-functional" in markdown
    assert "osiris-0.3.0-functional" in pdf

    history = ScanHistory(str(tmp_path / "history.db"))
    history.save_scan(
        "example.com",
        "https://example.com",
        summary.score,
        "Donnée insuffisante",
        {"O": 8.0},
        provenance=provenance,
    )
    row = history.get_latest("example.com")
    history.close()
    assert row is not None
    assert row["provenance_commit"] == provenance["commit"]
    assert json.loads(row["provenance_json"])["build_id"] == provenance["build_id"]
