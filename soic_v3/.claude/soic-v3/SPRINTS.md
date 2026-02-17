# SOIC v3.0 — SPRINTS

## Sprint 0 — Nettoyage & Audit de vérité
**Effort :** 5-7h

### Objectif
Consolider les 26 répertoires SOIC en 2 (prod + archive). Mesurer l'état RÉEL du codebase.

### Livrables
- `scripts/audit_truth.sh` — Script d'audit complet
- `reports/audit_baseline.md` — Rapport avec vrais chiffres

### Le script audit_truth.sh doit mesurer
1. Vrais fichiers Python (exclure venv/, node_modules/, site-packages/, __pycache__/)
2. LOC réelles (mêmes exclusions)
3. `pytest --co -q` → tests détectés
4. `pytest --tb=line -q` → tests qui passent réellement
5. `ruff check . --statistics`
6. `bandit -r AINOVA_BRAIN/ MODULES/ -f json -o reports/bandit_baseline.json`
7. `radon cc AINOVA_BRAIN/ -a -j -O reports/radon_baseline.json`

### Format du rapport
Tableau : Métrique | Valeur v2.0 déclarée | Valeur réelle mesurée | Delta

### Critère de succès
```bash
bash scripts/audit_truth.sh
# → génère reports/audit_baseline.md avec les vrais chiffres
```

---

## Sprint 1 — Gate Engine + DOMAIN_CODE
**Effort :** 15h

### Objectif
Implémenter le cœur de SOIC v3.0 : Gate Engine avec grille DOMAIN_CODE (6 gates).

### Fichiers à créer

```
AINOVA_BRAIN/soic_v3/
├── __init__.py          # Exports principaux
├── models.py            # GateResult, GateReport, SOICScore (dataclasses)
├── gate_engine.py       # Classe GateEngine : run_gate(), run_all_gates()
├── domain_grids/
│   ├── __init__.py
│   └── code.py          # 6 gates (voir ci-dessous)
├── persistence.py       # RunStore : JSON Lines dans soic_runs/
└── cli.py               # Click/argparse : soic evaluate

TESTS/unit/test_soic_v3/
├── __init__.py
└── test_gate_engine.py  # Tests unitaires
```

### Gates DOMAIN_CODE
| Gate | Outil | Commande | FAIL si |
|------|-------|----------|---------|
| C-01 | ruff | `ruff check {path} --statistics` | errors > 0 |
| C-02 | bandit | `bandit -r {path} -f json` | severity CRITICAL ou HIGH > 0 |
| C-03 | pytest | `python -m pytest {test_path} --tb=line -q` | exit code ≠ 0 |
| C-04 | radon | `radon cc {path} -a` | average complexity > 15 |
| C-05 | mypy | `mypy {path} --ignore-missing-imports` | errors > 0 |
| C-06 | gitleaks | `gitleaks detect --source {path} -f json` | findings > 0 |

### Spécifications techniques
- Chaque gate exécute via subprocess avec timeout 60s
- Si outil absent : GateResult(status="SKIP", evidence="Tool not found: {tool}")
- μ = (nombre PASS / nombre total hors SKIP) × 10
- Persistence en JSON Lines dans soic_runs/

### Critère de succès
```bash
python -m AINOVA_BRAIN.soic_v3.cli evaluate --path AINOVA_BRAIN/ --domain CODE
# → Tableau de 6 gates avec PASS/FAIL + score μ
```

---

## Sprint 2 — Feedback Loop & Converger
**Effort :** 8h

### Objectif
Boucle d'itération : evaluate → decide → feedback ciblé → re-evaluate.

### Fichiers à créer

```
AINOVA_BRAIN/soic_v3/
├── feedback_router.py   # FeedbackRouter : instructions correctives par gate FAIL
├── converger.py         # Converger : décision ACCEPT/ITERATE/ABORT
└── iterator.py          # SOICIterator : orchestre la boucle complète

TESTS/unit/test_soic_v3/
└── test_converger.py
```

### Logique de décision du Converger
| Condition | Décision |
|-----------|----------|
| Toutes gates PASS | ACCEPT |
| Gate critique FAIL + iter < MAX_ITER | ITERATE |
| delta_mu ≤ 0 pendant 2 itérations | ABORT_PLATEAU |
| iter ≥ MAX_ITER (3) | ABORT_MAX_ITER |

### FeedbackRouter
- Pour chaque gate FAIL : instruction corrective spécifique + evidence
- Ne mentionne PAS les gates PASS
- Output = bloc Markdown structuré

### CLI mise à jour
- `soic iterate --path <path> --domain CODE --max-iter 3`
- `soic history --path <path> [--last N]`

### Critère de succès
```bash
python -m AINOVA_BRAIN.soic_v3.cli iterate --path AINOVA_BRAIN/ --domain CODE --max-iter 3
# → N itérations avec feedback ciblé + convergence affichée
```

---

## Sprint 3 — Multi-domain (PROMPT, INFRA, PROSE)
**Effort :** 10h

### Objectif
Étendre aux domaines non-code + auto-détection du domaine.

### Fichiers à créer

```
AINOVA_BRAIN/soic_v3/
├── domain_grids/
│   ├── prompt.py        # 5 gates prompt
│   ├── infra.py         # 5 gates infrastructure
│   └── prose.py         # 5 gates documentation
└── classifier.py        # classify_domain(path) → list[str]
```

### Gates par domaine

**DOMAIN_PROMPT :**
PR-01: Regex → zéro {{VAR}} non résolu
PR-02: Pattern match → clauses fallback/incertitude présentes
PR-03: Format contraint vérifié (table/JSON/YAML)
PR-04: Structure Markdown hiérarchique valide
PR-05: Zéro placeholder non résolu ([TODO], [PLACEHOLDER], TBD)

**DOMAIN_INFRA :**
I-01: yamllint sur .yml/.yaml
I-02: docker build --check (si Dockerfile)
I-03: trivy fs (si installé, sinon SKIP)
I-04: hadolint sur Dockerfile (si présent, sinon SKIP)
I-05: kubeval sur manifests K8s (si présents, sinon SKIP)

**DOMAIN_PROSE :**
P-01: Fichiers > 500 lignes → doivent avoir des titres
P-02: Liens cassés (regex URLs + check basique)
P-03: Ratio code-blocks/texte raisonnable
P-04: Zéro section vide ou placeholder
P-05: Encodage UTF-8 propre

### Classifier
Heuristique sur extensions + contenu :
- .py majoritaire → CODE
- .md/.rst majoritaire → PROSE
- .yml/.yaml/.Dockerfile → INFRA
- Contient {{, ROLE:, DIRECTIVE → PROMPT
- Multi-domain possible

### CLI mise à jour
- `soic evaluate --path <path>` (sans --domain) → auto-détection
- `soic evaluate --path <path> --domain PROMPT,INFRA` → multi-domain

### Critère de succès
```bash
soic evaluate --path docs/           # → PROSE auto-détecté
soic evaluate --path DEPLOYMENT/     # → INFRA auto-détecté
```

---

## Sprint 4 — MCP Tool + Dashboard
**Effort :** 10h

### Objectif
Serveur MCP + dashboard terminal Rich.

### Fichiers à créer

```
MCP_SERVERS/soic_mcp/
├── server.py            # Serveur MCP (fastmcp)
└── config.json          # Config pour claude_desktop_config.json

AINOVA_BRAIN/soic_v3/
└── dashboard.py         # Dashboard Rich
```

### MCP Tools
- `soic_evaluate` : Input {path, domain?, max_iterations?} → Output {score, report, decision}
- `soic_iterate` : Input {path, domain?, max_iter?} → Output {iterations, final_score}
- Resource `soic://history/{path}` → Runs passés

### Dashboard (Rich)
- Tableau coloré du dernier run (PASS vert, FAIL rouge)
- Courbe convergence ASCII (μ par itération)
- Comparaison avant/après

### CLI mise à jour
- `soic dashboard [--last N]`
- `soic export --format sarif --output report.sarif`

### Critère de succès
```bash
python MCP_SERVERS/soic_mcp/server.py          # → serveur démarre
soic dashboard                                  # → affiche tableau Rich
```

---

## Sprint 5 — CI/CD Integration + Badge
**Effort :** 5h

### Objectif
GitHub Actions + badge README dynamique.

### Fichiers à créer

```
.github/workflows/soic-gate.yml
scripts/update_badge.py
```

### Workflow soic-gate.yml
- Trigger : push main, PR vers main
- Setup Python 3.11 + install outils
- Run soic evaluate → soic-report.json
- Run soic export --format sarif → soic.sarif
- Upload SARIF (github/codeql-action/upload-sarif)
- Upload artifact soic-report.json
- Fail si gate CRITICAL en échec

### Badge
Format : `SOIC v3.0 | μ X.X | N/M gates`
Couleurs : vert ≥ 8, jaune ≥ 6, rouge < 6

### Critère de succès
```bash
git push → CI passe → SARIF dans Security tab → Badge à jour
```
