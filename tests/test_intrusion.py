"""Tests unitaires pour axes/intrusion.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axes.intrusion import (
    _classify_domains,
    _compute_score,
    _extract_domains_from_html,
    _extract_host,
    _is_tracker,
    _load_blocklist,
    scan,
    scan_deep,
)

# --- Tests _load_blocklist ---


class TestLoadBlocklist:
    def test_load_valid(self, tmp_path: Path) -> None:
        data = {"domains": ["google-analytics.com", "facebook.net"]}
        path = tmp_path / "trackers.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = _load_blocklist(str(path))
        assert "google-analytics.com" in result
        assert "facebook.net" in result

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            _load_blocklist("/nonexistent/path.json")

    def test_invalid_format(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"no_domains": True}), encoding="utf-8")
        with pytest.raises(ValueError, match="domains"):
            _load_blocklist(str(path))


# --- Tests _extract_host ---


class TestExtractHost:
    def test_simple(self) -> None:
        assert _extract_host("https://example.com/path") == "example.com"

    def test_subdomain(self) -> None:
        assert _extract_host("https://www.example.com") == "example.com"

    def test_deep_subdomain(self) -> None:
        assert _extract_host("https://a.b.example.com") == "example.com"


# --- Tests _extract_domains_from_html ---


class TestExtractDomainsFromHtml:
    def test_script_src(self) -> None:
        html = '<script src="https://cdn.example.com/app.js"></script>'
        domains = _extract_domains_from_html(html)
        assert "cdn.example.com" in domains

    def test_img_src(self) -> None:
        html = '<img src="https://pixel.tracker.com/p.gif" />'
        domains = _extract_domains_from_html(html)
        assert "pixel.tracker.com" in domains

    def test_protocol_relative(self) -> None:
        html = '<script src="//analytics.example.com/track.js"></script>'
        domains = _extract_domains_from_html(html)
        assert "analytics.example.com" in domains

    def test_relative_url_ignored(self) -> None:
        html = '<script src="/js/app.js"></script>'
        domains = _extract_domains_from_html(html)
        assert len(domains) == 0

    def test_multiple_domains(self) -> None:
        html = """
        <script src="https://a.com/x.js"></script>
        <img src="https://b.com/p.gif" />
        <link href="https://c.com/style.css" />
        """
        domains = _extract_domains_from_html(html)
        assert {"a.com", "b.com", "c.com"}.issubset(domains)

    def test_css_url(self) -> None:
        html = '<style>background: url("https://cdn.font.com/f.woff")</style>'
        domains = _extract_domains_from_html(html)
        assert "cdn.font.com" in domains


# --- Tests _is_tracker ---


class TestIsTracker:
    def test_exact_match(self) -> None:
        blocklist = {"google-analytics.com"}
        assert _is_tracker("google-analytics.com", blocklist) is True

    def test_subdomain_match(self) -> None:
        blocklist = {"hotjar.com"}
        assert _is_tracker("static.hotjar.com", blocklist) is True

    def test_no_match(self) -> None:
        blocklist = {"google-analytics.com"}
        assert _is_tracker("cdn.example.com", blocklist) is False

    def test_partial_no_match(self) -> None:
        blocklist = {"analytics.com"}
        assert _is_tracker("myanalytics.company.com", blocklist) is False


# --- Tests _classify_domains ---


class TestClassifyDomains:
    def test_classification(self) -> None:
        domains = {"www.example.com", "cdn.example.com", "google-analytics.com", "cdn.other.com"}
        blocklist = {"google-analytics.com"}
        first, third, trackers = _classify_domains(domains, "example.com", blocklist)
        assert "www.example.com" in first
        assert "cdn.example.com" in first
        assert "cdn.other.com" in third
        assert "google-analytics.com" in trackers

    def test_empty_domains(self) -> None:
        first, third, trackers = _classify_domains(set(), "example.com", set())
        assert first == []
        assert third == []
        assert trackers == []


# --- Tests _compute_score ---


class TestComputeScore:
    def test_no_trackers(self) -> None:
        assert _compute_score(0) == 10.0

    def test_max_trackers(self) -> None:
        assert _compute_score(15) == 0.0

    def test_above_max(self) -> None:
        assert _compute_score(20) == 0.0

    def test_some_trackers(self) -> None:
        score = _compute_score(5)
        assert 0.0 < score < 10.0
        assert score == round(10.0 * (1.0 - 5 / 15), 1)


# --- Tests scan() ---


class TestScan:
    @pytest.mark.asyncio
    async def test_scan_no_trackers(self, tmp_path: Path) -> None:
        """Page sans tracker → score 10."""
        blocklist_path = tmp_path / "trackers.json"
        blocklist_path.write_text(
            json.dumps({"domains": ["google-analytics.com"]}),
            encoding="utf-8",
        )

        html = '<html><script src="https://cdn.example.com/app.js"></script></html>'
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("axes.intrusion.requests.get", return_value=mock_response):
            result = await scan("https://example.com", blocklist_path=str(blocklist_path))

        assert result.score == 10.0
        assert result.details["trackers_found"] == 0

    @pytest.mark.asyncio
    async def test_scan_with_trackers(self, tmp_path: Path) -> None:
        """Page avec trackers → score réduit."""
        blocklist_path = tmp_path / "trackers.json"
        blocklist_path.write_text(
            json.dumps({"domains": ["google-analytics.com", "facebook.net", "hotjar.com"]}),
            encoding="utf-8",
        )

        html = """
        <html>
        <script src="https://www.google-analytics.com/analytics.js"></script>
        <script src="https://connect.facebook.net/sdk.js"></script>
        <script src="https://static.hotjar.com/c/hotjar.js"></script>
        <script src="https://cdn.example.com/app.js"></script>
        </html>
        """
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("axes.intrusion.requests.get", return_value=mock_response):
            result = await scan("https://example.com", blocklist_path=str(blocklist_path))

        assert result.score < 10.0
        assert result.details["trackers_found"] == 3
        assert len(result.details["tracker_domains"]) == 3

    @pytest.mark.asyncio
    async def test_scan_page_error(self, tmp_path: Path) -> None:
        """Page inaccessible → RuntimeError."""
        blocklist_path = tmp_path / "trackers.json"
        blocklist_path.write_text(
            json.dumps({"domains": ["example.com"]}),
            encoding="utf-8",
        )

        import requests as req_lib

        with (
            patch(
                "axes.intrusion.requests.get",
                side_effect=req_lib.Timeout("timeout"),
            ),
            pytest.raises(RuntimeError, match="timeout"),
        ):
            await scan("https://unreachable.com", blocklist_path=str(blocklist_path))


class TestScanDeep:
    """Tests for deep mode (Playwright-based)."""

    @pytest.mark.asyncio
    async def test_deep_detects_dynamic_trackers(self, tmp_path: Path) -> None:
        """Deep mode detects trackers loaded via JS that fast misses."""
        blocklist_path = tmp_path / "trackers.json"
        blocklist_path.write_text(
            json.dumps({"domains": ["google-analytics.com", "doubleclick.net"]}),
            encoding="utf-8",
        )

        # Mock Playwright: capture the on("request") handler, then fire it in goto
        captured_handler = None

        mock_page = AsyncMock()

        def fake_on(event: str, handler: object) -> None:
            nonlocal captured_handler
            if event == "request":
                captured_handler = handler

        mock_page.on = fake_on

        async def fake_goto(*_args: object, **_kwargs: object) -> None:
            # Simulate network requests hitting the captured handler
            if captured_handler:
                for url in [
                    "https://www.google-analytics.com/analytics.js",
                    "https://example.com/main.js",
                ]:
                    req = MagicMock()
                    req.url = url
                    captured_handler(req)

        mock_page.goto = fake_goto
        mock_page.wait_for_timeout = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw = AsyncMock()
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "playwright.async_api.async_playwright", return_value=mock_pw,
        ):
            result = await scan_deep(
                "https://example.com", blocklist_path=str(blocklist_path),
            )

        assert result.details["mode"] == "deep"
        assert result.details["trackers_found"] >= 1
        assert "www.google-analytics.com" in result.details["tracker_domains"]
        assert result.tool_used == "OSIRIS Deep Analysis (Playwright)"
