"""Domain grid registry for SOIC v3.0."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_DOMAIN_REGISTRY: dict[str, Callable] = {}


def register_domain(name: str, loader: Callable) -> None:
    """Register a domain grid loader function."""
    _DOMAIN_REGISTRY[name.upper()] = loader


def get_domain_gates(domain: str) -> list:
    """Return gate instances for the given domain."""
    loader = _DOMAIN_REGISTRY.get(domain.upper())
    if loader is None:
        raise ValueError(f"Unknown domain: {domain!r}. Available: {list(_DOMAIN_REGISTRY)}")
    return loader()


def list_domains() -> list[str]:
    """Return list of registered domain names."""
    return list(_DOMAIN_REGISTRY)
