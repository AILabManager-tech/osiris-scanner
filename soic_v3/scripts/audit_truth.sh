#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# SOIC v3.0 — Sprint 0 : Audit de vérité
# Mesure l'état RÉEL du codebase AINOVA_OS
# =============================================================================

# --- Configuration -----------------------------------------------------------
TARGET="${1:-/home/jarvis/projects/ai/ainova-os}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REPORT_DIR="${PROJECT_ROOT}/reports"
REPORT_FILE="${REPORT_DIR}/audit_baseline.md"

# Exclusions standard
EXCLUDE_DIRS="venv .venv node_modules site-packages __pycache__ .git"
FIND_EXCLUDES=""
for dir in $EXCLUDE_DIRS; do
    FIND_EXCLUDES="$FIND_EXCLUDES -not -path '*/${dir}/*'"
done

# --- Fonctions utilitaires ---------------------------------------------------
log() { echo "[AUDIT] $*"; }
separator() { echo "────────────────────────────────────────────────────"; }

install_tools() {
    log "Vérification et installation des outils d'audit..."
    local tools_to_install=()

    for tool in ruff bandit radon mypy pytest; do
        if ! command -v "$tool" &>/dev/null; then
            tools_to_install+=("$tool")
        fi
    done

    if [ ${#tools_to_install[@]} -gt 0 ]; then
        log "Installation : ${tools_to_install[*]}"
        pip3 install --quiet --user "${tools_to_install[@]}" 2>/dev/null || \
        pip3 install --quiet --break-system-packages --user "${tools_to_install[@]}" 2>/dev/null || \
        { log "ERREUR: Impossible d'installer ${tools_to_install[*]}"; exit 1; }
    fi

    log "Tous les outils sont disponibles."
}

# --- Vérifications préliminaires ---------------------------------------------
if [ ! -d "$TARGET" ]; then
    echo "ERREUR: Répertoire cible introuvable : $TARGET"
    exit 1
fi

mkdir -p "$REPORT_DIR"

log "Cible : $TARGET"
log "Rapport : $REPORT_FILE"
separator

# --- Installation des outils -------------------------------------------------
install_tools
separator

# =============================================================================
# MESURE 1 : Fichiers Python réels
# =============================================================================
log "1/7 — Comptage des fichiers Python réels..."

PY_COUNT=$(eval "find '$TARGET' -name '*.py' -type f $FIND_EXCLUDES" | wc -l)
log "   Fichiers Python : $PY_COUNT"

# =============================================================================
# MESURE 2 : Lignes de code réelles (LOC)
# =============================================================================
log "2/7 — Comptage des LOC réelles..."

ALL_PY_CONTENT=$(eval "find '$TARGET' -name '*.py' -type f $FIND_EXCLUDES -exec cat {} +")
LOC_TOTAL=$(echo "$ALL_PY_CONTENT" | wc -l)
LOC_CODE=$(echo "$ALL_PY_CONTENT" | grep -cvE '^\s*$|^\s*#' || true)
LOC_BLANK=$(echo "$ALL_PY_CONTENT" | grep -cE '^\s*$' || true)
LOC_COMMENT=$(echo "$ALL_PY_CONTENT" | grep -cE '^\s*#' || true)
unset ALL_PY_CONTENT

log "   LOC total : $LOC_TOTAL"
log "   Code      : $LOC_CODE"
log "   Vides     : $LOC_BLANK"
log "   Commentaires : $LOC_COMMENT"

# =============================================================================
# MESURE 3 : Tests détectés (pytest --co)
# Note: -o "addopts=" neutralise les options de pyproject.toml (ex: --cov)
# =============================================================================
log "3/7 — Détection des tests (pytest --co -q)..."

TESTS_DETECTED_OUTPUT=$(cd "$TARGET" && python3 -m pytest -o "addopts=" --continue-on-collection-errors --co -q 2>&1) || true
# Compter les lignes qui ressemblent à des chemins de tests collectés
TESTS_DETECTED=$(echo "$TESTS_DETECTED_OUTPUT" | grep -cE "::" || true)
TESTS_DETECTED_SUMMARY=$(echo "$TESTS_DETECTED_OUTPUT" | tail -5)

log "   Tests détectés : $TESTS_DETECTED"

# =============================================================================
# MESURE 4 : Tests qui passent réellement
# =============================================================================
log "4/7 — Exécution des tests (pytest --tb=line -q)..."

PYTEST_OUTPUT=$(cd "$TARGET" && python3 -m pytest -o "addopts=" --continue-on-collection-errors --tb=line -q 2>&1) || true
PYTEST_SUMMARY=$(echo "$PYTEST_OUTPUT" | tail -10)

# Extraire passed/failed/errors depuis la dernière ligne de résumé
PYTEST_RESULT_LINE=$(echo "$PYTEST_OUTPUT" | tail -3)
TESTS_PASSED=$(echo "$PYTEST_RESULT_LINE" | grep -oE '[0-9]+ passed' | head -1 | grep -oE '[0-9]+' || echo "0")
TESTS_FAILED=$(echo "$PYTEST_RESULT_LINE" | grep -oE '[0-9]+ failed' | head -1 | grep -oE '[0-9]+' || echo "0")
TESTS_ERRORS=$(echo "$PYTEST_RESULT_LINE" | grep -oE '[0-9]+ error' | head -1 | grep -oE '[0-9]+' || echo "0")
TESTS_WARNINGS=$(echo "$PYTEST_RESULT_LINE" | grep -oE '[0-9]+ warning' | head -1 | grep -oE '[0-9]+' || echo "0")

log "   Passed  : $TESTS_PASSED"
log "   Failed  : $TESTS_FAILED"
log "   Errors  : $TESTS_ERRORS"

# =============================================================================
# MESURE 5 : Ruff (linting)
# =============================================================================
log "5/7 — Analyse ruff..."

RUFF_STATS=$(cd "$TARGET" && ruff check . --statistics --exclude "venv,node_modules,.venv,__pycache__,site-packages" 2>&1) || true
RUFF_SUMMARY=$(echo "$RUFF_STATS" | tail -20)

# Extraire le nombre total depuis "Found N errors"
RUFF_VIOLATIONS=$(echo "$RUFF_STATS" | grep -oE 'Found [0-9]+ error' | grep -oE '[0-9]+' || echo "0")

log "   Violations ruff : $RUFF_VIOLATIONS"

# =============================================================================
# MESURE 6 : Bandit (SAST / sécurité)
# =============================================================================
log "6/7 — Analyse bandit..."

BANDIT_JSON="${REPORT_DIR}/bandit_baseline.json"
# bandit avec -f json envoie le JSON sur stdout, les warnings sur stderr
bandit -r "$TARGET/AINOVA_BRAIN/" "$TARGET/MODULES/" -f json -o "$BANDIT_JSON" 2>/dev/null || true

# Extraire les métriques du fichier JSON
BANDIT_METRICS=$(python3 -c "
import json, sys
try:
    with open('$BANDIT_JSON') as f:
        data = json.load(f)
    results = data.get('results', [])
    high = sum(1 for r in results if r.get('issue_severity') in ('HIGH', 'CRITICAL'))
    medium = sum(1 for r in results if r.get('issue_severity') == 'MEDIUM')
    low = sum(1 for r in results if r.get('issue_severity') == 'LOW')
    print(f'{high}|{medium}|{low}')
except Exception as e:
    print(f'0|0|0', file=sys.stdout)
    print(f'Bandit parse error: {e}', file=sys.stderr)
" 2>/dev/null || echo "0|0|0")

BANDIT_HIGH=$(echo "$BANDIT_METRICS" | cut -d'|' -f1)
BANDIT_MEDIUM=$(echo "$BANDIT_METRICS" | cut -d'|' -f2)
BANDIT_LOW=$(echo "$BANDIT_METRICS" | cut -d'|' -f3)
BANDIT_TOTAL=$((BANDIT_HIGH + BANDIT_MEDIUM + BANDIT_LOW))

log "   Bandit HIGH/CRIT : $BANDIT_HIGH"
log "   Bandit MEDIUM    : $BANDIT_MEDIUM"
log "   Bandit LOW       : $BANDIT_LOW"

# =============================================================================
# MESURE 7 : Radon (complexité cyclomatique)
# =============================================================================
log "7/7 — Analyse radon..."

RADON_JSON="${REPORT_DIR}/radon_baseline.json"
radon cc "$TARGET/AINOVA_BRAIN/" -a -j > "$RADON_JSON" 2>/dev/null || echo "{}" > "$RADON_JSON"

RADON_AVERAGE=$(radon cc "$TARGET/AINOVA_BRAIN/" -a 2>/dev/null | grep -oE 'Average complexity: [A-Z] \([0-9.]+\)' || echo "N/A")
RADON_SCORE=$(echo "$RADON_AVERAGE" | grep -oE '[0-9]+\.[0-9]+' || echo "N/A")
RADON_GRADE=$(echo "$RADON_AVERAGE" | grep -oE '[A-Z] \(' | tr -d ' (' || echo "N/A")

log "   Complexité moyenne : $RADON_AVERAGE"

separator
log "Audit terminé. Génération du rapport..."

# =============================================================================
# GÉNÉRATION DU RAPPORT
# =============================================================================

# Versions des outils
RUFF_VER=$(ruff --version 2>/dev/null || echo "N/A")
BANDIT_VER=$(bandit --version 2>&1 | head -1 || echo "N/A")
RADON_VER=$(radon --version 2>/dev/null || echo "N/A")
MYPY_VER=$(mypy --version 2>/dev/null || echo "N/A")
PYTEST_VER=$(python3 -m pytest --version 2>/dev/null || echo "N/A")

cat > "$REPORT_FILE" << HEREDOC
# SOIC v3.0 — Rapport d'Audit de Vérité (Baseline)

**Date :** $(date '+%Y-%m-%d %H:%M:%S')
**Cible :** \`$TARGET\`
**Outils :** ruff $RUFF_VER, $BANDIT_VER, radon $RADON_VER, $MYPY_VER, $PYTEST_VER

---

## Tableau comparatif : v2.0 déclaré vs Réalité mesurée

| Métrique | Valeur v2.0 déclarée | Valeur réelle mesurée | Delta |
|---|---|---|---|
| Fichiers Python | 55 | **$PY_COUNT** | $(python3 -c "print(f'{$PY_COUNT - 55:+d}')") |
| LOC totales | 15 498 | **$LOC_TOTAL** | $(python3 -c "print(f'{$LOC_TOTAL - 15498:+d}')") |
| LOC code (hors vides/commentaires) | 9 535 | **$LOC_CODE** | $(python3 -c "print(f'{$LOC_CODE - 9535:+d}')") |
| Tests détectés | 69 | **$TESTS_DETECTED** | $(python3 -c "print(f'{$TESTS_DETECTED - 69:+d}')") |
| Tests PASS | 69 (100%) | **$TESTS_PASSED** | $(python3 -c "print(f'{$TESTS_PASSED - 69:+d}')") |
| Tests FAIL | 0 | **$TESTS_FAILED** | +$TESTS_FAILED |
| Tests ERRORS | 0 | **$TESTS_ERRORS** | +$TESTS_ERRORS |
| Violations ruff | _(non mesuré)_ | **$RUFF_VIOLATIONS** | — |
| Bandit HIGH/CRIT | _(non audité)_ | **$BANDIT_HIGH** | — |
| Bandit MEDIUM | _(non audité)_ | **$BANDIT_MEDIUM** | — |
| Bandit LOW | _(non audité)_ | **$BANDIT_LOW** | — |
| Bandit total | _(non audité)_ | **$BANDIT_TOTAL** | — |
| Radon complexité moyenne | _(non mesuré)_ | **$RADON_SCORE ($RADON_GRADE)** | — |
| Score mu SOIC v2.0 | 7.86 / 10 | _(auto-évalué, non vérifiable)_ | — |

---

## Détail par mesure

### 1. Fichiers Python réels
- **Nombre :** $PY_COUNT fichiers
- **Exclusions :** venv/, .venv/, node_modules/, site-packages/, \_\_pycache\_\_/

### 2. Lignes de code
| Type | Lignes | % |
|---|---|---|
| Code effectif | $LOC_CODE | $(python3 -c "print(f'{$LOC_CODE/$LOC_TOTAL*100:.1f}' if $LOC_TOTAL > 0 else 'N/A')")% |
| Commentaires | $LOC_COMMENT | $(python3 -c "print(f'{$LOC_COMMENT/$LOC_TOTAL*100:.1f}' if $LOC_TOTAL > 0 else 'N/A')")% |
| Lignes vides | $LOC_BLANK | $(python3 -c "print(f'{$LOC_BLANK/$LOC_TOTAL*100:.1f}' if $LOC_TOTAL > 0 else 'N/A')")% |
| **Total** | **$LOC_TOTAL** | 100% |

### 3. Tests détectés (pytest --co -q)
\`\`\`
$TESTS_DETECTED_SUMMARY
\`\`\`

### 4. Tests exécutés (pytest --tb=line -q)
\`\`\`
$PYTEST_SUMMARY
\`\`\`

| Résultat | Nombre |
|---|---|
| Passed | $TESTS_PASSED |
| Failed | $TESTS_FAILED |
| Errors | $TESTS_ERRORS |
| Warnings | $TESTS_WARNINGS |

### 5. Ruff (linting)
**Violations totales :** $RUFF_VIOLATIONS

\`\`\`
$RUFF_SUMMARY
\`\`\`

### 6. Bandit (SAST / sécurité)
**Rapport JSON :** \`reports/bandit_baseline.json\`

| Sévérité | Nombre |
|---|---|
| HIGH / CRITICAL | $BANDIT_HIGH |
| MEDIUM | $BANDIT_MEDIUM |
| LOW | $BANDIT_LOW |
| **Total** | **$BANDIT_TOTAL** |

### 7. Radon (complexité cyclomatique)
**Rapport JSON :** \`reports/radon_baseline.json\`
**Complexité moyenne :** $RADON_AVERAGE

---

## Conclusion

Ce rapport établit la **baseline de vérité** du codebase AINOVA_OS.
Les valeurs mesurées par des outils externes remplacent les auto-évaluations de SOIC v2.0.
Ce mu0 mesuré servira de point de départ pour la convergence SOIC v3.0.

> **Principe v3.0 :** Le LLM GÉNÈRE. Les OUTILS VÉRIFIENT. Le score mu = ratio de gates PASS.
HEREDOC

log "Rapport généré : $REPORT_FILE"
separator
log "Fichiers produits :"
log "  - $REPORT_FILE"
log "  - $BANDIT_JSON"
log "  - $RADON_JSON"
echo ""
log "Audit de vérité terminé."
