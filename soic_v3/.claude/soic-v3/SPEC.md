# SOIC v3.0 — Self-Optimizing Iterative Convergence (Next Generation)

## Résumé exécutif

SOIC v3.0 abandonne le paradigme "le LLM se note lui-même" au profit d'un système hybride où **chaque assertion qualité est vérifiable par un outil externe ou une preuve binaire**. La convergence n'est plus simulée — elle est mesurée.

---

## 1. ARCHITECTURE

```
┌──────────────────────────────────────────────────────┐
│                    SOIC v3.0 CORE                     │
│                                                       │
│  ┌─────────────┐   ┌──────────────┐   ┌───────────┐ │
│  │  GENERATOR   │──▶│  GATE ENGINE  │──▶│ CONVERGER │ │
│  │  (LLM Call)  │   │  (Tool-Based) │   │ (Tracker) │ │
│  └─────────────┘   └──────────────┘   └───────────┘ │
│         ▲                  │                  │       │
│         │            ┌─────▼─────┐            │       │
│         └────────────│ FEEDBACK  │◀───────────┘       │
│                      │  ROUTER   │                    │
│                      └───────────┘                    │
│                                                       │
│  ┌────────────────────────────────────────────────┐  │
│  │              DOMAIN GRIDS (adaptatif)           │  │
│  │  CODE │ PROSE │ INFRA │ PROMPT │ ANALYSIS │ ... │  │
│  └────────────────────────────────────────────────┘  │
│                                                       │
│  ┌────────────────────────────────────────────────┐  │
│  │           PERSISTENCE LAYER (sqlite/json)       │  │
│  │  Historique μ │ Courbe σ │ Iteration logs       │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### Composantes

| Composante | Rôle | v2.0 équivalent |
|---|---|---|
| **Generator** | Produit l'output (LLM call classique) | Identique |
| **Gate Engine** | Valide chaque critère via outils/preuves externes | Remplace l'auto-évaluation μ/σ |
| **Converger** | Track l'historique, calcule la convergence réelle, décide PASS/ITERATE/FAIL | Nouveau |
| **Feedback Router** | Si ITERATE : synthétise les failures en instructions correctives ciblées | Remplace "itère si μ < 9.0" |
| **Domain Grids** | Critères adaptatifs selon le type de tâche | Remplace les 6 critères fixes |
| **Persistence** | Stocke les runs, scores, deltas entre sessions | Nouveau |

---

## 2. DOMAIN GRIDS — Critères adaptatifs

Chaque domaine a sa propre grille de quality gates. Les gates sont **binaires** (PASS/FAIL) avec une **preuve** obligatoire.

### 2.1 DOMAIN_CODE

| Gate ID | Critère | Méthode de vérification | Preuve |
|---|---|---|---|
| C-01 | Syntaxe valide | Parser/Linter (`ruff`, `eslint`, `rustc --check`) | Exit code 0 |
| C-02 | Zéro vulnérabilité critique | SAST (`semgrep`, `bandit`) | Rapport JSON, 0 CRITICAL |
| C-03 | Tests passent | Test runner (`pytest`, `vitest`) | Exit code 0 + coverage % |
| C-04 | Complexité maîtrisée | Analyse cyclomatique (`radon`, `lizard`) | Score < seuil configurable |
| C-05 | Type safety | Type checker (`mypy`, `tsc --noEmit`) | Exit code 0 |
| C-06 | Pas de secrets leakés | `gitleaks`, `trufflehog` | 0 findings |

### 2.2 DOMAIN_PROSE

| Gate ID | Critère | Méthode de vérification | Preuve |
|---|---|---|---|
| P-01 | Grammaire | `languagetool` API ou `vale` | 0 errors |
| P-02 | Lisibilité | Flesch-Kincaid / `textstat` | Score dans range cible |
| P-03 | Ancrage factuel | Chaque claim mappé à une source (URL, doc, data) | Ratio claims:sources ≥ 0.8 |
| P-04 | Structure | Validation du schema Markdown attendu | Schema match |
| P-05 | Densité informationnelle | Ratio contenu utile / tokens total | > seuil configurable |

### 2.3 DOMAIN_INFRA

| Gate ID | Critère | Méthode de vérification | Preuve |
|---|---|---|---|
| I-01 | YAML/JSON valide | Schema validator (`yamllint`, `ajv`) | Exit code 0 |
| I-02 | Dry-run pass | `terraform plan`, `kubectl --dry-run`, `docker build` | Exit code 0 |
| I-03 | Security scan | `trivy`, `checkov`, `kube-bench` | 0 CRITICAL/HIGH |
| I-04 | Idempotence | Double-apply sans diff | Diff = ∅ |
| I-05 | Conformité CIS/NIST | Benchmark tool spécifique | Score ≥ seuil |

### 2.4 DOMAIN_PROMPT

| Gate ID | Critère | Méthode de vérification | Preuve |
|---|---|---|---|
| PR-01 | Variables résolues | Regex scan : zéro `{{VAR}}` non injecté dans output | Match count = 0 |
| PR-02 | Anti-hallucination | Clauses de fallback/incertitude présentes | Pattern match |
| PR-03 | Format contraint | Output conforme au schema déclaré (table, JSON, YAML) | Schema validation |
| PR-04 | Persona cohérent | Pas de contradiction rôle vs contenu | LLM-as-judge (seul cas autorisé) |
| PR-05 | Testabilité | Le prompt peut être exécuté avec des inputs mock | Dry-run réussi |

### 2.5 DOMAIN_ANALYSIS

| Gate ID | Critère | Méthode de vérification | Preuve |
|---|---|---|---|
| A-01 | Données sourcées | Chaque chiffre/statistique a une référence | Ratio ≥ 0.9 |
| A-02 | Calculs vérifiables | Formules reproduisibles (script de vérification) | Script output match |
| A-03 | Biais identifiés | Limites et biais explicitement déclarés | Section présente |
| A-04 | Comparaison équitable | Critères de comparaison explicites et constants | Matrice de critères fournie |

---

## 3. GATE ENGINE — Logique de validation

### 3.1 Classification automatique du domaine

```python
def classify_domain(task: str, output: str) -> str:
    """
    Détermine le domaine applicable.
    Heuristique basée sur le contenu, pas sur les intentions déclarées.
    """
    signals = {
        "CODE":     has_code_blocks(output) and code_ratio(output) > 0.4,
        "INFRA":    contains_patterns(output, ["yaml", "dockerfile", "terraform", "pipeline"]),
        "PROSE":    code_ratio(output) < 0.1 and word_count(output) > 200,
        "PROMPT":   contains_patterns(task, ["soic:", "prompt", "directive", "system prompt"]),
        "ANALYSIS": contains_patterns(task, ["compare", "audit", "évalue", "analyse"]),
    }
    # Multi-domain possible — retourne tous les domaines applicables
    return [domain for domain, match in signals.items() if match]
```

### 3.2 Exécution des gates

```python
async def run_gates(output: str, domains: list[str]) -> GateReport:
    """
    Exécute toutes les gates applicables.
    Chaque gate retourne PASS/FAIL + preuve.
    """
    report = GateReport()
    
    for domain in domains:
        grid = DOMAIN_GRIDS[domain]
        for gate in grid:
            result = await gate.verify(output)
            report.add(gate.id, result.status, result.evidence)
    
    return report
```

### 3.3 Scoring v3.0

On garde μ et σ mais ils sont maintenant **calculés**, pas **estimés** :

```python
def compute_score(report: GateReport) -> SOICScore:
    """
    μ = ratio de gates PASS (0.0 à 1.0, affiché sur 10)
    σ = écart-type des scores par domaine
    
    Plus de notes sur 10 subjectives — c'est un taux de passage factuel.
    """
    gate_scores = [1.0 if g.status == "PASS" else 0.0 for g in report.gates]
    
    mu = mean(gate_scores) * 10  # Ramené sur 10 pour compatibilité
    sigma = stdev(gate_scores) * 10
    
    return SOICScore(
        mu=round(mu, 2),
        sigma=round(sigma, 2),
        pass_rate=f"{sum(gate_scores)}/{len(gate_scores)}",
        failures=[g for g in report.gates if g.status == "FAIL"]
    )
```

**Différence clé v2 → v3 :**

| Métrique | v2.0 | v3.0 |
|---|---|---|
| μ = 9.5 | "Je pense que c'est bon" | "19/20 gates passées, 1 FAIL sur C-04" |
| σ = 0.1 | "C'est assez uniforme" | "Tous les domaines entre 90-100% sauf INFRA à 75%" |

---

## 4. CONVERGER — Tracking et décision

### 4.1 Persistence

```python
# Structure de stockage (SQLite ou JSON lines)
@dataclass
class IterationRecord:
    run_id: str              # UUID
    timestamp: datetime
    task_hash: str           # Hash du prompt/tâche original
    iteration: int           # 1, 2, 3...
    domains: list[str]
    gate_report: GateReport
    mu: float
    sigma: float
    delta_mu: float          # μ(n) - μ(n-1)
    decision: str            # ACCEPT | ITERATE | ABORT
    feedback_given: str      # Instructions correctives envoyées au Generator
```

### 4.2 Règles de décision

```python
DECISION_MATRIX = {
    # Condition                          → Action
    "all_gates_pass":                    "ACCEPT",
    "critical_gate_fail":               "ITERATE",   # Toujours réessayer
    "non_critical_fail_and_mu >= 8.0":  "ACCEPT_WITH_NOTES",
    "iteration >= MAX_ITER":            "ABORT_WITH_REPORT",
    "delta_mu <= 0 for 2 iterations":   "ABORT_PLATEAU",  # Pas de progrès
}

MAX_ITER = 3  # Pragmatique : au-delà, le LLM tourne en rond
```

### 4.3 Convergence réelle

```python
def has_converged(history: list[IterationRecord]) -> bool:
    """
    Convergence = toutes les gates PASS
    OU plateau détecté (plus d'amélioration possible)
    """
    if not history:
        return False
    
    latest = history[-1]
    
    # Convergence positive
    if latest.gate_report.all_pass():
        return True
    
    # Plateau (2 itérations sans amélioration)
    if len(history) >= 2:
        if history[-1].mu <= history[-2].mu:
            return True  # Convergé, mais pas à 100%
    
    return False
```

---

## 5. FEEDBACK ROUTER — Itérations intelligentes

Le problème de v2.0 : "itère" sans dire **quoi corriger**. 

v3.0 : le feedback est **généré à partir des gates en échec**, pas du jugement global.

```python
def generate_feedback(report: GateReport) -> str:
    """
    Construit des instructions correctives ciblées
    basées uniquement sur les gates FAIL.
    """
    instructions = []
    
    for gate in report.failures:
        instructions.append(
            f"[{gate.id}] {gate.criterion} — FAIL\n"
            f"  Preuve: {gate.evidence}\n"
            f"  Action requise: {gate.remediation_hint}\n"
        )
    
    return (
        "## Corrections requises (Itération N+1)\n\n"
        "Corrige UNIQUEMENT les points suivants. "
        "Ne modifie PAS les sections qui ont passé.\n\n"
        + "\n".join(instructions)
    )
```

---

## 6. INTERFACE — Modes d'utilisation

### 6.1 Mode Prompt (rétrocompatible avec v2.0)

Le trigger `soic:` continue de fonctionner, mais le comportement change :

```
soic: Écris un script Python qui parse des logs Apache et génère un rapport CSV

→ SOIC v3.0 active :
  1. Generator produit le script
  2. Gate Engine classifie → DOMAIN_CODE
  3. Gates exécutées : syntax, linter, type check, complexity
  4. Si FAIL → Feedback Router → Generator itère
  5. Si PASS → Output livré avec rapport de gates
```

### 6.2 Mode MCP Tool (nouveau)

```json
{
  "tool": "soic_evaluate",
  "input": {
    "content": "<output à évaluer>",
    "domain_override": null,
    "max_iterations": 3,
    "strict_mode": true
  },
  "output": {
    "score": { "mu": 9.0, "sigma": 0.5 },
    "pass_rate": "18/20",
    "failures": [...],
    "decision": "ACCEPT_WITH_NOTES",
    "iteration_history": [...]
  }
}
```

### 6.3 Mode CLI (claude-code-cli)

```bash
# Évaluation d'un fichier
soic evaluate --file ./output.py --domain CODE --strict

# Évaluation d'un prompt
soic evaluate --file ./prompt.md --domain PROMPT

# Historique de convergence
soic history --task "parser-logs" --format table

# Dashboard
soic dashboard --last 30d
```

---

## 7. ANTI-PATTERNS DE v2.0 ÉLIMINÉS

| Anti-pattern v2.0 | Solution v3.0 |
|---|---|
| LLM se note 10/10 | Scoring par tool verification, pas par auto-évaluation |
| σ = 0.00 (impossible en réalité) | σ calculé sur gates réelles — toujours > 0 sauf 100% PASS |
| Critères identiques pour tout | Domain Grids adaptatifs |
| "Itère" sans direction | Feedback Router avec instructions ciblées par gate |
| Pas de mémoire entre sessions | Persistence Layer (SQLite) |
| Convergence déclarative | Convergence mesurée avec plateau detection |
| LLM-as-judge partout | LLM-as-judge limité à 1 gate (PR-04 cohérence persona) — tout le reste est tool-verified |

---

## 8. MIGRATION v2.0 → v3.0

### Ce qui reste
- Le trigger `soic:` 
- Le concept μ/σ (mais recalculé)
- La philosophie "itération vers la convergence"
- Compatibilité Markdown

### Ce qui change
- Les 6 critères fixes → Domain Grids
- Auto-évaluation → Gate Engine
- Scoring subjectif → Scoring factuel
- Pas de persistence → SQLite/JSON tracking
- Prompt-only → MCP Tool + CLI

### Effort estimé d'implémentation

| Composante | Effort | Priorité |
|---|---|---|
| Domain Grids (définition) | 2-4h | P0 — Fondation |
| Gate Engine (wrapper autour d'outils existants) | 8-12h | P0 — Cœur |
| Feedback Router | 2-3h | P1 — Qualité des itérations |
| Persistence Layer | 4-6h | P1 — Tracking |
| MCP Tool interface | 4-6h | P2 — Intégration AINOVA_OS |
| CLI wrapper | 2-4h | P2 — DX |
| Dashboard / visualisation | 4-8h | P3 — Nice to have |
| **Total** | **~26-43h** | |

---

## 9. PREMIER LIVRABLE MINIMAL (MVP)

Pour une première itération fonctionnelle de SOIC v3.0, implémenter :

1. **DOMAIN_CODE grid** (6 gates avec outils réels)
2. **Gate Engine** en Python (~200 lignes)
3. **Persistence** en JSON lines (pas besoin de SQLite day 1)
4. **Feedback Router** basique (template par gate)

Cela donne un SOIC v3.0 fonctionnel pour le domaine CODE en ~15h de travail.
