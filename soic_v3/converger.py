"""SOIC v3.0 — Converger: iteration decision engine."""

from __future__ import annotations

from enum import StrEnum

from soic_v3.models import GateReport, GateStatus


class Decision(StrEnum):
    """Convergence decision after an evaluation."""

    ACCEPT = "ACCEPT"
    ITERATE = "ITERATE"
    ABORT_PLATEAU = "ABORT_PLATEAU"
    ABORT_MAX_ITER = "ABORT_MAX_ITER"


class Converger:
    """Decides whether to accept, iterate, or abort based on gate results."""

    def __init__(self, max_iter: int = 3) -> None:
        self.max_iter = max_iter
        self.mu_history: list[float] = []

    def decide(self, report: GateReport, iteration: int) -> Decision:
        """Evaluate the report and return a decision.

        Args:
            report: The latest gate evaluation report.
            iteration: Current iteration number (1-based).

        Returns:
            Decision enum value.
        """
        self.mu_history.append(report.mu)

        # All gates PASS -> accept
        all_pass = all(
            g.status in (GateStatus.PASS, GateStatus.SKIP)
            for g in report.gates
        )
        if all_pass:
            return Decision.ACCEPT

        # Max iterations reached -> abort
        if iteration >= self.max_iter:
            return Decision.ABORT_MAX_ITER

        # Plateau: delta_mu <= 0 for 2 consecutive iterations
        if len(self.mu_history) >= 2:
            delta = self.mu_history[-1] - self.mu_history[-2]
            if delta <= 0 and len(self.mu_history) >= 3:
                prev_delta = self.mu_history[-2] - self.mu_history[-3]
                if prev_delta <= 0:
                    return Decision.ABORT_PLATEAU

        # Default: iterate
        return Decision.ITERATE

    def reset(self) -> None:
        """Reset history for a fresh run."""
        self.mu_history.clear()

    def get_summary(self, decision: Decision, iteration: int) -> str:
        """Return a human-readable summary of the decision."""
        mu_str = f"mu={self.mu_history[-1]:.2f}" if self.mu_history else "mu=N/A"
        summaries = {
            Decision.ACCEPT: f"ACCEPT -- All gates passed ({mu_str})",
            Decision.ITERATE: f"ITERATE -- Iteration {iteration}/{self.max_iter} ({mu_str})",
            Decision.ABORT_PLATEAU: f"ABORT -- Score plateau detected ({mu_str})",
            Decision.ABORT_MAX_ITER: f"ABORT -- Max iterations reached ({mu_str})",
        }
        return summaries[decision]


class WebConverger:
    """Convergence analysis for web scan history.

    Analyzes the trend of a site across multiple scans:
    - improving: scores are going up
    - stable: scores are flat
    - degrading: scores are going down
    """

    def __init__(self, plateau_threshold: float = 0.3) -> None:
        self.plateau_threshold = plateau_threshold

    def analyze_trend(self, scores: list[float]) -> str:
        """Determine the trend from a list of chronological scores.

        Returns:
            One of 'improving', 'stable', 'degrading', or 'insufficient_data'.
        """
        if len(scores) < 2:
            return "insufficient_data"

        deltas = [scores[i] - scores[i - 1] for i in range(1, len(scores))]
        avg_delta = sum(deltas) / len(deltas)

        if avg_delta > self.plateau_threshold:
            return "improving"
        if avg_delta < -self.plateau_threshold:
            return "degrading"
        return "stable"

    def detect_plateau(self, scores: list[float]) -> bool:
        """Return True if the last 3+ scores show no meaningful change."""
        if len(scores) < 3:
            return False
        recent = scores[-3:]
        spread = max(recent) - min(recent)
        return spread <= self.plateau_threshold

    def detect_regression(self, scores: list[float]) -> bool:
        """Return True if the latest score is lower than the previous."""
        if len(scores) < 2:
            return False
        return scores[-1] < scores[-2] - self.plateau_threshold
