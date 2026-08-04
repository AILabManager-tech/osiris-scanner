"""Moteur et CLI OSIRIS Scanner."""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from axes import CANONICAL_AXIS_KEYS, AxisInfo, discover_axes, registry
from axes.performance import AxisResult
from history import ScanHistory
from report import (
    _build_report_data,
    generate_json_report,
    generate_markdown_report,
    generate_pdf_report,
)
from scoring import ScoreSummary, compute_score_summary, get_grade
from url_security import NetworkPolicy, URLSecurityError, validate_target_url, validate_url_syntax
from utils import extract_domain

console = Console()
logger = logging.getLogger("osiris")
ProgressCallback = Callable[[str, str, int], None]

discover_axes()


@dataclass
class AxisRun:
    """Résultat d'exécution d'un axe, succès ou erreur explicite."""

    key: str
    label: str
    result: AxisResult | None
    error: str | None
    elapsed_seconds: float


@dataclass
class ScanOutcome:
    """Résultat complet consommé par le CLI, le web et les rapports."""

    url: str
    mode: str
    status: str
    results: dict[str, AxisResult] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    score: float | None = None
    technical_score: float | None = None
    grade: str = "Non évalué"
    coverage: float = 0.0
    reliability_factor: float = 0.0
    duration_seconds: float = 0.0
    runs: int = 1
    scan_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def is_partial(self) -> bool:
        return self.status == "partial"

    def scan_meta(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "scan_id": self.scan_id,
            "runs": self.runs,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "coverage": self.coverage,
            "reliability_factor": self.reliability_factor,
            "technical_score": self.technical_score,
            "failed_axes": self.errors,
        }


def _get_axes() -> list[AxisInfo]:
    """Retourne les six axes canoniques dans l'ordre public."""

    axes = registry.all()
    keys = tuple(axis.key for axis in axes)
    if set(keys) != set(CANONICAL_AXIS_KEYS):
        missing = sorted(set(CANONICAL_AXIS_KEYS) - set(keys))
        raise RuntimeError(f"Registre d'axes incomplet; axes manquants : {', '.join(missing)}")
    registry.validate()
    return axes


def _validate_url(url: str) -> str:
    """Validation CLI syntaxique; la résolution sécurisée se fait dans le moteur."""

    try:
        return validate_url_syntax(url)
    except URLSecurityError as exc:
        raise click.BadParameter(str(exc)) from exc


def _display_result(axis: AxisInfo, result: AxisResult) -> None:
    console.print(
        f"Axe {axis.key} ({axis.label}) : {result.score}/10 — "
        f"couverture {result.coverage:.0%} — {result.tool_used}"
    )


def _is_deep_tool_error(exc: Exception) -> bool:
    """Reconnaît une indisponibilité Playwright sans masquer une erreur de programmation."""

    return isinstance(exc, RuntimeError) or type(exc).__module__.startswith("playwright.")


def _concise_error(exc: BaseException, limit: int = 300) -> str:
    """Retire les bannières multilignes d'outils tout en conservant la cause utile."""

    first_line = next((line.strip() for line in str(exc).splitlines() if line.strip()), "Erreur")
    return first_line[:limit]


async def _run_single_performance(
    url: str, network_policy: NetworkPolicy | None = None
) -> AxisResult:
    axis = registry.get("O")
    if axis is None:
        raise RuntimeError("Axe Performance (O) absent du registre")
    return await axis.scan_fn(url, network_policy=network_policy)


async def _run_performance_multi(
    url: str,
    runs: int,
    network_policy: NetworkPolicy | None = None,
) -> AxisResult:
    """Répète la mesure rapide et conserve la médiane sans masquer les échecs."""

    results: list[AxisResult] = []
    errors: list[str] = []
    for _index in range(runs):
        try:
            results.append(await _run_single_performance(url, network_policy))
        except (RuntimeError, ValueError) as exc:
            errors.append(str(exc))
    if not results:
        raise RuntimeError(
            f"Toutes les mesures performance ont échoué : {errors[-1] if errors else 'inconnu'}"
        )

    run_scores = [result.score for result in results]
    median_score = round(statistics.median(run_scores), 1)
    selected = min(results, key=lambda result: abs(result.score - median_score))
    selected.score = median_score
    selected.coverage = round(
        selected.coverage * (len(results) / runs),
        2,
    )
    selected.details = {
        **selected.details,
        "runs_requested": runs,
        "runs_succeeded": len(results),
        "runs_failed": len(errors),
        "run_scores": run_scores,
        "aggregate": "median" if runs > 1 else "single",
    }
    if errors:
        selected.limitations.append(f"{len(errors)} mesure(s) performance ont échoué.")
    return selected


async def _invoke_deep_tool(
    scan_context: dict[str, Any],
    operation: Callable[[], Awaitable[AxisResult]],
) -> AxisResult:
    """Borne à un le nombre de navigateurs Playwright actifs pour un scan."""

    semaphore = scan_context.get("browser_semaphore")
    if not isinstance(semaphore, asyncio.Semaphore):
        semaphore = asyncio.Semaphore(1)
        scan_context["browser_semaphore"] = semaphore
    async with semaphore:
        return await operation()


async def _invoke_axis(
    axis: AxisInfo,
    url: str,
    *,
    mode: str,
    runs: int,
    scan_context: dict[str, Any],
    network_policy: NetworkPolicy,
) -> AxisResult:
    """Sélectionne l'implémentation rapide/profonde d'un axe."""

    if axis.key == "O":
        if mode == "deep":
            from axes.performance import scan_deep as performance_scan_deep

            try:
                result = await _invoke_deep_tool(
                    scan_context,
                    lambda: performance_scan_deep(url, network_policy),
                )
            except Exception as exc:
                if not _is_deep_tool_error(exc):
                    raise
                result = await _run_performance_multi(url, runs, network_policy)
                reason = _concise_error(exc)
                result.details["degraded_from"] = reason
                result.limitations.append(
                    f"Mesure approfondie indisponible; repli HTTP sécurisé : {reason}"
                )
            return result
        return await _run_performance_multi(url, runs, network_policy)

    if axis.key == "S":
        return await axis.scan_fn(url, network_policy=network_policy)

    if axis.key == "I":
        if mode == "deep":
            from axes.intrusion import scan_deep as intrusion_scan_deep

            try:
                return await _invoke_deep_tool(
                    scan_context,
                    lambda: intrusion_scan_deep(url, network_policy=network_policy),
                )
            except Exception as exc:
                if not _is_deep_tool_error(exc):
                    raise
                result = await axis.scan_fn(url, network_policy=network_policy)
                reason = _concise_error(exc)
                result.details["degraded_from"] = reason
                result.limitations.append(f"Repli statique après échec Playwright : {reason}")
                return result
        return await axis.scan_fn(url, network_policy=network_policy)

    if axis.key == "R":
        if mode == "deep":
            from axes.resource import scan_deep as resource_scan_deep

            try:
                return await _invoke_deep_tool(
                    scan_context,
                    lambda: resource_scan_deep(url, network_policy),
                )
            except Exception as exc:
                if not _is_deep_tool_error(exc):
                    raise
                result = await axis.scan_fn(
                    url,
                    network_policy=network_policy,
                )
                reason = _concise_error(exc)
                result.details["degraded_from"] = reason
                result.limitations.append(f"Repli HTML après échec Playwright : {reason}")
                return result
        return await axis.scan_fn(
            url,
            network_policy=network_policy,
        )

    if axis.key == "V":
        from axes.sovereignty import scan_static

        if mode == "deep":
            try:
                return await _invoke_deep_tool(
                    scan_context,
                    lambda: axis.scan_fn(url, network_policy=network_policy),
                )
            except Exception as exc:
                if not _is_deep_tool_error(exc):
                    raise
                result = await scan_static(url, network_policy)
                reason = _concise_error(exc)
                result.details["degraded_from"] = reason
                result.limitations.append(f"Repli DNS/HTML après échec Playwright : {reason}")
                return result
        return await scan_static(url, network_policy)

    if axis.key == "L":
        from axes.legal import scan_static

        if mode == "deep":
            try:
                return await _invoke_deep_tool(
                    scan_context,
                    lambda: axis.scan_fn(url, network_policy=network_policy),
                )
            except Exception as exc:
                if not _is_deep_tool_error(exc):
                    raise
                result = await scan_static(url, network_policy)
                reason = _concise_error(exc)
                result.details["degraded_from"] = reason
                result.limitations.append(f"Repli HTML après échec Playwright : {reason}")
                return result
        return await scan_static(url, network_policy)

    raise RuntimeError(f"Axe inconnu : {axis.key}")


async def _execute_axis(
    axis: AxisInfo,
    url: str,
    *,
    mode: str,
    runs: int,
    scan_context: dict[str, Any],
    network_policy: NetworkPolicy,
) -> AxisRun:
    started = time.monotonic()
    try:
        result = await _invoke_axis(
            axis,
            url,
            mode=mode,
            runs=runs,
            scan_context=scan_context,
            network_policy=network_policy,
        )
        degraded = result.details.get("degraded_from")
        error = f"Repli après erreur approfondie : {degraded}" if degraded else None
        return AxisRun(axis.key, axis.label, result, error, time.monotonic() - started)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.debug("Axe %s échoué", axis.key, exc_info=True)
        return AxisRun(
            axis.key,
            axis.label,
            None,
            f"{type(exc).__name__}: {_concise_error(exc)}",
            time.monotonic() - started,
        )


def _emit(
    callback: ProgressCallback | None,
    stage: str,
    message: str,
    progress: int,
) -> None:
    if callback:
        callback(stage, message, progress)


async def execute_scan(
    url: str,
    *,
    mode: str = "fast",
    runs: int = 1,
    network_policy: NetworkPolicy | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ScanOutcome:
    """Exécute le moteur canonique et retourne un résultat sans effet de bord."""

    if mode not in {"fast", "deep"}:
        raise ValueError("Le mode doit être 'fast' ou 'deep'")
    if not 1 <= runs <= 5:
        raise ValueError("runs doit être compris entre 1 et 5")

    policy = network_policy or NetworkPolicy()
    started = time.monotonic()
    _emit(progress_callback, "validation", "Validation sécurisée de la cible", 5)
    try:
        async with asyncio.timeout(min(policy.request_timeout, policy.total_timeout)):
            normalized_url = await asyncio.to_thread(validate_target_url, url, policy)
    except TimeoutError:
        return ScanOutcome(
            url=url,
            mode=mode,
            runs=runs,
            status="failed",
            errors={"target": "Délai de résolution DNS dépassé"},
            duration_seconds=round(time.monotonic() - started, 3),
        )
    except URLSecurityError as exc:
        return ScanOutcome(
            url=url,
            mode=mode,
            runs=runs,
            status="failed",
            errors={"target": str(exc)},
            duration_seconds=round(time.monotonic() - started, 3),
        )

    axes = _get_axes()
    remaining = {axis.key: axis for axis in axes}
    completed: set[str] = set()
    results: dict[str, AxisResult] = {}
    errors: dict[str, str] = {}
    scan_context: dict[str, Any] = {"browser_semaphore": asyncio.Semaphore(1)}

    try:
        remaining_timeout = max(0.001, policy.total_timeout - (time.monotonic() - started))
        async with asyncio.timeout(remaining_timeout):
            while remaining:
                ready = [
                    axis
                    for axis in axes
                    if axis.key in remaining and set(axis.after).issubset(completed)
                ]
                if not ready:
                    raise RuntimeError("Cycle détecté dans les dépendances d'axes")
                progress = 10 + int(75 * len(completed) / len(axes))
                _emit(
                    progress_callback,
                    "axes",
                    " · ".join(f"{axis.key} {axis.label}" for axis in ready),
                    progress,
                )
                tasks = [
                    asyncio.create_task(
                        _execute_axis(
                            axis,
                            normalized_url,
                            mode=mode,
                            runs=runs,
                            scan_context=scan_context,
                            network_policy=policy,
                        ),
                        name=f"osiris-axis-{axis.key}",
                    )
                    for axis in ready
                ]
                try:
                    for completed_task in asyncio.as_completed(tasks):
                        axis_run = await completed_task
                        if axis_run.result is not None:
                            results[axis_run.key] = axis_run.result
                        if axis_run.error:
                            errors[axis_run.key] = axis_run.error
                        completed.add(axis_run.key)
                        remaining.pop(axis_run.key, None)
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
    except TimeoutError:
        for axis_key in remaining:
            errors[axis_key] = "Durée globale maximale dépassée"
    except RuntimeError as exc:
        errors["engine"] = str(exc)

    duration = round(time.monotonic() - started, 3)
    if not results:
        _emit(progress_callback, "failed", "Aucun axe n'a produit de résultat", 100)
        return ScanOutcome(
            url=normalized_url,
            mode=mode,
            runs=runs,
            status="failed",
            errors=errors,
            duration_seconds=duration,
        )

    results = {key: results[key] for key in CANONICAL_AXIS_KEYS if key in results}
    errors = {
        key: errors[key] for key in (*CANONICAL_AXIS_KEYS, "target", "engine") if key in errors
    }
    summary: ScoreSummary = compute_score_summary(results)
    status = "partial" if errors or summary.missing_axes else "complete"
    outcome = ScanOutcome(
        url=normalized_url,
        mode=mode,
        runs=runs,
        status=status,
        results=results,
        errors=errors,
        score=summary.score,
        technical_score=summary.technical_score,
        grade=("Donnée insuffisante" if summary.coverage < 0.7 else get_grade(summary.score)),
        coverage=summary.coverage,
        reliability_factor=summary.reliability_factor,
        duration_seconds=duration,
    )
    _emit(progress_callback, "complete", "Rapport prêt", 100)
    return outcome


def _display_outcome(outcome: ScanOutcome) -> None:
    if outcome.status == "failed":
        console.print("[red]Échec du scan[/red]")
        for key, error in outcome.errors.items():
            console.print(f"  {key}: {error}")
        return

    table = Table(title="Résultats OSIRIS — six axes canoniques")
    table.add_column("Axe", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Couverture", justify="right")
    table.add_column("Source")
    for axis in _get_axes():
        result = outcome.results.get(axis.key)
        if result:
            table.add_row(
                f"{axis.key} — {axis.label}",
                f"{result.score:.1f}/10",
                f"{result.coverage:.0%}",
                result.tool_used,
            )
        else:
            table.add_row(axis.key, "—", "0%", "Erreur technique")
    console.print(table)
    console.print(
        f"\n[bold]Score publié : {outcome.score}/10 — {outcome.grade}[/bold]\n"
        f"Score technique : {outcome.technical_score}/10 · couverture : {outcome.coverage:.0%} "
        f"· facteur de fiabilité : {outcome.reliability_factor:.3f}"
    )
    if outcome.errors:
        console.print("[yellow]Erreurs techniques partielles :[/yellow]")
        for key, error in outcome.errors.items():
            console.print(f"  {key}: {error}")


async def _run_scan(
    url: str,
    output: str | None = None,
    *,
    history: bool = False,
    runs: int = 1,
    mode: str = "fast",
    output_dir: str | None = None,
) -> ScanOutcome:
    """Exécute, affiche, persiste et génère les sorties demandées."""

    outcome = await execute_scan(url, mode=mode, runs=runs)
    _display_outcome(outcome)
    if outcome.status == "failed" or outcome.score is None:
        return outcome

    domain = extract_domain(outcome.url)
    if history:
        scan_history = ScanHistory()
        scan_history.save_scan(
            domain,
            outcome.url,
            outcome.score,
            outcome.grade,
            {key: result.score for key, result in outcome.results.items()},
            mode=mode,
            details=outcome.scan_meta(),
        )
        scan_history.close()

    if output == "report":
        meta = outcome.scan_meta()
        report_data = _build_report_data(
            outcome.url,
            outcome.results,
            outcome.score,
            outcome.grade,
            meta,
        )
        paths = (
            generate_json_report(
                outcome.url,
                outcome.results,
                outcome.score,
                outcome.grade,
                output_dir=output_dir,
                scan_meta=meta,
                report_data=report_data,
            ),
            generate_markdown_report(
                outcome.url,
                outcome.results,
                outcome.score,
                outcome.grade,
                output_dir=output_dir,
                scan_meta=meta,
                report_data=report_data,
            ),
            generate_pdf_report(
                outcome.url,
                outcome.results,
                outcome.score,
                outcome.grade,
                output_dir=output_dir,
                scan_meta=meta,
                report_data=report_data,
            ),
        )
        for path in paths:
            console.print(f"[green]Rapport[/green] : {path}")
    return outcome


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    osiris_logger = logging.getLogger("osiris")
    osiris_logger.setLevel(level)
    if not osiris_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s — %(message)s"))
        osiris_logger.addHandler(handler)


@click.command()
@click.option("--url", required=True, help="URL HTTP(S) publique à scanner")
@click.option("--output", type=click.Choice(["report"]), default=None)
@click.option("--output-dir", type=click.Path(file_okay=False), default=None)
@click.option("--history", is_flag=True, default=False, help="Conserver ce scan localement")
@click.option("--runs", type=click.IntRange(1, 5), default=1)
@click.option("--mode", type=click.Choice(["fast", "deep"]), default="fast")
@click.option("--verbose", is_flag=True, default=False)
def main(
    url: str,
    output: str | None,
    output_dir: str | None,
    history: bool,
    runs: int,
    mode: str,
    verbose: bool,
) -> None:
    """OSIRIS — diagnostic multidimensionnel de sites web."""

    _setup_logging(verbose)
    validated_url = _validate_url(url)
    outcome = asyncio.run(
        _run_scan(
            validated_url,
            output,
            history=history,
            runs=runs,
            mode=mode,
            output_dir=output_dir,
        )
    )
    if outcome.status == "failed":
        raise click.ClickException("Le scan n'a produit aucune donnée exploitable")


if __name__ == "__main__":
    main()
