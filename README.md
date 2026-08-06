# OSIRIS Scanner

Diagnostic multidimensionnel de sites web. Un outil Auxo Systems.

OSIRIS observe une URL publique sur six axes, conserve les preuves disponibles et distingue
un résultat faible d’une mesure absente ou d’une erreur technique. Il fournit un CLI, une
interface web légère et des rapports JSON, Markdown et PDF issus du même modèle de données.

> Prédiagnostic technique automatisé. Ne constitue pas une certification de conformité ni un
> avis juridique.
>
> Automated technical pre-assessment. It does not constitute compliance certification or
> legal advice.

## Axes canoniques

| Clé | Axe | Poids | Mode rapide | Mode approfondi |
|---|---|---:|---|---|
| O | Performance | 15 % | temps de réponse HTTP protégé | navigation et rendu Playwright |
| S | Sécurité | 25 % | en-têtes HTTP + Mozilla Observatory | identique |
| I | Intrusion | 20 % | domaines et traceurs visibles dans le HTML | requêtes réseau Playwright |
| R | Ressources | 10 % | poids du HTML + estimation carbone | octets réellement transférés |
| V | Souveraineté | 15 % | DNS et domaines visibles | destinations réseau, IP, ASN et pays apparents |
| L | Signaux vie privée | 15 % | traceurs, lien de confidentialité, contrôle visible | comportement avant/après refus observable |

Il n’existe actuellement aucun axe Accessibilité ou SEO dans le produit livré. Si ces axes sont
ajoutés plus tard, ils resteront expérimentaux et hors score tant que la méthodologie, les rapports
et les tests ne les intègrent pas explicitement.

## Installation

Prérequis : Python 3.11 ou 3.12.

Installation normale :

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
osiris --help
```

Développement en mode editable :

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Le mode approfondi requiert aussi Chromium :

```bash
python -m pip install -e ".[deep]"
python -m playwright install chromium
```

Sans navigateur disponible, OSIRIS se replie sur les mesures rapides, marque le scan `partial`,
réduit la couverture et explique la dégradation. Il n’invente pas de résultat approfondi.

## CLI

```bash
# Scan rapide
osiris --url https://example.com

# Scan approfondi et trois formats de rapport
osiris --url https://example.com --mode deep --output report

# Médiane de trois mesures de performance HTTP
osiris --url https://example.com --runs 3

# Historique SQLite local explicite
osiris --url https://example.com --history
```

`--output report` produit un JSON, un Markdown et un PDF dans `reports/` ou dans le répertoire
fourni à `--output-dir`. L’historique est désactivé par défaut et ne dépend plus du composant SOIC
privé retiré du dépôt.

## Interface publique

```bash
osiris-web
# ouvre le premier port libre entre 25000 et 25099
```

L’interface permet de choisir le mode rapide ou approfondi, de suivre les étapes, de consulter la
couverture, les six scores, les observations, les preuves, les risques, les recommandations et les
limites, puis de télécharger les trois rapports. Elle n’utilise ni compte, ni cookie, ni analytics,
ni stockage de renseignements personnels. Les jobs et rapports temporaires expirent avec le
processus; aucun faux historique utilisateur n’est présenté.

Le profil **Diagnostic technique Loi 25** met en évidence S, I, V et L. Il s’agit d’une lecture
ciblée de signaux techniques — traceurs, consentement observable, services externes, souveraineté
apparente et mentions visibles — et non d’une conclusion juridique.

## Docker

```bash
docker compose config
docker compose up --build
# http://127.0.0.1:25000
```

L’image installe Chromium, démarre l’interface comme utilisateur non-root et fournit `/health`.
Pour utiliser uniquement le CLI dans l’image :

```bash
docker run --rm --entrypoint osiris osiris-scanner-osiris-web \
  --url https://example.com --output report
```

## Scoring et fiabilité

Méthodologie : `OSIRIS-6A-2026.1`.

```text
score technique = Σ(score axe × poids axe)
couverture = Σ(couverture axe × poids axe)
facteur de fiabilité = 0,75 + 0,25 × couverture
score publié = score technique × facteur de fiabilité
```

Lorsqu’un axe manque, le score technique est normalisé sur les axes réellement produits, puis le
facteur de fiabilité applique une pénalité explicite. Une erreur d’outil n’est jamais convertie en
mauvais score. Les statuts publics sont : `bon`, `à surveiller`, `risque élevé`, `non évalué`,
`donnée insuffisante` et `erreur technique`.

La méthodologie détaillée est dans [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Sécurité des URL

La politique réseau est fermée par défaut :

- HTTP et HTTPS seulement;
- ports publics 80 et 443 seulement;
- refus des identifiants intégrés, localhost, loopback, réseaux privés, link-local, réservés et
  métadonnées cloud;
- résolution DNS contrôlée au départ et à la connexion;
- revalidation de chaque redirection et relais de chaque sous-ressource Playwright par la pile HTTP
  protégée; Chromium ne contacte jamais directement la cible;
- aucune autorisation DNS mise en cache;
- maximum de cinq redirections, 30 secondes par requête, 180 secondes globales, 5 MiB par réponse
  et 20 MiB par axe navigateur;
- aucun accès implicite au système de fichiers local.

Voir [docs/SECURITY.md](docs/SECURITY.md) pour le modèle de menace et les limites.

## Données et services externes

| Source | Donnée envoyée | Repli |
|---|---|---|
| Mozilla Observatory | nom d’hôte public | en-têtes locaux seulement |
| Green Web Foundation | nom d’hôte public | statut vert inconnu |
| Website Carbon | nombre d’octets et indicateur vert | estimation locale SWD v4 |
| ipwho.is | adresse IP publique observée | pays/ASN inconnus, couverture réduite |
| blocklist locale | aucune donnée externe | résultat limité à la liste embarquée |

Les réponses externes sont indicatives, peuvent être mises en cache localement et peuvent devenir
indisponibles. Le rapport conserve cette limite au lieu de transformer l’absence en preuve.

## Calibration et benchmark

```bash
osiris-calibrate
python benchmark/run_benchmark.py --mode fast
```

Ces commandes utilisent des URL publiques et écrivent respectivement `osiris-calibration-results.json`
et les sorties ignorées de `benchmark/raw/` et `benchmark/summary/`. Les résultats historiques
d’une ancienne méthodologie ne doivent pas être comparés à `OSIRIS-6A-2026.1`.

## Développement et validation

```bash
python -m compileall -q .
pytest -q
ruff check .
ruff format --check .
mypy --explicit-package-bases .
bandit -q -r . -x ./tests
pip-audit
python -m build
docker compose config
```

La procédure complète et les fixtures réseau locales sont décrites dans
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). L’architecture est documentée dans
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Limites

- OSIRIS n’est pas un pentest et n’exploite pas les vulnérabilités.
- Les mesures de laboratoire et la géolocalisation IP varient selon le réseau, le CDN et le temps.
- Le mode rapide ne voit pas tous les scripts injectés par JavaScript ni toutes les sous-ressources.
- Les blocklists ont des faux négatifs et parfois des faux positifs.
- L’absence d’une bannière, d’un lien ou d’un traceur n’établit aucune conformité globale.
- Les sites qui bloquent l’automatisation peuvent produire un scan partiel.

## Licence

MIT — Copyright © 2026 Auxo Systems. Voir [LICENSE](LICENSE).
