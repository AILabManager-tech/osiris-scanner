"""Tests unitaires pour history.py."""

from __future__ import annotations

import sqlite3
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
            grade="Bon",
            scores={"O": 8.0, "S": 6.0, "I": 8.0, "R": 9.0},
        )
        assert row_id > 0

        history = db.get_history("example.com")
        assert len(history) == 1
        assert history[0]["osiris_score"] == 7.5
        assert history[0]["grade"] == "Bon"
        assert history[0]["score_o"] == 8.0

    def test_get_latest(self, db: ScanHistory) -> None:
        db.save_scan("example.com", "https://example.com", 6.0, "À risque", {"O": 6.0})
        db.save_scan("example.com", "https://example.com", 8.0, "Bon", {"O": 8.0})

        latest = db.get_latest("example.com")
        assert latest is not None
        assert latest["osiris_score"] == 8.0

    def test_get_latest_empty(self, db: ScanHistory) -> None:
        assert db.get_latest("unknown.com") is None

    def test_get_delta(self, db: ScanHistory) -> None:
        db.save_scan(
            "example.com",
            "https://example.com",
            6.0,
            "À risque",
            {"O": 6.0, "S": 5.0, "I": 7.0, "R": 6.0},
        )
        db.save_scan(
            "example.com",
            "https://example.com",
            8.0,
            "Bon",
            {"O": 8.0, "S": 7.0, "I": 9.0, "R": 8.0},
        )

        delta = db.get_delta("example.com")
        assert delta is not None
        assert delta["delta"] == 2.0
        assert "O" in delta["improved_axes"]
        assert len(delta["regressed_axes"]) == 0

    def test_get_delta_with_regression(self, db: ScanHistory) -> None:
        db.save_scan(
            "example.com",
            "https://example.com",
            8.0,
            "Bon",
            {"O": 9.0, "S": 8.0, "I": 7.0, "R": 8.0},
        )
        db.save_scan(
            "example.com",
            "https://example.com",
            6.0,
            "À risque",
            {"O": 5.0, "S": 8.0, "I": 5.0, "R": 6.0},
        )

        delta = db.get_delta("example.com")
        assert delta is not None
        assert delta["delta"] == -2.0
        assert "O" in delta["regressed_axes"]
        assert "I" in delta["regressed_axes"]

    def test_get_delta_insufficient_data(self, db: ScanHistory) -> None:
        db.save_scan("example.com", "https://example.com", 7.0, "Bon", {})
        assert db.get_delta("example.com") is None

    def test_count(self, db: ScanHistory) -> None:
        assert db.count() == 0
        db.save_scan("a.com", "https://a.com", 7.0, "Bon", {})
        db.save_scan("b.com", "https://b.com", 8.0, "Bon", {})
        db.save_scan("a.com", "https://a.com", 9.0, "Exemplaire", {})
        assert db.count() == 3
        assert db.count("a.com") == 2
        assert db.count("b.com") == 1

    def test_history_order_newest_first(self, db: ScanHistory) -> None:
        db.save_scan("example.com", "https://example.com", 5.0, "À risque", {})
        db.save_scan("example.com", "https://example.com", 7.0, "Bon", {})
        db.save_scan("example.com", "https://example.com", 9.0, "Exemplaire", {})

        history = db.get_history("example.com")
        assert len(history) == 3
        assert history[0]["osiris_score"] == 9.0  # Most recent
        assert history[2]["osiris_score"] == 5.0  # Oldest

    def test_details_json(self, db: ScanHistory) -> None:
        details = {"mode": "deep", "runs": 3}
        db.save_scan("example.com", "https://example.com", 7.0, "Bon", {}, details=details)

        history = db.get_history("example.com")
        assert '"mode": "deep"' in history[0]["details_json"]

    def test_history_limit(self, db: ScanHistory) -> None:
        for i in range(10):
            db.save_scan("example.com", "https://example.com", float(i), "Critique", {})

        history = db.get_history("example.com", limit=3)
        assert len(history) == 3

    def test_multiple_domains_isolated(self, db: ScanHistory) -> None:
        db.save_scan("a.com", "https://a.com", 7.0, "Bon", {})
        db.save_scan("b.com", "https://b.com", 8.0, "Bon", {})

        assert len(db.get_history("a.com")) == 1
        assert len(db.get_history("b.com")) == 1
        assert len(db.get_history("c.com")) == 0

    def test_six_axis_scores_are_persisted_and_compared(self, db: ScanHistory) -> None:
        first = {"O": 6.0, "S": 6.0, "I": 6.0, "R": 6.0, "V": 5.0, "L": 7.0}
        second = {**first, "V": 8.0, "L": 4.0}
        db.save_scan("example.com", "https://example.com", 6.0, "Risque élevé", first)
        db.save_scan("example.com", "https://example.com", 6.5, "À surveiller", second)
        latest = db.get_latest("example.com")
        delta = db.get_delta("example.com")
        assert latest is not None and latest["score_v"] == 8.0 and latest["score_l"] == 4.0
        assert delta is not None
        assert "V" in delta["improved_axes"]
        assert "L" in delta["regressed_axes"]

    def test_migrates_legacy_four_axis_database(self, tmp_path: Path) -> None:
        path = tmp_path / "legacy.db"
        connection = sqlite3.connect(path)
        connection.execute(
            """CREATE TABLE scans (
            id INTEGER PRIMARY KEY, domain TEXT, url TEXT, timestamp TEXT,
            osiris_score REAL, grade TEXT, score_o REAL, score_s REAL,
            score_i REAL, score_r REAL, mode TEXT, details_json TEXT
            )"""
        )
        connection.commit()
        connection.close()

        migrated = ScanHistory(str(path))
        columns = {row[1] for row in migrated._conn.execute("PRAGMA table_info(scans)").fetchall()}
        migrated.close()
        assert {"score_v", "score_l"}.issubset(columns)
