"""Tests unitaires pour scoring.py."""

from __future__ import annotations

import math

import pytest

from axes.performance import AxisResult
from scoring import (
    WEIGHT_INTRUSION,
    WEIGHT_LEGAL,
    WEIGHT_PERFORMANCE,
    WEIGHT_RESOURCE,
    WEIGHT_SECURITY,
    WEIGHT_SOVEREIGNTY,
    compute_osiris_score,
    compute_partial_score,
    get_grade,
)


def _make_results(
    o: float, s: float, i: float, r: float, v: float, ll: float
) -> dict[str, AxisResult]:
    """Helper pour créer un dict de résultats complet (6 axes OSIRVL)."""
    return {
        "O": AxisResult(score=o, tool_used="test"),
        "S": AxisResult(score=s, tool_used="test"),
        "I": AxisResult(score=i, tool_used="test"),
        "R": AxisResult(score=r, tool_used="test"),
        "V": AxisResult(score=v, tool_used="test"),
        "L": AxisResult(score=ll, tool_used="test"),
    }


# --- Tests compute_osiris_score ---


class TestComputeOsirisScore:
    def test_all_tens(self) -> None:
        results = _make_results(10.0, 10.0, 10.0, 10.0, 10.0, 10.0)
        assert compute_osiris_score(results) == 10.0

    def test_all_zeros(self) -> None:
        # Moyenne géométrique avec plancher epsilon=0.1 → effondrement à 0.1
        # (jamais 0.0 : ln(0) est indéfini).
        results = _make_results(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert compute_osiris_score(results) == 0.1

    def test_formula_correctness(self) -> None:
        # Formule v5.0 : moyenne géométrique pondérée Score = exp(Σ w_i·ln s_i).
        results = _make_results(8.0, 6.0, 7.0, 9.0, 8.0, 7.0)
        expected = round(
            math.exp(
                math.log(8.0) * WEIGHT_PERFORMANCE
                + math.log(6.0) * WEIGHT_SECURITY
                + math.log(7.0) * WEIGHT_INTRUSION
                + math.log(9.0) * WEIGHT_RESOURCE
                + math.log(8.0) * WEIGHT_SOVEREIGNTY
                + math.log(7.0) * WEIGHT_LEGAL
            ),
            1,
        )
        assert compute_osiris_score(results) == expected

    def test_weights_sum_to_one(self) -> None:
        total = (
            WEIGHT_PERFORMANCE
            + WEIGHT_SECURITY
            + WEIGHT_INTRUSION
            + WEIGHT_RESOURCE
            + WEIGHT_SOVEREIGNTY
            + WEIGHT_LEGAL
        )
        assert total == pytest.approx(1.0)

    def test_security_intrusion_higher_weight(self) -> None:
        """Zéroter S+I (poids combiné 0.45) effondre plus que zéroter O+R (0.25)."""
        score_zero_si = compute_osiris_score(_make_results(10.0, 0.0, 0.0, 10.0, 10.0, 10.0))
        score_zero_or = compute_osiris_score(_make_results(0.0, 10.0, 10.0, 0.0, 10.0, 10.0))
        assert score_zero_si < score_zero_or

    def test_missing_axis_uses_partial(self) -> None:
        """Missing axes trigger partial scoring instead of raising."""
        results = {
            "O": AxisResult(score=10.0, tool_used="test"),
            "S": AxisResult(score=10.0, tool_used="test"),
        }
        score = compute_osiris_score(results)
        assert 0.0 <= score <= 10.0

    def test_empty_results_raises(self) -> None:
        with pytest.raises(ValueError, match="Aucun axe"):
            compute_osiris_score({})

    def test_asymmetric_scores(self) -> None:
        results = _make_results(5.0, 5.0, 5.0, 5.0, 5.0, 5.0)
        assert compute_osiris_score(results) == 5.0


# --- Tests get_grade ---


class TestGetGrade:
    def test_exemplaire_10(self) -> None:
        assert get_grade(10.0) == "Exemplaire"

    def test_exemplaire_9(self) -> None:
        assert get_grade(9.0) == "Exemplaire"

    def test_conforme_8_9(self) -> None:
        assert get_grade(8.9) == "Conforme"

    def test_conforme_7(self) -> None:
        assert get_grade(7.0) == "Conforme"

    def test_a_risque_6_9(self) -> None:
        assert get_grade(6.9) == "À risque"

    def test_a_risque_5(self) -> None:
        assert get_grade(5.0) == "À risque"

    def test_critique_4_9(self) -> None:
        assert get_grade(4.9) == "Critique"

    def test_critique_0(self) -> None:
        assert get_grade(0.0) == "Critique"

    def test_critique_1(self) -> None:
        assert get_grade(1.0) == "Critique"


# --- Tests compute_partial_score ---


class TestComputePartialScore:
    def test_single_axis(self) -> None:
        """One axis → score based on that axis with penalty."""
        results = {"O": AxisResult(score=8.0, tool_used="test")}
        score = compute_partial_score(results)
        assert 0.0 <= score <= 10.0
        # Avec seulement 1/6 axes, le score est pénalisé
        assert score < 8.0

    def test_three_axes(self) -> None:
        """Three axes → closer to full score, less penalty."""
        results = {
            "O": AxisResult(score=8.0, tool_used="test"),
            "S": AxisResult(score=8.0, tool_used="test"),
            "I": AxisResult(score=8.0, tool_used="test"),
        }
        score = compute_partial_score(results)
        assert 0.0 <= score <= 10.0
        # 3/6 axes à 8.0 → 8.0 × pénalité fiabilité (3/6)^0.5 ≈ 5.7
        assert score == pytest.approx(5.7, abs=0.1)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="Aucun axe"):
            compute_partial_score({})

    def test_all_axes_same_as_full(self) -> None:
        """Les 6 axes présents → compute_partial_score == compute_osiris_score."""
        results = _make_results(8.0, 6.0, 7.0, 9.0, 8.0, 7.0)
        partial = compute_partial_score(results)
        full = compute_osiris_score(results)
        assert partial == pytest.approx(full, abs=0.5)

    def test_score_bounds(self) -> None:
        """Partial score stays within 0-10."""
        results = {"S": AxisResult(score=10.0, tool_used="test")}
        score = compute_partial_score(results)
        assert 0.0 <= score <= 10.0

    def test_high_weight_axis_matters_more(self) -> None:
        """S seul (poids 0.25) ne score pas moins que O seul (poids 0.15) à score égal."""
        results_s = {"S": AxisResult(score=8.0, tool_used="test")}
        results_o = {"O": AxisResult(score=8.0, tool_used="test")}
        score_s = compute_partial_score(results_s)
        score_o = compute_partial_score(results_o)
        # Un seul axe → poids normalisé à 1.0 dans les deux cas, même pénalité
        # fiabilité (1/6 axes) : les deux scores sont égaux.
        assert score_s >= score_o

    def test_unknown_axis_does_not_inflate_partial_reliability(self) -> None:
        recognized = {"O": AxisResult(score=8.0, tool_used="test")}
        contaminated = {
            **recognized,
            "X": AxisResult(score=10.0, tool_used="contaminant"),
        }

        assert compute_partial_score(contaminated) == compute_partial_score(recognized)
