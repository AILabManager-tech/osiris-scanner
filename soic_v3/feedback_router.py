"""SOIC v3.0 — Feedback Router: corrective instructions for failed gates."""

from __future__ import annotations

from soic_v3.models import GateReport, GateResult, GateStatus

# Gate-specific corrective templates
_CORRECTIVE_TEMPLATES: dict[str, str] = {
    "C-01": (
        "**Linting (ruff):** Fix the reported lint violations.\n"
        "Run `ruff check {path} --statistics` to see details, "
        "then `ruff check {path} --fix` to auto-fix what's possible."
    ),
    "C-02": (
        "**Security (bandit):** Resolve HIGH/CRITICAL security issues.\n"
        "Run `bandit -r {path} -f json` and address each finding. "
        "Common fixes: avoid hardcoded passwords, use safe deserialization."
    ),
    "C-03": (
        "**Tests (pytest):** Fix failing tests.\n"
        "Run `python -m pytest {path} --tb=short -q -o \"addopts=\"` "
        "to identify failures. Fix broken assertions or missing fixtures."
    ),
    "C-04": (
        "**Complexity (radon):** Reduce cyclomatic complexity.\n"
        "Run `radon cc {path} -a -nc` to find complex functions (grade C+). "
        "Extract helper methods, simplify conditions, reduce nesting."
    ),
    "C-05": (
        "**Type checking (mypy):** Fix type errors.\n"
        "Run `mypy {path} --ignore-missing-imports` and resolve each error. "
        "Add type annotations and fix incompatible types."
    ),
    "C-06": (
        "**Secrets (gitleaks):** Remove detected secrets from source.\n"
        "Move secrets to environment variables or a .env file (gitignored). "
        "Rotate any exposed credentials immediately."
    ),
}


class FeedbackRouter:
    """Generates corrective feedback for failed gates."""

    def generate(self, report: GateReport) -> str:
        """Produce a Markdown feedback block for all failed gates.

        Only includes gates with FAIL or ERROR status.
        Gates with PASS or SKIP are not mentioned.
        """
        failed_gates = [
            g for g in report.gates
            if g.status in (GateStatus.FAIL, GateStatus.ERROR)
        ]
        if not failed_gates:
            return "All gates passed. No corrective action needed."

        sections = [
            "## Corrective Feedback -- Iteration\n",
            f"**{len(failed_gates)} gate(s) require attention:**\n",
        ]
        for gate in failed_gates:
            sections.append(self._gate_feedback(gate, report.target_path))

        return "\n".join(sections)

    def _gate_feedback(self, gate: GateResult, target_path: str) -> str:
        """Build feedback section for a single failed gate."""
        template = _CORRECTIVE_TEMPLATES.get(gate.gate_id, "Review and fix the reported issues.")
        instruction = template.format(path=target_path)

        return (
            f"### {gate.gate_id} -- {gate.name} [{gate.status.value}]\n"
            f"**Evidence:** {gate.evidence}\n\n"
            f"{instruction}\n"
        )


# Web-specific feedback templates
_WEB_FEEDBACK: dict[str, dict[str, str]] = {
    "O": {
        "low": (
            "**Performance critique.** Optimisez les Core Web Vitals : "
            "compressez images, minifiez JS/CSS, activez le lazy loading."
        ),
        "mid": (
            "**Performance acceptable.** Envisagez un CDN "
            "et le prechargement des ressources critiques."
        ),
    },
    "S": {
        "low": (
            "**Securite deficiente.** Ajoutez les headers manquants : "
            "HSTS, CSP, X-Frame-Options, Referrer-Policy."
        ),
        "mid": (
            "**Securite partielle.** Renforcez la CSP "
            "et activez Permissions-Policy."
        ),
    },
    "I": {
        "low": (
            "**Trop de trackers.** Reduisez les scripts tiers "
            "et utilisez un gestionnaire de consentement."
        ),
        "mid": (
            "**Quelques trackers presents.** "
            "Verifiez la conformite RGPD/CCPA."
        ),
    },
    "R": {
        "low": (
            "**Page trop lourde.** Compressez les assets, "
            "reduisez les requetes HTTP, optimisez les images."
        ),
        "mid": (
            "**Poids acceptable.** Utilisez des formats modernes "
            "(WebP, AVIF) et la compression Brotli."
        ),
    },
}


class WebFeedbackRouter:
    """Generates recommendations for underperforming OSIRIS axes."""

    def __init__(self, threshold: float = 7.0) -> None:
        self.threshold = threshold

    def generate(
        self,
        axes: dict[str, dict],
        weights: dict[str, float] | None = None,
        delta: dict[str, float] | None = None,
    ) -> list[dict[str, str]]:
        """Generate prioritized recommendations.

        Args:
            axes: Dict of axis_key -> {"score": float, ...}.
            weights: Optional weight per axis (for impact prioritization).
            delta: Optional delta per axis vs previous scan.

        Returns:
            List of {"axis": str, "priority": str, "recommendation": str}.
        """
        weights = weights or {"O": 0.20, "S": 0.30, "I": 0.30, "R": 0.20}
        recs: list[tuple[float, dict[str, str]]] = []

        for axis_key, data in axes.items():
            score = data.get("score", 10.0)
            if score >= self.threshold:
                continue

            level = "low" if score < 5.0 else "mid"
            feedback = _WEB_FEEDBACK.get(axis_key, {}).get(level, "")
            if not feedback:
                continue

            # Priority = weight * improvement potential
            w = weights.get(axis_key, 0.25)
            potential = self.threshold - score
            impact = w * potential

            delta_str = ""
            if delta and axis_key in delta:
                d = delta[axis_key]
                delta_str = f" (delta: {d:+.1f})"

            recs.append((impact, {
                "axis": axis_key,
                "priority": f"{impact:.2f}",
                "recommendation": feedback + delta_str,
            }))

        # Sort by impact descending
        recs.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in recs]
