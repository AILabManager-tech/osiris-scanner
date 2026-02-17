"""OSIRIS Scanner — Orchestrateur principal.

Score composite (0-10) mesurant la santé opérationnelle d'un site web.
4 axes : Performance (O) + Sécurité (S) + Intrusion (I) + Ressources (R).
"""

from __future__ import annotations

import asyncio
import re
import statistics

import click
from rich.console import Console
from rich.table import Table

from axes.intrusion import scan as scan_intrusion
from axes.performance import AxisResult
from axes.performance import scan as scan_performance
from axes.resource import scan as scan_resource
from axes.security import scan as scan_security
from report import generate_json_report, generate_markdown_report
from scoring import compute_osiris_score, get_grade

console = Console()

URL_PATTERN = re.compile(
    r"^https?://"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,}"
    r"(?::\d{1,5})?"
    r"(?:/[^\s]*)?$"
)

# Axes definition: (key, label, scan_function, weight_display, exception_types)
AXES = [
    ("O", "Performance", scan_performance, "20%", (FileNotFoundError, RuntimeError, ValueError)),
    ("S", "Security", scan_security, "30%", (RuntimeError,)),
    ("I", "Intrusion", scan_intrusion, "30%", (FileNotFoundError, RuntimeError)),
    ("R", "Resource", scan_resource, "20%", (RuntimeError,)),
]

SCAN_LABELS = {
    "O": "Scan Performance (Lighthouse)...",
    "S": "Scan Security (Observatory + Headers)...",
    "I": "Scan Intrusion (Blocklist Analysis)...",
    "R": "Scan Resource (Page Weight + Carbon)...",
}


def _validate_url(url: str) -> str:
    """Valide et normalise une URL.

    Args:
        url: URL à valider.

    Returns:
        URL validée.

    Raises:
        click.BadParameter: Si l'URL est invalide.
    """
    if not URL_PATTERN.match(url):
        raise click.BadParameter(f"URL invalide : {url}")
    return url


def _display_result(axis_name: str, axis_label: str, result: AxisResult) -> None:
    """Affiche le résultat d'un axe dans le terminal."""
    console.print(
        f"Axe {axis_name} ({axis_label}) : {result.score}/10 — Source: {result.tool_used}"
    )


async def _run_single_performance(url: str) -> AxisResult:
    """Run a single Lighthouse scan, returning result or raising."""
    return await scan_performance(url)


async def _run_performance_multi(url: str, runs: int) -> AxisResult:
    """Run Lighthouse N times and return median result.

    Tolerates individual timeouts. If all runs fail, raises RuntimeError.
    """
    results: list[AxisResult] = []
    errors: list[str] = []

    for i in range(runs):
        if runs > 1:
            console.print(f"  [dim]Run {i + 1}/{runs}...[/dim]")
        try:
            result = await _run_single_performance(url)
            results.append(result)
        except (FileNotFoundError, RuntimeError, ValueError) as e:
            errors.append(str(e))
            if runs > 1:
                console.print(f"  [yellow]Run {i + 1} échoué : {e}[/yellow]")

    if not results:
        raise RuntimeError(
            f"Tous les {runs} runs Lighthouse ont échoué. Dernière erreur : {errors[-1]}"
        )

    # Median score
    scores = [r.score for r in results]
    median_score = round(statistics.median(scores), 1)

    # Pick the result closest to median for details
    best = min(results, key=lambda r: abs(r.score - median_score))

    # Build runs detail for JSON report
    runs_detail = [
        {"run": i + 1, "score": r.score, "lighthouse_score": r.details.get("lighthouse_score")}
        for i, r in enumerate(results)
    ]

    details = {
        **best.details,
        "runs": runs_detail,
        "runs_requested": runs,
        "runs_succeeded": len(results),
        "runs_failed": len(errors),
        "aggregate": "median" if runs > 1 else "single",
    }

    return AxisResult(
        score=median_score,
        details=details,
        tool_used=f"Lighthouse (median of {len(results)})" if runs > 1 else "Lighthouse",
        raw_output=best.raw_output,
    )


async def _scan_axis(
    url: str,
    axis_key: str,
    axis_label: str,
    scan_fn: object,
    exc_types: tuple[type[Exception], ...],
    *,
    runs: int = 1,
    mode: str = "fast",
) -> AxisResult | None:
    """Scan a single axis, returning None on failure instead of crashing."""
    console.print(f"[dim]{SCAN_LABELS.get(axis_key, f'Scan {axis_label}...')}[/dim]")
    try:
        if axis_key == "O":
            result = await _run_performance_multi(url, runs)
        elif axis_key == "I" and mode == "deep":
            from axes.intrusion import scan_deep as scan_intrusion_deep
            result = await scan_intrusion_deep(url)
        elif axis_key == "R" and mode == "deep":
            from axes.resource import scan_deep as scan_resource_deep
            result = await scan_resource_deep(url)
        else:
            result = await scan_fn(url)
        _display_result(axis_key, axis_label, result)
        return result
    except exc_types as e:
        console.print(f"[red]ERREUR {axis_label}[/red] : {e}")
        return None


async def _run_scan(
    url: str,
    output: str | None = None,
    *,
    history: bool = False,
    runs: int = 1,
    mode: str = "fast",
) -> None:
    """Exécute le scan OSIRIS sur une URL."""
    console.print(f"\n[bold]OSIRIS Scanner[/bold] — Analyse de {url}")
    if mode == "deep":
        console.print("[bold cyan]Mode : deep (Playwright)[/bold cyan]")
    console.print()

    results: dict[str, AxisResult] = {}
    failed_axes: list[str] = []

    for axis_key, axis_label, scan_fn, _weight, exc_types in AXES:
        result = await _scan_axis(
            url, axis_key, axis_label, scan_fn, exc_types, runs=runs, mode=mode,
        )
        if result is not None:
            results[axis_key] = result
        else:
            failed_axes.append(axis_key)

    # Need all 4 axes for scoring
    if failed_axes:
        console.print(
            f"\n[yellow]Axes en échec : {', '.join(failed_axes)}[/yellow]"
        )
        if len(results) < 4:
            # Compute partial score with available axes
            if results:
                partial = sum(r.score for r in results.values()) / len(results)
                partial = round(partial, 1)
                grade = get_grade(partial)
                console.print(
                    f"\n[bold]Score OSIRIS partiel : {partial}/10 ({grade})[/bold]"
                    f" — basé sur {len(results)}/4 axes\n"
                )
            else:
                console.print("\n[red]Aucun axe n'a réussi. Scan avorté.[/red]\n")
            return

    osiris_score = compute_osiris_score(results)
    grade = get_grade(osiris_score)

    # Summary table
    console.print()
    table = Table(title="Résultats OSIRIS")
    table.add_column("Axe", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Poids", justify="right")
    table.add_column("Source")
    for axis_key, axis_label, _fn, weight, _exc in AXES:
        if axis_key in results:
            r = results[axis_key]
            table.add_row(f"{axis_key} — {axis_label}", f"{r.score}/10", weight, r.tool_used)
    console.print(table)

    console.print(f"\n[bold]Score OSIRIS : {osiris_score}/10 ({grade})[/bold]\n")

    # SOIC persistence
    try:
        from soic_v3.osiris_adapter import save_osiris_scan
        from soic_v3.persistence import RunStore

        store = RunStore()
        save_osiris_scan(url, results, osiris_score, grade, store)

        delta = store.get_delta(url)
        if delta:
            delta_sign = "+" if delta.delta >= 0 else ""
            delta_color = "green" if delta.delta >= 0 else "red"
            console.print(
                f"[{delta_color}]Delta vs précédent : "
                f"{delta_sign}{delta.delta}/10[/{delta_color}]"
            )
            if delta.improved_axes:
                console.print(f"  Améliorés : {', '.join(delta.improved_axes)}")
            if delta.regressed_axes:
                console.print(f"  Régressés : {', '.join(delta.regressed_axes)}")
    except ImportError:
        pass

    # Reports
    if output == "report":
        scan_meta = {
            "mode": mode,
            "runs": runs,
            "timeouts": len(failed_axes),
        }
        json_path = generate_json_report(
            url, results, osiris_score, grade, scan_meta=scan_meta,
        )
        md_path = generate_markdown_report(
            url, results, osiris_score, grade, scan_meta=scan_meta,
        )
        console.print(f"[green]Rapport JSON[/green] : {json_path}")
        console.print(f"[green]Rapport Markdown[/green] : {md_path}")

    # History
    if history:
        try:
            from soic_v3.osiris_adapter import get_osiris_history
            from soic_v3.persistence import RunStore

            store = RunStore()
            hist = get_osiris_history(url, store, limit=10)
            if hist:
                console.print("\n[bold]Historique des scans[/bold]")
                hist_table = Table(show_header=True)
                hist_table.add_column("Score", justify="right")
                hist_table.add_column("Grade")
                hist_table.add_column("Date")
                for entry in hist:
                    hist_table.add_row(
                        f"{entry.get('osiris_score', 0):.1f}/10",
                        entry.get("grade", "?"),
                        entry.get("timestamp", "?")[:19],
                    )
                console.print(hist_table)
        except ImportError:
            pass


@click.command()
@click.option("--url", required=True, help="URL du site à scanner")
@click.option("--output", type=click.Choice(["report"]), default=None, help="Générer un rapport")
@click.option("--history", is_flag=True, default=False, help="Afficher l'historique du site")
@click.option("--runs", type=int, default=1, help="Nombre de runs Lighthouse (médiane)")
@click.option(
    "--mode",
    type=click.Choice(["fast", "deep"]),
    default="fast",
    help="Mode de scan (fast=HTML, deep=Playwright)",
)
def main(url: str, output: str | None, history: bool, runs: int, mode: str) -> None:
    """OSIRIS — Score composite de santé opérationnelle d'un site web."""
    validated_url = _validate_url(url)
    asyncio.run(_run_scan(validated_url, output, history=history, runs=runs, mode=mode))


if __name__ == "__main__":
    main()
