"""Contrat HTTP, accessibilité statique et téléchargements de l'interface."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import webapp
from axes import CANONICAL_AXIS_KEYS
from axes.performance import AxisResult
from scanner import ScanOutcome
from tests.conftest import first_free_port


@pytest.fixture
def web_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setattr(webapp, "STORE", webapp.JobStore())
    port = first_free_port()
    server = webapp.ThreadingHTTPServer(("127.0.0.1", port), webapp.OsirisHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _get(url: str) -> tuple[int, dict[str, str], bytes]:
    with urlopen(url, timeout=3) as response:  # noqa: S310 - fixture locale explicite
        return response.status, dict(response.headers.items()), response.read()


def test_home_is_accessible_and_hardened(web_server: str) -> None:
    status, headers, body = _get(web_server)
    html = body.decode("utf-8")
    assert status == 200
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Frame-Options"] == "DENY"
    assert '<html lang="fr-CA">' in html
    assert 'class="skip-link"' in html
    assert '<label for="scan-url">' in html
    assert 'id="results" hidden tabindex="-1"' in html
    assert "Prédiagnostic technique automatisé" in html


def test_head_exposes_security_headers_without_body(web_server: str) -> None:
    request = Request(web_server, method="HEAD")
    with urlopen(request, timeout=3) as response:  # noqa: S310 - fixture locale explicite
        assert response.status == 200
        assert response.headers["Content-Security-Policy"].startswith("default-src 'self'")
        assert int(response.headers["Content-Length"]) > 0
        assert response.read() == b""


def test_assets_have_focus_mobile_and_safe_dom_patterns(web_server: str) -> None:
    _, _, css = _get(f"{web_server}/styles.css")
    _, _, javascript = _get(f"{web_server}/app.js")
    css_text = css.decode("utf-8")
    js_text = javascript.decode("utf-8")
    assert ":focus-visible" in css_text
    assert "@media (max-width: 720px)" in css_text
    assert "prefers-reduced-motion" in css_text
    assert "textContent" in js_text
    assert "innerHTML" not in js_text
    assert 'summary.status === "partial" ? "scan partiel"' in js_text


def test_api_rejects_non_http_scheme(web_server: str) -> None:
    body = json.dumps({"url": "file:///etc/passwd", "mode": "fast"}).encode()
    request = Request(
        f"{web_server}/api/scans",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=3)  # noqa: S310 - fixture locale explicite
    assert error.value.code == 400


def test_completed_job_exposes_same_json_markdown_pdf(
    web_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = {
        key: AxisResult(
            score=8.0,
            coverage=1.0,
            tool_used="fixture",
            observations=[f"observation-{key}"],
            evidence=[{"axis": key}],
        )
        for key in CANONICAL_AXIS_KEYS
    }
    outcome = ScanOutcome(
        url="https://example.com/",
        mode="fast",
        status="complete",
        results=results,
        score=8.0,
        technical_score=8.0,
        grade="À surveiller",
        coverage=1.0,
        reliability_factor=1.0,
    )

    async def fake_scan(*_args: object, **_kwargs: object) -> ScanOutcome:
        return outcome

    monkeypatch.setattr(webapp, "execute_scan", fake_scan)
    job = webapp.STORE.create("https://example.com/", "fast", "loi25")
    webapp._run_job(job.id)

    _, _, payload_body = _get(f"{web_server}/api/scans/{job.id}")
    payload = json.loads(payload_body)
    assert payload["status"] == "complete"
    assert payload["result"]["meta"]["profile"] == "loi25"
    assert set(payload["downloads"]) == {"json", "markdown", "pdf"}
    for kind in ("json", "markdown", "pdf"):
        status, headers, body = _get(f"{web_server}{payload['downloads'][kind]}")
        assert status == 200
        assert "attachment" in headers["Content-Disposition"]
        assert body
    assert json.loads(_get(f"{web_server}{payload['downloads']['json']}")[2])["axes"].keys() == set(
        CANONICAL_AXIS_KEYS
    )


def test_static_resources_are_packaged() -> None:
    from importlib.resources import files

    assert files("osiris_web").joinpath("static", "index.html").is_file()
    assert files("blocklists").joinpath("trackers.json").is_file()


def test_job_pruning_removes_expired_reports(tmp_path) -> None:
    store = webapp.JobStore()
    expired = store.create("https://example.com/", "fast", "general")
    report_dir = tmp_path / expired.id
    report_dir.mkdir()
    report_path = report_dir / "report.json"
    report_path.write_text("{}", encoding="utf-8")
    store.update(expired.id, status="complete", report_paths={"json": report_path})
    expired.updated_at = time.time() - 3601

    store.create("https://example.org/", "fast", "general")

    assert store.get(expired.id) is None
    assert not report_dir.exists()
