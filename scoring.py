"""OSIRIS Scoring — Agrégation pondérée des 4 axes.

Formule publique :
    μ_osiris = O × 0.20 + S × 0.30 + I × 0.30 + R × 0.20

Grades :
    9.0 - 10.0 : Exemplaire
    7.0 -  8.9 : Conforme
    5.0 -  6.9 : À risque
    0.0 -  4.9 : Critique
"""

from __future__ import annotations

from axes.performance import AxisResult

# --- Pondérations (PUBLIQUES) ---

WEIGHT_PERFORMANCE: float = 0.20
WEIGHT_SECURITY: float = 0.30
WEIGHT_INTRUSION: float = 0.30
WEIGHT_RESOURCE: float = 0.20

WEIGHTS: dict[str, float] = {
    "O": WEIGHT_PERFORMANCE,
    "S": WEIGHT_SECURITY,
    "I": WEIGHT_INTRUSION,
    "R": WEIGHT_RESOURCE,
}

# --- Seuils de grade ---

GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (9.0, "Exemplaire"),
    (7.0, "Conforme"),
    (5.0, "À risque"),
    (0.0, "Critique"),
]


def compute_osiris_score(results: dict[str, AxisResult]) -> float:
    """Calcule le score OSIRIS composite.

    Formule : μ = O×0.20 + S×0.30 + I×0.30 + R×0.20

    Args:
        results: Dictionnaire {axe: AxisResult} avec clés O, S, I, R.

    Returns:
        Score composite entre 0.0 et 10.0.

    Raises:
        ValueError: Si un axe requis est manquant.
    """
    missing = set(WEIGHTS.keys()) - set(results.keys())
    if missing:
        raise ValueError(f"Axes manquants pour le calcul OSIRIS : {', '.join(sorted(missing))}")

    score = sum(
        results[axis].score * weight
        for axis, weight in WEIGHTS.items()
    )
    return round(score, 1)


def get_grade(score: float) -> str:
    """Détermine le grade OSIRIS à partir du score.

    Args:
        score: Score OSIRIS entre 0.0 et 10.0.

    Returns:
        Grade correspondant (Exemplaire, Conforme, À risque, Critique).
    """
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "Critique"


def get_formula_description() -> str:
    """Retourne la description textuelle de la formule de scoring.

    Returns:
        Description de la formule pour inclusion dans les rapports.
    """
    return (
        f"μ_osiris = "
        f"Performance × {WEIGHT_PERFORMANCE} + "
        f"Security × {WEIGHT_SECURITY} + "
        f"Intrusion × {WEIGHT_INTRUSION} + "
        f"Resource × {WEIGHT_RESOURCE}"
    )
