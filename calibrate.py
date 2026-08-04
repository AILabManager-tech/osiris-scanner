"""Calibration multi-sites du moteur canonique OSIRIS."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scanner import execute_scan


async def scan_site(url: str, *, mode: str = "fast") -> dict[str, Any]:
    outcome = await execute_scan(url, mode=mode)
    return {
        "url": outcome.url,
        "status": outcome.status,
        "score": outcome.score,
        "technical_score": outcome.technical_score,
        "grade": outcome.grade,
        "coverage": outcome.coverage,
        "errors": outcome.errors,
        "axes": {
            key: {
                "score": result.score,
                "coverage": result.coverage,
                "tool": result.tool_used,
            }
            for key, result in outcome.results.items()
        },
    }


async def main() -> None:
    sites_file = Path("calibration/sites.txt")
    urls = [
        line.strip()
        for line in sites_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    results = [await scan_site(url) for url in urls]
    output = {
        "calibration_date": datetime.now(UTC).isoformat(),
        "methodology": "OSIRIS-6A-2026.1",
        "sites_scanned": sum(result["status"] != "failed" for result in results),
        "sites_failed": sum(result["status"] == "failed" for result in results),
        "results": results,
    }
    path = Path("calibration/results.json")
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Résultats sauvegardés : {path}")


if __name__ == "__main__":
    asyncio.run(main())
