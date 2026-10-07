#!/usr/bin/env bash
#
# Testability audit for the backend. Prints Markdown and exits 1 if any HARD
# check has findings. Run from backend/: `bash scripts/testability-audit.sh`.
#
# HARD checks are rules the codebase is clean on today, so any hit is a
# regression and CI fails. ADVISORY checks list known debt; when one reaches
# zero, promote it to HARD. Rules are described in tests/README.md.
#
# Must stay bash 3.2-compatible (macOS default): feed checks into `report`
# with `report HARD < <(cmd)`, never `cmd | report HARD` — a pipeline runs
# `report` in a subshell and its failure counter is lost.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

HARD_FAILS=0

report() {
    local level="$1" title="$2" findings
    findings=$(cat)
    echo "### ${level}: ${title}"
    if [ -z "$findings" ]; then
        echo "none"
    else
        echo '```'
        echo "$findings"
        echo '```'
        [ "$level" = "HARD" ] && HARD_FAILS=$((HARD_FAILS + 1))
    fi
    echo
}

py_grep() { grep -rnE --include='*.py' "$@" 2>/dev/null; }

echo "## Testability audit"
echo

# --- HARD -------------------------------------------------------------------

report HARD "A1 LLM clients (ChatOpenAI) only in app/agents/" \
    < <(py_grep 'ChatOpenAI\(' app | grep -v '^app/agents/')

report HARD "A2 Google API clients (build()) only in app/tools/" \
    < <(py_grep '(^|[^_a-zA-Z.])build\(' app | grep -v '^app/tools/')

report HARD "A3 settings come from get_settings(), not os.environ/os.getenv" \
    < <(py_grep 'os\.(environ|getenv)' app)

report HARD "T1 tests never enter the app lifespan (starts the scheduler + Telegram poller)" \
    < <(py_grep '^[[:space:]]*(async +)?with +TestClient\(' tests)

report HARD "T2 no real sleeps in tests" \
    < <(py_grep '(^|[^.a-zA-Z_])time\.sleep\(' tests)

# --- ADVISORY ---------------------------------------------------------------

report ADVISORY "A4 raw httpx calls outside app/tools/ (move behind a tool function)" \
    < <(py_grep 'httpx\.(Client|AsyncClient|get|post)\(' app | grep -v '^app/tools/')

report ADVISORY "A5 hidden clock in agents/routers (inject 'now' or patch the module's datetime)" \
    < <(py_grep 'datetime\.(now|utcnow)\(|time\.time\(' app/agents app/routers app/main.py)

report ADVISORY "A6 settings read at import time (binds config before tests can override it)" \
    < <(py_grep '^[A-Za-z_][A-Za-z_0-9]* *= *get_settings\(\)' app)

untested_modules() {
    local f mod parent name
    for f in $(find app -name '*.py' ! -name '__init__.py' | sort); do
        grep -q '@testability-exempt' "$f" && continue
        mod=$(echo "${f%.py}" | tr '/' '.')
        parent=${mod%.*}
        name=${mod##*.}
        if ! grep -rqE --include='*.py' \
            "(from|import) ${mod}( |$)|from ${parent} import .*\b${name}\b" tests; then
            echo "$f"
        fi
    done
}

report ADVISORY "A7 module with no test importing it (opt out: '# @testability-exempt: <reason>')" \
    < <(untested_modules)

if [ "$HARD_FAILS" -gt 0 ]; then
    echo "**${HARD_FAILS} hard check(s) failed.**"
    exit 1
fi
echo "**All hard checks passed.**"
