"""Tests de l'axe Legal (axes/legal.py) au niveau évaluateurs.

Ne touche pas Playwright : on injecte des observations synthétiques (les faits
qu'`_observe` produirait) dans le moteur via `EVALUATORS`. Le scénario clé est
le **faux positif usine-rh** : RPP absent mais politique de confidentialité
présente — l'ancien code passait gamma (10/10), le nouveau échoue la règle RPP.
"""

from __future__ import annotations

import pytest

import axes.legal as legal
from axes.legal import (
    EVALUATORS,
    _acceptance_selectors,
    _get_ruleset,
    _is_privacy_policy_link,
    _observe_acceptance,
    _refusal_selectors,
)
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


def test_faux_refus_span_not_treated_as_refusal_control():
    # VAL-001: un texte visible sans contrôle actionnable ne constitue pas un refus.
    selectors = _refusal_selectors("refuser")
    assert all(selector.startswith(("button:", "a:")) for selector in selectors)
    assert not any(selector.startswith("span:") for selector in selectors)


def test_rpp_mailto_not_treated_as_privacy_policy():
    # VAL-002: le contact RPP ne remplace pas un lien vers une politique publiée.
    assert not _is_privacy_policy_link(
        "Responsable de la protection des renseignements personnels",
        "mailto:responsable@example.com",
    )
    assert _is_privacy_policy_link("Politique de confidentialité", "/privacy-policy")


def test_acceptance_selectors_require_actionable_controls():
    selectors = _acceptance_selectors("accepter")
    assert all(selector.startswith(("button:", "a:")) for selector in selectors)
    assert not any(selector.startswith("span:") for selector in selectors)


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeControl:
    def __init__(self, page: _FakePage) -> None:
        self.page = page

    async def is_visible(self) -> bool:
        return True

    async def click(self) -> None:
        await self.page.emit_request("https://pixel.quantserve.com/collect?phase=after-accept")


class _FakePage:
    def __init__(self) -> None:
        self.listeners: list = []

    def on(self, event: str, callback) -> None:
        assert event == "request"
        self.listeners.append(callback)

    def remove_listener(self, event: str, callback) -> None:
        assert event == "request"
        self.listeners.remove(callback)

    async def emit_request(self, url: str) -> None:
        for callback in list(self.listeners):
            await callback(_FakeRequest(url))

    async def goto(self, *_args, **_kwargs) -> None:
        await self.emit_request("https://fixture.localhost/page")

    async def wait_for_timeout(self, _timeout: int) -> None:
        return None

    async def query_selector(self, selector: str):
        if selector.startswith("button:") and "accepter" in selector:
            return _FakeControl(self)
        return None


class _FakeContext:
    def __init__(self) -> None:
        self.page = _FakePage()
        self.closed = False

    async def new_page(self) -> _FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self) -> None:
        self.context = _FakeContext()

    async def new_context(self, **_kwargs) -> _FakeContext:
        return self.context


@pytest.mark.asyncio
async def test_acceptance_branch_separates_before_action_and_after_requests():
    browser = _FakeBrowser()

    branch = await _observe_acceptance(browser, "https://fixture.localhost/page")

    assert branch["status"] == "observed"
    assert branch["before"]["trackers"] == []
    assert branch["before"]["accept_button_found"] is True
    assert branch["action"] == {"attempted": True, "performed": True, "error": None}
    assert branch["after"]["trackers"] == [
        "https://pixel.quantserve.com/collect?phase=after-accept"
    ]
    assert browser.context.closed is True


@pytest.mark.asyncio
async def test_acceptance_signal_is_technical_and_does_not_change_score(
    monkeypatch: pytest.MonkeyPatch,
):
    observation = _obs()
    observation["acceptance_branch"] = {
        "status": "observed",
        "before": {"trackers": [], "accept_button_found": True},
        "action": {"attempted": True, "performed": True, "error": None},
        "after": {"trackers": ["https://pixel.quantserve.com/after-accept"]},
    }

    async def observed(_url: str):
        return observation

    monkeypatch.setattr(legal, "_observe", observed)
    result = await legal.scan("https://fixture.localhost/page")

    assert result.score == _audit(_obs()).score
    assert (
        result.details["technical_observation"]["acceptance_branch"]
        == observation["acceptance_branch"]
    )
    assert result.details["legal_status"]["acceptance_branch"] == "not_assessed"


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
