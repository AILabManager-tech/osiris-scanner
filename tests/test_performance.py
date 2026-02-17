"""Tests unitaires pour axes/performance.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axes.performance import (
    AxisResult,
    _normalize_score,
    _parse_lighthouse_json,
    scan,
)
from scanner import _run_performance_multi

# --- Tests _normalize_score ---


class TestNormalizeScore:
    def test_score_100_gives_10(self) -> None:
        assert _normalize_score(100.0) == 10.0

    def test_score_0_gives_0(self) -> None:
        assert _normalize_score(0.0) == 0.0

    def test_score_50_gives_5(self) -> None:
        assert _normalize_score(50.0) == 5.0

    def test_score_above_100_clamped(self) -> None:
        assert _normalize_score(150.0) == 10.0

    def test_score_below_0_clamped(self) -> None:
        assert _normalize_score(-10.0) == 0.0

    def test_score_73_gives_7_3(self) -> None:
        assert _normalize_score(73.0) == 7.3


# --- Tests _parse_lighthouse_json ---


def _make_lighthouse_json(score: float, tmp_path: Path) -> Path:
    """Crée un fichier JSON Lighthouse simulé."""
    data = {
        "categories": {
            "performance": {
                "score": score,
            }
        },
        "audits": {
            "first-contentful-paint": {
                "displayValue": "1.2 s",
                "score": 0.85,
            },
            "largest-contentful-paint": {
                "displayValue": "2.1 s",
                "score": 0.70,
            },
        },
    }
    json_path = tmp_path / "report.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return json_path


class TestParseLighthouseJson:
    def test_valid_report(self, tmp_path: Path) -> None:
        json_path = _make_lighthouse_json(0.85, tmp_path)
        score, details = _parse_lighthouse_json(json_path)
        assert score == 85.0
        assert "first-contentful-paint" in details

    def test_perfect_score(self, tmp_path: Path) -> None:
        json_path = _make_lighthouse_json(1.0, tmp_path)
        score, _ = _parse_lighthouse_json(json_path)
        assert score == 100.0

    def test_zero_score(self, tmp_path: Path) -> None:
        json_path = _make_lighthouse_json(0.0, tmp_path)
        score, _ = _parse_lighthouse_json(json_path)
        assert score == 0.0

    def test_missing_performance_category(self, tmp_path: Path) -> None:
        data = {"categories": {}}
        json_path = tmp_path / "report.json"
        json_path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="performance"):
            _parse_lighthouse_json(json_path)

    def test_missing_score(self, tmp_path: Path) -> None:
        data = {"categories": {"performance": {}}}
        json_path = tmp_path / "report.json"
        json_path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="Score"):
            _parse_lighthouse_json(json_path)


# --- Tests scan() ---


class TestScan:
    @pytest.mark.asyncio
    async def test_scan_success(self, tmp_path: Path) -> None:
        """Test scan avec un mock de subprocess Lighthouse."""
        lighthouse_json = {
            "categories": {
                "performance": {"score": 0.92}
            },
            "audits": {
                "first-contentful-paint": {
                    "displayValue": "0.8 s",
                    "score": 0.95,
                },
            },
        }

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0
        mock_process.kill = MagicMock()

        with (
            patch("axes.performance._find_lighthouse", return_value="/usr/bin/lighthouse"),
            patch("axes.performance.asyncio.create_subprocess_exec", return_value=mock_process),
            patch("axes.performance.tempfile.TemporaryDirectory") as mock_tmpdir,
        ):
            mock_tmpdir.return_value.__enter__ = MagicMock(return_value=str(tmp_path))
            mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

            # Écrire le faux rapport JSON
            report_path = tmp_path / "report.json"
            report_path.write_text(json.dumps(lighthouse_json), encoding="utf-8")

            result = await scan("https://example.com")

        assert isinstance(result, AxisResult)
        assert result.score == 9.2
        assert result.tool_used == "Lighthouse"
        assert result.details["lighthouse_score"] == 92.0

    @pytest.mark.asyncio
    async def test_scan_lighthouse_not_found(self) -> None:
        """Test scan quand Lighthouse n'est pas installé."""
        with (
            patch("axes.performance._find_lighthouse", side_effect=FileNotFoundError("not found")),
            pytest.raises(FileNotFoundError),
        ):
            await scan("https://example.com")

    @pytest.mark.asyncio
    async def test_scan_lighthouse_failure(self, tmp_path: Path) -> None:
        """Test scan quand Lighthouse retourne une erreur."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error occurred"))
        mock_process.returncode = 1
        mock_process.kill = MagicMock()

        with (
            patch("axes.performance._find_lighthouse", return_value="/usr/bin/lighthouse"),
            patch("axes.performance.asyncio.create_subprocess_exec", return_value=mock_process),
            patch("axes.performance.tempfile.TemporaryDirectory") as mock_tmpdir,
        ):
            mock_tmpdir.return_value.__enter__ = MagicMock(return_value=str(tmp_path))
            mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(RuntimeError, match="échoué"):
                await scan("https://example.com")

    @pytest.mark.asyncio
    async def test_scan_timeout_clean_exit(self) -> None:
        """Test that timeout kills process cleanly without RuntimeError at exit."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            side_effect=TimeoutError("timeout")
        )
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with (
            patch("axes.performance._find_lighthouse", return_value="/usr/bin/lighthouse"),
            patch("axes.performance.asyncio.create_subprocess_exec", return_value=mock_process),
            patch("axes.performance.tempfile.TemporaryDirectory") as mock_tmpdir,
        ):
            mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/lh")
            mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(RuntimeError, match="timeout"):
                await scan("https://slow-site.example.com")

            # Process must have been killed and waited
            mock_process.kill.assert_called_once()
            mock_process.wait.assert_awaited_once()


class TestMultiRun:
    """Tests for median multi-run strategy."""

    @pytest.mark.asyncio
    async def test_median_of_3_runs(self) -> None:
        """Median of 3 runs returns middle value."""
        results = [
            AxisResult(score=7.0, details={"lighthouse_score": 70.0}, tool_used="Lighthouse"),
            AxisResult(score=9.0, details={"lighthouse_score": 90.0}, tool_used="Lighthouse"),
            AxisResult(score=8.0, details={"lighthouse_score": 80.0}, tool_used="Lighthouse"),
        ]
        call_count = 0

        async def mock_scan(url: str) -> AxisResult:
            nonlocal call_count
            r = results[call_count]
            call_count += 1
            return r

        with patch("scanner.scan_performance", side_effect=mock_scan):
            result = await _run_performance_multi("https://example.com", runs=3)

        assert result.score == 8.0
        assert result.details["aggregate"] == "median"
        assert result.details["runs_succeeded"] == 3
        assert len(result.details["runs"]) == 3

    @pytest.mark.asyncio
    async def test_partial_timeout_uses_remaining(self) -> None:
        """If 1 of 3 runs times out, uses median of remaining 2."""
        good = AxisResult(
            score=8.0, details={"lighthouse_score": 80.0}, tool_used="Lighthouse",
        )
        call_count = 0

        async def mock_scan(url: str) -> AxisResult:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("timeout")
            return good

        with patch("scanner.scan_performance", side_effect=mock_scan):
            result = await _run_performance_multi("https://example.com", runs=3)

        assert result.score == 8.0
        assert result.details["runs_succeeded"] == 2
        assert result.details["runs_failed"] == 1

    @pytest.mark.asyncio
    async def test_all_timeout_raises(self) -> None:
        """If all runs fail, raises RuntimeError."""

        async def mock_scan(url: str) -> AxisResult:
            raise RuntimeError("timeout")

        with (
            patch("scanner.scan_performance", side_effect=mock_scan),
            pytest.raises(RuntimeError, match="Tous les"),
        ):
            await _run_performance_multi("https://example.com", runs=3)
