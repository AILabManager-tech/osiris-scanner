"""Script de calibration — Scanne plusieurs sites et compare les résultats."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from axes.intrusion import scan as scan_intrusion
from axes.performance import scan as scan_performance
from axes.resource import scan as scan_resource
from axes.security import scan as scan_security
from scoring import compute_osiris_score, get_grade


async def scan_site(url: str) -> dict | None:
    """Scanne un site et retourne les résultats."""
    print(f"\n{'='*60}")
    print(f"Scan: {url}")
    print(f"{'='*60}")

    results = {}

    # Axe O
    try:
        print("  [O] Performance...", end=" ", flush=True)
        results["O"] = await scan_performance(url)
        print(f"{results['O'].score}/10")
    except Exception as e:
        print(f"ERREUR: {e}")
        return None

    # Axe S
    try:
        print("  [S] Security...", end=" ", flush=True)
        results["S"] = await scan_security(url)
        print(f"{results['S'].score}/10")
    except Exception as e:
        print(f"ERREUR: {e}")
        return None

    # Axe I
    try:
        print("  [I] Intrusion...", end=" ", flush=True)
        results["I"] = await scan_intrusion(url)
        print(f"{results['I'].score}/10")
    except Exception as e:
        print(f"ERREUR: {e}")
        return None

    # Axe R
    try:
        print("  [R] Resource...", end=" ", flush=True)
        results["R"] = await scan_resource(url)
        print(f"{results['R'].score}/10")
    except Exception as e:
        print(f"ERREUR: {e}")
        return None

    score = compute_osiris_score(results)
    grade = get_grade(score)
    print(f"  => OSIRIS: {score}/10 ({grade})")

    return {
        "url": url,
        "score": score,
        "grade": grade,
        "axes": {
            k: {"score": r.score, "details": r.details}
            for k, r in results.items()
        },
    }


async def main() -> None:
    sites_file = Path("calibration/sites.txt")
    urls = [
        line.strip()
        for line in sites_file.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    all_results = []
    for url in urls:
        result = await scan_site(url)
        if result:
            all_results.append(result)

    # Sauvegarder
    output = {
        "calibration_date": datetime.now(UTC).isoformat(),
        "sites_scanned": len(all_results),
        "sites_failed": len(urls) - len(all_results),
        "results": all_results,
    }

    out_path = Path("calibration/results.json")
    out_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nRésultats sauvegardés: {out_path}")

    # Tableau récapitulatif
    print(f"\n{'='*70}")
    print(f"{'Site':<35} {'O':>5} {'S':>5} {'I':>5} {'R':>5} {'OSIRIS':>7} {'Grade':<12}")
    print(f"{'-'*70}")
    for r in all_results:
        a = r["axes"]
        print(
            f"{r['url']:<35} "
            f"{a['O']['score']:>5} {a['S']['score']:>5} "
            f"{a['I']['score']:>5} {a['R']['score']:>5} "
            f"{r['score']:>7} {r['grade']:<12}"
        )


if __name__ == "__main__":
    asyncio.run(main())
