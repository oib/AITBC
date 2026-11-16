#!/bin/bash
# Coverage-floor ratchet for the money/consensus paths (#1860 Phase 7 Tier-2).
#
# Same "baseline + gate the delta" mechanism as check-c901-ratchet.sh, applied
# to coverage.py percent_covered per file. A file whose measured coverage drops
# below its floor in scripts/ci/coverage-baseline.txt fails the gate. Floors are
# the measured values rounded DOWN to the integer, so sub-percent noise cannot
# trip it. When coverage legitimately improves, regenerate:
#
#   scripts/ci/check-coverage-ratchet.sh --update
#
# WHAT IS MEASURED (derived selection — do not hand-list test files):
#
#   Run A — the blockchain-node critical paths. The -k expression selects every
#   test whose name mentions a money/consensus concern; pytest's own pythonpath
#   config (pyproject.toml [tool.pytest.ini_options]) puts
#   apps/blockchain-node/src on sys.path, and the explicit PYTHONPATH below
#   repeats it plus the editable-package src dirs so the script also works when
#   invoked outside the repo's pytest config resolution:
#
#     PYTHONPATH=apps/blockchain-node/src:packages/py/aitbc-sdk/src:packages/py/aitbc-crypto/src #       $PYTHON -m pytest apps/blockchain-node/tests #       -k "consensus or cross_chain or bridge or settlement or state_transition or escrow or attestation or poa or slashing" #       --cov=aitbc_chain.consensus --cov=aitbc_chain.cross_chain #       --cov=aitbc_chain.state --cov=aitbc_chain.contracts.escrow #       --cov=aitbc_chain.rpc.escrow_routes
#
#   Run B — the coordinator payments context, appended onto Run A's .coverage
#   data so the JSON report is the UNION of both runs (pytest-cov --cov-append):
#
#     PYTHONPATH=<same> #       $PYTHON -m pytest apps/coordinator-api/tests -k "payment or escrow" #       --cov=aitbc_chain.consensus --cov=aitbc_chain.cross_chain #       --cov=aitbc_chain.state --cov=aitbc_chain.contracts.escrow #       --cov=aitbc_chain.rpc.escrow_routes --cov=coordinator_api.contexts.payments #       --cov-append --cov-report=json:<tmp>/coverage.json
#
#   Runtime is ~10-12 min on a dev node (Run A alone was ~8.5 min / 2781 tests
#   on node2). That is why this is wired into run-suite-manual.sh / ci.yml as a
#   check, NOT into pre-commit.
#
# A nonzero pytest exit does NOT by itself fail this gate — test redness is
# gated by the suite runs; coverage floors are the delta this ratchet owns.
# But if pytest dies before writing the JSON report the script fails closed.
#
# Known gap (documented, accepted): settlement_coordinator.py measures 0% —
# no test in the selection imports it. Its floor is 0 until coverage lands;
# --update will then raise it automatically.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
BASELINE="scripts/ci/coverage-baseline.txt"

PYTHON="$("$(dirname "${BASH_SOURCE[0]}")/repo-python.sh")" || exit 1

# pytest-cov + coverage must exist — a missing plugin makes --cov a hard
# pytest error anyway, but check up front for a clear message (#981 pattern:
# "checked nothing" must never read as green).
if ! "$PYTHON" -c 'import pytest_cov, coverage' >/dev/null 2>&1; then
  echo "coverage ratchet: pytest-cov/coverage not importable for '$PYTHON'." >&2
  echo "   This check measured nothing; that is not a pass." >&2
  echo "   Install: $PYTHON -m pip install -r requirements-dev.txt" >&2
  echo "   Or set PYTHON=/opt/aitbc/venv/bin/python." >&2
  exit 1
fi

COV_PKGS="aitbc_chain.consensus aitbc_chain.cross_chain aitbc_chain.state aitbc_chain.contracts.escrow aitbc_chain.rpc.escrow_routes"
COV_ARGS=()
for pkg in $COV_PKGS; do COV_ARGS+=(--cov="$pkg"); done

WORK="$(mktemp -d)"
REPORT="$WORK/coverage.json"
trap 'rm -rf "$WORK"; rm -f "$REPO_ROOT"/.coverage "$REPO_ROOT"/.coverage.*' EXIT
# A stale .coverage from an earlier run would silently merge into ours.
rm -f .coverage .coverage.*

export PYTHONPATH="apps/blockchain-node/src:packages/py/aitbc-sdk/src:packages/py/aitbc-crypto/src:apps/coordinator-api/src"

node_rc=0
"$PYTHON" -m pytest apps/blockchain-node/tests \
  -k "consensus or cross_chain or bridge or settlement or state_transition or escrow or attestation or poa or slashing" \
  "${COV_ARGS[@]}" -q || node_rc=$?

coord_rc=0
"$PYTHON" -m pytest apps/coordinator-api/tests -k "payment or escrow" \
  "${COV_ARGS[@]}" --cov=coordinator_api.contexts.payments \
  --cov-append --cov-report=json:"$REPORT" -q || coord_rc=$?

if [ "$coord_rc" -ne 0 ]; then
  echo "coverage ratchet: coordinator payments pytest exited $coord_rc — see output above." >&2
fi
if [ "$node_rc" -ne 0 ]; then
  echo "coverage ratchet: WARNING — blockchain-node selection exited $node_rc (flaky or red tests still produce coverage data; redness is gated by the suite runs)." >&2
fi
if [ ! -s "$REPORT" ]; then
  echo "coverage ratchet: no coverage JSON produced — the measurement did not run; this is not a pass." >&2
  exit 1
fi

if [ "${1:-}" = "--update" ]; then
  "$PYTHON" - "$REPORT" "$BASELINE" <<'PYEOF'
import json, math, sys
report, baseline = sys.argv[1], sys.argv[2]
d = json.load(open(report))
rows = []
for f, s in sorted(d['files'].items()):
    rows.append(f"{math.floor(s['summary']['percent_covered']):3d} {f}")
head = [
    '# Coverage floors for the money/consensus ratchet (#1860).',
    '# Format: <floor_pct> <repo-relative path>. Floors are the measured',
    '# percent_covered rounded DOWN to the integer, so sub-percent noise cannot',
    '# trip the gate. Regenerate ONLY via scripts/ci/check-coverage-ratchet.sh --update.',
    '#',
]
open(baseline, 'w').write('\n'.join(head + rows) + '\n')
print(f'coverage baseline updated: {len(rows)} files')
PYEOF
  exit 0
fi

"$PYTHON" - "$REPORT" "$BASELINE" <<'PYEOF'
import json, sys
report, baseline = sys.argv[1], sys.argv[2]

base = {}
for line in open(baseline):
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    floor, _, path = line.partition(' ')
    base[path.strip()] = int(floor)

d = json.load(open(report))
measured = {f: s['summary']['percent_covered'] for f, s in d['files'].items()}

status = 0
for path, floor in sorted(base.items()):
    if path not in measured:
        print(f'coverage ratchet: STALE floor {path} (no longer measured — module moved or --cov target dropped); run --update')
        continue
    pct = measured[path]
    if pct < floor:
        print(f'coverage regression: {path} is {pct:.2f}% (floor {floor}%)')
        status = 1
    elif pct >= floor + 1:
        print(f'coverage improvement: {path} is {pct:.2f}% (floor {floor}%) — run scripts/ci/check-coverage-ratchet.sh --update')

new_files = sorted(set(measured) - set(base))
for path in new_files:
    print(f'coverage ratchet: WARNING {path} is measured ({measured[path]:.2f}%) but has no floor — run --update to pin it')

if status == 0:
    print(f'coverage ratchet: no coverage drop across {len(base)} floored files (total {d["totals"]["percent_covered"]:.2f}%)')
else:
    print('''
A money/consensus path lost coverage. Add or fix tests that exercise the
dropped lines — do NOT regenerate the baseline to hide the loss. Re-run
with --update only after coverage legitimately improved or the measured
set intentionally changed:

    scripts/ci/check-coverage-ratchet.sh --update
''', file=sys.stderr)
sys.exit(status)
PYEOF
