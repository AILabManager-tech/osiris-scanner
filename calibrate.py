"""Calibration multi-sites du moteur canonique OSIRIS."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from importlib.resources import files
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


async def main(
    sites_path: str | None = None,
    output_path: str = "osiris-calibration-results.json",
) -> None:
    sites_text = (
        Path(sites_path).read_text(encoding="utf-8")
        if sites_path
        else files("calibration").joinpath("sites.txt").read_text(encoding="utf-8")
    )
    urls = [
        line.strip()
        for line in sites_text.splitlines()
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
    path = Path(output_path)
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Résultats sauvegardés : {path}")


def cli() -> None:
    parser = argparse.ArgumentParser(description="Calibration multi-cibles OSIRIS")
    parser.add_argument("--sites", default=None, help="Fichier d'URL, une par ligne")
    parser.add_argument("--output", default="osiris-calibration-results.json")
    args = parser.parse_args()
    asyncio.run(main(args.sites, args.output))


if __name__ == "__main__":
    cli()
