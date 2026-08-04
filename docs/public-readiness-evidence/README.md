# Preuves de préparation publique — 2026-08-04

Ce dossier contient des sorties produites par le code de la branche
`feat/osiris-auxo-public-ready`. Les URL de démonstration sont publiques et ne contiennent aucune
donnée personnelle ni aucun secret.

## Captures

| Fichier | Preuve |
|---|---|
| `01-initial-desktop.png` | écran initial Auxo, formulaire et avertissement juridique |
| `02-scan-in-progress.png` | mode approfondi en cours |
| `03-result-desktop.png` | résultat approfondi complet, six axes et profil Loi 25 |
| `04-result-partial.png` | Chromium volontairement indisponible, repli explicite et scan partiel |
| `initial-responsive-*.png` | écran initial à 375×812, 768×1024 et 1280×720 |
| `result-responsive-*.png` | résultat aux mêmes trois tailles |

Les captures ont été générées avec GStack Browser contre l’interface locale. Le parcours final ne
produit aucune erreur console, conserve le focus sur `#results` et ne présente aucun débordement
horizontal aux tailles testées.

## Rapports réels

`example-report/example.com_15560114468842e1bbdba73487a362ae.*` vient du scan Docker
approfondi post-révision de `https://example.com` : état `complete`, 6/6 axes, score publié 6,4/10
et couverture 86,8 %. Chromium a reçu chaque réponse par le relais SSRF borné. Les trois formats
partagent le même identifiant de scan et le même modèle en mémoire. Les fichiers
`osiris-example-deep.*` conservent la preuve antérieure à titre de comparaison.

`partial-report/` vient du même parcours avec
`PLAYWRIGHT_BROWSERS_PATH=/tmp/osiris-browser-intentionally-unavailable` : état `partial`, six
mesures rapides de repli, score 6,2/10, couverture 68,5 % et cause technique conservée.

Empreintes SHA-256 :

```text
b5bb672a26394186da5ee2a58a02fa575270dd52653cf0f4f8016f50c9bd19a6  example-report/example.com_15560114468842e1bbdba73487a362ae.json
fdb2c94c864917c884be29560c9e9f3459544a75f5c30b583022c09b39093b2f  example-report/example.com_15560114468842e1bbdba73487a362ae.md
491ef3769b9d864bf2e60afead88e207894d39f06fd9567bb7e4fa1868b40cec  example-report/example.com_15560114468842e1bbdba73487a362ae.pdf
20d092998feb8b25843adf19af80aa247193dfcc65e5a120a011a321f1e6b3f5  example-report/osiris-example-deep.json
8e974ed945853fdfed7ed0c23df31595ef400575bff66fc3ed83f4d1e677a596  example-report/osiris-example-deep.md
48b59b6ef9c08d9911fdbe6423ca5d864dd34ed9590a796860b1822a0629deaa  example-report/osiris-example-deep.pdf
92b6e874b6235b289d5ed06db7a469c784806400150ce44d0a8b7c7347d36d34  partial-report/example.com_2026-08-04.json
90b823d6e2d66ab4f3b77ffa4cd8ec1c7adaeae075b4a7d2ee6741d6384cb88d  partial-report/example.com_2026-08-04.md
75e109df5675077405ed0bcf3080a522d83d025200f19843945c714527814428  partial-report/example.com_2026-08-04.pdf
```

## Résultats de validation

| Validation | Résultat exact |
|---|---|
| compilation Python | OK, tous les fichiers livrés |
| pytest | 214 réussis en 27,75 s |
| Ruff lint + format | réussi, 0 erreur |
| Mypy | réussi, 39 fichiers source |
| Bandit | réussi, 0 constat |
| pip-audit | aucune vulnérabilité connue; paquet local OSIRIS non publié donc ignoré |
| Radon | complexité moyenne A, 4,654; maintenabilité A sauf `scanner.py` et `webapp.py` B |
| build Python | wheel et sdist 0.3.0 créés |
| installation wheel vierge | imports, ressources, CLI, web et scan rapide réussis |
| installation sdist vierge | imports et CLI réussis |
| installation editable | OSIRIS 0.3.0 chargé depuis ce dépôt |
| CLI vierge | scan rapide réel et trois rapports réussis |
| calibration | 5/5 cibles, six axes, aucun échec |
| benchmark rapide | 8/8 cibles, six axes, aucun échec |
| Dockerfile | image construite depuis la base Python épinglée par digest |
| docker-compose | configuration valide, service sain sur 25000 |
| conteneur | UID 10001, racine en lecture seule, 1 GiB, 2 CPU, 256 PID, `no-new-privileges` |
| scan Docker approfondi | complet, 6/6 axes, 6,4/10, couverture 86,8 % |
| rapports Docker | JSON, Markdown et PDF téléchargeables |
| interface | console propre, responsive, focus résultat, 6 axes, 3 téléchargements |
| audit de dépendances | aucune vulnérabilité connue |
| recherche de secrets | aucune candidate dans l’arbre ni motif critique dans l’historique |
| Gitleaks | non installé sur la machine; non exécuté |

L’application n’a pas de gestionnaire JavaScript ni de dépendance npm : lint, typecheck, audit et
build npm ne s’appliquent pas à cette interface statique sans bundler.

> Prédiagnostic technique automatisé. Ne constitue pas une certification de conformité ni un avis
> juridique.
