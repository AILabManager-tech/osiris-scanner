"""OSIRIS Cache — Cache mémoire avec TTL configurable.

Fournit un cache simple en mémoire avec expiration configurable par clé.
Utilisé pour éviter les appels API répétés lors de scans successifs.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("osiris")

# TTL par défaut par type de données (en secondes)
DEFAULT_TTLS: dict[str, int] = {
    "observatory": 86400,  # 24h — Observatory cache interne
    "carbon": 3600,  # 1h — données carbone changent rarement
    "headers": 300,  # 5min — headers peuvent changer
    "page": 300,  # 5min — contenu de page
    "green_hosting": 86400,  # 24h — statut d'hébergement vert
}


class TTLCache:
    """Cache mémoire thread-safe avec TTL configurable.

    Attributes:
        _store: Dictionnaire {clé: (valeur, timestamp_expiration)}.
        _default_ttl: TTL par défaut en secondes.
    """

    def __init__(self, default_ttl: int = 300, max_entries: int = 1_024) -> None:
        """Initialise le cache.

        Args:
            default_ttl: TTL par défaut en secondes (5 minutes).
            max_entries: Nombre maximal d'entrées conservées en mémoire.
        """
        if max_entries < 1:
            raise ValueError("max_entries doit être positif")
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl
        self._max_entries = max_entries
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        """Récupère une valeur du cache si non expirée.

        Args:
            key: Clé de cache.

        Returns:
            Valeur mise en cache, ou None si absente/expirée.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None

            value, expires_at = entry
            if time.monotonic() > expires_at:
                self._store.pop(key, None)
                logger.debug("Cache miss (expiré) : %s", key)
                return None

        logger.debug("Cache hit : %s", key)
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Stocke une valeur dans le cache.

        Args:
            key: Clé de cache.
            value: Valeur à stocker.
            ttl: TTL en secondes (utilise default_ttl si None).
        """
        actual_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.monotonic() + actual_ttl
        with self._lock:
            if key not in self._store and len(self._store) >= self._max_entries:
                now = time.monotonic()
                expired_keys = [
                    existing_key
                    for existing_key, (_, expiration) in self._store.items()
                    if now > expiration
                ]
                for expired_key in expired_keys:
                    self._store.pop(expired_key, None)
            while key not in self._store and len(self._store) >= self._max_entries:
                self._store.pop(next(iter(self._store)))
            self._store[key] = (value, expires_at)
        logger.debug("Cache set : %s (TTL=%ds)", key, actual_ttl)

    async def get_or_set(
        self,
        key: str,
        factory: Any,
        ttl: int | None = None,
    ) -> Any:
        """Récupère du cache ou exécute la factory et met en cache le résultat.

        Args:
            key: Clé de cache.
            factory: Coroutine async à exécuter si la valeur n'est pas en cache.
            ttl: TTL en secondes.

        Returns:
            Valeur (du cache ou fraîchement calculée).
        """
        cached = self.get(key)
        if cached is not None:
            return cached

        value = await factory
        self.set(key, value, ttl)
        return value

    def clear(self) -> None:
        """Vide entièrement le cache."""
        with self._lock:
            self._store.clear()

    def size(self) -> int:
        """Retourne le nombre d'entrées dans le cache (y compris expirées)."""
        with self._lock:
            return len(self._store)

    def evict_expired(self) -> int:
        """Supprime les entrées expirées. Retourne le nombre supprimé."""
        now = time.monotonic()
        with self._lock:
            expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired_keys:
                self._store.pop(k, None)
            return len(expired_keys)


# Instance globale partagée par tous les axes
scan_cache = TTLCache(default_ttl=300)
