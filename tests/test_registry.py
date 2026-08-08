"""Tests pour le système de plugins axes (registre dynamique)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from axes import AxisRegistry, discover_axes, registry
from scoring import _get_weights


class TestAxisRegistry:
    def test_register_axis(self) -> None:
        reg = AxisRegistry()

        @reg.register("X", label="Test", weight=0.50)
        async def scan_test(url: str):
            return None

        assert "X" in reg
        assert len(reg) == 1
        info = reg.get("X")
        assert info is not None
        assert info.label == "Test"
        assert info.weight == 0.50
        assert info.scan_fn is scan_test

    def test_register_multiple_axes(self) -> None:
        reg = AxisRegistry()

        @reg.register("A", label="Alpha", weight=0.30)
        async def scan_a(url: str):
            pass

        @reg.register("B", label="Beta", weight=0.70)
        async def scan_b(url: str):
            pass

        assert len(reg) == 2
        assert reg.keys() == ["A", "B"]

    def test_all_sorted(self) -> None:
        reg = AxisRegistry()

        @reg.register("Z", label="Zulu", weight=0.25)
        async def scan_z(url: str):
            pass

        @reg.register("A", label="Alpha", weight=0.75)
        async def scan_a(url: str):
            pass

        axes = reg.all()
        assert axes[0].key == "A"
        assert axes[1].key == "Z"

    def test_weights(self) -> None:
        reg = AxisRegistry()

        @reg.register("O", label="Perf", weight=0.20)
        async def scan_o(url: str):
            pass

        @reg.register("S", label="Sec", weight=0.80)
        async def scan_s(url: str):
            pass

        weights = reg.weights()
        assert weights == {"O": 0.20, "S": 0.80}

    def test_get_missing_returns_none(self) -> None:
        reg = AxisRegistry()
        assert reg.get("X") is None

    def test_contains(self) -> None:
        reg = AxisRegistry()

        @reg.register("T", label="Test", weight=1.0)
        async def scan_t(url: str):
            pass

        assert "T" in reg
        assert "X" not in reg

    def test_custom_exc_types(self) -> None:
        reg = AxisRegistry()

        @reg.register("E", label="Exc", weight=0.5, exc_types=(ValueError, IOError))
        async def scan_e(url: str):
            pass

        info = reg.get("E")
        assert info is not None
        assert info.exc_types == (ValueError, IOError)

    def test_scan_label_default(self) -> None:
        reg = AxisRegistry()

        @reg.register("D", label="Default", weight=0.5)
        async def scan_d(url: str):
            pass

        info = reg.get("D")
        assert info is not None
        assert info.scan_label == "Scan Default..."

    def test_scan_label_custom(self) -> None:
        reg = AxisRegistry()

        @reg.register("C", label="Custom", weight=0.5, scan_label="Custom scan in progress...")
        async def scan_c(url: str):
            pass

        info = reg.get("C")
        assert info is not None
        assert info.scan_label == "Custom scan in progress..."


class TestDiscoverAxes:
    def test_discover_registers_all_six(self) -> None:
        """discover_axes() importe les 6 modules et enregistre O, S, I, R, V, L."""
        # Le registre global devrait déjà avoir les axes enregistrés
        # car les imports au top du fichier déclenchent les décorateurs
        discover_axes()
        assert len(registry) >= 6
        for key in ["O", "S", "I", "R", "V", "L"]:
            assert key in registry, f"Axe {key} non enregistré"

    def test_discover_weights_sum_to_one(self) -> None:
        """La somme des poids des 6 axes OSIRVL doit être 1.0."""
        discover_axes()
        weights = registry.weights()
        total_weight = sum(weights[k] for k in ["O", "S", "I", "R", "V", "L"])
        assert abs(total_weight - 1.0) < 1e-9

    def test_discover_axis_info_complete(self) -> None:
        """Chaque axe enregistré a toutes ses métadonnées."""
        discover_axes()
        for key in ["O", "S", "I", "R", "V", "L"]:
            info = registry.get(key)
            assert info is not None
            assert info.label
            assert info.weight > 0
            assert info.scan_fn is not None
            assert info.scan_label
            assert callable(info.scan_fn)

    def test_partial_import_is_restored_in_fresh_process(self) -> None:
        """Un registre ayant perdu cinq entrées retrouve les six axes canoniques."""
        code = (
            "import axes, axes.performance; "
            "o = axes.registry.get('O'); "
            "axes.registry._axes = {'O': o}; "
            "axes.discover_axes(); "
            "assert set(axes.registry.keys()) == set('OSIRVL'); "
            "assert abs(sum(axes.registry.weights().values()) - 1.0) < 1e-9"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    def test_partial_global_registry_cannot_replace_canonical_weights(
        self,
    ) -> None:
        code = (
            "import axes, axes.performance; "
            "o = axes.registry.get('O'); "
            "axes.registry._axes = {'O': o}; "
            "from scoring import _get_weights; "
            "weights = _get_weights(); "
            "assert set(weights) == set('OSIRVL'); "
            "assert abs(sum(weights.values()) - 1.0) < 1e-9"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    def test_contaminated_global_registry_falls_back_to_canonical_weights(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        contaminated = dict(registry._axes)
        monkeypatch.setattr(registry, "_axes", contaminated)

        @registry.register("X", label="Contaminant", weight=0.5)
        async def scan_x(_url: str) -> None:
            return None

        weights = _get_weights()

        assert set(weights) == set("OSIRVL")
        assert "X" not in weights
        assert sum(weights.values()) == pytest.approx(1.0)
