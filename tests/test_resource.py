"""Tests de l'axe ressources indépendant."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from axes.resource import (
    _compute_score,
    _count_resources,
    _estimate_carbon_local,
    _extract_domain,
    scan,
)


@pytest.mark.parametrize(
    ("size", "expected"),
    [(0, 10.0), (500_000, 10.0), (5_000_000, 0.0), (6_000_000, 0.0)],
)
def test_resource_score_bounds(size: int, expected: float) -> None:
    assert _compute_score(size) == expected


def test_count_resources_and_ignore_inline_script() -> None:
    html = """
    <script src="app.js"></script><script>void 0</script>
    <img src="logo.png"><link href="style.css"><iframe src="frame.html"></iframe>
    """
    assert _count_resources(html) == 4


def test_local_carbon_estimate_and_domain() -> None:
    assert _estimate_carbon_local(0) == 0.0
    assert _estimate_carbon_local(1_000_000) > _estimate_carbon_local(100_000)
    assert _extract_domain("https://www.example.com/path") == "www.example.com"


@pytest.mark.asyncio
async def test_scan_uses_its_own_measurement_and_local_fallback() -> None:
    with (
        patch(
            "axes.resource._fetch_page_with_resources",
            new_callable=AsyncMock,
            return_value=(300_000, 2, "<html></html>"),
        ),
        patch("axes.resource._check_green_hosting", new_callable=AsyncMock, return_value=False),
        patch("axes.resource._fetch_carbon_data", new_callable=AsyncMock, return_value=None),
    ):
        result = await scan("https://example.com")
    assert result.score == 10.0
    assert result.coverage == 0.55
    assert result.details["weight_source"] == "HTML principal"
    assert "estimation locale" in result.details["carbon_source"]
    assert result.evidence[0]["bytes"] == 300_000


@pytest.mark.asyncio
async def test_page_failure_does_not_fabricate_resource_score() -> None:
    with (
        patch(
            "axes.resource._fetch_page_with_resources",
            new_callable=AsyncMock,
            side_effect=RuntimeError("timeout cible"),
        ),
        pytest.raises(RuntimeError, match="timeout cible"),
    ):
        await scan("https://example.com")
