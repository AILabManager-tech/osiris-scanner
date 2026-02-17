"""Tests unitaires pour scoring.py."""

from __future__ import annotations

import pytest

from axes.performance import AxisResult
from scoring import (
    WEIGHT_INTRUSION,
    WEIGHT_PERFORMANCE,
    WEIGHT_RESOURCE,
    WEIGHT_SECURITY,
    compute_osiris_score,
    get_grade,
)


def _make_results(o: float, s: float, i: float, r: float) -> dict[str, AxisResult]:
    """Helper pour créer un dict de résultats."""
    return {
        "O": AxisResult(score=o, tool_used="test"),
        "S": AxisResult(score=s, tool_used="test"),
        "I": AxisResult(score=i, tool_used="test"),
        "R": AxisResult(score=r, tool_used="test"),
    }


# --- Tests compute_osiris_score ---


class TestComputeOsirisScore:
    def test_all_tens(self) -> None:
        results = _make_results(10.0, 10.0, 10.0, 10.0)
        assert compute_osiris_score(results) == 10.0

    def test_all_zeros(self) -> None:
        results = _make_results(0.0, 0.0, 0.0, 0.0)
        assert compute_osiris_score(results) == 0.0

    def test_formula_correctness(self) -> None:
        results = _make_results(8.0, 6.0, 7.0, 9.0)
        expected = round(
            8.0 * WEIGHT_PERFORMANCE
            + 6.0 * WEIGHT_SECURITY
            + 7.0 * WEIGHT_INTRUSION
            + 9.0 * WEIGHT_RESOURCE,
            1,
        )
        assert compute_osiris_score(results) == expected

    def test_weights_sum_to_one(self) -> None:
        total = WEIGHT_PERFORMANCE + WEIGHT_SECURITY + WEIGHT_INTRUSION + WEIGHT_RESOURCE
        assert total == pytest.approx(1.0)

    def test_security_intrusion_higher_weight(self) -> None:
        """S et I à 0, O et R à 10 → score bas car S+I pèsent 60%."""
        results = _make_results(10.0, 0.0, 0.0, 10.0)
        score = compute_osiris_score(results)
        assert score == 4.0  # (10*0.2 + 0*0.3 + 0*0.3 + 10*0.2) = 4.0

    def test_missing_axis_raises(self) -> None:
        results = {
            "O": AxisResult(score=10.0, tool_used="test"),
            "S": AxisResult(score=10.0, tool_used="test"),
        }
        with pytest.raises(ValueError, match="Axes manquants"):
            compute_osiris_score(results)

    def test_asymmetric_scores(self) -> None:
        results = _make_results(5.0, 5.0, 5.0, 5.0)
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
