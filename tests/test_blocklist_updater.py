"""Tests unitaires pour blocklist_updater.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from blocklist_updater import (
    _load_existing_blocklist,
    _save_blocklist,
    update_blocklist,
)


class TestLoadExistingBlocklist:
    def test_load_valid(self, tmp_path: Path) -> None:
        data = {"domains": ["a.com", "b.com"], "_meta": {"count": 2}}
        path = tmp_path / "trackers.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        domains, meta = _load_existing_blocklist(str(path))
        assert "a.com" in domains
        assert meta["count"] == 2

    def test_load_missing_file(self, tmp_path: Path) -> None:
        domains, meta = _load_existing_blocklist(str(tmp_path / "nonexistent.json"))
        assert len(domains) == 0
        assert meta == {}


class TestSaveBlocklist:
    def test_save_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "trackers.json"
        saved = _save_blocklist({"a.com", "b.com"}, str(path), ["test source"])
        assert saved.exists()
        data = json.loads(saved.read_text(encoding="utf-8"))
        assert len(data["domains"]) == 2
        assert data["_meta"]["count"] == 2
        assert "test source" in data["_meta"]["sources"]

    def test_save_sorted(self, tmp_path: Path) -> None:
        path = tmp_path / "trackers.json"
        _save_blocklist({"z.com", "a.com", "m.com"}, str(path))
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["domains"] == ["a.com", "m.com", "z.com"]


class TestUpdateBlocklist:

    async def test_update_merges_sources(self, tmp_path: Path) -> None:
        # Create existing blocklist
        path = tmp_path / "trackers.json"
        path.write_text(
            json.dumps({"domains": ["existing.com"], "_meta": {}}),
            encoding="utf-8",
        )

        with (
            patch(
                "blocklist_updater._fetch_disconnect_domains",
                new_callable=AsyncMock,
                return_value={"disconnect-tracker.com"},
            ),
            patch(
                "blocklist_updater._fetch_easyprivacy_domains",
                new_callable=AsyncMock,
                return_value={"easyprivacy-tracker.com"},
            ),
        ):
            stats = await update_blocklist(str(path))

        assert stats["previous_count"] == 1
        assert stats["new_count"] == 2
        assert stats["total_count"] == 3

        # Verify file content
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "existing.com" in data["domains"]
        assert "disconnect-tracker.com" in data["domains"]
        assert "easyprivacy-tracker.com" in data["domains"]


    async def test_update_handles_source_failure(self, tmp_path: Path) -> None:
        """If one source fails, still merges the other."""
        path = tmp_path / "trackers.json"
        path.write_text(
            json.dumps({"domains": ["existing.com"], "_meta": {}}),
            encoding="utf-8",
        )

        with (
            patch(
                "blocklist_updater._fetch_disconnect_domains",
                new_callable=AsyncMock,
                return_value=set(),  # Failed
            ),
            patch(
                "blocklist_updater._fetch_easyprivacy_domains",
                new_callable=AsyncMock,
                return_value={"new-tracker.com"},
            ),
        ):
            stats = await update_blocklist(str(path))

        assert stats["total_count"] == 2  # existing + easyprivacy


    async def test_update_no_duplicates(self, tmp_path: Path) -> None:
        """Domains from multiple sources are deduplicated."""
        path = tmp_path / "trackers.json"
        path.write_text(
            json.dumps({"domains": ["shared.com"], "_meta": {}}),
            encoding="utf-8",
        )

        with (
            patch(
                "blocklist_updater._fetch_disconnect_domains",
                new_callable=AsyncMock,
                return_value={"shared.com", "disconnect-only.com"},
            ),
            patch(
                "blocklist_updater._fetch_easyprivacy_domains",
                new_callable=AsyncMock,
                return_value={"shared.com", "easyprivacy-only.com"},
            ),
        ):
            stats = await update_blocklist(str(path))

        assert stats["total_count"] == 3  # shared + disconnect-only + easyprivacy-only
