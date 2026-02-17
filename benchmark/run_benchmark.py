"""OSIRIS Benchmark — Compare les scores OSIRIS entre runs successifs.

Usage :
    python benchmark/run_benchmark.py                   # fast mode, 1 run
    python benchmark/run_benchmark.py --mode deep       # deep mode
    python benchmark/run_benchmark.py --runs 3          # 3 runs Lighthouse (median)

Lit benchmark/inputs/urls.txt et produit :
    benchmark/raw/<timestamp>.json          — resultats bruts
    benchmark/summary/latest.json           — resume avec delta vs run precedent
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Remonter d'un niveau pour importer les modules OSIRIS
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from axes.intrusion import scan as scan_intrusion
from axes.performance import AxisResult
from axes.performance import scan as scan_performance
from axes.resource import scan as scan_resource
from axes.security import scan as scan_security
from scoring import compute_osiris_score, get_grade

BENCHMARK_DIR = Path(__file__).resolve().parent
URLS_FILE = BENCHMARK_DIR / "inputs" / "urls.txt"
RAW_DIR = BENCHMARK_DIR / "raw"
SUMMARY_DIR = BENCHMARK_DIR / "summary"


def _load_urls() -> list[str]:
    """Charge les URLs depuis le fichier d'entree."""
    if not URLS_FILE.exists():
        print(f"ERREUR : {URLS_FILE} introuvable")
        sys.exit(1)
    return [
        line.strip()
        for line in URLS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _load_previous_run() -> dict | None:
    """Charge le dernier run depuis summary/latest.json."""
    latest = SUMMARY_DIR / "latest.json"
    if latest.exists():
        return json.loads(latest.read_text(encoding="utf-8"))
    return None


async def _scan_site(
    url: str, *, mode: str = "fast", runs: int = 1,
) -> dict | None:
    """Scanne un site et retourne les resultats."""
    print(f"\n  Scan: {url}")
    results: dict[str, AxisResult] = {}
    axes = [
        ("O", "Performance", scan_performance),
        ("S", "Security", scan_security),
        ("I", "Intrusion", scan_intrusion),
        ("R", "Resource", scan_resource),
    ]

    for key, label, scan_fn in axes:
        try:
            print(f"    [{key}] {label}...", end=" ", flush=True)
            if key == "I" and mode == "deep":
                from axes.intrusion import scan_deep as scan_i_deep
                results[key] = await scan_i_deep(url)
            elif key == "R" and mode == "deep":
                from axes.resource import scan_deep as scan_r_deep
                results[key] = await scan_r_deep(url)
            else:
                results[key] = await scan_fn(url)
            print(f"{results[key].score}/10")
        except Exception as e:
            print(f"ERREUR: {e}")

    if len(results) < 4:
        print(f"    => INCOMPLET ({len(results)}/4 axes)")
        if not results:
            return None

    try:
        score = compute_osiris_score(results)
    except ValueError:
        # Partial score
        score = round(sum(r.score for r in results.values()) / len(results), 1)

    grade = get_grade(score)
    print(f"    => OSIRIS: {score}/10 ({grade})")

    return {
        "url": url,
        "score": score,
        "grade": grade,
        "axes": {
            k: {"score": r.score, "tool": r.tool_used}
            for k, r in results.items()
        },
    }


def _compute_deltas(
    current: list[dict], previous: list[dict] | None,
) -> list[dict]:
    """Ajoute le delta vs run precedent pour chaque site."""
    if not previous:
        return current

    prev_map = {r["url"]: r for r in previous}
    for site in current:
        prev = prev_map.get(site["url"])
        if prev:
            site["delta"] = round(site["score"] - prev["score"], 1)
        else:
            site["delta"] = None
    return current


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="OSIRIS Benchmark")
    parser.add_argument("--mode", choices=["fast", "deep"], default="fast")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    urls = _load_urls()
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")

    print(f"OSIRIS Benchmark — {len(urls)} sites, mode={args.mode}, runs={args.runs}")
    print("=" * 60)

    site_results = []
    for url in urls:
        result = await _scan_site(url, mode=args.mode, runs=args.runs)
        if result:
            site_results.append(result)

    # Load previous for delta
    previous = _load_previous_run()
    prev_results = previous.get("results", []) if previous else None
    site_results = _compute_deltas(site_results, prev_results)

    # Build raw output
    raw_data = {
        "benchmark_date": datetime.now(UTC).isoformat(),
        "mode": args.mode,
        "runs": args.runs,
        "sites_scanned": len(site_results),
        "sites_failed": len(urls) - len(site_results),
        "results": site_results,
    }

    # Save raw
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"{timestamp}.json"
    raw_path.write_text(
        json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    # Save summary (latest)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = SUMMARY_DIR / "latest.json"
    summary_path.write_text(
        json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    # Print table
    print(f"\n{'=' * 75}")
    print(
        f"{'Site':<30} {'O':>4} {'S':>4} {'I':>4} {'R':>4}"
        f" {'OSIRIS':>6} {'Delta':>6} {'Grade':<12}"
    )
    print(f"{'-' * 75}")
    for r in site_results:
        a = r["axes"]
        delta_str = ""
        if r.get("delta") is not None:
            d = r["delta"]
            delta_str = f"{'+' if d >= 0 else ''}{d}"

        print(
            f"{r['url']:<30} "
            f"{a.get('O', {}).get('score', '-'):>4} "
            f"{a.get('S', {}).get('score', '-'):>4} "
            f"{a.get('I', {}).get('score', '-'):>4} "
            f"{a.get('R', {}).get('score', '-'):>4} "
            f"{r['score']:>6} "
            f"{delta_str:>6} "
            f"{r['grade']:<12}"
        )

    print(f"\nResultats : {raw_path}")
    print(f"Resume    : {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
