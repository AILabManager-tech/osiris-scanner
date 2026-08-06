# Développement

## Environnement

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

`dev` installe pytest, pytest-asyncio, Ruff, Mypy, Bandit, pip-audit, Radon, build et la bibliothèque
Playwright. Installer Chromium seulement pour exécuter un vrai parcours approfondi local :

```bash
python -m playwright install chromium
```

## Suite locale

```bash
python -m compileall -q .
pytest -q
ruff check .
ruff format --check .
mypy --explicit-package-bases .
bandit -q -r . -x ./tests
pip-audit
radon cc . -e '.venv*,build/*,dist/*,tests/*' -s -a
python -m build
docker compose config
docker build -t osiris-scanner:local .
```

Les tests réseau démarrent un serveur HTTP contrôlé sur le premier port libre de 25000–25099. Ils
couvrent HTML simple, en-têtes faibles, traceur simulé, JavaScript, redirection, réponse lente,
réponse volumineuse, erreur HTTP, URL invalide, domaine inexistant et indisponibilité Playwright.
Ils ne dépendent pas d’Internet pour valider ces contrats.

## Ajouter ou modifier un axe

1. retourner un `AxisResult` complet;
2. enregistrer l’axe avec `@register_axis`, un poids, un ordre et `after` si nécessaire;
3. ne partager aucune donnée implicite entre tâches parallèles;
4. mettre à jour simultanément méthodologie, rapports, interface, historique, calibration et tests;
5. incrémenter la version de méthodologie si le score change;
6. ne pas inclure un axe expérimental dans le score canonique sans migration complète.

## Rapports

Modifier d’abord `_build_report_data`; les rendus JSON, Markdown, PDF et l’interface consomment ce
modèle commun. Un nouveau champ doit être testé dans tous les formats. Les formulations juridiques
absolues sont interdites et l’avertissement FR/EN est obligatoire.

## Packaging propre

```bash
python -m build
python -m venv /tmp/osiris-wheel
/tmp/osiris-wheel/bin/pip install dist/osiris_scanner-*.whl
/tmp/osiris-wheel/bin/osiris --help
```

Vérifier ensuite les ressources `blocklists/trackers.json` et `osiris_web/static/index.html` avec
`importlib.resources`.

## Git et publication

Les commits doivent être locaux, ciblés et testés. Aucun push, merge, déploiement ou publication de
paquet n’est automatique dans ce dépôt. Le workflow CI compile, lint, type-check, audite, teste Python
3.11/3.12 et construit les distributions sans déployer.
