# Architecture OSIRIS Scanner

## Surfaces livrées

- `scanner.py` : API asynchrone `execute_scan` et CLI `osiris`;
- `webapp.py` : serveur HTTP léger, file bornée de jobs et téléchargements;
- `axes/` : registre et six plugins canoniques;
- `scoring.py` : score, couverture et statuts;
- `report.py` : modèle commun puis rendus JSON, Markdown et PDF;
- `history.py` : historique SQLite local optionnel;
- `calibrate.py` et `benchmark/run_benchmark.py` : exécution multi-cibles;
- `url_security.py` : politique réseau commune à HTTP et Playwright.

## Flux principal

```text
CLI ou HTTP
    │
    ▼
validation URL + DNS ── refus SSRF ──► échec de cible
    │
    ▼
registre O/S/I/R/V/L
    │
    ├── niveaux indépendants en parallèle
    └── dépendances `after` séquencées par le moteur
    │
    ▼
AxisResult ou erreur explicite
    │
    ▼
score technique + couverture + facteur de fiabilité
    │
    ▼
modèle de rapport unique
    ├── JSON
    ├── Markdown
    ├── PDF
    └── interface web
```

Chaque `AxisResult` transporte le score observé, sa couverture, les observations, preuves,
risques, recommandations, limites, détails techniques et la source. Un échec total ne produit pas
d’`AxisResult`. Une dégradation approfondi→rapide conserve plutôt le résultat rapide et l’erreur de
l’outil approfondi; l’axe est marqué `erreur technique` et le scan `partial`.

## Concurrence et déterminisme

`AxisInfo.after` déclare les dépendances. Le moteur lance seulement les axes dont les prérequis sont
terminés, et parallélise le reste par niveau. Le reliquat historique où Ressources lisait un résultat
Lighthouse partagé a été supprimé : R mesure désormais ses propres octets et ne dépend plus de O.
Les tests utilisent aussi une dépendance synthétique O→R pour verrouiller le scheduler.
Les opérations Playwright sont sérialisées par scan afin d’éviter cinq navigateurs concurrents;
les axes HTTP indépendants restent parallèles. Les résultats terminés sont conservés même si la
durée globale expire pendant un autre axe.

## Modes

Le mode rapide n’exécute pas JavaScript. Le mode approfondi utilise Playwright avec services workers
bloqués. Chaque requête navigateur est satisfaite par `safe_fetch`, qui valide et épingle la
destination, puis applique les limites de taille; Chromium ne contacte jamais directement la cible.
Si Playwright ou Chromium est absent, les axes concernés se
replient sur leurs mesures rapides, ajoutent `degraded_from`, diminuent la couverture et rendent le
scan global `partial`.

## Interface web

Le serveur standard Python expose :

- `GET`/`HEAD /`, `/styles.css`, `/app.js`;
- `GET`/`HEAD /health` et `/api/methodology`;
- `POST /api/scans`;
- `GET /api/scans/{id}`;
- `GET /api/scans/{id}/reports/{json|markdown|pdf}`.

Deux workers traitent au plus quatre jobs actifs. Le serveur borne aussi les connexions et les
lectures lentes. L’état reste en mémoire et les rapports sont
écrits dans un répertoire temporaire propre au processus. Les jobs expirés après une heure et leurs
fichiers sont supprimés; le reste est nettoyé à la fin du processus. Aucun compte, cookie,
analytics ou base utilisateur n’est créé.

## Packaging

Le projet distribue les modules racine nécessaires, les packages `axes`, `blocklists`, `calibration`,
`blocklists/trackers.json`, `calibration/sites.txt` et les assets `osiris_web/static`. Les scripts
installés sont `osiris`, `osiris-web` et `osiris-calibrate`. Le mainteneur de blocklist demeure un
outil source, car une installation standard ne doit pas modifier ses ressources de paquet. Le composant SOIC ne fait
pas partie du produit public : l’historique Git confirme son extraction vers un dépôt privé.
