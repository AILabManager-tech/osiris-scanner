# RAPPORT COMPLET — PROJET OSIRIS SCANNER

**Date** : 7 fevrier 2026
**Version** : 0.1.0
**Statut** : COMPLET — 6 sprints livres et valides
**Environnement** : Ubuntu Linux 6.17, Python 3.12.3, Node.js 18+, Chrome 144, Lighthouse 13.0.1

---

## Table des matieres

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture technique](#2-architecture-technique)
3. [Formule de scoring](#3-formule-de-scoring)
4. [Detail des 4 axes](#4-detail-des-4-axes)
5. [Deroulement des sprints](#5-deroulement-des-sprints)
6. [Resultats de calibration](#6-resultats-de-calibration)
7. [Suite de tests](#7-suite-de-tests)
8. [Problemes rencontres et solutions](#8-problemes-rencontres-et-solutions)
9. [Limites connues](#9-limites-connues)
10. [Evolutions futures](#10-evolutions-futures)
11. [Arborescence finale](#11-arborescence-finale)

---

## 1. Vue d'ensemble

### Qu'est-ce qu'OSIRIS ?

OSIRIS (Operational Site Inspection & Rating Information System) est un scanner composite qui mesure la **sante operationnelle** d'un site web sur une echelle de 0 a 10. Il agrege les resultats d'outils tiers sur 4 axes :

| Lettre | Axe | Mesure |
|--------|-----|--------|
| **O** | Performance | Core Web Vitals via Lighthouse CLI |
| **S** | Security | Grade Mozilla Observatory + Headers HTTP |
| **I** | Intrusion | Detection de trackers via blocklist |
| **R** | Resource | Poids page + empreinte carbone (Website Carbon API) |

OSIRIS **agrege, il ne certifie pas**. Chaque axe s'appuie sur un outil tiers reconnu.

### Philosophie

- **Transparence** : formule de scoring publique et documentee
- **Outils tiers** : aucune metrique proprietaire, tout est verifiable
- **Rapports actionnables** : recommandations concretes par axe
- **Eco-responsabilite** : l'axe Resource mesure l'empreinte carbone

---

## 2. Architecture technique

### Arborescence du projet

```
osiris-scanner/
├── scanner.py              # Orchestrateur principal (CLI Click)
├── scoring.py              # Agregation ponderee (formule publique)
├── report.py               # Generation rapports JSON + Markdown
├── calibrate.py            # Script de calibration multi-sites
├── axes/
│   ├── __init__.py
│   ├── performance.py      # Axe O — Wrapper Lighthouse CLI
│   ├── security.py         # Axe S — Mozilla Observatory + Headers HTTP
│   ├── intrusion.py        # Axe I — Detection trackers via blocklist
│   └── resource.py         # Axe R — Poids page + Website Carbon API
├── blocklists/
│   └── trackers.json       # 110+ domaines de tracking connus
├── calibration/
│   ├── sites.txt           # 5 sites de reference
│   └── results.json        # Resultats de calibration
├── reports/                # Rapports generes (JSON + Markdown)
├── tests/
│   ├── test_performance.py # 14 tests
│   ├── test_security.py    # 19 tests
│   ├── test_intrusion.py   # 25 tests
│   ├── test_resource.py    # 20 tests
│   ├── test_scoring.py     # 16 tests
│   └── test_integration.py #  6 tests
├── pyproject.toml
└── README.md
```

### Stack technique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| Langage | Python | 3.12.3 |
| Performance | Lighthouse CLI | 13.0.1 |
| Navigateur | Google Chrome (headless) | 144 |
| HTTP | requests | >= 2.31 |
| CLI | click | >= 8.1 |
| Terminal | rich | >= 13.0 |
| Tests | pytest + pytest-asyncio | >= 7.0 / >= 0.21 |
| Linter | ruff | 0.15.0 |

### Dependances externes (APIs)

| API | Usage | Endpoint |
|-----|-------|----------|
| Mozilla Observatory v2 | Grades securite | `POST https://observatory-api.mdn.mozilla.net/api/v2/scan?host=<domain>` |
| Website Carbon API | Estimation gCO2 | `GET https://api.websitecarbon.com/data?bytes=X&green=0` |
| Green Web Foundation | Hebergement vert | `GET https://api.thegreenwebfoundation.org/api/v3/greencheck/<domain>` |

### Dataclass centrale

Tous les axes retournent un `AxisResult` standardise (defini dans `axes/performance.py`) :

```python
@dataclass
class AxisResult:
    score: float                            # 0.0 a 10.0
    details: dict[str, Any] = field(...)    # Donnees specifiques a l'axe
    tool_used: str = ""                     # Nom de l'outil source
    raw_output: Any = None                  # Sortie brute (debug)
```

---

## 3. Formule de scoring

### Formule publique

```
μ_osiris = Performance × 0.20 + Security × 0.30 + Intrusion × 0.30 + Resource × 0.20
```

### Ponderations

| Axe | Poids | Justification |
|-----|------:|---------------|
| O — Performance | 20% | Qualite de l'experience utilisateur |
| S — Security | 30% | Protection des utilisateurs (priorite haute) |
| I — Intrusion | 30% | Respect de la vie privee (priorite haute) |
| R — Resource | 20% | Eco-responsabilite et sobriete |

**Total = 100%** — Invariant verifie par les tests unitaires.

### Grades

| Score | Grade | Signification |
|------:|-------|---------------|
| 9.0 - 10.0 | Exemplaire | Site modele sur tous les axes |
| 7.0 - 8.9 | Conforme | Bon niveau general, ameliorations mineures possibles |
| 5.0 - 6.9 | A risque | Faiblesses significatives sur un ou plusieurs axes |
| 0.0 - 4.9 | Critique | Deficiences majeures, action corrective urgente |

---

## 4. Detail des 4 axes

### 4.1 Axe O — Performance (`axes/performance.py`)

**Outil** : Google Lighthouse CLI v13.0.1
**Methode** : Execution Chrome headless via `asyncio.create_subprocess_exec`
**Timeout** : 60 secondes

**Processus** :
1. Localise l'executable `lighthouse` via `shutil.which`
2. Lance Lighthouse avec les flags : `--output=json`, `--chrome-flags=--headless=new --no-sandbox --disable-gpu`, `--quiet`
3. Parse le rapport JSON temporaire
4. Extrait le score global (0-100) et les metriques Core Web Vitals
5. Normalise : `score_osiris = score_lighthouse / 100 × 10`

**Metriques extraites** :
- First Contentful Paint (FCP)
- Largest Contentful Paint (LCP)
- Total Blocking Time (TBT)
- Cumulative Layout Shift (CLS)
- Speed Index

**Normalisation** : Score Lighthouse 0-100 → Score OSIRIS 0-10 (division simple avec clamping)

---

### 4.2 Axe S — Security (`axes/security.py`)

**Outils** : Mozilla Observatory API v2 (70%) + Analyse headers HTTP (30%)
**Methode** : Appels HTTP paralleles via `asyncio.run_in_executor`
**Timeouts** : Observatory 30s, Headers 15s

**Processus** :
1. Extrait le domaine de l'URL
2. Lance en parallele :
   - `POST` vers Observatory API v2 (`observatory-api.mdn.mozilla.net`)
   - `HEAD` (puis `GET` en fallback) vers l'URL pour recuperer les headers
3. Convertit le grade Observatory (A+ → 10.0, F → 1.5)
4. Analyse 6 headers de securite avec poids differencies
5. Combine : `score = observatory × 0.70 + headers × 0.30`

**Headers de securite verifies** :

| Header | Poids |
|--------|------:|
| Strict-Transport-Security | 1.0 |
| Content-Security-Policy | 1.0 |
| X-Frame-Options | 0.5 |
| X-Content-Type-Options | 0.5 |
| Referrer-Policy | 0.5 |
| Permissions-Policy | 0.5 |

**Mapping grade → score** : A+ (10.0), A (9.5), A- (9.0), B+ (8.5), B (8.0), B- (7.5), C+ (7.0), C (6.0), C- (5.5), D+ (5.0), D (4.0), D- (3.0), F (1.5)

---

### 4.3 Axe I — Intrusion (`axes/intrusion.py`)

**Outil** : OSIRIS Blocklist Analysis (110+ domaines)
**Methode** : Parsing HTML statique + comparaison a la blocklist
**Timeout** : 30 secondes

**Processus** :
1. Charge la blocklist depuis `blocklists/trackers.json`
2. Recupere le HTML de la page
3. Extrait les domaines via 4 patterns regex :
   - `src="..."` / `href="..."`
   - `url(...)` (CSS)
   - URLs absolues (`https://...`)
4. Classifie chaque domaine : 1st-party, 3rd-party, ou tracker
5. Calcule un score inverse : `score = 10 × (1 - trackers / 15)`

**Scoring** :
- 0 tracker detecte = 10.0/10
- 15+ trackers detectes = 0.0/10
- Interpolation lineaire entre les deux

**Blocklist** : 110+ domaines issus de Disconnect.me, EasyPrivacy, uBlock Origin. Inclut Google Analytics, Meta Pixel, TikTok, HotJar, Mixpanel, Amplitude, Segment, FullStory, HubSpot, Intercom, Criteo, Taboola, Outbrain, etc.

---

### 4.4 Axe R — Resource (`axes/resource.py`)

**Outils** : Mesure poids page + Website Carbon API + Green Web Foundation
**Methode** : Appels HTTP sequentiels/paralleles via `asyncio.run_in_executor`
**Timeouts** : Page 30s, API Carbon 15s

**Processus** :
1. Recupere la page et mesure le poids en octets
2. Compte les ressources HTML (`<script src>`, `<link href>`, `<img src>`, etc.)
3. Verifie l'hebergement vert via Green Web Foundation API
4. Appelle Website Carbon API (`/data?bytes=X&green=0|1`)
5. Si API indisponible → fallback local SWD v4 (`0.000000442 gCO2/byte`)
6. Calcule le score par interpolation lineaire du poids

**Scoring** :
- <= 500 KB = 10.0/10
- >= 5 MB = 0.0/10
- Interpolation lineaire entre les deux

**Donnees retournees** :
- Poids page (octets et KB)
- Nombre de ressources HTML
- gCO2 estime
- Hebergement vert (oui/non)
- Rating carbone (A+, A, B, C, D, E, F)
- Percentile (`cleaner_than`)

---

## 5. Deroulement des sprints

### Sprint 0 — Scaffold + Axe O (Performance)

**Objectif** : Creer la structure du projet et implementer le premier axe.

**Livrables** :
- `pyproject.toml` avec dependances et configuration ruff/pytest
- `axes/performance.py` — Wrapper Lighthouse CLI complet
- `scanner.py` — Orchestrateur CLI (1 axe)
- `tests/test_performance.py` — 14 tests unitaires
- Fichiers de pilotage `.claude/osiris/` (CLAUDE.md, STATE.md, RULES.md, SPRINTS.md)

**Critere de succes** : `pytest tests/test_performance.py -v` → 14 PASS
**Statut** : COMPLETE

---

### Sprint 1 — Axe S (Security)

**Objectif** : Implementer l'analyse de securite via Observatory + headers.

**Livrables** :
- `axes/security.py` — Observatory API v2 + headers HTTP
- `tests/test_security.py` — 19 tests unitaires
- `scanner.py` mis a jour (2 axes)

**Critere de succes** : `pytest tests/ -v` → 33 PASS
**Statut** : COMPLETE

---

### Sprint 2 — Axe I (Intrusion)

**Objectif** : Implementer la detection de trackers par blocklist.

**Livrables** :
- `blocklists/trackers.json` — 110+ domaines de tracking
- `axes/intrusion.py` — Parsing HTML + classification
- `tests/test_intrusion.py` — 25 tests unitaires
- `scanner.py` mis a jour (3 axes)

**Critere de succes** : `pytest tests/ -v` → 58 PASS
**Statut** : COMPLETE

---

### Sprint 3 — Axe R (Resource)

**Objectif** : Implementer la mesure du poids page et de l'empreinte carbone.

**Livrables** :
- `axes/resource.py` — Poids + Carbon API + Greencheck + fallback SWD v4
- `tests/test_resource.py` — 20 tests unitaires
- `scanner.py` mis a jour (4 axes)

**Critere de succes** : `pytest tests/ -v` → 78 PASS
**Statut** : COMPLETE

---

### Sprint 4 — Scoring + Report

**Objectif** : Implementer la formule d'agregation et la generation de rapports.

**Livrables** :
- `scoring.py` — Formule, grades, poids comme constantes nommees
- `report.py` — Rapports JSON structures + Markdown lisibles
- `tests/test_scoring.py` — 16 tests unitaires
- `scanner.py` mis a jour (option `--output report`)

**Critere de succes** : `pytest tests/ -v` → 94 PASS
**Statut** : COMPLETE

---

### Sprint 5 — Tests + Calibration

**Objectif** : Tests d'integration end-to-end et calibration sur sites reels.

**Livrables** :
- `tests/test_integration.py` — 6 tests d'integration
- `calibrate.py` — Script de calibration multi-sites
- `calibration/sites.txt` — 5 sites de reference
- `calibration/results.json` — Resultats de calibration
- `README.md` — Documentation complete

**Critere de succes** : `pytest tests/ -v` → 100 PASS, `ruff check` → 0 erreurs
**Statut** : COMPLETE

---

## 6. Resultats de calibration

### Tableau comparatif

Calibration executee le 7 fevrier 2026 sur 5 sites de reference.

| Site | O (Perf) | S (Sec) | I (Intru) | R (Ress) | OSIRIS | Grade |
|------|:--------:|:-------:|:---------:|:--------:|:------:|:-----:|
| **gov.uk** | 7.6 | 10.0 | 10.0 | 10.0 | **9.5** | Exemplaire |
| **wikipedia.org** | 5.9 | 4.9 | 10.0 | 10.0 | **7.7** | Conforme |
| **google.com** | 3.5 | 5.3 | 10.0 | 10.0 | **7.3** | Conforme |
| **example.com** | 10.0 | 1.0 | 10.0 | 10.0 | **7.3** | Conforme |
| **motherfuckingwebsite.com** | 9.1 | 1.0 | 10.0 | 10.0 | **7.1** | Conforme |

### Analyse des resultats

**gov.uk (9.5 — Exemplaire)** : Reference absolue. Seul site avec un grade Observatory A+ (score 120/100). Tous les 6 headers de securite presents. 10/10 tests Observatory reussis. Performance correcte (76/100 Lighthouse) penalisee par un CLS eleve (0.565). Page legere (83 KB, 17 ressources). Zero tracker.

**wikipedia.org (7.7 — Conforme)** : Bonne structure mais securite perfectible. Observatory grade C (50/100). Seul le header HSTS est present (5/6 manquants). Performance moyenne (59/100) avec un FCP lent (7.0s). Page legere (190 KB) et aucun tracker. 362 domaines references (sous-domaines multilingues).

**google.com (7.3 — Conforme)** : Performance faible en headless (35/100, LCP 9.6s) car le site est optimise pour le rendu navigateur reel. Observatory C+ (60/100). Seul X-Frame-Options present (5/6 headers manquants). Page ultra-legere (18 KB). **Zero tracker detecte dans le HTML statique** — limitation connue : les trackers Google sont charges dynamiquement par JS.

**example.com (7.3 — Conforme)** : Performance parfaite (100/100, page minimale de 513 octets). Aucune securite configuree (Observatory F, 0 header). Zero tracker. Score plombe uniquement par l'axe S.

**motherfuckingwebsite.com (7.1 — Conforme)** : Memes caracteristiques qu'example.com. Excellente performance (91/100). Zero securite. Page minimale (4.9 KB). Zero tracker.

### Coherence observee

Les resultats montrent une coherence attendue :
- Les sites gouvernementaux (gov.uk) excellent en securite
- Les sites minimalistes (example.com, motherfuckingwebsite.com) excellent en performance et resource mais echouent en securite
- Les sites complexes (google.com) ont des performances degradees en mode headless
- L'axe I donne 10/10 partout car le HTML statique ne revele pas les trackers JS

---

## 7. Suite de tests

### Vue d'ensemble

**100 tests au total** — tous PASS
**0 erreurs ruff** — linter propre

| Fichier de test | Nb tests | Couverture |
|----------------|:--------:|------------|
| `test_performance.py` | 14 | Normalisation, parsing JSON, scan mock, erreurs |
| `test_security.py` | 19 | Grade→score, extraction host, headers, scan mock |
| `test_intrusion.py` | 25 | Blocklist, extraction domaines, trackers, classification, scoring |
| `test_resource.py` | 20 | Score interpolation, ressources, carbone local, scan mock, fallback |
| `test_scoring.py` | 16 | Formule, poids, grades (toutes bornes), axes manquants |
| `test_integration.py` | 6 | Pipeline complet, rapports JSON/MD, extremes, coherence |

### Details des tests d'integration

1. **test_scoring_pipeline** : 4 axes mock → score 7.5, grade Conforme (calcul verifie manuellement)
2. **test_json_report_generation** : Verification structure JSON (score, grade, url, formula, 4 axes, recommendations)
3. **test_markdown_report_generation** : Verification hierarchie H1→H2→H3, tableau, formule, recommandations
4. **test_full_pipeline_extreme_good** : 4 axes a 10.0 → score 10.0, grade Exemplaire
5. **test_full_pipeline_extreme_bad** : 4 axes a 0.0 → score 0.0, grade Critique
6. **test_report_data_consistency** : Coherence entre rapport JSON et Markdown (memes valeurs)

### Strategie de test

- **Mocking systematique** : Toutes les requetes HTTP et appels subprocess sont mockes via `unittest.mock.patch`
- **Mode pytest-asyncio auto** : Configure dans `pyproject.toml` (`asyncio_mode = "auto"`)
- **Bornes testees** : Valeurs extremes (0, max), valeurs limites (seuils de grades), cas nominaux
- **Absence de tests live** : Les tests ne font aucun appel reseau reel

---

## 8. Problemes rencontres et solutions

### Chrome 144 — Flag headless

**Probleme** : Chrome 144+ ne supporte plus `--headless` classique.
**Solution** : Utilisation de `--headless=new` dans les flags Chrome de Lighthouse.
**Fichier** : `axes/performance.py:137`

### Wikipedia — Blocage requetes HEAD

**Probleme** : Wikipedia retourne HTTP 403 pour les requetes HEAD sans User-Agent.
**Solution** : Fallback GET avec `stream=True` + header `User-Agent: OSIRIS-Scanner/0.1 (Security Audit)`.
**Fichier** : `axes/security.py:120-136`

### Website Carbon API — Endpoint deprecie

**Probleme** : L'endpoint `/site` est deprecie depuis juillet 2025.
**Solution** : Migration vers `/data?bytes=X&green=0|1` avec fallback local SWD v4 si l'API est down.
**Fichier** : `axes/resource.py:151-171`

### Mozilla Observatory — Migration MDN

**Probleme** : L'ancienne API Observatory (`observatory.mozilla.org`) a ete migree vers MDN.
**Solution** : Utilisation du nouvel endpoint `observatory-api.mdn.mozilla.net/api/v2/scan`.
**Fichier** : `axes/security.py:19`

### PEP 668 — pip install sur Ubuntu

**Probleme** : Ubuntu moderne refuse `pip install` sans environnement virtuel.
**Solution** : Utilisation du flag `--break-system-packages` pour l'installation globale.

### ruff — Multiples corrections

| Regle | Description | Correction |
|-------|-------------|------------|
| UP041 | `asyncio.TimeoutError` deprecie | Remplace par `TimeoutError` builtin |
| B904 | `raise` sans `from` | Ajout de `from None` / `from e` |
| I001 | Ordre des imports | `ruff check --fix` |
| SIM117 | `with` imbrique | Context managers parentheses |
| F401 | Import inutilise | Suppression |
| F541 | f-string sans placeholder | Suppression du prefixe `f` |
| E501 | Ligne trop longue | Concatenation parenthesee |

---

## 9. Limites connues

### Axe O (Performance)

- Lighthouse en mode headless peut donner des scores differents d'un navigateur reel
- Certains sites bloquent Chrome headless (erreur NO_FCP)
- Les scores Lighthouse varient naturellement entre executions (~10% de variance)
- Le site marksystem.ca est injoignable depuis cet environnement

### Axe S (Security)

- Mozilla Observatory cache les resultats 24h ; un re-scan immediat retourne le cache
- L'analyse des headers verifie la presence/absence, pas la qualite de la configuration
- Certains serveurs bloquent les requetes HEAD (necessite fallback GET)

### Axe I (Intrusion) — LIMITATION MAJEURE

- **L'analyse est basee sur le HTML statique uniquement**
- Les trackers charges dynamiquement par JavaScript ne sont pas detectes
- Cela explique les scores de 10/10 meme pour des sites connus pour leur tracking (ex: Google)
- La blocklist couvre 110+ domaines mais n'est pas exhaustive

### Axe R (Resource)

- Le poids mesure est celui du HTML principal uniquement (pas les ressources chargees dynamiquement)
- L'API Website Carbon `/site` est depreciee ; on utilise `/data` avec le poids calcule
- L'estimation gCO2 est approximative (modele SWD v4)

### General

- OSIRIS mesure la sante operationnelle, pas la qualite du contenu
- Le scanner necessite un acces reseau aux APIs externes
- Rate limiting : 1 scan Observatory par domaine toutes les 60 secondes

---

## 10. Evolutions futures

### Priorite haute

1. **Analyse dynamique (Axe I)** : Integrer Puppeteer ou Playwright pour capturer les requetes reseau reelles et detecter les trackers charges par JavaScript. Cela resoudrait la limitation majeure actuelle.

2. **Initialisation Git** : Creer le depot Git avec le premier commit et eventuellement publier sur GitHub.

### Priorite moyenne

3. **Mode concurrent** : Scanner les 4 axes en parallele (actuellement sequentiel) pour reduire le temps de scan total.

4. **Cache intelligent** : Mettre en cache les resultats Observatory (24h) et Carbon API pour eviter les appels redondants.

5. **Support multi-pages** : Scanner plusieurs pages d'un meme site (pas seulement la page d'accueil).

### Priorite basse

6. **Interface web** : Dashboard HTML avec graphiques pour visualiser les resultats.

7. **Export PDF** : Generation de rapports PDF en plus de JSON/Markdown.

8. **Historique** : Base de donnees locale pour suivre l'evolution des scores dans le temps.

9. **Mise a jour automatique de la blocklist** : Synchronisation periodique avec les sources amont (Disconnect.me, EasyPrivacy).

---

## 11. Arborescence finale

```
osiris-scanner/
├── scanner.py              # 157 lignes — CLI Click, orchestration des 4 axes
├── scoring.py              #  94 lignes — Formule, grades, constantes
├── report.py               # 320 lignes — Rapports JSON + Markdown
├── calibrate.py            # 121 lignes — Calibration multi-sites
├── axes/
│   ├── __init__.py
│   ├── performance.py      # 182 lignes — Lighthouse CLI wrapper
│   ├── security.py         # 244 lignes — Observatory + Headers
│   ├── intrusion.py        # 263 lignes — Blocklist + HTML parsing
│   └── resource.py         # 282 lignes — Poids + Carbon + SWD v4
├── blocklists/
│   └── trackers.json       # 110+ domaines (Disconnect, EasyPrivacy, uBlock)
├── calibration/
│   ├── sites.txt           # 5 URLs de reference
│   └── results.json        # Resultats calibration 2026-02-07
├── reports/                # Rapports generes
├── tests/
│   ├── test_performance.py # 14 tests
│   ├── test_security.py    # 19 tests
│   ├── test_intrusion.py   # 25 tests
│   ├── test_resource.py    # 20 tests
│   ├── test_scoring.py     # 16 tests
│   └── test_integration.py #  6 tests
├── pyproject.toml          # Config projet, deps, ruff, pytest
└── README.md               # Documentation complete
```

---

## Resume final

| Metrique | Valeur |
|----------|--------|
| Sprints completes | 6/6 |
| Tests unitaires + integration | 100 PASS |
| Erreurs ruff | 0 |
| Sites calibres | 5 |
| Domaines dans la blocklist | 110+ |
| Axes implementes | 4/4 |
| Fichiers source Python | 8 |
| Fichiers de test | 6 |

**OSIRIS Scanner v0.1.0 est fonctionnel et pret a l'emploi.**

---

*Rapport genere le 7 fevrier 2026 — Projet OSIRIS Scanner v0.1.0*
