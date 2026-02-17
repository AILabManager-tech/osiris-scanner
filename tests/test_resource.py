"""Tests unitaires pour axes/resource.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from axes.resource import (
    _compute_score,
    _count_resources,
    _estimate_carbon_local,
    _extract_domain,
    scan,
)

# --- Tests _compute_score ---


class TestComputeScore:
    def test_under_500kb(self) -> None:
        assert _compute_score(400_000) == 10.0

    def test_exactly_500kb(self) -> None:
        assert _compute_score(500_000) == 10.0

    def test_over_5mb(self) -> None:
        assert _compute_score(6_000_000) == 0.0

    def test_exactly_5mb(self) -> None:
        assert _compute_score(5_000_000) == 0.0

    def test_midpoint(self) -> None:
        mid = (500_000 + 5_000_000) // 2  # 2_750_000
        score = _compute_score(mid)
        assert 4.0 <= score <= 6.0

    def test_1mb(self) -> None:
        score = _compute_score(1_000_000)
        assert 8.0 <= score <= 10.0

    def test_3mb(self) -> None:
        score = _compute_score(3_000_000)
        assert 3.0 <= score <= 6.0


# --- Tests _count_resources ---


class TestCountResources:
    def test_scripts_and_images(self) -> None:
        html = """
        <script src="app.js"></script>
        <script src="vendor.js"></script>
        <img src="logo.png" />
        <link href="style.css" rel="stylesheet" />
        """
        assert _count_resources(html) == 4

    def test_empty_html(self) -> None:
        assert _count_resources("<html><body></body></html>") == 0

    def test_inline_scripts_not_counted(self) -> None:
        html = "<script>console.log('hi')</script>"
        assert _count_resources(html) == 0

    def test_iframe(self) -> None:
        html = '<iframe src="https://embed.com/video"></iframe>'
        assert _count_resources(html) == 1


# --- Tests _estimate_carbon_local ---


class TestEstimateCarbonLocal:
    def test_zero_bytes(self) -> None:
        assert _estimate_carbon_local(0) == 0.0

    def test_1mb(self) -> None:
        gco2 = _estimate_carbon_local(1_000_000)
        assert gco2 > 0.0
        assert gco2 < 1.0  # Should be small

    def test_positive_correlation(self) -> None:
        small = _estimate_carbon_local(100_000)
        large = _estimate_carbon_local(1_000_000)
        assert large > small


# --- Tests _extract_domain ---


class TestExtractDomain:
    def test_simple(self) -> None:
        assert _extract_domain("https://example.com/path") == "example.com"

    def test_subdomain(self) -> None:
        assert _extract_domain("https://www.example.com") == "www.example.com"


# --- Tests scan() ---


class TestScan:
    @pytest.mark.asyncio
    async def test_scan_light_page(self) -> None:
        """Page légère → score élevé."""
        mock_page_response = MagicMock()
        mock_page_response.content = b"x" * 200_000  # 200 KB
        mock_page_response.text = "<html><body>Hello</body></html>"
        mock_page_response.raise_for_status = MagicMock()

        mock_green_response = MagicMock()
        mock_green_response.status_code = 200
        mock_green_response.json.return_value = {"green": True}

        mock_carbon_response = MagicMock()
        mock_carbon_response.status_code = 200
        mock_carbon_response.json.return_value = {
            "gco2e": 0.02,
            "rating": "A+",
            "cleanerThan": 0.95,
            "statistics": {
                "co2": {
                    "grid": {"grams": 0.02, "litres": 0.01},
                    "renewable": {"grams": 0.015, "litres": 0.008},
                },
            },
        }

        with patch("axes.resource.requests") as mock_requests:
            mock_requests.get.side_effect = [
                mock_page_response,
                mock_green_response,
                mock_carbon_response,
            ]
            mock_requests.Timeout = TimeoutError
            mock_requests.RequestException = Exception

            result = await scan("https://example.com")

        assert result.score == 10.0
        assert result.details["page_weight_bytes"] == 200_000
        assert result.details["green_hosting"] is True
        assert result.details["gco2"] == 0.02

    @pytest.mark.asyncio
    async def test_scan_heavy_page(self) -> None:
        """Page lourde → score bas."""
        mock_page_response = MagicMock()
        mock_page_response.content = b"x" * 4_000_000  # 4 MB
        mock_page_response.text = "<html><script src='a.js'></script></html>"
        mock_page_response.raise_for_status = MagicMock()

        mock_green_response = MagicMock()
        mock_green_response.status_code = 200
        mock_green_response.json.return_value = {"green": False}

        mock_carbon_response = MagicMock()
        mock_carbon_response.status_code = 200
        mock_carbon_response.json.return_value = {
            "gco2e": 0.8,
            "rating": "F",
            "cleanerThan": 0.05,
            "statistics": {
                "co2": {
                    "grid": {"grams": 0.8, "litres": 0.44},
                    "renewable": {"grams": 0.65, "litres": 0.36},
                },
            },
        }

        with patch("axes.resource.requests") as mock_requests:
            mock_requests.get.side_effect = [
                mock_page_response,
                mock_green_response,
                mock_carbon_response,
            ]
            mock_requests.Timeout = TimeoutError
            mock_requests.RequestException = Exception

            result = await scan("https://heavy-site.com")

        assert result.score < 3.0
        assert result.details["page_weight_bytes"] == 4_000_000
        assert result.details["green_hosting"] is False

    @pytest.mark.asyncio
    async def test_scan_carbon_api_down_fallback(self) -> None:
        """API Carbon down → fallback calcul local."""
        mock_page_response = MagicMock()
        mock_page_response.content = b"x" * 300_000
        mock_page_response.text = "<html></html>"
        mock_page_response.raise_for_status = MagicMock()

        mock_green_response = MagicMock()
        mock_green_response.status_code = 500  # API down

        mock_carbon_response = MagicMock()
        mock_carbon_response.status_code = 500  # API down

        with patch("axes.resource.requests") as mock_requests:
            mock_requests.get.side_effect = [
                mock_page_response,
                mock_green_response,
                mock_carbon_response,
            ]
            mock_requests.Timeout = TimeoutError
            mock_requests.RequestException = Exception

            result = await scan("https://example.com")

        assert result.score == 10.0
        assert "estimation locale" in result.details["carbon_source"]
        assert result.details["gco2"] > 0.0

    @pytest.mark.asyncio
    async def test_scan_page_timeout(self) -> None:
        """Page timeout → RuntimeError."""
        with patch("axes.resource.requests") as mock_requests:
            mock_requests.get.side_effect = mock_requests.Timeout("timeout")
            mock_requests.Timeout = type("Timeout", (Exception,), {})
            mock_requests.RequestException = Exception

            # The Timeout must be the right type
            mock_requests.get.side_effect = mock_requests.Timeout("timeout")

            with pytest.raises(RuntimeError, match="timeout"):
                await scan("https://slow-site.com")
