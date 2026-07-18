"""Tests de l'axe Legal (axes/legal.py) au niveau évaluateurs.

Ne touche pas Playwright : on injecte des observations synthétiques (les faits
qu'`_observe` produirait) dans le moteur via `EVALUATORS`. Le scénario clé est
le **faux positif usine-rh** : RPP absent mais politique de confidentialité
présente — l'ancien code passait gamma (10/10), le nouveau échoue la règle RPP.
"""

from __future__ import annotations

from axes.legal import EVALUATORS, _get_ruleset
from governance import evaluate


def _audit(observation):
    return evaluate(_get_ruleset(), observation, EVALUATORS)


def _obs(**overrides):
    """Observation par défaut conforme (site propre), surchargeable."""
    base = {
        "trackers_pre_consent": [],
        "refuse_button_found": True,
        "refuse_pattern": "refuser",
        "trackers_after_refusal": [],
        "rpp_found": True,
        "rpp_evidence": "mailto:privacy@exemple.com",
        "privacy_policy_links": [{"text": "Confidentialité", "href": "/privacy"}],
    }
    base.update(overrides)
    return base


def _verdict(audit, rule_id):
    return next(v for v in audit.verdicts if v.rule_id == rule_id)


# --- Le faux positif usine-rh -------------------------------------------------


def test_usine_rh_faux_positif_corrige():
    # RPP absent, mais lien politique de confidentialité présent. Avant : gamma
    # passait (10/10). Maintenant : la règle RPP échoue, l'absence n'est plus
    # noyée par le lien-confidentialité.
    audit = _audit(_obs(rpp_found=False, rpp_evidence=None))
    rpp = _verdict(audit, "loi25-designation-rpp")
    politique = _verdict(audit, "loi25-politique-confidentialite-publiee")

    assert rpp.status == "fail"
    assert politique.status == "pass"
    assert audit.conforme is False
    assert audit.score < 10.0


# --- Évaluateurs individuels --------------------------------------------------


def test_traceurs_pre_consentement_echoue_si_trackers():
    audit = _audit(_obs(trackers_pre_consent=["https://google-analytics.com/x"]))
    assert _verdict(audit, "loi25-traceurs-pre-consentement").status == "fail"


def test_mecanisme_de_refus_echoue_si_absent():
    audit = _audit(_obs(refuse_button_found=False, refuse_pattern=None))
    v = _verdict(audit, "loi25-mecanisme-de-refus")
    assert v.status == "fail"
    assert v.severite == "bloquant"
    assert audit.bloquant_en_echec is True


def test_respect_du_refus_non_applicable_sans_bouton():
    # Pas de mécanisme -> on ne teste pas le respect (pas de double peine).
    audit = _audit(_obs(refuse_button_found=False, refuse_pattern=None))
    assert _verdict(audit, "loi25-respect-du-refus").status == "non_applicable"


def test_respect_du_refus_echoue_si_trackers_apres_clic():
    audit = _audit(_obs(trackers_after_refusal=["https://facebook.com/tr"]))
    assert _verdict(audit, "loi25-respect-du-refus").status == "fail"


def test_politique_confidentialite_echoue_si_absente():
    audit = _audit(_obs(privacy_policy_links=[]))
    assert _verdict(audit, "loi25-politique-confidentialite-publiee").status == "fail"


# --- Garde-fou citation au niveau ruleset réel --------------------------------


def test_site_propre_reste_indetermine_citations_todo():
    # Le ruleset livré a encore des `source: TODO`. Même un site parfait ne peut
    # pas être déclaré conforme tant que Gear n'a pas rempli les citations P-39.1.
    audit = _audit(_obs())
    assert audit.echecs() == []
    assert audit.citations_completes is False
    assert audit.conforme is None
    assert audit.statut_lisible == "indetermine"
