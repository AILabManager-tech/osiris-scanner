"""Tests unitaires pour cache.py."""

from __future__ import annotations

import time
from unittest.mock import patch

from cache import DEFAULT_TTLS, TTLCache


class TestTTLCache:
    def test_set_and_get(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self) -> None:
        cache = TTLCache()
        assert cache.get("nonexistent") is None

    def test_expired_entry_returns_none(self) -> None:
        cache = TTLCache(default_ttl=1)
        cache.set("key1", "value1", ttl=0)
        # TTL=0 means already expired on next check
        # We need to advance time slightly
        with patch("cache.time.monotonic", return_value=time.monotonic() + 1):
            assert cache.get("key1") is None

    def test_custom_ttl_per_entry(self) -> None:
        cache = TTLCache(default_ttl=10)
        cache.set("short", "val", ttl=1)
        cache.set("long", "val", ttl=3600)

        now = time.monotonic()
        with patch("cache.time.monotonic", return_value=now + 2):
            assert cache.get("short") is None
            assert cache.get("long") == "val"

    def test_clear(self) -> None:
        cache = TTLCache()
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.size() == 2
        cache.clear()
        assert cache.size() == 0
        assert cache.get("a") is None

    def test_evict_expired(self) -> None:
        cache = TTLCache(default_ttl=1)
        cache.set("expired", "val", ttl=0)
        cache.set("fresh", "val", ttl=3600)

        now = time.monotonic()
        with patch("cache.time.monotonic", return_value=now + 1):
            evicted = cache.evict_expired()
            assert evicted == 1
            assert cache.get("fresh") == "val"

    async def test_get_or_set_cache_miss(self) -> None:
        cache = TTLCache(default_ttl=60)

        async def factory() -> str:
            return "computed"

        result = await cache.get_or_set("key", factory(), ttl=60)
        assert result == "computed"
        assert cache.get("key") == "computed"

    async def test_get_or_set_cache_hit(self) -> None:
        cache = TTLCache(default_ttl=60)
        cache.set("key", "cached_value")

        call_count = 0

        async def factory() -> str:
            nonlocal call_count
            call_count += 1
            return "new_value"

        # Pass an already-resolved value instead of an unawaited coroutine
        # to avoid RuntimeWarning when cache hit skips the factory
        coro = factory()
        result = await cache.get_or_set("key", coro, ttl=60)
        # Should return cached value, not call factory
        assert result == "cached_value"
        # Explicitly close the unawaited coroutine to suppress warning
        coro.close()

    def test_size(self) -> None:
        cache = TTLCache()
        assert cache.size() == 0
        cache.set("a", 1)
        assert cache.size() == 1
        cache.set("b", 2)
        assert cache.size() == 2

    def test_overwrite_existing_key(self) -> None:
        cache = TTLCache()
        cache.set("key", "old")
        cache.set("key", "new")
        assert cache.get("key") == "new"


class TestDefaultTTLs:
    def test_observatory_24h(self) -> None:
        assert DEFAULT_TTLS["observatory"] == 86400

    def test_carbon_1h(self) -> None:
        assert DEFAULT_TTLS["carbon"] == 3600

    def test_page_5min(self) -> None:
        assert DEFAULT_TTLS["page"] == 300
