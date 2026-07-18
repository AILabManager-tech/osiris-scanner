"""Tests du moteur de gouvernance agnostique (governance.py).

Couvre : chargement ruleset, détection de citation non vérifiée, scoring
décomposé par poids, sévérité bloquante, et le garde-fou anti-hallucination
(pas de vert sur citation `TODO`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from governance import (
    NormativeRule,
    Ruleset,
    evaluate,
    load_ruleset,
)

RULESET_PATH = Path(__file__).parent.parent / "rulesets" / "loi25.ruleset.yaml"


def _passing(_obs):
    return "pass", {}


def _failing(_obs):
    return "fail", {}


def _na(_obs):
    return "non_applicable", {}


def _rule(rule_id, *, source="L. test, art. 1", severite="majeur", poids=1.0):
    return NormativeRule(
        id=rule_id,
        obligation="obligation test",
        source=source,
        observation="dom_presence",
        verdict_logic="test",
        preuve=[],
        severite=severite,
        poids=poids,
    )


def _ruleset(*regles):
    return Ruleset(
        id="test",
        juridiction="QC-CA",
        loi="loi test",
        version="v0",
        source_officielle="https://exemple",
        statut="test",
        regles=list(regles),
    )


# --- Chargement ---------------------------------------------------------------


def test_load_ruleset_loi25_reel():
    rs = load_ruleset(RULESET_PATH)
    assert rs.id == "loi25"
    assert rs.juridiction == "QC-CA"
    assert len(rs.regles) == 5
    ids = {r.id for r in rs.regles}
    assert "loi25-designation-rpp" in ids
    assert "loi25-traceurs-pre-consentement" in ids


def test_load_ruleset_fichier_absent():
    with pytest.raises(FileNotFoundError):
        load_ruleset(Path("/nope/inexistant.ruleset.yaml"))


def test_load_ruleset_schema_invalide(tmp_path):
    bad = tmp_path / "bad.ruleset.yaml"
    bad.write_text("juste: du texte\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_ruleset(bad)


# --- Citation vérifiée --------------------------------------------------------


def test_citation_todo_non_verifiee():
    assert _rule("x", source="TODO — à remplir").citation_verifiee is False


def test_citation_avec_marqueur_a_verifier():
    assert _rule("x", source="P-39.1 art. 8 [À VÉRIFIER]").citation_verifiee is False


def test_citation_reelle_verifiee():
    assert _rule("x", source="RLRQ c. P-39.1, art. 8.1").citation_verifiee is True


def test_citation_vide_non_verifiee():
    assert _rule("x", source="  ").citation_verifiee is False


# --- Scoring décomposé --------------------------------------------------------


def test_score_plein_si_tout_passe():
    rs = _ruleset(_rule("a", poids=3), _rule("b", poids=5))
    v = evaluate(rs, {}, {"a": _passing, "b": _passing})
    assert v.score == 10.0


def test_poids_soustrait_par_echec():
    rs = _ruleset(_rule("a", poids=3), _rule("b", poids=5))
    v = evaluate(rs, {}, {"a": _failing, "b": _passing})
    assert v.score == 7.0


def test_score_plancher_zero():
    rs = _ruleset(_rule("a", poids=8), _rule("b", poids=8))
    v = evaluate(rs, {}, {"a": _failing, "b": _failing})
    assert v.score == 0.0


def test_non_applicable_ne_penalise_pas():
    rs = _ruleset(_rule("a", poids=5))
    v = evaluate(rs, {}, {"a": _na})
    assert v.score == 10.0
    assert v.verdicts[0].status == "non_applicable"


def test_regle_sans_evaluateur_non_applicable():
    rs = _ruleset(_rule("orphan", poids=5))
    v = evaluate(rs, {}, {})  # aucun évaluateur câblé
    assert v.verdicts[0].status == "non_applicable"
    assert v.score == 10.0


# --- Statut conforme / non / indéterminé --------------------------------------


def test_bloquant_en_echec_non_conforme():
    rs = _ruleset(_rule("a", severite="bloquant", poids=5))
    v = evaluate(rs, {}, {"a": _failing})
    assert v.bloquant_en_echec is True
    assert v.conforme is False
    assert v.statut_lisible == "non_conforme"


def test_tout_passe_citations_reelles_conforme():
    rs = _ruleset(_rule("a", source="P-39.1 art. 8"), _rule("b", source="P-39.1 art. 9"))
    v = evaluate(rs, {}, {"a": _passing, "b": _passing})
    assert v.citations_completes is True
    assert v.conforme is True
    assert v.statut_lisible == "conforme"


def test_garde_fou_citation_todo_indetermine():
    # Aucune faute observée, MAIS citation TODO -> on ne certifie pas (None).
    rs = _ruleset(_rule("a", source="TODO — à remplir"))
    v = evaluate(rs, {}, {"a": _passing})
    assert v.citations_completes is False
    assert v.conforme is None
    assert v.statut_lisible == "indetermine"


def test_faute_observee_prime_sur_citation_manquante():
    # Une faute factuelle ne nécessite pas de citation pour être constatée.
    rs = _ruleset(_rule("a", source="TODO"))
    v = evaluate(rs, {}, {"a": _failing})
    assert v.conforme is False
