"""OSIRIS History — Persistance SQLite des scans.

Stocke chaque scan OSIRIS (domaine, date, scores, grade) dans une base SQLite.
Permet de suivre l'évolution d'un site dans le temps.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from provenance import resolve_provenance

DEFAULT_DB_PATH: str = "osiris_history.db"


class ScanHistory:
    """Gestionnaire d'historique des scans OSIRIS via SQLite.

    Attributes:
        db_path: Chemin vers le fichier SQLite.
    """

    def __init__(self, db_path: str | None = None) -> None:
        """Initialise la connexion et crée la table si nécessaire.

        Args:
            db_path: Chemin vers le fichier SQLite (défaut: osiris_history.db).
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self) -> None:
        """Crée la table de scans si elle n'existe pas."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                url TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                osiris_score REAL NOT NULL,
                grade TEXT NOT NULL,
                score_o REAL,
                score_s REAL,
                score_i REAL,
                score_r REAL,
                score_v REAL,
                score_l REAL,
                mode TEXT DEFAULT 'fast',
                provenance_commit TEXT,
                provenance_json TEXT,
                details_json TEXT
            )
        """)
        existing_columns = {
            row[1] for row in self._conn.execute("PRAGMA table_info(scans)").fetchall()
        }
        migrations = {
            "score_v": "REAL",
            "score_l": "REAL",
            "provenance_commit": "TEXT",
            "provenance_json": "TEXT",
        }
        for column, definition in migrations.items():
            if column not in existing_columns:
                self._conn.execute(f"ALTER TABLE scans ADD COLUMN {column} {definition}")
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scans_domain
            ON scans(domain, timestamp DESC)
        """)
        self._conn.commit()

    def save_scan(
        self,
        domain: str,
        url: str,
        osiris_score: float,
        grade: str,
        scores: dict[str, float],
        mode: str = "fast",
        details: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> int:
        """Enregistre un scan dans l'historique.

        Args:
            domain: Domaine scanné.
            url: URL complète scannée.
            osiris_score: Score OSIRIS composite.
            grade: Grade OSIRIS.
            scores: Dict des scores par axe canonique (O, S, I, R, V, L).
            mode: Mode de scan (fast/deep).
            details: Détails supplémentaires (sérialisés en JSON).
            provenance: Identité du build; résolue localement si omise.

        Returns:
            ID de l'enregistrement créé.
        """
        now = datetime.now(UTC).isoformat()
        provenance = provenance or resolve_provenance().to_dict()
        cursor = self._conn.execute(
            """
            INSERT INTO scans (domain, url, timestamp, osiris_score, grade,
                               score_o, score_s, score_i, score_r, score_v, score_l,
                               mode, provenance_commit, provenance_json, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                domain,
                url,
                now,
                osiris_score,
                grade,
                scores.get("O"),
                scores.get("S"),
                scores.get("I"),
                scores.get("R"),
                scores.get("V"),
                scores.get("L"),
                mode,
                provenance.get("commit") or provenance.get("build_id"),
                json.dumps(provenance, ensure_ascii=False),
                json.dumps(details, ensure_ascii=False) if details else None,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid or 0

    def get_history(self, domain: str, limit: int = 20) -> list[dict[str, Any]]:
        """Récupère l'historique des scans pour un domaine.

        Args:
            domain: Domaine à rechercher.
            limit: Nombre maximum de résultats.

        Returns:
            Liste de dictionnaires (les plus récents en premier).
        """
        rows = self._conn.execute(
            """
            SELECT * FROM scans
            WHERE domain = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (domain, limit),
        ).fetchall()

        return [dict(row) for row in rows]

    def get_latest(self, domain: str) -> dict[str, Any] | None:
        """Récupère le dernier scan pour un domaine.

        Args:
            domain: Domaine à rechercher.

        Returns:
            Dictionnaire du dernier scan, ou None.
        """
        history = self.get_history(domain, limit=1)
        return history[0] if history else None

    def get_delta(self, domain: str) -> dict[str, Any] | None:
        """Calcule le delta entre les deux derniers scans.

        Args:
            domain: Domaine à comparer.

        Returns:
            Dict avec delta score et axes améliorés/régressés, ou None.
        """
        history = self.get_history(domain, limit=2)
        if len(history) < 2:
            return None

        current = history[0]
        previous = history[1]
        delta = round(current["osiris_score"] - previous["osiris_score"], 1)

        improved = []
        regressed = []
        for axis in ["O", "S", "I", "R", "V", "L"]:
            key = f"score_{axis.lower()}"
            curr = current.get(key)
            prev = previous.get(key)
            if curr is not None and prev is not None:
                if curr > prev:
                    improved.append(axis)
                elif curr < prev:
                    regressed.append(axis)

        return {
            "delta": delta,
            "improved_axes": improved,
            "regressed_axes": regressed,
            "previous_score": previous["osiris_score"],
            "current_score": current["osiris_score"],
        }

    def count(self, domain: str | None = None) -> int:
        """Compte le nombre de scans enregistrés.

        Args:
            domain: Filtrer par domaine (optionnel).

        Returns:
            Nombre de scans.
        """
        if domain:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM scans WHERE domain = ?", (domain,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM scans").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        """Ferme la connexion SQLite."""
        self._conn.close()
