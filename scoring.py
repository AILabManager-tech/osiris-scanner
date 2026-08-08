"""OSIRIS Scoring — Moteur Géométrique Pondéré (GEARGRINDER).

Formule v5.0 :
    Score = Π (s_i ^ w_i)
    où s_i est le score de l'axe i et w_i son poids (Σ w_i = 1.0).

Cette méthode garantit qu'un échec critique sur un axe pilier
fait s'effondrer le score global, empêchant le "maquillage" par le SEO.

Grades :
    9.0 - 10.0 : Exemplaire
    7.0 -  8.9 : Conforme
    5.0 -  6.9 : À risque
    0.0 -  4.9 : Critique
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from typing import Literal

from axes.performance import AxisResult

logger = logging.getLogger("osiris")

# --- Pondérations v5.0 (Total = 1.0) ---

WEIGHT_PERFORMANCE: float = 0.15
WEIGHT_SECURITY: float = 0.25
WEIGHT_INTRUSION: float = 0.20
WEIGHT_RESOURCE: float = 0.10
WEIGHT_SOVEREIGNTY: float = 0.15
WEIGHT_LEGAL: float = 0.15

_DEFAULT_WEIGHTS: dict[str, float] = {
    "O": WEIGHT_PERFORMANCE,
    "S": WEIGHT_SECURITY,
    "I": WEIGHT_INTRUSION,
    "R": WEIGHT_RESOURCE,
    "V": WEIGHT_SOVEREIGNTY,
    "L": WEIGHT_LEGAL,
}

ScanStatus = Literal["complete", "partial", "failed", "indeterminate"]


def _get_weights() -> dict[str, float]:
    """Retourne un jeu de poids complet et normalisé.

    Un import direct d'un seul module d'axe peuple partiellement le registre.
    Ce registre incomplet ne doit jamais remplacer silencieusement les six poids
    canoniques utilisés par la formule OSIRIS.
    """
    try:
        from axes import discover_axes, registry

        registered = registry.weights()
        complete = set(registered) == set(_DEFAULT_WEIGHTS)
        valid_values = all(math.isfinite(weight) and weight > 0 for weight in registered.values())
        normalized = math.isclose(sum(registered.values()), 1.0, abs_tol=1e-9)
        if not (complete and valid_values and normalized):
            discover_axes()
            registered = registry.weights()
            complete = set(registered) == set(_DEFAULT_WEIGHTS)
            valid_values = all(
                math.isfinite(weight) and weight > 0 for weight in registered.values()
            )
            normalized = math.isclose(sum(registered.values()), 1.0, abs_tol=1e-9)
        if complete and valid_values and normalized:
            return registered
        if registered:
            logger.warning(
                "Registre d'axes incomplet ou incohérent (%s); utilisation des poids canoniques",
                sorted(registered),
            )
    except (ImportError, RuntimeError):
        pass
    return dict(_DEFAULT_WEIGHTS)


def _legal_is_indeterminate(result: AxisResult | None) -> bool:
    """Détecte l'absence de conclusion légale dans les détails structurés."""
    if result is None:
        return False
    details = result.details or {}
    audit = details.get("audit")
    statuses = [details.get("statut"), details.get("status")]
    if isinstance(audit, dict):
        statuses.extend((audit.get("statut"), audit.get("status")))
        if audit.get("conforme") is None and "conforme" in audit:
            return True
    return any(status in {"indetermine", "indeterminate"} for status in statuses)


def get_scan_status(
    results: dict[str, AxisResult],
    expected_axes: Iterable[str] | None = None,
) -> ScanStatus:
    """Retourne le statut global sans modifier le calcul du score."""
    expected = set(expected_axes or _DEFAULT_WEIGHTS)
    present = set(results)
    if not present:
        return "failed"
    if expected - present:
        return "partial"
    if _legal_is_indeterminate(results.get("L")):
        return "indeterminate"
    return "complete"


def get_status_grade(status: ScanStatus, score_grade: str) -> str:
    """Empêche un statut incomplet d'être présenté comme un grade normal."""
    if status == "complete":
        return score_grade
    return {
        "partial": "Partiel",
        "failed": "Échec",
        "indeterminate": "Indéterminé",
    }[status]


# --- Seuils de grade ---

GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (9.0, "Exemplaire"),
    (7.0, "Conforme"),
    (5.0, "À risque"),
    (0.0, "Critique"),
]


def compute_osiris_score(results: dict[str, AxisResult]) -> float:
    """Calcule le score OSIRIS composite via Moyenne Géométrique Pondérée.

    Formule : Score = exp( Σ (w_i * ln(s_i)) )
    Pour éviter ln(0), on utilise un epsilon de 0.1 (score minimal technique).

    Args:
        results: Dictionnaire {axe: AxisResult}.

    Returns:
        Score composite entre 0.0 et 10.0.
    """
    if not results:
        raise ValueError("Aucun axe fourni pour le calcul OSIRIS")

    weights = _get_weights()

    # Vérifier si tous les axes requis sont présents
    missing = set(weights.keys()) - set(results.keys())
    if missing:
        logger.warning("Axes manquants pour le calcul complet : %s", missing)
        return compute_partial_score(results)

    # Calcul géométrique
    weighted_ln_sum = 0.0
    epsilon = 0.1  # Plancher pour éviter ln(0) et permettre l'effondrement contrôlé

    for axis, weight in weights.items():
        score = max(epsilon, results[axis].score)
        ln_val = math.log(score)
        weighted_ln_sum += weight * ln_val
        logger.debug(
            "Axe %s: score=%.1f, poids=%.2f, ln=%.4f, weighted=%.4f",
            axis,
            score,
            weight,
            ln_val,
            weight * ln_val,
        )

    final_score = math.exp(weighted_ln_sum)
    logger.debug("Score final calculé: %.4f (weighted_ln_sum=%.4f)", final_score, weighted_ln_sum)
    return round(final_score, 1)


def compute_partial_score(results: dict[str, AxisResult]) -> float:
    """Calcule un score partiel (Géométrique normalisé)."""
    if not results:
        raise ValueError("Aucun axe fourni pour le calcul OSIRIS partiel")

    weights = _get_weights()

    # Normalisation des poids des axes disponibles
    available_weight_sum = sum(weights[axis] for axis in results if axis in weights)
    if available_weight_sum == 0:
        return 0.0

    weighted_ln_sum = 0.0
    epsilon = 0.1

    for axis, result in results.items():
        if axis in weights:
            normalized_weight = weights[axis] / available_weight_sum
            score = max(epsilon, result.score)
            weighted_ln_sum += normalized_weight * math.log(score)

    normalized_score = math.exp(weighted_ln_sum)

    # Pénalité de fiabilité : seuls les axes reconnus comptent. Un résultat
    # injecté par un registre contaminé ne doit pas augmenter artificiellement
    # la couverture ni le score.
    recognized_axes = sum(axis in weights for axis in results)
    reliability = (recognized_axes / len(weights)) ** 0.5
    return round(normalized_score * reliability, 1)


def get_grade(score: float) -> str:
    """Détermine le grade OSIRIS à partir du score."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "Critique"


def get_formula_description() -> str:
    """Description de la formule géométrique."""
    return "Score = Π (Axe_i ^ Poids_i) — Moyenne Géométrique Pondérée"
