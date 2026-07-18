"""Moteur de gouvernance *regulation-as-code* — agnostique à la loi.

Consomme `(observation, ruleset)` et produit des verdicts **décomposés et
cités**, règle par règle. La Loi 25 est le premier ruleset
(`rulesets/loi25.ruleset.yaml`) ; elle n'est JAMAIS codée en dur. Le même moteur
évalue GDPR / EU AI Act / CCPA via d'autres fichiers, même schéma.

Séparation des responsabilités :
- Le **YAML** porte la vérité normative : obligation, citation légale, sévérité,
  poids. C'est l'expert (texte de loi officiel) qui le remplit.
- Le **code appelant** (ex. `axes/legal.py`) porte l'*observation* (les faits
  bruts capturés sur le site) et un *évaluateur* par règle (le prédicat
  pass/fail). Il injecte ces évaluateurs dans `evaluate()`.

Garde-fou anti-hallucination (non négociable) : une règle dont la `source` est
encore un placeholder (`TODO` / `[À VÉRIFIER]`) n'a PAS de citation vérifiée. Un
audit qui n'observe aucune faute mais repose sur des citations non vérifiées
n'est PAS déclaré conforme — il est `indéterminé`. On ne certifie jamais un vert
par-dessus une citation inventée.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

logger = logging.getLogger("osiris")

VerdictStatus = Literal["pass", "fail", "non_applicable"]
Severite = Literal["bloquant", "majeur", "mineur"]

# Marqueurs de citation non vérifiée. Une `source` qui commence par l'un de ces
# préfixes (ou qui contient le second) est un placeholder, pas une citation.
_CITATION_PLACEHOLDERS = ("TODO", "[À VÉRIFIER]")


@dataclass(frozen=True)
class NormativeRule:
    """Une obligation légale observable, citée à sa source."""

    id: str
    obligation: str
    source: str
    observation: str
    verdict_logic: str
    preuve: list[str] = field(default_factory=list)
    severite: Severite = "majeur"
    poids: float = 1.0

    @property
    def citation_verifiee(self) -> bool:
        """True si la `source` est une citation réelle, pas un placeholder."""
        s = (self.source or "").strip()
        if not s:
            return False
        if s.upper().startswith("TODO"):
            return False
        return not any(marker in s for marker in _CITATION_PLACEHOLDERS)


@dataclass(frozen=True)
class Ruleset:
    """Un corpus normatif versionné (une loi, une juridiction)."""

    id: str
    juridiction: str
    loi: str
    version: str
    source_officielle: str
    statut: str
    regles: list[NormativeRule]


@dataclass
class RuleVerdict:
    """Verdict d'UNE règle pour UNE observation — traçable et cité."""

    rule_id: str
    obligation: str
    source: str
    severite: Severite
    poids: float
    status: VerdictStatus
    citation_verifiee: bool
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditVerdict:
    """Résultat agrégé d'un audit ruleset — décomposé, cité, scoré par règle."""

    ruleset_id: str
    ruleset_version: str
    score: float
    conforme: bool | None  # None = indéterminé (citations non vérifiées)
    bloquant_en_echec: bool
    citations_completes: bool
    verdicts: list[RuleVerdict]

    @property
    def statut_lisible(self) -> str:
        if self.conforme is True:
            return "conforme"
        if self.conforme is False:
            return "non_conforme"
        return "indetermine"

    def echecs(self) -> list[RuleVerdict]:
        return [v for v in self.verdicts if v.status == "fail"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "score": self.score,
            "conforme": self.conforme,
            "statut": self.statut_lisible,
            "bloquant_en_echec": self.bloquant_en_echec,
            "citations_completes": self.citations_completes,
            "verdicts": [v.to_dict() for v in self.verdicts],
        }


# Un évaluateur prend l'observation brute et retourne (status, evidence).
Evaluator = Callable[[dict[str, Any]], tuple[VerdictStatus, dict[str, Any]]]

SCORE_MAX = 10.0


def load_ruleset(path: str | Path) -> Ruleset:
    """Charge un fichier `*.ruleset.yaml` en objets typés.

    Raises:
        FileNotFoundError: fichier absent.
        ValueError: schéma YAML invalide (clés `ruleset`/`regles` manquantes).
    """
    p = Path(path)
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "ruleset" not in data or "regles" not in data:
        raise ValueError(
            f"Ruleset invalide {p} : clés `ruleset` et `regles` requises."
        )

    meta = data["ruleset"]
    regles = [
        NormativeRule(
            id=r["id"],
            obligation=r.get("obligation", "").strip(),
            source=r.get("source", ""),
            observation=r.get("observation", ""),
            verdict_logic=r.get("verdict_logic", ""),
            preuve=list(r.get("preuve", [])),
            severite=r.get("severite", "majeur"),
            poids=float(r.get("poids", 1.0)),
        )
        for r in data["regles"]
    ]

    return Ruleset(
        id=meta["id"],
        juridiction=meta.get("juridiction", ""),
        loi=meta.get("loi", ""),
        version=meta.get("version", ""),
        source_officielle=meta.get("source_officielle", ""),
        statut=meta.get("statut", ""),
        regles=regles,
    )


def evaluate(
    ruleset: Ruleset,
    observation: dict[str, Any],
    evaluators: dict[str, Evaluator],
) -> AuditVerdict:
    """Évalue un ruleset contre une observation, règle par règle.

    Args:
        ruleset: corpus normatif chargé.
        observation: faits bruts capturés par le scanner (clés = `preuve`).
        evaluators: `{rule_id: evaluator}`. Une règle sans évaluateur câblé est
            marquée `non_applicable` (pas d'échec silencieux : c'est tracé).

    Returns:
        AuditVerdict avec score décomposé et statut conforme/non/indéterminé.

    Scoring : départ à 10, on soustrait `poids` pour chaque règle en `fail`,
    plancher 0. Le score numérique ne PEUT pas verdir un audit dont une règle
    bloquante échoue, ni un audit aux citations non vérifiées.
    """
    verdicts: list[RuleVerdict] = []
    score = SCORE_MAX

    for rule in ruleset.regles:
        ev = evaluators.get(rule.id)
        if ev is None:
            status: VerdictStatus = "non_applicable"
            evidence: dict[str, Any] = {"raison": "aucun évaluateur câblé"}
            logger.debug("Règle %s : aucun évaluateur, non_applicable", rule.id)
        else:
            status, evidence = ev(observation)

        if status == "fail":
            score -= rule.poids

        verdicts.append(
            RuleVerdict(
                rule_id=rule.id,
                obligation=rule.obligation,
                source=rule.source,
                severite=rule.severite,
                poids=rule.poids,
                status=status,
                citation_verifiee=rule.citation_verifiee,
                evidence=evidence,
            )
        )

    score = max(0.0, round(score, 1))

    bloquant_en_echec = any(
        v.status == "fail" and v.severite == "bloquant" for v in verdicts
    )
    # Citations complètes = toute règle effectivement évaluée (pass/fail) cite
    # une source vérifiée. Les `non_applicable` ne comptent pas.
    citations_completes = all(
        v.citation_verifiee for v in verdicts if v.status in ("pass", "fail")
    )
    has_fail = any(v.status == "fail" for v in verdicts)

    if bloquant_en_echec or has_fail:
        # Faute observée -> non conforme, indépendamment des citations
        # (on n'a pas besoin de citation pour constater une faute factuelle).
        conforme: bool | None = False
    elif not citations_completes:
        # Aucune faute observée MAIS citations non vérifiées -> on ne certifie
        # pas. Indéterminé, pas vert. C'est le garde-fou anti-hallucination.
        conforme = None
    else:
        conforme = True

    return AuditVerdict(
        ruleset_id=ruleset.id,
        ruleset_version=ruleset.version,
        score=score,
        conforme=conforme,
        bloquant_en_echec=bloquant_en_echec,
        citations_completes=citations_completes,
        verdicts=verdicts,
    )
