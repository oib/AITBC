#!/usr/bin/env bash
# run-suite-manual.sh — replay .gitea/workflows/ci.yml on a scratch clone on
# the runner host, while the repo's Actions unit is kept off by policy.
#
# It is the pre-push gate for the dark-CI era: bundle the ref, ship it to the
# runner, clone with real .git (the CLI suite needs it), build the cached
# venv exactly like the workflow, run every suite under a timeout, and write
# one junit XML + log per suite. Failures listed in
# scripts/ci/manual-ci-known-red.txt are tolerated; anything red that is NOT
# on that list fails the run.
#
# Usage:
#   scripts/ci/run-suite-manual.sh [--ref REF] [--host HOST] [--timeout SECS]
#                                  [--out-dir DIR] [--with-contracts]
#                                  [--keep-scratch] [-h|--help]
#
#   --ref REF           commit-ish to test (default: HEAD of the invoking
#                       checkout — run this from your candidate worktree)
#   --host HOST         ssh host to run on (default: gitea-runner;
#                       AITBC_CI_HOST overrides). Live validators are refused.
#   --timeout SECS      per-suite timeout (default: 1500; hardhat: 900)
#   --out-dir DIR       junit + logs destination (default: ./ci-manual-out)
#   --with-contracts    also run npm ci + npx hardhat test (off by default:
#                       the task list is the python suites; forge is never
#                       attempted — no forge on the runner)
#   --keep-scratch      keep the remote scratch dir for debugging
#
# Exit codes: 0 = green modulo tolerated known-red; 1 = at least one new red;
#             2 = usage or infrastructure error.
#
# Never run this on a live validator. The five fleet hosts are refused
# outright; do not widen the allowlist without the operator.

set -euo pipefail

HOST="${AITBC_CI_HOST:-gitea-runner}"
REF="HEAD"
TIMEOUT=1500
OUT_DIR=""
WITH_CONTRACTS=0
KEEP_SCRATCH=0

usage() { sed -n '2,32p' "$0"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --with-contracts) WITH_CONTRACTS=1; shift ;;
    --keep-scratch) KEEP_SCRATCH=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$HOST" in
  hub|hub1|node0|node1|node2|hub.aitbc|hub1.aitbc|*.aitbc.bubuit.net|localhost|127.0.0.1|"")
    echo "refusing to run on live validator / local host: '$HOST'" >&2
    echo "default host is gitea-runner; override with --host or AITBC_CI_HOST" >&2
    exit 2 ;;
esac

SRC="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "not inside a git checkout" >&2; exit 2; }
SHA="$(git -C "$SRC" rev-parse "$REF")" || { echo "cannot resolve ref: $REF" >&2; exit 2; }
KNOWN_RED="${KNOWN_RED:-$SRC/scripts/ci/manual-ci-known-red.txt}"
[ -f "$KNOWN_RED" ] || { echo "known-red list missing: $KNOWN_RED" >&2; exit 2; }
OUT_DIR="${OUT_DIR:-$PWD/ci-manual-out}"
mkdir -p "$OUT_DIR"

BUNDLE_LOCAL="$(mktemp /tmp/aitbc-ci-XXXXXX.bundle)"
TMP_REF="refs/manual-ci/$(date +%s)-$$"
cleanup_local() { rm -f "$BUNDLE_LOCAL"; git -C "$SRC" update-ref -d "$TMP_REF" 2>/dev/null || true; }
trap cleanup_local EXIT

git -C "$SRC" update-ref "$TMP_REF" "$SHA"
git -C "$SRC" bundle create -q "$BUNDLE_LOCAL" "$TMP_REF"

BUNDLE_REMOTE="/tmp/aitbc-ci-$SHA.bundle"
SCRATCH_NAME="aitbc-ci-$(date +%s)-$$"
OUT_REMOTE="/tmp/$SCRATCH_NAME-out"

echo "host=$HOST ref=$REF sha=$SHA scratch=/tmp/$SCRATCH_NAME"
scp -q "$BUNDLE_LOCAL" "$HOST:$BUNDLE_REMOTE"

# ---------------------------------------------------------------------------
# Remote driver: clone the bundle into scratch, build the cached venv the way
# the workflow does, then run every suite/check under `timeout` and emit one
# junit XML + one log per suite into the remote out dir.
# ---------------------------------------------------------------------------
ssh "$HOST" bash -s -- "$SHA" "$BUNDLE_REMOTE" "$SCRATCH_NAME" "$TIMEOUT" "$WITH_CONTRACTS" "$TMP_REF" <<'REMOTE'
set -euo pipefail
SHA="$1"; BUNDLE="$2"; SCRATCH_NAME="$3"; TIMEOUT="$4"; WITH_CONTRACTS="$5"; BUNDLE_REF="$6"
SCRATCH="/tmp/$SCRATCH_NAME"
OUT="/tmp/$SCRATCH_NAME-out"
mkdir -p "$OUT"

git init -q "$SCRATCH"
git -C "$SCRATCH" fetch -q "$BUNDLE" "$BUNDLE_REF"
git -C "$SCRATCH" checkout -q -b manual-ci FETCH_HEAD
rm -f "$BUNDLE"

cd "$SCRATCH"
python3 -c "import sys; assert sys.version_info[:3] == (3,13,5), f'Python {sys.version} — AITBC pins exactly 3.13.5'"

bash scripts/ci/setup-python-venv.sh \
  --cache-root /opt/gitea-runner/.cache/aitbc-venvs \
  --venv-dir ./venv \
  --extra-packages "-r requirements-dev.txt" \
  --mode copy
./venv/bin/python -m pip install -q --force-reinstall --no-deps -e cli

# The workflow's job env, with scratch-unique paths so the api-key lockfile
# and ipfs/oracle dirs cannot collide with the host's own /var/lib/aitbc.
export PYTHON="./venv/bin/python"
export API_KEY_STORAGE_PATH="$SCRATCH/api-keys.json"
export AITBC_IPFS_DIR="$SCRATCH/ipfs"
export AITBC_ORACLE_DIR="$SCRATCH/oracle"
export PYTHONPATH=""

junit_fail() {  # synthesize a one-case failing junit for check suites/timeouts
  python3 - "$1" "$2" "$3" <<'PY'
import html, os, sys
suite, reason, out = sys.argv[1], sys.argv[2], sys.argv[3]
log = out[:-4] + ".log" if out.endswith(".xml") else out + ".log"
body = html.escape(open(log, errors="replace").read()[-4000:]) if os.path.exists(log) else ""
print(f'<?xml version="1.0"?><testsuite name="{suite}" tests="1" failures="1" skipped="0" errors="0">'
      f'<testcase classname="check" name="{suite}" time="0">'
      f'<failure message="{html.escape(reason)}">{body}</failure></testcase></testsuite>',
      file=open(out, "w"))
PY
}

junit_skip() {
  printf '<?xml version="1.0"?><testsuite name="%s" tests="0" failures="0" skipped="1" errors="0"><testcase classname="check" name="%s" time="0"><skipped message="%s"/></testcase></testsuite>\n' \
    "$1" "$1" "$2" > "$3"
}

# name|command|env  — pytest suites get real junitxml; everything else is a
# one-case check whose junit is synthesized from the exit code.
run_pytest() {  # name, extra_env, pytest args...
  local name="$1" env="$2"; shift 2
  local t0 rc
  t0=$(date +%s)
  set +e
  if [ -n "$env" ]; then
    timeout "$TIMEOUT" env $env ./venv/bin/python -m pytest "$@" --junitxml="$OUT/$name.xml" -q > "$OUT/$name.log" 2>&1
  else
    timeout "$TIMEOUT" ./venv/bin/python -m pytest "$@" --junitxml="$OUT/$name.xml" -q > "$OUT/$name.log" 2>&1
  fi
  rc=$?
  set -e
  if [ "$rc" -eq 124 ]; then
    junit_fail "$name" "timeout after ${TIMEOUT}s" "$OUT/$name.xml"
  elif [ ! -s "$OUT/$name.xml" ]; then
    junit_fail "$name" "no junit emitted (rc=$rc)" "$OUT/$name.xml"
  fi
  printf '%s\t%s\t%s\n' "$name" "$rc" "$(( $(date +%s) - t0 ))" >> "$OUT/results.tsv"
}

run_check() {  # name, env, command...
  local name="$1" env="$2"; shift 2
  local t0 rc
  t0=$(date +%s)
  set +e
  if [ -n "$env" ]; then
    timeout "$TIMEOUT" env $env "$@" > "$OUT/$name.log" 2>&1
  else
    timeout "$TIMEOUT" "$@" > "$OUT/$name.log" 2>&1
  fi
  rc=$?
  set -e
  if [ "$rc" -eq 0 ]; then
    printf '<?xml version="1.0"?><testsuite name="%s" tests="1" failures="0" skipped="0" errors="0"><testcase classname="check" name="%s" time="0"/></testsuite>\n' "$name" "$name" > "$OUT/$name.xml"
  elif [ "$rc" -eq 124 ]; then
    junit_fail "$name" "timeout after ${TIMEOUT}s" "$OUT/$name.xml"
  else
    junit_fail "$name" "exit code $rc" "$OUT/$name.xml"
  fi
  printf '%s\t%s\t%s\n' "$name" "$rc" "$(( $(date +%s) - t0 ))" >> "$OUT/results.tsv"
}

: > "$OUT/results.tsv"

# Checks first — fast fail-fast signal before the expensive test suites.
run_check lint-strict      "" ./venv/bin/python -m ruff check .
run_check c901-ratchet     "" bash scripts/ci/check-c901-ratchet.sh
run_check except-ratchet   "" bash scripts/ci/check-except-ratchet.sh
run_check no-float-money   "" ./venv/bin/python scripts/lint/no_float_money.py
run_check typecheck        "" bash scripts/ci/mypy-precommit.sh
run_check version-check    "" ./venv/bin/python scripts/ci/check-version-consistency.py
run_check suite-parity     "" ./venv/bin/python scripts/ci/check_test_suite_parity.py
run_check openapi-check    "" bash scripts/ci/check-openapi-drift.sh
run_check cli-docs         "" bash scripts/ci/check-cli-docs.sh
run_check validate-docs    "" bash scripts/validate_docs.sh
run_check master-index     "" ./venv/bin/python scripts/docs/gen_master_index.py --check
run_check check-ports      "" ./venv/bin/python scripts/docs/check_ports.py
run_check bind-policy      "" ./venv/bin/python scripts/docs/check_bind_policy.py
run_check live-dry-run     "WALLET_URL=http://127.0.0.1:1 BLOCKCHAIN_RPC_URL=http://127.0.0.1:1" bash scripts/ci/live-scenario-dry-run.sh

# Test suites — same targets as the workflow.
run_pytest unit       "PYTHONPATH=apps/blockchain-node/src" tests/unit mcp-server/tests
run_pytest apps       "PYTHONPATH=apps/blockchain-node/src" \
  --deselect=apps/coordinator-api/tests/test_phase8_integration.py \
  --deselect=apps/coordinator-api/tests/test_zk_receipt.py \
  apps/coordinator-api/tests/test_*.py apps/coordinator-api/tests/integration \
  apps/blockchain-node/tests
run_pytest governance "" apps/governance/tests
run_pytest critical   "" \
  apps/exchange/tests apps/api-gateway/tests apps/wallet/tests apps/market/tests \
  apps/trading/tests apps/agent-coordinator/tests apps/bridge-monitor/tests \
  tests/security tests/core tests/property_tests tests/smoke
run_pytest cli        "WALLET_URL=http://127.0.0.1:1 BLOCKCHAIN_RPC_URL=http://127.0.0.1:1" \
  cli/tests tests/cli tests/test_cli_docs_sync.py tests/test_syspath_hygiene.py

if [ "$WITH_CONTRACTS" = 1 ] && command -v npm >/dev/null 2>&1; then
  t0=$(date +%s)
  set +e
  (cd apps/zk-circuits && npm ci --no-audit --no-fund >/dev/null 2>&1)
  (cd contracts && npm ci --no-audit --no-fund >/dev/null 2>&1 && timeout 900 npx hardhat test) \
    > "$OUT/hardhat.log" 2>&1
  rc=$?
  set -e
  if [ "$rc" -eq 0 ]; then
    n=$(grep -c 'passing' "$OUT/hardhat.log" || true)
    printf '<?xml version="1.0"?><testsuite name="hardhat" tests="1" failures="0" skipped="0" errors="0"><testcase classname="check" name="hardhat" time="0"/></testsuite>\n' > "$OUT/hardhat.xml"
  else
    junit_fail hardhat "exit code $rc" "$OUT/hardhat.xml"
  fi
  printf 'hardhat\t%s\t%s\n' "$rc" "$(( $(date +%s) - t0 ))" >> "$OUT/results.tsv"
elif [ "$WITH_CONTRACTS" != 1 ]; then
  junit_skip hardhat "--with-contracts not passed" "$OUT/hardhat.xml"
  printf 'hardhat\t0\t0\n' >> "$OUT/results.tsv"
else
  junit_skip hardhat "npm absent on runner" "$OUT/hardhat.xml"
  printf 'hardhat\t0\t0\n' >> "$OUT/results.tsv"
fi
REMOTE
rc_remote=$?
[ "$rc_remote" -eq 0 ] || { echo "remote driver failed rc=$rc_remote" >&2; exit 2; }

scp -qr "$HOST:/tmp/$SCRATCH_NAME-out/." "$OUT_DIR/"

if [ "$KEEP_SCRATCH" -eq 1 ]; then
  echo "scratch kept: $HOST:/tmp/$SCRATCH_NAME"
else
  ssh "$HOST" "rm -rf /tmp/$SCRATCH_NAME /tmp/$SCRATCH_NAME-out /tmp/aitbc-ci-$SHA.bundle"
fi
LEFT=$(ssh "$HOST" 'find /tmp -maxdepth 1 -name "aitbc-ci-*" | wc -l')

# ---------------------------------------------------------------------------
# Local verdict: parse junit, diff failures against the known-red list.
# ---------------------------------------------------------------------------
set +e
python3 - "$OUT_DIR" "$KNOWN_RED" <<'PY'
import re, sys, xml.etree.ElementTree as ET
from pathlib import Path

out_dir, known_path = Path(sys.argv[1]), Path(sys.argv[2])
known = {}
for line in known_path.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    ident, _, note = line.partition("\t")
    known[ident.strip()] = note.strip()

results = {}
for tsv in out_dir.glob("results.tsv"):
    for line in tsv.read_text().splitlines():
        name, rc, wall = line.split("\t")
        results[name] = (int(rc), int(wall))

new_red, tolerated, stale_tol, skipped = [], [], [], []
seen_ids = set()
for xml in sorted(out_dir.glob("*.xml")):
    tree = ET.parse(xml)
    for ts in tree.getroot().iter("testsuite"):
        suite = xml.stem  # junit internal name is always "pytest"; the file name is ours
        fails = [tc for tc in ts.iter("testcase")
                 if tc.find("failure") is not None or tc.find("error") is not None]
        skips = [tc for tc in ts.iter("testcase") if tc.find("skipped") is not None]
        npass = int(ts.get("tests", "0")) - len(fails) - len(skips)
        rc, wall = results.get(suite, (0, 0))
        if skips and int(ts.get("tests", "0")) == 0:
            skipped.append(suite)
            print(f"SKIP  {suite:<16} {skips[0].find('skipped').get('message','')}")
            continue
        failing_ids = {f"{tc.get('classname')}::{tc.get('name')}" for tc in fails}
        seen_ids |= failing_ids
        new = sorted(failing_ids - set(known))
        tol = sorted(failing_ids & set(known))
        if new:
            new_red.append((suite, new))
            print(f"NEW-RED {suite:<13} {npass}p/{len(fails)}f  ({wall}s)")
            for t in new[:4]:
                print(f"         {t}")
            if len(new) > 4:
                print(f"         … and {len(new)-4} more")
        elif fails:
            tolerated.append((suite, tol))
            print(f"TOLER {suite:<14} {npass}p/{len(fails)}f  ({wall}s)  all {len(tol)} failure(s) tolerated")
        else:
            print(f"PASS  {suite:<14} {npass}p/{len(skips)}s  ({wall}s)")

for ident in set(known) - seen_ids:
    # An entry that never fired means the debt cleared (or the test moved) —
    # report it so the tolerance list cannot silently mask a renamed failure.
    stale_tol.append(ident)
    print(f"STALE-TOLERANCE {ident}  (did not fire — debt cleared or renamed; remove the entry)")

print()
if new_red:
    total = sum(len(n) for _, n in new_red)
    print(f"RESULT: FAIL — {total} new red across {len(new_red)} suite(s); tolerated {sum(len(t) for _, t in tolerated)}")
    sys.exit(1)
print(f"RESULT: OK — 0 new red; {sum(len(t) for _, t in tolerated)} tolerated failure(s); {len(stale_tol)} stale tolerance(s)")
sys.exit(0)
PY
rc_verdict=$?
set -e

echo
echo "junit+logs: $OUT_DIR"
echo "scratch leftovers on $HOST: $LEFT"
exit "$rc_verdict"
