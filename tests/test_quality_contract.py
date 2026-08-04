"""Régressions de syntaxe, imports, CLI et prudence juridique."""

from __future__ import annotations

import importlib
import py_compile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from report import LEGAL_DISCLAIMER_EN, LEGAL_DISCLAIMER_FR
from scanner import ScanOutcome, main

ROOT = Path(__file__).parents[1]
PUBLIC_MODULES = (
    "scanner",
    "scoring",
    "report",
    "history",
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
