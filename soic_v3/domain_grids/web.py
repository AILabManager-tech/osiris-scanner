"""SOIC v3.0 — DOMAIN_WEB: 4 quality gates wrapping OSIRIS axes."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from soic_v3.domain_grids import register_domain
from soic_v3.models import GateResult, GateStatus


@dataclass
class OsirisAxisGate:
    """Base for WEB domain gates that wrap OSIRIS axis scans."""

    gate_id: str
    name: str
    axis_module: str
    pass_threshold: float = 7.0

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        """Execute the OSIRIS axis scan and convert to GateResult.

        `path` is interpreted as a URL for web domain.
        """
        url = path
        start = time.monotonic()

        try:
            # Dynamic import of axis scan function
            if self.axis_module == "performance":
                from axes.performance import scan
            elif self.axis_module == "security":
                from axes.security import scan
            elif self.axis_module == "intrusion":
                from axes.intrusion import scan
            elif self.axis_module == "resource":
                from axes.resource import scan
            else:
                return GateResult(
                    gate_id=self.gate_id, name=self.name, status=GateStatus.ERROR,
                    evidence=f"Unknown axis module: {self.axis_module}",
                    duration_ms=0, command="",
                )

            # Run the async scan
            result = asyncio.run(scan(url))
            duration_ms = int((time.monotonic() - start) * 1000)

            status = GateStatus.PASS if result.score >= self.pass_threshold else GateStatus.FAIL
            evidence = f"Score: {result.score:.1f}/10 (threshold: {self.pass_threshold})"

            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=status,
                evidence=evidence,
                duration_ms=duration_ms,
                command=f"osiris.axes.{self.axis_module}.scan({url})",
            )

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.ERROR,
                evidence=str(e)[:200], duration_ms=duration_ms,
                command=f"osiris.axes.{self.axis_module}.scan({url})",
            )


def _load_web_gates() -> list:
    """Load all WEB domain gates."""
    return [
        OsirisAxisGate(gate_id="W-01", name="performance", axis_module="performance"),
        OsirisAxisGate(gate_id="W-02", name="security", axis_module="security"),
        OsirisAxisGate(
            gate_id="W-03", name="intrusion", axis_module="intrusion", pass_threshold=8.0,
        ),
        OsirisAxisGate(gate_id="W-04", name="resource", axis_module="resource"),
    ]


register_domain("WEB", _load_web_gates)
