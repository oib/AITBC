#!/usr/bin/env bash
# =============================================================================
# Test: backend-prune-instances.sh (PILOT-46 / ABS-546, AC3)
# =============================================================================
# Exercises the seat_spawn prune tool with a STUB psql (no real database), so
# the safety contract is asserted mechanically:
#   - dry-run is the default: a CSV backup is written but NO DELETE is issued
#   - --apply issues the DELETE (after the backup)
#   - the instance_id pattern is passed as a bound psql variable (-v pat=…),
#     never concatenated into SQL
#   - missing --pattern / missing database URL fail with a setup error (exit 2)
#
# Run from repo root: bash tests/test-backend-prune-instances.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PRUNE="$REPO_ROOT/scripts/backend-prune-instances.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

ok()   { TOTAL=$((TOTAL+1)); PASS=$((PASS+1)); echo -e "  ${GREEN}PASS${NC} $1"; }
# bad() takes an optional 2nd arg: the ACTUAL haystack the assertion saw. On a
# failure we print it (indented) so the suite shows WHAT the tool emitted, not
# just "missing: <string>" (AC3 — a suite that hides the real output is itself a
# diagnostic defect).
bad()  { TOTAL=$((TOTAL+1)); FAIL=$((FAIL+1)); echo -e "  ${RED}FAIL${NC} $1";
         [ "$#" -ge 2 ] && printf '%s\n' "$2" | sed 's/^/         actual| /'; return 0; }
assert_contains() { if echo "$1" | grep -qF -- "$2"; then ok "$3"; else bad "$3 (missing: $2)" "$1"; fi; }
assert_absent()   { if echo "$1" | grep -qF -- "$2"; then bad "$3 (unexpected: $2)" "$1"; else ok "$3"; fi; }
assert_eq()       { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (want '$2' got '$1')"; fi; }

# work/scratch is a gitignored RUNTIME dir — it does not exist in a fresh
# checkout, so mktemp -d into it fails there, leaving WORK empty and cascading
# into 11 spurious failures (exit 2 "backup dir does not exist"). Create it
# first, and fail loudly if the workdir still cannot be made (AC1/AC2 — the red
# main was this test's precondition, not the tool).
mkdir -p "$REPO_ROOT/work/scratch"
WORK="$(mktemp -d "$REPO_ROOT/work/scratch/prune-test-XXXXXX")" \
    || { echo "test-backend-prune-instances: cannot create workdir under work/scratch" >&2; exit 1; }
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin"

# ---- stub psql: log every invocation, canned count, materialise \copy file --
# The tool feeds SQL on STDIN (not -c), because psql only interpolates :'pat'
# for stdin/-f. So the stub captures stdin and asserts against that, plus argv
# (the -v pat=… bound variable still travels in argv).
cat > "$WORK/bin/psql" <<'STUB'
#!/usr/bin/env bash
sql="$(cat)"                                        # the SQL the tool piped in
echo "PSQL $* :: $sql" >> "$PSQL_LOG"
case "$sql" in
  *"count(*)"*)  echo "3" ;;                         # canned match count
  *"TO STDOUT"*) echo "instance_id" ;;               # CSV streamed to the tool's redirect
esac
exit 0
STUB
chmod +x "$WORK/bin/psql"
export PSQL="$WORK/bin/psql"
export PSQL_LOG="$WORK/psql.log"

echo "== AC3: dry-run default =="
: > "$PSQL_LOG"
out="$(bash "$PRUNE" --pattern '^devops01\.local-' --database-url 'postgres://x' --backup-dir "$WORK" 2>&1)"
rc=$?
log="$(cat "$PSQL_LOG")"
assert_eq "$rc" "0" "dry-run exits 0"
assert_contains "$out" "3 row(s) match" "reports match count from psql"
assert_contains "$out" "DRY-RUN" "announces dry-run"
assert_contains "$log" "count(*)" "issued a count query"
assert_contains "$log" "TO STDOUT" "wrote a CSV backup"
assert_contains "$log" "pat=^devops01\\.local-" "pattern passed as bound psql variable"
assert_absent "$log" "DELETE" "dry-run issues NO DELETE"
if ls "$WORK"/seat_spawn-prune-*.csv >/dev/null 2>&1; then ok "CSV backup file created"; else bad "CSV backup file created"; fi

echo "== AC3: --apply deletes =="
: > "$PSQL_LOG"
out="$(bash "$PRUNE" --pattern '^test-instance-' --apply --database-url 'postgres://x' --backup-dir "$WORK" 2>&1)"
rc=$?
log="$(cat "$PSQL_LOG")"
assert_eq "$rc" "0" "--apply exits 0"
assert_contains "$log" "TO STDOUT" "backup written before delete"
assert_contains "$log" "DELETE FROM seat_spawn" "--apply issues DELETE"
assert_contains "$out" "DELETED 3 row(s)" "reports deleted count"

echo "== AC3: setup errors =="
out="$(bash "$PRUNE" --database-url 'postgres://x' 2>&1)"; rc=$?
assert_eq "$rc" "2" "missing --pattern → exit 2"
assert_contains "$out" "--pattern" "explains missing pattern"

out="$(DATABASE_URL='' bash "$PRUNE" --pattern 'x' 2>&1)"; rc=$?
assert_eq "$rc" "2" "missing database URL → exit 2"

echo ""
echo "backend-prune-instances: $PASS/$TOTAL passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
