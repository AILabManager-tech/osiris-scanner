"""SOIC v3.0 — Gate Engine: orchestrates quality gate execution."""

from __future__ import annotations

from soic_v3.domain_grids import get_domain_gates
from soic_v3.models import GateReport, GateResult, SOICScore


class GateEngine:
    """Orchestrates gate execution for a given domain."""

    def __init__(self, domain: str, target_path: str, test_path: str | None = None) -> None:
        self.domain = domain.upper()
        self.target_path = target_path
        self.test_path = test_path
        self.gates = get_domain_gates(self.domain)

    def run_gate(self, gate_id: str) -> GateResult:
        """Execute a single gate by ID."""
        for gate in self.gates:
            if gate.gate_id == gate_id:
                return gate.run(self.target_path, self.test_path)
        raise ValueError(f"Gate {gate_id!r} not found in domain {self.domain}")

    def run_all_gates(self) -> GateReport:
        """Execute all gates sequentially and return a full report."""
        report = GateReport(domain=self.domain, target_path=self.target_path)
        for gate in self.gates:
            result = gate.run(self.target_path, self.test_path)
            report.gates.append(result)
        report.compute_score()
        return report

    def get_score(self, report: GateReport) -> SOICScore:
        """Compute score from an existing report."""
        return report.compute_score()
