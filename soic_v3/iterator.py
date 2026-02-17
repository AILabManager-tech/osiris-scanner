"""SOIC v3.0 — SOICIterator: orchestrates the evaluate-decide-feedback loop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from soic_v3.converger import Converger, Decision
from soic_v3.feedback_router import FeedbackRouter
from soic_v3.gate_engine import GateEngine
from soic_v3.models import GateReport
from soic_v3.persistence import RunStore


@dataclass
class IterationResult:
    """Result of a single iteration within the loop."""

    iteration: int
    report: GateReport
    decision: Decision
    feedback: str
    summary: str

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "iteration": self.iteration,
            "report": self.report.to_dict(),
            "decision": self.decision.value,
            "feedback": self.feedback,
            "summary": self.summary,
        }


@dataclass
class LoopResult:
    """Full result of an iteration loop."""

    iterations: list[IterationResult] = field(default_factory=list)
    final_decision: Decision = Decision.ITERATE
    final_mu: float = 0.0

    @property
    def total_iterations(self) -> int:
        return len(self.iterations)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "total_iterations": self.total_iterations,
            "final_decision": self.final_decision.value,
            "final_mu": self.final_mu,
            "iterations": [it.to_dict() for it in self.iterations],
        }


# Type alias for the iteration callback
IterationCallback = Callable[[int, IterationResult], None]


class SOICIterator:
    """Orchestrates the full SOIC iteration loop.

    Loop: evaluate -> decide -> feedback -> (repeat or stop)
    """

    def __init__(
        self,
        domain: str,
        target_path: str,
        test_path: str | None = None,
        max_iter: int = 3,
    ) -> None:
        self.domain = domain
        self.target_path = target_path
        self.test_path = test_path
        self.max_iter = max_iter
        self.converger = Converger(max_iter=max_iter)
        self.feedback_router = FeedbackRouter()
        self.store = RunStore()

    def run(self, on_iteration: IterationCallback | None = None) -> LoopResult:
        """Execute the full iteration loop.

        Args:
            on_iteration: Optional callback called after each iteration
                with (iteration_number, IterationResult). Useful for
                real-time CLI output.

        Returns:
            LoopResult with all iteration details.
        """
        loop = LoopResult()

        for i in range(1, self.max_iter + 1):
            # Evaluate
            engine = GateEngine(
                domain=self.domain,
                target_path=self.target_path,
                test_path=self.test_path,
            )
            report = engine.run_all_gates()
            self.store.save_run(report)

            # Decide
            decision = self.converger.decide(report, iteration=i)
            summary = self.converger.get_summary(decision, iteration=i)

            # Feedback
            if decision == Decision.ACCEPT:
                feedback = "All gates passed. No corrective action needed."
            else:
                feedback = self.feedback_router.generate(report)

            result = IterationResult(
                iteration=i,
                report=report,
                decision=decision,
                feedback=feedback,
                summary=summary,
            )
            loop.iterations.append(result)

            if on_iteration is not None:
                on_iteration(i, result)

            # Stop conditions
            if decision in (Decision.ACCEPT, Decision.ABORT_PLATEAU, Decision.ABORT_MAX_ITER):
                loop.final_decision = decision
                loop.final_mu = report.mu
                break

        if not loop.iterations:
            loop.final_decision = Decision.ABORT_MAX_ITER
        elif loop.final_decision == Decision.ITERATE:
            loop.final_decision = Decision.ABORT_MAX_ITER
            loop.final_mu = loop.iterations[-1].report.mu

        return loop
