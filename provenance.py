"""Résolution fiable de la provenance du build OSIRIS.

Ordre de priorité : variables du runner, manifeste embarqué, dépôt Git qui suit
réellement ce module, puis état indisponible. Aucun SHA n'est déduit d'un dépôt
parent sans lien avec les fichiers livrés.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil

# Appel Git borné, sans shell ni entrée utilisateur.
import subprocess  # nosec B404
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("osiris")

MANIFEST_NAME = "BUILD_INFO.json"
ENV_COMMIT = "OSIRIS_BUILD_COMMIT"
ENV_COMMIT_STATE = "OSIRIS_BUILD_COMMIT_STATE"
ENV_BUILD_ID = "OSIRIS_BUILD_ID"
ENV_NOTE = "OSIRIS_BUILD_NOTE"

_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")
_COMMIT_STATES = {"exact", "derived", "unknown"}
_UNAVAILABLE_NOTE = (
    "Aucune provenance fiable : ni variable de runner, ni manifeste BUILD_INFO.json, "
    "ni dépôt Git suivant ce package. Aucun commit n'est supposé."
)


@dataclass(frozen=True)
class Provenance:
    """Identité vérifiable de l'artefact ayant produit un résultat."""

    source: str
    commit: str | None = None
    commit_short: str | None = None
    commit_state: str = "unknown"
    build_id: str | None = None
    manifest_path: str | None = None
    note: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.source != "unavailable" and bool(self.commit or self.build_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _valid_commit(value: object) -> str | None:
    candidate = _clean(value)
    if candidate is None:
        return None
    if not _SHA_PATTERN.fullmatch(candidate):
        logger.warning("Provenance : valeur de commit rejetée : %r", candidate)
        return None
    return candidate.lower()


def _valid_state(value: object, *, default: str) -> str:
    candidate = (_clean(value) or "").lower()
    return candidate if candidate in _COMMIT_STATES else default


def _from_env() -> Provenance | None:
    commit = _valid_commit(os.environ.get(ENV_COMMIT))
    build_id = _clean(os.environ.get(ENV_BUILD_ID))
    if commit is None and build_id is None:
        return None
    return Provenance(
        source="runner_env",
        commit=commit,
        commit_short=commit[:7] if commit else None,
        commit_state=_valid_state(
            os.environ.get(ENV_COMMIT_STATE), default="exact" if commit else "unknown"
        ),
        build_id=build_id,
        note=_clean(os.environ.get(ENV_NOTE)),
    )


def _manifest_candidates(package_root: Path) -> tuple[Path, ...]:
    """Couvre l'archive source et la ressource incluse dans le wheel."""

    return (
        package_root / MANIFEST_NAME,
        package_root / "osiris_web" / MANIFEST_NAME,
    )


def _from_manifest(package_root: Path) -> Provenance | None:
    manifest = next((path for path in _manifest_candidates(package_root) if path.is_file()), None)
    if manifest is None:
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Provenance : manifeste %s illisible : %s", manifest, exc)
        return None
    if not isinstance(data, dict):
        return None
    commit = _valid_commit(data.get("commit"))
    build_id = _clean(data.get("build_id"))
    if commit is None and build_id is None:
        return None
    return Provenance(
        source="manifest",
        commit=commit,
        commit_short=commit[:7] if commit else None,
        commit_state=_valid_state(
            data.get("commit_state"), default="exact" if commit else "unknown"
        ),
        build_id=build_id,
        manifest_path=str(manifest),
        note=_clean(data.get("note")),
    )


def _git(package_root: Path, *args: str) -> str | None:
    git_path = shutil.which("git")
    if git_path is None:
        return None
    try:
        # L'exécutable est absolu et les arguments sont internes et fixes.
        result = subprocess.run(  # nosec B603
            [git_path, *args],
            cwd=package_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _from_git(package_root: Path) -> Provenance | None:
    if _git(package_root, "ls-files", "--error-unmatch", Path(__file__).name) is None:
        return None
    commit = _valid_commit(_git(package_root, "rev-parse", "HEAD"))
    if commit is None:
        return None
    dirty = _git(package_root, "status", "--porcelain", "--", ".")
    return Provenance(
        source="git",
        commit=commit,
        commit_short=commit[:7],
        commit_state="derived" if dirty else "exact",
        note="Arbre de travail modifié par rapport au commit." if dirty else None,
    )


def resolve_provenance(package_root: str | Path | None = None) -> Provenance:
    """Résout une provenance sans fabriquer d'identifiant."""

    root = Path(package_root).resolve() if package_root else Path(__file__).resolve().parent
    return (
        _from_env()
        or _from_manifest(root)
        or _from_git(root)
        or Provenance(source="unavailable", note=_UNAVAILABLE_NOTE)
    )


def provenance_label(provenance: dict[str, Any] | None) -> str:
    if not provenance:
        return "non disponible"
    identifier = (
        provenance.get("commit_short")
        or provenance.get("commit")
        or provenance.get("build_id")
        or "non disponible"
    )
    return (
        f"{identifier} (source : {provenance.get('source', 'unavailable')}, "
        f"état : {provenance.get('commit_state', 'unknown')})"
    )
