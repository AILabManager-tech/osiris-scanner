"""OSIRIS Axes — Registre dynamique de plugins.

Chaque axe s'enregistre via le décorateur @register_axis.
L'orchestrateur (scanner.py) et le scoring (scoring.py) consultent
le registre au lieu de hardcoder les axes.

Exemple d'enregistrement dans un module d'axe :

    from axes import register_axis

    @register_axis("O", label="Performance", weight=0.15)
    async def scan(url: str, **kwargs) -> AxisResult:
        ...
"""

from __future__ import annotations

import importlib
import logging
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
    order: int = 100
    after: tuple[str, ...] = ()

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
        order: int = 100,
        after: tuple[str, ...] = (),
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
                order=order,
                after=after,
            )
            logger.debug("Axe %s (%s) enregistré, poids=%.2f", key, label, weight)
            return fn

        return decorator

    def get(self, key: str) -> AxisInfo | None:
        """Retourne les infos d'un axe par sa clé."""
        return self._axes.get(key)

    def all(self) -> list[AxisInfo]:
        """Retourne tous les axes enregistrés, triés par clé."""
        return sorted(self._axes.values(), key=lambda axis: (axis.order, axis.key))

    def keys(self) -> list[str]:
        """Retourne les clés de tous les axes enregistrés."""
        return [axis.key for axis in self.all()]

    def weights(self) -> dict[str, float]:
        """Retourne le dictionnaire {clé: poids} pour le scoring."""
        return {a.key: a.weight for a in self._axes.values()}

    def __len__(self) -> int:
        return len(self._axes)

    def __contains__(self, key: str) -> bool:
        return key in self._axes

    def validate(self) -> None:
        """Valide les invariants du registre canonique."""
        missing_dependencies = {
            dependency
            for axis in self._axes.values()
            for dependency in axis.after
            if dependency not in self._axes
        }
        if missing_dependencies:
            raise RuntimeError(
                "Dépendances d'axes inconnues : " + ", ".join(sorted(missing_dependencies))
            )
        total = sum(axis.weight for axis in self._axes.values())
        if abs(total - 1.0) > 1e-9:
            raise RuntimeError(f"La somme des poids des axes doit être 1.0, reçue : {total}")


# Instance globale du registre
registry = AxisRegistry()

# Raccourci pour le décorateur
register_axis = registry.register

CANONICAL_AXIS_KEYS: tuple[str, ...] = ("O", "S", "I", "R", "V", "L")


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
    if set(CANONICAL_AXIS_KEYS).issubset(registry.keys()):
        registry.validate()
