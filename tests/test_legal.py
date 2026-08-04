"""Régressions des signaux vie privée sans conclusions juridiques."""

from __future__ import annotations

import pytest

from axes.legal import _has_privacy_contact_signal
from url_security import redact_url


@pytest.mark.parametrize(
    "address",
    [
        "privacy@example.com",
        "rpp@auxo.ca",
        "confidentialite@exemple.ca",
        "legal-team@example.org",
    ],
)
def test_privacy_contact_signal_uses_mailbox_local_part(address: str) -> None:
    assert _has_privacy_contact_signal(f'<a href="mailto:{address}">Contact</a>')


def test_privacy_contact_signal_does_not_use_domain_name() -> None:
    assert not _has_privacy_contact_signal(
        '<a href="mailto:contact@privacy.example.com">Contact</a>'
    )


def test_evidence_url_redaction_removes_query_and_fragment() -> None:
    assert redact_url("https://user:secret@tracker.example/pixel?id=secret#token") == (
        "https://tracker.example/pixel"
    )
