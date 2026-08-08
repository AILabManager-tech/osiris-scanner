"""OSIRIS Axes — Registre dynamique de plugins.

Chaque axe s'enregistre via le décorateur @register_axis.
L'orchestrateur (scanner.py) et le scoring (scoring.py) consultent
le registre au lieu de hardcoder les axes.

Exemple d'enregistrement dans un module d'axe :

    from axes import register_axis

    @register_axis("O", label="Performance", weight=0.20)
    async def scan(url: str, **kwargs) -> AxisResult:
        ...
"""

from __future__ import annotations

import importlib
import logging
import sys
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger("osiris")


@dataclass
class AxisInfo:
    """Métadonnées d'un axe enregistré."""

    key: str
    label: str
    weight: float
    scan_fn: Callable[..., Coroutine[Any, Any, Any]]
    exc_types: tuple[type[Exception], ...] = (RuntimeError,)
    scan_label: str = ""

    def __post_init__(self) -> None:
        if not self.scan_label:
            self.scan_label = f"Scan {self.label}..."


class AxisRegistry:
    """Registre central des axes OSIRIS.

    Les axes s'enregistrent via le décorateur register_axis().
    L'orchestrateur et le scoring consultent ce registre.
    """

    def __init__(self) -> None:
        self._axes: dict[str, AxisInfo] = {}

    def register(
        self,
        key: str,
        *,
        label: str,
        weight: float,
        exc_types: tuple[type[Exception], ...] = (RuntimeError,),
        scan_label: str = "",
    ) -> Callable[[F], F]:
        """Décorateur pour enregistrer une fonction scan comme axe.

        Args:
            key: Clé de l'axe (ex: "O", "S", "I", "R").
            label: Nom lisible de l'axe.
            weight: Pondération dans le score composite.
            exc_types: Exceptions capturées lors du scan.
            scan_label: Message affiché pendant le scan.

        Returns:
            Décorateur qui enregistre la fonction et la retourne inchangée.
        """

        def decorator(fn: F) -> F:
            self._axes[key] = AxisInfo(
                key=key,
                label=label,
                weight=weight,
                scan_fn=fn,
                exc_types=exc_types,
                scan_label=scan_label,
            )
            logger.debug("Axe %s (%s) enregistré, poids=%.2f", key, label, weight)
            return fn

        return decorator

    def get(self, key: str) -> AxisInfo | None:
        """Retourne les infos d'un axe par sa clé."""
        return self._axes.get(key)

    def all(self) -> list[AxisInfo]:
        """Retourne tous les axes enregistrés, triés par clé."""
        return sorted(self._axes.values(), key=lambda a: a.key)

    def keys(self) -> list[str]:
        """Retourne les clés de tous les axes enregistrés."""
        return sorted(self._axes.keys())

    def weights(self) -> dict[str, float]:
        """Retourne le dictionnaire {clé: poids} pour le scoring."""
        return {a.key: a.weight for a in self._axes.values()}

    def __len__(self) -> int:
        return len(self._axes)

    def __contains__(self, key: str) -> bool:
        return key in self._axes


# Instance globale du registre
registry = AxisRegistry()

# Raccourci pour le décorateur
register_axis = registry.register


def discover_axes() -> None:
    """Importe tous les modules d'axes pour déclencher l'enregistrement.

    Chaque module axes/*.py qui utilise @register_axis sera
    automatiquement enregistré lors de l'import.
    """
    axis_modules = [
        "axes.performance",
        "axes.security",
        "axes.intrusion",
        "axes.resource",
        "axes.sovereignty",
        "axes.legal",
    ]
    for module_name in axis_modules:
        try:
            importlib.import_module(module_name)
        except ImportError as e:
            logger.warning("Module %s non trouvé : %s", module_name, e)

    # Un module peut déjà être dans sys.modules alors que son entrée de registre
    # a été perdue ou remplacée. Réexécuter uniquement les modules canoniques
    # absents restaure le registre sans recharger le chemin nominal complet.
    module_by_key = dict(zip(("O", "S", "I", "R", "V", "L"), axis_modules, strict=True))
    for key, module_name in module_by_key.items():
        if key not in registry and module_name in sys.modules:
            importlib.reload(sys.modules[module_name])

    missing = [key for key in module_by_key if key not in registry]
    if missing:
        raise RuntimeError(f"Registre OSIRIS incomplet; axes absents : {', '.join(missing)}")
    canonical_weights = [
        axis.weight for key in module_by_key if (axis := registry.get(key)) is not None
    ]
    if any(weight <= 0 for weight in canonical_weights) or abs(sum(canonical_weights) - 1.0) > 1e-9:
        raise RuntimeError("Registre OSIRIS incohérent; les poids OSIRVL doivent totaliser 1.0")
