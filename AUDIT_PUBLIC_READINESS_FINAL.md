# Audit final de préparation publique — OSIRIS Scanner

**Date :** 2026-08-04

**Branche :** `feat/osiris-auxo-public-ready`

**Produit :** OSIRIS Scanner 0.3.0

**Méthodologie :** `OSIRIS-6A-2026.1`

**Statut final : PRÊT POUR PRÉSENTATION PUBLIQUE**

> Prédiagnostic technique automatisé. Ne constitue pas une certification de conformité ni un avis
> juridique.
>
> Automated technical pre-assessment. It does not constitute compliance certification or legal
> advice.

## 1. État initial constaté

Le dépôt mélangeait trois générations du produit : documentation et rapports à quatre axes,
scoring à six axes, puis modules V et L partiellement raccordés. Les constats principaux étaient :

- `report.py` contenait bien une accolade surnuméraire et ne compilait pas;
- le registre, le CLI, l’historique, la calibration, le benchmark et les rapports ne partageaient
  pas une définition canonique des axes;
- Ressources pouvait lire un contexte Lighthouse produit concurremment par Performance;
- Playwright empêchait l’enregistrement fiable de V et L quand le navigateur manquait;
- le paquet ne découvrait que `axes` et risquait d’omettre les modules racine, données et assets;
- les rendus JSON/Markdown ne représentaient pas toutes les données du scoring; le PDF et
  l’interface publique utilisable manquaient;
- l’entrée URL n’avait pas une politique SSRF complète sur les redirections et sous-ressources;
- l’ancien workflow et le script de badge SOIC visaient un composant retiré du dépôt dans
  l’historique Git;
- `osiris_cli.py` et `osiris_sec_scan.py` n’existaient pas. `scanner.py` était déjà le meilleur
  point d’entrée et a été conservé au lieu de recréer des doublons;
- l’audit et le rapport historiques affirmaient un état à quatre axes devenu faux;
- aucune interface web publique cohérente avec Auxo Systems n’était livrée.

La branche dédiée a été créée sans supprimer ni écraser le travail déjà présent. Aucun historique
n’a été réécrit.

## 2. Architecture livrée

```text
CLI `osiris` / API Python / HTTP `osiris-web`
                  │
          validation URL + DNS
                  │
      scheduler de plugins O/S/I/R/V/L
                  │
       AxisResult ou erreur explicite
                  │
 score technique + couverture + fiabilité
                  │
          modèle de rapport commun
       ├── JSON   ├── Markdown   ├── PDF
       └── interface Auxo
```

Les composants canoniques sont `scanner.py`, `url_security.py`, `axes/`, `scoring.py`,
`report.py`, `history.py`, `webapp.py`, `calibrate.py` et `benchmark/run_benchmark.py`. Le registre
porte l’ordre, le poids et les dépendances `after`; les axes prêts au même niveau sont exécutés en
parallèle.

Le SOIC privé ne fait pas partie de la distribution. Son workflow et son générateur de badge morts
ont été retirés. L’audit de février est conservé sous `docs/archive/` avec un avertissement
d’obsolescence.

## 3. Axes réellement actifs

| Clé | Libellé public | Poids | Rapide | Approfondi |
|---|---|---:|---|---|
| O | Performance | 15 % | chronométrage HTTP | navigation/rendu Playwright |
| S | Sécurité | 25 % | en-têtes + Observatory | même méthode |
| I | Intrusion | 20 % | domaines HTML + blocklist | requêtes réseau Playwright |
| R | Ressources | 10 % | poids HTML + carbone | octets transférés |
| V | Souveraineté | 15 % | DNS + hôtes HTML | IP, ASN et pays apparents |
| L | Signaux vie privée | 15 % | traceurs/liens/contrôle visibles | avant/après refus observable |

Les six axes sont exécutés, scorés, historisés, calibrés, affichés et rendus dans chaque format.
Accessibilité et SEO n’existent pas comme modules de scan : ils sont explicitement hors score et
ne sont pas simulés. L’accessibilité de l’interface elle-même est toutefois testée.

## 4. Défauts corrigés

### Cohérence et moteur

- correction de la syntaxe de `report.py` et test de non-régression par compilation;
- registre canonique à six axes avec somme des poids et dépendances validées;
- suppression du partage implicite Lighthouse O→R; R mesure ses propres données;
- scheduler déterministe par niveaux de dépendance, avec parallélisme des axes indépendants;
- distinction `complete`, `partial` et `failed`, sans transformer une erreur d’outil en score nul;
- repli profond→rapide documenté lorsque Playwright/Chromium manque;
- score technique, couverture pondérée, facteur de fiabilité et score publié bornés;
- calibration et benchmark migrés vers le moteur commun;
- historique SQLite migré sans perdre les colonnes historiques O/S/I/R;
- cache et mise à jour de blocklist couverts par tests;
- intégration Observatory v2 corrigée après reproduction réelle du HTTP 415 avec aiohttp.

### Packaging

- métadonnées 0.3.0 et dépendances séparées `core`, `deep` et `dev`;
- modules racine, packages `axes`, `blocklists`, `osiris_web`, JSON et assets statiques inclus;
- scripts `osiris` et `osiris-web` installés;
- wheel et sdist construits puis installés hors dépôt dans deux environnements vierges;
- ressources et six axes vérifiés depuis le wheel installé;
- scan rapide et trois rapports exécutés depuis ce wheel.

### Rapports et prudence juridique

- `_build_report_data` est l’unique source de vérité pour JSON, Markdown, PDF et web;
- chaque axe contient score, couverture, statut, source, observations, preuves, risques,
  recommandations, limites et erreur éventuelle;
- les axes manquants restent visibles avec score `null` et statut technique;
- avertissements FR et EN présents dans l’interface et tous les rapports;
- suppression des conclusions absolues de conformité;
- profil **Diagnostic technique Loi 25** limité à la mise en évidence de S, I, V et L, sans second
  score ni conclusion juridique;
- génération PDF réelle validée, y compris pour un scan partiel.

## 5. Décisions autonomes prises

1. Les poids existants du scoring à six axes ont été retenus comme méthodologie canonique, car ils
   totalisaient déjà 1 et correspondaient aux modules présents.
2. L’axe L a été renommé publiquement **Signaux vie privée** : il conserve sa clé de compatibilité
   mais n’est plus présenté comme un jugement légal.
3. Accessibilité et SEO restent hors score faute de modules et de méthodologie existants.
4. `scanner.py` demeure l’orchestrateur unique; aucun alias mort `osiris_cli.py` ou
   `osiris_sec_scan.py` n’a été inventé.
5. Une interface Python standard, sans framework JavaScript ni bundler, a été choisie pour réduire
   la surface et conserver un déploiement simple.
6. Le mode approfondi utilise Playwright protégé; l’ancien Lighthouse non sûr sur cible non fiable
   n’est pas réactivé.
7. Les ports publics de cible sont limités à 80/443. Le serveur de démonstration reste dans le bloc
   OSIRIS 25000–25099.
8. La version produit est fixée à 0.3.0 et le copyright public à Auxo Systems.
9. Les cibles de calibration/benchmark peu cohérentes avec la présentation ont été remplacées par
   W3C et Auxo Systems.

## 6. Interface publique créée

Le dépôt n’avait aucune interface web utilisable. `osiris-web` fournit maintenant :

- saisie URL, modes rapide/approfondi et profil général/Loi 25;
- progression par validation, six axes et rapports;
- état final explicite, incluant **scan partiel**;
- résumé, couverture, fiabilité, score, axes, priorités, observations, preuves,
  recommandations et limites dans l’ordre demandé;
- téléchargements JSON, Markdown et PDF;
- relance sans compte, cookie, analytics ni base utilisateur;
- file bornée à quatre jobs, deux workers et corps HTTP limité à 4 KiB;
- nettoyage des jobs et rapports expirés, puis du répertoire temporaire à la fin du processus;
- `GET` et `HEAD`, `/health`, API de méthodologie et en-têtes de défense.

## 7. Identité visuelle Auxo Systems

L’interface utilise un fond ivoire minéral, surfaces papier, texte charbon, vert forêt et bleu
pétrole, bordures fines, ombres discrètes et grille architecturale subtile. Le branding livré est
**OSIRIS Scanner**, **Diagnostic multidimensionnel de sites web**, **Un outil Auxo Systems**.

La revue visuelle GStack a entraîné une correction matérielle du lien d’évitement, initialement
visible hors focus. Les contrôles finaux couvrent clavier/focus visible, titres sémantiques,
`aria-live`, barre de progression, mobile 375 px, tablette 768 px, desktop 1280/1440 px,
réduction des animations, absence de débordement et console sans erreur.

## 8. Protection SSRF

`url_security.py` applique les contrôles suivants aux accès de cible :

- HTTP/HTTPS seulement, sans identifiants intégrés;
- ports 80/443 seulement en politique publique;
- refus des hôtes localhost/métadonnées et de toute IP non globale;
- refus loopback, privé, link-local, réservé, multicast, non spécifié et métadonnées cloud;
- refus d’une réponse DNS mixte public/privé;
- nouvelle résolution contrôlée au moment de la connexion, sans cache d’autorisation;
- redirections manuelles revalidées, maximum cinq;
- interception et revalidation de chaque navigation/sous-ressource Playwright;
- service workers bloqués;
- 30 s par requête, 180 s globales et 5 MiB par réponse;
- aucun accès `file:`, `ftp:`, `javascript:` ou implicite au système de fichiers.

Les tests couvrent aussi redirection vers privé, rebinding simulé, port interdit, réponse lente,
réponse trop grande et schéma navigateur non HTTP. Les essais live ont refusé `file:` et
`javascript:` en HTTP 400, puis l’adresse 169.254.169.254 comme cible non publique.

## 9. Fonctionnement des rapports

Le scan Docker approfondi final de `https://example.com` a produit :

- état `complete`, 6/6 axes;
- score publié 6,8/10, score technique 7,0/10;
- couverture 86,8 %, facteur de fiabilité 0,967;
- JSON valide, Markdown UTF-8 et PDF 1.4 de trois pages.

Le scénario sans navigateur a produit un scan `partial`, six résultats de repli, couverture 68,5 %
et trois rapports valides. Les causes Playwright sont conservées dans `failed_axes`,
`degraded_from` et les limites, sans résultat approfondi fabriqué.

## 10. Tests ajoutés ou renforcés

La suite couvre :

- compilation/import de tous les modules publics et régression de l’accolade `report.py`;
- registre exact O/S/I/R/V/L, ordre, poids et dépendances;
- scoring complet, partiel, fiabilité et statuts non juridiques;
- parité JSON/Markdown/PDF, avertissements et axes absents;
- CLI, modes rapide/approfondi, repli, historique et migration quatre→six axes;
- cache, blocklist et mise à jour de blocklist;
- serveur local : HTML simple, en-têtes faibles, traceur, JavaScript, redirections, lenteur,
  taille excessive et erreurs HTTP;
- URL invalide, DNS inexistant, cible inaccessible, métadonnées cloud et SSRF complet;
- ordonnanceur : parallélisme, séquençage et absence de course O/R;
- interface, CSP, accessibilité statique, HEAD, état partiel, nettoyage temporaire et trois
  téléchargements;
- prudence juridique FR/EN et absence de conclusions absolues.

Résultat final : **192 tests réussis en 19,62 secondes**.

## 11. Résultats exacts des validations

| Commande ou contrôle | Résultat |
|---|---|
| `python -m compileall` | réussi |
| `pytest -q` | 192 réussis, 0 échec, 19,62 s |
| `ruff check .` | réussi, 0 constat |
| `ruff format --check .` | réussi |
| `mypy .` | réussi, 37 fichiers source |
| `bandit` sur les sources | réussi, 0 constat |
| `pip-audit` | aucune vulnérabilité connue; paquet local non publié ignoré |
| `radon cc` | 159 blocs, moyenne A (4,553) |
| `radon mi` | A partout sauf `scanner.py` B |
| `python -m build` | wheel + sdist 0.3.0 réussis |
| installation editable | OSIRIS 0.3.0, dépôt courant |
| installation wheel vierge | réussie, ressources/CLI/web/scan validés |
| installation sdist vierge | réussie, imports/CLI validés |
| CLI wheel vierge | scan rapide réel + 3 rapports |
| `calibrate.py` | 5/5 sites, 0 échec, 6 axes par site |
| benchmark rapide | 8/8 sites, 0 échec, 6 axes par site |
| `docker compose config` | valide |
| build Docker final | réussi, image `sha256:8dfaf3…`, 558 777 533 octets |
| santé Docker | HTTP 200, OSIRIS 0.3.0 |
| sécurité conteneur | UID 10001, lecture seule, `no-new-privileges` |
| scan Docker rapide | complet, 6/6 axes |
| scan Docker approfondi | complet, 6/6 axes, couverture 86,8 % |
| GStack Browser | console propre, aucun débordement, focus résultat, 3 téléchargements |
| recherche manuelle de secrets | aucun candidat dans l’arbre, aucun motif critique historique |
| Gitleaks | indisponible sur la machine, donc non exécuté |

Il n’existe aucun projet npm : les contrôles npm, lint/typecheck/build JavaScript et audit npm ne
s’appliquent pas. Le JavaScript livré est un asset statique sans dépendance externe.

## 12. Fichiers modifiés

### Moteur et données

`scanner.py`, `scoring.py`, `report.py`, `history.py`, `cache.py`, `url_security.py`, `utils.py`,
`calibrate.py`, `blocklist_updater.py`, `axes/__init__.py`, `axes/performance.py`,
`axes/security.py`, `axes/intrusion.py`, `axes/resource.py`, `axes/sovereignty.py`,
`axes/legal.py`, `blocklists/__init__.py`, `calibration/sites.txt`,
`calibration/results.json`, `benchmark/inputs/urls.txt`, `benchmark/run_benchmark.py`.

### Interface, distribution et automatisation

`webapp.py`, `osiris_web/__init__.py`, `osiris_web/static/index.html`,
`osiris_web/static/styles.css`, `osiris_web/static/app.js`, `pyproject.toml`, `Dockerfile`,
`docker-compose.yml`, `.dockerignore`, `.gitignore`, `.github/workflows/ci.yml`, `LICENSE`.

Le workflow `.github/workflows/soic-gate.yml` et `scripts/update_badge.py` obsolètes sont supprimés.

### Tests

`tests/conftest.py`, `tests/test_blocklist_updater.py`, `tests/test_cache.py`,
`tests/test_history.py`, `tests/test_integration.py`, `tests/test_intrusion.py`,
`tests/test_performance.py`, `tests/test_quality_contract.py`, `tests/test_registry.py`,
`tests/test_resource.py`, `tests/test_scanner.py`, `tests/test_scoring.py`,
`tests/test_security.py`, `tests/test_url_security.py`, `tests/test_utils.py`,
`tests/test_webapp.py`.

### Documentation et preuves

`README.md`, `RAPPORT_PROJET_OSIRIS.md`, `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`,
`docs/SECURITY.md`, `docs/DEVELOPMENT.md`, `docs/archive/AUDIT_COMPLET_2026-02-17.md`,
`docs/public-readiness-evidence/` et ce rapport. L’ancien audit racine est déplacé vers l’archive.

## 13. Preuves produites

Le dossier `docs/public-readiness-evidence/` contient :

- écran initial, progression, résultat complet et résultat partiel;
- vues mobile, tablette et desktop;
- exemple complet JSON/Markdown/PDF;
- exemple partiel JSON/Markdown/PDF;
- empreintes SHA-256;
- résumé exact des commandes et résultats de validation.

## 14. Limites restantes

- Les services Observatory, Green Web Foundation, Website Carbon et ipwho.is restent externes et
  peuvent réduire la couverture sans invalider les preuves locales.
- La géolocalisation IP, le modèle carbone et les blocklists sont indicatifs.
- L’automatisation d’une bannière de consentement ne couvre pas toutes les langues et interfaces.
- Les fonctions dynamiques principales de `scanner.py` restent plus complexes que la moyenne
  (maintenabilité B), sans défaut fonctionnel ou alerte statique observé.
- L’image Docker fait environ 559 Mo, principalement à cause de Chromium et de ses bibliothèques.
- Avant une exposition Internet permanente, ajouter TLS, isolation réseau d’infrastructure,
  limitation par IP et observabilité au niveau reverse proxy. L’interface actuelle est une
  démonstration publique mono-instance, pas une plateforme multi-tenant.
- Cet audit de sécurité automatisé ne remplace pas un audit professionnel, un pentest ni une revue
  juridique.

## 15. Blocages externes

- Gitleaks n’est pas installé. La recherche de secrets a été remplacée par une recherche de motifs
  dans l’arbre et l’historique, sans candidat trouvé.
- Python 3.11 n’est pas installé sur cette machine; la validation locale complète a été faite sous
  Python 3.12.3. Le workflow CI configure 3.11 et 3.12, mais n’a pas été exécuté à distance puisqu’il
  n’y a eu ni push ni ouverture de PR.
- Le paquet GStack `review` installé référence deux fichiers absents de son bundle. Une revue
  directe du diff et `git diff --check` ont été exécutés à la place.
- Aucun push, déploiement, merge ou publication de paquet n’a été effectué, conformément aux
  restrictions de la mission.

Aucun de ces points ne bloque le parcours local de présentation, le moteur, les rapports ou la
sécurité d’URL.

## 16. Statut final

**PRÊT POUR PRÉSENTATION PUBLIQUE**

Le moteur s’installe, le CLI et l’interface fonctionnent, les six axes sont cohérents, les rapports
sont réels, les scans complets et partiels sont démontrés, les URL sont protégées, la suite qualité
est verte et les limites sont visibles. Ce statut autorise une présentation publique contrôlée; il
ne constitue ni une autorisation de déploiement Internet permanent ni une certification juridique
ou de sécurité.
