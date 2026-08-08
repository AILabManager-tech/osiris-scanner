"""Régressions du contrat de statut et de traçabilité OSIRIS."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

import report
import scanner
from axes.performance import AxisResult
from history import ScanHistory
from report import generate_json_report, generate_markdown_report, generate_pdf_report

EXPECTED_AXES = tuple("OSIRVL")


def _result(score: float = 8.0, *, details: dict | None = None) -> AxisResult:
    return AxisResult(score=score, details=details or {}, tool_used="synthetic")


def _full_results(*, legal_indeterminate: bool = False) -> dict[str, AxisResult]:
    results = {axis: _result() for axis in EXPECTED_AXES}
    if legal_indeterminate:
        results["L"] = _result(
            10.0,
            details={
                "statut": "indetermine",
                "audit": {"statut": "indetermine", "conforme": None},
                "preuves": ["preuve-L"],
                "limites": ["citation légale manquante"],
            },
        )
    return results


def _extract_pdf_text(path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", str(path), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_cli_all_failed_returns_nonzero_and_persists_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def fail_axis(
        _url: str,
        axis_key: str,
        axis_label: str,
        *_args: object,
        **_kwargs: object,
    ) -> scanner.AxisFailure:
        return scanner.AxisFailure(
            axis=axis_key,
            label=axis_label,
            error_type="RuntimeError",
            message="service indisponible",
        )

    monkeypatch.setattr(scanner, "_scan_axis", fail_axis)
    monkeypatch.chdir(tmp_path)

    invocation = CliRunner().invoke(scanner.main, ["--url", "https://example.com"])

    assert invocation.exit_code == 1
    assert "Aucun axe n'a réussi" in invocation.output
    history = ScanHistory(str(tmp_path / "osiris_history.db"))
    latest = history.get_latest("example.com")
    history.close()
    assert latest is not None
    assert latest["status_global"] == "failed"
    assert latest["grade"] == "Échec"


@pytest.mark.asyncio
async def test_partial_scan_persists_missing_axes_errors_and_real_timeouts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def partial_axis(
        _url: str,
        axis_key: str,
        axis_label: str,
        *_args: object,
        **_kwargs: object,
    ) -> AxisResult | scanner.AxisFailure:
        if axis_key != "V":
            return _result()
        return scanner.AxisFailure(
            axis=axis_key,
            label=axis_label,
            error_type="TimeoutError",
            message="délai dépassé",
            kind="timeout",
        )

    monkeypatch.setattr(scanner, "_scan_axis", partial_axis)
    monkeypatch.setenv("OSIRIS_BUILD_ID", "OSIRIS-partial-test")
    monkeypatch.setenv("OSIRIS_BUILD_COMMIT", "6d6102db463ce9b59b951786af74fb98bf715253")
    monkeypatch.chdir(tmp_path)

    status = await scanner._run_scan("https://example.com")

    assert status == "partial"
    history = ScanHistory(str(tmp_path / "osiris_history.db"))
    latest = history.get_latest("example.com")
    history.close()
    assert latest is not None
    assert latest["status_global"] == "partial"
    assert latest["timeouts"] == 1
    assert latest["build_id"] == "OSIRIS-partial-test"
    assert latest["build_commit"] == "6d6102db463ce9b59b951786af74fb98bf715253"
    assert latest["provenance_source"] == "runner_env"
    assert latest["provenance_status"] == "observed"
    assert json.loads(latest["missing_axes_json"]) == ["V"]
    assert json.loads(latest["axis_errors_json"])["V"]["kind"] == "timeout"


@pytest.mark.asyncio
async def test_axis_failures_distinguish_timeout_exception_and_missing_result() -> None:
    async def timeout_scan(_url: str) -> AxisResult:
        raise TimeoutError("délai réseau")

    async def error_scan(_url: str) -> AxisResult:
        raise RuntimeError("réponse invalide")

    async def missing_scan(_url: str) -> None:
        return None

    timeout = await scanner._scan_axis(
        "https://example.com",
        "X",
        "Timeout",
        timeout_scan,
        (TimeoutError,),
    )
    error = await scanner._scan_axis(
        "https://example.com",
        "Y",
        "Erreur",
        error_scan,
        (RuntimeError,),
    )
    missing = await scanner._scan_axis(
        "https://example.com",
        "Z",
        "Absent",
        missing_scan,
        (RuntimeError,),
    )

    assert isinstance(timeout, scanner.AxisFailure)
    assert timeout.kind == "timeout"
    assert isinstance(error, scanner.AxisFailure)
    assert error.kind == "error"
    assert isinstance(missing, scanner.AxisFailure)
    assert missing.kind == "missing_result"


def test_partial_reports_expose_same_status_missing_axes_errors_and_metadata(
    tmp_path: Path,
) -> None:
    results = _full_results()
    del results["I"]
    del results["V"]
    errors = {
        "I": {
            "axis": "I",
            "label": "Intrusion",
            "error_type": "TimeoutError",
            "message": "délai dépassé",
            "kind": "timeout",
        },
        "V": {
            "axis": "V",
            "label": "Sovereignty",
            "error_type": "RuntimeError",
            "message": "réponse absente",
            "kind": "error",
        },
    }
    meta = {
        "mode": "deep",
        "runs": 3,
        "timeouts": 99,
        "expected_axes": list(EXPECTED_AXES),
        "axis_errors": errors,
    }

    json_path = generate_json_report(
        "https://example.com", results, 6.5, "À risque", str(tmp_path), meta
    )
    md_path = generate_markdown_report(
        "https://example.com", results, 6.5, "À risque", str(tmp_path), meta
    )
    pdf_path = generate_pdf_report(
        "https://example.com", results, 6.5, "À risque", str(tmp_path), meta
    )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")
    pdf = _extract_pdf_text(pdf_path)
    assert data["status"] == "partial"
    assert data["grade"] == "Partiel"
    assert data["missing_axes"] == ["I", "V"]
    assert data["meta"]["timeouts"] == 1
    for content in (markdown, pdf):
        normalized = " ".join(content.split())
        assert "partial" in normalized
        assert "Partiel" in normalized
        assert "I, V" in normalized
        assert "TimeoutError" in normalized
        assert "RuntimeError" in normalized
        assert "délai dépassé" in normalized
        assert "réponse absente" in normalized
        assert "deep" in normalized
        assert "3" in normalized


def test_all_failed_reports_use_failed_status_in_all_formats(tmp_path: Path) -> None:
    errors = {
        axis: {
            "axis": axis,
            "label": axis,
            "error_type": "RuntimeError",
            "message": "échec synthétique",
            "kind": "error",
        }
        for axis in EXPECTED_AXES
    }
    meta = {"expected_axes": list(EXPECTED_AXES), "axis_errors": errors}

    json_path = generate_json_report(
        "https://failed.example", {}, 0.0, "Critique", str(tmp_path), meta
    )
    md_path = generate_markdown_report(
        "https://failed.example", {}, 0.0, "Critique", str(tmp_path), meta
    )
    pdf_path = generate_pdf_report(
        "https://failed.example", {}, 0.0, "Critique", str(tmp_path), meta
    )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")
    pdf = _extract_pdf_text(pdf_path)
    assert data["status"] == "failed"
    assert data["grade"] == "Échec"
    assert data["missing_axes"] == list(EXPECTED_AXES)
    for content in (markdown, pdf):
        assert "failed" in content
        assert "Échec" in content
        assert "O, S, I, R, V, L" in content


def test_complete_report_keeps_numeric_grade(tmp_path: Path) -> None:
    path = generate_json_report(
        "https://complete.example", _full_results(), 8.0, "Conforme", str(tmp_path)
    )
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["status"] == "complete"
    assert data["grade"] == "Conforme"


def test_legal_indeterminate_never_presents_conforme_and_pdf_keeps_evidence(
    tmp_path: Path,
) -> None:
    results = _full_results(legal_indeterminate=True)
    meta = {"expected_axes": list(EXPECTED_AXES)}

    json_path = generate_json_report(
        "https://example.com", results, 8.3, "Conforme", str(tmp_path), meta
    )
    md_path = generate_markdown_report(
        "https://example.com", results, 8.3, "Conforme", str(tmp_path), meta
    )
    pdf_path = generate_pdf_report(
        "https://example.com", results, 8.3, "Conforme", str(tmp_path), meta
    )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")
    pdf = _extract_pdf_text(pdf_path)
    assert data["status"] == "indeterminate"
    assert data["score_grade"] == "Conforme"
    assert data["grade"] == "Indéterminé"
    assert "8.3/10 (Conforme)" not in markdown
    assert "8.3/10 (Conforme)" not in pdf
    for content in (markdown, pdf):
        normalized = " ".join(content.split())
        assert "indeterminate" in normalized
        assert "Indéterminé" in normalized
        assert "preuve-L" in normalized
        assert "citation légale manquante" in normalized
        assert "avis juridique" in normalized


def test_same_domain_same_day_reports_do_not_overwrite(tmp_path: Path) -> None:
    results = _full_results()
    first = generate_json_report("https://example.com", results, 8.0, "Conforme", str(tmp_path))
    first_content = first.read_text(encoding="utf-8")
    second = generate_json_report("https://example.com", results, 6.0, "À risque", str(tmp_path))

    assert first != second
    assert first.exists() and second.exists()
    assert first.read_text(encoding="utf-8") == first_content
    assert json.loads(second.read_text(encoding="utf-8"))["score"] == 6.0

    for generator in (generate_markdown_report, generate_pdf_report):
        first_format = generator("https://example.com", results, 8.0, "Conforme", str(tmp_path))
        original = first_format.read_bytes()
        second_format = generator("https://example.com", results, 6.0, "À risque", str(tmp_path))
        assert first_format != second_format
        assert first_format.read_bytes() == original


def test_runner_provenance_crosses_json_markdown_and_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    build_id = "OSIRIS-validation-20260805T230000Z"
    build_commit = "6d6102db463ce9b59b951786af74fb98bf715253"
    monkeypatch.setenv("OSIRIS_BUILD_ID", build_id)
    monkeypatch.setenv("OSIRIS_BUILD_COMMIT", build_commit)
    monkeypatch.setattr(report, "BUILD_MANIFEST_PATH", tmp_path / "missing-manifest.json")

    json_path = generate_json_report(
        "https://example.com", _full_results(), 8.0, "Conforme", str(tmp_path)
    )
    md_path = generate_markdown_report(
        "https://example.com", _full_results(), 8.0, "Conforme", str(tmp_path)
    )
    pdf_path = generate_pdf_report(
        "https://example.com", _full_results(), 8.0, "Conforme", str(tmp_path)
    )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")
    pdf = _extract_pdf_text(pdf_path)

    assert data["provenance"] == {
        "build_id": build_id,
        "build_commit": build_commit,
        "source": "runner_env",
        "status": "observed",
    }
    assert data["meta"]["git_commit"] == build_commit
    for content in (markdown, pdf):
        assert build_id in content
        assert build_commit in content
        assert "runner_env" in content
        assert "observed" in content


def test_acceptance_technical_observation_crosses_all_report_formats(
    tmp_path: Path,
) -> None:
    results = _full_results()
    results["L"] = _result(
        details={
            "technical_observation": {
                "acceptance_branch": {
                    "status": "observed",
                    "before": {"trackers": []},
                    "action": {"performed": True},
                    "after": {"trackers": ["https://pixel.quantserve.com/after-accept"]},
                }
            },
            "legal_status": {"acceptance_branch": "not_assessed"},
        }
    )

    json_path = generate_json_report("https://example.com", results, 8.0, "Conforme", str(tmp_path))
    md_path = generate_markdown_report(
        "https://example.com", results, 8.0, "Conforme", str(tmp_path)
    )
    pdf_path = generate_pdf_report("https://example.com", results, 8.0, "Conforme", str(tmp_path))

    data = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")
    pdf = _extract_pdf_text(pdf_path)
    details = data["axes"]["L"]["details"]
    assert details["technical_observation"]["acceptance_branch"]["status"] == "observed"
    assert details["legal_status"]["acceptance_branch"] == "not_assessed"
    for content in (markdown, pdf):
        assert "technical_observation" in content
        assert "legal_status" in content
        assert "after-accept" in content
        assert "not_assessed" in content


def test_manifest_provenance_is_used_without_git(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "build-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "build_id": "OSIRIS-manifest-build",
                "build_commit": "6d6102db463ce9b59b951786af74fb98bf715253",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("OSIRIS_BUILD_ID", raising=False)
    monkeypatch.delenv("OSIRIS_BUILD_COMMIT", raising=False)
    monkeypatch.setenv("OSIRIS_BUILD_MANIFEST", str(manifest))

    provenance = report.resolve_build_provenance()

    assert provenance["build_id"] == "OSIRIS-manifest-build"
    assert provenance["build_commit"] == "6d6102db463ce9b59b951786af74fb98bf715253"
    assert provenance["source"] == "manifest"
    assert provenance["status"] == "observed"


def test_missing_provenance_stays_indeterminate_instead_of_guessing_git(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OSIRIS_BUILD_ID", raising=False)
    monkeypatch.delenv("OSIRIS_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("OSIRIS_BUILD_MANIFEST", raising=False)
    monkeypatch.setattr(report, "BUILD_MANIFEST_PATH", tmp_path / "missing-manifest.json")

    provenance = report.resolve_build_provenance()

    assert provenance == {
        "build_id": None,
        "build_commit": None,
        "source": "unavailable",
        "status": "indeterminate",
    }
