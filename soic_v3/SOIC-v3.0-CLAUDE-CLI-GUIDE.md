# SOIC v3.0 — Guide de mandat claude-code-cli

## 1. PRÉPARATION (Avant tout prompt)

### 1.1 Fichier CLAUDE.md (à placer à la racine du repo)

Crée ce fichier AVANT de lancer claude-code-cli.
C'est le contexte permanent que Claude Code lira automatiquement.

```bash
cat > ~/SAFE_WORKDIR/ainova-os/CLAUDE.md << 'EOF'
# AINOVA_OS — Contexte pour Claude Code

## Projet
AINOVA_OS est un AI Operating System avec orchestration d'agents BMAD.
Version actuelle : v2.3.0 (production)

## Tâche en cours : SOIC v3.0
Migration du framework SOIC de v2.0 (auto-évaluation LLM) vers v3.0 (tool-verified gates).

### Principe fondamental
SOIC v3.0 = Quality Gate Engine. Chaque critère qualité est vérifié par un OUTIL EXTERNE, pas par le LLM.
- Le LLM GÉNÈRE
- Les OUTILS VÉRIFIENT (ruff, bandit, pytest, mypy, radon, gitleaks)
- Le score μ = ratio de gates PASS (factuel, pas estimé)

### Architecture cible
```
AINOVA_BRAIN/
├── soic_engine.py          # EXISTANT — NE PAS MODIFIER
├── orchestrator.py         # EXISTANT — NE PAS MODIFIER
└── soic_v3/                # NOUVEAU MODULE
    ├── __init__.py
    ├── gate_engine.py      # Exécuteur de gates
    ├── domain_grids/       # Grilles par domaine
    │   ├── __init__.py
    │   ├── code.py         # 6 gates : ruff, bandit, pytest, radon, mypy, gitleaks
    │   ├── prose.py
    │   ├── infra.py
    │   ├── prompt.py
    │   └── analysis.py
    ├── feedback_router.py  # Feedback ciblé par gate FAIL
    ├── converger.py        # Tracking + décision PASS/ITERATE/ABORT
    ├── persistence.py      # JSON Lines storage
    └── cli.py              # CLI : soic evaluate / soic iterate / soic history
```

### Règles strictes
1. NE JAMAIS modifier les fichiers existants sauf si explicitement demandé
2. Tout nouveau code va dans AINOVA_BRAIN/soic_v3/
3. Tests obligatoires dans TESTS/unit/test_soic_v3/
4. Python 3.11+, typing strict, docstrings Google style
5. Zéro dépendance nouvelle sauf les outils de vérification (ruff, bandit, etc.)
6. Chaque gate retourne un résultat binaire PASS/FAIL + preuve (evidence)

### Outils de vérification
| Outil | Usage | Install |
|-------|-------|---------|
| ruff | Linter + formatter | pip install ruff |
| bandit | SAST Python | pip install bandit |
| radon | Complexité cyclomatique | pip install radon |
| mypy | Type checking | pip install mypy |
| gitleaks | Détection de secrets | go install / binary |
| pytest | Test runner | déjà installé |

### Convention de commit
feat(soic-v3): description courte
fix(soic-v3): description courte
test(soic-v3): description courte
EOF
```

### 1.2 Fichier .claude/settings.json (optionnel)

```bash
mkdir -p ~/SAFE_WORKDIR/ainova-os/.claude
cat > ~/SAFE_WORKDIR/ainova-os/.claude/settings.json << 'EOF'
{
  "permissions": {
    "allow": [
      "Bash(pip install *)",
      "Bash(python -m pytest *)",
      "Bash(ruff *)",
      "Bash(bandit *)",
      "Bash(radon *)",
      "Bash(mypy *)"
    ]
  }
}
EOF
```

---

## 2. PROMPTS PAR SPRINT

### Règles d'or pour mandater claude-code-cli

```
✅ UN sprint = UN prompt (pas de méga-prompt multi-sprint)
✅ Commencer par "Lis CLAUDE.md" si tu doutes qu'il l'a chargé
✅ Spécifier les FICHIERS DE SORTIE attendus (pas juste "fais X")
✅ Donner le CRITÈRE DE SUCCÈS (la commande qui prouve que c'est fait)
✅ Interdire explicitement ce qu'il ne doit PAS faire
❌ Ne pas dire "fais au mieux" — dire exactement quoi produire
❌ Ne pas mélanger implémentation + refactoring dans le même prompt
```

---

### SPRINT 0 — Nettoyage & Audit

```
CONTEXTE : Sprint 0 du projet SOIC v3.0 (voir CLAUDE.md)

TÂCHE : Créer un script d'audit qui mesure l'état RÉEL du codebase.

Crée le fichier : scripts/audit_truth.sh

Le script doit :
1. Compter les vrais fichiers Python (exclure venv/, node_modules/, site-packages/, __pycache__/)
2. Compter les LOC réelles (même exclusions)
3. Lancer pytest en mode --co -q (list only, pas d'exécution) pour compter les tests détectés
4. Lancer pytest --tb=line -q pour voir combien passent réellement
5. Lancer ruff check . --statistics (après pip install ruff si absent)
6. Lancer bandit -r AINOVA_BRAIN/ MODULES/ -f json -o reports/bandit_baseline.json
7. Lancer radon cc AINOVA_BRAIN/ -a -j -O reports/radon_baseline.json
8. Produire un rapport résumé dans reports/audit_baseline.md avec les vrais chiffres

Format du rapport :
- Tableau avec : Métrique | Valeur v2.0 déclarée | Valeur réelle mesurée | Delta
- Section "Score μ₀ estimé" basé sur le ratio de checks qui passent

CRITÈRE DE SUCCÈS :
bash scripts/audit_truth.sh → génère reports/audit_baseline.md

NE PAS : modifier du code existant, lancer de refactoring, toucher à soic_engine.py
```

---

### SPRINT 1 — Gate Engine + DOMAIN_CODE

```
CONTEXTE : Sprint 1 du projet SOIC v3.0 (voir CLAUDE.md)

TÂCHE : Implémenter le Gate Engine et la grille DOMAIN_CODE.

Crée ces fichiers :

1. AINOVA_BRAIN/soic_v3/__init__.py
   - Exports principaux

2. AINOVA_BRAIN/soic_v3/models.py
   - Dataclasses : GateResult(gate_id, status: PASS|FAIL, evidence: str, duration_ms: float)
   - Dataclasses : GateReport(gates: list[GateResult], domain: str, timestamp, mu: float, pass_rate: str)
   - Dataclasses : SOICScore(mu: float, sigma: float, pass_rate: str, failures: list)

3. AINOVA_BRAIN/soic_v3/gate_engine.py
   - Classe GateEngine
   - Méthode run_gate(gate_id, target_path) → GateResult
   - Méthode run_all_gates(domain, target_path) → GateReport
   - Chaque gate exécute un outil externe via subprocess et parse le résultat
   - Timeout de 60s par gate
   - Si l'outil n'est pas installé : GateResult(status="SKIP", evidence="Tool not found: {tool}")

4. AINOVA_BRAIN/soic_v3/domain_grids/code.py
   - 6 gates concrètes :
     C-01: ruff check {path} --exit-zero --statistics
     C-02: bandit -r {path} -f json → parse severity counts
     C-03: python -m pytest {test_path} --tb=line -q → parse pass/fail
     C-04: radon cc {path} -a → parse average complexity, FAIL si > 15
     C-05: mypy {path} --ignore-missing-imports → parse error count
     C-06: gitleaks detect --source {path} -f json → parse findings count

5. AINOVA_BRAIN/soic_v3/persistence.py
   - Classe RunStore
   - Stockage JSON Lines dans soic_runs/
   - Méthodes : save_run(), get_history(), get_latest()

6. AINOVA_BRAIN/soic_v3/cli.py
   - Click ou argparse
   - Commande : soic evaluate --path <path> --domain CODE [--output json|table]
   - Affichage tableau avec Rich si disponible, sinon print formaté

7. TESTS/unit/test_soic_v3/test_gate_engine.py
   - Test chaque gate individuellement avec des fixtures
   - Test le calcul de μ (ratio PASS/total)
   - Test la persistence (write + read)

Après création, lance :
- ruff check AINOVA_BRAIN/soic_v3/
- python -m pytest TESTS/unit/test_soic_v3/ -v

CRITÈRE DE SUCCÈS :
python -m AINOVA_BRAIN.soic_v3.cli evaluate --path AINOVA_BRAIN/ --domain CODE
→ Affiche un tableau de 6 gates avec PASS/FAIL + score μ

NE PAS : modifier soic_engine.py, orchestrator.py, ou tout fichier hors soic_v3/
```

---

### SPRINT 2 — Feedback Loop & Converger

```
CONTEXTE : Sprint 2 du projet SOIC v3.0 (voir CLAUDE.md). Le Gate Engine (Sprint 1) est fonctionnel.

TÂCHE : Implémenter le Feedback Router et le Converger.

Crée ces fichiers :

1. AINOVA_BRAIN/soic_v3/feedback_router.py
   - Classe FeedbackRouter
   - Méthode generate_feedback(report: GateReport) → str
   - Pour chaque gate FAIL, produit une instruction corrective ciblée
   - Template par gate_id (ex: C-01 FAIL → "Corriger les erreurs ruff suivantes : {evidence}")
   - Le feedback ne contient QUE les gates en échec, pas les PASS
   - Retourne un bloc Markdown structuré prêt à injecter comme prompt

2. AINOVA_BRAIN/soic_v3/converger.py
   - Classe Converger
   - Méthode decide(history: list[IterationRecord]) → Decision (ACCEPT|ITERATE|ABORT)
   - Règles :
     * All gates PASS → ACCEPT
     * Gate critique FAIL + iterations < MAX_ITER → ITERATE
     * delta_mu <= 0 pendant 2 itérations consécutives → ABORT_PLATEAU
     * iterations >= MAX_ITER (3) → ABORT_MAX_ITER
   - Méthode has_converged() → bool
   - MAX_ITER = 3 (configurable)

3. AINOVA_BRAIN/soic_v3/iterator.py
   - Classe SOICIterator
   - Orchestre la boucle : evaluate → decide → feedback → re-evaluate
   - Utilise GateEngine + FeedbackRouter + Converger + RunStore
   - Log chaque itération dans persistence

4. Mise à jour cli.py :
   - Nouvelle commande : soic iterate --path <path> --domain CODE --max-iter 3
   - Nouvelle commande : soic history --path <path> [--last N]

5. TESTS/unit/test_soic_v3/test_converger.py
   - Test ACCEPT quand tout PASS
   - Test ITERATE quand FAIL critique
   - Test ABORT_PLATEAU quand delta_mu <= 0 deux fois
   - Test ABORT_MAX_ITER

CRITÈRE DE SUCCÈS :
python -m AINOVA_BRAIN.soic_v3.cli iterate --path AINOVA_BRAIN/ --domain CODE --max-iter 3
→ Exécute N itérations, affiche le feedback entre chaque, montre la convergence

NE PAS : modifier le Gate Engine existant (sauf imports dans __init__.py), toucher aux fichiers hors soic_v3/
```

---

### SPRINT 3 — Multi-domain

```
CONTEXTE : Sprint 3 du projet SOIC v3.0 (voir CLAUDE.md). Gate Engine + Feedback Loop fonctionnels.

TÂCHE : Ajouter les grilles DOMAIN_PROMPT, DOMAIN_INFRA, DOMAIN_PROSE + auto-détection.

Crée ces fichiers :

1. AINOVA_BRAIN/soic_v3/domain_grids/prompt.py
   Gates :
   PR-01: Regex scan → zéro {{VAR}} non résolu dans l'output
   PR-02: Pattern match → clauses de fallback/incertitude présentes
   PR-03: Détection de format contraint (table, JSON, YAML déclaré = vérifié)
   PR-04: Vérification structure Markdown (titres hiérarchiques, pas de saut de niveau)
   PR-05: Détection de placeholders non résolus ([TODO], [PLACEHOLDER], TBD)

2. AINOVA_BRAIN/soic_v3/domain_grids/infra.py
   Gates :
   I-01: yamllint sur les fichiers .yml/.yaml
   I-02: docker build --check (si Dockerfile présent)
   I-03: trivy fs --scanners vuln,config {path} (si trivy installé, sinon SKIP)
   I-04: hadolint sur Dockerfile (si présent, sinon SKIP)
   I-05: kubeval/kubeconform sur les manifests K8s (si présents, sinon SKIP)

3. AINOVA_BRAIN/soic_v3/domain_grids/prose.py
   Gates :
   P-01: Détection de fichiers > 500 lignes sans titres (structure manquante)
   P-02: Liens cassés (regex URLs + check basique)
   P-03: Ratio code-blocks/texte (documentation technique devrait avoir des exemples)
   P-04: Détection de sections vides ou placeholder
   P-05: Vérification d'encodage UTF-8 propre

4. AINOVA_BRAIN/soic_v3/classifier.py
   - Fonction classify_domain(path: str) → list[str]
   - Heuristique basée sur les extensions et le contenu :
     * .py majoritaire → CODE
     * .md/.rst majoritaire → PROSE
     * .yml/.yaml/.Dockerfile → INFRA
     * Contient {{, ROLE:, DIRECTIVE → PROMPT
   - Retourne une liste (multi-domain possible)

5. Mise à jour cli.py :
   - soic evaluate --path <path> sans --domain → auto-détection
   - soic evaluate --path <path> --domain PROMPT,INFRA → multi-domain explicite

6. Tests pour chaque nouveau domaine

CRITÈRE DE SUCCÈS :
soic evaluate --path docs/ → auto-détecte PROSE, lance les gates prose
soic evaluate --path DEPLOYMENT/ → auto-détecte INFRA, lance les gates infra
soic evaluate --path prompts/ → auto-détecte PROMPT, lance les gates prompt

NE PAS : modifier les grilles CODE existantes, changer la logique du Gate Engine
```

---

### SPRINT 4 — MCP Tool + Dashboard

```
CONTEXTE : Sprint 4 du projet SOIC v3.0 (voir CLAUDE.md). Tous les domaines fonctionnels.

TÂCHE : Exposer SOIC v3.0 comme serveur MCP + créer un dashboard terminal.

Crée ces fichiers :

1. MCP_SERVERS/soic_mcp/server.py
   - Serveur MCP avec fastmcp ou mcp SDK
   - Tool : soic_evaluate
     Input : { path: str, domain?: str, max_iterations?: int }
     Output : { score: SOICScore, report: GateReport, decision: str }
   - Tool : soic_iterate
     Input : { path: str, domain?: str, max_iter?: int }
     Output : { iterations: list[IterationRecord], final_score: SOICScore }
   - Resource : soic://history/{path}
     Output : Liste des runs passés pour ce path

2. MCP_SERVERS/soic_mcp/config.json
   - Configuration pour claude_desktop_config.json
   - Commande de lancement du serveur

3. AINOVA_BRAIN/soic_v3/dashboard.py
   - Utilise Rich (pip install rich)
   - Commande : soic dashboard [--last 10]
   - Affiche :
     * Tableau du dernier run (gates PASS/FAIL avec couleurs)
     * Courbe de convergence ASCII (μ au fil des itérations)
     * Comparaison avant/après si ≥ 2 runs

4. Mise à jour cli.py :
   - soic dashboard [--last N]
   - soic export --format sarif --output report.sarif (pour CI/CD Sprint 5)

CRITÈRE DE SUCCÈS :
1. python MCP_SERVERS/soic_mcp/server.py → serveur MCP démarre
2. Depuis claude-code-cli avec MCP configuré : "Évalue AINOVA_BRAIN avec SOIC" → retourne le rapport
3. soic dashboard → affiche le tableau Rich + courbe

NE PAS : modifier les fichiers des sprints précédents sauf cli.py (ajout commandes)
```

---

### SPRINT 5 — CI/CD + Badge

```
CONTEXTE : Sprint 5 du projet SOIC v3.0 (voir CLAUDE.md). MCP + Dashboard fonctionnels.

TÂCHE : Intégrer SOIC v3.0 dans GitHub Actions + badge dynamique.

Crée ces fichiers :

1. .github/workflows/soic-gate.yml
   - Trigger : push sur main, PR vers main
   - Job soic-audit :
     * Setup Python 3.11
     * Install deps : ruff, bandit, radon, mypy, gitleaks
     * Run : python -m AINOVA_BRAIN.soic_v3.cli evaluate --path AINOVA_BRAIN/ --domain CODE --output json > soic-report.json
     * Run : python -m AINOVA_BRAIN.soic_v3.cli export --format sarif --output soic.sarif
     * Upload SARIF : github/codeql-action/upload-sarif
     * Upload artifact : soic-report.json
     * Fail condition : jq '.failures | map(select(.severity == "CRITICAL")) | length > 0' soic-report.json

2. scripts/update_badge.py
   - Lit soic-report.json
   - Génère un badge shields.io dynamique
   - Format : "SOIC v3.0 | μ X.X | N/M gates"
   - Couleur : vert si μ ≥ 8, jaune si ≥ 6, rouge si < 6
   - Met à jour la ligne badge dans README.md

3. Mise à jour README.md :
   - Ajouter la ligne badge en haut
   - Section "Quality — SOIC v3.0" expliquant le scoring

CRITÈRE DE SUCCÈS :
1. Push → GitHub Actions → job soic-audit passe
2. SARIF visible dans l'onglet Security de GitHub
3. Badge à jour dans README.md

NE PAS : modifier la logique SOIC, changer les seuils de gates sans discussion
```

---

## 3. COMMANDES DE LANCEMENT

### Séquence type pour chaque sprint

```bash
# 1. Se placer dans le repo
cd ~/SAFE_WORKDIR/ainova-os

# 2. Lancer claude-code-cli
claude

# 3. Coller le prompt du sprint

# 4. Laisser travailler, intervenir si question

# 5. Quand terminé, valider le critère de succès manuellement

# 6. Commit
git add -A
git commit -m "feat(soic-v3): Sprint N — [description]"
```

### Si claude-code-cli déraille

```
STOP. Reviens au CLAUDE.md.
Tu es en train de [décrire le problème].
Rappel : tu ne dois PAS [ce qu'il fait de mal].
Reprends uniquement la tâche : [reformuler précisément].
```

### Pour forcer un re-focus

```
Montre-moi l'état actuel :
1. Liste les fichiers créés dans AINOVA_BRAIN/soic_v3/
2. Lance le critère de succès du sprint
3. Dis-moi ce qui manque
```

---

## 4. PIÈGES À ÉVITER

| Piège | Comment l'éviter |
|---|---|
| Claude Code réécrit soic_engine.py | "NE PAS modifier" dans CLAUDE.md + rappel dans chaque prompt |
| Il installe 15 dépendances | Lister les deps autorisées dans CLAUDE.md |
| Il crée une archi différente | Spécifier les noms de fichiers exacts dans le prompt |
| Il fait du over-engineering | Limiter le scope : "6 gates, pas plus" |
| Il génère sans tester | Toujours finir le prompt par "lance les tests" |
| Il s'auto-évalue au lieu d'utiliser les outils | C'est littéralement ce que SOIC v3.0 corrige — rappeler si besoin |
| Il part sur un refactoring global | "NE PAS toucher aux fichiers hors soic_v3/" |
