"""Tests pour le système de plugins axes (registre dynamique)."""

from __future__ import annotations

import pytest

from axes import CANONICAL_AXIS_KEYS, AxisRegistry, discover_axes, registry


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
    def test_discover_registers_six_canonical_axes(self) -> None:
        discover_axes()
        assert tuple(registry.keys()) == CANONICAL_AXIS_KEYS

    def test_discover_weights_sum_to_one(self) -> None:
        """La somme des poids des six axes doit être 1.0."""
        discover_axes()
        weights = registry.weights()
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_discover_axis_info_complete(self) -> None:
        """Chaque axe enregistré a toutes ses métadonnées."""
        discover_axes()
        for key in CANONICAL_AXIS_KEYS:
            info = registry.get(key)
            assert info is not None
            assert info.label
            assert info.weight > 0
            assert info.scan_fn is not None
            assert info.scan_label
            assert callable(info.scan_fn)
            assert info.scan_fn.__name__ == "scan"

    def test_resource_has_no_implicit_performance_dependency(self) -> None:
        """R mesure ses propres octets et ne lit plus un contexte Lighthouse partagé."""
        discover_axes()
        resource = registry.get("R")
        assert resource is not None
        assert resource.after == ()
