# SOIC v3.0 — STRATÉGIE DE MIGRATION ET CONSOLIDATION

## 1. CARTOGRAPHIE DES ASSETS (Valeur réelle)

### 1.1 Classification par valeur

```
TIER S — Assets à migrer en priorité (valeur prouvée)
├── AINOVA_BRAIN/soic_engine.py        → Noyau SOIC, à refactorer pour v3.0
├── AINOVA_BRAIN/orchestrator.py       → 1,890 lignes, logique d'orchestration réelle
├── TESTS/ (35 suites)                 → Infrastructure de test existante
├── MODULES/CORE/ (14 fichiers)        → Utilitaires réutilisables
├── SECURITY/ (decorators)             → @require_auth, @rate_limit, etc. — code battle-tested
└── API/ (8 endpoints OpenAPI 3.1)     → Interface REST existante

TIER A — Assets à auditer puis décider
├── AGENTS_AI/ (35+ agents BMAD)       → Valeur dépend de la qualité des prompts
├── MCP_SERVERS/                       → À évaluer si fonctionnel ou stub
├── MODULES/PROTOCOLS/                 → mcp_manager.py, a2a_manager.py — état inconnu
├── DEPLOYMENT/ (K8s + Docker)         → Utile si les images buildent réellement
└── docs/ (71 fichiers, 859 KB)        → Volume ≠ qualité, à trier

TIER B — Assets à archiver
├── _AINOVA_OS_v.3.0_SEMI-FINAL_       → Supplanté par v2.3.0, garder comme référence
├── OptA_SPECTRA-VENOM/                → Exploration architecturale, valeur historique
├── OptB_HEXCORTEX/                    → Idem
├── OptC_SYNAPSE-PRIME/                → Idem
├── AINOVA_TERMINAL/BACKUP_*/v1        → Legacy
└── AINOVA_OS_v.2.0 (36 KB)           → Squelette, aucune valeur opérationnelle

TIER C — À supprimer (bruit)
├── Copies multiples dans ARCHIVE/, BACKUPS/, Bureau/SOIC/
├── .claude/sandbox/soic-viz           → Prototypes jetables
└── Duplicatas de rapports d'audit
```

### 1.2 Fragmentation — Le vrai problème

```
26 répertoires contenant "SOIC" sur le disque
 5 versions identifiées
 3 branches architecturales (Opt A/B/C)
 4 archives d'audits n8n-SOIC
 ? copies dans ARCHIVE/ et BACKUPS/
```

**Diagnostic : dette d'organisation massive.**
Chaque exploration a créé un fork sans nettoyage.
Le temps passé à naviguer entre ces versions = temps perdu.

---

## 2. PLAN DE CONSOLIDATION (Avant de toucher au code)

### Phase 0 : Nettoyage (2-3 heures)

L'objectif est de passer de 26 répertoires SOIC à **2** :
- `ainova-os/` (production, git-tracked)
- `ainova-os-archive/` (tout le reste, compressé)

```bash
# 1. Créer l'archive consolidée
mkdir -p ~/AINOVA_ARCHIVE
tar czf ~/AINOVA_ARCHIVE/legacy-versions-$(date +%Y%m%d).tar.gz \
  ~/_AINOVA_OS_v.3.0_SEMI-FINAL_ \
  ~/Bureau/_OptA_SPECTRA-VENOM \
  ~/Bureau/_OptB_HEXCORTEX \
  ~/Bureau/_OptC_SYNAPSE-PRIME \
  ~/AINOVA_OS_v.2.0 \
  ~/AINOVA_TERMINAL/BACKUP_* \
  ~/Bureau/SOIC/SOIC-Vault \
  ~/SOIC_TERMINAL \
  ~/.claude/sandbox/soic-viz \
  ~/.claude/sandbox/soic-visual

# 2. Vérifier l'intégrité
tar tzf ~/AINOVA_ARCHIVE/legacy-versions-*.tar.gz | wc -l

# 3. Supprimer les originaux (seulement après vérification)
# rm -rf [liste ci-dessus]

# 4. Résultat : 
#    ~/AINOVA_ARCHIVE/        → Tout l'historique, compressé
#    ~/_SAFE_WORKDIR_/ainova-os/ → La seule version de travail
```

### Phase 0.5 : Audit de vérité (3-4 heures)

Avant toute évolution, obtenir les **vrais chiffres** :

```bash
cd ~/_SAFE_WORKDIR_/ainova-os

# 1. Vrais fichiers Python (exclure venv et deps)
find . -name "*.py" \
  -not -path "*/venv/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/.venv/*" \
  -not -path "*/site-packages/*" \
  -not -path "*/__pycache__/*" | wc -l
# Prédiction : 500-1000 fichiers (pas 20,090)

# 2. Lignes de code réelles (custom)
find . -name "*.py" \
  -not -path "*/venv/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/site-packages/*" | xargs wc -l | tail -1
# Prédiction : 15,000-25,000 LOC (pas 800K+)

# 3. Taille réelle (sans deps)
du -sh --exclude='venv' --exclude='node_modules' \
  --exclude='.venv' --exclude='.git' .
# Prédiction : 50-80 MB

# 4. Tests qui passent RÉELLEMENT
python -m pytest --tb=short -q 2>&1 | tail -5
# C'est LE chiffre qui compte

# 5. Scan de sécurité réel
pip install bandit safety --break-system-packages
bandit -r AINOVA_BRAIN/ MODULES/ -f json -o bandit_report.json
safety check --json > safety_report.json

# 6. Complexité réelle
pip install radon --break-system-packages
radon cc AINOVA_BRAIN/ -a -nc  # Moyenne de complexité cyclomatique
radon mi AINOVA_BRAIN/ -nc     # Maintenability Index

# 7. Type coverage
pip install mypy --break-system-packages
mypy AINOVA_BRAIN/ --ignore-missing-imports --no-error-summary 2>&1 | tail -3
```

**Ce script produit le VRAI score de base — le μ₀ de SOIC v3.0.**

---

## 3. STRATÉGIE DE MIGRATION v2.0 → v3.0

### Principe directeur

```
NE PAS réécrire AINOVA_OS.
GREFFER le Gate Engine v3.0 SUR le codebase existant.
```

La v2.3.0 a du code réel qui fonctionne. L'objectif n'est pas de tout refaire,
c'est de remplacer le système d'évaluation par un système vérifiable.

### Architecture cible

```
ainova-os/                          # Repo existant
├── AINOVA_BRAIN/
│   ├── soic_engine.py              # EXISTANT — garder
│   ├── orchestrator.py             # EXISTANT — garder
│   └── soic_v3/                    # NOUVEAU — Gate Engine
│       ├── __init__.py
│       ├── gate_engine.py          # Exécuteur de gates
│       ├── domain_grids/           # Grilles par domaine
│       │   ├── code.py
│       │   ├── prose.py
│       │   ├── infra.py
│       │   ├── prompt.py
│       │   └── analysis.py
│       ├── feedback_router.py      # Génération de feedback ciblé
│       ├── converger.py            # Tracking + décision PASS/ITERATE/ABORT
│       ├── persistence.py          # JSON Lines ou SQLite
│       └── cli.py                  # Interface CLI `soic evaluate`
├── TESTS/
│   └── unit/
│       └── test_soic_v3/           # NOUVEAU — tests du Gate Engine
│           ├── test_gate_engine.py
│           ├── test_domain_grids.py
│           └── test_converger.py
└── soic_runs/                      # NOUVEAU — Historique des évaluations
    └── .gitkeep
```

### Feuille de route par sprints

```
SPRINT 1 — Fondations (Semaine 1-2, ~15h)
═══════════════════════════════════════════
Objectif : Gate Engine fonctionnel pour DOMAIN_CODE

Livrables :
  [1] gate_engine.py — Framework d'exécution de gates
  [2] domain_grids/code.py — 6 gates (lint, sast, tests, complexity, types, secrets)
  [3] persistence.py — JSON Lines basique
  [4] test_gate_engine.py — Tests du Gate Engine lui-même
  [5] Premier run SOIC v3.0 sur AINOVA_BRAIN/ → Score de référence μ₀

Critère de succès :
  $ python -m soic_v3.cli evaluate --path AINOVA_BRAIN/ --domain CODE
  → Produit un rapport avec gates PASS/FAIL et score factuel

Outils à intégrer :
  - ruff (remplace flake8+isort+pyflakes — plus rapide, tout-en-un)
  - bandit (SAST Python)
  - radon (complexité cyclomatique)
  - mypy (type checking)
  - gitleaks (secrets)
  - pytest (test runner, déjà en place)


SPRINT 2 — Feedback Loop (Semaine 3, ~8h)
═══════════════════════════════════════════
Objectif : Boucle d'itération automatique

Livrables :
  [1] feedback_router.py — Génère des instructions correctives par gate FAIL
  [2] converger.py — Logique PASS/ITERATE/ABORT + plateau detection
  [3] Intégration avec le soic_engine.py existant

Critère de succès :
  $ python -m soic_v3.cli iterate --path AINOVA_BRAIN/ --max-iter 3
  → Évalue, génère feedback, re-évalue, track la convergence


SPRINT 3 — Multi-domain (Semaine 4-5, ~10h)
═══════════════════════════════════════════
Objectif : Couvrir PROMPT, INFRA, PROSE

Livrables :
  [1] domain_grids/prompt.py — Gates pour validation de prompts
  [2] domain_grids/infra.py — Gates pour YAML, Docker, K8s
  [3] domain_grids/prose.py — Gates pour documentation
  [4] Classification automatique du domaine

Critère de succès :
  $ python -m soic_v3.cli evaluate --path docs/ --domain PROSE
  $ python -m soic_v3.cli evaluate --path DEPLOYMENT/ --domain INFRA
  → Chaque domaine a ses propres gates pertinentes


SPRINT 4 — MCP + Dashboard (Semaine 6-7, ~10h)
═══════════════════════════════════════════
Objectif : SOIC v3.0 comme outil MCP + visualisation

Livrables :
  [1] MCP Tool soic_evaluate (appel depuis Claude Code)
  [2] MCP Resource soic_history (accès aux runs passés)
  [3] Dashboard terminal (convergence curves en ASCII ou Rich)
  [4] Export JSON/SARIF pour intégration CI/CD

Critère de succès :
  Depuis claude-code-cli :
  > "Évalue AINOVA_BRAIN avec SOIC"
  → Claude appelle le MCP tool, reçoit le rapport structuré


SPRINT 5 — CI/CD Integration (Semaine 8, ~5h)
═══════════════════════════════════════════
Objectif : SOIC v3.0 dans le pipeline GitHub Actions

Livrables :
  [1] Job GitHub Actions : soic-gate
  [2] Fail si gate critique FAIL
  [3] Rapport SARIF uploadé comme artifact
  [4] Badge dynamique μ dans README.md

Critère de succès :
  Push → CI lance SOIC v3.0 → Gate report dans les artifacts
  Badge README : "SOIC v3.0 | μ 8.7/10 | 17/20 gates"
```

---

## 4. CE QUI CHANGE POUR LE SCORE μ

### Prédiction honnête du premier run v3.0

Quand tu vas exécuter SOIC v3.0 sur le codebase actuel, voici ce qui va
probablement se passer :

```
Gate Engine v3.0 — Premier run sur AINOVA_BRAIN/
═══════════════════════════════════════════════════

DOMAIN_CODE Results:
┌────────┬──────────────────────────┬──────────┬────────────────────────────┐
│ Gate   │ Critère                  │ Status   │ Preuve attendue            │
├────────┼──────────────────────────┼──────────┼────────────────────────────┤
│ C-01   │ Syntaxe valide (ruff)    │ ⚠️ FAIL? │ Probablement des warnings  │
│ C-02   │ SAST (bandit)            │ ⚠️ FAIL? │ Findings medium/low        │
│ C-03   │ Tests passent            │ ❓ ???   │ Dépend du vrai pytest run  │
│ C-04   │ Complexité (radon)       │ ⚠️ FAIL? │ orchestrator.py = 1890 LOC │
│ C-05   │ Type safety (mypy)       │ ❌ FAIL  │ Quasi certain sans typing  │
│ C-06   │ Secrets (gitleaks)       │ ❓ ???   │ À vérifier                 │
└────────┴──────────────────────────┴──────────┴────────────────────────────┘

Prédiction : μ ≈ 5.0 - 7.0 / 10 (RÉEL)

vs.

SOIC v2.0 actuel : μ = 10.0 / 10 (AUTO-DÉCLARÉ)
```

**Ce delta est normal et sain.** C'est la différence entre un thermomètre
calibré et un thermomètre qui affiche toujours 37°C.

Le μ₀ de v3.0 sera plus bas, mais il sera VRAI. Et surtout : chaque
amélioration sera prouvée par un delta mesurable.

---

## 5. RISQUES ET MITIGATIONS

| Risque | Impact | Mitigation |
|---|---|---|
| Le vrai μ₀ est décourageant (ex: 4/10) | Démotivation | Normal : v3.0 est plus strict. Le chemin de 4→8 est plus satisfaisant que de rester à un faux 10. |
| Tests existants ne passent pas | Bloque Sprint 1 | Commencer par `pytest --co -q` (list sans run) pour compter les tests détectés. Fixer les imports cassés d'abord. |
| Trop de gates FAIL = bruit | Paralysie | Commencer avec 3 gates seulement (lint + tests + secrets), ajouter progressivement. |
| orchestrator.py trop complexe pour radon | Score C-04 bloqué | Définir un seuil réaliste (CC ≤ 15 au lieu de ≤ 10) puis réduire progressivement. |
| Scope creep vers AINOVA_OS v4 | Perte de focus | SOIC v3.0 est un OUTIL, pas un rewrite d'AINOVA_OS. Il se greffe, il ne remplace pas. |

---

## 6. DÉCISION ARCHITECTURALE FINALE

```
                    ┌─────────────────────────────┐
                    │   RECOMMANDATION STRATÉGIQUE │
                    └─────────────────────────────┘

  ❌ NE PAS : Créer une v4.0 / v5.0 / nouveau repo
  ❌ NE PAS : Réécrire le soic_engine.py existant
  ❌ NE PAS : Toucher aux 3 branches Opt A/B/C (archiver)

  ✅ FAIRE : Greffer soic_v3/ comme sous-module dans le repo existant
  ✅ FAIRE : Nettoyer les 26 répertoires → 2 (prod + archive)
  ✅ FAIRE : Obtenir le vrai μ₀ avant toute évolution
  ✅ FAIRE : Sprints de 1-2 semaines, livrables testables

  Temps total estimé : 48h sur 8 semaines (6h/semaine)
  Premier livrable fonctionnel : Sprint 1 (~15h)
```
