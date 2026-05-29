"""Configuration pytest partagée.

scanner.py appelle `discover_axes()` au niveau module (à l'import), donc en
production le registre 6-axes (O/S/I/R/V/L) est toujours complet avant le
scoring et la génération de rapports.

Les tests qui n'importent pas scanner.py doivent reproduire ce précondition :
sans lui, `_get_weights()` retourne un registre PARTIEL (par ex. seul "O" est
enregistré via `from axes.performance import AxisResult`), ce qui shadow les
`_DEFAULT_WEIGHTS` complets et provoque soit un KeyError dans report.py, soit
des scores faux dans scoring.py.
"""

from __future__ import annotations

import pytest

from axes import discover_axes


@pytest.fixture(autouse=True)
def _populate_axis_registry() -> None:
    """Garantit les 6 axes enregistrés avant chaque test (idempotent)."""
    discover_axes()
