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

- [x] Documentation méthodologique et release alignées — README/DEVELOPMENT/ARCHITECTURE/METHODOLOGY/SECURITY
  relus et confrontés au code. Un écart réel corrigé : `mypy .` (sans `--explicit-package-bases`)
  documenté dans README.md et docs/DEVELOPMENT.md échouait réellement (`api/scan.py` : conflit de
  module), corrigé aux deux endroits pour matcher la CI et le checkpoint. Limites documentées
  (port 25000-25099, 4 jobs actifs, 4096 octets, 32 connexions) vérifiées identiques à `webapp.py`.
- [ ] SBOM/checksums/signatures finales — checksums de l'archive faits ; SBOM (format/outil) et
  signature (clé/mécanisme) restent un choix de portée non tranché, non inventé ici
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
- Deuxième checkpoint indépendant, `7c9cd87`, à partir de l'archive `osiris-scanner-v0.3.0-7c9cd8797017.tar.gz`
  (SHA-256 `b49b40682900c5be2d04bd6d72fe5b7022231049d82e23541f051e45c3042c37`, vérifié) : `pytest -q -W error`
  (**219 passed**), `ruff check`, `ruff format --check` (58 fichiers déjà formatés), Mypy
  `--explicit-package-bases` (44 fichiers, aucun problème), `bandit` (aucun problème, 4303 lignes scannées),
  `compileall`, `uv build --offline`, `scripts/verify_package.py` sur les deux artefacts et
  `docker compose config` reproduisent tous des résultats identiques. `pip-audit` relancé (accès réseau
  utilisé pour la base de vulnérabilités PyPI) confirme aussi l'absence de CVE connue. Aucune correction
  requise ; aucun accès externe supplémentaire, push ni déploiement effectué.
