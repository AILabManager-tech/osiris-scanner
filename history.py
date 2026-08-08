"""OSIRIS History — Persistance SQLite des scans.

Stocke chaque scan OSIRIS (domaine, date, scores, grade) dans une base SQLite.
Permet de suivre l'évolution d'un site dans le temps.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

DEFAULT_DB_PATH: str = "osiris_history.db"

# Axes OSIRVL persistés (colonnes score_<clé minuscule>).
_AXIS_KEYS: tuple[str, ...] = ("O", "S", "I", "R", "V", "L")


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
        """Crée la table de scans si elle n'existe pas, puis migre les colonnes d'axes."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                url TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                osiris_score REAL NOT NULL,
                grade TEXT NOT NULL,
                status_global TEXT NOT NULL DEFAULT 'complete',
                build_id TEXT,
                build_commit TEXT,
                provenance_source TEXT NOT NULL DEFAULT 'unavailable',
                provenance_status TEXT NOT NULL DEFAULT 'indeterminate',
                score_o REAL,
                score_s REAL,
                score_i REAL,
                score_r REAL,
                score_v REAL,
                score_l REAL,
                mode TEXT DEFAULT 'fast',
                timeouts INTEGER NOT NULL DEFAULT 0,
                missing_axes_json TEXT,
                axis_errors_json TEXT,
                details_json TEXT
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scans_domain
            ON scans(domain, timestamp DESC)
        """)
        self._migrate_columns()
        self._conn.commit()

    def _migrate_columns(self) -> None:
        """Ajoute les colonnes de statut et d'axes aux bases historiques.

        CREATE TABLE IF NOT EXISTS n'altère pas une table existante : les bases
        créées avant l'ajout de V/L n'ont que score_o/s/i/r. On ajoute les
        colonnes manquantes de façon idempotente.
        """
        existing = {row["name"] for row in self._conn.execute("PRAGMA table_info(scans)")}
        for key in _AXIS_KEYS:
            column = f"score_{key.lower()}"
            if column not in existing:
                self._conn.execute(f"ALTER TABLE scans ADD COLUMN {column} REAL")
        migrations = {
            "status_global": "TEXT NOT NULL DEFAULT 'complete'",
            "build_id": "TEXT",
            "build_commit": "TEXT",
            "provenance_source": "TEXT NOT NULL DEFAULT 'unavailable'",
            "provenance_status": "TEXT NOT NULL DEFAULT 'indeterminate'",
            "timeouts": "INTEGER NOT NULL DEFAULT 0",
            "missing_axes_json": "TEXT",
            "axis_errors_json": "TEXT",
        }
        for column, definition in migrations.items():
            if column not in existing:
                self._conn.execute(f"ALTER TABLE scans ADD COLUMN {column} {definition}")

    def save_scan(
        self,
        domain: str,
        url: str,
        osiris_score: float,
        grade: str,
        scores: dict[str, float],
        mode: str = "fast",
        details: dict[str, Any] | None = None,
        status_global: str | None = None,
        timeouts: int = 0,
        missing_axes: list[str] | None = None,
        axis_errors: dict[str, Any] | None = None,
        build_id: str | None = None,
        build_commit: str | None = None,
        provenance_source: str = "unavailable",
        provenance_status: str | None = None,
    ) -> int:
        """Enregistre un scan dans l'historique.

        Args:
            domain: Domaine scanné.
            url: URL complète scannée.
            osiris_score: Score OSIRIS composite.
            grade: Grade OSIRIS.
            scores: Dict des scores par axe (O, S, I, R, V, L).
            mode: Mode de scan (fast/deep).
            details: Détails supplémentaires (sérialisés en JSON).
            status_global: État complete/partial/failed/indeterminate. Dérivé des
                axes présents si omis.
            timeouts: Nombre d'échecs réellement classés comme timeouts.
            missing_axes: Axes attendus sans résultat.
            axis_errors: Erreurs structurées par axe.
            build_id: Identifiant explicite fourni par le runner ou le manifeste.
            build_commit: Commit explicite fourni par le runner ou le manifeste.
            provenance_source: Origine de l'identifiant de build.
            provenance_status: observed si une provenance existe, sinon indeterminate.

        Returns:
            ID de l'enregistrement créé.
        """
        now = datetime.now(UTC).isoformat()
        expected_axes = set(_AXIS_KEYS)
        present_axes = set(scores) & expected_axes
        if status_global is None:
            if not present_axes:
                status_global = "failed"
            elif present_axes != expected_axes:
                status_global = "partial"
            else:
                status_global = "complete"
        if missing_axes is None:
            missing_axes = [axis for axis in _AXIS_KEYS if axis not in present_axes]
        axis_errors = axis_errors or {}
        if provenance_status is None:
            provenance_status = "observed" if build_id or build_commit else "indeterminate"
        if axis_errors and timeouts == 0:
            timeouts = sum(
                isinstance(error, dict) and error.get("kind") == "timeout"
                for error in axis_errors.values()
            )
        stored_grade = (
            grade
            if status_global == "complete"
            else {
                "partial": "Partiel",
                "failed": "Échec",
                "indeterminate": "Indéterminé",
            }.get(status_global, grade)
        )
        axis_columns = ", ".join(f"score_{k.lower()}" for k in _AXIS_KEYS)
        axis_placeholders = ", ".join("?" for _ in _AXIS_KEYS)
        cursor = self._conn.execute(
            f"""
            INSERT INTO scans (domain, url, timestamp, osiris_score, grade, status_global,
                               build_id, build_commit, provenance_source, provenance_status,
                               {axis_columns}, mode, timeouts, missing_axes_json,
                               axis_errors_json, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {axis_placeholders}, ?, ?, ?, ?, ?)
            """,
            (
                domain,
                url,
                now,
                osiris_score,
                stored_grade,
                status_global,
                build_id,
                build_commit,
                provenance_source,
                provenance_status,
                *(scores.get(k) for k in _AXIS_KEYS),
                mode,
                timeouts,
                json.dumps(missing_axes, ensure_ascii=False),
                json.dumps(axis_errors, ensure_ascii=False),
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
        for axis in _AXIS_KEYS:
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
