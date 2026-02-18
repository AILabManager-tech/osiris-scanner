# OSIRIS Scanner

Score composite (0-10) mesurant la **sante operationnelle** d'un site web.

OSIRIS agregre les resultats d'outils tiers sur 4 axes :
**Performance (O)** + **Securite (S)** + **Intrusion (I)** + **Ressources (R)**.

> **Avertissement** : OSIRIS est un outil d'observation automatisee, pas un pentest ni
> une certification de conformite. Les scores sont indicatifs et sujets a variance
> (cf. [Limitations](#limitations)).

## Installation

### Prerequis

- Python 3.11+
- Node.js 18+ (pour Lighthouse CLI)
- Google Chrome / Chromium

### Setup

```bash
# Cloner et installer
cd osiris-scanner
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Installer Lighthouse CLI
npm install -g lighthouse

# (Optionnel) Mode deep — installer les navigateurs Playwright
playwright install chromium
```

## Usage

### Scan basique (mode fast)

```bash
python scanner.py --url https://example.com
```

### Scan avec rapport JSON + Markdown

```bash
python scanner.py --url https://example.com --output report
```

Genere :
- `reports/<domain>_<date>.json` — Rapport JSON structure
- `reports/<domain>_<date>.md` — Rapport Markdown lisible

### Multi-run Lighthouse (stabilisation variance)

```bash
python scanner.py --url https://example.com --runs 3
```

Execute Lighthouse N fois et retourne la **mediane**. Tolere les timeouts partiels :
si 1 run sur 3 echoue, la mediane est calculee sur les 2 restants.

### Mode deep (Playwright headless)

```bash
python scanner.py --url https://example.com --mode deep
```

En mode deep, les axes Intrusion et Resource utilisent Playwright au lieu du HTML statique :

| Axe | Mode fast | Mode deep |
|-----|-----------|-----------|
| I — Intrusion | Parse HTML pour trouver les domaines dans `<script>`, `<img>`, `<link>` | Capture toutes les **network requests reelles** (inclut trackers JS dynamiques) |
| R — Resource | Mesure le poids du HTML principal | Somme le **poids total transfere** (tous assets : JS, CSS, images, fonts) |
| O — Performance | Lighthouse CLI (identique) | Lighthouse CLI (identique) |
| S — Security | Observatory + Headers (identique) | Observatory + Headers (identique) |

### Combinaison des options

```bash
# Deep mode + 3 runs Lighthouse + rapport + historique
python scanner.py --url https://example.com --mode deep --runs 3 --output report --history
```

### Historique des scans

```bash
python scanner.py --url https://example.com --history
```

Affiche les scans precedents du meme domaine (necessite le module `soic_v3`).

### Calibration multi-sites

```bash
python calibrate.py
```

Scanne les sites listes dans `calibration/sites.txt` et produit `calibration/results.json`.

## Architecture

```
osiris-scanner/
├── scanner.py          # Orchestrateur principal (CLI)
├── scoring.py          # Agregation ponderee (formule publique)
├── report.py           # Generation rapports JSON + Markdown
├── calibrate.py        # Script de calibration multi-sites
├── axes/
│   ├── performance.py  # Axe O — Wrapper Lighthouse CLI
│   ├── security.py     # Axe S — Mozilla Observatory + Headers HTTP
│   ├── intrusion.py    # Axe I — Detection trackers (fast: HTML, deep: Playwright)
│   └── resource.py     # Axe R — Poids page + Website Carbon API
├── blocklists/
│   └── trackers.json   # 110+ domaines de tracking connus
├── soic_v3/            # Quality gates, persistance, convergence (optionnel)
├── calibration/        # Donnees de calibration
├── reports/            # Rapports generes
├── tests/              # ~156 tests unitaires
└── pyproject.toml
```

## Formule de scoring

```
mu_osiris = Performance x 0.20 + Security x 0.30 + Intrusion x 0.30 + Resource x 0.20
```

| Axe | Poids | Outil | Mesure |
|-----|------:|-------|--------|
| O — Performance | 20% | Lighthouse CLI | Core Web Vitals, score 0-100 normalise a 0-10 |
| S — Security | 30% | Mozilla Observatory + Headers | Grade + presence headers securite |
| I — Intrusion | 30% | Blocklist Analysis (fast) / Playwright (deep) | Trackers detectes |
| R — Resource | 20% | Page Weight + Website Carbon | Poids page + gCO2 estimes |

### Grades

| Score | Grade |
|------:|-------|
| 9.0 - 10.0 | Exemplaire |
| 7.0 - 8.9 | Conforme |
| 5.0 - 6.9 | A risque |
| 0.0 - 4.9 | Critique |

### Ponderations

- **Securite et Intrusion (30% chacun)** : priorite a la protection des utilisateurs
- **Performance et Resource (20% chacun)** : qualite de l'experience et eco-responsabilite

## Limitations

### Axe O — Performance

- Lighthouse en mode headless peut donner des scores differents d'un navigateur reel
- Certains sites bloquent Chrome headless (`NO_FCP`), rendant le scan impossible
- **Variance ~10% entre executions** — utiliser `--runs 3` pour obtenir une mediane stable
- Timeout par defaut : 120 secondes par run

### Axe S — Security

- Mozilla Observatory **cache les resultats 24h** ; un re-scan immediat retourne le cache
- L'analyse des headers est limitee a la presence/absence, pas a la qualite de la configuration
- Certains serveurs bloquent les requetes HEAD, necessitant un fallback GET

### Axe I — Intrusion

- **Mode fast** : analyse basee sur le HTML statique uniquement ; les trackers charges
  dynamiquement par JavaScript ne sont **pas detectes** (cela explique les scores eleves
  meme pour des sites connus pour leur tracking, ex: Google)
- **Mode deep** : capture les network requests via Playwright ; detecte les trackers JS
  dynamiques, mais necessite Chromium installe (`playwright install chromium`)
- La blocklist couvre ~110 domaines ; les trackers non listes ne sont pas detectes

### Axe R — Resource

- **Mode fast** : mesure le poids du HTML principal uniquement (pas les assets)
- **Mode deep** : mesure le poids total transfere (tous assets via Playwright)
- L'API Website Carbon `/data` peut etre indisponible ; fallback sur le modele SWD v4 local
- L'estimation gCO2 est approximative

### General

- OSIRIS mesure la sante **operationnelle** d'un site, pas sa qualite de contenu
- **Ce n'est pas un pentest** et ne remplace pas un audit de securite professionnel
- **Ce n'est pas une certification** de conformite (RGPD, WCAG, etc.)
- Le scanner necessite un acces reseau aux APIs externes (Observatory, Website Carbon, Green Web Foundation)
- Rate limiting : 1 scan Observatory par domaine toutes les 60 secondes
- Un scan echoue partiellement est affiche avec un score partiel (moyenne des axes reussis)

## Degradation gracieuse

Si un axe echoue (timeout, API indisponible, Lighthouse absent), OSIRIS :
1. Affiche l'erreur pour l'axe concerne
2. Continue les axes restants
3. Calcule un **score partiel** base sur les axes reussis (au lieu de crash)

## Tests

```bash
# Tous les tests
python -m pytest tests/ -v

# Tests specifiques
python -m pytest tests/test_performance.py -v
python -m pytest tests/test_intrusion.py -v

# Lint
ruff check .

# Type checking
mypy axes/ scanner.py scoring.py report.py --ignore-missing-imports
```

## License

MIT License — Copyright (c) 2026 [Mark Systems](https://marksystems.ca)

See [LICENSE](LICENSE) for details.
