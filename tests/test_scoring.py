"""Contrat public du scoring canonique à six axes."""

from __future__ import annotations

import pytest

from axes.performance import AxisResult
from scoring import (
    METHODOLOGY_VERSION,
    WEIGHT_INTRUSION,
    WEIGHT_LEGAL,
    WEIGHT_PERFORMANCE,
    WEIGHT_RESOURCE,
    WEIGHT_SECURITY,
    WEIGHT_SOVEREIGNTY,
    compute_osiris_score,
    compute_partial_score,
    compute_score_summary,
    get_grade,
)


def _results(score: float = 8.0, coverage: float = 1.0) -> dict[str, AxisResult]:
    return {
        key: AxisResult(score=score, coverage=coverage, tool_used="test")
        for key in ("O", "S", "I", "R", "V", "L")
    }


def test_weights_sum_to_one() -> None:
    total = (
        WEIGHT_PERFORMANCE
        + WEIGHT_SECURITY
        + WEIGHT_INTRUSION
        + WEIGHT_RESOURCE
        + WEIGHT_SOVEREIGNTY
        + WEIGHT_LEGAL
    )
    assert total == pytest.approx(1.0)


def test_complete_equal_scores_are_unchanged() -> None:
    summary = compute_score_summary(_results(8.0))
    assert summary.technical_score == 8.0
    assert summary.score == 8.0
    assert summary.coverage == 1.0
    assert summary.missing_axes == ()


def test_weighted_arithmetic_formula() -> None:
    results = _results()
    scores = {"O": 8.0, "S": 6.0, "I": 7.0, "R": 9.0, "V": 5.0, "L": 4.0}
    for key, value in scores.items():
        results[key].score = value
    expected = round(
        8.0 * WEIGHT_PERFORMANCE
        + 6.0 * WEIGHT_SECURITY
        + 7.0 * WEIGHT_INTRUSION
        + 9.0 * WEIGHT_RESOURCE
        + 5.0 * WEIGHT_SOVEREIGNTY
        + 4.0 * WEIGHT_LEGAL,
        1,
    )
    assert compute_osiris_score(results) == expected


def test_partial_scan_gets_documented_reliability_penalty() -> None:
    summary = compute_score_summary({"S": AxisResult(score=8.0, coverage=1.0)})
    assert summary.technical_score == 8.0
    assert summary.coverage == WEIGHT_SECURITY
    assert summary.reliability_factor == pytest.approx(0.812, abs=0.001)
    assert summary.score < summary.technical_score
    assert set(summary.missing_axes) == {"O", "I", "R", "V", "L"}


def test_axis_coverage_reduces_reliability_without_faking_axis_score() -> None:
    summary = compute_score_summary(_results(10.0, coverage=0.5))
    assert summary.technical_score == 10.0
    assert summary.coverage == 0.5
    assert summary.score == 8.8


def test_scores_are_bounded() -> None:
    results = _results()
    results["O"].score = 99
    results["S"].score = -5
    assert 0.0 <= compute_osiris_score(results) <= 10.0


def test_empty_or_unknown_results_raise() -> None:
    with pytest.raises(ValueError, match="Aucun axe"):
        compute_osiris_score({})
    with pytest.raises(ValueError, match="canonique"):
        compute_osiris_score({"X": AxisResult(score=5.0)})


@pytest.mark.parametrize(
    ("score", "status"),
    [
        (10.0, "Bon"),
        (8.5, "Bon"),
        (8.4, "À surveiller"),
        (6.5, "À surveiller"),
        (6.4, "Risque élevé"),
        (0.0, "Risque élevé"),
    ],
)
def test_statuses_are_technical_not_legal(score: float, status: str) -> None:
    assert get_grade(score) == status


def test_partial_alias_and_methodology_version() -> None:
    results = {"O": AxisResult(score=7.0, coverage=0.6)}
    assert compute_partial_score(results) == compute_osiris_score(results)
    assert METHODOLOGY_VERSION == "OSIRIS-6A-2026.1"
