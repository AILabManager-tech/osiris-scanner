"""Parcours deep déterministe des implémentations canoniques O/S/I/R/V."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from axes import CANONICAL_AXIS_KEYS
from scanner import execute_scan
from url_security import NetworkPolicy


@pytest.mark.asyncio
async def test_controlled_deep_scan_exercises_real_axes(target_server: str) -> None:
    """Le mode deep traverse Chromium réel, avec DNS tiers remappé vers la fixture."""

    from playwright.async_api import async_playwright as real_async_playwright

    class LocalPlaywright:
        def __init__(self) -> None:
            self._context = real_async_playwright()
            self.executable: Path | None = None

        async def __aenter__(self) -> Any:
            playwright = await self._context.__aenter__()
            configured = os.environ.get("OSIRIS_PLAYWRIGHT_EXECUTABLE")
            expected = Path(configured or playwright.chromium.executable_path)
            candidates = (
                [expected]
                if expected.is_file()
                else sorted(expected.parent.parent.parent.glob("chromium-*/chrome-linux64/chrome"))
            )
            if not candidates:
                await self._context.__aexit__(None, None, None)
                pytest.skip("Chromium Playwright absent; définir OSIRIS_PLAYWRIGHT_EXECUTABLE")
            self.executable = candidates[-1]
            launch = playwright.chromium.launch

            async def launch_local(**kwargs: Any) -> Any:
                return await launch(executable_path=str(self.executable), **kwargs)

            playwright.chromium.launch = launch_local  # type: ignore[method-assign]
            return playwright

        async def __aexit__(self, *args: Any) -> bool | None:
            return await cast(Any, self._context).__aexit__(*args)

    policy = NetworkPolicy(
        allow_private=True,
        allowed_ports=None,
        request_timeout=5.0,
        total_timeout=45.0,
    )
    observatory = {"grade": "B", "score": 80, "tests_passed": 8, "tests_failed": 2}
    geo = {"country": "CA", "asn": 64500, "org": "Fixture locale"}
    with (
        patch("playwright.async_api.async_playwright", side_effect=LocalPlaywright),
        patch("axes.security._fetch_observatory", new_callable=AsyncMock, return_value=observatory),
        patch("axes.resource._check_green_hosting", new_callable=AsyncMock, return_value=False),
        patch("axes.resource._fetch_carbon_data", new_callable=AsyncMock, return_value=None),
        patch("axes.sovereignty._get_geo_info", new_callable=AsyncMock, return_value=geo),
        patch("url_security.resolve_public_host", return_value=("127.0.0.1",)),
        patch("axes.sovereignty.resolve_public_host", return_value=("127.0.0.1",)),
    ):
        outcome = await execute_scan(f"{target_server}/deep", mode="deep", network_policy=policy)
        await asyncio.sleep(0.2)

    assert outcome.status == "complete"
    assert tuple(outcome.results) == CANONICAL_AXIS_KEYS
    assert not outcome.errors
    assert outcome.coverage > 0.8
    assert outcome.results["O"].details["mode"] == "deep"
    assert outcome.results["I"].details["mode"] == "deep"
    assert outcome.results["I"].details["trackers_found"] >= 1
    assert outcome.results["R"].details["mode"] == "deep"
    assert outcome.results["V"].details["total_destinations_ip"] >= 1
    assert outcome.results["V"].details["geolocated_destinations"] >= 1
