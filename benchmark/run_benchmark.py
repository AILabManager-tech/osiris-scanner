"""Benchmark reproductible du moteur canonique OSIRIS."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner import execute_scan  # noqa: E402

BENCHMARK_DIR = Path(__file__).resolve().parent
URLS_FILE = BENCHMARK_DIR / "inputs" / "urls.txt"
RAW_DIR = BENCHMARK_DIR / "raw"
SUMMARY_DIR = BENCHMARK_DIR / "summary"


def _load_urls() -> list[str]:
    return [
        line.strip()
        for line in URLS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _load_previous() -> dict[str, Any] | None:
    path = SUMMARY_DIR / "latest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


async def _scan(url: str, mode: str, runs: int) -> dict[str, Any]:
    outcome = await execute_scan(url, mode=mode, runs=runs)
    return {
        "url": outcome.url,
        "status": outcome.status,
        "score": outcome.score,
        "technical_score": outcome.technical_score,
        "grade": outcome.grade,
        "coverage": outcome.coverage,
        "duration_seconds": outcome.duration_seconds,
        "errors": outcome.errors,
        "axes": {
            key: {"score": value.score, "coverage": value.coverage, "tool": value.tool_used}
            for key, value in outcome.results.items()
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="OSIRIS Benchmark")
    parser.add_argument("--mode", choices=["fast", "deep"], default="fast")
    parser.add_argument("--runs", type=int, choices=range(1, 6), default=1)
    args = parser.parse_args()
    urls = _load_urls()
    results = [await _scan(url, args.mode, args.runs) for url in urls]
    previous = _load_previous()
    previous_by_url = {result["url"]: result for result in (previous or {}).get("results", [])}
    for result in results:
        old = previous_by_url.get(result["url"])
        result["delta"] = (
            round(result["score"] - old["score"], 1)
            if old and result["score"] is not None and old.get("score") is not None
            else None
        )

    payload = {
        "benchmark_date": datetime.now(UTC).isoformat(),
        "methodology": "OSIRIS-6A-2026.1",
        "mode": args.mode,
        "runs": args.runs,
        "sites_scanned": sum(result["status"] != "failed" for result in results),
        "sites_failed": sum(result["status"] == "failed" for result in results),
        "results": results,
    }
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"{timestamp}.json"
    raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (SUMMARY_DIR / "latest.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Résultats : {raw_path}")


if __name__ == "__main__":
    asyncio.run(main())
