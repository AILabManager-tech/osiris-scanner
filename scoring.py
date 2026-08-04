"""Scoring canonique OSIRIS à six axes.

Le score technique est une moyenne arithmétique pondérée. Une couverture
incomplète ne devient jamais un bon résultat par défaut : un facteur de
fiabilité explicite réduit le score publié d'au plus 25 %.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from axes.performance import AxisResult

logger = logging.getLogger("osiris")

METHODOLOGY_VERSION = "OSIRIS-6A-2026.1"

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


@dataclass(frozen=True)
class ScoreSummary:
    """Décomposition transparente du score publié."""

    score: float
    technical_score: float
    coverage: float
    reliability: float
    reliability_factor: float
    missing_axes: tuple[str, ...]


def _get_weights() -> dict[str, float]:
    """Retourne les poids du registre seulement s'il est canonique et complet."""

    try:
        from axes import CANONICAL_AXIS_KEYS, registry

        if set(registry.keys()) == set(CANONICAL_AXIS_KEYS):
            weights = registry.weights()
            if abs(sum(weights.values()) - 1.0) <= 1e-9:
                return weights
    except (ImportError, RuntimeError):
        pass
    return dict(_DEFAULT_WEIGHTS)


GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (8.5, "Bon"),
    (6.5, "À surveiller"),
    (0.0, "Risque élevé"),
]


def compute_score_summary(results: dict[str, AxisResult]) -> ScoreSummary:
    """Calcule score technique, couverture et pénalité de fiabilité.

    La couverture est la somme des poids effectivement observés, modulée par
    ``AxisResult.coverage``. Le facteur publié est ``0.75 + 0.25 × couverture``.
    Il vaut 1 pour un scan complet et ne récompense jamais une donnée absente.
    """

    if not results:
        raise ValueError("Aucun axe fourni pour le calcul OSIRIS")

    weights = _get_weights()
    known_results = {key: value for key, value in results.items() if key in weights}
    if not known_results:
        raise ValueError("Aucun axe canonique fourni pour le calcul OSIRIS")

    available_weight = sum(weights[key] for key in known_results)
    technical_score = round(
        sum(
            max(0.0, min(10.0, float(result.score))) * weights[key]
            for key, result in known_results.items()
        )
        / available_weight
        + 1e-12,
        1,
    )
    coverage = sum(
        weights[key] * max(0.0, min(1.0, float(result.coverage)))
        for key, result in known_results.items()
    )
    coverage = round(coverage, 3)
    reliability_factor = round(0.75 + 0.25 * coverage, 3)
    published_score = round(technical_score * reliability_factor, 1)
    missing = tuple(key for key in weights if key not in known_results)

    logger.debug(
        "Score technique=%.1f couverture=%.3f facteur=%.3f publié=%.1f",
        technical_score,
        coverage,
        reliability_factor,
        published_score,
    )
    return ScoreSummary(
        score=published_score,
        technical_score=technical_score,
        coverage=coverage,
        reliability=coverage,
        reliability_factor=reliability_factor,
        missing_axes=missing,
    )


def compute_osiris_score(results: dict[str, AxisResult]) -> float:
    """Retourne le score publié, pénalité de fiabilité incluse."""

    return compute_score_summary(results).score


def compute_partial_score(results: dict[str, AxisResult]) -> float:
    """Alias explicite du calcul canonique pour compatibilité API."""

    return compute_score_summary(results).score


def get_grade(score: float) -> str:
    """Retourne un statut technique sans affirmation de conformité."""

    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "Risque élevé"


def get_formula_description() -> str:
    """Description publique de la formule et de la fiabilité."""

    return (
        "Score technique = Σ(axe × poids); score publié = score technique × "
        "(0,75 + 0,25 × couverture)"
    )
