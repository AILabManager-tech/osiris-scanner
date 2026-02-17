# SOIC v3.0 — RÈGLES NON-NÉGOCIABLES

## Fichiers protégés (NE JAMAIS MODIFIER)
- AINOVA_BRAIN/soic_engine.py
- AINOVA_BRAIN/orchestrator.py
- Tout fichier hors de AINOVA_BRAIN/soic_v3/ et TESTS/unit/test_soic_v3/

## Périmètre d'écriture autorisé
```
AINOVA_BRAIN/soic_v3/**     # Code source
TESTS/unit/test_soic_v3/**  # Tests
MCP_SERVERS/soic_mcp/**     # Serveur MCP (Sprint 4+)
scripts/                    # Scripts utilitaires
soic_runs/                  # Données de persistence
.github/workflows/soic-*    # CI/CD (Sprint 5)
```

## Standards de code
- Python 3.11+
- Typing strict (mypy compatible)
- Docstrings Google style
- Zéro dépendance nouvelle sauf : ruff, bandit, radon, mypy, gitleaks, rich, click

## Principe fondamental
Le LLM GÉNÈRE. Les OUTILS VÉRIFIENT. Le score μ = ratio de gates PASS.
Jamais d'auto-évaluation. Jamais de score subjectif.

## Après chaque implémentation
1. Lancer ruff check sur le code créé
2. Lancer pytest sur les tests créés
3. Montrer les résultats — ne pas dire "c'est fait" sans preuve
