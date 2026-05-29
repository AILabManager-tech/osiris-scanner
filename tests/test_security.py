"""Tests unitaires pour axes/security.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from axes.security import (
    _analyze_headers,
    _extract_host,
    _grade_to_score,
    scan,
)

# --- Tests _grade_to_score ---


class TestGradeToScore:
    def test_a_plus(self) -> None:
        assert _grade_to_score("A+") == 10.0

    def test_a(self) -> None:
        assert _grade_to_score("A") == 9.5

    def test_f(self) -> None:
        assert _grade_to_score("F") == 1.5

    def test_unknown_grade(self) -> None:
        assert _grade_to_score("Z") == 0.0

    def test_b_plus(self) -> None:
        assert _grade_to_score("B+") == 8.5

    def test_d(self) -> None:
        assert _grade_to_score("D") == 4.0


# --- Tests _extract_host ---


class TestExtractHost:
    def test_simple_url(self) -> None:
        assert _extract_host("https://example.com") == "example.com"

    def test_url_with_path(self) -> None:
        assert _extract_host("https://example.com/path/page") == "example.com"

    def test_url_with_port(self) -> None:
        # Port is stripped for cleaner domain extraction (used in API calls)
        assert _extract_host("https://example.com:8080/path") == "example.com"

    def test_url_with_query(self) -> None:
        assert _extract_host("https://example.com?foo=bar") == "example.com"

    def test_http_url(self) -> None:
        assert _extract_host("http://sub.example.com") == "sub.example.com"


# --- Tests _analyze_headers ---


class TestAnalyzeHeaders:
    def test_all_headers_present_strong(self) -> None:
        """All headers present with strong values → high score."""
        headers = {
            "strict-transport-security": "max-age=31536000; includeSubDomains; preload",
            "content-security-policy": (
                "default-src 'self'; script-src 'self'; frame-ancestors 'self'"
            ),
            "x-frame-options": "DENY",
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
            "permissions-policy": "camera=(), microphone=(), geolocation=()",
        }
        score, analysis = _analyze_headers(headers)
        assert score == 10.0
        assert all(info["present"] for info in analysis.values())

    def test_no_headers(self) -> None:
        score, analysis = _analyze_headers({})
        assert score == 0.0
        assert not any(info["present"] for info in analysis.values())

    def test_partial_headers(self) -> None:
        headers = {
            "strict-transport-security": "max-age=31536000",
            "x-content-type-options": "nosniff",
        }
        score, analysis = _analyze_headers(headers)
        assert score > 0.0
        assert score < 10.0
        assert analysis["strict-transport-security"]["present"] is True
        assert analysis["content-security-policy"]["present"] is False

    def test_extra_headers_ignored(self) -> None:
        headers = {
            "strict-transport-security": "max-age=31536000",
            "x-custom-header": "value",
            "server": "nginx",
        }
        score, analysis = _analyze_headers(headers)
        assert analysis["strict-transport-security"]["present"] is True
        assert "x-custom-header" not in analysis

    def test_weak_hsts_penalized(self) -> None:
        """HSTS with short max-age gets lower quality score."""
        headers_strong = {"strict-transport-security": "max-age=31536000; includeSubDomains"}
        headers_weak = {"strict-transport-security": "max-age=3600"}
        score_strong, _ = _analyze_headers(headers_strong)
        score_weak, _ = _analyze_headers(headers_weak)
        assert score_strong > score_weak

    def test_csp_unsafe_inline_penalized(self) -> None:
        """CSP with unsafe-inline gets lower quality score."""
        headers_good = {"content-security-policy": "default-src 'self'"}
        headers_bad = {"content-security-policy": "default-src 'self' 'unsafe-inline'"}
        score_good, _ = _analyze_headers(headers_good)
        score_bad, _ = _analyze_headers(headers_bad)
        assert score_good > score_bad


# --- Tests scan() ---


class TestScan:
    async def test_scan_success(self) -> None:
        """Test scan avec mocks Observatory + headers."""
        observatory_data = {
            "grade": "B+",
            "score": 80,
            "tests_passed": 8,
            "tests_failed": 2,
        }
        raw_headers = {
            "strict-transport-security": "max-age=31536000",
            "content-security-policy": "default-src 'self'",
            "x-frame-options": "DENY",
            "x-content-type-options": "nosniff",
            "server": "nginx",
        }

        with (
            patch(
                "axes.security._fetch_observatory",
                new_callable=AsyncMock,
                return_value=observatory_data,
            ),
            patch("axes.security._fetch_headers", new_callable=AsyncMock, return_value=raw_headers),
        ):
            result = await scan("https://example.com")

        assert result.tool_used == "Mozilla Observatory + Headers"
        assert 0.0 <= result.score <= 10.0
        assert result.details["observatory_grade"] == "B+"
        assert "strict-transport-security" in result.details["headers_found"]
        assert "permissions-policy" in result.details["headers_missing"]

    async def test_scan_a_plus_all_headers(self) -> None:
        """Test scan avec grade A+ et tous les headers forts → score proche de 10."""
        observatory_data = {
            "grade": "A+",
            "score": 105,
            "tests_passed": 10,
            "tests_failed": 0,
        }
        raw_headers = {
            "strict-transport-security": "max-age=31536000; includeSubDomains; preload",
            "content-security-policy": (
                "default-src 'self'; script-src 'self'; frame-ancestors 'self'"
            ),
            "x-frame-options": "DENY",
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
            "permissions-policy": "camera=(), microphone=(), geolocation=()",
        }

        with (
            patch(
                "axes.security._fetch_observatory",
                new_callable=AsyncMock,
                return_value=observatory_data,
            ),
            patch("axes.security._fetch_headers", new_callable=AsyncMock, return_value=raw_headers),
        ):
            result = await scan("https://secure-site.com")

        assert result.score == 10.0
        assert result.details["observatory_grade"] == "A+"

    async def test_scan_f_no_headers(self) -> None:
        """Test scan avec grade F et aucun header → score très bas."""
        observatory_data = {
            "grade": "F",
            "score": 10,
            "tests_passed": 3,
            "tests_failed": 7,
        }
        raw_headers = {"server": "apache"}

        with (
            patch(
                "axes.security._fetch_observatory",
                new_callable=AsyncMock,
                return_value=observatory_data,
            ),
            patch("axes.security._fetch_headers", new_callable=AsyncMock, return_value=raw_headers),
        ):
            result = await scan("https://insecure-site.com")

        assert result.score < 2.0
        assert result.details["observatory_grade"] == "F"
        assert len(result.details["headers_missing"]) == 6

    async def test_scan_observatory_error(self) -> None:
        """Test scan quand Observatory retourne une erreur."""
        err_msg = (
            "Observatory erreur pour nonexistent.invalid :"
            " invalid-hostname-lookup — Cannot resolve host"
        )
        with (
            patch(
                "axes.security._fetch_observatory",
                new_callable=AsyncMock,
                side_effect=RuntimeError(err_msg),
            ),
            patch(
                "axes.security._fetch_headers",
                new_callable=AsyncMock,
                return_value={},
            ),
            pytest.raises(RuntimeError, match="Observatory erreur"),
        ):
            await scan("https://nonexistent.invalid")
