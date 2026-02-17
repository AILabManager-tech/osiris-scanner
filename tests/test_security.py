"""Tests unitaires pour axes/security.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
        assert _extract_host("https://example.com:8080/path") == "example.com:8080"

    def test_url_with_query(self) -> None:
        assert _extract_host("https://example.com?foo=bar") == "example.com"

    def test_http_url(self) -> None:
        assert _extract_host("http://sub.example.com") == "sub.example.com"


# --- Tests _analyze_headers ---


class TestAnalyzeHeaders:
    def test_all_headers_present(self) -> None:
        headers = {
            "strict-transport-security": "max-age=31536000",
            "content-security-policy": "default-src 'self'",
            "x-frame-options": "DENY",
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
            "permissions-policy": "camera=()",
        }
        score, presence = _analyze_headers(headers)
        assert score == 10.0
        assert all(presence.values())

    def test_no_headers(self) -> None:
        score, presence = _analyze_headers({})
        assert score == 0.0
        assert not any(presence.values())

    def test_partial_headers(self) -> None:
        headers = {
            "strict-transport-security": "max-age=31536000",
            "x-content-type-options": "nosniff",
        }
        score, presence = _analyze_headers(headers)
        assert score > 0.0
        assert score < 10.0
        assert presence["strict-transport-security"] is True
        assert presence["content-security-policy"] is False

    def test_extra_headers_ignored(self) -> None:
        headers = {
            "strict-transport-security": "max-age=31536000",
            "x-custom-header": "value",
            "server": "nginx",
        }
        score, presence = _analyze_headers(headers)
        assert presence["strict-transport-security"] is True
        assert "x-custom-header" not in presence


# --- Tests scan() ---


class TestScan:
    @pytest.mark.asyncio
    async def test_scan_success(self) -> None:
        """Test scan avec mocks Observatory + headers."""
        mock_observatory_response = MagicMock()
        mock_observatory_response.status_code = 200
        mock_observatory_response.json.return_value = {
            "grade": "B+",
            "score": 80,
            "tests_passed": 8,
            "tests_failed": 2,
        }
        mock_observatory_response.raise_for_status = MagicMock()

        mock_headers_response = MagicMock()
        mock_headers_response.status_code = 200
        mock_headers_response.headers = {
            "Strict-Transport-Security": "max-age=31536000",
            "Content-Security-Policy": "default-src 'self'",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Server": "nginx",
        }
        mock_headers_response.raise_for_status = MagicMock()

        with patch("axes.security.requests") as mock_requests:
            mock_requests.post.return_value = mock_observatory_response
            mock_requests.head.return_value = mock_headers_response
            mock_requests.Timeout = TimeoutError
            mock_requests.RequestException = Exception

            result = await scan("https://example.com")

        assert result.tool_used == "Mozilla Observatory + Headers"

        assert 0.0 <= result.score <= 10.0
        assert result.details["observatory_grade"] == "B+"
        assert "strict-transport-security" in result.details["headers_found"]
        assert "permissions-policy" in result.details["headers_missing"]

    @pytest.mark.asyncio
    async def test_scan_a_plus_all_headers(self) -> None:
        """Test scan avec grade A+ et tous les headers → score proche de 10."""
        mock_observatory_response = MagicMock()
        mock_observatory_response.json.return_value = {
            "grade": "A+",
            "score": 105,
            "tests_passed": 10,
            "tests_failed": 0,
        }
        mock_observatory_response.raise_for_status = MagicMock()

        mock_headers_response = MagicMock()
        mock_headers_response.status_code = 200
        mock_headers_response.headers = {
            "Strict-Transport-Security": "max-age=31536000",
            "Content-Security-Policy": "default-src 'self'",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=()",
        }
        mock_headers_response.raise_for_status = MagicMock()

        with patch("axes.security.requests") as mock_requests:
            mock_requests.post.return_value = mock_observatory_response
            mock_requests.head.return_value = mock_headers_response
            mock_requests.Timeout = TimeoutError
            mock_requests.RequestException = Exception

            result = await scan("https://secure-site.com")

        assert result.score == 10.0
        assert result.details["observatory_grade"] == "A+"

    @pytest.mark.asyncio
    async def test_scan_f_no_headers(self) -> None:
        """Test scan avec grade F et aucun header → score très bas."""
        mock_observatory_response = MagicMock()
        mock_observatory_response.json.return_value = {
            "grade": "F",
            "score": 10,
            "tests_passed": 3,
            "tests_failed": 7,
        }
        mock_observatory_response.raise_for_status = MagicMock()

        mock_headers_response = MagicMock()
        mock_headers_response.status_code = 200
        mock_headers_response.headers = {"Server": "apache"}
        mock_headers_response.raise_for_status = MagicMock()

        with patch("axes.security.requests") as mock_requests:
            mock_requests.post.return_value = mock_observatory_response
            mock_requests.head.return_value = mock_headers_response
            mock_requests.Timeout = TimeoutError
            mock_requests.RequestException = Exception

            result = await scan("https://insecure-site.com")

        assert result.score < 2.0
        assert result.details["observatory_grade"] == "F"
        assert len(result.details["headers_missing"]) == 6

    @pytest.mark.asyncio
    async def test_scan_observatory_error(self) -> None:
        """Test scan quand Observatory retourne une erreur."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "error": "invalid-hostname-lookup",
            "message": "Cannot resolve host",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("axes.security.requests") as mock_requests:
            mock_requests.post.return_value = mock_response
            mock_requests.Timeout = TimeoutError
            mock_requests.RequestException = Exception

            with pytest.raises(RuntimeError, match="Observatory erreur"):
                await scan("https://nonexistent.invalid")
