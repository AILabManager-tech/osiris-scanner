"""SOIC v3.0 — Core data models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class GateStatus(StrEnum):
    """Result status of a quality gate execution."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class GateResult:
    """Result of a single gate execution."""

    gate_id: str
    name: str
    status: GateStatus
    evidence: str
    duration_ms: int
    command: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "gate_id": self.gate_id,
            "name": self.name,
            "status": self.status.value,
            "evidence": self.evidence,
            "duration_ms": self.duration_ms,
            "command": self.command,
        }


@dataclass
class SOICScore:
    """Computed SOIC score from gate results."""

    mu: float
    pass_rate: float
    total_gates: int
    passed: int
    failed: int
    skipped: int
    failures: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "mu": self.mu,
            "pass_rate": self.pass_rate,
            "total_gates": self.total_gates,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "failures": self.failures,
        }


@dataclass
class GateReport:
    """Full report from a gate engine run."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    domain: str = ""
    target_path: str = ""
    gates: list[GateResult] = field(default_factory=list)
    mu: float = 0.0
    pass_rate: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def compute_score(self) -> SOICScore:
        """Compute the SOIC score from gate results.

        mu = (PASS count / evaluated count) * 10
        Evaluated = total - SKIP count.
        """
        skipped = sum(1 for g in self.gates if g.status == GateStatus.SKIP)
        evaluated = len(self.gates) - skipped
        passed = sum(1 for g in self.gates if g.status == GateStatus.PASS)
        failed = sum(1 for g in self.gates if g.status in (GateStatus.FAIL, GateStatus.ERROR))
        fail_statuses = (GateStatus.FAIL, GateStatus.ERROR)
        failures = [g.gate_id for g in self.gates if g.status in fail_statuses]

        if evaluated > 0:
            self.pass_rate = passed / evaluated
            self.mu = self.pass_rate * 10
        else:
            self.pass_rate = 0.0
            self.mu = 0.0

        return SOICScore(
            mu=self.mu,
            pass_rate=self.pass_rate,
            total_gates=len(self.gates),
            passed=passed,
            failed=failed,
            skipped=skipped,
            failures=failures,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize full report to dictionary."""
        return {
            "run_id": self.run_id,
            "domain": self.domain,
            "target_path": self.target_path,
            "gates": [g.to_dict() for g in self.gates],
            "mu": self.mu,
            "pass_rate": self.pass_rate,
            "timestamp": self.timestamp,
        }


@dataclass
class DeltaReport:
    """Delta between two scans (web or code)."""

    previous_score: float
    current_score: float
    delta: float
    improved_axes: list[str]
    regressed_axes: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "previous_score": self.previous_score,
            "current_score": self.current_score,
            "delta": self.delta,
            "improved_axes": self.improved_axes,
            "regressed_axes": self.regressed_axes,
        }
