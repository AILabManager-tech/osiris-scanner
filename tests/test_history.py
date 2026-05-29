"""Tests unitaires pour history.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from history import ScanHistory


@pytest.fixture
def db(tmp_path: Path) -> ScanHistory:
    """Crée une base SQLite temporaire."""
    return ScanHistory(db_path=str(tmp_path / "test.db"))


class TestScanHistory:
    def test_save_and_retrieve(self, db: ScanHistory) -> None:
        row_id = db.save_scan(
            domain="example.com",
            url="https://example.com",
            osiris_score=7.5,
            grade="Conforme",
            scores={"O": 8.0, "S": 6.0, "I": 8.0, "R": 9.0},
        )
        assert row_id > 0

        history = db.get_history("example.com")
        assert len(history) == 1
        assert history[0]["osiris_score"] == 7.5
        assert history[0]["grade"] == "Conforme"
        assert history[0]["score_o"] == 8.0

    def test_get_latest(self, db: ScanHistory) -> None:
        db.save_scan("example.com", "https://example.com", 6.0, "À risque", {"O": 6.0})
        db.save_scan("example.com", "https://example.com", 8.0, "Conforme", {"O": 8.0})

        latest = db.get_latest("example.com")
        assert latest is not None
        assert latest["osiris_score"] == 8.0

    def test_get_latest_empty(self, db: ScanHistory) -> None:
        assert db.get_latest("unknown.com") is None

    def test_get_delta(self, db: ScanHistory) -> None:
        db.save_scan("example.com", "https://example.com", 6.0, "À risque",
                      {"O": 6.0, "S": 5.0, "I": 7.0, "R": 6.0})
        db.save_scan("example.com", "https://example.com", 8.0, "Conforme",
                      {"O": 8.0, "S": 7.0, "I": 9.0, "R": 8.0})

        delta = db.get_delta("example.com")
        assert delta is not None
        assert delta["delta"] == 2.0
        assert "O" in delta["improved_axes"]
        assert len(delta["regressed_axes"]) == 0

    def test_get_delta_with_regression(self, db: ScanHistory) -> None:
        db.save_scan("example.com", "https://example.com", 8.0, "Conforme",
                      {"O": 9.0, "S": 8.0, "I": 7.0, "R": 8.0})
        db.save_scan("example.com", "https://example.com", 6.0, "À risque",
                      {"O": 5.0, "S": 8.0, "I": 5.0, "R": 6.0})

        delta = db.get_delta("example.com")
        assert delta is not None
        assert delta["delta"] == -2.0
        assert "O" in delta["regressed_axes"]
        assert "I" in delta["regressed_axes"]

    def test_get_delta_insufficient_data(self, db: ScanHistory) -> None:
        db.save_scan("example.com", "https://example.com", 7.0, "Conforme", {})
        assert db.get_delta("example.com") is None

    def test_count(self, db: ScanHistory) -> None:
        assert db.count() == 0
        db.save_scan("a.com", "https://a.com", 7.0, "Conforme", {})
        db.save_scan("b.com", "https://b.com", 8.0, "Conforme", {})
        db.save_scan("a.com", "https://a.com", 9.0, "Exemplaire", {})
        assert db.count() == 3
        assert db.count("a.com") == 2
        assert db.count("b.com") == 1

    def test_history_order_newest_first(self, db: ScanHistory) -> None:
        db.save_scan("example.com", "https://example.com", 5.0, "À risque", {})
        db.save_scan("example.com", "https://example.com", 7.0, "Conforme", {})
        db.save_scan("example.com", "https://example.com", 9.0, "Exemplaire", {})

        history = db.get_history("example.com")
        assert len(history) == 3
        assert history[0]["osiris_score"] == 9.0  # Most recent
        assert history[2]["osiris_score"] == 5.0  # Oldest

    def test_details_json(self, db: ScanHistory) -> None:
        details = {"mode": "deep", "runs": 3}
        db.save_scan("example.com", "https://example.com", 7.0, "Conforme", {},
                      details=details)

        history = db.get_history("example.com")
        assert '"mode": "deep"' in history[0]["details_json"]

    def test_history_limit(self, db: ScanHistory) -> None:
        for i in range(10):
            db.save_scan("example.com", "https://example.com", float(i), "Critique", {})

        history = db.get_history("example.com", limit=3)
        assert len(history) == 3

    def test_multiple_domains_isolated(self, db: ScanHistory) -> None:
        db.save_scan("a.com", "https://a.com", 7.0, "Conforme", {})
        db.save_scan("b.com", "https://b.com", 8.0, "Conforme", {})

        assert len(db.get_history("a.com")) == 1
        assert len(db.get_history("b.com")) == 1
        assert len(db.get_history("c.com")) == 0
