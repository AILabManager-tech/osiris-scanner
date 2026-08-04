"""Tests de l'orchestrateur, scans partiels et cibles contrôlées."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from axes import CANONICAL_AXIS_KEYS, AxisInfo
from axes.performance import AxisResult
from scanner import _execute_axis, _invoke_deep_tool, _run_performance_multi, execute_scan
from url_security import NetworkPolicy


def _axes_with_resource_dependency() -> list[AxisInfo]:
    async def unused(_url: str) -> AxisResult:
        return AxisResult(score=8.0)

    return [
        AxisInfo(
            key=key,
            label=key,
            weight=weight,
            scan_fn=unused,
            order=index * 10,
            after=("O",) if key == "R" else (),
        )
        for index, (key, weight) in enumerate(
            zip(CANONICAL_AXIS_KEYS, (0.15, 0.25, 0.20, 0.10, 0.15, 0.15), strict=True),
            start=1,
        )
    ]


@pytest.mark.asyncio
async def test_declared_dependency_waits_while_independent_axes_run_in_parallel() -> None:
    timeline: dict[str, float] = {}

    async def fake_invoke(axis: AxisInfo, *_args: object, **_kwargs: object) -> AxisResult:
        timeline[f"{axis.key}_start"] = time.monotonic()
        await asyncio.sleep(0.06 if axis.key == "O" else 0.005)
        timeline[f"{axis.key}_end"] = time.monotonic()
        return AxisResult(score=8.0, coverage=1.0, tool_used="fixture")

    with (
        patch("scanner.validate_target_url", return_value="https://example.com/"),
        patch("scanner._get_axes", return_value=_axes_with_resource_dependency()),
        patch("scanner._invoke_axis", side_effect=fake_invoke),
    ):
        outcome = await execute_scan("https://example.com")

    assert outcome.status == "complete"
    assert timeline["S_start"] < timeline["O_end"]
    assert timeline["R_start"] >= timeline["O_end"]


@pytest.mark.asyncio
async def test_axis_failure_produces_partial_scan_and_no_fabricated_result() -> None:
    async def fake_invoke(axis: AxisInfo, *_args: object, **_kwargs: object) -> AxisResult:
        if axis.key == "V":
            raise RuntimeError("géolocalisation indisponible")
        return AxisResult(score=7.0, coverage=1.0, tool_used="fixture")

    with (
        patch("scanner.validate_target_url", return_value="https://example.com/"),
        patch("scanner._get_axes", return_value=_axes_with_resource_dependency()),
        patch("scanner._invoke_axis", side_effect=fake_invoke),
    ):
        outcome = await execute_scan("https://example.com")

    assert outcome.status == "partial"
    assert "V" not in outcome.results
    assert "géolocalisation indisponible" in outcome.errors["V"]
    assert outcome.score is not None
    assert outcome.coverage < 1.0


@pytest.mark.asyncio
async def test_deep_fallback_is_preserved_as_partial_degradation() -> None:
    from playwright.async_api import Error as PlaywrightError

    performance = _axes_with_resource_dependency()[0]
    fallback = AxisResult(score=7.5, coverage=0.6, details={}, tool_used="HTTP")
    with (
        patch(
            "axes.performance.scan_deep",
            new_callable=AsyncMock,
            side_effect=PlaywrightError("absent"),
        ),
        patch("scanner._run_performance_multi", new_callable=AsyncMock, return_value=fallback),
    ):
        run = await _execute_axis(
            performance,
            "https://example.com/",
            mode="deep",
            runs=1,
            scan_context={},
            network_policy=NetworkPolicy(),
        )
    assert run.result is fallback
    assert run.error is not None
    assert fallback.details["degraded_from"] == "absent"
    assert "repli HTTP" in fallback.limitations[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    ["not-a-url", "file:///etc/passwd", "http://127.0.0.1/", "http://nonexistent.invalid/"],
)
async def test_invalid_inaccessible_and_private_targets_fail_before_axes(url: str) -> None:
    outcome = await execute_scan(
        url,
        network_policy=NetworkPolicy(request_timeout=0.5, total_timeout=1.0),
    )
    assert outcome.status == "failed"
    assert outcome.results == {}
    assert "target" in outcome.errors


@pytest.mark.asyncio
async def test_controlled_fast_scan_runs_all_six_axes(target_server: str) -> None:
    policy = NetworkPolicy(
        allow_private=True,
        allowed_ports=None,
        request_timeout=2.0,
        total_timeout=8.0,
    )
    geo = {"country": "CA", "asn": 64500, "org": "Fixture locale"}
    observatory = {"grade": "B", "score": 80, "tests_passed": 8, "tests_failed": 2}
    with (
        patch("axes.security._fetch_observatory", new_callable=AsyncMock, return_value=observatory),
        patch("axes.resource._check_green_hosting", new_callable=AsyncMock, return_value=False),
        patch("axes.resource._fetch_carbon_data", new_callable=AsyncMock, return_value=None),
        patch("axes.sovereignty._get_geo_info", new_callable=AsyncMock, return_value=geo),
        patch("axes.sovereignty.resolve_public_host", return_value=("127.0.0.1",)),
    ):
        outcome = await execute_scan(f"{target_server}/weak", network_policy=policy)

    assert outcome.status == "complete"
    assert tuple(outcome.results) == CANONICAL_AXIS_KEYS
    assert outcome.score is not None
    assert 0.0 <= outcome.score <= 10.0
    assert outcome.results["I"].details["trackers_found"] >= 1
    assert outcome.results["S"].details["headers_missing"]
    assert outcome.results["L"].details["privacy_links"]


@pytest.mark.asyncio
async def test_controlled_redirect_is_retained_as_evidence(target_server: str) -> None:
    policy = NetworkPolicy(allow_private=True, allowed_ports=None)
    from axes.performance import scan

    result = await scan(f"{target_server}/redirect", policy)
    assert result.evidence[0]["redirects"] == [f"{target_server}/simple"]


@pytest.mark.asyncio
async def test_global_timeout_preserves_axes_that_already_completed() -> None:
    axes = _axes_with_resource_dependency()
    for axis in axes:
        axis.after = ()

    async def fake_invoke(axis: AxisInfo, *_args: object, **_kwargs: object) -> AxisResult:
        await asyncio.sleep(1 if axis.key == "O" else 0.005)
        return AxisResult(score=8.0, coverage=1.0, tool_used="fixture")

    policy = NetworkPolicy(request_timeout=1.0, total_timeout=0.05)
    with (
        patch("scanner.validate_target_url", return_value="https://example.com/"),
        patch("scanner._get_axes", return_value=axes),
        patch("scanner._invoke_axis", side_effect=fake_invoke),
    ):
        outcome = await execute_scan("https://example.com", network_policy=policy)

    assert outcome.status == "partial"
    assert set(outcome.results) == {"S", "I", "R", "V", "L"}
    assert outcome.errors == {"O": "Durée globale maximale dépassée"}
    assert outcome.score is not None


@pytest.mark.asyncio
async def test_performance_median_preserves_raw_run_scores() -> None:
    measurements = [
        AxisResult(score=6.0, coverage=1.0, details={}),
        AxisResult(score=8.0, coverage=1.0, details={}),
    ]
    with patch(
        "scanner._run_single_performance",
        new_callable=AsyncMock,
        side_effect=measurements,
    ):
        result = await _run_performance_multi("https://example.com", 2)
    assert result.score == 7.0
    assert result.details["run_scores"] == [6.0, 8.0]


@pytest.mark.asyncio
async def test_deep_browser_operations_are_serialized_per_scan() -> None:
    context: dict[str, object] = {"browser_semaphore": asyncio.Semaphore(1)}
    active = 0
    peak = 0

    async def operation() -> AxisResult:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return AxisResult(score=8.0)

    await asyncio.gather(*(_invoke_deep_tool(context, operation) for _ in range(5)))
    assert peak == 1


@pytest.mark.asyncio
async def test_low_coverage_is_labeled_as_insufficient_data() -> None:
    async def fake_invoke(axis: AxisInfo, *_args: object, **_kwargs: object) -> AxisResult:
        if axis.key != "S":
            raise RuntimeError("outil indisponible")
        return AxisResult(score=8.0, coverage=1.0, tool_used="fixture")

    with (
        patch("scanner.validate_target_url", return_value="https://example.com/"),
        patch("scanner._get_axes", return_value=_axes_with_resource_dependency()),
        patch("scanner._invoke_axis", side_effect=fake_invoke),
    ):
        outcome = await execute_scan("https://example.com")
    assert outcome.coverage == 0.25
    assert outcome.grade == "Donnée insuffisante"
