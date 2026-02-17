#!/usr/bin/env python3
"""Update SOIC badge in README.md based on latest run."""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from soic_v3.persistence import RunStore


def get_badge_url(mu: float, pass_rate: float, total_gates: int) -> str:
    """Generate shields.io badge URL."""
    passed = int(pass_rate * total_gates)
    if mu >= 8:
        color = "brightgreen"
    elif mu >= 6:
        color = "yellow"
    else:
        color = "red"

    label = "SOIC v3.0"
    message = f"mu {mu:.1f}/10 | {passed}/{total_gates} gates"
    return f"https://img.shields.io/badge/{label}-{message}-{color}"


def update_readme(badge_url: str) -> bool:
    """Update the SOIC badge in README.md."""
    readme_path = Path(__file__).parent.parent / "README.md"
    if not readme_path.exists():
        print("README.md not found")
        return False

    content = readme_path.read_text(encoding="utf-8")

    badge_pattern = r"!\[SOIC[^\]]*\]\([^)]*\)"
    badge_md = f"![SOIC Badge]({badge_url})"

    if re.search(badge_pattern, content):
        new_content = re.sub(badge_pattern, badge_md, content)
    else:
        # Add badge after first heading
        new_content = re.sub(r"(^# .+\n)", rf"\1\n{badge_md}\n", content, count=1)

    if new_content != content:
        readme_path.write_text(new_content, encoding="utf-8")
        print(f"Badge updated: {badge_md}")
        return True

    print("No changes needed")
    return False


def main() -> None:
    """Main entry point."""
    store = RunStore()
    latest = store.get_latest()

    if not latest:
        print("No SOIC runs found. Run an evaluation first.")
        sys.exit(1)

    mu = latest.get("mu", 0.0)
    pass_rate = latest.get("pass_rate", 0.0)
    total_gates = len(latest.get("gates", []))

    badge_url = get_badge_url(mu, pass_rate, total_gates)
    update_readme(badge_url)


if __name__ == "__main__":
    main()
