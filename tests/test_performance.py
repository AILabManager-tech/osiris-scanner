"""Tests des mesures performance protégées."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from axes.performance import AxisResult, _score_response_time, scan
from scanner import _run_performance_multi
from url_security import SafeHTTPResponse


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [(0, 10.0), (500, 10.0), (5000, 0.0), (6000, 0.0)],
)
def test_response_time_score_bounds(elapsed: float, expected: float) -> None:
    assert _score_response_time(elapsed) == expected


@pytest.mark.asyncio
async def test_fast_scan_uses_guarded_fetch() -> None:
    response = SafeHTTPResponse(
        url="https://example.com/",
        status=200,
        headers={"content-type": "text/html"},
        body=b"<html>ok</html>",
    )
    with patch(
        "axes.performance.safe_fetch",
        new_callable=AsyncMock,
        return_value=response,
    ) as fetch:
        result = await scan("https://example.com")
    assert isinstance(result, AxisResult)
    assert result.tool_used == "Protected HTTP Timing"
    assert result.coverage == 0.6
    assert result.evidence[0]["status"] == 200
    fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_http_error_is_scan_failure_not_bad_score() -> None:
    response = SafeHTTPResponse(
        url="https://example.com/", status=503, headers={}, body=b"unavailable"
    )
    with (
        patch("axes.performance.safe_fetch", new_callable=AsyncMock, return_value=response),
        pytest.raises(RuntimeError, match="HTTP 503"),
    ):
        await scan("https://example.com")


@pytest.mark.asyncio
async def test_median_runs_and_partial_failure_affect_coverage() -> None:
    runs: list[AxisResult | Exception] = [
        AxisResult(score=7.0, coverage=0.6, details={}, tool_used="HTTP"),
        RuntimeError("timeout"),
        AxisResult(score=9.0, coverage=0.6, details={}, tool_used="HTTP"),
    ]

    async def fake_scan(_url: str, _policy: object = None) -> AxisResult:
        value = runs.pop(0)
        if isinstance(value, Exception):
            raise value
        assert isinstance(value, AxisResult)
        return value

    with patch("scanner._run_single_performance", side_effect=fake_scan):
        result = await _run_performance_multi("https://example.com", 3)
    assert result.score == 8.0
    assert result.coverage == 0.4
    assert result.details["runs_succeeded"] == 2
    assert result.details["runs_failed"] == 1


@pytest.mark.asyncio
async def test_all_performance_runs_fail_cleanly() -> None:
    with (
        patch(
            "scanner._run_single_performance",
            new_callable=AsyncMock,
            side_effect=RuntimeError("timeout"),
        ),
        pytest.raises(RuntimeError, match="Toutes les mesures"),
    ):
        await _run_performance_multi("https://example.com", 2)
