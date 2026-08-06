# OSIRIS — checklist d’exécution

Mise à jour : 2026-08-06

## Qualité et validation locale

- [x] Tests complets sans warnings bloquants — `219 passed`
- [x] Ruff, Mypy, compileall
- [x] Bandit et pip-audit
- [x] Packaging wheel/sdist
- [x] Exclusion `__pycache__`/`.pyc` des artefacts
- [x] Vérification reproductible des artefacts
- [x] Scan local de motifs de secrets

## Release et staging

- [x] Rejet explicite des payloads JSON non-objet
- [x] Headers CSP, X-Frame-Options, Referrer-Policy, Permissions-Policy
- [x] `docker compose config`
- [ ] Reverse proxy TLS
- [ ] Allowlist egress en infrastructure
- [ ] Rate limiting distribué
- [x] Validation Gitleaks officielle — job `gitleaks` dans `.github/workflows/ci.yml`, action officielle v2.3.9 (scan CI; aucune installation locale requise)
- [x] Matrice Python 3.11/3.12 en CI — job `tests` avec `strategy.matrix`

## Validation externe contrôlée

- [ ] Scans sur cibles publiques autorisées
- [ ] Validation Observatory / Green Web / Carbon / ipwho.is
- [ ] Variance, retries et dégradation hors disponibilité
- [ ] Consentement réel multilingue
- [ ] Tests SSRF/DNS avec infrastructure externe contrôlée

## Release ultime

- [ ] Documentation méthodologique et release alignées
- [ ] SBOM/checksums/signatures finales
- [ ] Canary staging
- [ ] Runbook incident, sauvegarde, rollback
- [ ] Approbation utilisateur pour push/déploiement

## Preuves et relève

- `feaabda` — qualité locale et warnings
- `1b38e19` — packaging propre et vérification artefacts
- `f747d30` — audit release/staging local
- `97c04c3` — scan Gitleaks officiel ajouté à la CI et Mypy explicite
- Checkpoint local du 2026-08-06 : `pytest -q -W error` (**219 passed**), Ruff,
  Mypy `--explicit-package-bases`, `compileall`, `uv build --offline`,
  `scripts/verify_package.py` et `docker compose config` passent. Le build
  isolé `python -m build` n’est pas relancé sans accès réseau, car son
  environnement PEP 517 tente de télécharger `setuptools`.
- Rapport qualité : `/tmp/osiris-quality-handoff-20260806.md`
- Rapport packaging : `/tmp/osiris-quality-handoff-20260806-packaging.md`
- Rapport staging : `docs/RELEASE_STAGING_AUDIT.md`
- CI : `.github/workflows/ci.yml` — `quality` appelle `scripts/verify_package.py` après `python -m build`; `tests` couvre Python 3.11 et 3.12; `gitleaks` utilise l’action officielle v2.3.9.
